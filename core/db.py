"""
core/db.py

SQLite接続・スキーマ初期化・全テーブルのCRUD関数を提供するモジュール。
UI層からは直接SQLを書かず、必ずこのモジュールの関数を通じてDBアクセスすること。
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB パス・接続
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    r"""AppData\Local\ShiftScheduler\shift_scheduler.db のパスを返す。"""
    app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ShiftScheduler"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "shift_scheduler.db"


def auto_backup(db_path: Path) -> None:
    """起動時に最新7世代の自動バックアップを作成する。"""
    if not db_path.exists():
        return
    backup_dir = db_path.parent / "backup"
    backup_dir.mkdir(exist_ok=True)
    dst = backup_dir / f"shift_scheduler_{date.today().strftime('%Y%m%d')}.db"
    if not dst.exists():
        shutil.copy2(db_path, dst)
        logger.info("自動バックアップ作成: %s", dst)
    backups = sorted(backup_dir.glob("*.db"))
    for old in backups[:-7]:
        old.unlink()
        logger.info("古いバックアップ削除: %s", old)


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """SQLite接続を返すコンテキストマネージャ。"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# スキーマ初期化
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shift_master (
    shift_id        INTEGER PRIMARY KEY,
    shift_name      TEXT NOT NULL,
    shift_code      TEXT NOT NULL,
    shift_namecode  TEXT,
    time_start      TEXT,
    time_end        TEXT,
    color_hex       TEXT DEFAULT '#FFFFFF'
);

CREATE TABLE IF NOT EXISTS employee_master (
    employee_id     INTEGER PRIMARY KEY,
    employee_name   TEXT NOT NULL,
    sur_name        TEXT,
    section         TEXT,
    group_name      TEXT,
    work_hours      TEXT,
    is_optimizer_target INTEGER DEFAULT 1,
    notes           TEXT,
    is_deleted      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS employee_shift_capability (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employee_master(employee_id),
    shift_id    INTEGER NOT NULL REFERENCES shift_master(shift_id),
    UNIQUE(employee_id, shift_id)
);

CREATE TABLE IF NOT EXISTS employee_constraints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     INTEGER NOT NULL REFERENCES employee_master(employee_id),
    constraint_type TEXT NOT NULL,
    value           TEXT,
    memo            TEXT
);

CREATE TABLE IF NOT EXISTS shift_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    employee_id INTEGER NOT NULL,
    shift_id    INTEGER NOT NULL,
    shift_code  TEXT,
    group_name  TEXT,
    sur_name    TEXT
);

CREATE TABLE IF NOT EXISTS shift_submitted (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employee_master(employee_id),
    day         INTEGER NOT NULL,
    request     TEXT NOT NULL,
    submitted_at TEXT DEFAULT (datetime('now')),
    UNIQUE(year, month, employee_id, day)
);

CREATE TABLE IF NOT EXISTS shift_result (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    assignment_day  INTEGER NOT NULL,
    employee_id     INTEGER NOT NULL,
    shift_id        INTEGER NOT NULL,
    shift_name      TEXT,
    shift_code      TEXT,
    sur_name        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shift_manual (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    assignment_day  INTEGER NOT NULL,
    sub_row         INTEGER NOT NULL,
    column_label    TEXT NOT NULL,
    staff_name      TEXT,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(year, month, assignment_day, sub_row, column_label)
);

CREATE TABLE IF NOT EXISTS shift_result_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    assignment_day  INTEGER NOT NULL,
    employee_id     INTEGER NOT NULL,
    change_type     TEXT NOT NULL,
    before_shift_id INTEGER,
    after_shift_id  INTEGER,
    changed_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT DEFAULT (datetime('now')),
    source_file TEXT,
    record_type TEXT,
    record_count INTEGER
);
"""


def init_db() -> None:
    """スキーマを初期化する。初回起動時に呼ぶ。"""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
        # マイグレーション: is_deleted 列が存在しない場合に追加
        cols = [r[1] for r in conn.execute("PRAGMA table_info(employee_master)").fetchall()]
        if "is_deleted" not in cols:
            conn.execute("ALTER TABLE employee_master ADD COLUMN is_deleted INTEGER DEFAULT 0")
    logger.info("DBスキーマ初期化完了: %s", get_db_path())


def next_employee_id() -> int:
    """employee_master の MAX(employee_id)+1 を返す（論理削除済みも含む）。"""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(employee_id) FROM employee_master").fetchone()
    max_id = row[0] if row and row[0] is not None else 0
    return max_id + 1


# ---------------------------------------------------------------------------
# shift_master CRUD
# ---------------------------------------------------------------------------


def get_all_shifts() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM shift_master ORDER BY shift_id").fetchall()
    return [dict(r) for r in rows]


def get_shift(shift_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM shift_master WHERE shift_id=?", (shift_id,)
        ).fetchone()
    return dict(row) if row else None


def insert_shift(
    shift_id: int,
    shift_name: str,
    shift_code: str,
    shift_namecode: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    color_hex: str = "#FFFFFF",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO shift_master
               (shift_id, shift_name, shift_code, shift_namecode, time_start, time_end, color_hex)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (shift_id, shift_name, shift_code, shift_namecode, time_start, time_end, color_hex),
        )


def update_shift(shift_id: int, **kwargs: Any) -> None:
    allowed = {"shift_name", "shift_code", "shift_namecode", "time_start", "time_end", "color_hex"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE shift_master SET {set_clause} WHERE shift_id=?",
            (*fields.values(), shift_id),
        )


def delete_shift(shift_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM shift_master WHERE shift_id=?", (shift_id,))


# ---------------------------------------------------------------------------
# employee_master CRUD
# ---------------------------------------------------------------------------


def get_all_employees(include_deleted: bool = False) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if include_deleted:
            rows = conn.execute(
                "SELECT * FROM employee_master ORDER BY employee_id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM employee_master WHERE is_deleted=0 ORDER BY employee_id"
            ).fetchall()
    return [dict(r) for r in rows]


def get_employee(employee_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM employee_master WHERE employee_id=? AND is_deleted=0", (employee_id,)
        ).fetchone()
    return dict(row) if row else None


def get_optimizer_target_employees() -> list[dict[str, Any]]:
    """最適化対象の職員一覧を返す（論理削除済みは除外）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM employee_master WHERE is_optimizer_target=1 AND is_deleted=0 ORDER BY employee_id"
        ).fetchall()
    return [dict(r) for r in rows]


def insert_employee(
    employee_id: int,
    employee_name: str,
    sur_name: str | None = None,
    section: str | None = None,
    group_name: str | None = None,
    work_hours: str | None = None,
    is_optimizer_target: int = 1,
    notes: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO employee_master
               (employee_id, employee_name, sur_name, section, group_name,
                work_hours, is_optimizer_target, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (employee_id, employee_name, sur_name, section, group_name,
             work_hours, is_optimizer_target, notes),
        )


def update_employee(employee_id: int, **kwargs: Any) -> None:
    allowed = {
        "employee_name", "sur_name", "section", "group_name",
        "work_hours", "is_optimizer_target", "notes",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE employee_master SET {set_clause} WHERE employee_id=?",
            (*fields.values(), employee_id),
        )


def delete_employee(employee_id: int) -> None:
    """論理削除（is_deleted=1 に設定。IDは保持してデータも残す）。"""
    with get_conn() as conn:
        conn.execute("UPDATE employee_master SET is_deleted=1 WHERE employee_id=?", (employee_id,))


# ---------------------------------------------------------------------------
# employee_shift_capability CRUD
# ---------------------------------------------------------------------------


def get_employee_capabilities(employee_id: int) -> list[int]:
    """職員が担当可能なshift_idリストを返す。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT shift_id FROM employee_shift_capability WHERE employee_id=?",
            (employee_id,),
        ).fetchall()
    return [r["shift_id"] for r in rows]


def set_employee_capabilities(employee_id: int, shift_ids: list[int]) -> None:
    """職員の担当可能シフトを上書き設定する。"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM employee_shift_capability WHERE employee_id=?", (employee_id,)
        )
        for sid in shift_ids:
            conn.execute(
                "INSERT OR IGNORE INTO employee_shift_capability (employee_id, shift_id) VALUES (?, ?)",
                (employee_id, sid),
            )


def add_employee_capability(employee_id: int, shift_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO employee_shift_capability (employee_id, shift_id) VALUES (?, ?)",
            (employee_id, shift_id),
        )


def remove_employee_capability(employee_id: int, shift_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM employee_shift_capability WHERE employee_id=? AND shift_id=?",
            (employee_id, shift_id),
        )


# ---------------------------------------------------------------------------
# employee_constraints CRUD
# ---------------------------------------------------------------------------


def get_employee_constraints(employee_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM employee_constraints WHERE employee_id=? ORDER BY id",
            (employee_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_constraints() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM employee_constraints ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_constraint(
    employee_id: int, constraint_type: str, value: str | None = None, memo: str | None = None
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO employee_constraints (employee_id, constraint_type, value, memo)
               VALUES (?, ?, ?, ?)""",
            (employee_id, constraint_type, value, memo),
        )
        return cur.lastrowid  # type: ignore[return-value]


def delete_constraint(constraint_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM employee_constraints WHERE id=?", (constraint_id,))


def delete_employee_constraints(employee_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM employee_constraints WHERE employee_id=?", (employee_id,))


# ---------------------------------------------------------------------------
# shift_history CRUD
# ---------------------------------------------------------------------------


def get_shift_history(year: int, month: int) -> list[dict[str, Any]]:
    date_prefix = f"{year}-{month:02d}"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM shift_history WHERE date LIKE ? ORDER BY date, employee_id",
            (f"{date_prefix}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_shift_history(
    date_str: str,
    employee_id: int,
    shift_id: int,
    shift_code: str | None = None,
    group_name: str | None = None,
    sur_name: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO shift_history (date, employee_id, shift_id, shift_code, group_name, sur_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date_str, employee_id, shift_id, shift_code, group_name, sur_name),
        )


def bulk_insert_shift_history(records: list[dict[str, Any]]) -> None:
    """shift_history を一括挿入する。"""
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO shift_history (date, employee_id, shift_id, shift_code, group_name, sur_name)
               VALUES (:date, :employee_id, :shift_id, :shift_code, :group_name, :sur_name)""",
            records,
        )


# ---------------------------------------------------------------------------
# shift_submitted CRUD
# ---------------------------------------------------------------------------


def get_submitted_requests(year: int, month: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM shift_submitted WHERE year=? AND month=?
               ORDER BY employee_id, day""",
            (year, month),
        ).fetchall()
    return [dict(r) for r in rows]


def get_submitted_request(year: int, month: int, employee_id: int, day: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM shift_submitted
               WHERE year=? AND month=? AND employee_id=? AND day=?""",
            (year, month, employee_id, day),
        ).fetchone()
    return dict(row) if row else None


def upsert_submitted_request(
    year: int, month: int, employee_id: int, day: int, request: str
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO shift_submitted (year, month, employee_id, day, request)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(year, month, employee_id, day)
               DO UPDATE SET request=excluded.request, submitted_at=datetime('now')""",
            (year, month, employee_id, day, request),
        )


def delete_submitted_request(year: int, month: int, employee_id: int, day: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """DELETE FROM shift_submitted WHERE year=? AND month=? AND employee_id=? AND day=?""",
            (year, month, employee_id, day),
        )


def clear_submitted_requests(year: int, month: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM shift_submitted WHERE year=? AND month=?", (year, month)
        )


# ---------------------------------------------------------------------------
# shift_result CRUD
# ---------------------------------------------------------------------------


def get_shift_results(year: int, month: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM shift_result WHERE year=? AND month=?
               ORDER BY assignment_day, employee_id""",
            (year, month),
        ).fetchall()
    return [dict(r) for r in rows]


def get_shift_result_for_day(year: int, month: int, day: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM shift_result WHERE year=? AND month=? AND assignment_day=?
               ORDER BY employee_id""",
            (year, month, day),
        ).fetchall()
    return [dict(r) for r in rows]


def get_shift_result_for_employee_day(
    year: int, month: int, employee_id: int, day: int
) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM shift_result
               WHERE year=? AND month=? AND employee_id=? AND assignment_day=?""",
            (year, month, employee_id, day),
        ).fetchone()
    return dict(row) if row else None


def insert_shift_result(
    year: int,
    month: int,
    assignment_day: int,
    employee_id: int,
    shift_id: int,
    shift_name: str | None = None,
    shift_code: str | None = None,
    sur_name: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO shift_result
               (year, month, assignment_day, employee_id, shift_id, shift_name, shift_code, sur_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (year, month, assignment_day, employee_id, shift_id, shift_name, shift_code, sur_name),
        )


def bulk_insert_shift_results(records: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO shift_result
               (year, month, assignment_day, employee_id, shift_id, shift_name, shift_code, sur_name)
               VALUES (:year, :month, :assignment_day, :employee_id, :shift_id,
                       :shift_name, :shift_code, :sur_name)""",
            records,
        )


def update_shift_result(
    year: int, month: int, employee_id: int, assignment_day: int, shift_id: int
) -> None:
    with get_conn() as conn:
        sm = conn.execute(
            "SELECT shift_name, shift_code FROM shift_master WHERE shift_id=?", (shift_id,)
        ).fetchone()
        em = conn.execute(
            "SELECT sur_name FROM employee_master WHERE employee_id=?", (employee_id,)
        ).fetchone()
        conn.execute(
            """INSERT INTO shift_result
               (year, month, assignment_day, employee_id, shift_id, shift_name, shift_code, sur_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (
                year, month, assignment_day, employee_id, shift_id,
                sm["shift_name"] if sm else None,
                sm["shift_code"] if sm else None,
                em["sur_name"] if em else None,
            ),
        )
        conn.execute(
            """UPDATE shift_result SET shift_id=?, shift_name=?, shift_code=?, sur_name=?
               WHERE year=? AND month=? AND assignment_day=? AND employee_id=?""",
            (
                shift_id,
                sm["shift_name"] if sm else None,
                sm["shift_code"] if sm else None,
                em["sur_name"] if em else None,
                year, month, assignment_day, employee_id,
            ),
        )


def delete_shift_result_for_employee_day(
    year: int, month: int, employee_id: int, assignment_day: int
) -> None:
    with get_conn() as conn:
        conn.execute(
            """DELETE FROM shift_result
               WHERE year=? AND month=? AND employee_id=? AND assignment_day=?""",
            (year, month, employee_id, assignment_day),
        )


def clear_shift_results(year: int, month: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM shift_result WHERE year=? AND month=?", (year, month)
        )


# ---------------------------------------------------------------------------
# shift_manual CRUD
# ---------------------------------------------------------------------------


def get_manual_shifts(year: int, month: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM shift_manual WHERE year=? AND month=?
               ORDER BY assignment_day, sub_row, column_label""",
            (year, month),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_manual_shift(
    year: int,
    month: int,
    assignment_day: int,
    sub_row: int,
    column_label: str,
    staff_name: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO shift_manual
               (year, month, assignment_day, sub_row, column_label, staff_name)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(year, month, assignment_day, sub_row, column_label)
               DO UPDATE SET staff_name=excluded.staff_name, updated_at=datetime('now')""",
            (year, month, assignment_day, sub_row, column_label, staff_name),
        )


# ---------------------------------------------------------------------------
# shift_result_log CRUD
# ---------------------------------------------------------------------------


def add_result_log(
    year: int,
    month: int,
    assignment_day: int,
    employee_id: int,
    change_type: str,
    before_shift_id: int | None,
    after_shift_id: int | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO shift_result_log
               (year, month, assignment_day, employee_id, change_type, before_shift_id, after_shift_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (year, month, assignment_day, employee_id, change_type, before_shift_id, after_shift_id),
        )


def get_result_logs(year: int, month: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT l.*, e.employee_name,
                      b.shift_code AS before_code, a.shift_code AS after_code
               FROM shift_result_log l
               LEFT JOIN employee_master e ON l.employee_id=e.employee_id
               LEFT JOIN shift_master b ON l.before_shift_id=b.shift_id
               LEFT JOIN shift_master a ON l.after_shift_id=a.shift_id
               WHERE l.year=? AND l.month=?
               ORDER BY l.changed_at DESC""",
            (year, month),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# import_log CRUD
# ---------------------------------------------------------------------------


def add_import_log(source_file: str, record_type: str, record_count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO import_log (source_file, record_type, record_count)
               VALUES (?, ?, ?)""",
            (source_file, record_type, record_count),
        )


def get_import_logs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM import_log ORDER BY imported_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
