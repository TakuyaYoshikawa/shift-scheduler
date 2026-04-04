"""
core/history_mapper.py

前年同月の実績データを当月の日付にマッピングし、
スコア算出に使うデータフレームを生成するモジュール。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

import pandas as pd

from core import db

logger = logging.getLogger(__name__)


def get_same_weekday_date(target_year: int, target_month: int, target_day: int) -> date | None:
    """
    対象日の曜日と同じ曜日を持つ前年同月の日付を返す。
    前年同月に存在しない場合はNoneを返す。
    """
    prev_year = target_year - 1
    try:
        target_date = date(target_year, target_month, target_day)
        target_weekday = target_date.weekday()

        prev_last_day = calendar.monthrange(prev_year, target_month)[1]
        for d in range(1, prev_last_day + 1):
            prev_date = date(prev_year, target_month, d)
            if prev_date.weekday() == target_weekday:
                # 同月内で同じ曜日の順番のものを探す
                # 例: 対象が第2木曜なら前年も第2木曜
                target_week_num = (target_day - 1) // 7
                prev_week_num = (d - 1) // 7
                if target_week_num == prev_week_num:
                    return prev_date
    except ValueError:
        pass
    return None


def build_history_scores(
    target_year: int,
    target_month: int,
    employee_ids: list[int],
    shift_ids: list[int],
) -> pd.DataFrame:
    """
    前年同月実績に基づくスコアデータフレームを生成する。

    戻り値: DataFrame with columns [day, employee_id, shift_id, score]
    """
    prev_year = target_year - 1
    history = db.get_shift_history(prev_year, target_month)

    if not history:
        logger.warning("前年同月(%d年%d月)の実績データがありません", prev_year, target_month)
        return pd.DataFrame(columns=["day", "employee_id", "shift_id", "score"])

    # 前年実績をDataFrameに変換
    hist_df = pd.DataFrame(history)
    hist_df["date"] = pd.to_datetime(hist_df["date"])
    hist_df["prev_day"] = hist_df["date"].dt.day
    hist_df["prev_weekday"] = hist_df["date"].dt.weekday

    # 対象月の日数
    days_in_month = calendar.monthrange(target_year, target_month)[1]

    # 祝日判定
    try:
        import holidays
        jp_holidays = holidays.Japan(years=[target_year, prev_year])
    except ImportError:
        jp_holidays = {}

    score_records = []

    for day in range(1, days_in_month + 1):
        target_date = date(target_year, target_month, day)
        target_weekday = target_date.weekday()
        is_target_holiday = target_date in jp_holidays

        # 前年同月の対応日（同じ曜日）を探す
        prev_date_same_weekday = get_same_weekday_date(target_year, target_month, day)

        for emp_id in employee_ids:
            emp_hist = hist_df[hist_df["employee_id"] == emp_id]
            if emp_hist.empty:
                continue

            for shift_id in shift_ids:
                # 前年同曜日・同シフトの実績
                score = 0
                if prev_date_same_weekday is not None:
                    same_wday_hist = emp_hist[
                        (emp_hist["date"].dt.date == prev_date_same_weekday)
                        & (emp_hist["shift_id"] == shift_id)
                    ]
                    if not same_wday_hist.empty:
                        if shift_id in (20, 21) and is_target_holiday:
                            score = max(score, 500)
                        else:
                            score = max(score, 200)

                if score > 0:
                    score_records.append({
                        "day": day,
                        "employee_id": emp_id,
                        "shift_id": shift_id,
                        "score": score,
                    })

    result_df = pd.DataFrame(score_records) if score_records else pd.DataFrame(
        columns=["day", "employee_id", "shift_id", "score"]
    )
    logger.info(
        "実績スコア生成完了: %d件 (%d年%d月 → %d年%d月)",
        len(result_df), prev_year, target_month, target_year, target_month,
    )
    return result_df


def build_yakkin_pair_bonus(
    target_year: int,
    target_month: int,
) -> dict[tuple[int, int], int]:
    """
    夜勤ペアボーナス辞書を生成する。
    戻り値: {(emp_id_min, emp_id_max): bonus_score, ...}
    """
    # 過去8ヶ月分の夜勤ペア実績を集計
    pair_counts: dict[tuple[int, int], int] = {}

    for months_back in range(1, 9):
        check_month = target_month - months_back
        check_year = target_year
        while check_month <= 0:
            check_month += 12
            check_year -= 1

        history = db.get_shift_history(check_year, check_month)
        yakkin_records = [r for r in history if r["shift_id"] == 20]

        # 日付でグループ化
        by_date: dict[str, list[int]] = {}
        for r in yakkin_records:
            date_str = r["date"]
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append(r["employee_id"])

        for emp_list in by_date.values():
            for i, e1 in enumerate(emp_list):
                for e2 in emp_list[i + 1:]:
                    pair = (min(e1, e2), max(e1, e2))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

    # ボーナス計算（上限150点）
    pair_bonus = {
        pair: min(count * 25, 150) for pair, count in pair_counts.items()
    }
    logger.info("夜勤ペアボーナス生成: %dペア", len(pair_bonus))
    return pair_bonus
