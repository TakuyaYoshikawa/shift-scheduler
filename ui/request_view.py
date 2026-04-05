"""
ui/request_view.py

希望シフト入力グリッド（QTableWidget ベース）。
職員×日付のグリッドでシフト希望・休暇を入力・保存する。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QHeaderView, QMessageBox,
    QAbstractItemView, QFileDialog,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QBrush, QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)

# 土日・祝日の着色
COLOR_SUNDAY    = QColor("#FFCCCC")
COLOR_SATURDAY  = QColor("#CCE0FF")
COLOR_HOLIDAY   = QColor("#FFCCCC")
COLOR_VACATION  = QColor("#D0D0D0")

# シフトコード → 色
SHIFT_COLORS: dict[str, QColor] = {
    "Y":  QColor("#D4A0D4"),
    "Ⓑ":  QColor("#FFD6A0"),
    "B":  QColor("#A0B4D4"),
    "C":  QColor("#A0D4A0"),
    "Ⓒ":  QColor("#B4D4A0"),
    "DG": QColor("#D4D4A0"),
    "P":  QColor("#D4D4D4"),
    "A":  QColor("#D4A0A0"),
    "休": QColor("#D0D0D0"),
}

SHIFT_CHOICES = ["", "Y", "B", "C", "Ⓒ", "DG", "A", "P", "Ⓑ", "休暇"]

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


class RequestView(QWidget):
    """希望シフト入力ビュー。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        year, month = main_window.get_year_month()
        self._year = year
        self._month = month
        self._jp_holidays: set[date] = set()
        self._load_holidays()
        self._setup_ui()
        self._load_grid()

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

        btn_clear = QPushButton("一括クリア")
        btn_clear.clicked.connect(self._clear_all)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._save)
        btn_csv = QPushButton("CSVエクスポート")
        btn_csv.clicked.connect(self._export_csv)

        toolbar.addWidget(btn_clear)
        toolbar.addWidget(btn_save)
        toolbar.addWidget(btn_csv)
        layout.addLayout(toolbar)

        # グリッド
        self.table = QTableWidget()
        self.table.setFont(QFont("Yu Gothic UI", 9))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

    def set_year_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._load_holidays()
        self._load_grid()

    def _load_grid(self) -> None:
        self.title_label.setText(f"{self._year}年{self._month}月 希望シフト入力")
        days = calendar.monthrange(self._year, self._month)[1]
        employees = db.get_all_employees()

        # 既存の希望データ
        submitted = db.get_submitted_requests(self._year, self._month)
        req_map: dict[tuple[int, int], str] = {
            (r["employee_id"], r["day"]): r["request"] for r in submitted
        }

        # 列: 氏名 + 日付(1..days) + 合計
        self.table.setColumnCount(1 + days + 1)
        self.table.setRowCount(len(employees))

        # ヘッダー行
        headers = ["氏名"]
        for d in range(1, days + 1):
            dt = date(self._year, self._month, d)
            wd = WEEKDAY_LABELS[dt.weekday()]
            headers.append(f"{d}\n{wd}")
        headers.append("合計")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setSectionResizeMode(
            1 + days, QHeaderView.ResizeMode.ResizeToContents
        )

        # 列の着色（土日・祝日）
        col_colors: dict[int, QColor] = {}
        for d in range(1, days + 1):
            dt = date(self._year, self._month, d)
            col = 1 + d - 1
            if dt in self._jp_holidays or dt.weekday() == 6:  # 日祝
                col_colors[col] = COLOR_SUNDAY
            elif dt.weekday() == 5:  # 土
                col_colors[col] = COLOR_SATURDAY

        for row, emp in enumerate(employees):
            emp_id = emp["employee_id"]
            name_item = QTableWidgetItem(emp["employee_name"] or "")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            workdays = 0
            for d in range(1, days + 1):
                col = d  # 列インデックス（氏名列の次から）
                request = req_map.get((emp_id, d), "")
                item = QTableWidgetItem(request if request != "休暇" else "／")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, (emp_id, d))

                # 背景色設定
                if request == "休暇":
                    item.setBackground(COLOR_VACATION)
                elif request in SHIFT_COLORS:
                    item.setBackground(SHIFT_COLORS[request])
                elif col - 1 in col_colors:
                    item.setBackground(col_colors[col - 1])

                self.table.setItem(row, col, item)
                if request and request != "休暇":
                    workdays += 1

            # 合計列
            total_item = QTableWidgetItem(str(workdays))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1 + days, total_item)

        self.table.resizeRowsToContents()
        self._employees = employees
        self._days = days

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """セルクリック時にドロップダウンでシフトを選択する。"""
        if col == 0 or col > self._days:
            return

        item = self.table.item(row, col)
        if item is None:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return

        emp_id, day = data
        current = item.text()
        if current == "／":
            current = "休暇"

        # ドロップダウン選択
        combo = QComboBox()
        combo.addItems(SHIFT_CHOICES)
        if current in SHIFT_CHOICES:
            combo.setCurrentText(current)
        combo.currentTextChanged.connect(
            lambda val, r=row, c=col, eid=emp_id, d=day: self._apply_shift(r, c, eid, d, val)
        )

        dlg_pos = self.table.viewport().mapToGlobal(
            self.table.visualItemRect(item).bottomLeft()
        )
        combo.move(dlg_pos)
        combo.showPopup()

        # インラインで表示（簡易実装）
        self.table.setCellWidget(row, col, combo)
        combo.activated.connect(lambda: self._finalize_combo(row, col, combo))

    def _finalize_combo(self, row: int, col: int, combo: QComboBox) -> None:
        val = combo.currentText()
        item = self.table.item(row, col)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                emp_id, day = data
                self._apply_shift(row, col, emp_id, day, val)
        self.table.removeCellWidget(row, col)

    def _apply_shift(self, row: int, col: int, emp_id: int, day: int, value: str) -> None:
        """シフト値をセルに反映する（未保存）。"""
        item = self.table.item(row, col)
        if item is None:
            return

        if value == "" or value is None:
            display = ""
            bg = QColor("#FFFFFF")
        elif value == "休暇":
            display = "／"
            bg = COLOR_VACATION
        else:
            display = value
            bg = SHIFT_COLORS.get(value, QColor("#FFFFFF"))

        item.setText(display)
        item.setBackground(bg)
        item.setData(Qt.ItemDataRole.UserRole + 1, value)  # 変更値を保持

        self.table.removeCellWidget(row, col)

    def _clear_all(self) -> None:
        reply = QMessageBox.question(
            self, "確認", "すべての入力をクリアしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.clear_submitted_requests(self._year, self._month)
            self._load_grid()
            self.main_window.log(f"{self._year}年{self._month}月の希望シフトをクリアしました")

    def _save(self) -> None:
        """グリッドの変更をDBに保存する。"""
        saved = 0
        for row in range(self.table.rowCount()):
            for col in range(1, 1 + self._days):
                item = self.table.item(row, col)
                if item is None:
                    continue
                changed_val = item.data(Qt.ItemDataRole.UserRole + 1)
                if changed_val is None:
                    continue  # 変更なし

                data = item.data(Qt.ItemDataRole.UserRole)
                if data is None:
                    continue
                emp_id, day = data

                if changed_val == "" or changed_val is None:
                    db.delete_submitted_request(self._year, self._month, emp_id, day)
                else:
                    db.upsert_submitted_request(self._year, self._month, emp_id, day, changed_val)
                saved += 1
                item.setData(Qt.ItemDataRole.UserRole + 1, None)  # 変更フラグをリセット

        self._load_grid()
        self.main_window.log(f"希望シフト保存完了: {saved}件更新")
        QMessageBox.information(self, "保存完了", f"{saved}件の希望シフトを保存しました")

    def _export_csv(self) -> None:
        """希望シフトをCSVに出力する。"""
        path, _ = QFileDialog.getSaveFileName(
            self, "CSVエクスポート", f"希望シフト_{self._year}_{self._month:02d}.csv",
            "CSV ファイル (*.csv)"
        )
        if not path:
            return

        days = self._days
        employees = db.get_all_employees()
        submitted = db.get_submitted_requests(self._year, self._month)
        req_map = {(r["employee_id"], r["day"]): r["request"] for r in submitted}

        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                header = "氏名," + ",".join(str(d) for d in range(1, days + 1)) + "\n"
                f.write(header)
                for emp in employees:
                    row_data = [emp["employee_name"] or ""]
                    for d in range(1, days + 1):
                        row_data.append(req_map.get((emp["employee_id"], d), ""))
                    f.write(",".join(row_data) + "\n")
            self.main_window.log(f"CSVエクスポート完了: {path}")
        except Exception as e:
            logger.exception("CSVエクスポートエラー")
            QMessageBox.critical(self, "エラー", f"CSV出力に失敗しました:\n{e}")
