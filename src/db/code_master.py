"""
Code Master Table Retrieval Module

Retrieves code names from JRA-VAN code master tables
and caches them for use.
"""

import logging

from asyncpg import Connection

logger = logging.getLogger(__name__)

# Global cache (loaded once at startup)
_CODE_CACHE: dict[str, dict[str, str]] = {}


async def load_code_master(conn: Connection, table_name: str) -> dict[str, str]:
    """
    Retrieve code -> name mapping from a code master table.

    Args:
        conn: Database connection
        table_name: Code master table name

    Returns:
        Dictionary mapping code to name
    """
    try:
        # Use different column names depending on the table
        if table_name == "keibajo_code":
            # Racecourse code uses jomei column
            query = f"SELECT code, jomei AS meisho FROM {table_name}"
        elif table_name == "tozai_shozoku_code":
            # East/West affiliation code uses meisho2 column (Miho/Ritto)
            query = f"SELECT code, meisho2 AS meisho FROM {table_name}"
        else:
            # Other tables use meisho column
            query = f"SELECT code, meisho FROM {table_name}"

        rows = await conn.fetch(query)

        mapping = {}
        for row in rows:
            code = row["code"].strip() if row["code"] else ""
            meisho = row["meisho"].strip() if row["meisho"] else ""
            if code:  # Exclude empty codes
                mapping[code] = meisho

        logger.info(f"Loaded {len(mapping)} codes from {table_name}")
        return mapping

    except Exception as e:
        logger.error(f"Failed to load code master {table_name}: {e}")
        return {}


async def initialize_code_cache(conn: Connection) -> None:
    """
    Load all code masters into cache.

    Args:
        conn: Database connection
    """
    global _CODE_CACHE

    # Code master tables to load
    tables = [
        "keibajo_code",  # Racecourse code
        "grade_code",  # Grade code
        "kyoso_shubetsu_code",  # Race type code
        "kyoso_joken_code",  # Race condition code
        "track_code",  # Track code
        "babajotai_code",  # Track condition code
        "tenko_code",  # Weather code
        "seibetsu_code",  # Sex code
        "moshoku_code",  # Coat color code
        "tozai_shozoku_code",  # East/West affiliation code
    ]

    for table in tables:
        _CODE_CACHE[table] = await load_code_master(conn, table)

    logger.info(f"Code cache initialized with {len(_CODE_CACHE)} tables")


def get_code_name(table_name: str, code: str) -> str:
    """
    Get name from code (from cache).

    Args:
        table_name: Code master table name
        code: Code value

    Returns:
        Name (empty string if not found)
    """
    if not code:
        return ""

    code = code.strip()

    if table_name not in _CODE_CACHE:
        logger.warning(f"Code table {table_name} not in cache")
        return ""

    return _CODE_CACHE[table_name].get(code, "")


# ===== Helper Functions (for backward compatibility) =====


def get_keibajo_name(code: str) -> str:
    """Get racecourse name from code."""
    return get_code_name("keibajo_code", code)


def get_grade_name(code: str) -> str:
    """Get grade name from code."""
    return get_code_name("grade_code", code)


def get_kyoso_shubetsu_name(code: str) -> str:
    """Get race type name from code."""
    name = get_code_name("kyoso_shubetsu_code", code)
    # Simplify "サラブレッド系3歳" -> "3歳"
    if "サラブレッド系" in name:
        name = name.replace("サラブレッド系", "").strip()
    return name


def get_kyoso_joken_name(code: str) -> str:
    """Get race condition name from code."""
    return get_code_name("kyoso_joken_code", code)


def get_track_name(code: str) -> str:
    """Get track name from code."""
    return get_code_name("track_code", code)


def get_babajotai_name(code: str) -> str:
    """Get track condition name from code."""
    return get_code_name("babajotai_code", code)


def get_tenko_name(code: str) -> str:
    """Get weather name from code."""
    return get_code_name("tenko_code", code)


def get_seibetsu_name(code: str) -> str:
    """Get sex name from code."""
    return get_code_name("seibetsu_code", code)


def get_moshoku_name(code: str) -> str:
    """Get coat color name from code."""
    return get_code_name("moshoku_code", code)


def generate_race_condition_name(
    kyoso_joken_code: str | None, kyoso_shubetsu_code: str | None, grade_code: str | None
) -> str:
    """
    Generate race condition name from codes.

    Args:
        kyoso_joken_code: Race condition code
        kyoso_shubetsu_code: Race type code
        grade_code: Grade code

    Returns:
        Generated race name (e.g., "3歳未勝利", "3歳以上1勝クラス")
    """
    # Graded races should use original race name
    if grade_code and grade_code in ["A", "B", "C", "D"]:
        return ""

    parts = []

    # Race type (age/sex)
    if kyoso_shubetsu_code:
        shubetsu = get_kyoso_shubetsu_name(kyoso_shubetsu_code)
        if shubetsu:
            parts.append(shubetsu)

    # Race condition (class)
    if kyoso_joken_code and kyoso_joken_code != "000":
        joken = get_kyoso_joken_name(kyoso_joken_code)
        if joken:
            parts.append(joken)

    if not parts:
        return "条件戦"

    return "".join(parts)
