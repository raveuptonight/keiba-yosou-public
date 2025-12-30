"""
JRA-VAN mykeibadb テーブル名マッピング

mykeibadbで生成された実際のテーブル名を定義。
2024/12/30 データ投入完了後に確認・更新済み。
"""

from typing import Final

# =============================================================================
# テーブル名定義（mykeibadb実テーブル名）
# =============================================================================

# レース関連
TABLE_RACE: Final[str] = "race_shosai"  # RA: レース詳細
TABLE_UMA_RACE: Final[str] = "umagoto_race_joho"  # SE: 馬毎レース情報

# 馬マスタ
TABLE_UMA: Final[str] = "kyosoba_master2"  # UM: 競走馬マスタ
TABLE_SANKU: Final[str] = "sanku_master2"  # SK: 産駒マスタ（3代血統）
TABLE_HANSYOKU: Final[str] = "hanshokuba_master2"  # HN: 繁殖馬マスタ

# 調教データ
TABLE_HANRO_CHOKYO: Final[str] = "hanro_chokyo"  # HC: 坂路調教
TABLE_WOOD_CHOKYO: Final[str] = "woodchip_chokyo"  # WC: ウッドチップ調教

# 人物マスタ
TABLE_KISYU: Final[str] = "kishu_master"  # KS: 騎手マスタ
TABLE_CHOKYOSI: Final[str] = "chokyoshi_master"  # CH: 調教師マスタ

# 出走別着度数（統計）
TABLE_SHUTUBA_KEIBAJO: Final[str] = "shussobetsu_keibajo"  # 競馬場別
TABLE_SHUTUBA_KYORI: Final[str] = "shussobetsu_kyori"  # 距離別
TABLE_SHUTUBA_BABA: Final[str] = "shussobetsu_baba"  # 馬場別
TABLE_SHUTUBA_KISHU: Final[str] = "shussobetsu_kishu"  # 騎手別
TABLE_SHUTUBA_CHOKYOSI: Final[str] = "shussobetsu_chokyoshi"  # 調教師別
TABLE_SHUTUBA_BANUSHI: Final[str] = "shussobetsu_banushi"  # 馬主別
TABLE_SHUTUBA_SEISANSHA: Final[str] = "shussobetsu_seisansha2"  # 生産者別

# 払戻・オッズ
TABLE_HARAIMODOSI: Final[str] = "haraimodoshi"  # HR: 払戻
TABLE_ODDS_TANSHO: Final[str] = "odds1_tansho"  # O1: 単勝オッズ
TABLE_ODDS_FUKUSHO: Final[str] = "odds1_fukusho"  # O1: 複勝オッズ
TABLE_ODDS_WAKUREN: Final[str] = "odds1_wakuren"  # O1: 枠連オッズ
TABLE_ODDS_UMAREN: Final[str] = "odds2_umaren"  # O2: 馬連オッズ
TABLE_ODDS_WIDE: Final[str] = "odds3_wide"  # O3: ワイドオッズ
TABLE_ODDS_UMATAN: Final[str] = "odds4_umatan"  # O4: 馬単オッズ
TABLE_ODDS_SANRENPUKU: Final[str] = "odds5_sanrenpuku"  # O5: 3連複オッズ
TABLE_ODDS_SANRENTAN: Final[str] = "odds6_sanrentan"  # O6: 3連単オッズ

# スケジュール・イベント
TABLE_KAISAI_SCHEDULE: Final[str] = "kaisai_schedule"  # 開催スケジュール
TABLE_TENKO_BABA: Final[str] = "tenko_baba_jotai"  # 天候・馬場状態
TABLE_HASSO_JIKOKU: Final[str] = "hassojikoku_henko"  # 発走時刻変更
TABLE_KISYU_HENKO: Final[str] = "kishu_henko"  # 騎手変更
TABLE_COURSE_HENKO: Final[str] = "course_henko"  # コース変更

# マスタ情報
TABLE_KEITO_INFO: Final[str] = "keito_joho2"  # BT: 系統情報
TABLE_COURSE_INFO: Final[str] = "course_joho"  # CS: コース情報
TABLE_RECORD_MASTER: Final[str] = "record_master"  # RC: レコードマスタ
TABLE_KEIBAJO_CODE: Final[str] = "keibajo_code"  # 競馬場コード

# 特別登録
TABLE_TOKUBETSU_TOROKU: Final[str] = "tokubetsu_torokuba"  # TK: 特別登録馬

# その他マスタ
TABLE_BANUSHI: Final[str] = "banushi_master"  # 馬主マスタ
TABLE_SEISANSHA: Final[str] = "seisansha_master2"  # 生産者マスタ

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
    """全テーブル名のマッピングを返す（論理名 -> 物理名）"""
    return {
        "race": TABLE_RACE,
        "uma_race": TABLE_UMA_RACE,
        "uma": TABLE_UMA,
        "sanku": TABLE_SANKU,
        "hansyoku": TABLE_HANSYOKU,
        "hanro_chokyo": TABLE_HANRO_CHOKYO,
        "wood_chokyo": TABLE_WOOD_CHOKYO,
        "kisyu": TABLE_KISYU,
        "chokyosi": TABLE_CHOKYOSI,
        "shutuba_keibajo": TABLE_SHUTUBA_KEIBAJO,
        "shutuba_kyori": TABLE_SHUTUBA_KYORI,
        "shutuba_baba": TABLE_SHUTUBA_BABA,
        "shutuba_kishu": TABLE_SHUTUBA_KISHU,
        "shutuba_chokyosi": TABLE_SHUTUBA_CHOKYOSI,
        "shutuba_banushi": TABLE_SHUTUBA_BANUSHI,
        "shutuba_seisansha": TABLE_SHUTUBA_SEISANSHA,
        "haraimodosi": TABLE_HARAIMODOSI,
        "odds_tansho": TABLE_ODDS_TANSHO,
        "odds_fukusho": TABLE_ODDS_FUKUSHO,
        "odds_wakuren": TABLE_ODDS_WAKUREN,
        "odds_umaren": TABLE_ODDS_UMAREN,
        "odds_wide": TABLE_ODDS_WIDE,
        "odds_umatan": TABLE_ODDS_UMATAN,
        "odds_sanrenpuku": TABLE_ODDS_SANRENPUKU,
        "odds_sanrentan": TABLE_ODDS_SANRENTAN,
        "kaisai_schedule": TABLE_KAISAI_SCHEDULE,
        "tenko_baba": TABLE_TENKO_BABA,
        "hasso_jikoku": TABLE_HASSO_JIKOKU,
        "kisyu_henko": TABLE_KISYU_HENKO,
        "course_henko": TABLE_COURSE_HENKO,
        "keito_info": TABLE_KEITO_INFO,
        "course_info": TABLE_COURSE_INFO,
        "record_master": TABLE_RECORD_MASTER,
        "keibajo_code": TABLE_KEIBAJO_CODE,
        "tokubetsu_toroku": TABLE_TOKUBETSU_TOROKU,
        "banushi": TABLE_BANUSHI,
        "seisansha": TABLE_SEISANSHA,
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
