"""
兼容入口脚本。

具体实现已拆分到 feishu_uploader/ 包，保留这个文件作为命令行入口，
同时继续导出常用符号，避免现有测试和调用方式失效。
"""

from feishu_uploader import (
    APP_NAME,
    AppConfig,
    BUNDLE_IDENTIFIER,
    RunCallbacks,
    RunOutcome,
    RuntimePaths,
    UploadPlanItem,
    UploadResult,
    build_parser,
    build_upload_plan,
    configure_runtime_environment,
    discover_video_files,
    get_runtime_paths,
    main,
    make_cell_ref,
    natural_sort_key,
    parse_args,
    resource_path,
    resolve_requested_file,
    response_matches,
    run,
    validate_config,
    write_summary,
)

__all__ = [
    "APP_NAME",
    "AppConfig",
    "BUNDLE_IDENTIFIER",
    "RunCallbacks",
    "RunOutcome",
    "RuntimePaths",
    "UploadPlanItem",
    "UploadResult",
    "build_parser",
    "parse_args",
    "configure_runtime_environment",
    "natural_sort_key",
    "make_cell_ref",
    "resolve_requested_file",
    "discover_video_files",
    "build_upload_plan",
    "get_runtime_paths",
    "resource_path",
    "validate_config",
    "response_matches",
    "write_summary",
    "run",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
