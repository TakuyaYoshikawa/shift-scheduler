"""
ui/result/history_view.py

4-D 修正履歴ビュー。自動計算後に加えた手動修正をすべてログとして記録・表示する。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)


class HistoryView(QWidget):
    """修正履歴ビュー。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        year, month = main_window.get_year_month()
        self._year = year
        self._month = month
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Yu Gothic UI", 11, QFont.Weight.Bold))
        toolbar.addWidget(self.title_label)
        toolbar.addStretch()

        btn_revert = QPushButton("すべて取り消し（自動計算結果に戻す）")
        btn_revert.clicked.connect(self._revert_all)
        toolbar.addWidget(btn_revert)

        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["日時", "変更内容", "種別", "日付"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

    def set_year_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self.refresh()

    def refresh(self) -> None:
        self.title_label.setText(f"{self._year}年{self._month}月 修正履歴")
        logs = db.get_result_logs(self._year, self._month)
        self.table.setRowCount(len(logs))

        for row, log in enumerate(logs):
            emp_name = log.get("employee_name") or f"ID:{log['employee_id']}"
            before = log.get("before_code") or "未配置"
            after = log.get("after_code") or "削除"
            change_desc = f"{emp_name}: {before} → {after}"

            change_type_map = {
                "manual_edit": "手動",
                "manual_delete": "手動削除",
                "manual_add": "手動追加",
                "auto_calc": "自動",
            }
            change_type = change_type_map.get(log["change_type"], log["change_type"])

            self.table.setItem(row, 0, QTableWidgetItem(str(log.get("changed_at", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(change_desc))
            self.table.setItem(row, 2, QTableWidgetItem(change_type))
            self.table.setItem(
                row, 3,
                QTableWidgetItem(f"{self._month}/{log['assignment_day']}")
            )

    def _revert_all(self) -> None:
        """自動計算結果（auto_calc）にすべて巻き戻す。"""
        reply = QMessageBox.question(
            self, "確認",
            "すべての手動修正を取り消し、自動計算結果に戻しますか？\n"
            "この操作は元に戻せません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        logs = db.get_result_logs(self._year, self._month)
        # 最新のauto_calcセットを取得
        auto_calc_entries = [l for l in logs if l["change_type"] == "auto_calc"]
        if not auto_calc_entries:
            QMessageBox.information(self, "情報", "自動計算履歴が見つかりません")
            return

        # 手動修正を削除してauto_calcの状態に戻す
        # auto_calc のentryは after_shift_id に自動配置結果が入っている
        db.clear_shift_results(self._year, self._month)

        restored = 0
        for entry in auto_calc_entries:
            if entry.get("after_shift_id") is not None:
                sm = db.get_shift(entry["after_shift_id"])
                emp = db.get_employee(entry["employee_id"])
                db.insert_shift_result(
                    year=self._year,
                    month=self._month,
                    assignment_day=entry["assignment_day"],
                    employee_id=entry["employee_id"],
                    shift_id=entry["after_shift_id"],
                    shift_name=sm["shift_name"] if sm else None,
                    shift_code=sm["shift_code"] if sm else None,
                    sur_name=emp["sur_name"] if emp else None,
                )
                restored += 1

        self.main_window.log(f"手動修正を取り消し、自動計算結果({restored}件)に戻しました")
        self.refresh()
        QMessageBox.information(self, "完了", f"自動計算結果({restored}件)に戻しました")
