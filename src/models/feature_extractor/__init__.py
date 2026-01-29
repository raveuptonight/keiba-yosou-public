"""
Feature Extractor Package

High-speed batch feature extraction for horse racing ML predictions.

Modules:
    base: FastFeatureExtractor main class
    db_queries: Database query methods
    performance: Performance statistics (surface, turn, track condition)
    pedigree: Pedigree and sire statistics
    venue: Venue and previous race (zenso) statistics
    feature_builder: Feature construction logic
    utils: Utility functions
"""

from .base import FastFeatureExtractor
from .utils import (
    safe_int,
    safe_float,
    encode_sex,
    calc_speed_index,
    determine_style,
    determine_class,
    get_distance_category,
    get_interval_category,
    calc_days_since_last,
    calc_style_pace_compatibility,
    stable_hash
)

__all__ = [
    'FastFeatureExtractor',
    'safe_int',
    'safe_float',
    'encode_sex',
    'calc_speed_index',
    'determine_style',
    'determine_class',
    'get_distance_category',
    'get_interval_category',
    'calc_days_since_last',
    'calc_style_pace_compatibility',
    'stable_hash'
]
