"""
ui/run_view.py

自動作成実行タブ。QThread + pyqtSignal でバックグラウンド実行し、
リアルタイムで進捗ログを表示する。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QProgressBar, QGroupBox, QFormLayout, QSpinBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)


class SchedulerWorker(QThread):
    """最適化をバックグラウンドで実行するワーカー。"""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)  # (is_optimal, message)

    def __init__(self, year: int, month: int, time_limit: int = 120) -> None:
        super().__init__()
        self._year = year
        self._month = month
        self._time_limit = time_limit

    def run(self) -> None:
        try:
            from core.scheduler import ShiftScheduler

            def progress_callback(msg: str) -> None:
                self.log_signal.emit(msg)

            self.progress_signal.emit(10)
            scheduler = ShiftScheduler(
                year=self._year,
                month=self._month,
                progress_callback=progress_callback,
                time_limit=self._time_limit,
            )
            self.progress_signal.emit(20)
            result = scheduler.run()
            self.progress_signal.emit(100)
            self.finished_signal.emit(result.is_optimal, result.message)
        except Exception as e:
            logger.exception("スケジューラ実行エラー")
            self.log_signal.emit(f"エラー: {e}")
            self.finished_signal.emit(False, f"エラーが発生しました: {e}")


class RunView(QWidget):
    """自動作成実行ビュー。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        year, month = main_window.get_year_month()
        self._year = year
        self._month = month
        self._worker: SchedulerWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 対象月表示
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Yu Gothic UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.title_label)

        # 実行前チェックグループ
        check_group = QGroupBox("実行前チェック")
        check_layout = QVBoxLayout(check_group)
        self.check_label = QLabel()
        self.check_label.setWordWrap(True)
        check_layout.addWidget(self.check_label)
        layout.addWidget(check_group)

        # 最適化オプション
        opt_group = QGroupBox("最適化オプション")
        opt_form = QFormLayout(opt_group)

        self.max_days_spin = QSpinBox()
        self.max_days_spin.setRange(15, 31)
        self.max_days_spin.setValue(23)
        opt_form.addRow("最大出勤日数 (日/月):", self.max_days_spin)

        self.yakkin_min_spin = QSpinBox()
        self.yakkin_min_spin.setRange(1, 5)
        self.yakkin_min_spin.setValue(2)
        opt_form.addRow("夜勤最低人数 (名/日):", self.yakkin_min_spin)

        self.max_per_shift_spin = QSpinBox()
        self.max_per_shift_spin.setRange(1, 5)
        self.max_per_shift_spin.setValue(3)
        opt_form.addRow("1シフト最大人数:", self.max_per_shift_spin)

        self.time_limit_spin = QSpinBox()
        self.time_limit_spin.setRange(30, 600)
        self.time_limit_spin.setValue(120)
        opt_form.addRow("ソルバータイムアウト (秒):", self.time_limit_spin)
        layout.addWidget(opt_group)

        # 実行ボタン
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("▶ シフト自動作成を実行")
        self.btn_run.setFixedHeight(40)
        self.btn_run.setFont(QFont("Yu Gothic UI", 11))
        self.btn_run.clicked.connect(self._run_scheduler)

        self.btn_cancel = QPushButton("■ キャンセル")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_scheduler)

        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 実行ログ
        log_label = QLabel("実行ログ:")
        layout.addWidget(log_label)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_area)

        self._update_title()
        self._update_check_info()

    def set_year_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._update_title()
        self._update_check_info()

    def _update_title(self) -> None:
        self.title_label.setText(f"対象月: {self._year}年{self._month}月")

    def _update_check_info(self) -> None:
        """実行前チェック情報を更新する。"""
        try:
            all_emps = db.get_optimizer_target_employees()
            total = len(all_emps)
            submitted = db.get_submitted_requests(self._year, self._month)
            submitted_emp_ids = {r["employee_id"] for r in submitted}
            submitted_count = len(submitted_emp_ids)
            not_submitted = total - submitted_count

            check_text = (
                f"✅ 職員マスタ: {total}名\n"
                f"✅ 希望シフト: {submitted_count}名 入力済み / {total}名中\n"
            )
            if not_submitted > 0:
                check_text += f"⚠️ 未入力の職員: {not_submitted}名（希望なしとして処理）"
            else:
                check_text += "✅ 全職員の希望が入力済みです"

            self.check_label.setText(check_text)
        except Exception as e:
            self.check_label.setText(f"チェック失敗: {e}")

    def _run_scheduler(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_area.clear()
        self._log(f"=== 自動作成開始: {self._year}年{self._month}月 ===")

        self._worker = SchedulerWorker(
            year=self._year,
            month=self._month,
            time_limit=self.time_limit_spin.value(),
        )
        self._worker.log_signal.connect(self._log)
        self._worker.progress_signal.connect(self.progress_bar.setValue)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _cancel_scheduler(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._log("キャンセルされました")
            self._reset_buttons()

    def _on_finished(self, is_optimal: bool, message: str) -> None:
        self._log(f"\n{'✅' if is_optimal else '⚠️'} {message}")
        self._reset_buttons()
        self.main_window.log(message)
        QMessageBox.information(
            self,
            "完了",
            message + "\n\n「シフト確認・調整」タブで結果を確認してください。",
        )

    def _reset_buttons(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)

    def _log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{ts}] {msg}")
        logger.info(msg)
