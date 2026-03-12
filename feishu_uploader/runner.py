from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .runtime import configure_runtime_environment

configure_runtime_environment()

from .cli import parse_args
from .file_plan import build_upload_plan
from .models import AppConfig, RunOutcome, UploadPlanItem, UploadResult
from .playwright_ops import (
    ensure_playwright_available,
    sync_playwright,
    upload_plan_item,
    wait_for_login,
)
from .report import build_summary, ensure_parent_dir, make_run_slug, utc_now, write_summary
from .validation import validate_config


@dataclass(frozen=True)
class RunCallbacks:
    log: Callable[[str], None] | None = None
    run_started: Callable[[AppConfig, Sequence[UploadPlanItem], Path], None] | None = None
    item_started: Callable[[UploadPlanItem, int], None] | None = None
    item_finished: Callable[[UploadResult, int], None] | None = None
    run_finished: Callable[[RunOutcome], None] | None = None


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def format_browser_mode(headless: bool) -> str:
    return "后台运行（无头）" if headless else "前台运行（显示浏览器）"


def print_run_header(config: AppConfig, plan: Sequence[UploadPlanItem], run_dir) -> None:
    print(f"[INFO] 目标表格: {config.url}")
    print(f"[INFO] 上传范围: {config.column}{config.start_row} 起，共 {len(plan)} 个文件槽位")
    print(f"[INFO] 登录态文件: {config.state_file}")
    print(f"[INFO] 运行报告目录: {run_dir}")
    print(f"[INFO] 运行模式: {format_browser_mode(config.headless)}")
    if config.overwrite:
        print("[INFO] 当前模式: 允许覆盖已有内容")
    else:
        print("[INFO] 当前模式: 默认跳过已有内容")


def build_run_header_lines(
    config: AppConfig,
    plan: Sequence[UploadPlanItem],
    run_dir: Path,
) -> list[str]:
    lines = [
        f"[INFO] 目标表格: {config.url}",
        f"[INFO] 上传范围: {config.column}{config.start_row} 起，共 {len(plan)} 个文件槽位",
        f"[INFO] 登录态文件: {config.state_file}",
        f"[INFO] 运行报告目录: {run_dir}",
        f"[INFO] 运行模式: {format_browser_mode(config.headless)}",
    ]
    if config.overwrite:
        lines.append("[INFO] 当前模式: 允许覆盖已有内容")
    else:
        lines.append("[INFO] 当前模式: 默认跳过已有内容")
    return lines


def _emit(callback: Callable[..., None] | None, *args: object) -> None:
    if callback is not None:
        callback(*args)


def make_result(item: UploadPlanItem) -> UploadResult:
    return UploadResult(
        index=item.index,
        cell=item.cell,
        file_name=item.file_name,
        file_path=str(item.file_path),
        size_bytes=item.size_bytes,
        started_at=utc_now(),
    )


def run(config: AppConfig, callbacks: RunCallbacks | None = None) -> RunOutcome:
    config = validate_config(config)
    callbacks = callbacks or RunCallbacks()
    ensure_playwright_available(log=callbacks.log, install=True)

    plan = build_upload_plan(config)
    run_dir = config.report_dir / make_run_slug()
    run_dir.mkdir(parents=True, exist_ok=True)
    _emit(callbacks.run_started, config, plan, run_dir)
    for line in build_run_header_lines(config, plan, run_dir):
        _emit(callbacks.log, line)

    started_at = utc_now()
    results: list[UploadResult] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless)
        context_options: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
        }
        if config.state_file.exists():
            context_options["storage_state"] = str(config.state_file)
            _emit(callbacks.log, f"[INFO] 复用登录态: {config.state_file.name}")

        context = browser.new_context(**context_options)
        page = context.new_page()
        try:
            page.goto(config.url, wait_until="domcontentloaded")
            wait_for_login(page, timeout_sec=config.login_timeout)
            ensure_parent_dir(config.state_file)
            context.storage_state(path=str(config.state_file))
            _emit(callbacks.log, f"[INFO] 登录态已更新: {config.state_file.name}")

            total = len(plan)
            for item in plan:
                _emit(callbacks.item_started, item, total)
                _emit(
                    callbacks.log,
                    f"[{item.index + 1}/{total}] {item.file_name} "
                    f"({format_size(item.size_bytes)}) -> {item.cell}",
                )
                result = upload_plan_item(
                    page,
                    item,
                    make_result(item),
                    overwrite=config.overwrite,
                    upload_timeout=config.upload_timeout,
                    retries=config.retries,
                    login_timeout=config.login_timeout,
                    run_dir=run_dir,
                    log=callbacks.log,
                )
                results.append(result)
                _emit(callbacks.item_finished, result, total)
                _emit(callbacks.log, f"  -> {result.status}")
                if result.reason:
                    _emit(callbacks.log, f"     reason: {result.reason}")
                if result.screenshot:
                    _emit(callbacks.log, f"     screenshot: {result.screenshot}")
        finally:
            browser.close()

    ended_at = utc_now()
    summary_path = write_summary(
        run_dir,
        config,
        results,
        started_at=started_at,
        ended_at=ended_at,
    )
    stats = build_summary(config, results)["stats"]
    has_errors = any(result.status in {"failed", "skipped_missing"} for result in results)
    outcome = RunOutcome(
        exit_code=1 if has_errors else 0,
        run_dir=run_dir,
        summary_path=summary_path,
        started_at=started_at,
        ended_at=ended_at,
        stats=stats,
        results=tuple(results),
    )
    _emit(callbacks.log, f"完成，统计: {stats}")
    _emit(callbacks.log, f"报告已写入: {summary_path}")
    _emit(callbacks.run_finished, outcome)
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        callbacks = RunCallbacks(log=print)
        outcome = run(config, callbacks=callbacks)
        return outcome.exit_code
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[WARN] 用户中断运行。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
