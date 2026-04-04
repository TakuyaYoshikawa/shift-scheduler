"""
ui/result/han_view.py

4-B 班別配当表ビュー。週タブ（第1〜4週）で切り替え、
Excelシート「1」〜「4」と同じ列構造を再現する。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QTabWidget, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)

# シフトコード→表示色
SHIFT_COLORS: dict[str, QColor] = {
    "Y":  QColor("#D4A0D4"),
    "B2": QColor("#FFD6A0"),
    "B1": QColor("#A0B4D4"),
    "C1": QColor("#A0D4A0"),
    "C2": QColor("#B4D4A0"),
    "DG": QColor("#D4D4A0"),
    "P":  QColor("#D4D4D4"),
    "A":  QColor("#D4A0A0"),
}

COLOR_SUNDAY   = QColor("#FFE8E8")
COLOR_SATURDAY = QColor("#E8E8FF")

# 列ラベル定義（週1-3用: 宿直B2あり）
# 各列: (表示名, 幅ヒント)
COLS_WEEK_1_3 = [
    # 戸外班
    ("戸外A", 35),  ("戸外B1", 35), ("戸外C1", 35), ("戸外C2", 35), ("戸外DG", 35), ("戸外P", 35),
    # 生活班1
    ("生1A", 35),  ("生1B1", 35), ("生1C1", 35), ("生1C2", 35), ("生1DG", 35), ("生1P", 35),
    # 生活班2
    ("生2A", 35),  ("生2B1", 35), ("生2C1", 35), ("生2C2", 35), ("生2DG", 35), ("生2P", 35),
    # 清掃・夜勤・宿直
    ("清掃P", 40), ("夜勤Y", 40), ("宿直B2", 45),
    # 手動列
    ("事務所", 50), ("医務", 40), ("世話人", 50),
]

# 週4用: 宿直B2なし
COLS_WEEK_4 = [
    ("戸外A", 35),  ("戸外B1", 35), ("戸外C1", 35), ("戸外C2", 35), ("戸外DG", 35), ("戸外P", 35),
    ("生1A", 35),  ("生1B1", 35), ("生1C1", 35), ("生1C2", 35), ("生1DG", 35), ("生1P", 35),
    ("生2A", 35),  ("生2B1", 35), ("生2C1", 35), ("生2C2", 35), ("生2DG", 35), ("生2P", 35),
    ("清掃P", 40), ("夜勤Y", 40),
    ("事務所", 50), ("医務", 40), ("世話人", 50),
]

# shift_code ↔ 列インデックス（COLS_WEEK_1_3 ベース）
CODE_TO_COL_1_3: dict[str, int] = {
    # 戸外班
    "戸外A": 0, "戸外B1": 1, "戸外C1": 2, "戸外C2": 3, "戸外DG": 4, "戸外P": 5,
    # 生活班1
    "生1A": 6, "生1B1": 7, "生1C1": 8, "生1C2": 9, "生1DG": 10, "生1P": 11,
    # 生活班2
    "生2A": 12, "生2B1": 13, "生2C1": 14, "生2C2": 15, "生2DG": 16, "生2P": 17,
    # 清掃・夜勤・宿直
    "清掃P": 18, "夜勤Y": 19, "宿直B2": 20,
}

CODE_TO_COL_4: dict[str, int] = {
    "戸外A": 0, "戸外B1": 1, "戸外C1": 2, "戸外C2": 3, "戸外DG": 4, "戸外P": 5,
    "生1A": 6, "生1B1": 7, "生1C1": 8, "生1C2": 9, "生1DG": 10, "生1P": 11,
    "生2A": 12, "生2B1": 13, "生2C1": 14, "生2C2": 15, "生2DG": 16, "生2P": 17,
    "清掃P": 18, "夜勤Y": 19,
    # 宿直なし
}


def shift_to_col_label(shift_name: str, shift_code: str) -> str:
    """shift_name + shift_code から列ラベルを生成する。"""
    name_prefix_map = {
        "戸外班": "戸外",
        "生活班1": "生1",
        "生活班2": "生2",
        "清掃": "清掃",
        "夜勤": "夜勤",
        "宿直": "宿直",
    }
    prefix = name_prefix_map.get(shift_name, "")
    if prefix:
        return f"{prefix}{shift_code}"
    return shift_code


class HanView(QWidget):
    """班別配当表ビュー（週タブ切り替え）。"""

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

        toolbar = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Yu Gothic UI", 11, QFont.Weight.Bold))
        toolbar.addWidget(self.title_label)
        toolbar.addStretch()
        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.week_tabs = QTabWidget()
        layout.addWidget(self.week_tabs)

    def set_year_month(self, year: int, month: int) -> None:
        self._year = year
        self._month = month
        self._load_holidays()
        self.refresh()

    def refresh(self) -> None:
        self.title_label.setText(f"{self._year}年{self._month}月 班別配当表")
        self.week_tabs.clear()

        days_in_month = calendar.monthrange(self._year, self._month)[1]
        results = db.get_shift_results(self._year, self._month)
        manual = db.get_manual_shifts(self._year, self._month)
        shifts = db.get_all_shifts()
        shift_map = {s["shift_id"]: s for s in shifts}

        # shift_result → {(day, col_label): [sur_name, ...]}
        result_by_day_col: dict[tuple[int, str], list[str]] = {}
        for r in results:
            s = shift_map.get(r["shift_id"])
            if not s:
                continue
            col_label = shift_to_col_label(s["shift_name"], s["shift_code"])
            key = (r["assignment_day"], col_label)
            result_by_day_col.setdefault(key, []).append(r["sur_name"] or "")

        # manual → {(day, sub_row, col_label): staff_name}
        manual_by_key: dict[tuple[int, int, str], str] = {
            (m["assignment_day"], m["sub_row"], m["column_label"]): m["staff_name"] or ""
            for m in manual
        }

        # 週の範囲を計算
        weeks = self._calc_weeks(days_in_month)

        for week_idx, (week_start, week_end) in enumerate(weeks):
            is_last_week = week_idx == len(weeks) - 1
            cols = COLS_WEEK_4 if is_last_week else COLS_WEEK_1_3
            code_to_col = CODE_TO_COL_4 if is_last_week else CODE_TO_COL_1_3

            week_days = list(range(week_start, week_end + 1))
            table = self._build_week_table(
                week_days, cols, code_to_col,
                result_by_day_col, manual_by_key
            )
            label = f"第{week_idx + 1}週 ({week_start}〜{week_end}日)"
            self.week_tabs.addTab(table, label)

    def _calc_weeks(self, days_in_month: int) -> list[tuple[int, int]]:
        """月を第1週〜第4週に分割する（日〜土 or 月末で区切る）。"""
        weeks = []
        # 第1週: 1〜7日
        # 第2週: 8〜14日
        # 第3週: 15〜21日
        # 第4週: 22〜末日
        starts = [1, 8, 15, 22]
        for i, start in enumerate(starts):
            if start > days_in_month:
                break
            end = starts[i + 1] - 1 if i + 1 < len(starts) else days_in_month
            end = min(end, days_in_month)
            weeks.append((start, end))
        return weeks

    def _build_week_table(
        self,
        week_days: list[int],
        cols: list[tuple[str, int]],
        code_to_col: dict[str, int],
        result_by_day_col: dict[tuple[int, str], list[str]],
        manual_by_key: dict[tuple[int, int, str], str],
    ) -> QTableWidget:
        """1週分のテーブルを構築する。"""
        SUB_ROWS = 3
        col_count = 2 + len(cols)  # 日付列 + サブ行列 + シフト列
        row_count = len(week_days) * SUB_ROWS

        table = QTableWidget(row_count, col_count)
        table.setFont(QFont("Yu Gothic UI", 9))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # ヘッダー
        headers = ["日付", "行"] + [c[0] for c in cols]
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for i, (_, width) in enumerate(cols):
            table.setColumnWidth(i + 2, width)

        WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

        for day_idx, day in enumerate(week_days):
            dt = date(self._year, self._month, day)
            wd = WEEKDAY_LABELS[dt.weekday()]
            is_sunday_or_holiday = dt in self._jp_holidays or dt.weekday() == 6
            is_saturday = dt.weekday() == 5

            for sub_row in range(SUB_ROWS):
                table_row = day_idx * SUB_ROWS + sub_row

                # 日付列（最初のサブ行のみ表示）
                if sub_row == 0:
                    date_item = QTableWidgetItem(f"{day}日({wd})")
                    date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(table_row, 0, date_item)
                    table.setSpan(table_row, 0, SUB_ROWS, 1)

                # サブ行番号
                sub_item = QTableWidgetItem(str(sub_row + 1))
                sub_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(table_row, 1, sub_item)

                # シフト列を埋める
                for col_idx, (col_label, _) in enumerate(cols):
                    table_col = col_idx + 2

                    # 自動配置結果
                    auto_values = result_by_day_col.get((day, col_label), [])
                    value = auto_values[sub_row] if sub_row < len(auto_values) else ""

                    # 手動入力（auto_valueが空の場合のみ）
                    if not value:
                        value = manual_by_key.get((day, sub_row + 1, col_label), "")

                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    # 背景色（土日着色）
                    if is_sunday_or_holiday:
                        item.setBackground(COLOR_SUNDAY)
                    elif is_saturday:
                        item.setBackground(COLOR_SATURDAY)

                    # シフト色
                    if value and value in SHIFT_COLORS:
                        item.setBackground(SHIFT_COLORS[value])

                    table.setItem(table_row, table_col, item)

        return table
