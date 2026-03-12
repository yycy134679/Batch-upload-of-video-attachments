from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "飞书附件批量上传"
BUNDLE_IDENTIFIER = "local.feishu.videoattachmentuploader"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


@dataclass(frozen=True)
class RuntimePaths:
    resource_root: Path
    app_support_dir: Path
    state_file: Path
    report_dir: Path
    browser_dir: Path


def is_frozen(*, frozen: bool | None = None) -> bool:
    if frozen is not None:
        return frozen
    return bool(getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None))


def get_runtime_paths(
    *,
    home_dir: Path | None = None,
    frozen: bool | None = None,
    meipass: str | Path | None = None,
) -> RuntimePaths:
    resource_root = PROJECT_ROOT
    if is_frozen(frozen=frozen):
        resource_root = Path(meipass or getattr(sys, "_MEIPASS"))

    base_home = Path(home_dir) if home_dir is not None else Path.home()
    app_support_dir = base_home / "Library" / "Application Support" / APP_NAME
    return RuntimePaths(
        resource_root=resource_root,
        app_support_dir=app_support_dir,
        state_file=app_support_dir / "storage_state.json",
        report_dir=app_support_dir / "reports",
        browser_dir=app_support_dir / "playwright-browsers",
    )


def resource_path(*parts: str | Path) -> Path:
    return get_runtime_paths().resource_root.joinpath(*map(str, parts))


def configure_runtime_environment() -> RuntimePaths:
    paths = get_runtime_paths()
    paths.app_support_dir.mkdir(parents=True, exist_ok=True)
    paths.browser_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(paths.browser_dir))
    return paths
