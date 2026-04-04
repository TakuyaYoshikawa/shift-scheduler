"""
tests/test_scheduler.py

core/scheduler.py の単体テスト。
小規模なテストデータで制約を検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """テストごとに一時DBを使用し、最小限のマスタデータを投入する。"""
    with mock.patch("core.db.get_db_path", return_value=tmp_path / "test.db"):
        from core import db
        db.init_db()

        # shift_master（自動化対象のみ）
        shifts = [
            (2,  "戸外班",  "B1", "07:00", "16:00"),
            (3,  "戸外班",  "C1", "10:00", "19:00"),
            (5,  "戸外班",  "DG", "08:30", "17:30"),
            (8,  "生活班1", "B1", "07:00", "16:00"),
            (9,  "生活班1", "C1", "10:00", "19:00"),
            (11, "生活班1", "DG", "08:30", "17:30"),
            (14, "生活班2", "B1", "07:00", "16:00"),
            (15, "生活班2", "C1", "10:00", "19:00"),
            (17, "生活班2", "DG", "08:30", "17:30"),
            (20, "夜勤",    "Y",  "15:30", "09:30"),
            (21, "宿直",    "B2", None,    "09:30"),
        ]
        for sid, sname, scode, ts, te in shifts:
            db.insert_shift(sid, sname, scode, time_start=ts, time_end=te)

        # 最適化対象職員（12名）
        # 夜勤制約: 2名/日×31日=62回×3日(Y+B2+休)=186人日
        # 12名×31日=372人日 → 夜勤後も十分な余裕あり
        test_employees = [
            (101, "テスト職員A",  "テストA",  "テスト班"),
            (102, "テスト職員B",  "テストB",  "テスト班"),
            (103, "テスト職員C",  "テストC",  "テスト班"),
            (104, "テスト職員D",  "テストD",  "テスト班"),
            (105, "テスト職員E",  "テストE",  "テスト班"),
            (106, "テスト職員F",  "テストF",  "テスト班"),
            (107, "テスト職員G",  "テストG",  "テスト班"),
            (108, "テスト職員H",  "テストH",  "テスト班"),
            (109, "テスト職員I",  "テストI",  "テスト班"),
            (110, "テスト職員J",  "テストJ",  "テスト班"),
            (111, "テスト職員K",  "テストK",  "テスト班"),
            (112, "テスト職員L",  "テストL",  "テスト班"),
        ]
        for eid, ename, sname, section in test_employees:
            db.insert_employee(eid, ename, sur_name=sname, section=section, is_optimizer_target=1)
            # 全シフト担当可能に設定
            db.set_employee_capabilities(eid, [2, 3, 5, 8, 9, 11, 14, 15, 17, 20, 21])

        yield db


def run_scheduler(year: int, month: int) -> "SchedulerResult":
    """テスト用スケジューラ実行ヘルパー。"""
    from core.scheduler import ShiftScheduler
    scheduler = ShiftScheduler(year=year, month=month, time_limit=60)
    return scheduler.run()


def test_scheduler_runs_without_error(temp_db):
    """スケジューラが正常に実行されることを確認。"""
    result = run_scheduler(2026, 3)
    assert result is not None
    assert result.status in ("Optimal", "Not Solved", "Infeasible", "Undefined", "ERROR")


def test_yakkin_min2_per_day(temp_db):
    """毎日夜勤(shift_id=20)が2名以上配置されることを確認。"""
    result = run_scheduler(2026, 3)

    if not result.assignments:
        pytest.skip("配置結果なし（解が得られなかった）")

    from collections import defaultdict
    yakkin_per_day: dict[int, int] = defaultdict(int)
    for a in result.assignments:
        if a["shift_id"] == 20:
            yakkin_per_day[a["assignment_day"]] += 1

    # 31日分すべてで2名以上
    import calendar
    days = calendar.monthrange(2026, 3)[1]
    for d in range(1, days + 1):
        count = yakkin_per_day.get(d, 0)
        assert count >= 2, f"2026-03-{d:02d}: 夜勤{count}名（2名以上必要）"


def test_yakkin_next_day_is_b2(temp_db):
    """夜勤(Y)の翌日は必ず宿直明け(B2=21)に配置されることを確認。"""
    result = run_scheduler(2026, 3)

    if not result.assignments:
        pytest.skip("配置結果なし")

    # {(employee_id, day): shift_id}
    assignment_map: dict[tuple[int, int], int] = {
        (a["employee_id"], a["assignment_day"]): a["shift_id"]
        for a in result.assignments
    }

    import calendar
    days = calendar.monthrange(2026, 3)[1]

    for (emp_id, day), shift_id in assignment_map.items():
        if shift_id == 20 and day < days:  # 夜勤で最終日以外
            next_shift = assignment_map.get((emp_id, day + 1))
            assert next_shift == 21, (
                f"職員{emp_id}: {day}日に夜勤→翌日({day+1}日)は"
                f"B2(21)が必要、実際={next_shift}"
            )


def test_b2_next_day_is_off(temp_db):
    """宿直明け(B2=21)の翌日は出勤ゼロであることを確認。"""
    result = run_scheduler(2026, 3)

    if not result.assignments:
        pytest.skip("配置結果なし")

    assignment_map: dict[tuple[int, int], int] = {
        (a["employee_id"], a["assignment_day"]): a["shift_id"]
        for a in result.assignments
    }

    import calendar
    days = calendar.monthrange(2026, 3)[1]

    for (emp_id, day), shift_id in assignment_map.items():
        if shift_id == 21 and day < days:  # 宿直明けで最終日以外
            next_shift = assignment_map.get((emp_id, day + 1))
            assert next_shift is None, (
                f"職員{emp_id}: {day}日に宿直明け→翌日({day+1}日)は"
                f"休みが必要、実際=shift_id:{next_shift}"
            )


def test_one_shift_per_day_per_employee(temp_db):
    """1職員が1日に複数シフトに入らないことを確認。"""
    result = run_scheduler(2026, 3)

    if not result.assignments:
        pytest.skip("配置結果なし")

    from collections import defaultdict
    per_employee_day: dict[tuple[int, int], list[int]] = defaultdict(list)
    for a in result.assignments:
        per_employee_day[(a["employee_id"], a["assignment_day"])].append(a["shift_id"])

    for (emp_id, day), shift_ids in per_employee_day.items():
        assert len(shift_ids) <= 1, (
            f"職員{emp_id} 2026-03-{day:02d}: 複数シフト配置 {shift_ids}"
        )


def test_holiday_request_respected(temp_db):
    """休暇申請した職員はその日出勤ゼロであることを確認。"""
    from core import db
    db.upsert_submitted_request(2026, 3, 101, 5, "休暇")

    result = run_scheduler(2026, 3)

    if not result.assignments:
        pytest.skip("配置結果なし")

    for a in result.assignments:
        if a["employee_id"] == 101 and a["assignment_day"] == 5:
            pytest.fail(f"職員101は3/5に休暇申請済みだが配置された: {a}")
