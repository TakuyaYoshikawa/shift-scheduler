"""
ui/result/monthly_grid.py

4-A 月次シフト表（職員×日付グリッド）。
シフト種別ごとに背景色、手動修正済みセルは紫枠、
制約違反セルは赤背景でハイライトする。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)

SHIFT_COLORS: dict[str, QColor] = {
    "Y":  QColor("#D4A0D4"),
    "Ⓑ":  QColor("#FFD6A0"),
    "B":  QColor("#A0B4D4"),
    "C":  QColor("#A0D4A0"),
    "Ⓒ":  QColor("#B4D4A0"),
    "DG": QColor("#D4D4A0"),
    "P":  QColor("#D4D4D4"),
    "A":  QColor("#D4A0A0"),
}

COLOR_SUNDAY   = QColor("#FFEEEE")
COLOR_SATURDAY = QColor("#EEF0FF")
COLOR_VIOLATION = QColor("#FF8080")
COLOR_MODIFIED  = QColor("#CC88FF")  # 手動修正済み枠色


class MonthlyGrid(QWidget):
    """月次シフト表グリッド。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        year, month = main_window.get_year_month()
        self._year = year
        self._month = month
        self._jp_holidays: set[date] = set()
        self._load_holidays()
        self._setup_ui()
        self.refresh()

    def _load_holidays(self) -> None:
        try:
            import holidays
            jp = holidays.Japan(years=[self._year])
            self._jp_holidays = {d for d in jp.keys() if d.year == self._year}
        except Exception:
            self._jp_holidays = set()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ツールバー
        toolbar = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Yu Gothic UI", 11, QFont.Weight.Bold))
        toolbar.addWidget(self.title_label)
        toolbar.addStretch()

        self.badge_label = QLabel()
        toolbar.addWidget(self.badge_label)

        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # グリッド
        self.table = QTableWidget()
        self.table.setFont(QFont("Yu Gothic UI", 9))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

    def set_year_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._load_holidays()
        self.refresh()

    def refresh(self) -> None:
        self.title_label.setText(f"{self._year}年{self._month}月 月次シフト表")
        days = calendar.monthrange(self._year, self._month)[1]
        employees = db.get_optimizer_target_employees()

        results = db.get_shift_results(self._year, self._month)
        # {(employee_id, day): shift_code}
        result_map: dict[tuple[int, int], str] = {
            (r["employee_id"], r["assignment_day"]): r["shift_code"] or ""
            for r in results
        }

        # 手動修正ログ
        logs = db.get_result_logs(self._year, self._month)
        manual_keys = {
            (l["employee_id"], l["assignment_day"])
            for l in logs if l["change_type"] == "manual_edit"
        }

        # 夜勤配置人数の計算
        yakkin_per_day: dict[int, int] = {}
        for r in results:
            if r["shift_id"] == 20:
                d = r["assignment_day"]
                yakkin_per_day[d] = yakkin_per_day.get(d, 0) + 1

        violation_count = sum(1 for d in range(1, days + 1) if yakkin_per_day.get(d, 0) < 2)

        # テーブル構築
        WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
        self.table.setColumnCount(1 + days + 1)
        self.table.setRowCount(len(employees) + 1)  # +1 for フッター

        headers = ["氏名"]
        for d in range(1, days + 1):
            dt = date(self._year, self._month, d)
            wd = WEEKDAY_LABELS[dt.weekday()]
            headers.append(f"{d}\n{wd}")
        headers.append("計")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setDefaultSectionSize(38)

        manual_count = 0
        for row, emp in enumerate(employees):
            emp_id = emp["employee_id"]
            name_item = QTableWidgetItem(emp["sur_name"] or emp["employee_name"] or "")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            workdays = 0
            for d in range(1, days + 1):
                code = result_map.get((emp_id, d), "")
                col = d
                item = QTableWidgetItem(code)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, (emp_id, d))

                # 背景色
                if code in SHIFT_COLORS:
                    item.setBackground(SHIFT_COLORS[code])
                else:
                    dt = date(self._year, self._month, d)
                    if dt in self._jp_holidays or dt.weekday() == 6:
                        item.setBackground(COLOR_SUNDAY)
                    elif dt.weekday() == 5:
                        item.setBackground(COLOR_SATURDAY)

                # 手動修正済み枠（前景色で代替表示）
                if (emp_id, d) in manual_keys:
                    item.setForeground(QBrush(COLOR_MODIFIED))
                    manual_count += 1

                if code:
                    workdays += 1
                self.table.setItem(row, col, item)

            total_item = QTableWidgetItem(str(workdays))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1 + days, total_item)

        # フッター行（夜勤配置人数）
        footer_row = len(employees)
        footer_label = QTableWidgetItem("夜勤計")
        footer_label.setFlags(footer_label.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(footer_row, 0, footer_label)

        for d in range(1, days + 1):
            count = yakkin_per_day.get(d, 0)
            item = QTableWidgetItem(str(count))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if count < 2:
                item.setBackground(COLOR_VIOLATION)
            self.table.setItem(footer_row, d, item)

        self.table.setItem(footer_row, 1 + days, QTableWidgetItem(""))

        # バッジ更新
        badge_parts = []
        if manual_count > 0:
            badge_parts.append(f"手動修正 {manual_count // 2} 件")  # 往復分で割る
        if violation_count > 0:
            badge_parts.append(f"警告 {violation_count} 件")
        self.badge_label.setText("  ".join(badge_parts))

        self.table.resizeRowsToContents()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """セルクリック時に手動調整パネルを開く。"""
        if col == 0 or col > calendar.monthrange(self._year, self._month)[1]:
            return
        item = self.table.item(row, col)
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        emp_id, day = data

        from ui.result.adjust_panel import AdjustPanel
        panel = AdjustPanel(self, self._year, self._month, emp_id, day)
        if panel.exec():
            self.refresh()
