"""
Feature Extractors Module

Database query functions and calculation helpers for feature extraction.
"""

from src.features.extractors.calculators import (
    calc_avg_time_diff,
    calc_class_change,
    calc_corner_avg,
    # Course and distance fit
    calc_course_fit,
    # Days and intervals
    calc_days_since_last,
    calc_distance_change,
    calc_distance_fit,
    # Last 3F calculations
    calc_last3f_avg,
    calc_last3f_rank_avg,
    # Pace calculations
    calc_pace_prediction,
    calc_place_rate,
    # Speed index calculations
    calc_speed_index_avg,
    calc_speed_index_max,
    calc_speed_index_recent,
    calc_style_pace_compatibility,
    calc_surface_rate,
    calc_turn_rate,
    calc_waku_bias,
    # Win/place rate calculations
    calc_win_rate,
    count_wins,
    determine_class_rank,
    # Running style and position
    determine_running_style,
    encode_sex,
    get_best_finish,
    # Default features
    get_default_enhanced_features,
    get_interval_category,
    # Other calculations
    is_jockey_changed,
    safe_float,
    # Type conversion helpers
    safe_int,
)
from src.features.extractors.db_queries import (
    get_baba_stats,
    get_detailed_training,
    get_distance_stats,
    get_interval_stats,
    get_jockey_horse_combo,
    get_jockey_stats,
    get_past_races,
    get_race_entries,
    get_race_info,
    get_trainer_stats,
    get_training_data,
)

__all__ = [
    # DB queries
    'get_race_entries',
    'get_race_info',
    'get_past_races',
    'get_jockey_stats',
    'get_trainer_stats',
    'get_jockey_horse_combo',
    'get_training_data',
    'get_distance_stats',
    'get_baba_stats',
    'get_detailed_training',
    'get_interval_stats',
    # Calculators
    'safe_int',
    'safe_float',
    'encode_sex',
    'calc_speed_index_avg',
    'calc_speed_index_max',
    'calc_speed_index_recent',
    'calc_last3f_avg',
    'calc_last3f_rank_avg',
    'determine_running_style',
    'calc_corner_avg',
    'calc_win_rate',
    'calc_place_rate',
    'count_wins',
    'calc_days_since_last',
    'get_interval_category',
    'calc_course_fit',
    'calc_distance_fit',
    'determine_class_rank',
    'calc_waku_bias',
    'is_jockey_changed',
    'calc_distance_change',
    'calc_surface_rate',
    'calc_class_change',
    'calc_avg_time_diff',
    'get_best_finish',
    'calc_turn_rate',
    'calc_pace_prediction',
    'calc_style_pace_compatibility',
    'get_default_enhanced_features',
]
