"""
Utility functions for feature extraction.

Contains safe type conversion, encoding, and calculation helpers.
"""

import hashlib
from datetime import date as dt_date


def safe_int(val, default: int = 0) -> int:
    """Safely convert value to integer.

    Args:
        val: Value to convert (can be str, int, float, or None)
        default: Default value if conversion fails

    Returns:
        Converted integer or default value
    """
    try:
        if val is None or val == "":
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_float(val, default: float = 0.0) -> float:
    """Safely convert value to float.

    Args:
        val: Value to convert
        default: Default value if conversion fails

    Returns:
        Converted float or default value
    """
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def encode_sex(sex_code: str) -> int:
    """Encode horse sex code to numeric value.

    Args:
        sex_code: JRA sex code ('1'=stallion, '2'=mare, '3'=gelding)

    Returns:
        Numeric encoding (0, 1, or 2)
    """
    mapping = {"1": 0, "2": 1, "3": 2}
    return mapping.get(sex_code, 0)


def calc_speed_index(avg_time: float | None) -> float:
    """Calculate speed index from average finishing time.

    Converts raw time (in 1/10 seconds format) to a normalized speed index
    where higher values indicate faster horses.

    Args:
        avg_time: Average finishing time (format: MSSSS where M=minutes, SSSS=seconds*10)

    Returns:
        Speed index (typically 50-120, centered around 80)
    """
    if not avg_time:
        return 80.0
    minutes = avg_time // 1000
    seconds = (avg_time % 1000) / 10
    total = minutes * 60 + seconds
    return max(50, min(120, 100 - (total - 90) * 2))


def determine_style(avg_corner3: float) -> int:
    """Determine running style from average 3rd corner position.

    Args:
        avg_corner3: Average position at 3rd corner

    Returns:
        Running style code:
        - 1: Nige (front runner)
        - 2: Senkou (stalker)
        - 3: Sashi (closer)
        - 4: Oikomi (deep closer)
    """
    if avg_corner3 <= 2:
        return 1  # Nige
    elif avg_corner3 <= 5:
        return 2  # Senkou
    elif avg_corner3 <= 10:
        return 3  # Sashi
    return 4  # Oikomi


def determine_class(grade_code: str) -> int:
    """Convert grade code to numeric class rank.

    Args:
        grade_code: JRA grade code (A-H)

    Returns:
        Numeric rank (8=highest/G1, 1=lowest)
    """
    mapping = {"A": 8, "B": 7, "C": 6, "D": 5, "E": 4, "F": 3, "G": 2, "H": 1}
    return mapping.get(grade_code, 3)


def grade_to_rank(grade_code: str) -> int:
    """Convert grade code to rank (alias for determine_class).

    Args:
        grade_code: JRA grade code (A-H)

    Returns:
        Numeric rank (8=highest, 1=lowest)
    """
    mapping = {"A": 8, "B": 7, "C": 6, "D": 5, "E": 4, "F": 3, "G": 2, "H": 1}
    return mapping.get(grade_code, 3)


def get_distance_category(distance: int) -> str:
    """Categorize race distance.

    Args:
        distance: Race distance in meters

    Returns:
        Distance category string
    """
    if distance <= 1200:
        return "sprint"
    elif distance <= 1600:
        return "mile"
    elif distance <= 2000:
        return "middle"
    elif distance <= 2400:
        return "classic"
    else:
        return "long"


def get_interval_category(days: int) -> str:
    """Categorize rest interval between races.

    Args:
        days: Days since last race

    Returns:
        Interval category string:
        - 'rentou': Back-to-back (1-7 days)
        - 'week1': 1 week rest (8-14 days)
        - 'week2': 2 weeks rest (15-21 days)
        - 'week3': 3 weeks rest (22-28 days)
        - 'week4plus': 4+ weeks rest (29+ days)
    """
    if days <= 7:
        return "rentou"
    elif days <= 14:
        return "week1"
    elif days <= 21:
        return "week2"
    elif days <= 28:
        return "week3"
    else:
        return "week4plus"


def calc_days_since_last(last_race_date: str, current_year: str, current_gappi: str) -> int:
    """Calculate days since last race.

    Args:
        last_race_date: Last race date string (YYYYMMDD format)
        current_year: Current race year (YYYY)
        current_gappi: Current race date (MMDD)

    Returns:
        Number of days since last race (default: 60 if calculation fails)
    """
    if not last_race_date or not current_year or not current_gappi:
        return 60

    try:
        last_year = int(last_race_date[:4])
        last_month = int(last_race_date[4:6])
        last_day = int(last_race_date[6:8])
        curr_year = int(current_year)
        curr_month = int(current_gappi[:2])
        curr_day = int(current_gappi[2:4])

        last = dt_date(last_year, last_month, last_day)
        curr = dt_date(curr_year, curr_month, curr_day)
        return max(0, (curr - last).days)
    except Exception:
        return 60


def calc_style_pace_compatibility(running_style: int, pace_type: int) -> float:
    """Calculate compatibility score between running style and race pace.

    Higher pace favors closers, lower pace favors front runners.

    Args:
        running_style: 1=Nige, 2=Senkou, 3=Sashi, 4=Oikomi
        pace_type: 1=Slow, 2=Middle, 3=High

    Returns:
        Compatibility score (0.0-1.0)
    """
    compatibility_matrix = {
        # (running_style, pace_type): compatibility_score
        (1, 1): 0.8,  # Nige x Slow = advantageous
        (1, 2): 0.5,  # Nige x Middle = neutral
        (1, 3): 0.2,  # Nige x High = disadvantageous
        (2, 1): 0.7,  # Senkou x Slow = slightly advantageous
        (2, 2): 0.5,  # Senkou x Middle = neutral
        (2, 3): 0.4,  # Senkou x High = slightly disadvantageous
        (3, 1): 0.3,  # Sashi x Slow = slightly disadvantageous
        (3, 2): 0.5,  # Sashi x Middle = neutral
        (3, 3): 0.7,  # Sashi x High = slightly advantageous
        (4, 1): 0.2,  # Oikomi x Slow = disadvantageous
        (4, 2): 0.5,  # Oikomi x Middle = neutral
        (4, 3): 0.8,  # Oikomi x High = advantageous
    }
    return compatibility_matrix.get((running_style, pace_type), 0.5)


def stable_hash(s: str, mod: int = 10000) -> int:
    """Generate a stable hash value (consistent across Python sessions).

    Uses MD5 to ensure deterministic hashing regardless of Python's hash randomization.

    Args:
        s: String to hash
        mod: Modulo value for hash range

    Returns:
        Hash value in range [0, mod)
    """
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod
