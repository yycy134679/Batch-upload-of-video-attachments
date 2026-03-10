"""
飞书表格 - 视频附件批量上传脚本
=================================
使用 Playwright 自动化将本地视频文件上传到飞书在线表格的指定列。

依赖安装:
    pip install playwright
    playwright install chromium

使用方式:
    python upload_attachments.py

首次运行时需要手动登录飞书，登录后会自动保存 Cookie，
后续运行可跳过登录步骤。
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ==================== 配置区 ====================

# 飞书表格地址
SPREADSHEET_URL = (
    "https://bytedance.larkoffice.com/wiki/GxGswlGQfiB0PSkL8ItcABlKnig"
)

# 视频文件目录
VIDEO_DIR = Path(__file__).parent / "media"

# 要上传的文件列表（按顺序）
VIDEO_FILES = [
    "1.mp4",
    "2.mp4",
    "3.mp4",
    "4.mp4",
    "5.mp4",
    "6.mp4",
    "7.mp4",
]

TARGET_COLUMN = "E"  # 附件所在列
START_ROW = 23        # 数据起始行（第 1 行为表头）

# 每个文件上传后的等待时间（秒），大文件适当增加
UPLOAD_WAIT_SEC = 2

# Cookie 持久化路径（登录一次后自动复用）
COOKIE_PATH = Path(__file__).parent / ".feishu_cookies.json"

# =================================================


def wait_for_login(page, timeout_sec=300):
    """等待用户在浏览器中手动完成飞书登录。"""
    if "login" not in page.url and "accounts" not in page.url:
        return  # 已登录

    print("=" * 50)
    print("  请在浏览器中完成飞书登录")
    print("  登录成功后脚本会自动继续")
    print("=" * 50)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if "login" not in page.url and "accounts" not in page.url:
            print("[OK] 登录成功！等待表格加载...")
            page.wait_for_timeout(8000)
            return
        page.wait_for_timeout(2000)

    raise TimeoutError(f"等待登录超时（{timeout_sec}s），请重试")


def navigate_to_cell(page, cell_ref):
    """
    通过名称框（Name Box）导航到指定单元格。

    飞书表格使用 Canvas 渲染，无法直接点击单元格 DOM，
    但名称框是普通 DOM 元素，可以通过它跳转到任意单元格。
    """
    name_box = page.get_by_role("main").get_by_label("").first
    name_box.click()
    name_box.fill(cell_ref)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)


def upload_attachment(page, cell_ref, file_path):
    """导航到指定单元格并上传附件。"""

    # 1) 导航到目标单元格
    navigate_to_cell(page, cell_ref)

    # 2) 点击工具栏「插入」菜单
    page.locator("#sheet-insert").click()
    page.wait_for_timeout(500)

    # 3) 点击「附件」选项，同时捕获文件选择器
    with page.expect_file_chooser(timeout=10000) as fc_info:
        page.get_by_role("menuitem", name="附件").click()

    file_chooser = fc_info.value
    file_chooser.set_files(str(file_path))

    # 4) 处理「单元格现有内容将被覆盖」确认弹窗
    page.wait_for_timeout(1500)
    try:
        confirm_btn = page.get_by_role("button", name="确认")
        if confirm_btn.is_visible(timeout=2000):
            confirm_btn.click()
    except PlaywrightTimeout:
        pass  # 单元格为空，没有弹窗

    # 5) 等待上传完成并保存到云端
    page.wait_for_timeout(UPLOAD_WAIT_SEC * 1000)


def main():
    with sync_playwright() as p:
        # ---------- 启动浏览器 ----------
        browser = p.chromium.launch(headless=False)

        # 尝试复用已保存的登录态
        if COOKIE_PATH.exists():
            print(f"[INFO] 检测到已保存的登录态: {COOKIE_PATH.name}")
            context = browser.new_context(
                storage_state=str(COOKIE_PATH),
                viewport={"width": 1440, "height": 900},
            )
        else:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
            )

        page = context.new_page()

        # ---------- 打开表格 ----------
        page.goto(SPREADSHEET_URL, wait_until="domcontentloaded")
        wait_for_login(page)

        # 保存登录态以便下次复用
        context.storage_state(path=str(COOKIE_PATH))
        print(f"[INFO] 登录态已保存到: {COOKIE_PATH.name}")

        # ---------- 逐个上传 ----------
        total = len(VIDEO_FILES)
        success = 0

        for i, filename in enumerate(VIDEO_FILES):
            row = START_ROW + i
            cell = f"{TARGET_COLUMN}{row}"
            filepath = VIDEO_DIR / filename

            if not filepath.exists():
                print(f"[SKIP] 文件不存在: {filepath}")
                continue

            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"[{i+1}/{total}] {filename} ({size_mb:.1f}MB) -> {cell}")

            try:
                upload_attachment(page, cell, filepath)
                success += 1
                print(f"  -> 上传成功")
            except Exception as e:
                print(f"  -> 上传失败: {e}")

        # ---------- 完成 ----------
        print(f"\n完成！成功上传 {success}/{total} 个文件。")
        input("按 Enter 关闭浏览器...")
        browser.close()


if __name__ == "__main__":
    main()
