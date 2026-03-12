from __future__ import annotations

from .cli import build_parser, parse_args
from .file_plan import (
    build_upload_plan,
    discover_video_files,
    make_cell_ref,
    natural_sort_key,
    resolve_requested_file,
)
from .models import AppConfig, RunOutcome, UploadPlanItem, UploadResult
from .playwright_ops import response_matches
from .report import write_summary
from .runtime import (
    APP_NAME,
    BUNDLE_IDENTIFIER,
    RuntimePaths,
    configure_runtime_environment,
    get_runtime_paths,
    resource_path,
)
from .validation import validate_config

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


def __getattr__(name: str):
    if name in {"RunCallbacks", "main", "run"}:
        from .runner import RunCallbacks, main, run

        exported = {
            "RunCallbacks": RunCallbacks,
            "main": main,
            "run": run,
        }
        return exported[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
