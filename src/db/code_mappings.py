"""
JRA-VAN Code Mapping Definitions (DEPRECATED)

This file is kept for backward compatibility.
For new code, use src.db.code_master instead.

Values are now dynamically retrieved from code master tables.
"""

# Import functions from new code_master module
from src.db.code_master import (
    generate_race_condition_name,
    get_babajotai_name,
    get_grade_name,
    get_keibajo_name,
    get_kyoso_joken_name,
    get_kyoso_shubetsu_name,
    get_moshoku_name,
    get_seibetsu_name,
    get_tenko_name,
    get_track_name,
)

# Export for backward compatibility
__all__ = [
    "get_keibajo_name",
    "get_grade_name",
    "get_kyoso_shubetsu_name",
    "get_kyoso_joken_name",
    "get_track_name",
    "get_babajotai_name",
    "get_tenko_name",
    "get_seibetsu_name",
    "get_moshoku_name",
    "generate_race_condition_name",
]
