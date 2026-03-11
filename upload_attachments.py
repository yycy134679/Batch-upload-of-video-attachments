"""
兼容入口脚本。

具体实现已拆分到 feishu_uploader/ 包，保留这个文件作为命令行入口，
同时继续导出常用符号，避免现有测试和调用方式失效。
"""

from feishu_uploader import (
    AppConfig,
    UploadPlanItem,
    UploadResult,
    build_parser,
    build_upload_plan,
    discover_video_files,
    main,
    make_cell_ref,
    natural_sort_key,
    parse_args,
    resolve_requested_file,
    response_matches,
    run,
    write_summary,
)

__all__ = [
    "AppConfig",
    "UploadPlanItem",
    "UploadResult",
    "build_parser",
    "parse_args",
    "natural_sort_key",
    "make_cell_ref",
    "resolve_requested_file",
    "discover_video_files",
    "build_upload_plan",
    "response_matches",
    "write_summary",
    "run",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
