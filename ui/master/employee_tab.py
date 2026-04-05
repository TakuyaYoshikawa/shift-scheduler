"""
ui/master/employee_tab.py

職員マスタの一覧表示・追加/編集/削除ダイアログ。
担当可能シフトのチェックボックス、同日禁止ペアの管理も含む。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QDialog, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QScrollArea, QLabel, QMessageBox, QHeaderView,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)


class EmployeeTab(QWidget):
    """職員マスタ管理タブ。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ツールバー
        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ 追加")
        btn_add.clicked.connect(self._add_employee)
        btn_edit = QPushButton("✏ 編集")
        btn_edit.clicked.connect(self._edit_employee)
        btn_del = QPushButton("🗑 削除")
        btn_del.clicked.connect(self._delete_employee)
        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_del)
        toolbar.addStretch()
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "氏名", "略称", "所属", "班", "最適化対象"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_employee)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        """テーブルを更新する。"""
        employees = db.get_all_employees()
        self.table.setRowCount(len(employees))
        for row, emp in enumerate(employees):
            self.table.setItem(row, 0, QTableWidgetItem(str(emp["employee_id"])))
            self.table.setItem(row, 1, QTableWidgetItem(emp["employee_name"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(emp["sur_name"] or ""))
            self.table.setItem(row, 3, QTableWidgetItem(emp["section"] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(emp["group_name"] or ""))
            target = "☑" if emp["is_optimizer_target"] else "☐"
            self.table.setItem(row, 5, QTableWidgetItem(target))

    def _get_selected_employee_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def _add_employee(self) -> None:
        dlg = EmployeeDialog(self, employee_id=None)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.main_window.log("職員を追加しました")

    def _edit_employee(self) -> None:
        emp_id = self._get_selected_employee_id()
        if emp_id is None:
            QMessageBox.information(self, "情報", "編集する職員を選択してください")
            return
        dlg = EmployeeDialog(self, employee_id=emp_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.main_window.log(f"職員(ID:{emp_id})を更新しました")

    def _delete_employee(self) -> None:
        emp_id = self._get_selected_employee_id()
        if emp_id is None:
            QMessageBox.information(self, "情報", "削除する職員を選択してください")
            return
        emp = db.get_employee(emp_id)
        name = emp["employee_name"] if emp else str(emp_id)
        reply = QMessageBox.question(
            self, "確認", f"{name} を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_employee(emp_id)
            self.refresh()
            self.main_window.log(f"職員(ID:{emp_id} {name})を削除しました")


class EmployeeDialog(QDialog):
    """職員追加/編集ダイアログ。"""

    def __init__(self, parent: QWidget, employee_id: int | None) -> None:
        super().__init__(parent)
        self.employee_id = employee_id
        self.setWindowTitle("職員追加" if employee_id is None else "職員編集")
        self.setMinimumWidth(500)
        self._setup_ui()
        if employee_id is not None:
            self._load_employee(employee_id)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_label = QLabel()  # 追加時は自動採番、表示のみ
        self.name_edit = QLineEdit()
        self.surname_edit = QLineEdit()
        self.section_edit = QLineEdit()
        self.group_edit = QLineEdit()
        self.work_hours_edit = QLineEdit()
        self.notes_edit = QLineEdit()
        self.optimizer_check = QCheckBox("最適化対象")
        self.optimizer_check.setChecked(True)

        # 追加時は自動採番、編集時は既存IDを表示
        if self.employee_id is None:
            next_id = db.next_employee_id()
            self.id_label.setText(f"{next_id}（自動採番）")
            self._auto_id = next_id
        else:
            self.id_label.setText(str(self.employee_id))
            self._auto_id = self.employee_id

        form.addRow("ID:", self.id_label)
        form.addRow("氏名:", self.name_edit)
        form.addRow("略称:", self.surname_edit)
        form.addRow("所属:", self.section_edit)
        form.addRow("班:", self.group_edit)
        form.addRow("勤務時間:", self.work_hours_edit)
        form.addRow("備考:", self.notes_edit)
        form.addRow("", self.optimizer_check)
        layout.addLayout(form)

        # 担当可能シフト
        layout.addWidget(QLabel("担当可能シフト:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        cap_widget = QWidget()
        cap_layout = QVBoxLayout(cap_widget)
        self.shift_checks: dict[int, QCheckBox] = {}
        shifts = db.get_all_shifts()
        for s in shifts:
            cb = QCheckBox(f"{s['shift_name']} [{s['shift_code']}] (ID:{s['shift_id']})")
            self.shift_checks[s["shift_id"]] = cb
            cap_layout.addWidget(cb)
        scroll.setWidget(cap_widget)
        layout.addWidget(scroll)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self._save)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _load_employee(self, employee_id: int) -> None:
        emp = db.get_employee(employee_id)
        if not emp:
            return
        self.id_label.setText(str(emp["employee_id"]))
        self._auto_id = emp["employee_id"]
        self.name_edit.setText(emp["employee_name"] or "")
        self.surname_edit.setText(emp["sur_name"] or "")
        self.section_edit.setText(emp["section"] or "")
        self.group_edit.setText(emp["group_name"] or "")
        self.work_hours_edit.setText(emp["work_hours"] or "")
        self.notes_edit.setText(emp["notes"] or "")
        self.optimizer_check.setChecked(bool(emp["is_optimizer_target"]))

        caps = set(db.get_employee_capabilities(employee_id))
        for sid, cb in self.shift_checks.items():
            cb.setChecked(sid in caps)

    def _save(self) -> None:
        emp_id = self._auto_id

        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "エラー", "氏名を入力してください")
            return

        db.insert_employee(
            employee_id=emp_id,
            employee_name=name,
            sur_name=self.surname_edit.text().strip() or None,
            section=self.section_edit.text().strip() or None,
            group_name=self.group_edit.text().strip() or None,
            work_hours=self.work_hours_edit.text().strip() or None,
            is_optimizer_target=1 if self.optimizer_check.isChecked() else 0,
            notes=self.notes_edit.text().strip() or None,
        )

        selected_shifts = [sid for sid, cb in self.shift_checks.items() if cb.isChecked()]
        db.set_employee_capabilities(emp_id, selected_shifts)

        self.accept()
