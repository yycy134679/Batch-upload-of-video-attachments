from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import VIDEO_SUFFIXES
from .models import AppConfig, UploadPlanItem


def natural_sort_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def make_cell_ref(column: str, row: int) -> str:
    return f"{column}{row}"


def resolve_requested_file(raw_path: str, video_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate

    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    return (video_dir / candidate).resolve()


def discover_video_files(video_dir: Path) -> list[Path]:
    if not video_dir.exists():
        return []
    return sorted(
        [
            path.resolve()
            for path in video_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        ],
        key=lambda path: natural_sort_key(path.name),
    )


def build_upload_plan(config: AppConfig) -> list[UploadPlanItem]:
    if config.files:
        file_paths = [resolve_requested_file(raw, config.video_dir) for raw in config.files]
    else:
        file_paths = discover_video_files(config.video_dir)

    if not file_paths:
        raise FileNotFoundError(f"没有找到可上传的视频文件: {config.video_dir}")

    plan: list[UploadPlanItem] = []
    for index, file_path in enumerate(file_paths):
        exists = file_path.exists()
        size_bytes = file_path.stat().st_size if exists else None
        plan.append(
            UploadPlanItem(
                index=index,
                cell=make_cell_ref(config.column, config.start_row + index),
                file_path=file_path,
                file_name=file_path.name,
                size_bytes=size_bytes,
                exists=exists,
            )
        )
    return plan
