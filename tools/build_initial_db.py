# -*- coding: utf-8 -*-
"""
tools/build_initial_db.py

マスタデータ（職員・シフト種別・担当可能シフト・制約）のみを含む
初期データベースを assets/initial.db として生成する。

シフト結果・希望シフト・履歴データは含まない（配布用クリーンDB）。

使い方:
    python tools/build_initial_db.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT = PROJECT_ROOT / "assets" / "initial.db"


def main() -> None:
    # 一時ディレクトリに初期DBを生成
    # get_db_path() は LOCALAPPDATA/ShiftScheduler/shift_scheduler.db を返すため
    # LOCALAPPDATA を一時ディレクトリに向ける
    tmp_dir = Path(tempfile.mkdtemp())
    os.environ["LOCALAPPDATA"] = str(tmp_dir)
    tmp_db = tmp_dir / "ShiftScheduler" / "shift_scheduler.db"

    from core import db
    from utils.excel_import import (
        seed_shift_master,
        seed_employee_master,
        seed_employee_constraints,
    )

    db.init_db()
    seed_shift_master()
    seed_employee_master()
    seed_employee_constraints()

    # assets/ にコピー
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp_db, OUTPUT)

    print(f"初期DB生成完了: {OUTPUT}")
    print(f"  サイズ: {OUTPUT.stat().st_size:,} bytes")

    # テーブル件数を確認
    import sqlite3
    conn = sqlite3.connect(OUTPUT)
    for table in ["shift_master", "employee_master", "employee_shift_capability", "employee_constraints"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} 件")
    conn.close()

    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
