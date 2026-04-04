"""
core/constraints.py

employee_constraints テーブルからハード制約リストを動的生成するモジュール。
PuLP の制約オブジェクトは生成せず、Pythonのデータ構造として返す。
scheduler.py と adjust_panel.py の両方から利用する。
"""

from __future__ import annotations

import logging
from typing import Any

from core import db

logger = logging.getLogger(__name__)


def get_no_pair_constraints() -> list[tuple[int, int]]:
    """
    同日勤務禁止ペアのリストを返す。
    employee_constraints の constraint_type='no_paired_with' から動的生成する。
    戻り値: [(emp_id_a, emp_id_b), ...] （重複なし、id小≦id大の順）
    """
    constraints = db.get_all_constraints()
    pairs: set[tuple[int, int]] = set()
    for c in constraints:
        if c["constraint_type"] == "no_paired_with":
            try:
                emp_a = c["employee_id"]
                emp_b = int(c["value"])
                pair = (min(emp_a, emp_b), max(emp_a, emp_b))
                pairs.add(pair)
            except (TypeError, ValueError):
                logger.warning("no_paired_with の value が不正: %s", c)
    return list(pairs)


def get_weekday_only_employees() -> list[int]:
    """平日のみ出勤（土日祝休み）の職員IDリストを返す。"""
    constraints = db.get_all_constraints()
    return [
        c["employee_id"]
        for c in constraints
        if c["constraint_type"] == "weekday_only"
    ]


def get_fixed_shift_employees() -> list[dict[str, Any]]:
    """
    固定シフト職員のリストを返す。
    戻り値: [{"employee_id": int, "shift_code": str}, ...]
    """
    constraints = db.get_all_constraints()
    return [
        {"employee_id": c["employee_id"], "shift_code": c["value"]}
        for c in constraints
        if c["constraint_type"] == "fixed_shift"
    ]


def check_constraints_for_change(
    year: int,
    month: int,
    employee_id: int,
    day: int,
    new_shift_id: int | None,
) -> list[dict[str, Any]]:
    """
    手動変更前の制約チェック（PuLPを使わず軽量検証）。
    戻り値: チェック結果リスト [{"label": str, "ok": bool, "message": str}, ...]
    """
    results: list[dict[str, Any]] = []
    days_in_month = _days_in_month(year, month)

    # 1) 1日1勤務チェック
    existing = db.get_shift_result_for_employee_day(year, month, employee_id, day)
    if existing and new_shift_id is not None and existing["shift_id"] == new_shift_id:
        results.append({
            "label": "1日1勤務",
            "ok": True,
            "message": "同一シフトへの変更（変更なし）",
        })
    else:
        results.append({
            "label": "1日1勤務",
            "ok": True,
            "message": "当日の既存シフトは上書きされます",
        })

    # 2) 担当可能シフトチェック
    if new_shift_id is not None:
        capable_ids = db.get_employee_capabilities(employee_id)
        ok = new_shift_id in capable_ids or new_shift_id in (20, 21)
        results.append({
            "label": "担当可能シフト",
            "ok": ok,
            "message": "担当可能" if ok else f"shift_id={new_shift_id} は担当可能シフト外",
        })

    # 3) Y翌日B2強制
    if new_shift_id == 20 and day < days_in_month:
        results.append({
            "label": "Y翌日B2設定",
            "ok": True,
            "message": f"翌日({day+1}日)に宿直明け(B2)が自動設定されます",
        })

    # 4) 月間出勤数
    all_results = db.get_shift_results(year, month)
    current_count = sum(
        1 for r in all_results if r["employee_id"] == employee_id
    )
    projected = current_count if existing else current_count + 1
    ok = projected <= 23
    results.append({
        "label": "月間出勤数",
        "ok": ok,
        "message": f"{current_count}日 → {projected}日（上限23日{'以内' if ok else '超過！'}）",
    })

    # 5) 夜勤配置人数（変更後に2名以上を維持）
    if new_shift_id == 20:
        day_results = db.get_shift_result_for_day(year, month, day)
        yakkin_count = sum(1 for r in day_results if r["shift_id"] == 20)
        if not existing or existing.get("shift_id") != 20:
            yakkin_count += 1
        ok = yakkin_count >= 2
        results.append({
            "label": "夜勤配置人数",
            "ok": True,
            "message": f"変更後の夜勤配置: {yakkin_count}名（{'OK' if ok else '2名未満の可能性あり'}）",
        })

    # 6) 同日禁止ペアチェック
    no_pairs = get_no_pair_constraints()
    paired_ids = [b for (a, b) in no_pairs if a == employee_id] + \
                 [a for (a, b) in no_pairs if b == employee_id]
    if paired_ids and new_shift_id is not None:
        day_results = db.get_shift_result_for_day(year, month, day)
        working_ids = {r["employee_id"] for r in day_results}
        conflicts = [pid for pid in paired_ids if pid in working_ids]
        ok = len(conflicts) == 0
        if not ok:
            conflict_names = []
            for pid in conflicts:
                emp = db.get_employee(pid)
                conflict_names.append(emp["employee_name"] if emp else str(pid))
            results.append({
                "label": "同日禁止ペア",
                "ok": False,
                "message": f"同日勤務禁止の職員が出勤中: {', '.join(conflict_names)}",
            })
        else:
            results.append({
                "label": "同日禁止ペア",
                "ok": True,
                "message": "禁止ペアとの重複なし",
            })

    return results


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]
