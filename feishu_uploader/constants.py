import re

from .runtime import PACKAGE_DIR, PROJECT_ROOT, get_runtime_paths


RUNTIME_PATHS = get_runtime_paths()
BROWSER_DIR = RUNTIME_PATHS.browser_dir
DEFAULT_COLUMN = "E"
DEFAULT_START_ROW = 23
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "media"
DEFAULT_STATE_FILE = RUNTIME_PATHS.state_file
DEFAULT_REPORT_DIR = RUNTIME_PATHS.report_dir
DEFAULT_LOGIN_TIMEOUT = 300
DEFAULT_UPLOAD_TIMEOUT = 120
DEFAULT_RETRIES = 2
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
CELL_REF_PATTERN = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")
