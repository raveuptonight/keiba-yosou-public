"""
Race Information Query Module.

Query functions for retrieving race basic information, race entries,
and race lists for a given date.
"""

import logging
from datetime import date
from typing import Any

from asyncpg import Connection

from src.db.table_names import (
    COL_BAMEI,
    COL_BAREI,
    COL_BATAIJU,
    COL_CHOKYOSI_NAME,
    COL_CHOKYOSICODE,
    COL_DATA_KUBUN,
    COL_DIRT_BABA_CD,
    COL_GRADE_CD,
    COL_HASSO_JIKOKU,
    COL_JYOCD,
    COL_KAISAI_MONTHDAY,
    COL_KAISAI_YEAR,
    COL_KETTONUM,
    COL_KINRYO,
    COL_KISYU_NAME,
    COL_KISYUCODE,
    COL_KYORI,
    COL_KYOSO_JOKEN_2SAI,
    COL_KYOSO_JOKEN_3SAI,
    COL_KYOSO_JOKEN_4SAI,
    COL_KYOSO_JOKEN_5SAI_IJO,
    COL_KYOSO_SHUBETSU_CD,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_RACE_NUM,
    COL_SEX,
    COL_SHIBA_BABA_CD,
    COL_TENKO_CD,
    COL_TOZAI_CODE,
    COL_TRACK_CD,
    COL_UMABAN,
    COL_WAKUBAN,
    DATA_KUBUN_KAKUTEI,
    TABLE_CHOKYOSI,
    TABLE_HANSYOKU,
    TABLE_KISYU,
    TABLE_RACE,
    TABLE_SANKU,
    TABLE_UMA,
    TABLE_UMA_RACE,
)

logger = logging.getLogger(__name__)


# SQL expression to get unified race condition code from age-specific columns
def get_kyoso_joken_code_expr() -> str:
    """
    Get SQL expression for the first non-'000' value from age-specific race condition code columns.

    Returns:
        COALESCE expression string with AS kyoso_joken_code alias.
    """
    return f"""COALESCE(
        NULLIF({COL_KYOSO_JOKEN_2SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_3SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_4SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_5SAI_IJO}, '000'),
        '000'
    ) as kyoso_joken_code"""


async def get_race_info(conn: Connection, race_id: str) -> dict[str, Any] | None:
    """
    Get race basic information.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        Race information dict, or None if not found.
    """
    # Get all registered races (including future races)
    # data_kubun: 1=registered, 2=preliminary, 3=post_position_confirmed,
    # 4=race_card, 5=in_progress, 6=before_finalized, 7=finalized
    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            honshokin1,
            honshokin2,
            honshokin3,
            honshokin4,
            honshokin5,
            {COL_SHIBA_BABA_CD},
            {COL_DIRT_BABA_CD},
            {COL_TENKO_CD},
            {COL_RACE_NUM},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {COL_HASSO_JIKOKU},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get race info: race_id={race_id}, error={e}")
        raise


async def get_race_entries(conn: Connection, race_id: str) -> list[dict[str, Any]]:
    """
    Get race entries list including pedigree and last race information.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        List of horse entry information sorted by horse number.
    """
    # Get all registered race entries (including future races)
    # Last race information is retrieved from finalized data only
    sql = f"""
        WITH last_race AS (
            -- Get last race info for each horse (finalized data only)
            SELECT DISTINCT ON (se2.{COL_KETTONUM})
                se2.{COL_KETTONUM},
                se2.{COL_JYOCD} AS last_venue_code,
                se2.kakutei_chakujun AS last_finish
            FROM {TABLE_UMA_RACE} se2
            WHERE se2.{COL_RACE_ID} < $1
              AND se2.{COL_DATA_KUBUN} = '7'
              AND se2.kakutei_chakujun IS NOT NULL
              AND se2.kakutei_chakujun::integer > 0
            ORDER BY se2.{COL_KETTONUM}, se2.{COL_RACE_ID} DESC
        )
        SELECT
            se.{COL_UMABAN},
            se.{COL_KETTONUM},
            um.{COL_BAMEI},
            se.{COL_KISYUCODE},
            ks.{COL_KISYU_NAME},
            se.{COL_CHOKYOSICODE},
            ch.{COL_CHOKYOSI_NAME},
            se.{COL_KINRYO},
            se.{COL_BATAIJU},
            se.tansho_odds,
            se.{COL_WAKUBAN},
            se.{COL_SEX},
            se.{COL_BAREI},
            se.{COL_TOZAI_CODE},
            hn_f.bamei AS sire_name,
            lr.last_venue_code,
            lr.last_finish
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_UMA} um ON se.{COL_KETTONUM} = um.{COL_KETTONUM}
        LEFT JOIN {TABLE_KISYU} ks ON se.{COL_KISYUCODE} = ks.{COL_KISYUCODE}
        LEFT JOIN {TABLE_CHOKYOSI} ch ON se.{COL_CHOKYOSICODE} = ch.{COL_CHOKYOSICODE}
        LEFT JOIN {TABLE_SANKU} sk ON se.{COL_KETTONUM} = sk.{COL_KETTONUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_f ON sk.ketto1_hanshoku_toroku_bango = hn_f.hanshoku_toroku_bango
        LEFT JOIN last_race lr ON se.{COL_KETTONUM} = lr.{COL_KETTONUM}
        WHERE se.{COL_RACE_ID} = $1
          AND se.{COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
        ORDER BY se.{COL_UMABAN}
    """

    try:
        rows = await conn.fetch(sql, race_id)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get race entries: race_id={race_id}, error={e}")
        raise


async def get_races_by_date(
    conn: Connection,
    target_date: date,
    venue_code: str | None = None,
    grade_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get race list for a specified date.

    Args:
        conn: Database connection.
        target_date: Target date (date type).
        venue_code: Racecourse code (optional).
        grade_filter: Grade filter (optional).

    Returns:
        List of race information sorted by race number.
    """
    year = str(target_date.year)
    monthday = target_date.strftime("%m%d")
    today = date.today()

    # Base SQL
    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            {COL_RACE_NUM},
            {COL_HASSO_JIKOKU},
            {COL_SHIBA_BABA_CD},
            {COL_DIRT_BABA_CD},
            {COL_TENKO_CD},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} = $2
    """

    params = [year, monthday]
    param_idx = 3

    # Past races: finalized data only; Future races: all registered data
    if target_date < today:
        sql += f" AND {COL_DATA_KUBUN} = ${param_idx}"
        params.append(DATA_KUBUN_KAKUTEI)
        param_idx += 1
    else:
        # Future races: registered('1'), preliminary('2'), post_confirmed('3'), race_card('4'), in_progress('5'), before_final('6')
        sql += f" AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')"

    # Racecourse filter
    if venue_code:
        sql += f" AND {COL_JYOCD} = ${param_idx}"
        params.append(venue_code)
        param_idx += 1

    # Grade filter
    if grade_filter:
        sql += f" AND {COL_GRADE_CD} = ${param_idx}"
        params.append(grade_filter)
        param_idx += 1

    sql += f" ORDER BY {COL_RACE_NUM}"

    try:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get races by date: date={target_date}, error={e}")
        raise


async def get_races_today(
    conn: Connection, venue_code: str | None = None, grade_filter: str | None = None
) -> list[dict[str, Any]]:
    """
    Get today's race list.

    Args:
        conn: Database connection.
        venue_code: Racecourse code (optional).
        grade_filter: Grade filter (optional).

    Returns:
        List of race information sorted by race number.
    """
    today = date.today()
    return await get_races_by_date(conn, today, venue_code, grade_filter)


async def get_race_entry_count(conn: Connection, race_id: str) -> int:
    """
    Get the number of entries in a race.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        Number of race entries.
    """
    # Get all registered races (including future races)
    sql = f"""
        SELECT COUNT(*) as entry_count
        FROM {TABLE_UMA_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return row["entry_count"] if row else 0
    except Exception as e:
        logger.error(f"Failed to get race entry count: race_id={race_id}, error={e}")
        raise


async def get_upcoming_races(
    conn: Connection, days_ahead: int = 7, grade_filter: str | None = None
) -> list[dict[str, Any]]:
    """
    Get race list for the upcoming N days.

    Args:
        conn: Database connection.
        days_ahead: Number of days ahead to retrieve (default: 7 days).
        grade_filter: Grade filter (optional).

    Returns:
        List of race information sorted by race date and race number.
    """
    today = date.today()
    year = str(today.year)
    start_monthday = today.strftime("%m%d")

    # Calculate end date
    from datetime import timedelta

    end_date = today + timedelta(days=days_ahead)
    end_monthday = end_date.strftime("%m%d")

    # Future races may have data_kubun '1'(registered) or '2'(preliminary)
    # so retrieve all registered races, not limited to finalized('7')
    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            {COL_RACE_NUM},
            {COL_HASSO_JIKOKU},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} >= $2
          AND {COL_KAISAI_MONTHDAY} <= $3
    """

    params = [year, start_monthday, end_monthday]

    # Grade filter
    if grade_filter:
        sql += f" AND {COL_GRADE_CD} = $4"
        params.append(grade_filter)

    sql += f" ORDER BY {COL_KAISAI_MONTHDAY}, {COL_RACE_NUM}"

    try:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get upcoming races: days_ahead={days_ahead}, error={e}")
        raise


async def get_race_detail(conn: Connection, race_id: str) -> dict[str, Any] | None:
    """
    Get race detail information (race info + entry list).

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        Race detail dict (race + entries), or None if not found.
    """
    # Race basic information
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        return None

    # Entry list
    entries = await get_race_entries(conn, race_id)

    return {"race": race_info, "entries": entries, "entry_count": len(entries)}


async def check_race_exists(conn: Connection, race_id: str) -> bool:
    """
    Check if a race exists.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        True if race exists, False otherwise.
    """
    # Check all registered races (including future races)
    # data_kubun: 1=registered, 2=preliminary, 3=post_position_confirmed,
    # 4=race_card, 5=in_progress, 6=before_finalized, 7=finalized
    sql = f"""
        SELECT EXISTS(
            SELECT 1 FROM {TABLE_RACE}
            WHERE {COL_RACE_ID} = $1
              AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
        ) AS exists
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return row["exists"] if row else False
    except Exception as e:
        logger.error(f"Failed to check race exists: race_id={race_id}, error={e}")
        raise


async def get_horse_head_to_head(
    conn: Connection, kettonums: list[str], limit: int = 20
) -> list[dict[str, Any]]:
    """
    Get head-to-head race history for multiple horses.

    Args:
        conn: Database connection.
        kettonums: List of pedigree registration numbers.
        limit: Maximum number of past races to retrieve.

    Returns:
        List of past races where target horses competed (with finishing positions).
    """
    if len(kettonums) < 2:
        return []

    # Search for races where 2 or more target horses competed
    sql = f"""
        WITH target_horses AS (
            SELECT {COL_RACE_ID}, {COL_KETTONUM}, {COL_UMABAN}, kakutei_chakujun, {COL_BAMEI}
            FROM {TABLE_UMA_RACE}
            WHERE {COL_KETTONUM} = ANY($1)
              AND {COL_DATA_KUBUN} = $2
              AND kakutei_chakujun IS NOT NULL
              AND kakutei_chakujun::integer > 0
        ),
        race_counts AS (
            SELECT {COL_RACE_ID}, COUNT(DISTINCT {COL_KETTONUM}) as horse_count
            FROM target_horses
            GROUP BY {COL_RACE_ID}
            HAVING COUNT(DISTINCT {COL_KETTONUM}) >= 2
        ),
        matched_races AS (
            SELECT DISTINCT th.{COL_RACE_ID}
            FROM target_horses th
            INNER JOIN race_counts rc ON th.{COL_RACE_ID} = rc.{COL_RACE_ID}
        )
        SELECT
            r.{COL_RACE_ID},
            r.{COL_RACE_NAME},
            r.{COL_KAISAI_YEAR},
            r.{COL_KAISAI_MONTHDAY},
            r.{COL_JYOCD},
            r.{COL_KYORI},
            th.{COL_KETTONUM},
            th.{COL_BAMEI},
            th.{COL_UMABAN},
            th.kakutei_chakujun
        FROM matched_races mr
        INNER JOIN {TABLE_RACE} r ON mr.{COL_RACE_ID} = r.{COL_RACE_ID}
        INNER JOIN target_horses th ON mr.{COL_RACE_ID} = th.{COL_RACE_ID}
        WHERE r.{COL_DATA_KUBUN} = $2
        ORDER BY r.{COL_KAISAI_YEAR} DESC, r.{COL_KAISAI_MONTHDAY} DESC, r.{COL_RACE_ID} DESC
        LIMIT $3
    """

    try:
        rows = await conn.fetch(sql, kettonums, DATA_KUBUN_KAKUTEI, limit * len(kettonums))

        # Group by race
        races_dict: dict[str, dict[str, Any]] = {}
        for row in rows:
            race_id = row[COL_RACE_ID]

            if race_id not in races_dict:
                races_dict[race_id] = {
                    "race_id": race_id,
                    "race_name": row[COL_RACE_NAME],
                    "race_date": f"{row[COL_KAISAI_YEAR]}-{row[COL_KAISAI_MONTHDAY][:2]}-{row[COL_KAISAI_MONTHDAY][2:]}",
                    "venue_code": row[COL_JYOCD],
                    "distance": row[COL_KYORI],
                    "horses": [],
                }

            races_dict[race_id]["horses"].append(
                {
                    "kettonum": row[COL_KETTONUM],
                    "name": row[COL_BAMEI],
                    "horse_number": row[COL_UMABAN],
                    "finish_position": row["kakutei_chakujun"],
                }
            )

        # Convert to list and sort (newest race date first)
        result = list(races_dict.values())
        result.sort(key=lambda x: x["race_date"], reverse=True)

        logger.info(f"Found {len(result)} head-to-head races for {len(kettonums)} horses")
        return result[:limit]

    except Exception as e:
        logger.error(f"Failed to get head-to-head data: {e}")
        raise


async def search_races_by_name_db(
    conn: Connection,
    race_name_query: str,
    days_before: int = 30,
    days_after: int = 30,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Search races by name directly from database with alias support.

    Args:
        conn: Database connection.
        race_name_query: Race name search query (partial match).
        days_before: Number of days to search in the past.
        days_after: Number of days to search in the future.
        limit: Maximum number of results.

    Returns:
        List of matching races.
    """
    from src.services.race_name_aliases import expand_race_name_query

    today = date.today()
    start_date = today - __import__("datetime").timedelta(days=days_before)
    end_date = today + __import__("datetime").timedelta(days=days_after)

    start_year = str(start_date.year)
    start_monthday = start_date.strftime("%m%d")
    end_year = str(end_date.year)
    end_monthday = end_date.strftime("%m%d")

    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {COL_JYOCD},
            {COL_RACE_NUM},
            {COL_GRADE_CD},
            {COL_KYORI},
            {COL_TRACK_CD},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_RACE_NAME} LIKE $1
          AND (
              ({COL_KAISAI_YEAR} > $2 OR ({COL_KAISAI_YEAR} = $2 AND {COL_KAISAI_MONTHDAY} >= $3))
              AND
              ({COL_KAISAI_YEAR} < $4 OR ({COL_KAISAI_YEAR} = $4 AND {COL_KAISAI_MONTHDAY} <= $5))
          )
          AND {COL_DATA_KUBUN} = $6
        ORDER BY {COL_KAISAI_YEAR} DESC, {COL_KAISAI_MONTHDAY} DESC, {COL_RACE_NUM} DESC
        LIMIT $7
    """

    try:
        # Expand aliases (e.g., "Japan Derby" -> ["Japan Derby", "Tokyo Yushun"])
        search_terms = expand_race_name_query(race_name_query)
        logger.info(f"Expanded search terms: {search_terms}")

        all_results = []
        seen_race_ids = set()

        # Search each term (with deduplication)
        for term in search_terms:
            search_pattern = f"%{term}%"
            logger.debug(f"Searching races with pattern: {search_pattern}")

            rows = await conn.fetch(
                sql,
                search_pattern,
                start_year,
                start_monthday,
                end_year,
                end_monthday,
                DATA_KUBUN_KAKUTEI,
                limit,
            )

            for row in rows:
                race_id = row[COL_RACE_ID]
                if race_id in seen_race_ids:
                    continue
                seen_race_ids.add(race_id)
                all_results.append(row)

        # Sort by date (newest first)
        all_results.sort(key=lambda r: (r[COL_KAISAI_YEAR], r[COL_KAISAI_MONTHDAY]), reverse=True)

        # Apply limit
        all_results = all_results[:limit]

        results = []
        for row in all_results:
            year = row[COL_KAISAI_YEAR]
            monthday = row[COL_KAISAI_MONTHDAY]
            race_date = f"{year}-{monthday[:2]}-{monthday[2:]}"

            results.append(
                {
                    "race_id": row[COL_RACE_ID],
                    "race_name": row[COL_RACE_NAME],
                    "race_date": race_date,
                    "venue_code": row[COL_JYOCD],
                    "race_number": row[COL_RACE_NUM],
                    "grade_code": row[COL_GRADE_CD],
                    "distance": row[COL_KYORI],
                    "track_code": row[COL_TRACK_CD],
                    "kyoso_joken_code": row.get("kyoso_joken_code"),
                    "kyoso_shubetsu_code": row.get(COL_KYOSO_SHUBETSU_CD),
                }
            )

        logger.info(f"Found {len(results)} races matching '{race_name_query}'")
        return results

    except Exception as e:
        logger.error(f"Failed to search races by name: {e}")
        raise
