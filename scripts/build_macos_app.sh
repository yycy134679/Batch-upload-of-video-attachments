#!/bin/zsh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
ICON_SOURCE="$PROJECT_DIR/media/icon.png"
BUILD_DIR="$PROJECT_DIR/build/macos"
ICONSET_DIR="$BUILD_DIR/AppIcon.iconset"
ICON_PATH="$BUILD_DIR/AppIcon.icns"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "未找到 .venv，请先运行 install.command。"
  exit 1
fi

if [[ ! -f "$ICON_SOURCE" ]]; then
  echo "未找到图标源文件：$ICON_SOURCE"
  exit 1
fi

cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install -r requirements-dev.txt

rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

render_icon() {
  local size="$1"
  local name="$2"
  sips -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET_DIR/$name" >/dev/null
}

render_icon 16 "icon_16x16.png"
render_icon 32 "icon_16x16@2x.png"
render_icon 32 "icon_32x32.png"
render_icon 64 "icon_32x32@2x.png"
render_icon 128 "icon_128x128.png"
render_icon 256 "icon_128x128@2x.png"
render_icon 256 "icon_256x256.png"
render_icon 512 "icon_256x256@2x.png"
render_icon 512 "icon_512x512.png"

iconutil -c icns "$ICONSET_DIR" -o "$ICON_PATH"

pyinstaller "$PROJECT_DIR/feishu_uploader.spec" --noconfirm --clean

echo
echo "构建完成：$PROJECT_DIR/dist/飞书附件批量上传.app"
