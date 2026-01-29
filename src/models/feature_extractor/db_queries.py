"""
Database query methods for feature extraction.

Contains all batch query methods for retrieving horse racing data:
- Race and entry data
- Past performance statistics
- Jockey/trainer statistics
- Training data
"""

import logging

logger = logging.getLogger(__name__)


def get_races(conn, year: int, max_races: int) -> list[dict]:
    """Get race list for a given year.

    Args:
        conn: Database connection
        year: Target year
        max_races: Maximum number of races to retrieve

    Returns:
        List of race dictionaries with race_code, venue, distance, etc.
    """
    sql = """
        SELECT
            race_code, kaisai_nen, kaisai_gappi, keibajo_code,
            kyori, track_code, grade_code,
            shiba_babajotai_code, dirt_babajotai_code
        FROM race_shosai
        WHERE kaisai_nen = %s AND data_kubun = '7'
        ORDER BY race_code
        LIMIT %s
    """
    cur = conn.cursor()
    cur.execute(sql, (str(year), max_races))
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return [dict(zip(cols, row)) for row in rows]


def get_all_entries(conn, race_codes: list[str]) -> list[dict]:
    """Batch fetch horse entry data for multiple races.

    Args:
        conn: Database connection
        race_codes: List of race codes

    Returns:
        List of entry dictionaries with horse/jockey/race details
    """
    if not race_codes:
        return []

    placeholders = ",".join(["%s"] * len(race_codes))
    sql = f"""
        SELECT
            race_code, umaban, wakuban, ketto_toroku_bango,
            seibetsu_code, barei, futan_juryo,
            blinker_shiyo_kubun, kishu_code, chokyoshi_code,
            bataiju, zogen_sa, kakutei_chakujun,
            soha_time, kohan_3f, kohan_4f,
            corner1_juni, corner2_juni, corner3_juni, corner4_juni
        FROM umagoto_race_joho
        WHERE race_code IN ({placeholders})
          AND data_kubun = '7'
        ORDER BY race_code, umaban::int
    """
    cur = conn.cursor()
    cur.execute(sql, race_codes)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return [dict(zip(cols, row)) for row in rows]


def get_past_stats_batch(conn, kettonums: list[str], entries: list[dict] = None) -> dict[str, dict]:
    """Batch fetch past performance stats (data leak prevention version).

    Retrieves last 10 races for each horse, excluding the current race to prevent data leakage.

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary mapping kettonum to performance stats
    """
    if not kettonums:
        return {}

    # Build horse -> current race_code mapping
    horse_race_map = {}
    if entries:
        for e in entries:
            k = e.get("ketto_toroku_bango", "")
            rc = e.get("race_code", "")
            if k and rc:
                horse_race_map[k] = rc

    placeholders = ",".join(["%s"] * len(kettonums))

    # Add condition to exclude current race
    if horse_race_map:
        # Build VALUES clause for per-horse filtering
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")  # Include all if not found
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        sql = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            ),
            ranked AS (
                SELECT
                    u.ketto_toroku_bango,
                    u.race_code,
                    u.kakutei_chakujun,
                    u.soha_time,
                    u.kohan_3f,
                    u.corner3_juni,
                    u.corner4_juni,
                    u.kishu_code,
                    u.kaisai_nen,
                    u.kaisai_gappi,
                    ROW_NUMBER() OVER (
                        PARTITION BY u.ketto_toroku_bango
                        ORDER BY u.race_code DESC
                    ) as rn
                FROM umagoto_race_joho u
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND u.race_code < hf.current_race_code  -- Only races before current
            )
            SELECT
                ketto_toroku_bango,
                COUNT(*) as race_count,
                AVG(CAST(kakutei_chakujun AS INTEGER)) as avg_rank,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as place_count,
                AVG(CAST(NULLIF(soha_time, '') AS INTEGER)) as avg_time,
                MIN(CAST(NULLIF(soha_time, '') AS INTEGER)) as best_time,
                MAX(CASE WHEN rn = 1 THEN CAST(NULLIF(soha_time, '') AS INTEGER) END) as recent_time,
                AVG(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as avg_last3f,
                MIN(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as best_last3f,
                AVG(CAST(NULLIF(corner3_juni, '') AS INTEGER)) as avg_corner3,
                AVG(CAST(NULLIF(corner4_juni, '') AS INTEGER)) as avg_corner4,
                MIN(CAST(kakutei_chakujun AS INTEGER)) as best_finish,
                MAX(CASE WHEN rn = 1 THEN kishu_code END) as last_jockey,
                MAX(CASE WHEN rn = 1 THEN kaisai_nen || kaisai_gappi END) as last_race_date
            FROM ranked
            WHERE rn <= 10
            GROUP BY ketto_toroku_bango
        """
    else:
        # Fallback for prediction mode (no entries provided)
        params = kettonums
        sql = f"""
            WITH ranked AS (
                SELECT
                    ketto_toroku_bango,
                    kakutei_chakujun,
                    soha_time,
                    kohan_3f,
                    corner3_juni,
                    corner4_juni,
                    kishu_code,
                    kaisai_nen,
                    kaisai_gappi,
                    ROW_NUMBER() OVER (
                        PARTITION BY ketto_toroku_bango
                        ORDER BY race_code DESC
                    ) as rn
                FROM umagoto_race_joho
                WHERE ketto_toroku_bango IN ({placeholders})
                  AND data_kubun = '7'
                  AND kakutei_chakujun ~ '^[0-9]+$'
            )
            SELECT
                ketto_toroku_bango,
                COUNT(*) as race_count,
                AVG(CAST(kakutei_chakujun AS INTEGER)) as avg_rank,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as place_count,
                AVG(CAST(NULLIF(soha_time, '') AS INTEGER)) as avg_time,
                MIN(CAST(NULLIF(soha_time, '') AS INTEGER)) as best_time,
                MAX(CASE WHEN rn = 1 THEN CAST(NULLIF(soha_time, '') AS INTEGER) END) as recent_time,
                AVG(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as avg_last3f,
                MIN(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as best_last3f,
                AVG(CAST(NULLIF(corner3_juni, '') AS INTEGER)) as avg_corner3,
                AVG(CAST(NULLIF(corner4_juni, '') AS INTEGER)) as avg_corner4,
                MIN(CAST(kakutei_chakujun AS INTEGER)) as best_finish,
                MAX(CASE WHEN rn = 1 THEN kishu_code END) as last_jockey,
                MAX(CASE WHEN rn = 1 THEN kaisai_nen || kaisai_gappi END) as last_race_date
            FROM ranked
            WHERE rn <= 10
            GROUP BY ketto_toroku_bango
        """

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    result = {}
    for row in rows:
        kettonum = row[0]
        race_count = int(row[1] or 0)
        avg_time = float(row[5]) if row[5] else None
        best_time = float(row[6]) if row[6] else None
        recent_time = float(row[7]) if row[7] else None

        result[kettonum] = {
            "race_count": race_count,
            "avg_rank": float(row[2]) if row[2] else 8.0,
            "win_rate": int(row[3] or 0) / race_count if race_count > 0 else 0,
            "place_rate": int(row[4] or 0) / race_count if race_count > 0 else 0,
            "win_count": int(row[3] or 0),
            "avg_time": avg_time,
            "best_time": best_time,
            "recent_time": recent_time,
            "avg_last3f": float(row[8] or 350) / 10.0,
            "best_last3f": float(row[9] or 350) / 10.0 if row[9] else 35.0,
            "avg_corner3": float(row[10]) if row[10] else 8.0,
            "avg_corner4": float(row[11]) if row[11] else 8.0,
            "best_finish": int(row[12]) if row[12] else 10,
            "last_jockey": row[13],
            "last_race_date": row[14],
        }

    return result


def get_jockey_horse_combo_batch(conn, pairs: list[tuple[str, str]]) -> dict[str, dict]:
    """Batch fetch jockey-horse combination performance.

    Args:
        conn: Database connection
        pairs: List of (jockey_code, kettonum) tuples

    Returns:
        Dictionary mapping "jockey_kettonum" to {runs, wins}
    """
    if not pairs:
        return {}

    unique_pairs = list(set(pairs))
    if len(unique_pairs) == 0:
        return {}

    # Build OR conditions for query
    conditions = []
    params = []
    for jockey, kettonum in unique_pairs[:1000]:  # Limit to 1000 pairs
        if jockey and kettonum:
            conditions.append("(kishu_code = %s AND ketto_toroku_bango = %s)")
            params.extend([jockey, kettonum])

    if not conditions:
        return {}

    sql = f"""
        SELECT
            kishu_code,
            ketto_toroku_bango,
            COUNT(*) as runs,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins
        FROM umagoto_race_joho
        WHERE ({' OR '.join(conditions)})
          AND data_kubun = '7'
          AND kakutei_chakujun ~ '^[0-9]+$'
        GROUP BY kishu_code, ketto_toroku_bango
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()

        result = {}
        for row in rows:
            key = f"{row[0]}_{row[1]}"
            result[key] = {"runs": int(row[2] or 0), "wins": int(row[3] or 0)}
        return result
    except Exception as e:
        logger.debug(f"Jockey-horse combo batch failed: {e}")
        conn.rollback()
        return {}


def get_training_stats_batch(conn, kettonums: list[str]) -> dict[str, dict]:
    """Batch fetch training data (hanro_chokyo + woodchip_chokyo).

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers

    Returns:
        Dictionary mapping kettonum to training stats
    """
    if not kettonums:
        return {}

    placeholders = ",".join(["%s"] * len(kettonums))

    # Slope training data
    sql_hanro = f"""
        SELECT
            ketto_toroku_bango,
            COUNT(*) as count,
            AVG(CAST(NULLIF(time_gokei_4furlong, '') AS INTEGER)) as avg_4f,
            AVG(CAST(NULLIF(time_gokei_3furlong, '') AS INTEGER)) as avg_3f,
            AVG(CAST(NULLIF(lap_time_1furlong, '') AS INTEGER)) as avg_1f
        FROM hanro_chokyo
        WHERE ketto_toroku_bango IN ({placeholders})
        GROUP BY ketto_toroku_bango
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql_hanro, kettonums)
        rows = cur.fetchall()

        for row in rows:
            kettonum = row[0]
            count = int(row[1] or 0)
            avg_4f = float(row[2]) / 10.0 if row[2] else 52.0
            avg_3f = float(row[3]) / 10.0 if row[3] else 38.0
            avg_1f = float(row[4]) / 10.0 if row[4] else 12.5

            # Training score (from 4F time: faster = higher score)
            # Base: 52sec = 50pts, +5pts per second faster
            score = 50.0 + (52.0 - avg_4f) * 5.0
            score = max(30.0, min(80.0, score))

            result[kettonum] = {
                "count": count,
                "score": score,
                "time_4f": avg_4f,
                "time_3f": avg_3f,
                "lap_1f": avg_1f,
                "days_before": 7,
            }

        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Training batch failed: {e}")
        conn.rollback()
        return {}


def cache_jockey_trainer_stats(conn, year: int) -> tuple[dict, dict]:
    """Cache jockey and trainer statistics.

    Aggregates performance stats from the previous year.

    Args:
        conn: Database connection
        year: Target year

    Returns:
        Tuple of (jockey_cache, trainer_cache) dictionaries
    """
    year_back = str(year - 1)
    jockey_cache = {}
    trainer_cache = {}

    # Jockey stats
    sql = """
        SELECT
            kishu_code,
            COUNT(*) as total,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho
        WHERE data_kubun = '7'
          AND kaisai_nen >= %s
          AND kaisai_nen < %s
          AND kakutei_chakujun ~ '^[0-9]+$'
        GROUP BY kishu_code
    """
    cur = conn.cursor()
    cur.execute(sql, (year_back, str(year)))
    for row in cur.fetchall():
        code, total, wins, places = row
        if code and total > 0:
            jockey_cache[code] = {"win_rate": wins / total, "place_rate": places / total}
    cur.close()

    # Trainer stats
    sql = """
        SELECT
            chokyoshi_code,
            COUNT(*) as total,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho
        WHERE data_kubun = '7'
          AND kaisai_nen >= %s
          AND kaisai_nen < %s
          AND kakutei_chakujun ~ '^[0-9]+$'
        GROUP BY chokyoshi_code
    """
    cur = conn.cursor()
    cur.execute(sql, (year_back, str(year)))
    for row in cur.fetchall():
        code, total, wins, places = row
        if code and total > 0:
            trainer_cache[code] = {"win_rate": wins / total, "place_rate": places / total}
    cur.close()

    logger.info(f"  Jockey cache: {len(jockey_cache)}, Trainer cache: {len(trainer_cache)}")
    return jockey_cache, trainer_cache
