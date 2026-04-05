"""
ui/main_window.py

メインウィンドウ。4タブ（マスタ管理・希望シフト入力・自動作成・確認調整）を管理する。
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QSplitter,
    QLabel,
    QHBoxLayout,
    QSpinBox,
    QStatusBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """シフト自動作成システムのメインウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("シフト自動作成システム")
        self.setMinimumSize(1280, 800)
        self._current_year = 2026
        self._current_month = 4
        self._setup_ui()

    def _setup_ui(self) -> None:
        # 中央ウィジェット
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ヘッダー（年月セレクタ）
        header = self._build_header()
        main_layout.addWidget(header)

        # コンテンツ（タブ + ログ）を縦分割
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        # タブ
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        splitter.addWidget(self.tab_widget)

        # ログエリア
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        self.log_area.setFont(QFont("Consolas", 9))
        self.log_area.setPlaceholderText("ログ出力エリア")
        splitter.addWidget(self.log_area)

        splitter.setSizes([600, 150])

        # タブを構築
        self._build_tabs()

        # ステータスバー
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("準備完了")

    def _build_header(self) -> QWidget:
        """年月セレクタヘッダーを構築する。"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)

        title = QLabel("シフト自動作成システム")
        title.setFont(QFont("Yu Gothic UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addStretch()

        layout.addWidget(QLabel("年:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2035)
        self.year_spin.setValue(self._current_year)
        self.year_spin.setFixedWidth(90)
        self.year_spin.valueChanged.connect(self._on_year_month_changed)
        layout.addWidget(self.year_spin)

        layout.addWidget(QLabel("月:"))
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(self._current_month)
        self.month_spin.setFixedWidth(90)
        self.month_spin.valueChanged.connect(self._on_year_month_changed)
        layout.addWidget(self.month_spin)

        return widget

    def _build_tabs(self) -> None:
        """4つのメインタブを構築する。"""
        # タブ1: マスタ管理
        from ui.master.employee_tab import EmployeeTab
        from ui.master.shift_tab import ShiftTab
        from ui.master.history_import import HistoryImportTab

        master_tab = QTabWidget()
        master_tab.addTab(EmployeeTab(self), "職員マスタ")
        master_tab.addTab(ShiftTab(self), "シフト種別")
        master_tab.addTab(HistoryImportTab(self), "履歴インポート")
        self.tab_widget.addTab(master_tab, "マスタ管理")

        # タブ2: 希望シフト入力
        from ui.request_view import RequestView
        self.request_view = RequestView(self)
        self.tab_widget.addTab(self.request_view, "希望シフト入力")

        # タブ3: 自動作成実行
        from ui.run_view import RunView
        self.run_view = RunView(self)
        self.tab_widget.addTab(self.run_view, "自動作成実行")

        # タブ4: シフト確認・調整・出力
        result_tab = QTabWidget()
        from ui.result.monthly_grid import MonthlyGrid
        from ui.result.han_view import HanView
        from ui.result.history_view import HistoryView

        self.monthly_grid = MonthlyGrid(self)
        self.han_view = HanView(self)
        self.history_view = HistoryView(self)

        result_tab.addTab(self.monthly_grid, "月次シフト表")
        result_tab.addTab(self.han_view, "班別配当表")
        result_tab.addTab(self.history_view, "修正履歴")
        self.tab_widget.addTab(result_tab, "シフト確認・調整")

    def _on_year_month_changed(self) -> None:
        """年月が変更されたときの処理。"""
        self._current_year = self.year_spin.value()
        self._current_month = self.month_spin.value()
        self.log(f"対象月変更: {self._current_year}年{self._current_month}月")
        # 各ビューに通知
        if hasattr(self, "request_view"):
            self.request_view.set_year_month(self._current_year, self._current_month)
        if hasattr(self, "run_view"):
            self.run_view.set_year_month(self._current_year, self._current_month)
        if hasattr(self, "monthly_grid"):
            self.monthly_grid.set_year_month(self._current_year, self._current_month)
        if hasattr(self, "han_view"):
            self.han_view.set_year_month(self._current_year, self._current_month)
        if hasattr(self, "history_view"):
            self.history_view.set_year_month(self._current_year, self._current_month)

    def get_year_month(self) -> tuple[int, int]:
        """現在選択中の年月を返す。"""
        return self._current_year, self._current_month

    def log(self, message: str) -> None:
        """ログエリアにメッセージを追加する。"""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{ts}] {message}")
        logger.info(message)
