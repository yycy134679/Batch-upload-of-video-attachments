from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    url: str
    column: str
    start_row: int
    video_dir: Path
    state_file: Path
    report_dir: Path
    login_timeout: int
    upload_timeout: int
    retries: int
    overwrite: bool
    headless: bool
    files: tuple[str, ...] | None


@dataclass(frozen=True)
class UploadPlanItem:
    index: int
    cell: str
    file_path: Path
    file_name: str
    size_bytes: int | None
    exists: bool


@dataclass
class UploadResult:
    index: int
    cell: str
    file_name: str
    file_path: str
    size_bytes: int | None
    status: str = "pending"
    reason: str = ""
    attempt_count: int = 0
    started_at: str = ""
    ended_at: str = ""
    duration_sec: float | None = None
    cell_display_before: str = ""
    cell_display_after: str = ""
    screenshot: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "cell": self.cell,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "reason": self.reason,
            "attempt_count": self.attempt_count,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_sec": self.duration_sec,
            "cell_display_before": self.cell_display_before,
            "cell_display_after": self.cell_display_after,
            "screenshot": self.screenshot,
        }


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    run_dir: Path
    summary_path: Path
    started_at: str
    ended_at: str
    stats: dict[str, int]
    results: tuple[UploadResult, ...]
