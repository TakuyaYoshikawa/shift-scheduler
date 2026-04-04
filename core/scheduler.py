"""
core/scheduler.py

PuLP による自動シフトスケジューリングエンジン。
CLAUDE.md の「最適化エンジン仕様」に従って実装。

使い方:
    python -m core.scheduler --year 2026 --month 3
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ペナルティ・重みの定数
PENALTY_UNFULFILLED_REQUEST = 2000
WEIGHT_FAIRNESS = 10
PENALTY_YAKKIN_INTERVAL = 300
PENALTY_B2_翌日出勤 = 500
PENALTY_YAKKIN_OVER_MAIN = 400    # 夜勤メイン職員5回超
PENALTY_YAKKIN_OVER_STD = 200     # 夜勤標準職員4回超
SCORE_REQUEST_MATCH = 1000
SCORE_INITIAL = -50


class SchedulerResult:
    """最適化結果を格納するクラス。"""

    def __init__(
        self,
        status: str,
        is_optimal: bool,
        assignments: list[dict],
        message: str = "",
    ):
        self.status = status
        self.is_optimal = is_optimal
        self.assignments = assignments  # [{year, month, assignment_day, employee_id, shift_id, ...}]
        self.message = message


class ShiftScheduler:
    """
    PuLP を用いたシフト最適化エンジン。

    Parameters
    ----------
    year, month : int
        スケジューリング対象年月。
    progress_callback : Callable[[str], None] | None
        進捗メッセージのコールバック（UI のログ表示に使用）。
    time_limit : int
        CBC ソルバーのタイムアウト秒数（デフォルト120秒）。
    """

    def __init__(
        self,
        year: int,
        month: int,
        progress_callback: Callable[[str], None] | None = None,
        time_limit: int = 120,
    ):
        self.year = year
        self.month = month
        self.progress_callback = progress_callback or (lambda msg: logger.info(msg))
        self.time_limit = time_limit

    def _log(self, msg: str) -> None:
        self.progress_callback(msg)
        logger.info(msg)

    def run(self) -> SchedulerResult:
        """スケジューリングを実行する。"""
        try:
            import pulp
        except ImportError:
            msg = "PuLPがインストールされていません: pip install pulp"
            self._log(msg)
            return SchedulerResult("ERROR", False, [], msg)

        import pandas as pd
        from core import db
        from core.constraints import get_no_pair_constraints
        from core.history_mapper import build_history_scores, build_yakkin_pair_bonus

        try:
            import holidays as holidays_lib
            jp_holidays = holidays_lib.Japan(years=[self.year])
        except ImportError:
            jp_holidays = {}

        self._log(f"最適化開始 ({self.year}年{self.month}月)")

        # ------------------------------------------------------------------
        # データ取得
        # ------------------------------------------------------------------
        self._log("データ取得中...")

        shifts = db.get_all_shifts()
        # list_shift は shift_id <= 21 のみ
        list_shift = [s["shift_id"] for s in shifts if s["shift_id"] <= 21]
        shift_map = {s["shift_id"]: s for s in shifts}

        employees = db.get_optimizer_target_employees()
        list_employee = [e["employee_id"] for e in employees]
        emp_map = {e["employee_id"]: e for e in employees}

        days_in_month = calendar.monthrange(self.year, self.month)[1]
        list_day = list(range(1, days_in_month + 1))

        self._log(f"対象: {len(list_employee)}名 × {days_in_month}日 × {len(list_shift)}シフト")

        # 職員ごとの担当可能シフト
        capabilities: dict[int, set[int]] = {}
        for emp_id in list_employee:
            cap_ids = db.get_employee_capabilities(emp_id)
            capabilities[emp_id] = set(cap_ids)

        # 希望シフト
        submitted = db.get_submitted_requests(self.year, self.month)
        # {(employee_id, day): request_code}
        requests: dict[tuple[int, int], str] = {
            (r["employee_id"], r["day"]): r["request"] for r in submitted
        }

        # shift_code → shift_id リスト（対象シフトのみ）
        code_to_ids: dict[str, list[int]] = {}
        for s in shifts:
            if s["shift_id"] <= 21:
                code = s["shift_code"]
                code_to_ids.setdefault(code, []).append(s["shift_id"])

        # 実績スコア
        self._log("実績データ処理中...")
        hist_score_df = build_history_scores(self.year, self.month, list_employee, list_shift)

        # 夜勤ペアボーナス
        yakkin_pair_bonus = build_yakkin_pair_bonus(self.year, self.month)

        # 同日禁止ペア
        no_pair_constraints = get_no_pair_constraints()

        # 祝日リスト
        holiday_dates = {
            d for d in [date(self.year, self.month, day) for day in list_day]
            if d in jp_holidays
        }
        holiday_days = {d.day for d in holiday_dates}

        self._log("スコア構築完了")

        # ------------------------------------------------------------------
        # PuLP 問題定義
        # ------------------------------------------------------------------
        problem = pulp.LpProblem(f"ShiftSchedule_{self.year}_{self.month}", pulp.LpMaximize)

        # 決定変数: shift[d][e][s] ∈ {0, 1}
        self._log("決定変数定義中...")
        shift: dict[int, dict[int, dict[int, pulp.LpVariable]]] = {}
        for d in list_day:
            shift[d] = {}
            for e in list_employee:
                shift[d][e] = {}
                for s in list_shift:
                    shift[d][e][s] = pulp.LpVariable(
                        f"x_{d}_{e}_{s}", cat="Binary"
                    )

        # 希望未充足スラック変数
        slack: dict[tuple[int, int], pulp.LpVariable] = {}
        request_work_index: list[tuple[int, int, str]] = []
        for (emp_id, day), req_code in requests.items():
            if req_code != "休暇" and emp_id in list_employee and day in list_day:
                if req_code in code_to_ids:
                    request_work_index.append((day, emp_id, req_code))
                    if (emp_id, day) not in slack:
                        slack[(emp_id, day)] = pulp.LpVariable(
                            f"slack_{emp_id}_{day}", cat="Binary"
                        )

        # 公平性補助変数
        max_workdays = pulp.LpVariable("max_workdays", lowBound=0)
        min_workdays = pulp.LpVariable("min_workdays", lowBound=0)
        workdays: dict[int, pulp.LpAffineExpression] = {}
        for e in list_employee:
            workdays[e] = pulp.lpSum(shift[d][e][s] for d in list_day for s in list_shift)

        # 夜勤インターバルペナルティ変数
        too_close_vars: list[pulp.LpVariable] = []

        # ------------------------------------------------------------------
        # ハード制約
        # ------------------------------------------------------------------
        self._log("制約構築中...")

        # H1: 1日1勤務
        for d in list_day:
            for e in list_employee:
                problem += pulp.lpSum(shift[d][e][s] for s in list_shift) <= 1, \
                    f"h1_one_shift_{d}_{e}"

        # H2: 1シフト上限3名
        for d in list_day:
            for s in list_shift:
                problem += pulp.lpSum(shift[d][e][s] for e in list_employee) <= 3, \
                    f"h2_max3_{d}_{s}"

        # H3: 夜勤(shift_id=20)毎日2名以上
        for d in list_day:
            problem += pulp.lpSum(shift[d][e][20] for e in list_employee) >= 2, \
                f"h3_yakkin_min2_{d}"

        # H4: 夜勤翌日は宿直明け(B2=21)に強制
        for d in list_day[:-1]:  # 最終日は対象外
            for e in list_employee:
                problem += shift[d + 1][e][21] >= shift[d][e][20], \
                    f"h4_yakkin_next_{d}_{e}"

        # H5: 宿直明け(B2=21)翌日は休み
        for d in list_day[:-1]:
            for e in list_employee:
                problem += (
                    pulp.lpSum(shift[d + 1][e][s] for s in list_shift)
                    <= 1 - shift[d][e][21]
                ), f"h5_b2_next_{d}_{e}"

        # H6: 休暇申請者は出勤ゼロ
        for (emp_id, day), req_code in requests.items():
            if req_code == "休暇" and emp_id in list_employee and day in list_day:
                problem += (
                    pulp.lpSum(shift[day][emp_id][s] for s in list_shift) == 0
                ), f"h6_holiday_{emp_id}_{day}"

        # H7: 担当可能パターン制限（Y/B2は全員に開放）
        for d in list_day:
            for e in list_employee:
                for s in list_shift:
                    if s in (20, 21):
                        continue  # 夜勤・宿直は全員に開放
                    if s not in capabilities[e]:
                        # 希望申請済みの場合も制限しない
                        req_code = requests.get((e, d))
                        if req_code and req_code != "休暇":
                            req_shift_ids = code_to_ids.get(req_code, [])
                            if s in req_shift_ids:
                                continue
                        problem += shift[d][e][s] == 0, f"h7_cap_{d}_{e}_{s}"

        # H8: 同日禁止ペア
        for d in list_day:
            for (emp_a, emp_b) in no_pair_constraints:
                if emp_a in list_employee and emp_b in list_employee:
                    problem += (
                        pulp.lpSum(shift[d][emp_a][s] for s in list_shift)
                        + pulp.lpSum(shift[d][emp_b][s] for s in list_shift)
                        <= 1
                    ), f"h8_nopair_{d}_{emp_a}_{emp_b}"

        # ソフト制約: 希望シフト充足
        for (day, emp_id, req_code) in request_work_index:
            deploy_ids = [sid for sid in code_to_ids.get(req_code, []) if sid in list_shift]
            if not deploy_ids:
                continue
            problem += (
                pulp.lpSum(shift[day][emp_id][sid] for sid in deploy_ids)
                + slack[(emp_id, day)] >= 1
            ), f"soft_req_{emp_id}_{day}"

        # 公平性: workdays の最大・最小
        for e in list_employee:
            problem += max_workdays >= workdays[e], f"fair_max_{e}"
            problem += min_workdays <= workdays[e], f"fair_min_{e}"

        # 夜勤インターバルペナルティ（ソフト）
        for e in list_employee:
            for i, d1 in enumerate(list_day):
                for d2 in list_day[i + 1:]:
                    if d2 - d1 < 5:
                        var = pulp.LpVariable(f"tc_{e}_{d1}_{d2}", cat="Binary")
                        problem += var >= shift[d1][e][20] + shift[d2][e][20] - 1, \
                            f"tc_c_{e}_{d1}_{d2}"
                        too_close_vars.append(var)
                    else:
                        break  # d2-d1 >= 5 になったら内側ループ終了

        # ------------------------------------------------------------------
        # 目的関数
        # ------------------------------------------------------------------
        self._log("目的関数構築中...")

        # スコア項（疎な形式で構築）
        score_terms = []

        # (1) 希望シフト一致スコア
        for (emp_id, day), req_code in requests.items():
            if req_code == "休暇" or emp_id not in list_employee or day not in list_day:
                continue
            for sid in code_to_ids.get(req_code, []):
                if sid in list_shift:
                    score_terms.append(SCORE_REQUEST_MATCH * shift[day][emp_id][sid])

        # (2) 実績スコア
        if not hist_score_df.empty:
            for _, row in hist_score_df.iterrows():
                d = int(row["day"])
                e = int(row["employee_id"])
                s = int(row["shift_id"])
                sc = int(row["score"])
                if d in list_day and e in list_employee and s in list_shift:
                    score_terms.append(sc * shift[d][e][s])

        # (3) 夜勤ペアボーナス
        for (e1, e2), bonus in yakkin_pair_bonus.items():
            if e1 in list_employee and e2 in list_employee:
                for d in list_day:
                    pair_var = pulp.LpVariable(f"ypair_{d}_{e1}_{e2}", cat="Binary")
                    problem += pair_var <= shift[d][e1][20], f"yp1_{d}_{e1}_{e2}"
                    problem += pair_var <= shift[d][e2][20], f"yp2_{d}_{e1}_{e2}"
                    score_terms.append(bonus * pair_var)

        # (4) 初期値（不要な配置を抑制）
        for d in list_day:
            for e in list_employee:
                for s in list_shift:
                    score_terms.append(SCORE_INITIAL * shift[d][e][s])

        # ペナルティ項
        penalty_terms = []

        # 希望未充足ペナルティ
        for sv in slack.values():
            penalty_terms.append(PENALTY_UNFULFILLED_REQUEST * sv)

        # 夜勤インターバルペナルティ
        for tc_var in too_close_vars:
            penalty_terms.append(PENALTY_YAKKIN_INTERVAL * tc_var)

        # 公平性ペナルティ
        fairness_term = WEIGHT_FAIRNESS * (max_workdays - min_workdays)

        problem += (
            pulp.lpSum(score_terms)
            - pulp.lpSum(penalty_terms)
            - fairness_term
        )

        # ------------------------------------------------------------------
        # ソルバー実行
        # ------------------------------------------------------------------
        self._log("PuLP 最適化実行中...")
        self._log(f"変数数: {len(problem.variables())}, 制約数: {len(problem.constraints)}")

        solver = pulp.PULP_CBC_CMD(timeLimit=self.time_limit, msg=0)
        problem.solve(solver)

        status_str = pulp.LpStatus[problem.status]
        self._log(f"ソルバー終了: Status={status_str}")

        # status: 1=Optimal, 0=Not Solved(時間切れ含む), -1=Infeasible, -2=Unbounded
        if problem.status == -1:
            msg = "実行不可能（制約を満たす解が存在しません）"
            self._log(msg)
            return SchedulerResult(status_str, False, [], msg)

        if problem.status == -2:
            msg = "目的関数が無界です（制約の確認が必要）"
            self._log(msg)
            return SchedulerResult(status_str, False, [], msg)

        is_optimal = problem.status == 1

        # status==0 (Not Solved / 時間切れ) でも変数に値があれば暫定解として採用
        if problem.status == 0:
            # 変数に値があるか確認
            test_val = pulp.value(problem.objective)
            if test_val is None:
                msg = "解が得られませんでした（Not Solved）"
                self._log(msg)
                return SchedulerResult(status_str, False, [], msg)
            self._log("時間切れ: 実行可能解を暫定解として採用")

        # ------------------------------------------------------------------
        # 結果収集
        # ------------------------------------------------------------------
        self._log("結果を収集中...")
        assignments = []
        for d in list_day:
            for e in list_employee:
                for s in list_shift:
                    val = pulp.value(shift[d][e][s])
                    if val is not None and val > 0.5:
                        sm = shift_map.get(s, {})
                        em = emp_map.get(e, {})
                        assignments.append({
                            "year": self.year,
                            "month": self.month,
                            "assignment_day": d,
                            "employee_id": e,
                            "shift_id": s,
                            "shift_name": sm.get("shift_name"),
                            "shift_code": sm.get("shift_code"),
                            "sur_name": em.get("sur_name"),
                        })

        # 結果をDBに保存
        self._log("結果をDBに保存中...")
        db.clear_shift_results(self.year, self.month)
        db.bulk_insert_shift_results(assignments)

        # auto_calc ログ
        for a in assignments:
            db.add_result_log(
                year=self.year,
                month=self.month,
                assignment_day=a["assignment_day"],
                employee_id=a["employee_id"],
                change_type="auto_calc",
                before_shift_id=None,
                after_shift_id=a["shift_id"],
            )

        status_msg = (
            f"最適解が得られました (Status: Optimal, {len(assignments)}件)"
            if is_optimal
            else f"暫定解で採用しました（制限時間超過, {len(assignments)}件）"
        )
        self._log(status_msg)

        return SchedulerResult(status_str, is_optimal, assignments, status_msg)


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="シフト自動作成CLI")
    parser.add_argument("--year",  type=int, required=True, help="対象年")
    parser.add_argument("--month", type=int, required=True, help="対象月")
    parser.add_argument("--time-limit", type=int, default=120, help="ソルバータイムアウト秒")
    args = parser.parse_args()

    from core import db as dbmod
    dbmod.init_db()

    scheduler = ShiftScheduler(year=args.year, month=args.month, time_limit=args.time_limit)
    result = scheduler.run()

    print(f"\n結果: {result.message}")
    print(f"配置件数: {len(result.assignments)}")


if __name__ == "__main__":
    main()
