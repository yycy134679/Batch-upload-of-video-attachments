#!/bin/zsh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3。"
  exit 1
fi

cd "$PROJECT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

echo
echo "开发环境已准备完成。"
echo "启动 GUI："
echo "  source .venv/bin/activate && python -m feishu_uploader.gui"
echo
echo "构建 macOS .app："
echo "  source .venv/bin/activate && scripts/build_macos_app.sh"
