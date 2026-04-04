"""
ui/result/adjust_panel.py

4-C 手動調整パネル。月次グリッドまたは班別ビューからセルをクリックすると表示。
変更前に制約をリアルタイムチェックし、問題なければ保存できる。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QGroupBox, QScrollArea, QWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

if TYPE_CHECKING:
    pass

from core import db, constraints as const_module

logger = logging.getLogger(__name__)


class AdjustPanel(QDialog):
    """手動調整パネル。"""

    def __init__(
        self,
        parent: QWidget,
        year: int,
        month: int,
        employee_id: int,
        day: int,
    ) -> None:
        super().__init__(parent)
        self.year = year
        self.month = month
        self.employee_id = employee_id
        self.day = day
        self.setWindowTitle("手動調整")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._load_current()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ヘッダー
        emp = db.get_employee(self.employee_id)
        emp_name = emp["employee_name"] if emp else str(self.employee_id)
        header = QLabel(
            f"修正中: {emp_name} — {self.year}/{self.month}/{self.day}"
        )
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        # 現在のシフト
        current_result = db.get_shift_result_for_employee_day(
            self.year, self.month, self.employee_id, self.day
        )
        current_code = current_result["shift_code"] if current_result else "未配置"
        current_label = QLabel(f"現在のシフト: {current_code}")
        layout.addWidget(current_label)
        self._current_shift_id = current_result["shift_id"] if current_result else None

        # シフト選択
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("変更後:"))
        self.shift_combo = QComboBox()
        self.shift_combo.addItem("（削除・未配置）", None)
        shifts = db.get_all_shifts()
        for s in shifts:
            if s["shift_id"] <= 21:
                self.shift_combo.addItem(
                    f"{s['shift_name']} [{s['shift_code']}]",
                    s["shift_id"]
                )
        # 現在のシフトを選択状態に
        if self._current_shift_id:
            for i in range(self.shift_combo.count()):
                if self.shift_combo.itemData(i) == self._current_shift_id:
                    self.shift_combo.setCurrentIndex(i)
                    break
        self.shift_combo.currentIndexChanged.connect(self._on_shift_changed)
        select_layout.addWidget(self.shift_combo)
        layout.addLayout(select_layout)

        # 制約チェック結果
        layout.addWidget(QLabel("制約チェック（リアルタイム）:"))
        self.check_group = QGroupBox()
        self.check_layout = QVBoxLayout(self.check_group)
        layout.addWidget(self.check_group)

        # ボタン
        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("この変更を適用")
        self.btn_apply.clicked.connect(self._apply)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # 初期チェック実行
        self._on_shift_changed()

    def _load_current(self) -> None:
        pass

    def _on_shift_changed(self) -> None:
        """シフト選択変更時に制約チェックを実行する。"""
        new_shift_id: int | None = self.shift_combo.currentData()

        # チェック実行
        try:
            check_results = const_module.check_constraints_for_change(
                self.year, self.month, self.employee_id, self.day, new_shift_id
            )
        except Exception as e:
            logger.exception("制約チェックエラー")
            check_results = [{"label": "エラー", "ok": False, "message": str(e)}]

        # 表示クリア
        while self.check_layout.count():
            item = self.check_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        has_violation = False
        for result in check_results:
            icon = "✓" if result["ok"] else "✗"
            color = "green" if result["ok"] else "red"
            label = QLabel(
                f'<span style="color:{color}">{icon} {result["label"]}: {result["message"]}</span>'
            )
            label.setWordWrap(True)
            self.check_layout.addWidget(label)
            if not result["ok"]:
                has_violation = True

        self.btn_apply.setEnabled(not has_violation)

    def _apply(self) -> None:
        """変更を適用する。"""
        new_shift_id: int | None = self.shift_combo.currentData()

        before_shift_id = self._current_shift_id

        if new_shift_id is None:
            # 削除
            db.delete_shift_result_for_employee_day(
                self.year, self.month, self.employee_id, self.day
            )
        else:
            # 更新
            # 既存を削除してから挿入
            db.delete_shift_result_for_employee_day(
                self.year, self.month, self.employee_id, self.day
            )
            sm = db.get_shift(new_shift_id)
            emp = db.get_employee(self.employee_id)
            db.insert_shift_result(
                year=self.year,
                month=self.month,
                assignment_day=self.day,
                employee_id=self.employee_id,
                shift_id=new_shift_id,
                shift_name=sm["shift_name"] if sm else None,
                shift_code=sm["shift_code"] if sm else None,
                sur_name=emp["sur_name"] if emp else None,
            )

            # Y(夜勤)の翌日にB2(宿直明け)を自動設定
            import calendar as cal_mod
            days_in_month = cal_mod.monthrange(self.year, self.month)[1]
            if new_shift_id == 20 and self.day < days_in_month:
                b2_shifts = [s for s in db.get_all_shifts() if s["shift_code"] == "B2"]
                if b2_shifts:
                    b2_id = b2_shifts[0]["shift_id"]
                    db.delete_shift_result_for_employee_day(
                        self.year, self.month, self.employee_id, self.day + 1
                    )
                    db.insert_shift_result(
                        year=self.year,
                        month=self.month,
                        assignment_day=self.day + 1,
                        employee_id=self.employee_id,
                        shift_id=b2_id,
                        shift_name="宿直",
                        shift_code="B2",
                        sur_name=emp["sur_name"] if emp else None,
                    )

        # ログ記録
        db.add_result_log(
            year=self.year,
            month=self.month,
            assignment_day=self.day,
            employee_id=self.employee_id,
            change_type="manual_edit",
            before_shift_id=before_shift_id,
            after_shift_id=new_shift_id,
        )

        self.accept()
