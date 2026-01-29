"""
Calculation Helper Functions for Feature Extraction

Pure functions for calculating various horse racing features and statistics.
"""

from datetime import date
from typing import Any

import numpy as np

# ===== Type conversion helpers =====

def safe_int(val, default: int = 0) -> int:
    """
    Safely convert value to int.

    Args:
        val: Value to convert
        default: Default value if conversion fails

    Returns:
        Integer value
    """
    try:
        if val is None or val == '':
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_float(val, default: float = 0.0) -> float:
    """
    Safely convert value to float.

    Args:
        val: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value
    """
    try:
        if val is None or val == '':
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def encode_sex(sex_code: str) -> int:
    """
    Encode sex code to integer.

    Args:
        sex_code: Sex code (1=male, 2=female, 3=gelding)

    Returns:
        Encoded value (0=male, 1=female, 2=gelding)
    """
    mapping = {'1': 0, '2': 1, '3': 2}
    return mapping.get(sex_code, 0)


# ===== Speed index calculations =====

def calc_speed_index_avg(past_races: list[dict], n: int = 5) -> float:
    """
    Calculate average speed index (simplified version based on time).

    Args:
        past_races: List of past race dictionaries
        n: Number of races to consider

    Returns:
        Average speed index
    """
    if not past_races:
        return 80.0

    times = []
    for race in past_races[:n]:
        time_str = race.get('soha_time', '')
        if time_str and time_str.isdigit():
            # Convert time to seconds (MMSSs format)
            time_val = int(time_str)
            minutes = time_val // 1000
            seconds = (time_val % 1000) / 10
            total_seconds = minutes * 60 + seconds
            # Simplified speed index (base time 90 seconds)
            speed_index = 100 - (total_seconds - 90) * 2
            times.append(max(50, min(120, speed_index)))

    return np.mean(times) if times else 80.0


def calc_speed_index_max(past_races: list[dict], n: int = 5) -> float:
    """
    Calculate maximum speed index.

    Args:
        past_races: List of past race dictionaries
        n: Number of races to consider

    Returns:
        Maximum speed index
    """
    if not past_races:
        return 85.0

    times = []
    for race in past_races[:n]:
        time_str = race.get('soha_time', '')
        if time_str and time_str.isdigit():
            time_val = int(time_str)
            minutes = time_val // 1000
            seconds = (time_val % 1000) / 10
            total_seconds = minutes * 60 + seconds
            speed_index = 100 - (total_seconds - 90) * 2
            times.append(max(50, min(120, speed_index)))

    return max(times) if times else 85.0


def calc_speed_index_recent(past_races: list[dict]) -> float:
    """
    Calculate most recent race speed index.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Recent speed index
    """
    if not past_races:
        return 80.0
    return calc_speed_index_avg(past_races[:1], 1)


# ===== Last 3F calculations =====

def calc_last3f_avg(past_races: list[dict], n: int = 5) -> float:
    """
    Calculate average last 3 furlong time.

    Args:
        past_races: List of past race dictionaries
        n: Number of races to consider

    Returns:
        Average last 3F time in seconds
    """
    if not past_races:
        return 35.0

    times = []
    for race in past_races[:n]:
        l3f = race.get('kohan_3f', '')
        if l3f and l3f.isdigit():
            times.append(int(l3f) / 10.0)

    return np.mean(times) if times else 35.0


def calc_last3f_rank_avg(past_races: list[dict], n: int = 5) -> float:
    """
    Calculate average last 3F rank (simplified).

    Args:
        past_races: List of past race dictionaries
        n: Number of races to consider

    Returns:
        Average last 3F rank
    """
    # Actual data doesn't have last 3F rank, so return default
    return 5.0


# ===== Running style and position =====

def determine_running_style(past_races: list[dict]) -> int:
    """
    Determine running style from past races.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Running style (1=front-runner, 2=stalker, 3=closer, 4=deep closer)
    """
    if not past_races:
        return 2  # Default: stalker

    avg_pos = []
    for race in past_races[:5]:
        c3 = safe_int(race.get('corner3_juni'), 0)
        if c3 > 0:
            avg_pos.append(c3)

    if not avg_pos:
        return 2

    avg = np.mean(avg_pos)
    if avg <= 2:
        return 1  # Front-runner
    elif avg <= 5:
        return 2  # Stalker
    elif avg <= 10:
        return 3  # Closer
    else:
        return 4  # Deep closer


def calc_corner_avg(past_races: list[dict], corner_col: str) -> float:
    """
    Calculate average corner position.

    Args:
        past_races: List of past race dictionaries
        corner_col: Column name for corner position

    Returns:
        Average position at specified corner
    """
    if not past_races:
        return 8.0

    positions = []
    for race in past_races[:5]:
        pos = safe_int(race.get(corner_col), 0)
        if pos > 0:
            positions.append(pos)

    return np.mean(positions) if positions else 8.0


# ===== Win/place rate calculations =====

def calc_win_rate(past_races: list[dict]) -> float:
    """
    Calculate win rate.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Win rate (0.0-1.0)
    """
    if not past_races:
        return 0.0

    wins = sum(1 for r in past_races if safe_int(r.get('kakutei_chakujun'), 99) == 1)
    return wins / len(past_races)


def calc_place_rate(past_races: list[dict]) -> float:
    """
    Calculate place rate (top 3 finish).

    Args:
        past_races: List of past race dictionaries

    Returns:
        Place rate (0.0-1.0)
    """
    if not past_races:
        return 0.0

    places = sum(1 for r in past_races if safe_int(r.get('kakutei_chakujun'), 99) <= 3)
    return places / len(past_races)


def count_wins(past_races: list[dict]) -> int:
    """
    Count number of wins.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Number of wins
    """
    return sum(1 for r in past_races if safe_int(r.get('kakutei_chakujun'), 99) == 1)


# ===== Days and intervals =====

def calc_days_since_last(past_races: list[dict], race_info: dict) -> int:
    """
    Calculate days since last race.

    Args:
        past_races: List of past race dictionaries
        race_info: Current race info

    Returns:
        Days since last race
    """
    if not past_races:
        return 60  # Default

    try:
        current_year = race_info.get('kaisai_nen', '')
        current_date = race_info.get('kaisai_gappi', '')
        last_year = past_races[0].get('kaisai_nen', '')
        last_date = past_races[0].get('kaisai_gappi', '')

        if not all([current_year, current_date, last_year, last_date]):
            return 60

        current = date(int(current_year), int(current_date[:2]), int(current_date[2:]))
        last = date(int(last_year), int(last_date[:2]), int(last_date[2:]))
        return (current - last).days
    except Exception:
        return 60


def get_interval_category(days: int) -> str:
    """
    Get interval category from days.

    Args:
        days: Number of days since last race

    Returns:
        Interval category string
    """
    if days <= 7:
        return 'rentou'
    elif days <= 14:
        return 'week1'
    elif days <= 21:
        return 'week2'
    elif days <= 28:
        return 'week3'
    else:
        return 'week4plus'


# ===== Course and distance fit =====

def calc_course_fit(past_races: list[dict], keibajo_code: str) -> float:
    """
    Calculate course fit (place rate at same venue).

    Args:
        past_races: List of past race dictionaries
        keibajo_code: Venue code

    Returns:
        Course fit score (0.0-1.0)
    """
    if not past_races or not keibajo_code:
        return 0.5

    same_course = [r for r in past_races if r.get('keibajo_code') == keibajo_code]
    if not same_course:
        return 0.5

    places = sum(1 for r in same_course if safe_int(r.get('kakutei_chakujun'), 99) <= 3)
    return places / len(same_course)


def calc_distance_fit(past_races: list[dict], target_distance: int) -> float:
    """
    Calculate distance fit (place rate at similar distances).

    Args:
        past_races: List of past race dictionaries
        target_distance: Target race distance

    Returns:
        Distance fit score (0.0-1.0)
    """
    if not past_races:
        return 0.5

    # Distance data requires JOIN, simplified version returns default
    return 0.5


def determine_class_rank(race_info: dict) -> int:
    """
    Determine class rank from race info.

    Args:
        race_info: Race info dictionary

    Returns:
        Class rank (1-8)
    """
    grade = race_info.get('grade_code', '')
    mapping = {
        'A': 8,  # G1
        'B': 7,  # G2
        'C': 6,  # G3
        'D': 5,  # Listed
        'E': 4,  # Open
        'F': 3,  # 3-win class
        'G': 2,  # 2-win class
        'H': 1,  # 1-win class
    }
    return mapping.get(grade, 3)


def calc_waku_bias(wakuban: int, race_info: dict) -> float:
    """
    Calculate post position bias (simplified).

    Args:
        wakuban: Post position
        race_info: Race info dictionary

    Returns:
        Bias value (-0.1 to 0.1)
    """
    # Assumes inside posts are advantageous
    return (wakuban - 4.5) * 0.02


# ===== Other calculations =====

def is_jockey_changed(past_races: list[dict], current_jockey: str) -> bool:
    """
    Check if jockey changed from last race.

    Args:
        past_races: List of past race dictionaries
        current_jockey: Current jockey code

    Returns:
        True if jockey changed
    """
    if not past_races or not current_jockey:
        return False
    last_jockey = past_races[0].get('kishu_code', '')
    return last_jockey != current_jockey


def calc_distance_change(past_races: list[dict], race_info: dict) -> int:
    """
    Calculate distance change from last race.

    Args:
        past_races: List of past race dictionaries
        race_info: Current race info

    Returns:
        Distance change in meters
    """
    if not past_races:
        return 0

    current_dist = safe_int(race_info.get('kyori'), 0)
    # Past race distance requires JOIN, simplified version returns 0
    return 0


def calc_surface_rate(past_races: list[dict], is_turf: bool) -> float:
    """
    Calculate place rate by surface type.

    Args:
        past_races: List of past race dictionaries
        is_turf: True for turf, False for dirt

    Returns:
        Place rate (0.0-1.0)
    """
    if not past_races:
        return 0.25

    # Filter by track_code (1x=turf, 2x=dirt)
    # If track_code not available in past races, return overall place rate
    places = sum(1 for r in past_races if safe_int(r.get('kakutei_chakujun'), 99) <= 3)
    return places / len(past_races) if past_races else 0.25


def calc_class_change(past_races: list[dict], race_info: dict) -> int:
    """
    Calculate class change from last race.

    Args:
        past_races: List of past race dictionaries
        race_info: Current race info

    Returns:
        Class change (-1=drop, 0=same, 1=rise)
    """
    # Simplified version: comparison with last race is complex
    return 0


def calc_avg_time_diff(past_races: list[dict]) -> float:
    """
    Calculate average time difference from winner.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Average time difference in seconds
    """
    if not past_races:
        return 1.0

    # Estimate time difference from finishing position if no time diff data
    diffs = []
    for race in past_races[:5]:
        chakujun = safe_int(race.get('kakutei_chakujun'), 10)
        # Estimate time diff: 1st=0s, 10th=2s
        estimated_diff = (chakujun - 1) * 0.2
        diffs.append(min(estimated_diff, 5.0))

    return np.mean(diffs) if diffs else 1.0


def get_best_finish(past_races: list[dict]) -> int:
    """
    Get best finishing position.

    Args:
        past_races: List of past race dictionaries

    Returns:
        Best finishing position
    """
    if not past_races:
        return 10

    finishes = [safe_int(r.get('kakutei_chakujun'), 99) for r in past_races]
    valid_finishes = [f for f in finishes if f < 99]
    return min(valid_finishes) if valid_finishes else 10


def calc_turn_rate(past_races: list[dict], is_right: bool) -> float:
    """
    Calculate place rate by turn direction.

    Args:
        past_races: List of past race dictionaries
        is_right: True for right-handed courses

    Returns:
        Place rate (0.0-1.0)
    """
    if not past_races:
        return 0.25

    # Right-handed: Sapporo(01), Hakodate(02), Fukushima(03), Nakayama(06), Hanshin(09), Kokura(10)
    # Left-handed: Niigata(04), Tokyo(05), Chukyo(07), Kyoto(08)
    right_courses = {'01', '02', '03', '06', '09', '10'}
    left_courses = {'04', '05', '07', '08'}

    target_courses = right_courses if is_right else left_courses
    filtered = [r for r in past_races if r.get('keibajo_code') in target_courses]

    if not filtered:
        return 0.25

    places = sum(1 for r in filtered if safe_int(r.get('kakutei_chakujun'), 99) <= 3)
    return places / len(filtered)


# ===== Pace calculations =====

def calc_pace_prediction(
    entries: list[dict],
    race_info: dict,
    get_past_races_func,
    conn,
    cache: dict
) -> dict:
    """
    Calculate pace prediction.

    Args:
        entries: List of entry dictionaries
        race_info: Race info dictionary
        get_past_races_func: Function to get past races
        conn: Database connection
        cache: Cache dictionary

    Returns:
        Dictionary with pace_maker_count, senkou_count, sashi_count, pace_type
    """
    pace_makers = 0
    senkou_count = 0
    sashi_count = 0
    oikomi_count = 0

    for entry in entries:
        kettonum = entry.get('ketto_toroku_bango', '')
        past_races = get_past_races_func(
            conn, kettonum, race_info.get('race_code', ''), cache, limit=5
        )
        style = determine_running_style(past_races)

        if style == 1:  # Front-runner
            pace_makers += 1
        elif style == 2:  # Stalker
            senkou_count += 1
        elif style == 3:  # Closer
            sashi_count += 1
        else:  # Deep closer
            oikomi_count += 1

    # Pace prediction: 2+ front-runners -> fast pace, 0 front-runners -> slow pace
    if pace_makers >= 2:
        pace_type = 3  # Fast pace
    elif pace_makers == 0:
        pace_type = 1  # Slow pace
    else:
        pace_type = 2  # Medium pace

    return {
        'pace_maker_count': pace_makers,
        'senkou_count': senkou_count,
        'sashi_count': sashi_count,
        'pace_type': pace_type
    }


def calc_style_pace_compatibility(running_style: int, pace_type: int) -> float:
    """
    Calculate running style vs pace compatibility score.

    Fast pace favors closers.
    Slow pace favors front-runners.

    Args:
        running_style: Running style (1-4)
        pace_type: Pace type (1-3)

    Returns:
        Compatibility score (0.0-1.0)
    """
    compatibility_matrix = {
        # (running_style, pace_type): compatibility_score
        (1, 1): 0.8,   # Front-runner x slow = advantageous
        (1, 2): 0.5,   # Front-runner x medium = neutral
        (1, 3): 0.2,   # Front-runner x fast = disadvantageous
        (2, 1): 0.7,   # Stalker x slow = slightly advantageous
        (2, 2): 0.5,   # Stalker x medium = neutral
        (2, 3): 0.4,   # Stalker x fast = slightly disadvantageous
        (3, 1): 0.3,   # Closer x slow = slightly disadvantageous
        (3, 2): 0.5,   # Closer x medium = neutral
        (3, 3): 0.7,   # Closer x fast = slightly advantageous
        (4, 1): 0.2,   # Deep closer x slow = disadvantageous
        (4, 2): 0.5,   # Deep closer x medium = neutral
        (4, 3): 0.8,   # Deep closer x fast = advantageous
    }
    return compatibility_matrix.get((running_style, pace_type), 0.5)


# ===== Default features =====

def get_default_enhanced_features() -> dict[str, Any]:
    """
    Get default values for enhanced features.

    Returns:
        Dictionary with default enhanced feature values
    """
    return {
        # Pedigree
        'sire_id_hash': 0,
        'broodmare_sire_id_hash': 0,
        'sire_distance_win_rate': 0.08,
        'sire_distance_place_rate': 0.25,
        'sire_distance_runs': 0,
        'sire_baba_win_rate': 0.08,
        'sire_baba_place_rate': 0.25,
        'sire_venue_win_rate': 0.08,
        'sire_venue_place_rate': 0.25,
        'broodmare_sire_win_rate': 0.08,
        'broodmare_sire_place_rate': 0.25,
        # Last race info
        'zenso1_chakujun': 10,
        'zenso1_ninki': 10,
        'zenso1_ninki_diff': 0,
        'zenso1_class_diff': 0,
        'zenso1_agari_rank': 9,
        'zenso1_corner_avg': 8.0,
        'zenso1_distance': 1600,
        'zenso1_distance_diff': 0,
        'zenso2_chakujun': 10,
        'zenso3_chakujun': 10,
        'zenso_chakujun_trend': 0,
        'zenso_agari_trend': 0,
        # Venue stats
        'venue_win_rate': 0.0,
        'venue_place_rate': 0.0,
        'venue_runs': 0,
        'small_track_place_rate': 0.25,
        'large_track_place_rate': 0.25,
        'track_type_fit': 0.25,
        # Pace enhancement
        'inner_nige_count': 0,
        'inner_senkou_count': 0,
        'waku_style_advantage': 0.0,
        # Trends
        'jockey_recent_win_rate': 0.08,
        'jockey_recent_place_rate': 0.25,
        'jockey_recent_runs': 0,
        # Season/timing
        'race_month': 6,
        'month_sin': 0.0,
        'month_cos': 1.0,
        'kaisai_week': 2,
        'growth_period': 0,
        'is_winter': 0,
    }
