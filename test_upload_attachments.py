import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import upload_attachments as ua

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from feishu_uploader.gui import UploadWindow, build_gui_config
from feishu_uploader import playwright_ops


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


class ConfigValidationTests(unittest.TestCase):
    def make_config(self, *, root: Path, url: str = "https://example.com/wiki/demo") -> ua.AppConfig:
        return ua.AppConfig(
            url=url,
            column="E",
            start_row=23,
            video_dir=root,
            state_file=root / ".state.json",
            report_dir=root / "reports",
            login_timeout=300,
            upload_timeout=120,
            retries=2,
            overwrite=False,
            headless=False,
            files=None,
        )

    def test_validate_config_requires_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")

            with self.assertRaisesRegex(ValueError, "请填写飞书表格 URL"):
                ua.validate_config(self.make_config(root=root, url="   "))

    def test_validate_config_requires_video_files_for_directory_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            with self.assertRaisesRegex(FileNotFoundError, "没有可上传的视频文件"):
                ua.validate_config(self.make_config(root=root))

    def test_validate_config_rejects_invalid_start_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")
            config = self.make_config(root=root)
            config = ua.AppConfig(
                url=config.url,
                column=config.column,
                start_row=0,
                video_dir=config.video_dir,
                state_file=config.state_file,
                report_dir=config.report_dir,
                login_timeout=config.login_timeout,
                upload_timeout=config.upload_timeout,
                retries=config.retries,
                overwrite=config.overwrite,
                headless=config.headless,
                files=config.files,
            )

            with self.assertRaisesRegex(ValueError, "起始行号必须大于 0"):
                ua.validate_config(config)


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
            self.assertFalse(payload["cancelled"])
            self.assertEqual(payload["planned_count"], 2)
            self.assertEqual(payload["processed_count"], 2)
            self.assertEqual(payload["remaining_count"], 0)
            self.assertEqual(payload["stats"]["uploaded"], 1)
            self.assertEqual(payload["stats"]["skipped_missing"], 1)
            self.assertEqual(payload["results"][0]["cell"], "E23")


class RunnerCancellationTests(unittest.TestCase):
    def make_config(self, root: Path) -> ua.AppConfig:
        return ua.AppConfig(
            url="https://example.com/wiki/demo",
            column="E",
            start_row=23,
            video_dir=root,
            state_file=root / ".state.json",
            report_dir=root / "reports",
            login_timeout=300,
            upload_timeout=120,
            retries=2,
            overwrite=False,
            headless=False,
            files=None,
        )

    @mock.patch("feishu_uploader.runner.ensure_playwright_available")
    @mock.patch("feishu_uploader.runner.sync_playwright")
    def test_run_stops_before_processing_when_stop_requested(
        self,
        sync_playwright: mock.Mock,
        _ensure_playwright_available: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")
            logs: list[str] = []

            outcome = ua.run(
                self.make_config(root),
                callbacks=ua.RunCallbacks(log=logs.append),
                should_stop=lambda: True,
            )

            self.assertTrue(outcome.cancelled)
            self.assertEqual(outcome.exit_code, 130)
            self.assertEqual(outcome.planned_count, 1)
            self.assertEqual(outcome.processed_count, 0)
            self.assertEqual(outcome.remaining_count, 1)
            self.assertEqual(outcome.results, ())
            sync_playwright.assert_not_called()

            payload = json.loads(outcome.summary_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["cancelled"])
            self.assertEqual(payload["processed_count"], 0)
            self.assertEqual(payload["remaining_count"], 1)
            self.assertTrue(any("开始处理前结束" in line for line in logs))

    @mock.patch("feishu_uploader.runner.ensure_playwright_available")
    @mock.patch("feishu_uploader.runner.wait_for_login")
    @mock.patch("feishu_uploader.runner.upload_plan_item")
    @mock.patch("feishu_uploader.runner.sync_playwright")
    def test_run_stops_after_first_item_when_stop_requested(
        self,
        sync_playwright: mock.Mock,
        upload_plan_item: mock.Mock,
        _wait_for_login: mock.Mock,
        _ensure_playwright_available: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")
            (root / "2.mp4").write_bytes(b"demo")
            logs: list[str] = []
            stop_requested = False

            page = mock.Mock()
            context = mock.Mock()
            context.new_page.return_value = page
            browser = mock.Mock()
            browser.new_context.return_value = context
            playwright = mock.Mock()
            playwright.chromium.launch.return_value = browser
            sync_playwright.return_value = contextlib.nullcontext(playwright)

            def fake_upload_plan_item(*args, **kwargs):
                nonlocal stop_requested
                stop_requested = True
                result = args[2]
                result.status = "uploaded"
                result.ended_at = "2026-03-13T10:00:03+08:00"
                result.duration_sec = 3.0
                return result

            upload_plan_item.side_effect = fake_upload_plan_item

            outcome = ua.run(
                self.make_config(root),
                callbacks=ua.RunCallbacks(log=logs.append),
                should_stop=lambda: stop_requested,
            )

            self.assertTrue(outcome.cancelled)
            self.assertEqual(outcome.exit_code, 130)
            self.assertEqual(outcome.planned_count, 2)
            self.assertEqual(outcome.processed_count, 1)
            self.assertEqual(outcome.remaining_count, 1)
            self.assertEqual(len(outcome.results), 1)
            self.assertEqual(outcome.results[0].status, "uploaded")
            upload_plan_item.assert_called_once()
            self.assertTrue(any("E24" in line for line in logs))

            payload = json.loads(outcome.summary_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["cancelled"])
            self.assertEqual(payload["processed_count"], 1)
            self.assertEqual(payload["remaining_count"], 1)


class RuntimePathTests(unittest.TestCase):
    def test_get_runtime_paths_source_mode_uses_application_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            home_dir = Path(tmp_dir)
            paths = ua.get_runtime_paths(home_dir=home_dir, frozen=False)

            app_support_dir = home_dir / "Library" / "Application Support" / ua.APP_NAME
            self.assertEqual(paths.resource_root, Path(__file__).resolve().parent)
            self.assertEqual(paths.app_support_dir, app_support_dir)
            self.assertEqual(paths.state_file, app_support_dir / "storage_state.json")
            self.assertEqual(paths.report_dir, app_support_dir / "reports")
            self.assertEqual(paths.browser_dir, app_support_dir / "playwright-browsers")

    def test_get_runtime_paths_frozen_mode_uses_meipass_for_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            home_dir = Path(tmp_dir)
            paths = ua.get_runtime_paths(
                home_dir=home_dir,
                frozen=True,
                meipass="/tmp/frozen-bundle",
            )

            self.assertEqual(paths.resource_root, Path("/tmp/frozen-bundle"))
            self.assertEqual(
                paths.app_support_dir,
                home_dir / "Library" / "Application Support" / ua.APP_NAME,
            )


class PlaywrightBootstrapTests(unittest.TestCase):
    def test_has_saved_login_state_returns_false_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            self.assertFalse(playwright_ops.has_saved_login_state(state_file))

    def test_has_saved_login_state_returns_false_for_expired_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {"domain": ".feishu.cn", "expires": 10},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(playwright_ops.has_saved_login_state(state_file, now_ts=100))

    def test_has_saved_login_state_returns_true_for_future_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {"domain": ".larkoffice.com", "expires": 200},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(playwright_ops.has_saved_login_state(state_file, now_ts=100))

    def test_clear_saved_login_state_removes_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            state_file.write_text("{}", encoding="utf-8")

            removed = playwright_ops.clear_saved_login_state(state_file)

            self.assertTrue(removed)
            self.assertFalse(state_file.exists())

    def test_clear_saved_login_state_returns_false_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"

            removed = playwright_ops.clear_saved_login_state(state_file)

            self.assertFalse(removed)

    @mock.patch.object(playwright_ops, "sync_playwright", object())
    @mock.patch.object(playwright_ops, "playwright_browser_installed", return_value=True)
    @mock.patch.object(playwright_ops, "install_playwright_browser")
    def test_ensure_playwright_available_skips_install_when_browser_present(
        self,
        install_browser: mock.Mock,
        _browser_installed: mock.Mock,
    ) -> None:
        playwright_ops.ensure_playwright_available(install=True)
        install_browser.assert_not_called()

    @mock.patch.object(playwright_ops, "sync_playwright", object())
    @mock.patch.object(playwright_ops, "playwright_browser_installed", side_effect=[False, True])
    @mock.patch.object(playwright_ops, "install_playwright_browser")
    def test_ensure_playwright_available_installs_missing_browser(
        self,
        install_browser: mock.Mock,
        _browser_installed: mock.Mock,
    ) -> None:
        playwright_ops.ensure_playwright_available(install=True)
        install_browser.assert_called_once()

    @mock.patch.object(playwright_ops, "sync_playwright", object())
    @mock.patch.object(playwright_ops, "compute_driver_executable", return_value=("/tmp/node", "/tmp/cli.js"))
    @mock.patch.object(playwright_ops, "get_driver_env", return_value={"PW_LANG_NAME": "python"})
    def test_build_playwright_install_command_includes_browser_dir_env(
        self,
        _get_driver_env: mock.Mock,
        _compute_driver_executable: mock.Mock,
    ) -> None:
        command, env = playwright_ops.build_playwright_install_command()

        self.assertEqual(command, ["/tmp/node", "/tmp/cli.js", "install", "chromium"])
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", env)
        self.assertTrue(env["PLAYWRIGHT_BROWSERS_PATH"].endswith("/playwright-browsers"))


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


class PlaywrightSheetUiTests(unittest.TestCase):
    def test_wait_for_sheet_ready_requires_surface_formula_bar_and_stable_state(self) -> None:
        page = mock.Mock()
        insert_button = mock.Mock()
        sheet_container = mock.Mock()
        sheet_canvas = mock.Mock()
        formula_bar = mock.Mock()

        with (
            mock.patch.object(playwright_ops, "get_insert_button", return_value=insert_button),
            mock.patch.object(playwright_ops, "get_loaded_sheet_container", return_value=sheet_container),
            mock.patch.object(playwright_ops, "get_sheet_canvas", return_value=sheet_canvas),
            mock.patch.object(playwright_ops, "get_formula_bar", return_value=formula_bar),
            mock.patch.object(playwright_ops, "current_cell_ref", side_effect=["A1", "A1"]),
        ):
            playwright_ops.wait_for_sheet_ready(page, timeout_ms=1_500)

        page.wait_for_load_state.assert_called_with("domcontentloaded", timeout=2_000)
        insert_button.wait_for.assert_called_with(state="visible", timeout=2_000)
        sheet_container.wait_for.assert_called_with(state="visible", timeout=2_000)
        sheet_canvas.wait_for.assert_called_with(state="visible", timeout=2_000)
        formula_bar.wait_for.assert_called_with(state="visible", timeout=2_000)
        self.assertEqual(page.wait_for_timeout.call_count, 1)

    def test_read_selected_cell_display_prefers_formula_bar(self) -> None:
        page = mock.Mock()
        formula_bar = mock.Mock()

        with (
            mock.patch.object(playwright_ops, "get_formula_bar", return_value=formula_bar),
            mock.patch.object(playwright_ops, "read_textbox_value", return_value="demo.mp4"),
        ):
            result = playwright_ops.read_selected_cell_display(page)

        self.assertEqual(result, "demo.mp4")
        formula_bar.wait_for.assert_called_once_with(state="visible", timeout=2_000)
        page.evaluate.assert_not_called()

    def test_read_selected_cell_display_falls_back_to_nearby_editor_when_formula_bar_missing(self) -> None:
        page = mock.Mock()
        page.evaluate.return_value = " fallback.mp4 "
        formula_bar = mock.Mock()
        formula_bar.wait_for.side_effect = RuntimeError("missing")

        with mock.patch.object(playwright_ops, "get_formula_bar", return_value=formula_bar):
            result = playwright_ops.read_selected_cell_display(page)

        self.assertEqual(result, "fallback.mp4")
        page.evaluate.assert_called_once()


class PlaywrightUploadCancellationTests(unittest.TestCase):
    @mock.patch.object(playwright_ops, "utc_now", return_value="2026-03-13T10:00:00+08:00")
    @mock.patch.object(playwright_ops, "take_failure_screenshot", return_value=Path("/tmp/failure.png"))
    @mock.patch.object(playwright_ops, "refresh_sheet")
    @mock.patch.object(playwright_ops, "recover_page_state")
    @mock.patch.object(playwright_ops, "upload_file_once", side_effect=RuntimeError("boom"))
    @mock.patch.object(playwright_ops, "read_selected_cell_display", return_value="")
    @mock.patch.object(playwright_ops, "navigate_to_cell")
    def test_upload_plan_item_stops_retry_when_stop_requested(
        self,
        _navigate_to_cell: mock.Mock,
        _read_selected_cell_display: mock.Mock,
        upload_file_once: mock.Mock,
        recover_page_state: mock.Mock,
        refresh_sheet: mock.Mock,
        take_failure_screenshot: mock.Mock,
        _utc_now: mock.Mock,
    ) -> None:
        page = mock.Mock()
        plan_item = ua.UploadPlanItem(
            index=0,
            cell="E23",
            file_path=Path("/tmp/1.mp4"),
            file_name="1.mp4",
            size_bytes=1024,
            exists=True,
        )
        result = ua.UploadResult(
            index=0,
            cell="E23",
            file_name="1.mp4",
            file_path="/tmp/1.mp4",
            size_bytes=1024,
            started_at="2026-03-13T09:59:57+08:00",
        )

        returned = playwright_ops.upload_plan_item(
            page,
            plan_item,
            result,
            overwrite=False,
            upload_timeout=120,
            retries=2,
            login_timeout=300,
            run_dir=Path("/tmp"),
            should_stop=lambda: True,
        )

        self.assertEqual(returned.status, "failed")
        self.assertEqual(returned.reason, "boom")
        self.assertEqual(returned.attempt_count, 1)
        self.assertEqual(returned.screenshot, "/tmp/failure.png")
        upload_file_once.assert_called_once()
        recover_page_state.assert_called_once()
        refresh_sheet.assert_not_called()
        take_failure_screenshot.assert_called_once()


class GuiConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def write_saved_login_state(self, state_file: Path) -> None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "cookies": [
                        {"domain": ".feishu.cn", "expires": 4102444800},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_build_gui_config_maps_form_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")

            config = build_gui_config(
                url="https://example.com/wiki/demo",
                video_dir=str(root),
                column="E",
                start_row=2,
                overwrite=True,
                headless=True,
            )

            self.assertEqual(config.url, "https://example.com/wiki/demo")
            self.assertEqual(config.video_dir, root.resolve())
            self.assertEqual(config.column, "E")
            self.assertEqual(config.start_row, 2)
            self.assertTrue(config.overwrite)
            self.assertTrue(config.headless)

    def test_build_gui_config_rejects_empty_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")

            with self.assertRaisesRegex(ValueError, "请填写飞书表格 URL"):
                build_gui_config(
                    url=" ",
                    video_dir=str(root),
                    column="E",
                    start_row=2,
                    overwrite=False,
                    headless=False,
                )

    def test_window_build_current_config_uses_widget_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "clip.mp4").write_bytes(b"demo")
            window = UploadWindow(auto_initialize_runtime=False)
            self.addCleanup(window.close)

            window.url_input.setText("https://example.com/wiki/demo")
            window.video_dir_input.setText(str(root))
            window.column_combo.setCurrentText("E")
            window.start_row_input.setValue(2)
            window.overwrite_checkbox.setChecked(True)
            window.run_mode_combo.setCurrentIndex(1)

            config = window.build_current_config()

            self.assertEqual(config.video_dir, root.resolve())
            self.assertEqual(config.column, "E")
            self.assertEqual(config.start_row, 2)
            self.assertTrue(config.overwrite)
            self.assertTrue(config.headless)

    def test_window_defaults_to_headful_upload_mode(self) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)

        self.assertEqual(window.run_mode_combo.currentText(), "前台运行（显示浏览器）")
        self.assertFalse(window.current_headless_mode())

    @mock.patch("feishu_uploader.gui.has_saved_login_state", return_value=True)
    def test_window_starts_with_form_disabled_until_runtime_ready(self, _has_login: mock.Mock) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)

        self.assertFalse(window.url_input.isEnabled())
        self.assertFalse(window.start_button.isEnabled())

        window.on_runtime_init_finished()

        self.assertTrue(window.url_input.isEnabled())
        self.assertTrue(window.start_button.isEnabled())

    @mock.patch("feishu_uploader.gui.QMessageBox.information")
    @mock.patch("feishu_uploader.gui.has_saved_login_state", return_value=False)
    def test_window_runtime_ready_without_login_prompts_user(
        self,
        _has_login: mock.Mock,
        information: mock.Mock,
    ) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)

        window.on_runtime_init_finished()

        self.assertTrue(window.login_button.isEnabled())
        self.assertFalse(window.start_button.isEnabled())
        self.assertEqual(window.summary_label.text(), "运行环境已就绪，请先点击“登录飞书”完成登录。")
        information.assert_called_once()

    def test_window_runtime_ready_with_saved_state_enables_clear_login_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            self.write_saved_login_state(state_file)

            with mock.patch("feishu_uploader.gui.DEFAULT_STATE_FILE", state_file):
                window = UploadWindow(auto_initialize_runtime=False)
                self.addCleanup(window.close)

                window.on_runtime_init_finished()

                self.assertTrue(window.start_button.isEnabled())
                self.assertTrue(window.clear_login_button.isEnabled())

    @mock.patch("feishu_uploader.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel)
    def test_clear_login_flow_cancel_keeps_state_and_summary(
        self,
        question: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            self.write_saved_login_state(state_file)

            with mock.patch("feishu_uploader.gui.DEFAULT_STATE_FILE", state_file):
                window = UploadWindow(auto_initialize_runtime=False)
                self.addCleanup(window.close)
                window.on_runtime_init_finished()

                summary_before = window.summary_label.text()
                window.clear_login_flow()

                self.assertTrue(state_file.exists())
                self.assertEqual(window.summary_label.text(), summary_before)
                self.assertTrue(window.start_button.isEnabled())
                question.assert_called_once()

    @mock.patch("feishu_uploader.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes)
    def test_clear_login_flow_confirm_clears_state_and_disables_upload(
        self,
        question: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            self.write_saved_login_state(state_file)

            with mock.patch("feishu_uploader.gui.DEFAULT_STATE_FILE", state_file):
                window = UploadWindow(auto_initialize_runtime=False)
                self.addCleanup(window.close)
                window.on_runtime_init_finished()

                window.clear_login_flow()

                self.assertFalse(state_file.exists())
                self.assertEqual(window.summary_label.text(), "运行环境已就绪，请先点击“登录飞书”完成登录。")
                self.assertTrue(window.login_button.isEnabled())
                self.assertFalse(window.start_button.isEnabled())
                self.assertFalse(window.clear_login_button.isEnabled())
                self.assertIn("已清理本地飞书登录信息，可重新登录其他账号。", window.log_output.toPlainText())
                question.assert_called_once()

    @mock.patch("feishu_uploader.gui.QMessageBox.critical")
    @mock.patch("feishu_uploader.gui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes)
    def test_clear_login_flow_delete_failure_shows_error_without_resetting_state(
        self,
        question: mock.Mock,
        critical: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_file = Path(tmp_dir) / "storage_state.json"
            self.write_saved_login_state(state_file)

            with (
                mock.patch("feishu_uploader.gui.DEFAULT_STATE_FILE", state_file),
                mock.patch("feishu_uploader.gui.clear_saved_login_state", side_effect=OSError("permission denied")),
            ):
                window = UploadWindow(auto_initialize_runtime=False)
                self.addCleanup(window.close)
                window.on_runtime_init_finished()

                summary_before = window.summary_label.text()
                window.clear_login_flow()

                self.assertTrue(state_file.exists())
                self.assertEqual(window.summary_label.text(), summary_before)
                self.assertTrue(window.start_button.isEnabled())
                self.assertIn("清理登录信息失败", window.log_output.toPlainText())
                question.assert_called_once()
                critical.assert_called_once()

    @mock.patch("feishu_uploader.gui.QThread.start", autospec=True)
    def test_window_can_start_runtime_initialization_from_pending_state(
        self,
        _thread_start: mock.Mock,
    ) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)

        window.start_runtime_initialization()

        self.assertIsNotNone(window._runtime_thread)
        self.assertIsNotNone(window._runtime_worker)
        self.assertTrue(window._runtime_initializing)

    @mock.patch("feishu_uploader.gui.QMessageBox.exec", return_value=0)
    def test_window_runtime_init_failure_keeps_retry_available(self, _exec: mock.Mock) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)

        window.on_runtime_init_failed("初始化失败")

        self.assertFalse(window.start_button.isEnabled())
        self.assertFalse(window.retry_init_button.isHidden())
        self.assertEqual(window.summary_label.text(), "运行环境初始化失败，请重试或退出应用。")

    @mock.patch("feishu_uploader.gui.has_saved_login_state", return_value=True)
    @mock.patch("feishu_uploader.gui.QThread.start", autospec=True)
    def test_start_upload_enables_stop_button(
        self,
        _thread_start: mock.Mock,
        _has_login: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "1.mp4").write_bytes(b"demo")
            window = UploadWindow(auto_initialize_runtime=False)
            self.addCleanup(window.close)
            window._runtime_ready = True
            window._runtime_initializing = False
            window._has_saved_login = True
            window.url_input.setText("https://example.com/wiki/demo")
            window.video_dir_input.setText(str(root))
            window.column_combo.setCurrentText("E")
            window.start_row_input.setValue(23)

            window.start_upload()

            self.assertFalse(window.start_button.isEnabled())
            self.assertTrue(window.stop_button.isEnabled())
            self.assertIsNotNone(window._worker)

    def test_stop_upload_requests_safe_stop_and_updates_summary(self) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)
        self.addCleanup(setattr, window, "_thread", None)
        thread = mock.Mock()
        thread.isRunning.return_value = True
        worker = mock.Mock()
        window._thread = thread
        window._worker = worker
        window.stop_button.setEnabled(True)

        window.stop_upload()

        worker.request_stop.assert_called_once()
        self.assertTrue(window._upload_stop_requested)
        self.assertFalse(window.stop_button.isEnabled())
        self.assertEqual(window.summary_label.text(), "正在等待当前文件处理完成后终止...")
        self.assertIn("已收到终止上传请求", window.log_output.toPlainText())

    def test_on_run_finished_marks_pending_rows_as_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir) / "reports" / "run-1"
            run_dir.mkdir(parents=True)
            summary_path = run_dir / "summary.json"
            summary_path.write_text("{}", encoding="utf-8")

            window = UploadWindow(auto_initialize_runtime=False)
            self.addCleanup(window.close)
            window._runtime_ready = True
            window._has_saved_login = True
            window._set_form_enabled(True)
            window._set_upload_stop_state(True)

            plan = [
                ua.UploadPlanItem(
                    index=0,
                    cell="E23",
                    file_path=Path("/tmp/1.mp4"),
                    file_name="1.mp4",
                    size_bytes=1024,
                    exists=True,
                ),
                ua.UploadPlanItem(
                    index=1,
                    cell="E24",
                    file_path=Path("/tmp/2.mp4"),
                    file_name="2.mp4",
                    size_bytes=1024,
                    exists=True,
                ),
            ]
            window.on_run_started(plan, str(run_dir))
            window.on_item_finished(
                ua.UploadResult(
                    index=0,
                    cell="E23",
                    file_name="1.mp4",
                    file_path="/tmp/1.mp4",
                    size_bytes=1024,
                    status="uploaded",
                ),
                2,
            )

            outcome = ua.RunOutcome(
                exit_code=130,
                cancelled=True,
                run_dir=run_dir,
                summary_path=summary_path,
                started_at="2026-03-13T10:00:00+08:00",
                ended_at="2026-03-13T10:00:03+08:00",
                planned_count=2,
                processed_count=1,
                remaining_count=1,
                stats={"uploaded": 1},
                results=(
                    ua.UploadResult(
                        index=0,
                        cell="E23",
                        file_name="1.mp4",
                        file_path="/tmp/1.mp4",
                        size_bytes=1024,
                        status="uploaded",
                    ),
                ),
            )

            window.on_run_finished(outcome)

            self.assertEqual(window.summary_label.text(), "已终止：上传成功 1，未处理 1 个")
            self.assertEqual(window.progress_table.item(0, 2).text(), "上传成功")
            self.assertEqual(window.progress_table.item(1, 2).text(), "已终止")
            self.assertEqual(window.progress_table.item(1, 3).text(), "用户终止，未开始处理")
            self.assertFalse(window.stop_button.isEnabled())

    @mock.patch("feishu_uploader.gui.QMessageBox.information")
    def test_close_event_shows_stop_waiting_message_after_stop_requested(
        self,
        information: mock.Mock,
    ) -> None:
        window = UploadWindow(auto_initialize_runtime=False)
        self.addCleanup(window.close)
        self.addCleanup(setattr, window, "_thread", None)
        thread = mock.Mock()
        thread.isRunning.return_value = True
        window._thread = thread
        window._upload_stop_requested = True
        event = QCloseEvent()

        window.closeEvent(event)

        information.assert_called_once()
        self.assertIn("正在等待当前文件处理完成后终止", information.call_args.args[2])
        self.assertFalse(event.isAccepted())


if __name__ == "__main__":
    unittest.main()
