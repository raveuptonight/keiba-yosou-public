"""
データベースクエリモジュール

各クエリモジュールの主要関数をエクスポート
"""

# レース情報取得クエリ
from src.db.queries.race_queries import (
    get_race_info,
    get_race_entries,
    get_races_by_date,
    get_races_today,
    get_race_entry_count,
    get_upcoming_races,
    get_race_detail,
    check_race_exists,
)

# 馬情報取得クエリ
from src.db.queries.horse_queries import (
    get_horse_info,
    get_horse_recent_races,
    get_horses_recent_races,
    get_horses_pedigree,
    get_horses_training,
    get_horses_statistics,
    get_horse_detail,
    check_horse_exists,
)

# オッズ情報取得クエリ
from src.db.queries.odds_queries import (
    get_odds_win_place,
    get_odds_quinella,
    get_odds_exacta,
    get_odds_wide,
    get_odds_trio,
    get_odds_trifecta,
    get_odds_bracket_quinella,
    get_race_odds,
)

# 予想データ集約クエリ
from src.db.queries.prediction_data import (
    get_race_prediction_data,
    get_multiple_races_prediction_data,
    get_race_prediction_data_slim,
    validate_prediction_data,
    get_prediction_data_summary,
)

__all__ = [
    # Race queries
    "get_race_info",
    "get_race_entries",
    "get_races_by_date",
    "get_races_today",
    "get_race_entry_count",
    "get_upcoming_races",
    "get_race_detail",
    "check_race_exists",
    # Horse queries
    "get_horse_info",
    "get_horse_recent_races",
    "get_horses_recent_races",
    "get_horses_pedigree",
    "get_horses_training",
    "get_horses_statistics",
    "get_horse_detail",
    "check_horse_exists",
    # Odds queries
    "get_odds_win_place",
    "get_odds_quinella",
    "get_odds_exacta",
    "get_odds_wide",
    "get_odds_trio",
    "get_odds_trifecta",
    "get_odds_bracket_quinella",
    "get_race_odds",
    # Prediction data queries
    "get_race_prediction_data",
    "get_multiple_races_prediction_data",
    "get_race_prediction_data_slim",
    "validate_prediction_data",
    "get_prediction_data_summary",
]
