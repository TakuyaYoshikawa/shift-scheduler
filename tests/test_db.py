"""
tests/test_db.py

core/db.py の単体テスト。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

# テスト用に DB パスを一時ディレクトリに向ける
@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """テストごとに一時DBを使用する。"""
    with mock.patch("core.db.get_db_path", return_value=tmp_path / "test.db"):
        from core import db
        db.init_db()
        yield db


def test_shift_master_crud(temp_db):
    db = temp_db
    db.insert_shift(1, "夜勤", "Y", time_start="15:30", time_end="09:30", color_hex="#D4A0D4")
    shifts = db.get_all_shifts()
    assert len(shifts) == 1
    assert shifts[0]["shift_code"] == "Y"

    db.update_shift(1, color_hex="#FFFFFF")
    s = db.get_shift(1)
    assert s["color_hex"] == "#FFFFFF"

    db.delete_shift(1)
    assert db.get_all_shifts() == []


def test_employee_master_crud(temp_db):
    db = temp_db
    db.insert_shift(20, "夜勤", "Y")
    db.insert_employee(10, "涛川 紀之", sur_name="涛川", section="本体男性支援員")
    emps = db.get_all_employees()
    assert any(e["employee_name"] == "涛川 紀之" for e in emps)

    db.update_employee(10, notes="テスト更新")
    emp = db.get_employee(10)
    assert emp["notes"] == "テスト更新"

    db.delete_employee(10)
    assert db.get_employee(10) is None


def test_employee_capabilities(temp_db):
    db = temp_db
    db.insert_shift(20, "夜勤", "Y")
    db.insert_shift(2, "戸外班", "B1")
    db.insert_employee(10, "涛川 紀之", sur_name="涛川")

    db.set_employee_capabilities(10, [2, 20])
    caps = db.get_employee_capabilities(10)
    assert set(caps) == {2, 20}

    db.remove_employee_capability(10, 20)
    caps = db.get_employee_capabilities(10)
    assert caps == [2]


def test_shift_submitted_upsert(temp_db):
    db = temp_db
    db.insert_employee(10, "涛川 紀之", sur_name="涛川")
    db.upsert_submitted_request(2026, 3, 10, 1, "Y")
    req = db.get_submitted_request(2026, 3, 10, 1)
    assert req["request"] == "Y"

    db.upsert_submitted_request(2026, 3, 10, 1, "B1")
    req = db.get_submitted_request(2026, 3, 10, 1)
    assert req["request"] == "B1"

    db.delete_submitted_request(2026, 3, 10, 1)
    assert db.get_submitted_request(2026, 3, 10, 1) is None


def test_shift_result_crud(temp_db):
    db = temp_db
    db.insert_shift(20, "夜勤", "Y")
    db.insert_employee(10, "涛川 紀之", sur_name="涛川")

    db.insert_shift_result(2026, 3, 1, 10, 20, "夜勤", "Y", "涛川")
    results = db.get_shift_results(2026, 3)
    assert len(results) == 1
    assert results[0]["shift_code"] == "Y"

    db.clear_shift_results(2026, 3)
    assert db.get_shift_results(2026, 3) == []


def test_constraints_crud(temp_db):
    db = temp_db
    db.insert_employee(13, "髙井 善崇", sur_name="髙井")
    db.insert_employee(20, "小幡 征志", sur_name="小幡")

    cid = db.add_constraint(13, "no_paired_with", "20", "小幡と同日禁止")
    constraints = db.get_employee_constraints(13)
    assert len(constraints) == 1
    assert constraints[0]["value"] == "20"

    db.delete_constraint(cid)
    assert db.get_employee_constraints(13) == []
