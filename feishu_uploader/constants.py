from pathlib import Path
import re


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DEFAULT_URL = "https://bytedance.larkoffice.com/wiki/GxGswlGQfiB0PSkL8ItcABlKnig"
DEFAULT_COLUMN = "E"
DEFAULT_START_ROW = 23
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "media"
DEFAULT_STATE_FILE = PROJECT_ROOT / ".feishu_storage_state.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "output" / "reports"
DEFAULT_LOGIN_TIMEOUT = 300
DEFAULT_UPLOAD_TIMEOUT = 120
DEFAULT_RETRIES = 2
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
CELL_REF_PATTERN = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")
