"""
Video Export Query Module.

Database queries for the video JSON exporter:
horse past races, jockey/horse course stats, waku/pace bias, and weekly accuracy.
"""

import logging
from typing import Any

from asyncpg import Connection

from src.db.table_names import (
    COL_DATA_KUBUN,
    COL_JYOCD,
    COL_KAISAI_KAI,
    COL_KAISAI_MONTHDAY,
    COL_KAISAI_YEAR,
    COL_KETTONUM,
    COL_KISYUCODE,
    COL_KYORI,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_RACE_NUM,
    COL_TRACK_CD,
    COL_UMABAN,
    DATA_KUBUN_KAKUTEI,
    TABLE_KISYU,
    TABLE_RACE,
    TABLE_UMA_RACE,
)

logger = logging.getLogger(__name__)


async def get_horse_past_races(
    conn: Connection, ketto_toroku_bango: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Get recent race results for a horse.

    Args:
        conn: Database connection.
        ketto_toroku_bango: Pedigree registration number.
        limit: Max number of past races to retrieve.

    Returns:
        List of past race dicts sorted by most recent first.
    """
    sql = f"""
        SELECT
            se.{COL_RACE_ID},
            r.{COL_RACE_NAME},
            r.{COL_KAISAI_YEAR},
            r.{COL_KAISAI_MONTHDAY},
            r.{COL_JYOCD},
            r.{COL_KYORI},
            r.{COL_TRACK_CD},
            r.grade_code,
            se.kakutei_chakujun,
            se.tansho_odds,
            se.ninki_jun,
            se.soha_time,
            se.kohan_3f,
            se.{COL_UMABAN},
            se.futan_juryo,
            ks.kishumei
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID}
            AND r.{COL_DATA_KUBUN} = $2
        LEFT JOIN {TABLE_KISYU} ks ON se.{COL_KISYUCODE} = ks.{COL_KISYUCODE}
        WHERE se.{COL_KETTONUM} = $1
          AND se.{COL_DATA_KUBUN} = $2
          AND se.kakutei_chakujun IS NOT NULL
        ORDER BY r.{COL_KAISAI_YEAR} DESC, r.{COL_KAISAI_MONTHDAY} DESC
        LIMIT $3
    """

    try:
        rows = await conn.fetch(sql, ketto_toroku_bango, DATA_KUBUN_KAKUTEI, limit)
        results = []
        for row in rows:
            year = row[COL_KAISAI_YEAR]
            monthday = row[COL_KAISAI_MONTHDAY]
            results.append(
                {
                    "race_code": row[COL_RACE_ID],
                    "race_name": (row[COL_RACE_NAME] or "").strip(),
                    "race_date": f"{year}-{monthday[:2]}-{monthday[2:]}",
                    "venue_code": row[COL_JYOCD],
                    "distance": row[COL_KYORI],
                    "track_code": row[COL_TRACK_CD],
                    "grade_code": row["grade_code"],
                    "finish": row["kakutei_chakujun"],
                    "odds": row["tansho_odds"],
                    "popularity": row["ninki_jun"],
                    "time": row["soha_time"],
                    "last_3f": row["kohan_3f"],
                    "horse_number": row[COL_UMABAN],
                    "weight": row["futan_juryo"],
                    "jockey": (row["kishumei"] or "").strip(),
                }
            )
        return results
    except Exception as e:
        logger.error(f"Failed to get horse past races: {ketto_toroku_bango}, error={e}")
        raise


async def get_jockey_course_stats(
    conn: Connection,
    kishu_code: str,
    keibajo_code: str,
    track_code: str,
    kyori: int,
) -> dict[str, Any]:
    """Get jockey stats for a specific course.

    Args:
        conn: Database connection.
        kishu_code: Jockey code.
        keibajo_code: Racecourse code.
        track_code: Track code (turf/dirt).
        kyori: Distance.

    Returns:
        Dict with win_count, place_count, runs, win_rate, place_rate.
    """
    # Distance range: +/- 200m
    dist_min = kyori - 200
    dist_max = kyori + 200

    sql = f"""
        SELECT
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun = '01') AS win_count,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun IN ('01','02','03')) AS place_count
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID}
            AND r.{COL_DATA_KUBUN} = $5
        WHERE se.{COL_KISYUCODE} = $1
          AND r.{COL_JYOCD} = $2
          AND r.{COL_TRACK_CD} LIKE $3
          AND r.{COL_KYORI}::int BETWEEN $4 AND $6
          AND se.{COL_DATA_KUBUN} = $5
          AND se.kakutei_chakujun IS NOT NULL
    """

    try:
        row = await conn.fetchrow(
            sql, kishu_code, keibajo_code, f"{track_code}%", dist_min, DATA_KUBUN_KAKUTEI, dist_max
        )
        runs = row["runs"] if row else 0
        win_count = row["win_count"] if row else 0
        place_count = row["place_count"] if row else 0
        return {
            "runs": runs,
            "win_count": win_count,
            "place_count": place_count,
            "win_rate": round(win_count / runs, 3) if runs > 0 else 0.0,
            "place_rate": round(place_count / runs, 3) if runs > 0 else 0.0,
        }
    except Exception as e:
        logger.error(f"Failed to get jockey course stats: {kishu_code}, error={e}")
        raise


async def get_horse_course_stats(
    conn: Connection,
    ketto_toroku_bango: str,
    keibajo_code: str,
    track_code: str,
    kyori: int,
) -> dict[str, Any]:
    """Get horse stats for a specific course.

    Args:
        conn: Database connection.
        ketto_toroku_bango: Pedigree registration number.
        keibajo_code: Racecourse code.
        track_code: Track code (turf/dirt).
        kyori: Distance.

    Returns:
        Dict with win_count, place_count, runs, win_rate, place_rate.
    """
    dist_min = kyori - 200
    dist_max = kyori + 200

    sql = f"""
        SELECT
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun = '01') AS win_count,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun IN ('01','02','03')) AS place_count
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID}
            AND r.{COL_DATA_KUBUN} = $5
        WHERE se.{COL_KETTONUM} = $1
          AND r.{COL_JYOCD} = $2
          AND r.{COL_TRACK_CD} LIKE $3
          AND r.{COL_KYORI}::int BETWEEN $4 AND $6
          AND se.{COL_DATA_KUBUN} = $5
          AND se.kakutei_chakujun IS NOT NULL
    """

    try:
        row = await conn.fetchrow(
            sql,
            ketto_toroku_bango,
            keibajo_code,
            f"{track_code}%",
            dist_min,
            DATA_KUBUN_KAKUTEI,
            dist_max,
        )
        runs = row["runs"] if row else 0
        win_count = row["win_count"] if row else 0
        place_count = row["place_count"] if row else 0
        return {
            "runs": runs,
            "win_count": win_count,
            "place_count": place_count,
            "win_rate": round(win_count / runs, 3) if runs > 0 else 0.0,
            "place_rate": round(place_count / runs, 3) if runs > 0 else 0.0,
        }
    except Exception as e:
        logger.error(f"Failed to get horse course stats: {ketto_toroku_bango}, error={e}")
        raise


async def get_waku_bias(
    conn: Connection,
    keibajo_code: str,
    track_code: str,
    kaisai_nen: str,
    kaisai_kai: str,
) -> dict[str, Any]:
    """Get waku (gate) bias for the current meeting.

    Aggregates win/place rates by wakuban for the specified meeting.

    Args:
        conn: Database connection.
        keibajo_code: Racecourse code.
        track_code: Track code.
        kaisai_nen: Meeting year.
        kaisai_kai: Meeting number.

    Returns:
        Dict mapping wakuban to stats {runs, win_count, place_count, win_rate, place_rate}.
    """
    sql = f"""
        SELECT
            se.wakuban,
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun = '01') AS win_count,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun IN ('01','02','03')) AS place_count
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID}
            AND r.{COL_DATA_KUBUN} = $4
        WHERE r.{COL_JYOCD} = $1
          AND r.{COL_TRACK_CD} LIKE $2
          AND r.{COL_KAISAI_YEAR} = $3
          AND r.{COL_KAISAI_KAI} = $5
          AND se.{COL_DATA_KUBUN} = $4
          AND se.kakutei_chakujun IS NOT NULL
        GROUP BY se.wakuban
        ORDER BY se.wakuban
    """

    try:
        rows = await conn.fetch(
            sql, keibajo_code, f"{track_code}%", kaisai_nen, DATA_KUBUN_KAKUTEI, kaisai_kai
        )
        result = {}
        for row in rows:
            waku = row["wakuban"]
            runs = row["runs"]
            win_count = row["win_count"]
            place_count = row["place_count"]
            result[waku] = {
                "runs": runs,
                "win_count": win_count,
                "place_count": place_count,
                "win_rate": round(win_count / runs, 3) if runs > 0 else 0.0,
                "place_rate": round(place_count / runs, 3) if runs > 0 else 0.0,
            }
        return result
    except Exception as e:
        logger.error(f"Failed to get waku bias: {keibajo_code}, error={e}")
        raise


async def get_pace_bias(
    conn: Connection,
    keibajo_code: str,
    track_code: str,
    kaisai_nen: str,
    kaisai_kai: str,
) -> dict[str, Any]:
    """Get pace bias for the current meeting.

    Analyzes how front-runners vs. closers perform at the meeting.

    Args:
        conn: Database connection.
        keibajo_code: Racecourse code.
        track_code: Track code.
        kaisai_nen: Meeting year.
        kaisai_kai: Meeting number.

    Returns:
        Dict with front/mid/rear runner stats.
    """
    # Use 4th corner position to classify running style
    sql = f"""
        SELECT
            CASE
                WHEN se.corner_4::int <= 3 THEN 'front'
                WHEN se.corner_4::int <= 8 THEN 'mid'
                ELSE 'rear'
            END AS position_group,
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE se.kakutei_chakujun IN ('01','02','03')) AS place_count
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_RACE} r ON se.{COL_RACE_ID} = r.{COL_RACE_ID}
            AND r.{COL_DATA_KUBUN} = $4
        WHERE r.{COL_JYOCD} = $1
          AND r.{COL_TRACK_CD} LIKE $2
          AND r.{COL_KAISAI_YEAR} = $3
          AND r.{COL_KAISAI_KAI} = $5
          AND se.{COL_DATA_KUBUN} = $4
          AND se.kakutei_chakujun IS NOT NULL
          AND se.corner_4 IS NOT NULL
          AND se.corner_4 != ''
          AND se.corner_4 != '0'
        GROUP BY position_group
        ORDER BY position_group
    """

    try:
        rows = await conn.fetch(
            sql, keibajo_code, f"{track_code}%", kaisai_nen, DATA_KUBUN_KAKUTEI, kaisai_kai
        )
        result = {}
        for row in rows:
            group = row["position_group"]
            runs = row["runs"]
            place_count = row["place_count"]
            result[group] = {
                "runs": runs,
                "place_count": place_count,
                "place_rate": round(place_count / runs, 3) if runs > 0 else 0.0,
            }
        return result
    except Exception as e:
        logger.error(f"Failed to get pace bias: {keibajo_code}, error={e}")
        raise


async def get_last_week_accuracy(
    conn: Connection, target_date: str
) -> dict[str, Any] | None:
    """Get last week's prediction accuracy from analysis_results table.

    Args:
        conn: Database connection.
        target_date: Target date (YYYY-MM-DD) to find the previous week's analysis.

    Returns:
        Dict with accuracy summary, or None if not found.
    """
    sql = """
        SELECT
            analysis_date,
            analysis_type,
            metrics
        FROM analysis_results
        WHERE analysis_date < $1::date
          AND analysis_type = 'weekly'
        ORDER BY analysis_date DESC
        LIMIT 1
    """

    try:
        row = await conn.fetchrow(sql, target_date)
        if not row:
            return None
        return {
            "analysis_date": str(row["analysis_date"]),
            "analysis_type": row["analysis_type"],
            "metrics": row["metrics"],
        }
    except Exception as e:
        logger.warning(f"Failed to get last week accuracy (may not exist): {e}")
        return None
