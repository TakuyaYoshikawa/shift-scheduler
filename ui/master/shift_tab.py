"""
ui/master/shift_tab.py

シフト種別マスタの一覧表示・追加/編集/削除。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QDialog, QFormLayout, QLineEdit, QLabel,
    QMessageBox, QHeaderView, QColorDialog,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)


class ShiftTab(QWidget):
    """シフト種別マスタ管理タブ。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ 追加")
        btn_add.clicked.connect(self._add_shift)
        btn_edit = QPushButton("✏ 編集")
        btn_edit.clicked.connect(self._edit_shift)
        btn_del = QPushButton("🗑 削除")
        btn_del.clicked.connect(self._delete_shift)
        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_del)
        toolbar.addStretch()
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "班名", "コード", "開始時刻", "終了時刻", "色"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_shift)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        shifts = db.get_all_shifts()
        self.table.setRowCount(len(shifts))
        for row, s in enumerate(shifts):
            self.table.setItem(row, 0, QTableWidgetItem(str(s["shift_id"])))
            self.table.setItem(row, 1, QTableWidgetItem(s["shift_name"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(s["shift_code"] or ""))
            self.table.setItem(row, 3, QTableWidgetItem(s["time_start"] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(s["time_end"] or ""))
            color_item = QTableWidgetItem(s["color_hex"] or "#FFFFFF")
            color_item.setBackground(QColor(s["color_hex"] or "#FFFFFF"))
            self.table.setItem(row, 5, color_item)

    def _get_selected_shift_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def _add_shift(self) -> None:
        dlg = ShiftDialog(self, shift_id=None)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.main_window.log("シフト種別を追加しました")

    def _edit_shift(self) -> None:
        sid = self._get_selected_shift_id()
        if sid is None:
            QMessageBox.information(self, "情報", "編集するシフトを選択してください")
            return
        dlg = ShiftDialog(self, shift_id=sid)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.main_window.log(f"シフト種別(ID:{sid})を更新しました")

    def _delete_shift(self) -> None:
        sid = self._get_selected_shift_id()
        if sid is None:
            QMessageBox.information(self, "情報", "削除するシフトを選択してください")
            return
        reply = QMessageBox.question(
            self, "確認", f"シフトID:{sid} を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_shift(sid)
            self.refresh()
            self.main_window.log(f"シフト種別(ID:{sid})を削除しました")


class ShiftDialog(QDialog):
    """シフト種別追加/編集ダイアログ。"""

    def __init__(self, parent: QWidget, shift_id: int | None) -> None:
        super().__init__(parent)
        self.shift_id = shift_id
        self._color = "#FFFFFF"
        self.setWindowTitle("シフト追加" if shift_id is None else "シフト編集")
        self.setMinimumWidth(400)
        self._setup_ui()
        if shift_id is not None:
            self._load_shift(shift_id)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("HH:MM")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("HH:MM")

        form.addRow("ID:", self.id_edit)
        form.addRow("班名:", self.name_edit)
        form.addRow("コード:", self.code_edit)
        form.addRow("開始時刻:", self.start_edit)
        form.addRow("終了時刻:", self.end_edit)
        layout.addLayout(form)

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("色:"))
        self.color_label = QLabel("  ")
        self.color_label.setFixedSize(40, 20)
        self.color_label.setAutoFillBackground(True)
        self.color_label.setStyleSheet("border: 1px solid gray;")
        btn_color = QPushButton("選択...")
        btn_color.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_label)
        color_layout.addWidget(btn_color)
        color_layout.addStretch()
        layout.addLayout(color_layout)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self._save)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _load_shift(self, shift_id: int) -> None:
        s = db.get_shift(shift_id)
        if not s:
            return
        self.id_edit.setText(str(s["shift_id"]))
        self.id_edit.setEnabled(False)
        self.name_edit.setText(s["shift_name"] or "")
        self.code_edit.setText(s["shift_code"] or "")
        self.start_edit.setText(s["time_start"] or "")
        self.end_edit.setText(s["time_end"] or "")
        self._color = s["color_hex"] or "#FFFFFF"
        self.color_label.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid gray;"
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name()
            self.color_label.setStyleSheet(
                f"background-color: {self._color}; border: 1px solid gray;"
            )

    def _save(self) -> None:
        try:
            sid = int(self.id_edit.text())
        except ValueError:
            QMessageBox.warning(self, "エラー", "IDは数値で入力してください")
            return

        name = self.name_edit.text().strip()
        code = self.code_edit.text().strip()
        if not name or not code:
            QMessageBox.warning(self, "エラー", "班名とコードは必須です")
            return

        db.insert_shift(
            shift_id=sid,
            shift_name=name,
            shift_code=code,
            shift_namecode=f"{name}{code}",
            time_start=self.start_edit.text().strip() or None,
            time_end=self.end_edit.text().strip() or None,
            color_hex=self._color,
        )
        self.accept()
