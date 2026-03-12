from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .constants import (
    DEFAULT_COLUMN,
    DEFAULT_LOGIN_TIMEOUT,
    DEFAULT_REPORT_DIR,
    DEFAULT_RETRIES,
    DEFAULT_START_ROW,
    DEFAULT_STATE_FILE,
    DEFAULT_UPLOAD_TIMEOUT,
    DEFAULT_VIDEO_DIR,
)
from .models import AppConfig
from .validation import validate_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量上传本地视频到飞书表格附件列。",
    )
    parser.add_argument("--url", required=True, help="目标飞书表格 URL。")
    parser.add_argument("--column", default=DEFAULT_COLUMN, help="目标列字母，默认 E。")
    parser.add_argument(
        "--start-row",
        type=int,
        default=DEFAULT_START_ROW,
        help="起始行号，默认 23。",
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=DEFAULT_VIDEO_DIR,
        help="视频目录。未指定 --files 时会自动扫描此目录。",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="显式指定上传顺序。相对路径优先按当前工作目录解析，找不到时回退到 video-dir。",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help="登录态 storage_state 文件路径。",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="运行报告输出目录。",
    )
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=DEFAULT_LOGIN_TIMEOUT,
        help="等待扫码登录的超时时间，单位秒。",
    )
    parser.add_argument(
        "--upload-timeout",
        type=int,
        default=DEFAULT_UPLOAD_TIMEOUT,
        help="等待单个文件上传完成的超时时间，单位秒。",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="单个文件失败后的重试次数，默认 2。",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="允许覆盖已有内容的单元格。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="使用无头模式运行浏览器。",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> AppConfig:
    args = build_parser().parse_args(argv)
    try:
        return validate_config(
            AppConfig(
                url=args.url,
                column=args.column,
                start_row=args.start_row,
                video_dir=args.video_dir.resolve(),
                state_file=args.state_file.resolve(),
                report_dir=args.report_dir.resolve(),
                login_timeout=args.login_timeout,
                upload_timeout=args.upload_timeout,
                retries=args.retries,
                overwrite=args.overwrite,
                headless=args.headless,
                files=tuple(args.files) if args.files else None,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
