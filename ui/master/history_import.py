"""
ui/master/history_import.py

過去シフト履歴のExcelインポートUI（初回移行専用）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QFileDialog, QMessageBox, QSpinBox,
    QHeaderView,
)
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from core import db

logger = logging.getLogger(__name__)


class HistoryImportTab(QWidget):
    """過去履歴インポートタブ。"""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # インポートセクション
        import_group = QHBoxLayout()
        import_group.addWidget(QLabel("Excelファイル:"))
        self.file_label = QLabel("（ファイル未選択）")
        import_group.addWidget(self.file_label)
        btn_browse = QPushButton("参照...")
        btn_browse.clicked.connect(self._browse_file)
        import_group.addWidget(btn_browse)
        import_group.addStretch()
        layout.addLayout(import_group)

        year_month_layout = QHBoxLayout()
        year_month_layout.addWidget(QLabel("対象年:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2035)
        self.year_spin.setValue(2025)
        year_month_layout.addWidget(self.year_spin)
        year_month_layout.addWidget(QLabel("月:"))
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(2)
        year_month_layout.addWidget(self.month_spin)
        year_month_layout.addStretch()
        layout.addLayout(year_month_layout)

        btn_import = QPushButton("インポート実行")
        btn_import.clicked.connect(self._run_import)
        layout.addWidget(btn_import)

        # 初期データ投入ボタン
        btn_seed = QPushButton("マスタ初期データを投入（シフト種別・職員マスタ）")
        btn_seed.clicked.connect(self._run_seed)
        layout.addWidget(btn_seed)

        layout.addWidget(QLabel("インポート履歴:"))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["日時", "ファイル", "種別", "件数"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        logs = db.get_import_logs()
        self.table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self.table.setItem(row, 0, QTableWidgetItem(str(log["imported_at"])))
            self.table.setItem(row, 1, QTableWidgetItem(str(log["source_file"] or "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(log["record_type"] or "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(log["record_count"] or "")))

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Excelファイルを選択", "", "Excel ファイル (*.xlsx *.xls)"
        )
        if path:
            self.file_label.setText(path)

    def _run_import(self) -> None:
        file_path = self.file_label.text()
        if not file_path or file_path == "（ファイル未選択）":
            QMessageBox.warning(self, "エラー", "ファイルを選択してください")
            return

        year = self.year_spin.value()
        month = self.month_spin.value()

        from utils.excel_import import import_from_excel
        try:
            import_from_excel(file_path, year, month)
            self.main_window.log(f"インポート完了: {file_path}")
            self.refresh()
        except Exception as e:
            logger.exception("インポートエラー")
            QMessageBox.critical(self, "エラー", f"インポートに失敗しました:\n{e}")

    def _run_seed(self) -> None:
        reply = QMessageBox.question(
            self, "確認",
            "シフト種別と職員マスタの初期データを投入します。\n既存データは上書きされます。続行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from utils.excel_import import seed_shift_master, seed_employee_master, seed_employee_constraints
        try:
            seed_shift_master()
            seed_employee_master()
            seed_employee_constraints()
            self.main_window.log("マスタ初期データ投入完了")
            self.refresh()
            QMessageBox.information(self, "完了", "マスタ初期データの投入が完了しました")
        except Exception as e:
            logger.exception("シードエラー")
            QMessageBox.critical(self, "エラー", f"初期データ投入に失敗しました:\n{e}")
