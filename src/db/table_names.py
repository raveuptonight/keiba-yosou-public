"""
JRA-VAN mykeibadb テーブル名マッピング

PostgreSQL接続後、実際のテーブル名を確認してこのファイルを更新してください。

確認コマンド:
    psql -U postgres -d keiba_db -c "\dt"

仮定している命名規則:
- データ種別コード（RA, SE等）をベースに英語名を使用
- 複数形で統一（races, horses等）
"""

from typing import Final

# =============================================================================
# テーブル名定義（仮置き）
# =============================================================================

# レース関連
TABLE_RACE: Final[str] = "race"  # RA: レース詳細
TABLE_UMA_RACE: Final[str] = "uma_race"  # SE: 馬毎レース情報

# 馬マスタ
TABLE_UMA: Final[str] = "uma"  # UM: 競走馬マスタ
TABLE_SANKU: Final[str] = "sanku"  # SK: 産駒マスタ（3代血統）
TABLE_HANSYOKU_MEIGARA: Final[str] = "hansyoku_meigara"  # HN: 繁殖馬マスタ

# 調教データ
TABLE_HANRO_CHOKYO: Final[str] = "hanro_chokyo"  # HC: 坂路調教
TABLE_WOOD_CHOKYO: Final[str] = "wood_chokyo"  # WC: ウッド調教

# 人物マスタ
TABLE_KISYU: Final[str] = "kisyu"  # KS: 騎手マスタ
TABLE_CHOKYOSI: Final[str] = "chokyosi"  # CH: 調教師マスタ

# 統計データ
TABLE_SHUTUBA_CHAKUDO: Final[str] = "shutuba_chakudo"  # CK: 出走別着度数

# 払戻・オッズ
TABLE_HARAIMODOSI: Final[str] = "haraimodosi"  # HR: 払戻
TABLE_ODDS_TANFUKU: Final[str] = "odds_tanfuku"  # O1: 単勝・複勝オッズ
TABLE_ODDS_WAKUREN: Final[str] = "odds_wakuren"  # O2: 枠連オッズ
TABLE_ODDS_UMAREN: Final[str] = "odds_umaren"  # O3: 馬連オッズ
TABLE_ODDS_WIDE: Final[str] = "odds_wide"  # O4: ワイドオッズ
TABLE_ODDS_UMATAN: Final[str] = "odds_umatan"  # O5: 馬単オッズ
TABLE_ODDS_SANREN: Final[str] = "odds_sanren"  # O6: 3連複・3連単オッズ

# スケジュール・イベント
TABLE_YOSOKU_SCHEDULE: Final[str] = "yosoku_schedule"  # YS: 開催スケジュール
TABLE_BABA_HENKO: Final[str] = "baba_henko"  # WE: 天候・馬場状態変更
TABLE_HASSO_JIKOKU: Final[str] = "hasso_jikoku"  # AV: 発走時刻変更
TABLE_KISYU_HENKO: Final[str] = "kisyu_henko"  # JC: 騎手変更
TABLE_FUTAN_HENKO: Final[str] = "futan_henko"  # TC: 負担重量変更
TABLE_COURSE_HENKO: Final[str] = "course_henko"  # CC: コース変更

# マスタ情報
TABLE_KEITOU_INFO: Final[str] = "keitou_info"  # BT: 系統情報
TABLE_COURSE_INFO: Final[str] = "course_info"  # CS: コース情報
TABLE_RECORD_MEIGARA: Final[str] = "record_meigara"  # RC: レコードマスタ

# 特別登録
TABLE_TOKUBETSU_TOROKU: Final[str] = "tokubetsu_toroku"  # TK: 特別登録

# =============================================================================
# カラム名定義（頻出フィールド）
# =============================================================================

# 主キー・外部キー
COL_RACE_ID: Final[str] = "race_id"
COL_KETTONUM: Final[str] = "kettonum"  # 血統登録番号
COL_UMABAN: Final[str] = "umaban"  # 馬番

# レース構成要素
COL_KAISAI_YEAR: Final[str] = "kaisai_year"  # 開催年
COL_KAISAI_MONTHDAY: Final[str] = "kaisai_monthday"  # 開催月日（MMDD）
COL_JYOCD: Final[str] = "jyocd"  # 競馬場コード
COL_KAISAI_KAI: Final[str] = "kaisai_kai"  # 開催回
COL_KAISAI_NICHIME: Final[str] = "kaisai_nichime"  # 開催日目
COL_RACE_NUM: Final[str] = "race_num"  # レース番号

# データ種別
COL_DATA_KUBUN: Final[str] = "data_kubun"  # データ区分（7=確定）

# レース情報
COL_RACE_NAME: Final[str] = "race_name"  # レース名
COL_GRADE_CD: Final[str] = "grade_cd"  # グレードコード
COL_TRACK_CD: Final[str] = "track_cd"  # トラックコード
COL_KYORI: Final[str] = "kyori"  # 距離

# 馬情報
COL_BAMEI: Final[str] = "bamei"  # 馬名
COL_SEX: Final[str] = "sex"  # 性別
COL_KEIROCODE: Final[str] = "keirocode"  # 毛色コード

# 成績
COL_KAKUTEI_CHAKUJUN: Final[str] = "kakutei_chakujun"  # 確定着順
COL_着順: Final[str] = "kakutei_chakujun"  # 確定着順（エイリアス）
COL_TIME: Final[str] = "time"  # タイム
COL_BATAIJU: Final[str] = "bataiju"  # 馬体重
COL_KINRYO: Final[str] = "kinryo"  # 斤量
COL_RACE_DATE: Final[str] = "race_date"  # レース日

# 騎手・調教師
COL_KISYUCODE: Final[str] = "kisyucode"  # 騎手コード
COL_CHOKYOSICODE: Final[str] = "chokyosicode"  # 調教師コード
COL_KISYU_NAME: Final[str] = "kisyu_name"  # 騎手名
COL_TRAINER_NAME: Final[str] = "chokyosi_name"  # 調教師名（エイリアス）
COL_CHOKYOSI_NAME: Final[str] = "chokyosi_name"  # 調教師名

# 血統
COL_SANDAI_KETTO: Final[str] = "sandai_ketto"  # 3代血統配列
COL_HANSYOKU_NUM: Final[str] = "hansyoku_num"  # 繁殖登録番号
COL_HANSYOKUBA_NAME: Final[str] = "hansyokuba_name"  # 繁殖馬名

# 調教
COL_CHOKYO_DATE: Final[str] = "chokyo_date"  # 調教日
COL_TIME_4F: Final[str] = "time_4f"  # 4ハロンタイム
COL_TIME_3F: Final[str] = "time_3f"  # 3ハロンタイム

# =============================================================================
# データ区分定数
# =============================================================================

DATA_KUBUN_KAKUTEI: Final[str] = "7"  # 確定データ
DATA_KUBUN_SOKUHO: Final[str] = "0"  # 速報データ

# =============================================================================
# グレードコード定数
# =============================================================================

GRADE_G1: Final[str] = "A"
GRADE_G2: Final[str] = "B"
GRADE_G3: Final[str] = "C"
GRADE_LISTED: Final[str] = "D"
GRADE_OPEN: Final[str] = "E"
GRADE_1600_BAN: Final[str] = "F"
GRADE_1000_BAN: Final[str] = "G"
GRADE_500_BAN: Final[str] = "H"
GRADE_UNDER_500: Final[str] = "I"
GRADE_SHINSHIN: Final[str] = "J"

# =============================================================================
# ユーティリティ関数
# =============================================================================

def get_all_table_names() -> dict[str, str]:
    """全テーブル名のマッピングを返す"""
    return {
        "race": TABLE_RACE,
        "uma_race": TABLE_UMA_RACE,
        "uma": TABLE_UMA,
        "sanku": TABLE_SANKU,
        "hansyoku_meigara": TABLE_HANSYOKU_MEIGARA,
        "hanro_chokyo": TABLE_HANRO_CHOKYO,
        "wood_chokyo": TABLE_WOOD_CHOKYO,
        "kisyu": TABLE_KISYU,
        "chokyosi": TABLE_CHOKYOSI,
        "shutuba_chakudo": TABLE_SHUTUBA_CHAKUDO,
        "haraimodosi": TABLE_HARAIMODOSI,
        "odds_tanfuku": TABLE_ODDS_TANFUKU,
        "odds_wakuren": TABLE_ODDS_WAKUREN,
        "odds_umaren": TABLE_ODDS_UMAREN,
        "odds_wide": TABLE_ODDS_WIDE,
        "odds_umatan": TABLE_ODDS_UMATAN,
        "odds_sanren": TABLE_ODDS_SANREN,
        "yosoku_schedule": TABLE_YOSOKU_SCHEDULE,
        "baba_henko": TABLE_BABA_HENKO,
        "hasso_jikoku": TABLE_HASSO_JIKOKU,
        "kisyu_henko": TABLE_KISYU_HENKO,
        "futan_henko": TABLE_FUTAN_HENKO,
        "course_henko": TABLE_COURSE_HENKO,
        "keitou_info": TABLE_KEITOU_INFO,
        "course_info": TABLE_COURSE_INFO,
        "record_meigara": TABLE_RECORD_MEIGARA,
        "tokubetsu_toroku": TABLE_TOKUBETSU_TOROKU,
    }


def verify_table_names_sql() -> str:
    """
    実際のテーブル名を確認するためのSQLを生成

    Returns:
        PostgreSQLで実行可能なテーブル一覧取得SQL
    """
    return """
-- 現在のデータベース内の全テーブルを表示
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
    """
