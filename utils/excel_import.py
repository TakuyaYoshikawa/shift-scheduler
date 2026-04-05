"""
utils/excel_import.py

Excelファイルから employee_master / shift_master / shift_history /
shift_submitted / employee_shift_capability を初回インポートするモジュール。

使い方:
    python utils/excel_import.py --seed   # shift_master の初期データを投入
    python utils/excel_import.py --file <Excel.xlsx> --year 2026 --month 2
"""

from __future__ import annotations

import argparse
import logging
import sys
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# プロジェクトルートをパスに追加（直接実行時）
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core import db  # noqa: E402

# ---------------------------------------------------------------------------
# 略称→正式名マッピング
# （班配当表の略称 → employee_master.employee_name の先頭部分など）
# ---------------------------------------------------------------------------
NICKNAME_MAP: dict[str, str] = {
    "涛川":    "涛川 紀之",
    "伊藤":    "伊藤 吉希",
    "清水":    "清水 賢爾",
    "髙井":    "髙井 善崇",
    "高井":    "髙井 善崇",
    "河野":    "河野 学",
    "渡辺倫":  "渡辺 倫也",
    "斉藤雅":  "斉藤 雅",
    "溝上":    "溝上 慎仁",
    "石井淳":  "石井 淳",
    "大庭":    "大庭 正博",
    "小幡":    "小幡 征志",
    "鈴木ゆ":  "鈴木 優子",
    "渡辺ひ":  "渡辺 ひろみ",
    "佐藤":    "佐藤 和代",
    "石野恵":  "石野 恵美子",
    "石井あ":  "石井 あ",
    "亜佐美":  "江澤 亜佐美",
    "吉野け":  "吉野 けいこ",
    "中村く":  "中村 くみ",
    "彦坂り":  "彦坂 り",
    "相馬":    "相馬 真紀",
    "荻野":    "荻野",
    "原田理":  "原田 理",
    "鈴木き":  "鈴木 君",
    "北田":    "北田 千晶",
    "魚住":    "魚住 公子",
    "板倉":    "板倉 幸代",
    "末吉":    "末吉",
    "末𠮷":    "末吉",
    "望月":    "望月",
    "祥子":    "鈴木 祥子",
    "今井":    "今井",
    "増塩":    "増塩 浩司",
    "小川":    "小川 尚美",
    "高田":    "高田",
    "鶴岡秀":  "鶴岡 秀隆",
    "片岡":    "片岡 認築拝",
    "石田":    "石田 久芳",
}


def normalize_name(name: str) -> str:
    """名前を正規化する（全角→半角・異体字対応）。"""
    if not name:
        return name
    name = str(name).strip()
    # 異体字の置換（末𠮷→末吉など）
    name = name.replace("\U00020B9F", "吉")
    name = unicodedata.normalize("NFKC", name)
    return name


def resolve_nickname(raw: str) -> str | None:
    """略称から正式名を解決する。解決できない場合はNoneを返す。"""
    raw = normalize_name(raw)
    if raw in NICKNAME_MAP:
        return NICKNAME_MAP[raw]
    # 部分一致で試みる
    for nick, full in NICKNAME_MAP.items():
        if raw.startswith(nick) or nick.startswith(raw):
            return full
    return None


# ---------------------------------------------------------------------------
# shift_master 初期データ
# ---------------------------------------------------------------------------
SHIFT_MASTER_SEED: list[dict[str, Any]] = [
    # 戸外班
    {"shift_id": 1,  "shift_name": "戸外班", "shift_code": "A",  "time_start": "15:30", "time_end": "09:30", "color_hex": "#D4A0A0"},
    {"shift_id": 2,  "shift_name": "戸外班", "shift_code": "B",  "time_start": "07:00", "time_end": "16:00", "color_hex": "#A0B4D4"},
    {"shift_id": 3,  "shift_name": "戸外班", "shift_code": "C",  "time_start": "10:00", "time_end": "19:00", "color_hex": "#A0D4A0"},
    {"shift_id": 4,  "shift_name": "戸外班", "shift_code": "Ⓒ",  "time_start": "11:00", "time_end": "20:00", "color_hex": "#B4D4A0"},
    {"shift_id": 5,  "shift_name": "戸外班", "shift_code": "DG", "time_start": "08:30", "time_end": "17:30", "color_hex": "#D4D4A0"},
    {"shift_id": 6,  "shift_name": "戸外班", "shift_code": "P",  "time_start": None,    "time_end": None,    "color_hex": "#D4D4D4"},
    # 生活班1
    {"shift_id": 7,  "shift_name": "生活班1", "shift_code": "A",  "time_start": "15:30", "time_end": "09:30", "color_hex": "#D4A0A0"},
    {"shift_id": 8,  "shift_name": "生活班1", "shift_code": "B",  "time_start": "07:00", "time_end": "16:00", "color_hex": "#A0B4D4"},
    {"shift_id": 9,  "shift_name": "生活班1", "shift_code": "C",  "time_start": "10:00", "time_end": "19:00", "color_hex": "#A0D4A0"},
    {"shift_id": 10, "shift_name": "生活班1", "shift_code": "Ⓒ",  "time_start": "11:00", "time_end": "20:00", "color_hex": "#B4D4A0"},
    {"shift_id": 11, "shift_name": "生活班1", "shift_code": "DG", "time_start": "08:30", "time_end": "17:30", "color_hex": "#D4D4A0"},
    {"shift_id": 12, "shift_name": "生活班1", "shift_code": "P",  "time_start": None,    "time_end": None,    "color_hex": "#D4D4D4"},
    # 生活班2
    {"shift_id": 13, "shift_name": "生活班2", "shift_code": "A",  "time_start": "15:30", "time_end": "09:30", "color_hex": "#D4A0A0"},
    {"shift_id": 14, "shift_name": "生活班2", "shift_code": "B",  "time_start": "07:00", "time_end": "16:00", "color_hex": "#A0B4D4"},
    {"shift_id": 15, "shift_name": "生活班2", "shift_code": "C",  "time_start": "10:00", "time_end": "19:00", "color_hex": "#A0D4A0"},
    {"shift_id": 16, "shift_name": "生活班2", "shift_code": "Ⓒ",  "time_start": "11:00", "time_end": "20:00", "color_hex": "#B4D4A0"},
    {"shift_id": 17, "shift_name": "生活班2", "shift_code": "DG", "time_start": "08:30", "time_end": "17:30", "color_hex": "#D4D4A0"},
    {"shift_id": 18, "shift_name": "生活班2", "shift_code": "P",  "time_start": None,    "time_end": None,    "color_hex": "#D4D4D4"},
    # 清掃
    {"shift_id": 19, "shift_name": "清掃",   "shift_code": "P",  "time_start": None,    "time_end": None,    "color_hex": "#D4D4D4"},
    # 夜勤
    {"shift_id": 20, "shift_name": "夜勤",   "shift_code": "Y",  "time_start": "15:30", "time_end": "09:30", "color_hex": "#D4A0D4"},
    # 宿直
    {"shift_id": 21, "shift_name": "宿直",   "shift_code": "Ⓑ",  "time_start": None,    "time_end": "09:30", "color_hex": "#FFD6A0"},
]


def seed_shift_master() -> None:
    """shift_master に初期データを投入する。"""
    for row in SHIFT_MASTER_SEED:
        db.insert_shift(
            shift_id=row["shift_id"],
            shift_name=row["shift_name"],
            shift_code=row["shift_code"],
            shift_namecode=f"{row['shift_name']}{row['shift_code']}",
            time_start=row["time_start"],
            time_end=row["time_end"],
            color_hex=row["color_hex"],
        )
    logger.info("shift_master: %d件投入完了", len(SHIFT_MASTER_SEED))
    db.add_import_log("seed", "shift_master", len(SHIFT_MASTER_SEED))


# ---------------------------------------------------------------------------
# 職員マスタ初期データ（CLAUDE.md記載の確定データ）
# ---------------------------------------------------------------------------
EMPLOYEE_SEED: list[dict[str, Any]] = [
    # 事務・専門職（最適化対象外）
    {"employee_id": 1,  "employee_name": "多田 美穂子",  "sur_name": "多田",  "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "法人会長・平日D勤"},
    {"employee_id": 2,  "employee_name": "内野 浩二",    "sur_name": "内野",  "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "法人理事長・平日D勤"},
    {"employee_id": 3,  "employee_name": "森 真由美",    "sur_name": "森",    "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "総務係長・平日D勤"},
    {"employee_id": 4,  "employee_name": "梶 由美子",    "sur_name": "梶",    "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "栄養士・平日D勤"},
    {"employee_id": 5,  "employee_name": "貞 光秀",      "sur_name": "貞",    "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "看護師・日月休"},
    {"employee_id": 6,  "employee_name": "桝田 勝貴",    "sur_name": "桝田",  "section": "事務専門職", "group_name": None, "is_optimizer_target": 0, "notes": "看護師・月火のみ"},
    # 本体男性支援員（最適化対象）
    {"employee_id": 7,  "employee_name": "鶴岡 秀隆",    "sur_name": "鶴岡",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "支援課長・GHサビ管"},
    {"employee_id": 8,  "employee_name": "片岡 認築拝",  "sur_name": "片岡",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "支援課長・入所サビ管"},
    {"employee_id": 9,  "employee_name": "石田 久芳",    "sur_name": "石田",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "平日D勤のみ"},
    {"employee_id": 10, "employee_name": "涛川 紀之",    "sur_name": "涛川",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 11, "employee_name": "伊藤 吉希",    "sur_name": "伊藤",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 12, "employee_name": "清水 賢爾",    "sur_name": "清水",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 13, "employee_name": "髙井 善崇",    "sur_name": "髙井",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": "小幡と同日禁止"},
    {"employee_id": 14, "employee_name": "河野 学",      "sur_name": "河野",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 15, "employee_name": "渡辺 倫也",    "sur_name": "渡辺",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": "GH兼務可"},
    {"employee_id": 16, "employee_name": "斉藤 雅",      "sur_name": "斉藤",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": "GH兼務可・YなしAが多い"},
    {"employee_id": 17, "employee_name": "溝上 慎仁",    "sur_name": "溝上",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 18, "employee_name": "石井 淳",      "sur_name": "石井",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 19, "employee_name": "大庭 正博",    "sur_name": "大庭",  "section": "本体男性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "出勤多め"},
    {"employee_id": 20, "employee_name": "小幡 征志",    "sur_name": "小幡",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": "髙井と同日禁止"},
    # 本体女性支援員（最適化対象）
    {"employee_id": 21, "employee_name": "鈴木 優子",    "sur_name": "鈴木",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "支援係長"},
    {"employee_id": 22, "employee_name": "渡辺 ひろみ",  "sur_name": "渡辺",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "GH兼務可"},
    {"employee_id": 23, "employee_name": "佐藤 和代",    "sur_name": "佐藤",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": "GH専従"},
    # 追加職員（班配当表確認済み）
    {"employee_id": 24, "employee_name": "石野 恵美子",  "sur_name": "石野",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 25, "employee_name": "石井 あ",      "sur_name": "石井",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 26, "employee_name": "江澤 亜佐美",  "sur_name": "江澤",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 27, "employee_name": "吉野 けいこ",  "sur_name": "吉野",  "section": "本体女性支援員", "group_name": "生活班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 28, "employee_name": "中村 くみ",    "sur_name": "中村",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 29, "employee_name": "彦坂 り",      "sur_name": "彦坂",  "section": "本体女性支援員パート", "group_name": None, "is_optimizer_target": 1, "notes": None},
    {"employee_id": 30, "employee_name": "相馬 真紀",    "sur_name": "相馬",  "section": "本体女性支援員パート", "group_name": None, "is_optimizer_target": 1, "notes": None},
    {"employee_id": 31, "employee_name": "荻野",         "sur_name": "荻野",  "section": "本体男性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 32, "employee_name": "原田 理",      "sur_name": "原田",  "section": "本体女性支援員パート", "group_name": None, "is_optimizer_target": 1, "notes": None},
    {"employee_id": 33, "employee_name": "鈴木 君",      "sur_name": "鈴木",  "section": "清掃パート",     "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 34, "employee_name": "北田 千晶",    "sur_name": "北田",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": "D勤のみ・子育て中"},
    {"employee_id": 35, "employee_name": "魚住 公子",    "sur_name": "魚住",  "section": "本体女性支援員パート", "group_name": None, "is_optimizer_target": 1, "notes": None},
    {"employee_id": 36, "employee_name": "板倉 幸代",    "sur_name": "板倉",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 37, "employee_name": "末吉",         "sur_name": "末吉",  "section": "本体男性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 38, "employee_name": "望月",         "sur_name": "望月",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 39, "employee_name": "鈴木 祥子",    "sur_name": "鈴木",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 40, "employee_name": "今井",         "sur_name": "今井",  "section": "本体",           "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 41, "employee_name": "増塩 浩司",    "sur_name": "増塩",  "section": "本体男性支援員", "group_name": "戸外班", "is_optimizer_target": 1, "notes": None},
    {"employee_id": 42, "employee_name": "小川 尚美",    "sur_name": "小川",  "section": "清掃パート",     "group_name": None,     "is_optimizer_target": 1, "notes": None},
    {"employee_id": 43, "employee_name": "高田",         "sur_name": "高田",  "section": "本体女性支援員", "group_name": None,     "is_optimizer_target": 1, "notes": None},
    # 大冨（事務・最適化対象外）
    {"employee_id": 44, "employee_name": "大冨 純子",    "sur_name": "大冨",  "section": "事務専門職",     "group_name": None,     "is_optimizer_target": 0, "notes": "事務・D勤中心"},
    # 手動列職員（最適化対象外）
    {"employee_id": 50, "employee_name": "伊東 孝浩",    "sur_name": "伊東",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 51, "employee_name": "石野 健太",    "sur_name": "石野",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 52, "employee_name": "平林 大裕",    "sur_name": "平林",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 53, "employee_name": "野坂 伸一郎",  "sur_name": "野坂",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 54, "employee_name": "渡辺 優子",    "sur_name": "渡辺",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 55, "employee_name": "山口 妙子",    "sur_name": "山口",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 56, "employee_name": "布施 宏",      "sur_name": "布施",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 57, "employee_name": "石井 兼司",    "sur_name": "石井",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 58, "employee_name": "熱田 真歩",    "sur_name": "熱田",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 59, "employee_name": "青木 由宇子",  "sur_name": "青木",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 60, "employee_name": "小林 洋美",    "sur_name": "小林",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 61, "employee_name": "新上 泰子",    "sur_name": "新上",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 62, "employee_name": "山口 久美子",  "sur_name": "山口",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 63, "employee_name": "山本 光明",    "sur_name": "山本",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 64, "employee_name": "ミカエラ",      "sur_name": "ミカエラ","section": "第一工房","group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 65, "employee_name": "鶴岡 裕太",    "sur_name": "鶴岡",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 66, "employee_name": "石橋 一博",    "sur_name": "石橋",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 67, "employee_name": "隈井 明美",    "sur_name": "隈井",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 68, "employee_name": "内野 美佐",    "sur_name": "内野",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 69, "employee_name": "安井 政子",    "sur_name": "安井",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 70, "employee_name": "真田 卓",      "sur_name": "真田",  "section": "相談支援",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 71, "employee_name": "石森 征義",    "sur_name": "石森",  "section": "どんちゃん","group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 72, "employee_name": "斉藤 正子",    "sur_name": "斉藤",  "section": "どんちゃん","group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 73, "employee_name": "斎藤 まゆみ",  "sur_name": "斎藤",  "section": "どんちゃん","group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 83, "employee_name": "椎名 進一",    "sur_name": "椎名",  "section": "第一工房",  "group_name": None, "is_optimizer_target": 0, "notes": None},
    {"employee_id": 86, "employee_name": "秋葉 典之",    "sur_name": "秋葉",  "section": "ナカポツ",  "group_name": None, "is_optimizer_target": 0, "notes": None},
]

# 職員別担当可能シフト（shift_id リスト）
# 戸外班:1-6, 生活班1:7-12, 生活班2:13-18, 清掃:19, 夜勤:20, 宿直:21
# B(2,8,14), C(3,9,15), Ⓒ(4,10,16), DG(5,11,17), P(6,12,18,19), Y=20, Ⓑ=21
_B_IDS = [2, 8, 14]   # B 各班
_C1_IDS = [3, 9, 15]  # C 各班
_C2_IDS = [4, 10, 16] # Ⓒ 各班
_DG_IDS = [5, 11, 17] # DG 各班
_P_IDS  = [6, 12, 18, 19]  # P 各班 + 清掃
_Y_ID   = [20]
_B2_ID  = [21]
_A_IDS  = [1, 7, 13]  # GH宿直（戸外班/生活班1/2のA列はGH宿直として使用）

EMPLOYEE_CAPABILITIES: dict[int, list[int]] = {
    # 事務専門職（固定D勤のみ）
    1:  _DG_IDS,
    2:  _DG_IDS,
    3:  _DG_IDS,
    4:  _DG_IDS,
    5:  _DG_IDS,
    6:  _DG_IDS,
    44: _DG_IDS,
    # 本体男性支援員
    7:  _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS + _A_IDS + _B2_ID,  # 鶴岡秀隆 B/C/D/A(GH)/B2(GH)
    8:  _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,                     # 片岡 B/C/D
    9:  _DG_IDS + _P_IDS,                                          # 石田 D/P
    10: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 涛川 Y/B/C/D
    11: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS,              # 伊藤 Y/B/C
    12: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 清水 Y/B/C/D
    13: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 髙井 Y/B/C/D
    14: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 河野 Y/B/C/D
    15: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _A_IDS,    # 渡辺倫 Y/B/C/GH兼務
    16: _B_IDS + _C1_IDS + _C2_IDS + _A_IDS + _B2_ID,             # 斉藤雅 B/C/A(GH)/B2(GH)
    17: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS,              # 溝上 Y/B/C
    18: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 石井淳 Y/B/C/D
    19: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 大庭 Y/B/C/D
    20: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS,              # 小幡 Y/B/C
    # 本体女性支援員
    21: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,   # 鈴木優子 Y/B/C/D
    22: _Y_ID + _B2_ID + _B_IDS + _C1_IDS + _C2_IDS + _A_IDS,    # 渡辺ひろみ Y/B/C/GH兼務
    23: _A_IDS + _B2_ID + _C1_IDS + _C2_IDS + _DG_IDS,            # 佐藤和代 A(GH)/B2(GH)/C(GH)/G/D
    # 追加職員
    24: _B_IDS + _C1_IDS + _C2_IDS,                                # 石野恵美子 B/C
    25: _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,                     # 石井あ B/C/D
    26: _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,                     # 江澤亜佐美 B/C/D
    27: _B_IDS + _C1_IDS + _C2_IDS + _DG_IDS,                     # 吉野けいこ B/C/D
    28: _P_IDS + _DG_IDS,                                          # 中村くみ P/D
    29: _P_IDS,                                                     # 彦坂り P
    30: _P_IDS,                                                     # 相馬 P
    31: _P_IDS,                                                     # 荻野 P
    32: _P_IDS,                                                     # 原田理 P
    33: _P_IDS,                                                     # 鈴木君 P(清掃)
    34: _DG_IDS,                                                    # 北田千晶 D勤のみ
    35: _P_IDS,                                                     # 魚住公子 P
    36: _B_IDS + _C1_IDS + _C2_IDS + _P_IDS,                      # 板倉幸代 B/C/P
    37: _B_IDS + _C1_IDS + _C2_IDS,                                # 末吉 B/C
    38: _B_IDS + _C1_IDS + _C2_IDS,                                # 望月 B/C
    39: _B_IDS + _C1_IDS + _C2_IDS,                                # 鈴木祥子 B/C
    40: _P_IDS,                                                     # 今井 P
    41: _A_IDS + _P_IDS,                                            # 増塩浩司 A/P
    42: _P_IDS,                                                     # 小川尚美 P(清掃)
    43: _B_IDS + _C1_IDS + _C2_IDS,                                # 高田 B/C
}


def seed_employee_master() -> None:
    """employee_master と employee_shift_capability に初期データを投入する。"""
    for emp in EMPLOYEE_SEED:
        db.insert_employee(
            employee_id=emp["employee_id"],
            employee_name=emp["employee_name"],
            sur_name=emp.get("sur_name"),
            section=emp.get("section"),
            group_name=emp.get("group_name"),
            is_optimizer_target=emp.get("is_optimizer_target", 1),
            notes=emp.get("notes"),
        )

    for emp_id, shift_ids in EMPLOYEE_CAPABILITIES.items():
        # 重複除去
        unique_shifts = list(set(shift_ids))
        db.set_employee_capabilities(emp_id, unique_shifts)

    logger.info("employee_master: %d件投入完了", len(EMPLOYEE_SEED))
    db.add_import_log("seed", "employee_master", len(EMPLOYEE_SEED))


def seed_employee_constraints() -> None:
    """高井(ID13)・小幡(ID20)の同日禁止制約を登録する。"""
    db.delete_employee_constraints(13)
    db.delete_employee_constraints(20)
    db.add_constraint(
        employee_id=13,
        constraint_type="no_paired_with",
        value="20",
        memo="小幡(ID20)と同日勤務禁止",
    )
    db.add_constraint(
        employee_id=20,
        constraint_type="no_paired_with",
        value="13",
        memo="髙井(ID13)と同日勤務禁止",
    )
    logger.info("employee_constraints: 高井・小幡の同日禁止を登録")


# ---------------------------------------------------------------------------
# Excel ファイルからのインポート（オプション）
# ---------------------------------------------------------------------------


def import_from_excel(file_path: str, year: int, month: int) -> None:
    """ExcelファイルからDBにインポートする（初回移行用）。"""
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxlがインストールされていません")
        return

    path = Path(file_path)
    if not path.exists():
        logger.error("ファイルが見つかりません: %s", file_path)
        return

    logger.info("Excelインポート開始: %s (year=%d, month=%d)", file_path, year, month)
    wb = openpyxl.load_workbook(file_path, data_only=True)
    logger.info("シート一覧: %s", wb.sheetnames)

    # シートの内容を確認してインポート処理を実行
    # ※実際のExcelファイル構造に応じて実装を追加する
    record_count = 0

    db.add_import_log(str(path.name), "excel_import", record_count)
    logger.info("Excelインポート完了: %d件", record_count)


# ---------------------------------------------------------------------------
# メインエントリポイント
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    log_dir = _HERE / "logs"
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
    parser = argparse.ArgumentParser(description="シフトスケジューラ初期データ投入・Excelインポート")
    parser.add_argument("--seed", action="store_true", help="マスタ初期データを投入")
    parser.add_argument("--file", help="インポートするExcelファイルパス")
    parser.add_argument("--year", type=int, default=2026, help="対象年")
    parser.add_argument("--month", type=int, default=2, help="対象月")
    args = parser.parse_args()

    db.init_db()

    if args.seed:
        logger.info("=== マスタ初期データ投入開始 ===")
        seed_shift_master()
        seed_employee_master()
        seed_employee_constraints()
        logger.info("=== マスタ初期データ投入完了 ===")

    if args.file:
        import_from_excel(args.file, args.year, args.month)

    if not args.seed and not args.file:
        parser.print_help()


if __name__ == "__main__":
    main()
