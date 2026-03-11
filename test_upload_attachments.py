import json
import tempfile
import unittest
from pathlib import Path

import upload_attachments as ua


class NaturalSortKeyTests(unittest.TestCase):
    def test_sorts_human_friendly_file_names(self) -> None:
        values = ["10.mp4", "2.mp4", "1.mp4", "clip-11.mp4", "clip-2.mp4"]
        self.assertEqual(
            sorted(values, key=ua.natural_sort_key),
            ["1.mp4", "2.mp4", "10.mp4", "clip-2.mp4", "clip-11.mp4"],
        )


class UploadPlanTests(unittest.TestCase):
    def make_config(
        self,
        *,
        video_dir: Path,
        files: tuple[str, ...] | None = None,
    ) -> ua.AppConfig:
        return ua.AppConfig(
            url="https://example.com/wiki/demo",
            column="E",
            start_row=23,
            video_dir=video_dir,
            state_file=video_dir / ".state.json",
            report_dir=video_dir / "reports",
            login_timeout=300,
            upload_timeout=120,
            retries=2,
            overwrite=False,
            headless=False,
            files=files,
        )

    def test_build_upload_plan_from_directory_uses_natural_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_dir = Path(tmp_dir)
            for name in ["10.mp4", "2.mp4", "1.mp4", "notes.txt"]:
                (video_dir / name).write_bytes(b"demo")

            plan = ua.build_upload_plan(self.make_config(video_dir=video_dir))

            self.assertEqual([item.file_name for item in plan], ["1.mp4", "2.mp4", "10.mp4"])
            self.assertEqual([item.cell for item in plan], ["E23", "E24", "E25"])

    def test_build_upload_plan_with_explicit_files_keeps_order_and_marks_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_dir = Path(tmp_dir)
            (video_dir / "2.mp4").write_bytes(b"demo")

            plan = ua.build_upload_plan(
                self.make_config(
                    video_dir=video_dir,
                    files=("2.mp4", "missing.mp4"),
                )
            )

            self.assertEqual([item.cell for item in plan], ["E23", "E24"])
            self.assertTrue(plan[0].exists)
            self.assertFalse(plan[1].exists)


class SummaryTests(unittest.TestCase):
    def make_config(self, root: Path) -> ua.AppConfig:
        return ua.AppConfig(
            url="https://example.com/wiki/demo",
            column="E",
            start_row=23,
            video_dir=root / "media",
            state_file=root / ".state.json",
            report_dir=root / "reports",
            login_timeout=300,
            upload_timeout=120,
            retries=2,
            overwrite=False,
            headless=False,
            files=None,
        )

    def test_write_summary_creates_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            run_dir = root / "reports" / "run-1"
            run_dir.mkdir(parents=True)
            config = self.make_config(root)
            results = [
                ua.UploadResult(
                    index=0,
                    cell="E23",
                    file_name="1.mp4",
                    file_path=str(root / "media" / "1.mp4"),
                    size_bytes=1024,
                    status="uploaded",
                    attempt_count=1,
                    started_at="2026-03-11T11:00:00+08:00",
                    ended_at="2026-03-11T11:00:03+08:00",
                    duration_sec=3.0,
                ),
                ua.UploadResult(
                    index=1,
                    cell="E24",
                    file_name="2.mp4",
                    file_path=str(root / "media" / "2.mp4"),
                    size_bytes=None,
                    status="skipped_missing",
                    reason="file_not_found",
                    attempt_count=0,
                    started_at="2026-03-11T11:00:03+08:00",
                    ended_at="2026-03-11T11:00:03+08:00",
                    duration_sec=0.0,
                ),
            ]

            summary_path = ua.write_summary(
                run_dir,
                config,
                results,
                started_at="2026-03-11T11:00:00+08:00",
                ended_at="2026-03-11T11:00:03+08:00",
            )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["uploaded"], 1)
            self.assertEqual(payload["stats"]["skipped_missing"], 1)
            self.assertEqual(payload["results"][0]["cell"], "E23")


class ResponseMatcherTests(unittest.TestCase):
    def test_response_matches_method_status_and_url(self) -> None:
        request = type("Request", (), {"method": "POST"})()
        response = type(
            "Response",
            (),
            {
                "request": request,
                "url": "https://example.com/space/api/box/upload/finish/",
                "status": 200,
            },
        )()

        self.assertTrue(
            ua.response_matches(
                response,
                method="POST",
                url_substring="/space/api/box/upload/finish/",
                status=200,
            )
        )
        self.assertFalse(
            ua.response_matches(
                response,
                method="GET",
                url_substring="/space/api/box/upload/finish/",
                status=200,
            )
        )


if __name__ == "__main__":
    unittest.main()
