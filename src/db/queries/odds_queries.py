"""
Odds Information Query Module.

Query functions for retrieving various odds data including win, place,
quinella, trifecta, and other betting types.
"""

import logging
from typing import Any

from asyncpg import Connection

from src.db.table_names import (
    COL_DATA_KUBUN,
    COL_RACE_ID,
    COL_UMABAN,
    TABLE_ODDS_FUKUSHO,
    TABLE_ODDS_SANRENPUKU,
    TABLE_ODDS_SANRENTAN,
    TABLE_ODDS_TANSHO,
    TABLE_ODDS_UMAREN,
    TABLE_ODDS_UMATAN,
    TABLE_ODDS_WAKUREN,
    TABLE_ODDS_WIDE,
)

logger = logging.getLogger(__name__)

# Data category constants
DATA_KUBUN_SAISYU_ODDS = "3"  # Final odds


async def get_odds_win_place(conn: Connection, race_id: str) -> dict[str, Any]:
    """
    Get win and place odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        {
            "win": [{"umaban": 1, "odds": 3.5}, ...],
            "place": [{"umaban": 1, "odds_min": 1.5, "odds_max": 2.0}, ...]
        }
    """
    # Get win odds
    sql_win = f"""
        SELECT
            {COL_UMABAN},
            odds,
            ninki
        FROM {TABLE_ODDS_TANSHO}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY {COL_UMABAN}
    """

    # Get place odds
    sql_place = f"""
        SELECT
            {COL_UMABAN},
            odds_saitei,
            odds_saikou,
            ninki
        FROM {TABLE_ODDS_FUKUSHO}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY {COL_UMABAN}
    """

    try:
        # Win odds
        win_rows = await conn.fetch(sql_win, race_id, DATA_KUBUN_SAISYU_ODDS)
        win_odds = []
        for row in win_rows:
            if row["odds"]:
                win_odds.append(
                    {
                        "umaban": row[COL_UMABAN],
                        "odds": float(row["odds"]) / 10.0,  # JRA-VAN stores 10x values
                        "ninki": row["ninki"],
                    }
                )

        # Place odds
        place_rows = await conn.fetch(sql_place, race_id, DATA_KUBUN_SAISYU_ODDS)
        place_odds = []
        for row in place_rows:
            if row["odds_saitei"] and row["odds_saikou"]:
                place_odds.append(
                    {
                        "umaban": row[COL_UMABAN],
                        "odds_min": float(row["odds_saitei"]) / 10.0,
                        "odds_max": float(row["odds_saikou"]) / 10.0,
                        "ninki": row["ninki"],
                    }
                )

        return {"win": win_odds, "place": place_odds}
    except Exception as e:
        logger.error(f"Failed to get win/place odds: race_id={race_id}, error={e}")
        raise


async def get_odds_quinella(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get quinella odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "3-7", "umaban1": 3, "umaban2": 7, "odds": 18.5, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            umaban_1,
            umaban_2,
            umaren_odds,
            umaren_ninki
        FROM {TABLE_ODDS_UMAREN}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY umaren_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["umaren_odds"]:
                result.append(
                    {
                        "kumi": f"{row['umaban_1']}-{row['umaban_2']}",
                        "umaban1": row["umaban_1"],
                        "umaban2": row["umaban_2"],
                        "odds": float(row["umaren_odds"]) / 10.0,
                        "ninki": row["umaren_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get quinella odds: race_id={race_id}, error={e}")
        raise


async def get_odds_exacta(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get exacta odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "3->7", "umaban1": 3, "umaban2": 7, "odds": 45.2, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            umaban_1,
            umaban_2,
            umatan_odds,
            umatan_ninki
        FROM {TABLE_ODDS_UMATAN}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY umatan_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["umatan_odds"]:
                result.append(
                    {
                        "kumi": f"{row['umaban_1']}→{row['umaban_2']}",
                        "umaban1": row["umaban_1"],
                        "umaban2": row["umaban_2"],
                        "odds": float(row["umatan_odds"]) / 10.0,
                        "ninki": row["umatan_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get exacta odds: race_id={race_id}, error={e}")
        raise


async def get_odds_wide(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get wide odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "3-7", "umaban1": 3, "umaban2": 7, "odds_min": 5.0, "odds_max": 7.5, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            umaban_1,
            umaban_2,
            wide_odds_min,
            wide_odds_max,
            wide_ninki
        FROM {TABLE_ODDS_WIDE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY wide_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["wide_odds_min"] and row["wide_odds_max"]:
                result.append(
                    {
                        "kumi": f"{row['umaban_1']}-{row['umaban_2']}",
                        "umaban1": row["umaban_1"],
                        "umaban2": row["umaban_2"],
                        "odds_min": float(row["wide_odds_min"]) / 10.0,
                        "odds_max": float(row["wide_odds_max"]) / 10.0,
                        "ninki": row["wide_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get wide odds: race_id={race_id}, error={e}")
        raise


async def get_odds_trio(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get trio odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "3-7-12", "umaban1": 3, "umaban2": 7, "umaban3": 12, "odds": 85.0, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            umaban_1,
            umaban_2,
            umaban_3,
            sanrenpuku_odds,
            sanrenpuku_ninki
        FROM {TABLE_ODDS_SANRENPUKU}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
          AND sanrenpuku_odds IS NOT NULL
        ORDER BY sanrenpuku_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["sanrenpuku_odds"]:
                result.append(
                    {
                        "kumi": f"{row['umaban_1']}-{row['umaban_2']}-{row['umaban_3']}",
                        "umaban1": row["umaban_1"],
                        "umaban2": row["umaban_2"],
                        "umaban3": row["umaban_3"],
                        "odds": float(row["sanrenpuku_odds"]) / 10.0,
                        "ninki": row["sanrenpuku_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get trio odds: race_id={race_id}, error={e}")
        raise


async def get_odds_trifecta(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get trifecta odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "3->7->12", "umaban1": 3, "umaban2": 7, "umaban3": 12, "odds": 450.0, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            umaban_1,
            umaban_2,
            umaban_3,
            sanrentan_odds,
            sanrentan_ninki
        FROM {TABLE_ODDS_SANRENTAN}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
          AND sanrentan_odds IS NOT NULL
        ORDER BY sanrentan_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["sanrentan_odds"]:
                result.append(
                    {
                        "kumi": f"{row['umaban_1']}→{row['umaban_2']}→{row['umaban_3']}",
                        "umaban1": row["umaban_1"],
                        "umaban2": row["umaban_2"],
                        "umaban3": row["umaban_3"],
                        "odds": float(row["sanrentan_odds"]) / 10.0,
                        "ninki": row["sanrentan_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get trifecta odds: race_id={race_id}, error={e}")
        raise


async def get_odds_bracket_quinella(
    conn: Connection, race_id: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Get bracket quinella odds.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        limit: Maximum number of results (optional, sorted by popularity).

    Returns:
        [{"kumi": "1-3", "wakuban1": 1, "wakuban2": 3, "odds": 12.5, "ninki": 1}, ...]
    """
    sql = f"""
        SELECT
            wakuban_1,
            wakuban_2,
            wakuren_odds,
            wakuren_ninki
        FROM {TABLE_ODDS_WAKUREN}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
        ORDER BY wakuren_ninki
    """

    if limit:
        sql += f" LIMIT {limit}"

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_SAISYU_ODDS)

        result = []
        for row in rows:
            if row["wakuren_odds"]:
                result.append(
                    {
                        "kumi": f"{row['wakuban_1']}-{row['wakuban_2']}",
                        "wakuban1": row["wakuban_1"],
                        "wakuban2": row["wakuban_2"],
                        "odds": float(row["wakuren_odds"]) / 10.0,
                        "ninki": row["wakuren_ninki"],
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Failed to get bracket quinella odds: race_id={race_id}, error={e}")
        raise


async def get_race_odds(
    conn: Connection, race_id: str, ticket_types: list[str] | None = None
) -> dict[str, Any]:
    """
    Get all odds information for a race.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).
        ticket_types: List of ticket types to retrieve (optional, None for all types).
                     ["win", "place", "quinella", "exacta", "wide", "trio", "trifecta", "bracket"]

    Returns:
        {
            "win": [...],
            "place": [...],
            "quinella": [...],
            "exacta": [...],
            "wide": [...],
            "trio": [...],
            "trifecta": [...],
            "bracket": [...]
        }
    """
    result = {}

    # Default to all ticket types
    if ticket_types is None:
        ticket_types = ["win", "place", "quinella", "exacta", "wide", "trio", "trifecta", "bracket"]

    try:
        # Win and place odds are retrieved together
        if "win" in ticket_types or "place" in ticket_types:
            win_place = await get_odds_win_place(conn, race_id)
            if "win" in ticket_types:
                result["win"] = win_place["win"]
            if "place" in ticket_types:
                result["place"] = win_place["place"]

        # Quinella
        if "quinella" in ticket_types:
            result["quinella"] = await get_odds_quinella(conn, race_id)

        # Exacta
        if "exacta" in ticket_types:
            result["exacta"] = await get_odds_exacta(conn, race_id)

        # Wide
        if "wide" in ticket_types:
            result["wide"] = await get_odds_wide(conn, race_id)

        # Trio
        if "trio" in ticket_types:
            result["trio"] = await get_odds_trio(conn, race_id)

        # Trifecta
        if "trifecta" in ticket_types:
            result["trifecta"] = await get_odds_trifecta(conn, race_id)

        # Bracket quinella
        if "bracket" in ticket_types:
            result["bracket"] = await get_odds_bracket_quinella(conn, race_id)

        return result
    except Exception as e:
        # Return empty dict if odds table doesn't exist
        logger.warning(f"Odds not available: race_id={race_id}, error={e}")
        return {}
