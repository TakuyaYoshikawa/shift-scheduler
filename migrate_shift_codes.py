# -*- coding: utf-8 -*-
"""DBの既存シフトコードを新表記に一括変換するマイグレーションスクリプト。"""
import sys
sys.path.insert(0, ".")
from core.db import get_conn

MIGRATIONS = [
    ("B1", "B"),
    ("C1", "C"),
    ("C2", "\u24b8"),   # Ⓒ (正規)
    ("\u24c2", "\u24b8"),  # Ⓜ→Ⓒ 誤変換修正
    ("B2", "\u24b7"),   # Ⓑ
]

tables_cols = [
    ("shift_master",    "shift_code"),
    ("shift_result",    "shift_code"),
    ("shift_history",   "shift_code"),
    ("shift_submitted", "request"),
]

with get_conn() as conn:
    for old, new in MIGRATIONS:
        for table, col in tables_cols:
            cur = conn.execute(
                f"UPDATE {table} SET {col}=? WHERE {col}=?", (new, old)
            )
            if cur.rowcount:
                sys.stdout.buffer.write(
                    f"  {table}.{col}: {old} -> {new}  ({cur.rowcount})\n".encode("utf-8")
                )
        conn.execute(
            "UPDATE shift_master SET shift_namecode=REPLACE(shift_namecode,?,?)"
            " WHERE shift_namecode LIKE ?",
            (old, new, f"%{old}%"),
        )

print("migration done")
