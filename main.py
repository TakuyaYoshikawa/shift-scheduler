"""
main.py

シフト自動作成システムのエントリポイント。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ログ設定
def setup_logging() -> None:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("シフト自動作成システム 起動")

    # DB 初期化・自動バックアップ
    from core import db
    db.init_db()
    db_path = db.get_db_path()
    db.auto_backup(db_path)
    logger.info("DB初期化完了: %s", db_path)

    # PyQt6 アプリ起動
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("シフト自動作成システム")
    app.setOrganizationName("ShiftScheduler")

    # High DPI サポート
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    logger.info("メインウィンドウ表示完了")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
