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
    return build_summary_with_run_state(
        config,
        results,
        cancelled=False,
        planned_count=len(results),
        processed_count=len(results),
        remaining_count=0,
    )


def build_summary_with_run_state(
    config: AppConfig,
    results: Sequence[UploadResult],
    *,
    cancelled: bool,
    planned_count: int,
    processed_count: int,
    remaining_count: int,
) -> dict[str, Any]:
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
        "cancelled": cancelled,
        "planned_count": planned_count,
        "processed_count": processed_count,
        "remaining_count": remaining_count,
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
    cancelled: bool = False,
    planned_count: int | None = None,
    processed_count: int | None = None,
    remaining_count: int | None = None,
) -> Path:
    resolved_planned_count = planned_count if planned_count is not None else len(results)
    resolved_processed_count = processed_count if processed_count is not None else len(results)
    if remaining_count is None:
        resolved_remaining_count = max(resolved_planned_count - resolved_processed_count, 0)
    else:
        resolved_remaining_count = remaining_count

    summary = build_summary_with_run_state(
        config,
        results,
        cancelled=cancelled,
        planned_count=resolved_planned_count,
        processed_count=resolved_processed_count,
        remaining_count=resolved_remaining_count,
    )
    summary["started_at"] = started_at
    summary["ended_at"] = ended_at
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary_path
