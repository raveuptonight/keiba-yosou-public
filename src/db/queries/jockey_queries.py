"""
Jockey and Trainer Information Query Module.

Query functions for retrieving jockey and trainer information and statistics.
"""

import logging
from typing import Any

from asyncpg import Connection

from src.config import ML_TRAINING_YEARS_BACK
from src.db.table_names import (
    COL_CHOKYOSICODE,
    COL_DATA_KUBUN,
    COL_JYOCD,
    COL_KAISAI_YEAR,
    COL_KAKUTEI_CHAKUJUN,
    COL_KISYUCODE,
    COL_KYORI,
    COL_RACE_ID,
    COL_TRACK_CD,
    DATA_KUBUN_KAKUTEI,
    TABLE_CHOKYOSI,
    TABLE_KISYU,
    TABLE_RACE,
    TABLE_UMA_RACE,
)

logger = logging.getLogger(__name__)


async def search_jockeys_by_name(
    conn: Connection, name: str, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Search jockeys by name.

    Args:
        conn: Database connection.
        name: Jockey name (partial match).
        limit: Maximum number of results.

    Returns:
        List of jockey information.
    """
    sql = f"""
        SELECT
            {COL_KISYUCODE} as kishu_code,
            kishumei as name,
            kishumei_ryakusho as name_short,
            tozai_shozoku_code,
            seinengappi as birth_date,
            kijo_shikaku_code
        FROM {TABLE_KISYU}
        WHERE {COL_DATA_KUBUN} = $1
          AND massho_kubun != '1'
          AND kishumei LIKE $2
        ORDER BY {COL_KISYUCODE} DESC
        LIMIT $3
    """

    try:
        rows = await conn.fetch(sql, DATA_KUBUN_KAKUTEI, f"%{name}%", limit)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to search jockeys: {e}")
        raise


async def get_jockey_stats(
    conn: Connection, kishu_code: str, years_back: int = ML_TRAINING_YEARS_BACK
) -> dict[str, Any] | None:
    """
    Get detailed jockey statistics.

    Args:
        conn: Database connection.
        kishu_code: Jockey code.
        years_back: Number of years back to retrieve data from.

    Returns:
        Jockey's detailed statistics.
    """
    from datetime import date

    cutoff_year = str(date.today().year - years_back)

    # Get basic information
    basic_sql = f"""
        SELECT
            {COL_KISYUCODE} as kishu_code,
            kishumei as name,
            kishumei_ryakusho as name_short,
            tozai_shozoku_code,
            seinengappi as birth_date,
            kijo_shikaku_code,
            menkyo_kofu_nengappi as license_date
        FROM {TABLE_KISYU}
        WHERE {COL_KISYUCODE} = $1
          AND {COL_DATA_KUBUN} = $2
        LIMIT 1
    """

    try:
        basic_info = await conn.fetchrow(basic_sql, kishu_code, DATA_KUBUN_KAKUTEI)
        if not basic_info:
            return None

        # Aggregate overall statistics
        stats_sql = f"""
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN}::integer <= 2 THEN 1 ELSE 0 END) as top2,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN}::integer <= 3 THEN 1 ELSE 0 END) as top3,

                -- Turf statistics
                COUNT(CASE WHEN r.{COL_TRACK_CD} LIKE '1%' THEN 1 END) as turf_races,
                SUM(CASE WHEN r.{COL_TRACK_CD} LIKE '1%' AND {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as turf_wins,

                -- Dirt statistics
                COUNT(CASE WHEN r.{COL_TRACK_CD} LIKE '2%' THEN 1 END) as dirt_races,
                SUM(CASE WHEN r.{COL_TRACK_CD} LIKE '2%' AND {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as dirt_wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_KISYUCODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
        """

        stats = await conn.fetchrow(stats_sql, kishu_code, DATA_KUBUN_KAKUTEI, cutoff_year)

        # Statistics by distance
        distance_sql = f"""
            SELECT
                CASE
                    WHEN r.{COL_KYORI}::integer <= 1400 THEN 'sprint'
                    WHEN r.{COL_KYORI}::integer <= 1800 THEN 'mile'
                    WHEN r.{COL_KYORI}::integer <= 2200 THEN 'middle'
                    ELSE 'long'
                END as distance_category,
                COUNT(*) as races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_KISYUCODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
            GROUP BY distance_category
        """

        distance_stats = await conn.fetch(distance_sql, kishu_code, DATA_KUBUN_KAKUTEI, cutoff_year)

        # Statistics by racecourse
        venue_sql = f"""
            SELECT
                r.{COL_JYOCD} as venue_code,
                COUNT(*) as races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_KISYUCODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
            GROUP BY r.{COL_JYOCD}
            ORDER BY wins DESC
        """

        venue_stats = await conn.fetch(venue_sql, kishu_code, DATA_KUBUN_KAKUTEI, cutoff_year)

        # Compile results
        return {
            "basic_info": dict(basic_info),
            "overall_stats": dict(stats),
            "distance_stats": [dict(row) for row in distance_stats],
            "venue_stats": [dict(row) for row in venue_stats],
        }

    except Exception as e:
        logger.error(f"Failed to get jockey stats: {e}")
        raise


async def search_trainers_by_name(
    conn: Connection, name: str, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Search trainers by name.

    Args:
        conn: Database connection.
        name: Trainer name (partial match).
        limit: Maximum number of results.

    Returns:
        List of trainer information.
    """
    sql = f"""
        SELECT
            {COL_CHOKYOSICODE} as chokyoshi_code,
            chokyoshimei as name,
            chokyoshimei_ryakusho as name_short,
            tozai_shozoku_code,
            seinengappi as birth_date
        FROM {TABLE_CHOKYOSI}
        WHERE {COL_DATA_KUBUN} = $1
          AND massho_kubun != '1'
          AND chokyoshimei LIKE $2
        ORDER BY {COL_CHOKYOSICODE} DESC
        LIMIT $3
    """

    try:
        rows = await conn.fetch(sql, DATA_KUBUN_KAKUTEI, f"%{name}%", limit)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to search trainers: {e}")
        raise


async def get_trainer_stats(
    conn: Connection, chokyoshi_code: str, years_back: int = ML_TRAINING_YEARS_BACK
) -> dict[str, Any] | None:
    """
    Get detailed trainer statistics.

    Args:
        conn: Database connection.
        chokyoshi_code: Trainer code.
        years_back: Number of years back to retrieve data from.

    Returns:
        Trainer's detailed statistics.
    """
    from datetime import date

    cutoff_year = str(date.today().year - years_back)

    # Get basic information
    basic_sql = f"""
        SELECT
            {COL_CHOKYOSICODE} as chokyoshi_code,
            chokyoshimei as name,
            chokyoshimei_ryakusho as name_short,
            tozai_shozoku_code,
            seinengappi as birth_date,
            menkyo_kofu_nengappi as license_date
        FROM {TABLE_CHOKYOSI}
        WHERE {COL_CHOKYOSICODE} = $1
          AND {COL_DATA_KUBUN} = $2
        LIMIT 1
    """

    try:
        basic_info = await conn.fetchrow(basic_sql, chokyoshi_code, DATA_KUBUN_KAKUTEI)
        if not basic_info:
            return None

        # Aggregate overall statistics
        stats_sql = f"""
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN}::integer <= 2 THEN 1 ELSE 0 END) as top2,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN}::integer <= 3 THEN 1 ELSE 0 END) as top3,

                -- Turf statistics
                COUNT(CASE WHEN r.{COL_TRACK_CD} LIKE '1%' THEN 1 END) as turf_races,
                SUM(CASE WHEN r.{COL_TRACK_CD} LIKE '1%' AND {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as turf_wins,

                -- Dirt statistics
                COUNT(CASE WHEN r.{COL_TRACK_CD} LIKE '2%' THEN 1 END) as dirt_races,
                SUM(CASE WHEN r.{COL_TRACK_CD} LIKE '2%' AND {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as dirt_wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_CHOKYOSICODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
        """

        stats = await conn.fetchrow(stats_sql, chokyoshi_code, DATA_KUBUN_KAKUTEI, cutoff_year)

        # Statistics by distance
        distance_sql = f"""
            SELECT
                CASE
                    WHEN r.{COL_KYORI}::integer <= 1400 THEN 'sprint'
                    WHEN r.{COL_KYORI}::integer <= 1800 THEN 'mile'
                    WHEN r.{COL_KYORI}::integer <= 2200 THEN 'middle'
                    ELSE 'long'
                END as distance_category,
                COUNT(*) as races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_CHOKYOSICODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
            GROUP BY distance_category
        """

        distance_stats = await conn.fetch(
            distance_sql, chokyoshi_code, DATA_KUBUN_KAKUTEI, cutoff_year
        )

        # Statistics by racecourse
        venue_sql = f"""
            SELECT
                r.{COL_JYOCD} as venue_code,
                COUNT(*) as races,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_CHOKYOSICODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
            GROUP BY r.{COL_JYOCD}
            ORDER BY wins DESC
        """

        venue_stats = await conn.fetch(venue_sql, chokyoshi_code, DATA_KUBUN_KAKUTEI, cutoff_year)

        # Top jockeys (most frequently ridden jockeys)
        top_jockeys_sql = f"""
            SELECT
                se.{COL_KISYUCODE} as kishu_code,
                se.kishumei as jockey_name,
                COUNT(*) as rides,
                SUM(CASE WHEN {COL_KAKUTEI_CHAKUJUN} = '1' THEN 1 ELSE 0 END) as wins
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID} AND r.{COL_DATA_KUBUN} = $2
            WHERE se.{COL_CHOKYOSICODE} = $1
              AND se.{COL_DATA_KUBUN} = $2
              AND r.{COL_KAISAI_YEAR} >= $3
            GROUP BY se.{COL_KISYUCODE}, se.kishumei
            ORDER BY rides DESC
            LIMIT 5
        """

        top_jockeys = await conn.fetch(
            top_jockeys_sql, chokyoshi_code, DATA_KUBUN_KAKUTEI, cutoff_year
        )

        # Compile results
        return {
            "basic_info": dict(basic_info),
            "overall_stats": dict(stats),
            "distance_stats": [dict(row) for row in distance_stats],
            "venue_stats": [dict(row) for row in venue_stats],
            "top_jockeys": [dict(row) for row in top_jockeys],
        }

    except Exception as e:
        logger.error(f"Failed to get trainer stats: {e}")
        raise
