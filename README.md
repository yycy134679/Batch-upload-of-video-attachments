# 飞书表格视频附件批量上传工具

这个工具会打开一个浏览器窗口，通过 Playwright 自动把本地视频批量上传到飞书表格的附件列。当前推荐的交付方式是 macOS `.app`。

## 给使用者

更详细的操作说明见：[内容运营使用文档](docs/内容运营使用文档.md)

### 安装 `.app`

1. 获取构建好的 `飞书附件批量上传.app`
2. 拖到 `Applications`
3. 首次打开如果被 Gatekeeper 拦截，右键应用并选择“打开”

### 首次启动

- 应用会自动检查 Chromium 浏览器内核
- 如果本机还没有对应版本，会在应用内自动初始化到 `~/Library/Application Support/飞书附件批量上传/playwright-browsers/`
- 首次初始化需要联网，可能需要几分钟
- 应用会检查本地飞书登录态；只有未登录或登录态过期时，才会提醒你点击“登录飞书”

### 上传步骤

1. 如果界面提示未登录，先点击“登录飞书”，扫码登录一次
2. 粘贴本次要上传的飞书表格 URL
3. 点击“选择目录”，或者把视频文件夹拖进窗口
4. 选择目标列并填写起始行
5. 选择运行模式：
   - 前台运行：显示浏览器窗口，适合观察页面和排查问题
   - 后台运行：使用无头模式上传，更适合安静地批量执行
6. 如需覆盖已有附件，勾选“允许覆盖已有附件”
7. 点击“开始上传”

说明：

- “登录飞书”始终会打开可见浏览器窗口，方便扫码登录
- 如需切换飞书账号，可先点击“清理登录信息（切换账号）”删除本地登录态，再重新扫码登录
- 运行模式只影响点击“开始上传”后的浏览器执行方式

### 运行数据位置

- 登录态：`~/Library/Application Support/飞书附件批量上传/storage_state.json`
- 报告目录：`~/Library/Application Support/飞书附件批量上传/reports/`
- 浏览器内核：`~/Library/Application Support/飞书附件批量上传/playwright-browsers/`

## 给开发者

### 环境准备

所有安装、运行、测试和构建命令都先进入 `.venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

也可以直接双击 `install.command` 让仓库自动准备开发环境。

### 启动 GUI

```bash
source .venv/bin/activate
python -m feishu_uploader.gui
```

首次运行如果缺少 Chromium，GUI 会自动初始化。

### 构建 macOS `.app`

```bash
source .venv/bin/activate
scripts/build_macos_app.sh
```

构建输出在：

```text
dist/飞书附件批量上传.app
```

构建脚本会：

- 读取 `media/icon.png`
- 生成 `.icns`
- 使用 `PyInstaller` 的 `onedir + windowed` 模式打包 GUI 入口

### 命令行用法

CLI 仍保留给开发调试使用：

```bash
source .venv/bin/activate
python -m feishu_uploader.runner \
  --url "https://bytedance.larkoffice.com/wiki/..." \
  --column E \
  --start-row 2 \
  --video-dir media
```

如需无头模式，可在命令末尾追加 `--headless`。

### 测试

```bash
source .venv/bin/activate
python -m pytest test_upload_attachments.py -v
```

## 说明

- 本轮不包含代码签名、notarization 和 DMG 封装
- 旧的项目根目录登录态不会自动迁移到 `.app` 版本
