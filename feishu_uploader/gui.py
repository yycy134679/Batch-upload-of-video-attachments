from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from threading import Event

from .runtime import APP_NAME, BUNDLE_IDENTIFIER, configure_runtime_environment, resource_path

configure_runtime_environment()

from .constants import (
    DEFAULT_COLUMN,
    DEFAULT_LOGIN_TIMEOUT,
    DEFAULT_REPORT_DIR,
    DEFAULT_RETRIES,
    DEFAULT_START_ROW,
    DEFAULT_STATE_FILE,
    DEFAULT_UPLOAD_TIMEOUT,
)
from .models import AppConfig, RunOutcome, UploadPlanItem, UploadResult
from .playwright_ops import (
    clear_saved_login_state,
    ensure_playwright_available,
    has_saved_login_state,
    login_to_feishu,
    playwright_browser_installed,
)
from .runner import RunCallbacks, run
from .validation import validate_config

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QCloseEvent, QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressDialog,
        QPushButton,
        QPlainTextEdit,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:
    raise SystemExit(
        "未安装 PySide6。请先进入 .venv 后执行安装脚本，或运行:\n"
        "  pip install -r requirements.txt"
    ) from exc


STATUS_LABELS = {
    "pending": "等待中",
    "running": "上传中",
    "cancelled": "已终止",
    "uploaded": "上传成功",
    "skipped_existing": "跳过已有内容",
    "overwritten": "覆盖成功",
    "failed": "上传失败",
    "skipped_missing": "文件缺失",
}


def format_browser_mode(headless: bool) -> str:
    return "后台运行（无头）" if headless else "前台运行（显示浏览器）"


def build_gui_config(
    *,
    url: str,
    video_dir: str,
    column: str,
    start_row: int,
    overwrite: bool,
    headless: bool,
) -> AppConfig:
    video_dir_text = video_dir.strip()
    if not video_dir_text:
        raise ValueError("请选择视频目录。")
    return validate_config(
        AppConfig(
            url=url,
            column=column,
            start_row=start_row,
            video_dir=Path(video_dir_text).expanduser().resolve(),
            state_file=DEFAULT_STATE_FILE.resolve(),
            report_dir=DEFAULT_REPORT_DIR.resolve(),
            login_timeout=DEFAULT_LOGIN_TIMEOUT,
            upload_timeout=DEFAULT_UPLOAD_TIMEOUT,
            retries=DEFAULT_RETRIES,
            overwrite=overwrite,
            headless=headless,
            files=None,
        )
    )


def format_stats(stats: dict[str, int]) -> str:
    if not stats:
        return "尚未开始上传。"
    parts = []
    for key in ("uploaded", "overwritten", "skipped_existing", "failed", "skipped_missing"):
        count = stats.get(key)
        if count:
            parts.append(f"{STATUS_LABELS.get(key, key)} {count}")
    return "，".join(parts) if parts else "本次没有处理任何文件。"


class DirectoryDropLineEdit(QLineEdit):
    directory_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("可拖入视频文件夹，或点击右侧“选择目录”")

    def _extract_directory(self, mime_data) -> str | None:
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                return str(path.resolve())
        return None

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        directory = self._extract_directory(event.mimeData())
        if directory:
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        directory = self._extract_directory(event.mimeData())
        if directory:
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        directory = self._extract_directory(event.mimeData())
        if not directory:
            event.ignore()
            return
        self.setText(directory)
        self.directory_selected.emit(directory)
        event.acceptProposedAction()


class UploadWorker(QObject):
    log = Signal(str)
    run_started = Signal(object, str)
    item_started = Signal(object, int)
    item_finished = Signal(object, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._stop_requested = Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def should_stop(self) -> bool:
        return self._stop_requested.is_set()

    def start(self) -> None:
        try:
            callbacks = RunCallbacks(
                log=self.log.emit,
                run_started=self._emit_run_started,
                item_started=self._emit_item_started,
                item_finished=self._emit_item_finished,
                run_finished=self.finished.emit,
            )
            run(self._config, callbacks=callbacks, should_stop=self.should_stop)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit_run_started(
        self,
        _config: AppConfig,
        plan: list[UploadPlanItem] | tuple[UploadPlanItem, ...],
        run_dir: Path,
    ) -> None:
        self.run_started.emit(list(plan), str(run_dir))

    def _emit_item_started(self, item: UploadPlanItem, total: int) -> None:
        self.item_started.emit(item, total)

    def _emit_item_finished(self, result: UploadResult, total: int) -> None:
        self.item_finished.emit(result, total)


class RuntimeInitWorker(QObject):
    log = Signal(str)
    install_started = Signal()
    finished = Signal()
    failed = Signal(str)

    def start(self) -> None:
        try:
            if not playwright_browser_installed():
                self.install_started.emit()
            ensure_playwright_available(log=self.log.emit, install=True)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class LoginWorker(QObject):
    log = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, state_file: Path, timeout_sec: int) -> None:
        super().__init__()
        self._state_file = state_file
        self._timeout_sec = timeout_sec

    def start(self) -> None:
        try:
            login_to_feishu(
                state_file=self._state_file,
                timeout_sec=self._timeout_sec,
                log=self.log.emit,
            )
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class UploadWindow(QMainWindow):
    def __init__(self, *, auto_initialize_runtime: bool = True) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: UploadWorker | None = None
        self._runtime_thread: QThread | None = None
        self._runtime_worker: RuntimeInitWorker | None = None
        self._login_thread: QThread | None = None
        self._login_worker: LoginWorker | None = None
        self._runtime_dialog: QProgressDialog | None = None
        self._runtime_ready = False
        self._runtime_initializing = False
        self._login_in_progress = False
        self._has_saved_login = False
        self._login_reminder_shown = False
        self._upload_stop_requested = False
        self._latest_run_dir: Path | None = None
        self._row_by_cell: dict[str, int] = {}

        self.setWindowTitle(APP_NAME)
        self.resize(1120, 820)
        self.setMinimumSize(980, 720)

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 20, 24, 24)
        root_layout.setSpacing(14)

        intro = QLabel("粘贴飞书表格地址，选择或拖入视频目录，再设置起始单元格后开始上传。")
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        form_card = QFrame()
        form_card.setFrameShape(QFrame.StyledPanel)
        form_card.setStyleSheet(
            "QFrame { border: 1px solid #d7dce5; border-radius: 10px; background: #fbfcfe; }"
        )
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(18, 18, 18, 18)
        form_layout.setSpacing(14)

        fields = QFormLayout()
        fields.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fields.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        fields.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        fields.setHorizontalSpacing(12)
        fields.setVerticalSpacing(12)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("每次运行请粘贴飞书表格 URL")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setMinimumWidth(820)
        self.url_input.setMinimumHeight(36)
        fields.addRow("表格地址", self.url_input)

        self.video_dir_input = DirectoryDropLineEdit()
        self.video_dir_input.directory_selected.connect(self._on_directory_selected)
        self.video_dir_input.setClearButtonEnabled(True)
        self.video_dir_input.setMinimumHeight(36)
        self.video_dir_input.setMinimumWidth(820)
        self.video_dir_input.setStyleSheet(
            "QLineEdit { border: 1px dashed #8ba1c7; padding: 6px 8px; min-height: 36px; }"
        )

        choose_button = QPushButton("选择目录")
        choose_button.clicked.connect(self.choose_directory)
        choose_button.setMinimumHeight(36)
        choose_button.setMinimumWidth(120)

        video_dir_row = QWidget()
        video_dir_layout = QHBoxLayout(video_dir_row)
        video_dir_layout.setContentsMargins(0, 0, 0, 0)
        video_dir_layout.setSpacing(8)
        video_dir_layout.addWidget(self.video_dir_input, stretch=1)
        video_dir_layout.addWidget(choose_button)
        fields.addRow("视频目录", video_dir_row)

        target_row = QWidget()
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(8)

        self.column_combo = QComboBox()
        self.column_combo.addItems([chr(code) for code in range(ord("A"), ord("Z") + 1)])
        self.column_combo.setCurrentText(DEFAULT_COLUMN)
        self.column_combo.setFixedWidth(96)
        self.column_combo.setMinimumHeight(34)

        self.start_row_input = QSpinBox()
        self.start_row_input.setMinimum(1)
        self.start_row_input.setMaximum(999999)
        self.start_row_input.setValue(DEFAULT_START_ROW)
        self.start_row_input.setFixedWidth(140)
        self.start_row_input.setMinimumHeight(34)

        target_layout.addWidget(QLabel("列"))
        target_layout.addWidget(self.column_combo)
        target_layout.addWidget(QLabel("起始行"))
        target_layout.addWidget(self.start_row_input)
        target_layout.addStretch(1)

        self.overwrite_checkbox = QCheckBox("允许覆盖已有附件")
        fields.addRow("提交位置", target_row)
        fields.addRow("", self.overwrite_checkbox)

        self.run_mode_combo = QComboBox()
        self.run_mode_combo.addItem(format_browser_mode(False), False)
        self.run_mode_combo.addItem(format_browser_mode(True), True)
        self.run_mode_combo.setMinimumWidth(280)
        self.run_mode_combo.setMinimumHeight(34)
        fields.addRow("运行模式", self.run_mode_combo)

        self.run_mode_hint = QLabel(
            "前台运行会显示浏览器页面，便于观察上传过程；后台运行不会显示浏览器，更适合在不打扰当前操作时批量执行。"
            "注意：点击“登录飞书”时始终会打开可见浏览器窗口，运行模式只影响开始上传后的执行方式。"
        )
        self.run_mode_hint.setWordWrap(True)
        self.run_mode_hint.setStyleSheet("color: #5f6b7a;")
        fields.addRow("", self.run_mode_hint)

        form_layout.addLayout(fields)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.login_button = QPushButton("登录飞书")
        self.login_button.clicked.connect(self.start_login_flow)
        self.clear_login_button = QPushButton("清理登录信息（切换账号）")
        self.clear_login_button.clicked.connect(self.clear_login_flow)
        self.start_button = QPushButton("开始上传")
        self.start_button.clicked.connect(self.start_upload)
        self.stop_button = QPushButton("终止上传")
        self.stop_button.clicked.connect(self.stop_upload)
        self.stop_button.setEnabled(False)
        self.retry_init_button = QPushButton("重新初始化")
        self.retry_init_button.clicked.connect(self.start_runtime_initialization)
        self.retry_init_button.setVisible(False)
        self.open_report_button = QPushButton("打开报告目录")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self.open_latest_report_dir)
        actions.addWidget(self.login_button)
        actions.addWidget(self.clear_login_button)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.retry_init_button)
        actions.addWidget(self.open_report_button)
        actions.addStretch(1)
        form_layout.addLayout(actions)
        root_layout.addWidget(form_card)

        self.summary_label = QLabel("尚未开始上传。")
        self.summary_label.setStyleSheet("font-weight: 600;")
        self.summary_label.setWordWrap(True)
        root_layout.addWidget(self.summary_label)

        self.progress_table = QTableWidget(0, 4)
        self.progress_table.setHorizontalHeaderLabels(["单元格", "文件名", "状态", "说明"])
        self.progress_table.setAlternatingRowColors(True)
        self.progress_table.verticalHeader().setVisible(False)
        header = self.progress_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root_layout.addWidget(self.progress_table, stretch=1)

        log_title = QLabel("运行日志")
        root_layout.addWidget(log_title)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("上传开始后，这里会显示浏览器登录提示、进度和结果。")
        self.log_output.setMinimumHeight(180)
        root_layout.addWidget(self.log_output, stretch=1)

        self._enter_runtime_initializing_state()
        if auto_initialize_runtime:
            QTimer.singleShot(0, self.start_runtime_initialization)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.url_input.setEnabled(enabled)
        self.video_dir_input.setEnabled(enabled)
        self.column_combo.setEnabled(enabled)
        self.start_row_input.setEnabled(enabled)
        self.overwrite_checkbox.setEnabled(enabled)
        self.run_mode_combo.setEnabled(enabled)
        self.login_button.setEnabled(
            enabled and self._runtime_ready and not self._runtime_initializing and not self._login_in_progress
        )
        self.clear_login_button.setEnabled(enabled and self._can_clear_login_state())
        self.start_button.setEnabled(
            enabled
            and self._runtime_ready
            and not self._runtime_initializing
            and not self._login_in_progress
            and self._has_saved_login
        )

    def _upload_in_progress(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _set_upload_stop_state(self, requested: bool) -> None:
        self._upload_stop_requested = requested
        self.stop_button.setEnabled(self._upload_in_progress() and not requested)

    def _mark_pending_rows_as_cancelled(self) -> None:
        for row in range(self.progress_table.rowCount()):
            status_item = self.progress_table.item(row, 2)
            if status_item is None or status_item.text() != STATUS_LABELS["pending"]:
                continue
            self._set_table_text(row, 2, STATUS_LABELS["cancelled"])
            self._set_table_text(row, 3, "用户终止，未开始处理")

    def _build_cancelled_summary(self, outcome: RunOutcome) -> str:
        if outcome.processed_count == 0:
            return f"已终止：本次未处理任何文件，未处理 {outcome.remaining_count} 个"
        return f"已终止：{format_stats(outcome.stats)}，未处理 {outcome.remaining_count} 个"

    def _can_clear_login_state(self) -> bool:
        return (
            self._runtime_ready
            and not self._runtime_initializing
            and not self._login_in_progress
            and not self._upload_in_progress()
            and DEFAULT_STATE_FILE.resolve().exists()
        )

    def _refresh_login_state(self, *, notify: bool = False) -> None:
        self._has_saved_login = has_saved_login_state(DEFAULT_STATE_FILE.resolve())
        if self._has_saved_login:
            self.summary_label.setText("运行环境已就绪，检测到已保存的飞书登录态，可开始上传。")
            self._set_form_enabled(True)
            return

        self.summary_label.setText("运行环境已就绪，请先点击“登录飞书”完成登录。")
        self._set_form_enabled(True)
        if notify and not self._login_reminder_shown:
            self._login_reminder_shown = True
            QMessageBox.information(
                self,
                "请先登录飞书",
                "检测到当前未登录或登录态已过期，请先点击“登录飞书”完成登录，登录态会自动持久化保存。",
            )

    def _enter_runtime_initializing_state(self) -> None:
        self._runtime_ready = False
        self._runtime_initializing = True
        self.retry_init_button.setVisible(False)
        self.summary_label.setText("正在检查运行环境...")
        self._set_form_enabled(False)

    def _show_runtime_progress_dialog(self) -> None:
        if self._runtime_dialog is not None:
            return
        dialog = QProgressDialog("正在初始化 Chromium 浏览器内核，请稍候...", "", 0, 0, self)
        dialog.setWindowTitle("初始化运行环境")
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()
        self._runtime_dialog = dialog

    def _close_runtime_progress_dialog(self) -> None:
        if self._runtime_dialog is None:
            return
        self._runtime_dialog.close()
        self._runtime_dialog.deleteLater()
        self._runtime_dialog = None

    def _set_table_text(self, row: int, column: int, value: str) -> None:
        item = self.progress_table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.progress_table.setItem(row, column, item)
        item.setText(value)

    def _on_directory_selected(self, directory: str) -> None:
        self.append_log(f"[INFO] 已选择视频目录: {directory}")

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def start_runtime_initialization(self) -> None:
        if self._runtime_thread is not None and self._runtime_thread.isRunning():
            return
        if not self._runtime_initializing:
            self._enter_runtime_initializing_state()
        runtime_paths = configure_runtime_environment()
        self.append_log(f"[INFO] 浏览器目录: {runtime_paths.browser_dir}")
        self.append_log(f"[INFO] 登录态文件: {runtime_paths.state_file}")
        self.append_log(f"[INFO] 报告目录: {runtime_paths.report_dir}")

        self._runtime_thread = QThread(self)
        self._runtime_worker = RuntimeInitWorker()
        self._runtime_worker.moveToThread(self._runtime_thread)

        self._runtime_thread.started.connect(self._runtime_worker.start)
        self._runtime_worker.log.connect(self.append_log)
        self._runtime_worker.install_started.connect(self.on_runtime_install_started)
        self._runtime_worker.finished.connect(self.on_runtime_init_finished)
        self._runtime_worker.failed.connect(self.on_runtime_init_failed)
        self._runtime_worker.finished.connect(self._runtime_thread.quit)
        self._runtime_worker.failed.connect(self._runtime_thread.quit)
        self._runtime_thread.finished.connect(self._cleanup_runtime_worker)
        self._runtime_thread.start()

    def on_runtime_install_started(self) -> None:
        self.append_log("[INFO] 未发现 Chromium 内核，开始执行首次初始化。")
        self._show_runtime_progress_dialog()

    def on_runtime_init_finished(self) -> None:
        self._runtime_initializing = False
        self._runtime_ready = True
        self._close_runtime_progress_dialog()
        self.retry_init_button.setVisible(False)
        self.append_log("[INFO] 运行环境检查完成。")
        self._refresh_login_state(notify=True)

    def on_runtime_init_failed(self, message: str) -> None:
        self._runtime_initializing = False
        self._runtime_ready = False
        self._close_runtime_progress_dialog()
        self._set_form_enabled(False)
        self.retry_init_button.setVisible(True)
        self.retry_init_button.setEnabled(True)
        self.summary_label.setText("运行环境初始化失败，请重试或退出应用。")
        self.append_log(f"[ERROR] {message}")

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("初始化失败")
        dialog.setText(message)
        retry_button = dialog.addButton("重试初始化", QMessageBox.ButtonRole.AcceptRole)
        close_button = dialog.addButton("退出应用", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is retry_button:
            QTimer.singleShot(0, self.start_runtime_initialization)
            return
        if dialog.clickedButton() is close_button:
            self.close()

    def start_login_flow(self) -> None:
        if self._runtime_initializing or not self._runtime_ready:
            QMessageBox.information(self, "运行环境未就绪", "请等待运行环境初始化完成后再登录飞书。")
            return
        if self._login_in_progress:
            return

        self._login_in_progress = True
        self.summary_label.setText("正在等待飞书登录完成...")
        self._set_form_enabled(False)
        self.append_log("[INFO] 正在启动飞书登录流程...")

        self._login_thread = QThread(self)
        self._login_worker = LoginWorker(DEFAULT_STATE_FILE.resolve(), DEFAULT_LOGIN_TIMEOUT)
        self._login_worker.moveToThread(self._login_thread)

        self._login_thread.started.connect(self._login_worker.start)
        self._login_worker.log.connect(self.append_log)
        self._login_worker.finished.connect(self.on_login_finished)
        self._login_worker.failed.connect(self.on_login_failed)
        self._login_worker.finished.connect(self._login_thread.quit)
        self._login_worker.failed.connect(self._login_thread.quit)
        self._login_thread.finished.connect(self._cleanup_login_worker)
        self._login_thread.start()

    def clear_login_flow(self) -> None:
        if self._runtime_initializing or not self._runtime_ready:
            QMessageBox.information(self, "运行环境未就绪", "请等待运行环境初始化完成后再清理登录信息。")
            return
        if self._login_in_progress:
            QMessageBox.information(self, "正在登录", "飞书登录仍在进行中，请等待完成后再清理登录信息。")
            return
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, "任务仍在运行", "上传还在进行中，请等待任务结束后再清理登录信息。")
            return

        state_file = DEFAULT_STATE_FILE.resolve()
        if not state_file.exists():
            self._refresh_login_state(notify=False)
            return

        confirmed = QMessageBox.question(
            self,
            "清理登录信息",
            "将删除本地保存的飞书登录信息，下次需要重新扫码登录。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            removed = clear_saved_login_state(state_file)
        except OSError as exc:
            self.append_log(f"[ERROR] 清理登录信息失败: {exc}")
            QMessageBox.critical(self, "清理失败", f"无法清理本地飞书登录信息：{exc}")
            return

        if removed or not state_file.exists():
            self.append_log("[INFO] 已清理本地飞书登录信息，可重新登录其他账号。")
        self._refresh_login_state(notify=False)

    def on_login_finished(self) -> None:
        self._login_in_progress = False
        self.append_log("[INFO] 飞书登录完成，登录态已保存。")
        self._refresh_login_state(notify=False)
        QMessageBox.information(self, "登录成功", "飞书登录态已保存，下次启动会自动复用。")

    def on_login_failed(self, message: str) -> None:
        self._login_in_progress = False
        self.append_log(f"[ERROR] {message}")
        self._refresh_login_state(notify=False)
        QMessageBox.critical(self, "登录失败", message)

    def choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择视频目录")
        if not directory:
            return
        self.video_dir_input.setText(directory)
        self._on_directory_selected(directory)

    def build_current_config(self) -> AppConfig:
        return build_gui_config(
            url=self.url_input.text(),
            video_dir=self.video_dir_input.text(),
            column=self.column_combo.currentText(),
            start_row=self.start_row_input.value(),
            overwrite=self.overwrite_checkbox.isChecked(),
            headless=self.current_headless_mode(),
        )

    def current_headless_mode(self) -> bool:
        return bool(self.run_mode_combo.currentData())

    def reset_progress_view(self) -> None:
        self._row_by_cell.clear()
        self.progress_table.setRowCount(0)
        self.log_output.clear()
        self.summary_label.setText("准备开始上传。")
        self._set_upload_stop_state(False)
        self.open_report_button.setEnabled(False)
        self._latest_run_dir = None

    def start_upload(self) -> None:
        if self._runtime_initializing or not self._runtime_ready:
            QMessageBox.information(self, "运行环境未就绪", "请等待运行环境初始化完成后再开始上传。")
            return
        if not has_saved_login_state(DEFAULT_STATE_FILE.resolve()):
            self._refresh_login_state(notify=False)
            QMessageBox.information(
                self,
                "请先登录飞书",
                "检测到当前未登录或登录态已过期，请先点击“登录飞书”完成登录。",
            )
            return
        try:
            config = self.build_current_config()
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "无法开始上传", str(exc))
            return

        self.reset_progress_view()
        self._set_form_enabled(False)
        self.append_log("[INFO] 正在启动上传任务...")
        self.append_log(f"[INFO] 运行模式: {format_browser_mode(config.headless)}")

        self._thread = QThread(self)
        self._worker = UploadWorker(config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start)
        self._worker.log.connect(self.append_log)
        self._worker.run_started.connect(self.on_run_started)
        self._worker.item_started.connect(self.on_item_started)
        self._worker.item_finished.connect(self.on_item_finished)
        self._worker.finished.connect(self.on_run_finished)
        self._worker.failed.connect(self.on_run_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()
        self.stop_button.setEnabled(True)

    def stop_upload(self) -> None:
        if self._thread is None or self._worker is None or self._upload_stop_requested:
            return
        self._worker.request_stop()
        self._set_upload_stop_state(True)
        self.append_log("[WARN] 已收到终止上传请求，将在当前文件处理完成后停止。")
        self.summary_label.setText("正在等待当前文件处理完成后终止...")

    def on_run_started(self, plan: list[UploadPlanItem], run_dir: str) -> None:
        self._latest_run_dir = Path(run_dir)
        self.open_report_button.setEnabled(True)
        if self._upload_stop_requested:
            self.summary_label.setText("正在等待当前文件处理完成后终止...")
        else:
            self.summary_label.setText(f"已生成上传计划，共 {len(plan)} 个文件。")
        self.progress_table.setRowCount(len(plan))
        for row, item in enumerate(plan):
            self._row_by_cell[item.cell] = row
            self._set_table_text(row, 0, item.cell)
            self._set_table_text(row, 1, item.file_name)
            self._set_table_text(row, 2, STATUS_LABELS["pending"])
            self._set_table_text(row, 3, "等待开始")

    def on_item_started(self, item: UploadPlanItem, total: int) -> None:
        row = self._row_by_cell.get(item.cell)
        if row is None:
            return
        self._set_table_text(row, 2, STATUS_LABELS["running"])
        self._set_table_text(row, 3, f"正在处理第 {item.index + 1}/{total} 个文件")
        self.summary_label.setText(f"正在上传第 {item.index + 1}/{total} 个文件...")

    def on_item_finished(self, result: UploadResult, _total: int) -> None:
        row = self._row_by_cell.get(result.cell)
        if row is None:
            return
        self._set_table_text(row, 2, STATUS_LABELS.get(result.status, result.status))
        detail = result.reason or result.cell_display_after or result.cell_display_before or "-"
        self._set_table_text(row, 3, detail)

    def on_run_finished(self, outcome: RunOutcome) -> None:
        self._latest_run_dir = outcome.run_dir
        self.open_report_button.setEnabled(True)
        self._runtime_ready = True
        if outcome.cancelled:
            self._mark_pending_rows_as_cancelled()
            self.summary_label.setText(self._build_cancelled_summary(outcome))
        else:
            self.summary_label.setText(f"完成：{format_stats(outcome.stats)}")
        self._set_upload_stop_state(False)
        self.stop_button.setEnabled(False)
        self._set_form_enabled(True)

    def on_run_failed(self, message: str) -> None:
        self._runtime_ready = True
        self._set_upload_stop_state(False)
        self.stop_button.setEnabled(False)
        self._set_form_enabled(True)
        self.summary_label.setText("上传未能完成，请查看日志或稍后重试。")
        self.append_log(f"[ERROR] {message}")
        QMessageBox.critical(self, "上传失败", message)

    def _cleanup_worker(self) -> None:
        self.stop_button.setEnabled(False)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _cleanup_runtime_worker(self) -> None:
        if self._runtime_worker is not None:
            self._runtime_worker.deleteLater()
            self._runtime_worker = None
        if self._runtime_thread is not None:
            self._runtime_thread.deleteLater()
            self._runtime_thread = None

    def _cleanup_login_worker(self) -> None:
        if self._login_worker is not None:
            self._login_worker.deleteLater()
            self._login_worker = None
        if self._login_thread is not None:
            self._login_thread.deleteLater()
            self._login_thread = None

    def open_latest_report_dir(self) -> None:
        if self._latest_run_dir is None:
            QMessageBox.information(self, "暂无报告", "当前还没有可打开的运行报告目录。")
            return
        subprocess.run(["open", str(self._latest_run_dir)], check=False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._runtime_initializing and self._runtime_thread is not None and self._runtime_thread.isRunning():
            QMessageBox.information(
                self,
                "正在初始化",
                "运行环境仍在初始化中，请等待完成或失败提示后再关闭窗口。",
            )
            event.ignore()
            return
        if self._login_in_progress and self._login_thread is not None and self._login_thread.isRunning():
            QMessageBox.information(self, "正在登录", "飞书登录仍在进行中，请等待完成后再关闭窗口。")
            event.ignore()
            return
        if self._thread is not None and self._thread.isRunning():
            message = "上传还在进行中，请等待任务结束后再关闭窗口。"
            if self._upload_stop_requested:
                message = "正在等待当前文件处理完成后终止，请稍后再关闭窗口。"
            QMessageBox.information(self, "任务仍在运行", message)
            event.ignore()
            return
        super().closeEvent(event)


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationDomain(BUNDLE_IDENTIFIER)
    icon_path = resource_path("media", "icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = UploadWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
