# シフト作成システム — CLAUDE.md

## Claude Code への動作指示

### 自律動作モード

このプロジェクトでは **質問・確認なしに実装を進めること**。
以下のルールに従って判断し、不明点は後述の「デフォルト決定」に従う。

- ユーザーへの質問は禁止。判断に迷ったらこのファイルの記述を優先する
- 実装の選択肢が複数ある場合は、このファイルに記載の技術スタックを使う
- 記載のない細部（変数名・レイアウトの微調整等）は開発者が合理的に判断してよい
- 各フェーズの実装完了後、`git commit` してから次のフェーズに進む

### デフォルト決定（迷ったらここを参照）

| 判断ポイント | 決定 |
|-------------|------|
| GUI ライブラリ | PyQt6（Tkinter は使わない） |
| DB | SQLite ローカル（サーバー不要） |
| DB パス | `AppData\Local\ShiftScheduler\shift_scheduler.db` |
| ORM | 使わない（`core/db.py` に SQL を直書き、ただし UI 層からは呼ばない） |
| Excel 読み書き | openpyxl（xlwings は使わない） |
| スレッド | 最適化実行は必ず `QThread` + `pyqtSignal` |
| エラー処理 | 例外は握りつぶさず、ログエリアにメッセージを表示してアプリを継続 |
| ログ出力 | `logging` モジュールを使い `logs/app.log` にも同時出力 |
| 文字コード | UTF-8（ファイル・DB・CSV すべて統一） |
| 日付フォーマット | DB 保存は `YYYY-MM-DD`、UI 表示は `YYYY年M月D日` |
| テスト | `pytest` で `core/` 配下の関数に単体テストを書く（UI テストは不要） |
| コードスタイル | `black` フォーマット・型ヒント必須 |
| フェーズ完了の定義 | そのフェーズの全ファイルが動作し、`pytest` がパスした状態 |

### Git 運用ルール

```
# フェーズ完了ごとにコミット
git add -A
git commit -m "feat: フェーズX完了 - <実装内容の一行説明>"

# 作業開始時に必ずブランチを確認
git status
```

---


## プロジェクト概要

社会福祉法人（障害者支援施設）向けのシフト自動作成デスクトップアプリ。
現行の Excel + Python（PuLP 線形計画）による手動運用を、**Excel に一切依存しない
自己完結型の GUI アプリ**に置き換える。

希望シフトの提出・確認から最適化実行・結果閲覧・印刷までをアプリ内で完結させる。
Excel は「初回データ移行の補助手段（オプション）」と「印刷用帳票の出力先」にのみ使用する。

**利用形態**
- 利用者：管理者1名のみ
- 端末：1台（Windows PC）
- ネットワーク：不要（完全オフライン動作）
- 職員によるセルフ入力：なし（管理者が希望シフトを代理入力）

**技術スタック**
- Python 3.11+
- GUI: PyQt6（リッチなグリッド表示・カラーセルが必要なため Tkinter より優先）
- 最適化エンジン: PuLP + CBC ソルバー
- データ永続化: SQLite（ローカルファイル、サーバー不要）
- Excel 出力（オプション）: openpyxl
- 祝日判定: holidays ライブラリ
- 配布: PyInstaller（単一 exe、Windows 10/11 対象）

---

## ドメイン知識

### 施設構成

| 施設名 | 区分 |
|--------|------|
| ピア宮敷（障害者支援施設） | 入所 |
| ピアの家（共同生活援助 GH） | GH |
| 第１工房（生活介護・就労継続B型） | 通所 |
| 夷隅郡市福祉作業所（生活介護） | 通所 |
| 相談支援事業所 | 事務 |

### シフト種別（shift_master）

各シフトは「班（shift_name）」＋「シフトコード（shift_code）」で一意に識別する。

**入所（ピア宮敷）**

| shift_id | shift_code | 名称 | 時間帯 |
|----------|------------|------|--------|
| 20 | Y | 夜勤 | 15:30〜翌9:30 |
| 21 | B2 | 宿直明け | 〜翌9:30 |
| 2,8,14 | B1 | 早番 | 7:00〜16:00 |
| 3,9,15 | C1 | 遅番① | 10:00〜19:00 |
| 4,10,16 | C2 | 遅番② | 11:00〜20:00 |
| 5,11,17 | DG | 日勤 | 8:30〜17:30 |
| 6,12,18,19 | P | パート | 個別 |

**GH（ピアの家）**

| shift_code | 名称 | 時間帯 |
|------------|------|--------|
| A | GH宿直 | 8:30〜翌9:30 |
| B2(GH) | GH宿直明け | 〜翌9:30 |
| B1(GH) | GH早番 | 7:00〜16:00 |
| C(GH) | GH遅番 | 12:00〜21:00 |
| G(GH) | GH風呂番 | 9:30〜18:30 |
| D(GH) | GH日勤 | 9:30〜17:30 |

**班構成**：戸外班・生活班1・生活班2・清掃・夜勤・宿直（shift_id 1〜21）

**自動スケジューリング対象**：shift_id 1〜21（戸外班・生活班1・生活班2・清掃・夜勤・宿直）のみ。
事務所・医務・世話人・第1工房・どんちゃん・ナカポツ・相談・福作 は対象外（手動入力）。

### 従業員マスタ

主な属性：
- `employee_id`：職員ID
  - 自動スケジューリング対象: ID 7〜23（および班配当表で確認された追加職員）
  - 事務専門職（ID 1〜6・大冨）: 固定D勤のため最適化対象外
  - 手動列職員（ID 50〜86）: 第一工房・ナカポツ・どんちゃん等・最適化対象外
- `employee_name` / `sur_name`：氏名
- `section`：所属（本体男性支援員、本体女性職員、事務専門職 等）
- 担当可能シフト：職員ごとに複数のシフトコードを設定（多対多）
- `group`：班（戸外班 / 生活班）

### 職員マスタ（シフト_R8_2.xlsx より確定）

#### 自動スケジューリング対象職員

**事務・専門職（ID 1〜6・大冨）— 最適化対象外（固定D勤）**

| ID | 氏名 | 役職 | 勤務パターン |
|----|------|------|------------|
| 1 | 多田 美穂子 | 法人会長 | 平日D勤のみ・土日祝休 |
| 2 | 内野 浩二 | 法人理事長 | 平日D勤のみ・土日祝休 |
| 3 | 森 真由美 | 総務係長 | 平日D勤のみ・土日祝休 |
| 4 | 梶 由美子 | 栄養士 | 平日D勤（8:30〜14:00）・土日祝休 |
| 5 | 貞 光秀 | 看護師 | 日月休・火〜土D勤 |
| 6 | 桝田 勝貴 | 看護師 | 月火のみD勤（8:30〜12:00） |
| — | 大冨 純子 | 事務 | D勤中心・詳細は初回インポート時に確認 |

**本体男性支援員（ID 7〜20）— 自動スケジューリング対象**

| ID | 氏名 | 担当可能シフト | 特記事項 |
|----|------|-------------|---------|
| 7 | 鶴岡 秀隆 | B/C/D/A(GH)/Ⓑ(GH) | 支援課長・GHサビ管 |
| 8 | 片岡 認築拝 | B/C/D | 支援課長・入所サビ管 |
| 9 | 石田 久芳 | D/P | 平日D勤のみ・土日祝休 |
| 10 | 涛川 紀之 | Y/B/C/D | 月28日実績: Y3 B6 C4 D2 |
| 11 | 伊藤 吉希 | Y/B/C/Ⓒ | 月28日実績: Y3 B5 C4 Ⓒ3 |
| 12 | 清水 賢爾 | Y/B/C/D | 月28日実績: Y3 B5 C6 |
| 13 | 髙井 善崇 | Y/B/C/D | **小幡(ID20)と同日勤務不可** |
| 14 | 河野 学 | Y/B/C/D | 月28日実績: Y4 B6 C3 D1 |
| 15 | 渡辺 倫也 | Y/B/C/Ⓒ/A(GH)/Ⓑ(GH) | GH兼務可 |
| 16 | 斉藤 雅 | B/C/Ⓒ/A(GH)/Ⓑ(GH) | GH兼務可・YなしⒶが多い |
| 17 | 溝上 慎仁 | Y/B/C | 月28日実績: Y3 B6 C6 |
| 18 | 石井 淳 | Y/B/C/D | 月28日実績: Y3 B3 C6 D2 |
| 19 | 大庭 正博 | Y/B/C/D | 月28日実績: Y3 B7 C6 D1（出勤多め） |
| 20 | 小幡 征志 | Y/B/C | **高井(ID13)と同日勤務不可** |

**本体女性支援員（ID 21〜、女性パート含む）— 自動スケジューリング対象**

| ID | 氏名 | 担当可能シフト | 特記事項 |
|----|------|-------------|---------|
| 21 | 鈴木 優子 | Y/B/C/D | 支援係長 |
| 22 | 渡辺 ひろみ | Y/B/C/Ⓒ/A(GH)/Ⓑ(GH) | GH兼務可 |
| 23 | 佐藤 和代 | A(GH)/Ⓑ(GH)/Ⓒ(GH)/G(GH)/D | GH専従に近い |

**班配当表から確認できる追加職員（ID未確定・初回インポート時に採番）**

班配当表（活動班配当表_２月_.xlsx）に登場する略称と対応する正式名・セクション：

| 略称 | 推定正式名 | 区分 | 担当可能シフト |
|------|-----------|------|-------------|
| 石野（恵美子） | 石野 恵美子 | 本体女性支援員 | B/C |
| 石井あ | 石井 あ（フルネーム確認要） | 本体女性支援員 | B/C/D |
| 亜佐美 | 江澤 亜佐美 | 本体女性支援員 | B/C/D |
| 吉野け | 吉野 けいこ（フルネーム確認要） | 本体女性支援員 | B/C/D |
| 中村く | 中村 くみ（フルネーム確認要） | 本体女性支援員 | P/D |
| 彦坂り | 彦坂 り（フルネーム確認要） | 本体女性支援員パート | P |
| 相馬 | 相馬 真紀 | 本体女性支援員パート | P |
| 荻野 | 荻野（フルネーム確認要） | 本体男性支援員 | P |
| 原田（理） | 原田 理（フルネーム確認要） | 本体女性支援員パート | P |
| 鈴木き | 鈴木 君（フルネーム確認要） | 清掃パート | P |
| 北田 | 北田 千晶 | 本体女性支援員 | D勤のみ（子育て中） |
| 魚住 | 魚住 公子 | 本体女性支援員パート | P |
| 板倉 | 板倉 幸代 | 本体女性支援員 | B/C/P |
| 末吉 | 末吉（フルネーム確認要） | 本体男性支援員 | B/C |
| 望月 | 望月（フルネーム確認要） | 本体女性支援員 | B/C |
| 祥子 | 鈴木 祥子（フルネーム確認要） | 本体女性支援員 | B/C |
| 今井 | 今井（フルネーム確認要） | 本体（GH？） | P |
| 増塩 | 増塩 浩司 | 本体男性支援員（戸外班） | A/P |
| 小川 | 小川 尚美 | 清掃パート | P |
| 高田 | 高田（フルネーム確認要） | 本体女性支援員 | B/C |

> **注意**: 略称のみの職員は初回Excelインポート時に正式名・IDを確定させ、  
> `employee_master` テーブルに正確に登録すること。

#### 手動列職員（スケジューリング対象外）

`shift_manual` テーブルで管理。班配当表のビュー表示には含めるが、最適化処理には一切使わない。

**世話人・GH関連（略称のみ・手動入力）**

| 略称 | 推定正式名 | 配置場所 |
|------|-----------|---------|
| 弓削 | 弓削 和子 | GH世話人 |
| とみ子（高師とみ子） | 高師 とみ子 | GH世話人 |
| 晴美 | 晴美（フルネーム確認要） | GH世話人 |
| 茂美 | 鶴岡 茂美 | GH世話人 |

**第一工房・ナカポツ・どんちゃん・相談支援（IDあり）**

| ID | 氏名 | 所属 |
|----|------|------|
| 50 | 伊東 孝浩 | 第一工房 |
| 51 | 石野 健太 | 第一工房 |
| 52 | 平林 大裕 | 第一工房 |
| 53 | 野坂 伸一郎 | 第一工房 |
| 54 | 渡辺 優子 | 第一工房 |
| 55 | 山口 妙子 | 第一工房 |
| 56 | 布施 宏 | 第一工房 |
| 57 | 石井 兼司 | 第一工房 |
| 58 | 熱田 真歩 | 第一工房 |
| 59 | 青木 由宇子 | 第一工房 |
| 60 | 小林 洋美 | 第一工房 |
| 61 | 新上 泰子 | 第一工房 |
| 62 | 山口 久美子 | 第一工房 |
| 63 | 山本 光明 | 第一工房 |
| 64 | ミカエラ | 第一工房 |
| 83 | 椎名 進一 | 第一工房 |
| 65 | 鶴岡 裕太 | ナカポツ |
| 66 | 石橋 一博 | ナカポツ |
| 67 | 隈井 明美 | ナカポツ |
| 68 | 内野 美佐 | ナカポツ |
| 69 | 安井 政子 | ナカポツ |
| 86 | 秋葉 典之 | ナカポツ |
| 70 | 真田 卓 | 相談支援 |
| 71 | 石森 征義 | どんちゃん |
| 72 | 斉藤 正子 | どんちゃん |
| 73 | 斎藤 まゆみ | どんちゃん |

---

## データモデル（SQLite）

```sql
-- シフト種別マスタ
CREATE TABLE shift_master (
    shift_id        INTEGER PRIMARY KEY,
    shift_name      TEXT NOT NULL,   -- 班名（戸外班、生活班1、夜勤 等）
    shift_code      TEXT NOT NULL,   -- シフト記号（Y, B1, C1, DG, P 等）
    shift_namecode  TEXT,            -- 結合キー（shift_name + shift_code）
    time_start      TEXT,            -- 開始時刻 "HH:MM"（表示用）
    time_end        TEXT,            -- 終了時刻 "HH:MM"（表示用）
    color_hex       TEXT DEFAULT '#FFFFFF'  -- UI 表示色
);

-- 従業員マスタ（1職員に対して1行）
CREATE TABLE employee_master (
    employee_id     INTEGER PRIMARY KEY,
    employee_name   TEXT NOT NULL,
    sur_name        TEXT,
    section         TEXT,            -- 所属（本体男性支援員 等）
    group_name      TEXT,            -- 班（戸外班 / 生活班）
    work_hours      TEXT,            -- 所定労働時間（"8:00〜17:00" 等）
    is_optimizer_target INTEGER DEFAULT 1,  -- 1=最適化対象, 0=除外（固定D勤等）
    notes           TEXT             -- 備考・特記事項
);

-- 職員ごとの担当可能シフト（多対多）
CREATE TABLE employee_shift_capability (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employee_master(employee_id),
    shift_id    INTEGER NOT NULL REFERENCES shift_master(shift_id),
    UNIQUE(employee_id, shift_id)
);

-- 個人別勘案事項ルール（構造化）
CREATE TABLE employee_constraints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     INTEGER NOT NULL REFERENCES employee_master(employee_id),
    constraint_type TEXT NOT NULL,
    -- 'weekday_only'    : 平日のみ出勤（土日祝は休暇）
    -- 'fixed_shift'     : 特定シフト固定（shift_code を value に）
    -- 'no_paired_with'  : 特定職員と同日禁止（employee_id を value に）
    -- 'holiday_off'     : 祝日休み
    -- 'days_of_week'    : 特定曜日のみ（"月火" 等を value に）
    value           TEXT,            -- ルールの値
    memo            TEXT             -- 表示用メモ
);

-- 勤務履歴（前年同月の実績）
CREATE TABLE shift_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,       -- YYYY-MM-DD
    employee_id INTEGER NOT NULL,
    shift_id    INTEGER NOT NULL,
    shift_code  TEXT,
    group_name  TEXT,
    sur_name    TEXT
);

-- 希望シフト提出（年月ごとに管理）
CREATE TABLE shift_submitted (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employee_master(employee_id),
    day         INTEGER NOT NULL,    -- 日（1〜31）
    request     TEXT NOT NULL,       -- シフトコード or '休暇'
    submitted_at TEXT DEFAULT (datetime('now')),
    UNIQUE(year, month, employee_id, day)
);

-- 最適化結果
CREATE TABLE shift_result (
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

-- 手動入力シフト（自動スケジューリング対象外の班・列）
-- 事務所・医務・世話人・第1工房・どんちゃん等
CREATE TABLE shift_manual (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    assignment_day  INTEGER NOT NULL,
    sub_row         INTEGER NOT NULL,  -- サブ行（1〜3）
    column_label    TEXT NOT NULL,     -- 列ラベル（'事務所', '医務', '世話人', '第1工房A' 等）
    staff_name      TEXT,              -- 氏名（略称）
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(year, month, assignment_day, sub_row, column_label)
);

-- 手動修正ログ（自動計算後の変更履歴）
CREATE TABLE shift_result_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    assignment_day  INTEGER NOT NULL,
    employee_id     INTEGER NOT NULL,
    change_type     TEXT NOT NULL,   -- 'manual_edit' | 'manual_delete' | 'manual_add' | 'auto_calc'
    before_shift_id INTEGER,         -- 変更前 shift_id（NULL=未配置）
    after_shift_id  INTEGER,         -- 変更後 shift_id（NULL=削除）
    changed_at      TEXT DEFAULT (datetime('now'))
);

-- 初期データの移行ログ（Excel インポート履歴）
CREATE TABLE import_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT DEFAULT (datetime('now')),
    source_file TEXT,
    record_type TEXT,    -- 'employee_master' | 'shift_history' | 'shift_submitted'
    record_count INTEGER
);
```

---

## 最適化エンジン仕様

### スコアリング

| 条件 | スコア |
|------|--------|
| 提出シフト希望と合致 | 1000（最優先） |
| 前年同月・祝日と同じ日に同シフト（夜勤・宿直） | 500 |
| 前年同月・同曜日に同シフト | 200 |
| その他（初期値） | -50 |

### 自動スケジューリング対象範囲

最適化エンジンが扱うのは以下の shift_id のみ。それ以外の列（事務所・医務・世話人・第1工房等）は
最適化変数に含めず、DB にも `shift_result` ではなく別途手動入力として保存する。

| 対象 | 班名 | shift_id | shift_code |
|------|------|----------|------------|
| ✅ 自動 | 戸外班 | 1〜6 | A, B, C, Ⓒ, D/G, P |
| ✅ 自動 | 生活班1 | 7〜12 | A, B, C, Ⓒ, D/G, P |
| ✅ 自動 | 生活班2 | 13〜18 | A, B, C, Ⓒ, D/G, P |
| ✅ 自動 | 清掃 | 19 | P |
| ✅ 自動 | 夜勤 | 20 | Y |
| ✅ 自動 | 宿直 | 21 | B2 |
| ❌ 手動 | 事務所 | — | D |
| ❌ 手動 | 医務 | — | D |
| ❌ 手動 | 世話人 | — | B/C/D |
| ❌ 手動 | 第1工房 | — | A, B, C/Ⓒ, D |
| ❌ 手動 | どんちゃん | — | — |
| ❌ 手動 | ナカポツ | — | — |
| ❌ 手動 | 相談 | — | — |
| ❌ 手動 | 福作 | — | — |

手動列は班配当表ビューには表示するが、`scheduler.py` の変数定義・制約・スコアには一切含めない。

### ハード制約（絶対条件・違反したら解なし）

1. **1日1勤務**: 1職員が同日に複数シフトに入れない  
   `Σ_s shift[d][e][s] <= 1`

2. **1シフト上限3名**: 同日同シフトIDは最大3名  
   `Σ_e shift[d][e][s] <= 3`

3. **夜勤毎日2名以上**: shift_id=20（Y）は毎日必ず2名以上  
   `Σ_e shift[d][e][20] >= 2`

4. **夜勤翌日は宿直**: 夜勤(Y)の翌日は宿直明け(B2)に強制配置（Big-M）  
   `shift[d+1][e][21] >= shift[d][e][20]`  
   ※ Big-M より等式不等式の方がソルバーに優しい。最終日は対象外。

5. **宿直明け翌日は休み（新規追加）**: B2の翌日は全シフト禁止  
   `Σ_s shift[d+1][e][s] <= 1 - shift[d][e][21]`  
   ※ 宿直→宿直明け→翌日出勤という過酷な連続を防ぐ。

6. **休暇申請者は出勤ゼロ**: request='休暇' の職員はその日の全シフト = 0  
   `Σ_s shift[d][e][s] = 0`

7. **勤務可能パターン制限**: `employee_shift_capability` にない（職員, shift_id）は配置禁止  
   ただし以下は除外（スコアで誘導）：  
   - 希望シフト申請済みの組み合わせ  
   - 夜勤(20)・宿直(21)（毎日必須のため全員に開放）

8. **特定職員ペア同日禁止**: `employee_constraints` の `no_paired_with` から動的生成  
   高井(id=14)と小幡(id=22)が代表例：  
   `Σ_s shift[d][14][s] + Σ_s shift[d][22][s] <= 1`

### ソフト制約（スコアで誘導・違反しても解は出る）

希望シフトはハード制約にすると実行不可能になりやすいため、**ペナルティ付きのソフト制約**に変更する。

```
# 希望シフトごとにペナルティ変数(slack)を導入
for (d, e, code) in requested_workdays:
    deploy_ids = shift_ids_for_code(code)
    slack[d][e] >= 0  # 整数変数
    Σ_s shift[d][e][s∈deploy_ids] + slack[d][e] >= 1
    # slack=0 なら希望充足、slack=1 なら未充足（目的関数でペナルティ）
```

ペナルティ重みは `PENALTY_UNFULFILLED_REQUEST = 2000`（スコア最大値1000の2倍）に設定し、
希望充足を強く促しながら、どうしても無理な場合は解を出せるようにする。

### 目的関数（改善後）

```
maximize:
    Σ_d Σ_e Σ_s  score[d][e][s] × shift[d][e][s]   # スコア最大化
  - Σ_d Σ_e      PENALTY_UNFULFILLED_REQUEST × slack[d][e]  # 希望未充足ペナルティ
  - WEIGHT_FAIRNESS × (max_workdays - min_workdays)  # 公平性（出勤日数の平準化）
```

`max_workdays`・`min_workdays` は職員ごとの出勤日数の最大・最小を表す補助変数：
```
for e in list_employee:
    workdays[e] = Σ_d Σ_s shift[d][e][s]
    max_workdays >= workdays[e]
    min_workdays <= workdays[e]
```
`WEIGHT_FAIRNESS = 10`（スコアに比べて小さく、公平性は二次目的として扱う）

### スコアリング体系（実績データ基づく改定版）

#### 基本スコア

| 条件 | スコア | 根拠 |
|------|--------|------|
| 希望シフト申請と合致 | **+1000** | 最優先。未充足ペナルティ2000と対になる |
| 前年同月・祝日同日・夜勤/宿直 | **+500** | 夜勤は曜日より日付パターンが強い（実績より） |
| 前年同月・同曜日に同シフト | **+200** | 曜日パターンの継続 |
| 夜勤ペアの継続（過去に同日夜勤した組み合わせ） | **+150** | 実績ペア分析より：慣れたペアを優先 |
| 初期値（上記以外） | **−50** | 不要な配置を抑制 |

#### ペナルティ体系

| 条件 | ペナルティ | 根拠 |
|------|-----------|------|
| 希望シフト未充足 | **−2000** | スコア最大値の2倍 |
| 夜勤インターバル5日未満 | **−300/日** | 実測最小3日あり、5日未満は30%。ソフトで抑制 |
| B2翌日出勤 | **−500** | 実績92.6%が休み。完全禁止は現場判断に委ねソフト化 |
| 月間出勤日数の均等化違反 | **−10×差分²** | 最大差≤3日を目標（実績最大差4日） |
| 夜勤メイン職員の月5回超 | **−400** | 実績上限は月5回（江澤亜佐美・末吉） |
| 夜勤標準職員の月4回超 | **−200** | 実績標準は月3〜4回 |

#### 夜勤ペアスコアの算出方法

```python
# 過去8ヶ月の同日夜勤実績からペアスコアを計算
# 例: 小幡×末吉は6回ペア → bonus +150
pair_history = build_pair_history(shift_history_df)

def yakkin_pair_bonus(emp1, emp2, pair_history):
    count = pair_history.get((min(emp1,emp2), max(emp1,emp2)), 0)
    return min(count * 25, 150)  # 上限150点
```

#### 夜勤インターバルペナルティの実装

```python
# 同月内での夜勤インターバルチェック
for e in list_employee:
    y_days = [d for d in list_day]  # 夜勤候補日
    for i, d1 in enumerate(y_days):
        for d2 in y_days[i+1:]:
            if d2 - d1 < 5:  # 5日未満インターバル
                # 両日に夜勤が入った場合にペナルティ
                too_close = pulp.LpVariable(f"too_close_{e}_{d1}_{d2}", cat='Binary')
                problem += too_close >= shift[d1][e][20] + shift[d2][e][20] - 1
                problem += penalty_interval += 300 * too_close
```

**スコアの実装方法（gap変数を廃止）**:
```python
# 現行（誤り）: gap変数経由
problem += gap[d][e][s] == score * shift[d][e][s]
problem.objective = lpSum(gap[d][e][s] ...)

# 改善後: 直接展開
scores_df = build_scores_dataframe(...)  # 疎なDataFrame
problem.objective = lpSum(
    scores_df.loc[(d,e,s), 'score'] * shift[d][e][s]
    for (d,e,s) in scores_df.index
) - lpSum(PENALTY * slack[d][e] for (d,e) in request_index)   - WEIGHT_FAIRNESS * (max_workdays - min_workdays)
```

### 実装指針

- スコア配列: `pd.DataFrame` でインデックスを `(day, emp_id, shift_id)` にした疎行列。  
  全パターン初期化（約150万エントリ）は行わず、実在するレコードのみ保持する。
- CBC ソルバー: `resource_path("cbc")` でバイナリパスを解決。
- 実行: `QThread` + `pyqtSignal` でバックグラウンド実行。UI をブロックしない。
- タイムアウト: `problem.solve(PULP_CBC_CMD(timeLimit=120))` で2分上限を設定。  
  最適解が出なくても実行可能解があれば採用し、UI に「暫定解」と表示する。

---

## 画面構成（Excel 不要・完全 UI 完結）

### 全体レイアウト

```
┌─────────────────────────────────────────────┐
│  シフト作成システム        [年: 2026] [月: 2]  │
├──────────┬──────────┬──────────┬────────────┤
│ マスタ管理 │ 希望シフト │ 自動作成  │ シフト確認  │
│          │  入力     │  実行    │  ・出力    │
└──────────┴──────────┴──────────┴────────────┘
│  タブコンテンツエリア                          │
│                                              │
└──────────────────────────────────────────────┘
│  [ログ出力エリア（スクロール、折りたたみ可）]    │
└──────────────────────────────────────────────┘
```

---

### タブ1：マスタ管理

サブタブで切り替え：

#### 1-A 職員マスタ

```
[+ 追加] [✏ 編集] [🗑 削除]  [Excelからインポート（初回のみ）]

 ID │ 氏名       │ 所属     │ 班   │ 最適化対象
  1 │ 多田美穂子  │ 事務専門 │ -   │ ☐
  8 │ 鶴岡秀隆   │ 男性支援 │ 生活 │ ☑
 .. │ ...        │ ...     │ ... │ ...
```

「追加/編集」ダイアログ：
- 氏名・省略名・所属・班・勤務時間・備考
- **担当可能シフト**：shift_master 全件をチェックボックスで表示
- **勘案事項**：ルール種別ドロップダウン＋値入力で複数行追加可能

#### 1-B シフト種別マスタ

```
[+ 追加] [✏ 編集] [🗑 削除]

 ID │ 班名  │ コード │ 時間帯         │ 色
  1 │ 戸外班 │ A     │ 15:30〜翌9:30 │ ██ #FFB3B3
  2 │ 戸外班 │ B1    │ 7:00〜16:00   │ ██ #B3FFB3
```

#### 1-C 過去履歴インポート

- 最適化スコア計算に使う前年実績を Excel から取り込む（初回移行専用）
- インポート済み期間の一覧表示・重複インポート防止チェック
- 日常運用では不要（結果が自動的に `shift_history` に蓄積される）

---

### タブ2：希望シフト入力

```
2026年 2月  [< 前月] [次月 >]  [一括クリア] [保存] [CSVエクスポート]

 氏名  │ 1  │ 2  │ 3  │ 4  │ 5  │ 6  │ 7  │...│ 28│合計
       │ 日  │ 月  │ 火  │ 水  │ 木  │ 金  │ 土  │   │ 金 │
───────┼────┼────┼────┼────┼────┼────┼────┼───┼───┼──
涛川紀之│    │    │    │    │    │    │ ／  │   │   │
伊藤吉希│    │    │    │    │    │    │ ／  │   │C1 │
 ...   │    │    │    │    │    │    │    │   │   │
```

**セル操作**
- セルをクリック → ドロップダウンでシフトコード / 「休暇」/ 空欄を選択
- 土日・祝日列は薄灰色で自動着色
- 入力済みセル：シフトコードに応じた背景色で表示
- 休暇セル：「／」表示・グレー背景

**ボタン**
- `[保存]`：DB の `shift_submitted` テーブルに UPSERT
- `[Excelからインポート]`：既存 Excel からの初回移行用（通常は使わない）
- `[CSVエクスポート]`：入力内容を CSV で書き出し（バックアップ用）

---

### タブ3：自動作成実行

```
対象月: 2026年2月

■ 実行前チェック
✅ 職員マスタ: 50名
✅ 過去履歴: 2025年2月〜4月 インポート済み
✅ 希望シフト: 38名 入力済み / 50名中
⚠️ 未入力の職員: 12名（希望なしとして処理）

■ 最適化オプション
最大出勤日数 [23] 日/月   夜勤最低人数 [2] 名/日   1シフト最大人数 [3] 名

         [▶ シフト自動作成を実行]    [■ キャンセル（実行中のみ有効）]

─── 実行ログ ────────────────────────────────────────
[10:23:01] 最適化開始（対象: 50名×28日）
[10:23:02] 履歴データ処理中... 1,240件
[10:23:05] スコア構築完了
[10:23:05] PuLP 最適化実行中...
[10:23:18] 最適解発見 (Status: Optimal)
[10:23:18] 結果を DB に保存完了
      ✅ 完了 → [シフト確認・出力タブへ]
```

- 実行中はボタンを無効化・プログレスバーを表示
- 完了後、過去の実行履歴（日時・Status）をドロップダウンで参照切り替え可能

---
### タブ4：シフト確認・調整・出力

自動計算後に管理者が手動で確認・修正することを想定した設計。
4つのサブビューをタブで切り替える。

---

#### 4-A 月次シフト表（職員×日付グリッド）

- 職員×日付のグリッド。セルをクリックすると即座に手動調整パネル（4-C）へ遷移
- シフト種別ごとに背景色を設定（Y=紫、B1=青、C1=緑、DG=黄、休=灰）
- 手動修正済みセル：紫枠でハイライト（自動計算結果との差分を一目で確認）
- 制約違反セル：赤背景＋赤枠でハイライト（夜勤不足・同日重複等）
- フッター行：日付ごとの夜勤配置人数を集計表示。2名未満は赤で警告
- タイトルバー右上に「手動修正N件」「警告N件」バッジをリアルタイム表示

```
[手動修正 3件]  [警告 1件]  [確定・保存]

 氏名    │ 1日 │ 2月 │ 3火 │...│ 10火      │...│ 28金 │ 計
─────────┼─────┼─────┼─────┼───┼───────────┼───┼──────┼───
涛川紀之  │ ／  │ C1  │  Y  │...│ Y ←紫枠   │...│  DG  │ 20
伊藤吉希  │ ／  │  B1 │  B1 │...│ Y? ←赤枠  │...│   Y  │ 18
─────────┼─────┼─────┼─────┼───┼───────────┼───┼──────┼───
夜勤計    │  0  │  2  │  2  │...│  1!←赤    │...│   2  │
```

---

#### 4-B 班別配当表ビュー（Excel シート「1」〜「4」と同一フォーマット）

既存 Excel のシート「1」〜「4」と同じ週別・行列構造を画面上に再現する。
2月（28日）の場合は第1〜4週タブで切り替え、該当範囲だけを表示する。

**週タブと日付範囲（2月28日の場合）**

| タブ | 対応 Excel シート | 日付範囲 |
|------|-----------------|---------|
| 第1週 | シート「1」 | 1日（日）〜 7日（土） |
| 第2週 | シート「2」 | 8日（日）〜 14日（土） |
| 第3週 | シート「3」 | 15日（日）〜 21日（土） |
| 第4週 | シート「4」 | 22日（日）〜 28日（金） |

月によって最終日が変わるため、週タブと日付範囲は `calendar.monthrange()` で動的に計算する。

**列構造（シート「1」〜「3」共通、列インデックスは Excel 準拠）**

```
日付(3行) | サブ行 | 戸外班(A B C Ⓒ D/G P) | 生活班1(A B C Ⓒ D/G P) | 生活班2(A B C Ⓒ D/G P) | 清掃P | 夜勤Y | 宿直B2 | 事務所D | 医務D | 世話人B/C/D | …
```

シート「4」は宿直列（B2）がなく、列オフセットが2つ左にずれる。

**行構造（各日付につき3サブ行）**

- サブ行1・2・3 はそれぞれ最大3名まで配置できるスロット
- 自動スケジューリング結果（`shift_result`）はサブ行1から順に埋める
- 手動入力列（事務所・医務・世話人・第1工房等）は `shift_manual` テーブルから表示

**表示・編集ルール**

- 自動配置セル（`shift_result`）：クリックで手動調整パネルを開く
- 手動入力セル（`shift_manual`）：クリックでインライン編集（テキスト直接入力）
- 手動修正済みセル：紫枠でハイライト
- 土日列：列全体を薄着色（日=薄赤、土=薄青）
- 祝日：日曜と同色（薄赤）

```
          │     │ 戸外班              │ 生活班１            │ 生活班２            │清│夜│宿│事│医│世
          │     │ 1  2  3  4  5  6  │ 7  8  9 10 11 12  │13 14 15 16 17 18  │掃│勤│直│務│務│話
          │     │ A  B  C  Ⓒ D/G P  │ A  B  C  Ⓒ D/G P  │ A  B  C  Ⓒ D/G P  │P │Y │B2│D │D │人
──────────┼─────┼────────────────────┼────────────────────┼────────────────────┼──┼──┼──┼──┼──┼──
 3日(火)  │  1  │    髙井            │    大庭             │                   │  │涛│渡 │内│  │弓
          │  2  │    河野            │                   │                   │  │清│大 │森│  │
          │  3  │    伊藤            │                   │                   │  │  │   │梶│  │
──────────┼─────┼─────...
```

---

#### 4-C 手動調整パネル

月次グリッドまたは班別ビューからセルをクリックすると表示。
変更を適用する前に**制約チェックをリアルタイム実行**して結果を表示する。

```
修正中: 伊藤 吉希 — 2/10（火）  [制約違反セル]

現在のシフト: 未配置（夜勤不足）
変更後:      [Y（夜勤）▼]

制約チェック（リアルタイム）
✓ 1日1勤務: 問題なし（当日未配置）
✓ 担当可能シフト: Y は担当可
✓ 翌日（2/11）: 宿直明け(B2)が自動設定されます
✓ 月間出勤数: 19日 → 20日（上限23日 以内）
✓ 2/10 夜勤計: 1名 → 2名（制約クリア）
✓ 高井・小幡との同日制約: 両名とも当日未出勤

[この変更を適用]  [キャンセル]
```

制約チェックの実装：`constraints.py` の制約生成ロジックを再利用し、
変更後の状態でチェックのみ実行する（PuLP は使わず Python で軽量検証）。

制約に引っかかる場合は該当チェック行を赤表示し、適用ボタンを無効化する。

---

#### 4-D 修正履歴

自動計算後に加えた手動修正をすべてログとして記録・表示する。

```
[すべて取り消し（自動計算結果に戻す）]

 日時           変更内容                          種別
 2/10 10:31    涛川 紀之: 未配置 → Y（夜勤）      手動
 2/10 10:28    高井 善崇: B1 → C1（遅番①）        手動
 2/10 10:25    清水 賢爾: DG → C1（遅番①）        手動
 2/10 10:20    自動計算完了（PuLP Optimal）         自動
```

- 修正履歴は `shift_result_log` テーブルに保存（year, month, 変更前後, 日時, 種別）
- 「すべて取り消し」で `shift_result` を最新の自動計算結果に巻き戻す
- 個別の取り消しは未実装でよい（全件取り消し後に再調整）

---

#### 出力オプション

| ボタン | 動作 |
|--------|------|
| `[印刷]` | OS の印刷ダイアログ（A3横向き） |
| `[Excelエクスポート]` | openpyxl で `生データ` シートを書き込み |
| `[CSV出力]` | 職員×日付のシフトコードを CSV で保存 |
| `[PDF出力]` | QPrinter で PDF 書き出し |

---


## ファイル構成

```
shift_scheduler/
├── main.py                      # エントリポイント・アプリ起動
├── ui/
│   ├── main_window.py           # メインウィンドウ・4タブ管理
│   ├── master/
│   │   ├── employee_tab.py      # 職員マスタ CRUD + 担当シフト設定
│   │   ├── shift_tab.py         # シフト種別マスタ CRUD
│   │   └── history_import.py    # 過去履歴インポート（Excel 読み込み）
│   ├── request_view.py          # 希望シフト入力グリッド（QTableWidget）
│   ├── run_view.py              # 自動作成実行・ログ表示（QThread 連携）
│   └── result/
│       ├── monthly_grid.py      # 4-A 月次シフト表（色付きセル・違反ハイライト）
│       ├── han_view.py          # 4-B 班別配当表（Excel シート1-4フォーマット・週タブ切替）
│       ├── adjust_panel.py      # 4-C 手動調整パネル（制約リアルタイムチェック）
│       ├── history_view.py      # 4-D 修正履歴・全件取り消し
│       └── export.py            # 印刷・Excel・CSV・PDF 出力
├── core/
│   ├── db.py                    # SQLite 接続・スキーマ初期化・CRUD
│   ├── scheduler.py             # PuLP 最適化エンジン（def_scheduling.py 移植）
│   ├── constraints.py           # employee_constraints からハード制約を生成
│   └── history_mapper.py        # 前年履歴→当月日付マッピングロジック
├── utils/
│   ├── excel_import.py          # Excel → DB インポート（初期移行用）
│   └── excel_export.py          # DB → Excel / CSV / PDF エクスポート
├── data/
│   └── shift_scheduler.db       # SQLite（初回起動時に自動生成）
├── assets/
│   └── shift_colors.json        # シフトコード→表示色マッピング
├── requirements.txt
└── shift_scheduler.spec         # PyInstaller 設定
```

---

## requirements.txt

```
PyQt6>=6.6
pulp>=2.8
pandas>=2.0
openpyxl>=3.1
holidays>=0.46
pyinstaller>=6.0
```

---

## 開発フェーズ

### フェーズ1：データ層（最優先）

1. `core/db.py` — SQLite スキーマ作成・全テーブルの CRUD 関数
2. `utils/excel_import.py` — 既存 `shift_scheduler.xlsx` から DB への初回インポート  
   （職員マスタ・シフト種別・過去履歴・希望シフトをすべて DB に移行）
3. `core/scheduler.py` — `def_scheduling.py` をクラス化・PuLP 移植
4. `core/constraints.py` — `employee_constraints` テーブルからハード制約を動的生成
5. CLI 動作確認：`python -m core.scheduler --year 2026 --month 2`

### フェーズ2：UI 骨格

6. `ui/main_window.py` — メインウィンドウ・4タブの骨格
7. `ui/request_view.py` — 希望シフト入力グリッド（QTableWidget ベース）
8. `ui/run_view.py` — 実行ボタン・ログ表示・QThread でバックグラウンド実行
9. `ui/result/monthly_grid.py` — 月次シフト表グリッド（色付きセル）

### フェーズ3：マスタ管理 UI

10. `ui/master/employee_tab.py` — 職員一覧・追加/編集ダイアログ（担当シフクのチェックボックス含む）
11. `ui/master/shift_tab.py` — シフト種別マスタの編集
12. `ui/master/history_import.py` — 過去履歴のインポート UI

### フェーズ4：確認・調整 UI

13. `ui/result/monthly_grid.py` — 月次グリッド（違反ハイライト・修正済みセル紫枠）
14. `ui/result/han_view.py` — 班別ビュー（日付ナビ・シフト種別カード・追加/変更/削除）
15. `ui/result/adjust_panel.py` — 手動調整パネル（制約リアルタイムチェック）
16. `ui/result/history_view.py` — 修正履歴・全件取り消し

### フェーズ5：出力・仕上げ

17. `utils/excel_export.py` — Excel / CSV / PDF 出力
18. PyInstaller ビルド（CBC バイナリ同梱・Windows exe）

---

## 既知の注意点・引き継ぎ事項

1. **Excel は入力 UI として使わない**  
   既存コードは全入力を Excel に依存しているが、本アプリではすべて SQLite に持ち、
   UI から直接 CRUD する。Excel は「初回データ移行」と「印刷・提出用出力」にのみ使う。

2. **xlwings は使わない**  
   PyInstaller での配布に問題があるため `openpyxl` で代替。
   出力時は `生データ` シートのみ書き込み、`シフト` シートの XLOOKUP 数式は自動反映。

3. **希望シフト提出フローの変更**  
   従来は職員が Excel に記入して管理者に渡していたが、本アプリでは管理者がグリッドに
   直接入力する。将来的に Web フォームで職員自身が提出する拡張も、
   `shift_submitted` テーブル設計を変えずに対応可能。

4. **CBC ソルバーのパス**  
   PyInstaller ビルド時、CBC バイナリ（`cbc.exe`）を同梱する必要がある。
   `resource_path("cbc")` で解決すること。

5. **夜勤翌日の宿直制約 (Big-M)**  
   ```python
   problem += shift[d+1][e][21] - 1 >= -99 * (1 - shift[d][e][20])
   ```
   「Y に入った翌日は B2（宿直明け）に強制配置」のビッグM制約。
   最終日（`d = last_day`）はループ外のため注意。

6. **高井・小幡の同日勤務禁止（現行コードに未実装）**  
   employee_id=14（高井）と employee_id=22（小幡）に対して追加実装が必要：
   ```python
   for d in list_day:
       problem += lpSum(shift[d][14][s] for s in list_shift) + \
                  lpSum(shift[d][22][s] for s in list_shift) <= 1
   ```
   `employee_constraints` テーブルの `constraint_type='no_paired_with'` から動的生成する。

7. **スコア配列のメモリ改善**  
   現行コードは 4 重辞書全初期化（約150万エントリ）。
   `pd.DataFrame` で疎行列として保持し、存在する (day, emp, shift) のみを持つ。

8. **職員略称の名寄せ（重要）**
   班配当表では略称（「涛川」「石井あ」等）が使われており、`employee_master` の正式名と
   突合して正確に名寄せする必要がある。初回インポート時に以下を確認すること：
   - 「石井あ」「石井淳(ID18)」など同姓の別人が存在する
   - 「鈴木ゆ（鈴木優子ID21）」「鈴木き（鈴木君）」など同姓別人
   - 「斉藤雅(ID16)」「斉藤正子(ID72)」「斎藤まゆみ(ID73)」など類似名
   `excel_import.py` に略称→正式名のマッピング辞書を必ず実装する。

9. **実績から読み取れる1ヶ月あたりの夜勤回数**
   R8（令和8年2月）の実績: Y=3〜4回/人/月が標準。大庭(ID19)は出勤日数が多い傾向。
   最大出勤日数の上限（現行23日）はこの実績に概ね合致している。

10. **自動スケジューリング対象は shift_id 1〜21 のみ**
   `scheduler.py` の `list_shift` は `shift_master` テーブルから
   `shift_id <= 21` の行だけを取得すること。事務所・医務・世話人等を
   誤って最適化変数に含めると計算量が無駄に増え、制約も壊れる。
   ```python
   list_shift = df_shift_master[df_shift_master['shift_id'] <= 21]['shift_id'].tolist()
   ```

9. **班別配当表の列オフセット差異**
   シート「1」〜「3」と「4」では列のオフセットが異なる（シート4は宿直列がなく2つ左ずれ）。
   `han_view.py` では週番号に応じてマッピング辞書を切り替えること：
   - 週1〜3: `COL_MAP = {4:'戸外A', 5:'戸外B', ..., 24:'宿直B2', 25:'事務所', 27:'医務', 28:'世話人'}`
   - 週4:    `COL_MAP = {2:'戸外A', 3:'戸外B', ..., 21:'夜勤Y', 22:'事務所', 24:'医務', 25:'世話人'}`
   （宿直列は存在しない）

10. **QThread 必須**  
   PyQt6 での最適化実行は必ず `QThread` + `pyqtSignal` で行うこと。
   メインスレッドでブロッキング処理を実行するとウィンドウがフリーズする。

---

## データベース設計方針

### 配置場所

SQLite の DB ファイルは**アプリと同じ PC のローカルに配置**する。サーバー・クラウド不要。

```
C:\Users\<ユーザー名>\AppData\Local\ShiftScheduler\
└── shift_scheduler.db       ← DB ファイル本体
```

`AppData\Local` に置く理由：
- exe と同じフォルダに置くと、`Program Files` インストール時に書き込み権限エラーになる
- `AppData\Local` はユーザーごとの書き込み可能領域で、Windows の慣例に沿っている

`core/db.py` の接続処理：
```python
from pathlib import Path
import os

def get_db_path() -> Path:
    app_data = Path(os.getenv("LOCALAPPDATA", Path.home())) / "ShiftScheduler"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "shift_scheduler.db"
```

### バックアップ

管理者が手動でバックアップできるよう、アプリ内に**バックアップ機能**を実装する。

```
設定メニュー → [DB をバックアップ]
  → ファイル保存ダイアログ
  → shift_scheduler_20260201.db として任意の場所に保存
```

また、**起動時に直近7世代を自動バックアップ**する：

```
AppData\Local\ShiftSchedulerackup\
├── shift_scheduler_20260401.db
├── shift_scheduler_20260331.db
└── ...（7世代まで保持、古いものは自動削除）
```

`core/db.py` の起動時バックアップ処理：
```python
import shutil
from datetime import date

def auto_backup(db_path: Path):
    backup_dir = db_path.parent / "backup"
    backup_dir.mkdir(exist_ok=True)
    dst = backup_dir / f"shift_scheduler_{date.today().strftime('%Y%m%d')}.db"
    if not dst.exists():
        shutil.copy2(db_path, dst)
    # 7世代超過分を削除
    backups = sorted(backup_dir.glob("*.db"))
    for old in backups[:-7]:
        old.unlink()
```

### 将来のオンライン化に備えた設計方針

現在は1台・1人運用だが、将来「複数担当者が使いたい」「職員が Web で希望を提出したい」
という要件が生じた場合の拡張ポイントを以下に示す。**現時点では実装不要。**

| 将来要件 | 対応方針 |
|----------|----------|
| 複数 PC から同一 DB を参照 | SQLite ファイルを NAS や OneDrive に移動するだけで対応可。`get_db_path()` の返す場所を設定画面から変更できるようにしておく |
| 同時書き込みが必要 | SQLite → PostgreSQL に移行。`core/db.py` の接続文字列を変えるだけで済むよう、SQL を UI 層に直書きしない |
| 職員が Web でシフト希望提出 | `shift_submitted` テーブルの設計はそのまま使える。Web フォームからこのテーブルに書き込む API を別途作成する |

このため、DB アクセスは必ず `core/db.py` の関数経由で行い、
SQL を UI 層に直書きしないこと（将来の DB 移行を容易にするため）。

---

## 動作確認用サンプルデータ

初回起動時に `utils/excel_import.py` を使って以下を DB へインポート：

| ファイル | 用途 | インポート内容 |
|---------|------|-------------|
| `shift_scheduler.xlsx` | 旧マスタ・履歴 | シフト種別マスタ・過去履歴（2025年度） |
| `シフト_R8_2.xlsx` | 最新シフト実績（令和8年2月） | 職員マスタ確定・2026年2月の実績履歴として使用 |
| `シフト_R7_4〜11.xlsx` | 月次シフト表8ヶ月分 | 職員別日次シフト・スコア体系の根拠データ |
| `活動班配当表_２月_.xlsx` | 班配当表実績 | 班配当表フォーマットの確認・手動列データの参考 |
| `活動班配当表_4〜11月_.xlsx` | 班配当表8ヶ月分 | 夜勤ペア実績・配置パターン分析に使用 |

- 対象年月: 2026年3月（次月）の自動作成に向けた初期データ
- 自動スケジューリング対象職員: ID 7〜23 + 班配当表確認済み追加職員（計約30名）
- 手動列職員: ID 50〜86（第一工房・ナカポツ・どんちゃん等）

**初回インポートで必ず実施すること**:
1. 略称→正式名マッピング辞書を `excel_import.py` に定義
2. 班配当表に登場する略称職員の正式名・IDを確定
3. `employee_shift_capability` テーブルに R8 実績から各職員の担当可能シフトを登録
4. `employee_constraints` テーブルに高井・小幡の同日禁止ルールを登録
---

## Claude Code への引き渡し手順

このファイル（CLAUDE.md）をプロジェクトルートに置くと Claude Code が自動で読み込む。
以下のフェーズ順に指示を出すこと。**1フェーズ完了→git commit** を必ず徹底させる。

### 作業開始時の初回指示

```
CLAUDE.mdを読んで全体設計を把握してください。
不明点があれば質問してください。
把握できたら「理解しました」と概要を要約して報告し、
フェーズ1の作業を開始してください。
```

---

### フェーズ1 — DB・データ基盤

**目標**: SQLiteスキーマ作成・CRUD・初回Excelインポートの動作確認

```
フェーズ1を開始してください。

【実装対象】
- core/db.py
  - CLAUDE.mdのSQLiteスキーマを全テーブル作成
  - CRUD関数（get/insert/update/delete）を各テーブルに実装
  - get_db_path() と auto_backup()（起動時7世代）を実装
- utils/excel_import.py
  - シフト_R8_2.xlsx から employee_master を初回インポート
  - 略称→正式名マッピング辞書を必ず定義すること
    （「石井あ」「鈴木ゆ」「末𠮷」等の異体字・略称に対応）
  - unicodedata.normalize('NFKC', name) を名寄せ前に適用
  - 活動班配当表から employee_shift_capability を登録
  - employee_constraints に高井(ID13)・小幡(ID20)の同日禁止を登録

【確認手順】
python utils/excel_import.py --file シフト_R8_2.xlsx --year 2026 --month 2
を実行し、エラーなく完了することを確認してください。
名寄せ失敗があれば修正して再実行してください。

完了したら git commit して報告してください。
```

**詰まったときの追加指示**:
```
# 異体字「末𠮷」が正規化されない場合
unicodedata.normalize の前に
name = name.replace('\U00020B9F', '吉') を追加してください。

# インポート後に重複レコードが入る場合
INSERT OR REPLACE INTO を使い、
UNIQUE制約のあるカラムを確認してください。
```

---

### フェーズ2 — 最適化エンジン

**目標**: PuLP による自動スケジューリングの CLI 動作確認

```
フェーズ2を開始してください。

【実装対象】
- core/scheduler.py
  - CLAUDE.mdの「最適化エンジン仕様」に従って実装
  - gap変数は使わず、スコアを直接 lpSum(score * shift) で目的関数に組み込む
  - ハード制約8項目をすべて実装
  - ソフト制約（希望未充足・B2翌日出勤・夜勤インターバル）はペナルティ変数で実装
  - list_shift は shift_id <= 21 のみ（事務所・医務等を含めないこと）
  - タイムアウトは120秒、暫定解があれば採用
- core/constraints.py
  - employee_constraints テーブルから同日禁止ペアを動的生成
- tests/test_scheduler.py
  - 2026年3月の小規模テストデータでユニットテスト作成
  - 夜勤2名以上・Y翌日B2・B2翌日休みの3制約は必ずテストすること

【確認手順】
python -m pytest tests/test_scheduler.py -v
を実行し、全テストがパスすることを確認してください。

完了したら git commit して報告してください。
```

**詰まったときの追加指示**:
```
# INFEASIBLE になる場合
制約をひとつずつ外して原因を特定してください。
まず希望シフト制約（slack変数）を確認し、
次にharder制約（夜勤2名以上）を確認してください。

# CBCソルバーが見つからない場合
solver = PULP_CBC_CMD(path=resource_path('cbc'), timeLimit=120)
として resource_path() でバイナリを指定してください。

# 計算が120秒でも終わらない場合
list_employee を自動スケジューリング対象（ID7〜23近辺）のみに
絞り込んでいるか確認してください。
```

---

### フェーズ3 — UI骨格

**目標**: PyQt6で4タブのウィンドウが起動・切り替えできる状態

```
フェーズ3を開始してください。

【実装対象】
- main.py
  - QApplication + MainWindow の起動
  - core/db.py の auto_backup() を起動時に呼ぶ
- ui/main_window.py
  - QTabWidget で4タブ（マスタ管理・希望入力・自動作成・確認調整）
  - タブ切り替えが動けばよい（中身は後のフェーズで実装）
  - ウィンドウタイトルは「シフト自動作成システム」
  - 最小サイズ: 1280×800

【確認手順】
python main.py
でウィンドウが起動し、4タブが切り替えられることを確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ4 — 希望シフト入力グリッド

**目標**: 職員×日付のグリッドで希望シフトを入力・保存できる

```
フェーズ4を開始してください。

【実装対象】
- ui/request_view.py
  - QTableWidget で職員×日付グリッド
  - セルクリック → ドロップダウン（Y/B1/C1/C2/DG/休暇/空白）
  - 土日列を薄青・薄赤で着色
  - 日本の祝日（holidays ライブラリ）を薄赤で着色
  - 年月セレクタで表示月を切り替え
  - [保存] → shift_submitted テーブルに UPSERT
  - [クリア] → 選択中のセルを空白に戻す

【確認手順】
タブ「希望シフト入力」で2026年3月を表示し、
いくつかセルを入力して保存後、再度開いて値が残っていることを確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ5 — 自動作成実行タブ

**目標**: ボタン1つで最適化が走り、進捗とログが表示される

```
フェーズ5を開始してください。

【実装対象】
- ui/run_view.py
  - 年月セレクタ
  - [自動作成実行] ボタン
  - QThread + pyqtSignal でバックグラウンド実行（UIをブロックしない）
  - QTextEdit にリアルタイムでログを流す
  - 進捗バー（QProgressBar）: 制約構築中/ソルバー実行中/結果保存中
  - 完了後: 「最適解が得られました」or「暫定解で採用しました（制限時間超過）」を表示
  - エラー時: エラー内容をログに表示し、ポップアップで通知

【確認手順】
2026年3月で実行し、120秒以内に結果が shift_result テーブルに保存されることを確認。
QThread がメインスレッドをブロックしていないことも確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ6 — 月次シフト表グリッド（4-A）

**目標**: 自動計算結果を職員×日付グリッドで確認・セル編集できる

```
フェーズ6を開始してください。

【実装対象】
- ui/result/monthly_grid.py
  - shift_result + shift_manual を合わせて職員×日付で表示
  - シフト種別ごとに背景色（Y=紫・B=青・C=緑・B2=薄橙・DG=黄・休=灰）
  - 手動修正済みセル: 紫枠（shift_result_log に記録あり）
  - 制約違反セル: 赤背景+赤枠（夜勤2名未満・同日重複等をリアルタイムチェック）
  - フッター行: 日付ごとの夜勤配置人数（2名未満は赤表示）
  - タイトルバー: 「手動修正N件」「警告N件」バッジをリアルタイム更新
  - セルクリック → 手動調整パネル（ui/result/adjust_panel.py）を開く

【確認手順】
2026年3月の計算結果を表示し、
セルをクリックして手動調整パネルが開くことを確認してください。
夜勤2名未満の日があれば赤でハイライトされることも確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ7 — 班別配当表ビュー（4-B）

**目標**: ExcelシートとまったくExcelシート「1」〜「4」と同じ列構造で表示される

```
フェーズ7を開始してください。

【実装対象】
- ui/result/han_view.py
  - 週タブ（第1〜4週）で切り替え
  - 各週はQTableWidget で Excel のシート「1」〜「4」と同一の列構造を再現
    - シート「1」〜「3」: col2〜21（戸外班A〜夜勤Y・宿直B2あり）
    - シート「4」: col2〜21（宿直列なし・2列左ずれ）
  - 各日付は3サブ行で構成
  - 自動配置セル（shift_result）: クリックで調整パネルを開く
  - 手動入力セル（shift_manual）: クリックでインライン編集（テキスト直接入力）
  - 手動修正済みセル: 紫枠
  - 土日列: 薄着色（日=薄赤・土=薄青）
  - 週タブの日付範囲は calendar.monthrange() で動的計算

【注意事項】
CLAUDE.mdの「4-B 班別配当表ビュー」の列マッピングを必ず参照すること。
シート「4」は宿直列がなく列オフセットが異なる点に注意。

【確認手順】
活動班配当表_２月_.xlsx を目視で参照しながら、
アプリの表示が Excel と同じ列構造になっていることを確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ8 — 手動調整パネル（4-C）

**目標**: セルをクリックして変更前に制約チェックが走り、問題なければ保存できる

```
フェーズ8を開始してください。

【実装対象】
- ui/result/adjust_panel.py
  - 修正対象（職員・日付・現在のシフト）を表示
  - シフト選択ドロップダウン
  - [変更後] を選択した瞬間に制約をリアルタイムチェック（PuLPは使わずPythonで軽量検証）
    チェック項目:
    - 1日1勤務（同日の他シフトとの重複）
    - 担当可能シフト（employee_shift_capability テーブル）
    - Y翌日はB2自動設定（確認メッセージとして表示）
    - 月間出勤数（上限23日以内）
    - 夜勤配置人数（変更後に2名以上を維持）
    - 高井・小幡の同日禁止
  - 制約違反がある場合: 該当行を赤表示・[適用] ボタンを無効化
  - [適用]: shift_result を更新 + shift_result_log に記録
  - [キャンセル]: 変更破棄

【確認手順】
月次グリッドのセルをクリックして調整パネルを開き、
制約違反になるシフトを選ぶとボタンが無効化されることを確認してください。
問題なければ適用でき、月次グリッドに紫枠で反映されることを確認してください。

完了したら git commit して報告してください。
```

---

### フェーズ9 — 修正履歴・マスタ管理（4-D・タブ1）

**目標**: 修正履歴の閲覧・全件取り消し、職員マスタのCRUD

```
フェーズ9を開始してください。

【実装対象】
- ui/result/history_view.py
  - shift_result_log から修正履歴を一覧表示
  - [すべて取り消し]: shift_result を最新の自動計算結果に巻き戻す
    （shift_result_log の auto_calc エントリ時点の状態に戻す）
  - 日時・変更内容・種別（手動/自動）を表示
- ui/master/employee_tab.py
  - employee_master の CRUD テーブル
  - 担当可能シフトをチェックボックスで編集
  - 同日禁止ペアを employee_constraints から管理
- ui/master/shift_tab.py
  - shift_master の一覧表示（編集は基本不要だが参照できること）

【確認手順】
手動修正を3件行った後、「すべて取り消し」で自動計算結果に戻ることを確認。
職員マスタで担当可能シフトを変更後、スケジューリングに反映されることを確認。

完了したら git commit して報告してください。
```

---

### フェーズ10 — 出力・ビルド

**目標**: Excel/PDF出力が動き、Windows exe が配布できる

```
フェーズ10を開始してください。

【実装対象】
- utils/excel_export.py
  - openpyxl で活動班配当表フォーマット（シート「1」〜「4」）を再現して出力
  - 月次シフト表（職員×日付）も別シートで出力
  - セル色はシフト種別に対応した背景色を設定
- ui/result/export.py
  - [Excel出力] [CSV出力] [PDF出力] [印刷] ボタン
  - PDF出力は QPrinter（A3横向き）
  - ファイル保存ダイアログで保存先を指定
- shift_scheduler.spec（PyInstaller設定）
  - CBC バイナリを同梱
  - assets/shift_colors.json を同梱
  - onefile モードでビルド

【確認手順】
python utils/excel_export.py --year 2026 --month 3
で Excel が出力され、活動班配当表と同じ列構造になっていることを確認。
pyinstaller shift_scheduler.spec でビルドし、
dist/shift_scheduler.exe が別 PC でも起動することを確認。

完了したら git commit して報告してください。
```

---

### 全フェーズ共通の注意事項

Claude Code に常に意識させること。指示の冒頭に付け加えると効果的。

```
作業にあたって以下を守ってください:
- CLAUDE.mdの仕様から外れる場合は必ず事前に確認すること
- SQL は必ず core/db.py 経由で実行し、UI層に直書きしないこと
- list_shift は shift_id <= 21 のみ（事務所・医務等を含めない）
- QThread を使わず UI 操作する処理は書かないこと
- デバッグ用 print は logging.debug() に置き換えること
- 各ファイルの先頭にモジュールの役割をdocstringで記載すること
```

### 問題が起きたときの汎用指示

```
# コンテキストが切れて再開するとき
CLAUDE.mdを読んで現在の実装状況を確認してください。
git log --oneline -10 で進捗を確認し、
次に実装すべきフェーズを教えてください。

# 想定外の挙動が起きたとき
[具体的な症状] が発生しています。
原因を調査して修正してください。
修正前に原因の仮説を教えてください。

# 設計の変更が必要になったとき
[変更内容] を変更したいです。
影響範囲を洗い出してから実装してください。
CLAUDE.mdも合わせて更新してください。
```
