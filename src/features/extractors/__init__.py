"""
Feature Extractors Module

Database query functions and calculation helpers for feature extraction.
"""

from src.features.extractors.db_queries import (
    get_race_entries,
    get_race_info,
    get_past_races,
    get_jockey_stats,
    get_trainer_stats,
    get_jockey_horse_combo,
    get_training_data,
    get_distance_stats,
    get_baba_stats,
    get_detailed_training,
    get_interval_stats,
)

from src.features.extractors.calculators import (
    # Type conversion helpers
    safe_int,
    safe_float,
    encode_sex,
    # Speed index calculations
    calc_speed_index_avg,
    calc_speed_index_max,
    calc_speed_index_recent,
    # Last 3F calculations
    calc_last3f_avg,
    calc_last3f_rank_avg,
    # Running style and position
    determine_running_style,
    calc_corner_avg,
    # Win/place rate calculations
    calc_win_rate,
    calc_place_rate,
    count_wins,
    # Days and intervals
    calc_days_since_last,
    get_interval_category,
    # Course and distance fit
    calc_course_fit,
    calc_distance_fit,
    determine_class_rank,
    calc_waku_bias,
    # Other calculations
    is_jockey_changed,
    calc_distance_change,
    calc_surface_rate,
    calc_class_change,
    calc_avg_time_diff,
    get_best_finish,
    calc_turn_rate,
    # Pace calculations
    calc_pace_prediction,
    calc_style_pace_compatibility,
    # Default features
    get_default_enhanced_features,
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
