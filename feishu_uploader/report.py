from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .models import AppConfig, UploadResult


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def make_run_slug() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_summary(config: AppConfig, results: Sequence[UploadResult]) -> dict[str, Any]:
    stats: dict[str, int] = {}
    for result in results:
        stats[result.status] = stats.get(result.status, 0) + 1

    return {
        "config": {
            "url": config.url,
            "column": config.column,
            "start_row": config.start_row,
            "video_dir": str(config.video_dir),
            "state_file": str(config.state_file),
            "report_dir": str(config.report_dir),
            "login_timeout": config.login_timeout,
            "upload_timeout": config.upload_timeout,
            "retries": config.retries,
            "overwrite": config.overwrite,
            "headless": config.headless,
            "files": list(config.files) if config.files else None,
        },
        "stats": stats,
        "results": [result.to_dict() for result in results],
    }


def write_summary(
    run_dir: Path,
    config: AppConfig,
    results: Sequence[UploadResult],
    *,
    started_at: str,
    ended_at: str,
) -> Path:
    summary = build_summary(config, results)
    summary["started_at"] = started_at
    summary["ended_at"] = ended_at
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary_path
