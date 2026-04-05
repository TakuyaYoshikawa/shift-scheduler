"""
ui/result/han_view.py

4-B 班別配当表ビュー。週タブ（第1〜4週）で切り替え、
Excelシート「1」〜「4」と同じ列構造を再現する。
セルクリックで人員をドロップダウン選択（同日重複防止あり）。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QTabWidget, QHeaderView, QDialog,
    QComboBox, QDialogButtonBox, QFormLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 色定数
# ---------------------------------------------------------------------------
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

COLOR_SUNDAY   = QColor("#FFE8E8")
COLOR_SATURDAY = QColor("#E8E8FF")

# 班グループ → (セル背景色, ヘッダー背景色)
GROUP_COLORS: list[tuple[list[str], QColor, QColor]] = [
    (["戸外班\n"],  QColor("#FFFFFF"), QColor("#DDEEFF")),   # 白 / 薄青
    (["生活班1\n"], QColor("#F4F4F4"), QColor("#D8EED8")),   # 薄グレー / 薄緑
    (["生活班2\n"], QColor("#FFFFFF"), QColor("#DDEEFF")),   # 白 / 薄青
    (["清掃\n"],    QColor("#F4F4F4"), QColor("#EEE8D8")),   # 薄グレー / 薄黄
    (["夜勤\n"],    QColor("#FFFFFF"), QColor("#EED8EE")),   # 白 / 薄紫
    (["宿直\n"],    QColor("#F4F4F4"), QColor("#FFE8CC")),   # 薄グレー / 薄橙
    (["事務所", "医務", "世話人"], QColor("#FFFFFF"), QColor("#E8E8E8")),  # 白 / 薄グレー
]


def _group_colors(col_label: str) -> tuple[QColor, QColor]:
    """列ラベルから (セル背景色, ヘッダー背景色) を返す。"""
    for prefixes, cell_bg, header_bg in GROUP_COLORS:
        for prefix in prefixes:
            if col_label.startswith(prefix) or col_label == prefix:
                return cell_bg, header_bg
    return QColor("#FFFFFF"), QColor("#E0E0E0")


# ---------------------------------------------------------------------------
# 列定義
# ---------------------------------------------------------------------------
COLS_WEEK_1_3 = [
    ("戸外班\nA",  45), ("戸外班\nB", 45), ("戸外班\nC", 45), ("戸外班\nⒸ", 45), ("戸外班\nDG", 45), ("戸外班\nP",  45),
    ("生活班1\nA",  45), ("生活班1\nB", 45), ("生活班1\nC", 45), ("生活班1\nⒸ", 45), ("生活班1\nDG", 45), ("生活班1\nP",  45),
    ("生活班2\nA",  45), ("生活班2\nB", 45), ("生活班2\nC", 45), ("生活班2\nⒸ", 45), ("生活班2\nDG", 45), ("生活班2\nP",  45),
    ("清掃\nP", 45), ("夜勤\nY", 45), ("宿直\nⒷ", 45),
    ("事務所", 55), ("医務", 45), ("世話人", 55),
]

COLS_WEEK_4 = [
    ("戸外班\nA",  45), ("戸外班\nB", 45), ("戸外班\nC", 45), ("戸外班\nⒸ", 45), ("戸外班\nDG", 45), ("戸外班\nP",  45),
    ("生活班1\nA",  45), ("生活班1\nB", 45), ("生活班1\nC", 45), ("生活班1\nⒸ", 45), ("生活班1\nDG", 45), ("生活班1\nP",  45),
    ("生活班2\nA",  45), ("生活班2\nB", 45), ("生活班2\nC", 45), ("生活班2\nⒸ", 45), ("生活班2\nDG", 45), ("生活班2\nP",  45),
    ("清掃\nP", 45), ("夜勤\nY", 45),
    ("事務所", 55), ("医務", 45), ("世話人", 55),
]

# 手動入力列ラベルのセット
MANUAL_COL_LABELS = {"事務所", "医務", "世話人"}


def shift_to_col_label(shift_name: str, shift_code: str) -> str:
    name_map = {
        "戸外班": "戸外班", "生活班1": "生活班1", "生活班2": "生活班2",
        "清掃": "清掃", "夜勤": "夜勤", "宿直": "宿直",
    }
    prefix = name_map.get(shift_name, shift_name)
    return f"{prefix}\n{shift_code}"


# ---------------------------------------------------------------------------
# HanView
# ---------------------------------------------------------------------------
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

        # 同日に配置済みの名前セット {day: set(名前)}（重複防止用）
        used_names_per_day: dict[int, set[str]] = {}
        for r in results:
            d = r["assignment_day"]
            name = r["sur_name"] or ""
            if name:
                used_names_per_day.setdefault(d, set()).add(name)
        for m in manual:
            d = m["assignment_day"]
            name = m["staff_name"] or ""
            if name:
                used_names_per_day.setdefault(d, set()).add(name)

        weeks = self._calc_weeks(days_in_month)
        for week_idx, (week_start, week_end) in enumerate(weeks):
            is_last_week = week_idx == len(weeks) - 1
            cols = COLS_WEEK_4 if is_last_week else COLS_WEEK_1_3
            week_days = list(range(week_start, week_end + 1))
            table = self._build_week_table(
                week_days, cols,
                result_by_day_col, manual_by_key, used_names_per_day,
            )
            label = f"第{week_idx + 1}週 ({week_start}〜{week_end}日)"
            self.week_tabs.addTab(table, label)

    def _calc_weeks(self, days_in_month: int) -> list[tuple[int, int]]:
        starts = [1, 8, 15, 22]
        weeks = []
        for i, start in enumerate(starts):
            if start > days_in_month:
                break
            end = starts[i + 1] - 1 if i + 1 < len(starts) else days_in_month
            weeks.append((start, min(end, days_in_month)))
        return weeks

    def _build_week_table(
        self,
        week_days: list[int],
        cols: list[tuple[str, int]],
        result_by_day_col: dict[tuple[int, str], list[str]],
        manual_by_key: dict[tuple[int, int, str], str],
        used_names_per_day: dict[int, set[str]],
    ) -> QTableWidget:
        SUB_ROWS = 3
        col_count = 2 + len(cols)
        row_count = len(week_days) * SUB_ROWS

        table = QTableWidget(row_count, col_count)
        table.setFont(QFont("Yu Gothic UI", 9))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # ヘッダー設定
        headers = ["日付", "行"] + [c[0] for c in cols]
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for i, (col_label, width) in enumerate(cols):
            table.setColumnWidth(i + 2, width)
            # ヘッダーセルに色を設定
            h_item = table.horizontalHeaderItem(i + 2)
            if h_item is None:
                h_item = QTableWidgetItem(col_label)
                table.setHorizontalHeaderItem(i + 2, h_item)
            _, header_bg = _group_colors(col_label)
            h_item.setBackground(header_bg)

        WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

        for day_idx, day in enumerate(week_days):
            dt = date(self._year, self._month, day)
            wd = WEEKDAY_LABELS[dt.weekday()]
            is_sunday_or_holiday = dt in self._jp_holidays or dt.weekday() == 6
            is_saturday = dt.weekday() == 5

            for sub_row in range(SUB_ROWS):
                table_row = day_idx * SUB_ROWS + sub_row

                if sub_row == 0:
                    date_item = QTableWidgetItem(f"{day}日({wd})")
                    date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(table_row, 0, date_item)
                    table.setSpan(table_row, 0, SUB_ROWS, 1)

                sub_item = QTableWidgetItem(str(sub_row + 1))
                sub_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(table_row, 1, sub_item)

                for col_idx, (col_label, _) in enumerate(cols):
                    table_col = col_idx + 2
                    is_manual = col_label in MANUAL_COL_LABELS

                    # 値の取得
                    if is_manual:
                        value = manual_by_key.get((day, sub_row + 1, col_label), "")
                    else:
                        auto_values = result_by_day_col.get((day, col_label), [])
                        value = auto_values[sub_row] if sub_row < len(auto_values) else ""
                        if not value:
                            value = manual_by_key.get((day, sub_row + 1, col_label), "")

                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    # 背景色（優先順位: シフト色 > 土日 > 班グループ）
                    cell_bg, _ = _group_colors(col_label)
                    item.setBackground(cell_bg)
                    if is_sunday_or_holiday:
                        item.setBackground(COLOR_SUNDAY)
                    elif is_saturday:
                        item.setBackground(COLOR_SATURDAY)
                    if value and value in SHIFT_COLORS:
                        item.setBackground(SHIFT_COLORS[value])

                    # セルメタデータ（クリック時に使用）
                    item.setData(Qt.ItemDataRole.UserRole, {
                        "day": day,
                        "sub_row": sub_row + 1,
                        "col_label": col_label,
                        "is_manual": is_manual,
                        "value": value,
                    })

                    table.setItem(table_row, table_col, item)

        # クリックイベント（ラムダのスコープ問題を避けるため参照渡し）
        table.cellClicked.connect(
            lambda row, col, t=table, d=week_days, u=used_names_per_day:
                self._on_cell_clicked(t, row, col, d, u)
        )

        return table

    def _on_cell_clicked(
        self,
        table: QTableWidget,
        row: int,
        col: int,
        week_days: list[int],
        used_names_per_day: dict[int, set[str]],
    ) -> None:
        """セルクリック：人員選択ダイアログを表示する。"""
        if col < 2:
            return
        item = table.item(row, col)
        if item is None:
            return
        meta = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            return

        day = meta["day"]
        sub_row = meta["sub_row"]
        col_label = meta["col_label"]
        current_value = meta["value"]

        # 全職員の略称リスト
        all_employees = db.get_all_employees()
        all_names = [e["sur_name"] or e["employee_name"] for e in all_employees if e["sur_name"] or e["employee_name"]]
        all_names = sorted(set(all_names))

        # 同日に既に配置済みの名前（自分自身は除外しない）
        used = set(used_names_per_day.get(day, set()))
        if current_value and current_value in used:
            used.discard(current_value)  # 現在の値は選択肢に残す

        # ダイアログ表示
        dlg = PersonSelectDialog(
            self,
            title=f"{self._month}/{day} {col_label.replace(chr(10), ' ')} ({sub_row}行目)",
            current=current_value,
            all_names=all_names,
            used_names=used,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_value = dlg.selected_name()

        # DBに保存
        db.upsert_manual_shift(
            year=self._year,
            month=self._month,
            assignment_day=day,
            sub_row=sub_row,
            column_label=col_label,
            staff_name=new_value if new_value else None,
        )

        # セルを即時更新
        item.setText(new_value)
        meta["value"] = new_value
        item.setData(Qt.ItemDataRole.UserRole, meta)

        # 背景色更新
        cell_bg, _ = _group_colors(col_label)
        item.setBackground(cell_bg)
        dt = date(self._year, self._month, day)
        if dt in self._jp_holidays or dt.weekday() == 6:
            item.setBackground(COLOR_SUNDAY)
        elif dt.weekday() == 5:
            item.setBackground(COLOR_SATURDAY)

        self.main_window.log(
            f"班別配当表更新: {self._month}/{day} {col_label.replace(chr(10), ' ')} "
            f"({sub_row}行目) → {new_value or '（削除）'}"
        )

        # used_names_per_day を更新
        day_used = used_names_per_day.setdefault(day, set())
        if current_value:
            day_used.discard(current_value)
        if new_value:
            day_used.add(new_value)


# ---------------------------------------------------------------------------
# 人員選択ダイアログ
# ---------------------------------------------------------------------------
class PersonSelectDialog(QDialog):
    """人員選択ダイアログ。使用済みの名前はグレーアウトして選べない。"""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        current: str,
        all_names: list[str],
        used_names: set[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("人員選択")
        self.setMinimumWidth(300)
        self._build_ui(title, current, all_names, used_names)

    def _build_ui(
        self, title: str, current: str, all_names: list[str], used_names: set[str]
    ) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))

        self._combo = QComboBox()
        self._combo.addItem("（空欄）", "")

        for name in all_names:
            self._combo.addItem(name, name)
            if name in used_names:
                idx = self._combo.count() - 1
                # モデルアイテムをグレーアウト・無効化
                model = self._combo.model()
                model_item = model.item(idx)
                if model_item:
                    model_item.setEnabled(False)
                    model_item.setForeground(QColor("#AAAAAA"))

        # 現在値を選択
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == current:
                self._combo.setCurrentIndex(i)
                break

        layout.addWidget(self._combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_name(self) -> str:
        return self._combo.currentData() or ""
