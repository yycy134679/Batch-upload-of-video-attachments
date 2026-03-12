from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from .constants import VIDEO_SUFFIXES
from .models import AppConfig


SINGLE_COLUMN_PATTERN = re.compile(r"^[A-Z]$")


def _has_supported_videos(video_dir: Path) -> bool:
    if not video_dir.exists() or not video_dir.is_dir():
        return False
    return any(
        path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        for path in video_dir.iterdir()
    )


def validate_config(config: AppConfig) -> AppConfig:
    normalized = replace(
        config,
        url=config.url.strip(),
        column=config.column.strip().upper(),
    )
    if not normalized.url:
        raise ValueError("请填写飞书表格 URL。")
    if not SINGLE_COLUMN_PATTERN.fullmatch(normalized.column):
        raise ValueError("目标列必须是单个大写字母 A-Z。")
    if normalized.start_row <= 0:
        raise ValueError("起始行号必须大于 0。")
    if normalized.login_timeout <= 0 or normalized.upload_timeout <= 0:
        raise ValueError("登录超时和上传超时都必须大于 0。")
    if normalized.retries < 0:
        raise ValueError("重试次数不能小于 0。")
    if normalized.files:
        return normalized
    if not normalized.video_dir.exists() or not normalized.video_dir.is_dir():
        raise FileNotFoundError(f"视频目录不存在: {normalized.video_dir}")
    if not _has_supported_videos(normalized.video_dir):
        raise FileNotFoundError(f"视频目录中没有可上传的视频文件: {normalized.video_dir}")
    return normalized
