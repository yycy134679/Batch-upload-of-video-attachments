from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from .constants import CELL_REF_PATTERN
from .models import UploadPlanItem, UploadResult
from .report import utc_now
from .runtime import configure_runtime_environment

configure_runtime_environment()

Logger = Callable[[str], None]
FEISHU_LOGIN_CHECK_URL = "https://www.feishu.cn/messenger/"
try:
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    compute_driver_executable = None
    get_driver_env = None
    sync_playwright = None
    PlaywrightTimeout = TimeoutError

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Response
else:
    Locator = Page = Response = Any


def response_matches(
    response: Response,
    *,
    method: str,
    url_substring: str,
    status: int,
) -> bool:
    return (
        response.request.method.upper() == method.upper()
        and url_substring in response.url
        and response.status == status
    )


def ensure_playwright_package_installed() -> None:
    if sync_playwright is not None:
        return
    raise RuntimeError(
        "未安装 Playwright。请先进入 .venv 后执行:\n"
        "  pip install -r requirements.txt"
    )


def _get_logger(log: Logger | None) -> Logger:
    return log or print


def chromium_executable_path() -> Path:
    ensure_playwright_package_installed()
    try:
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path)
    except Exception as exc:
        raise RuntimeError(f"无法解析 Playwright Chromium 路径: {exc}") from exc


def playwright_browser_installed() -> bool:
    try:
        return chromium_executable_path().exists()
    except RuntimeError:
        return False


def build_playwright_install_command(browser: str = "chromium") -> tuple[list[str], dict[str, str]]:
    ensure_playwright_package_installed()
    if compute_driver_executable is None or get_driver_env is None:
        raise RuntimeError("当前 Playwright 安装不完整，缺少 driver CLI。")

    driver_executable, driver_cli = compute_driver_executable()
    configure_runtime_environment()
    env = get_driver_env()
    env.update(os.environ)
    return [driver_executable, driver_cli, "install", browser], env


def install_playwright_browser(
    browser: str = "chromium",
    *,
    log: Logger | None = None,
) -> None:
    logger = _get_logger(log)
    command, env = build_playwright_install_command(browser)
    logger("[INFO] 首次启动正在初始化 Playwright Chromium，请保持联网并稍候...")
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        message = line.strip()
        if message:
            logger(message)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Playwright Chromium 初始化失败，退出码 {return_code}。")


def ensure_playwright_available(
    *,
    log: Logger | None = None,
    install: bool = False,
) -> None:
    ensure_playwright_package_installed()

    if playwright_browser_installed():
        return

    if not install:
        browser_path = chromium_executable_path()
        raise RuntimeError(
            "缺少 Playwright Chromium 内核，请先初始化运行环境：\n"
            f"  预期路径: {browser_path}"
        )

    install_playwright_browser(log=log)
    if not playwright_browser_installed():
        raise RuntimeError("Chromium 初始化完成后仍未检测到浏览器可执行文件。")


def has_saved_login_state(state_file: Path, *, now_ts: float | None = None) -> bool:
    if not state_file.exists():
        return False
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        return False

    now_value = now_ts if now_ts is not None else time.time()
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain", "")).lower()
        if not any(key in domain for key in ("feishu", "larkoffice", "larksuite")):
            continue
        expires = cookie.get("expires")
        if expires in (None, -1):
            return True
        try:
            if float(expires) > now_value:
                return True
        except (TypeError, ValueError):
            return True
    return False


def is_login_page(page: Page) -> bool:
    url = page.url.lower()
    return any(
        token in url
        for token in (
            "accounts.feishu.cn",
            "passport.feishu.cn",
            "accounts.larkoffice.com",
            "passport.larkoffice.com",
            "accounts.larksuite.com",
            "passport.larksuite.com",
            "login",
        )
    )


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def read_textbox_value(locator: Locator) -> str:
    try:
        return normalize_text(locator.input_value(timeout=500))
    except Exception:
        return normalize_text(locator.text_content(timeout=500))


def locate_name_box(page: Page) -> Locator:
    selector = "main input, main textarea, main [role='textbox']"
    index = page.evaluate(
        """
        (selector) => {
          const isVisible = (element) => {
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              style.display !== "none" &&
              style.visibility !== "hidden"
            );
          };
          const getValue = (element) => {
            if ("value" in element && typeof element.value === "string") {
              return element.value.trim();
            }
            return (element.textContent || "").trim();
          };
          const matcher = /^[A-Z]{1,3}[1-9]\\d*$/;
          const nodes = Array.from(document.querySelectorAll(selector));
          return nodes.findIndex((node) => isVisible(node) && matcher.test(getValue(node)));
        }
        """,
        selector,
    )
    if index is None or index < 0:
        raise RuntimeError("未找到飞书表格名称框，页面可能尚未加载完成。")
    return page.locator(selector).nth(index)


def current_cell_ref(page: Page) -> str:
    value = read_textbox_value(locate_name_box(page))
    if not CELL_REF_PATTERN.fullmatch(value):
        raise RuntimeError(f"名称框内容异常: {value!r}")
    return value


def get_insert_button(page: Page) -> Locator:
    primary = page.locator("#sheet-insert")
    if primary.count() > 0:
        return primary.first
    return page.locator("main").get_by_text("插入", exact=True).first


def get_formula_bar(page: Page) -> Locator:
    return page.locator("main .formulabar__inputarea").first


def get_loaded_sheet_container(page: Page) -> Locator:
    return page.locator("main .faster_container.first-sheet-loaded.spread-loaded").first


def get_sheet_canvas(page: Page) -> Locator:
    return page.locator("main canvas.faster-single-canvas").first


def wait_for_sheet_ready(page: Page, timeout_ms: int = 60_000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    last_error: Exception | None = None
    stable_checks = 0
    while time.monotonic() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=2_000)
            get_insert_button(page).wait_for(state="visible", timeout=2_000)
            get_loaded_sheet_container(page).wait_for(state="visible", timeout=2_000)
            get_sheet_canvas(page).wait_for(state="visible", timeout=2_000)
            get_formula_bar(page).wait_for(state="visible", timeout=2_000)
            current_cell_ref(page)
            stable_checks += 1
            if stable_checks >= 2:
                return
        except Exception as exc:
            last_error = exc
            stable_checks = 0
        page.wait_for_timeout(500)
    raise TimeoutError(f"等待飞书表格加载超时: {last_error}")


def wait_for_login(
    page: Page,
    timeout_sec: int,
    log: Callable[[str], None] | None = None,
) -> None:
    if not is_login_page(page):
        wait_for_sheet_ready(page)
        return

    logger = log or print
    logger("=" * 50)
    logger("请在浏览器中完成飞书扫码登录")
    logger("登录成功后脚本会自动继续")
    logger("=" * 50)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not is_login_page(page):
            wait_for_sheet_ready(page)
            return
        page.wait_for_timeout(1_000)

    raise TimeoutError(f"等待登录超时（{timeout_sec}s）。")


def wait_for_manual_login(
    page: Page,
    timeout_sec: int,
    log: Callable[[str], None] | None = None,
) -> None:
    logger = log or print
    if not is_login_page(page):
        return

    logger("=" * 50)
    logger("请在浏览器中完成飞书扫码登录")
    logger("登录成功后会自动保存到本地，下次可直接复用")
    logger("=" * 50)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not is_login_page(page):
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
            return
        page.wait_for_timeout(1_000)

    raise TimeoutError(f"等待手动登录超时（{timeout_sec}s）。")


def login_to_feishu(
    *,
    state_file: Path,
    timeout_sec: int,
    log: Logger | None = None,
) -> None:
    ensure_playwright_available(log=log, install=True)
    logger = _get_logger(log)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context_options: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
        }
        if state_file.exists():
            context_options["storage_state"] = str(state_file)
        context = browser.new_context(**context_options)
        page = context.new_page()
        try:
            logger("[INFO] 正在打开飞书登录页面...")
            page.goto(FEISHU_LOGIN_CHECK_URL, wait_until="domcontentloaded")
            wait_for_manual_login(page, timeout_sec=timeout_sec, log=logger)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(state_file))
            logger(f"[INFO] 登录态已保存: {state_file}")
        finally:
            browser.close()


def navigate_to_cell(page: Page, cell_ref: str, timeout_ms: int = 10_000) -> None:
    name_box = locate_name_box(page)
    name_box.click()
    name_box.fill(cell_ref)
    page.keyboard.press("Enter")

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            if current_cell_ref(page) == cell_ref:
                page.wait_for_timeout(200)
                return
        except Exception:
            pass
        page.wait_for_timeout(250)

    raise TimeoutError(f"跳转到单元格 {cell_ref} 超时。")


def read_selected_cell_display(page: Page) -> str:
    try:
        formula_bar = get_formula_bar(page)
        formula_bar.wait_for(state="visible", timeout=2_000)
        return read_textbox_value(formula_bar)
    except Exception:
        selector = "main input, main textarea, main [role='textbox'], main [contenteditable='true']"
        text = page.evaluate(
            """
            (selector) => {
              const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
              const isVisible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                return (
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.display !== "none" &&
                  style.visibility !== "hidden"
                );
              };
              const getText = (element) => {
                if (!element) return "";
                if ("value" in element && typeof element.value === "string") {
                  return normalize(element.value);
                }
                return normalize(element.innerText || element.textContent || "");
              };
              const matcher = /^[A-Z]{1,3}[1-9]\\d*$/;
              const nodes = Array.from(document.querySelectorAll(selector)).filter(isVisible);
              const nameBox = nodes.find((node) => matcher.test(getText(node)));
              if (!nameBox) {
                return "";
              }

              const box = nameBox.getBoundingClientRect();
              const nearbyEditor = nodes
                .filter((node) => node !== nameBox && !node.contains(nameBox) && !nameBox.contains(node))
                .map((node) => ({ node, text: getText(node) }))
                .filter(({ node }) => {
                  const rect = node.getBoundingClientRect();
                  return (
                    rect.left >= box.right - 6 &&
                    rect.left < box.right + 1200 &&
                    Math.abs(rect.top - box.top) <= 20 &&
                    rect.height >= Math.max(box.height - 8, 12)
                  );
                })
                .sort((a, b) => {
                  return a.node.getBoundingClientRect().left - b.node.getBoundingClientRect().left;
                });
              return nearbyEditor.length > 0 ? nearbyEditor[0].text : "";
            }
            """,
            selector,
        )
        return normalize_text(text)


def locate_attachment_menu_item(page: Page) -> Locator:
    item = page.locator("[role='menuitem']:visible", has_text="附件").first
    item.wait_for(state="visible", timeout=5_000)
    return item


def click_insert_then_attachment(page: Page) -> Any:
    get_insert_button(page).click(timeout=5_000)
    page.wait_for_timeout(150)
    attachment_item = locate_attachment_menu_item(page)
    with page.expect_file_chooser(timeout=10_000) as chooser_info:
        attachment_item.click()
    return chooser_info.value


def handle_overwrite_prompt(page: Page, allow_overwrite: bool) -> bool:
    confirm_button = page.locator("button:visible", has_text="确认").first
    try:
        confirm_button.wait_for(state="visible", timeout=2_000)
    except PlaywrightTimeout:
        return False

    if allow_overwrite:
        confirm_button.click()
        return True

    cancel_button = page.locator("button:visible", has_text="取消").first
    if cancel_button.count() > 0:
        cancel_button.click(timeout=500)
    else:
        page.keyboard.press("Escape")
    raise RuntimeError("目标单元格已有内容，已取消覆盖。")


def wait_for_post_upload_ui(page: Page, file_name: str, timeout_ms: int = 8_000) -> str:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        display = read_selected_cell_display(page)
        if file_name in display:
            return display
        page.wait_for_timeout(250)
    raise TimeoutError(f"上传后未在 UI 中看到文件名 {file_name!r}。")


def upload_file_once(
    page: Page,
    plan_item: UploadPlanItem,
    *,
    overwrite: bool,
    upload_timeout_sec: int,
) -> tuple[str, str]:
    existing_display = read_selected_cell_display(page)
    if existing_display and not overwrite:
        return "skipped_existing", existing_display

    chooser = click_insert_then_attachment(page)
    timeout_ms = upload_timeout_sec * 1000
    with page.expect_response(
        lambda response: response_matches(
            response,
            method="POST",
            url_substring="/space/api/box/upload/finish/",
            status=200,
        ),
        timeout=timeout_ms,
    ) as finish_info, page.expect_response(
        lambda response: response_matches(
            response,
            method="POST",
            url_substring="/space/api/v2/sheet/user_changes",
            status=200,
        ),
        timeout=timeout_ms,
    ) as changes_info:
        chooser.set_files(str(plan_item.file_path))
        handle_overwrite_prompt(page, allow_overwrite=overwrite)

    finish_info.value
    changes_info.value
    display_after = wait_for_post_upload_ui(page, plan_item.file_name)
    status = "overwritten" if existing_display and overwrite else "uploaded"
    return status, display_after


def recover_page_state(page: Page) -> None:
    for _ in range(3):
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(150)

    cancel_button = page.locator("button:visible", has_text="取消").first
    if cancel_button.count() > 0:
        try:
            cancel_button.click(timeout=500)
            page.wait_for_timeout(150)
        except Exception:
            pass


def refresh_sheet(
    page: Page,
    login_timeout: int,
    log: Callable[[str], None] | None = None,
) -> None:
    page.reload(wait_until="domcontentloaded")
    wait_for_login(page, timeout_sec=login_timeout, log=log)
    wait_for_sheet_ready(page)


def take_failure_screenshot(page: Page, run_dir: Path, plan_item: UploadPlanItem) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", plan_item.file_name)
    screenshot_path = run_dir / f"failure-{plan_item.cell}-{safe_name}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    return screenshot_path


def upload_plan_item(
    page: Page,
    plan_item: UploadPlanItem,
    result: UploadResult,
    *,
    overwrite: bool,
    upload_timeout: int,
    retries: int,
    login_timeout: int,
    run_dir: Path,
    log: Callable[[str], None] | None = None,
) -> UploadResult:
    if not plan_item.exists:
        result.status = "skipped_missing"
        result.reason = "file_not_found"
        result.ended_at = utc_now()
        result.duration_sec = 0.0
        return result

    max_attempts = retries + 1
    started = time.monotonic()
    for attempt in range(1, max_attempts + 1):
        result.attempt_count = attempt
        try:
            navigate_to_cell(page, plan_item.cell)
            result.cell_display_before = read_selected_cell_display(page)
            status, display_after = upload_file_once(
                page,
                plan_item,
                overwrite=overwrite,
                upload_timeout_sec=upload_timeout,
            )
            result.status = status
            result.cell_display_after = display_after
            result.reason = ""
            break
        except Exception as exc:
            result.reason = str(exc)
            recover_page_state(page)
            if attempt >= max_attempts:
                screenshot = take_failure_screenshot(page, run_dir, plan_item)
                result.status = "failed"
                result.screenshot = str(screenshot)
                break
            try:
                refresh_sheet(page, login_timeout=login_timeout, log=log)
            except Exception:
                pass

    result.ended_at = utc_now()
    result.duration_sec = round(time.monotonic() - started, 3)
    return result
