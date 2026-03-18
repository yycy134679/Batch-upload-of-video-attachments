# 飞书表格视频附件批量上传工具

将本地视频目录按文件名顺序批量上传到飞书表格附件列。项目提供面向使用者的 macOS 图形界面，也保留了便于调试和测试的命令行入口。

[使用文档](docs/使用文档.md) · [开发说明](#开发说明) · [项目结构](#项目结构)

## 项目简介

这个项目主要解决两类问题：

- 内容运营同学需要把一批本地视频快速回填到飞书表格指定列，并且希望尽量减少手工重复操作。
- 开发同学需要一个可测试、可打包、可复用登录态的自动化上传工具，用于维护内部上传流程。

上传时，工具会扫描视频目录、按自然顺序生成上传计划，然后从指定列和起始行开始逐个写入附件。每次运行都会输出报告；失败时会额外保存截图，方便回溯。

## 核心能力

- 提供 PySide6 GUI，可填写表格地址、目标列、起始行，并支持拖拽目录。
- 基于 Playwright 自动操作飞书表格，首次运行会自动初始化 Chromium。
- 复用本地飞书登录态，未登录或登录过期时可重新扫码。
- 支持前台运行与后台运行，兼顾可观察性与安静执行。
- 支持中途安全终止，当前文件处理结束后停止后续任务。
- 为每次运行生成 `summary.json` 和失败截图，便于排查问题。
- 保留 CLI 入口，方便开发调试、自动化测试和脚本集成。

## 快速开始

### 给使用者

1. 获取构建好的 `飞书附件批量上传.app` 并拖到 `Applications`。
2. 首次打开如被 macOS 拦截，右键应用并选择“打开”。
3. 首次启动时等待运行环境初始化完成，再点击 `登录飞书` 扫码登录。
4. 填写飞书表格 URL，选择视频目录，设置目标列与起始行后开始上传。

详细操作、常见状态和排错建议见 [docs/使用文档.md](docs/使用文档.md)。

> [!NOTE]
> `登录飞书` 始终会打开可见浏览器窗口；前台/后台模式只影响正式开始上传后的执行方式。

### 给开发者

> [!IMPORTANT]
> 所有安装依赖、运行脚本、测试和打包命令都必须先进入 `.venv`。

准备开发环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

也可以直接双击 `install.command` 自动准备环境。

启动 GUI：

```bash
source .venv/bin/activate
python -m feishu_uploader.gui
```

使用 CLI 调试：

```bash
source .venv/bin/activate
python -m feishu_uploader.runner \
  --url "https://bytedance.larkoffice.com/wiki/..." \
  --column E \
  --start-row 23 \
  --video-dir media
```

如需后台运行，可追加 `--headless`；如需覆盖已有附件，可追加 `--overwrite`。

运行测试：

```bash
source .venv/bin/activate
python -m pytest test_upload_attachments.py -v
```

构建 macOS `.app`：

```bash
source .venv/bin/activate
scripts/build_macos_app.sh
```

构建输出目录：

```text
dist/飞书附件批量上传.app
```

> [!WARNING]
> 打包脚本依赖 `media/icon.png` 作为应用图标源文件；当前项目不包含代码签名、notarization 和 DMG 封装。

## 项目结构

- `feishu_uploader/gui.py`：桌面界面、运行环境初始化、登录与上传任务控制。
- `feishu_uploader/runner.py`：批量上传主流程，串联计划生成、浏览器操作和报告输出。
- `feishu_uploader/playwright_ops.py`：Playwright 相关操作，包括浏览器初始化、登录态处理与单文件上传。
- `feishu_uploader/cli.py`：命令行参数定义与配置解析。
- `feishu_uploader/runtime.py`：运行时路径与应用数据目录管理。
- `upload_attachments.py`：兼容入口脚本，继续导出常用符号，方便旧调用方式和测试复用。
- `app_main.py`：GUI 应用入口。
- `test_upload_attachments.py`：核心测试，覆盖排序、上传计划、配置校验、报告输出和终止逻辑。
- `docs/使用文档.md`：面向使用者的详细操作手册。
- `scripts/build_macos_app.sh`：macOS 应用打包脚本。

## 运行数据位置

应用默认把运行数据放在：

- 登录态：`~/Library/Application Support/飞书附件批量上传/storage_state.json`
- 运行报告：`~/Library/Application Support/飞书附件批量上传/reports/`
- Playwright 浏览器：`~/Library/Application Support/飞书附件批量上传/playwright-browsers/`

如果需要切换账号，可在 GUI 中使用 `清理登录信息（切换账号）` 删除本地登录态后重新扫码。

## 补充说明

- 项目当前推荐的交付方式是 macOS `.app`。
- GUI 是主要使用入口，CLI 更适合开发调试和排查问题。
- 文件上传顺序以文件名自然排序为准，不依赖创建时间。
