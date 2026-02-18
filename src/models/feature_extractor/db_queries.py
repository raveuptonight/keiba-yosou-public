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

SURFACE_FILTERS = {
    "turf": "track_code::int BETWEEN 10 AND 23",
    "dirt": "(track_code::int IN (24, 25, 26, 27) OR track_code = '51')",
}


def get_races(conn, year: int, max_races: int, surface: str | None = None) -> list[dict]:
    """Get race list for a given year.

    Args:
        conn: Database connection
        year: Target year
        max_races: Maximum number of races to retrieve
        surface: Surface filter ("turf", "dirt", or None for all)

    Returns:
        List of race dictionaries with race_code, venue, distance, etc.
    """
    surface_clause = ""
    if surface is not None:
        if surface not in SURFACE_FILTERS:
            raise ValueError(f"Unknown surface: {surface!r}. Use 'turf' or 'dirt'.")
        surface_clause = f" AND {SURFACE_FILTERS[surface]}"

    sql = f"""
        SELECT
            race_code, kaisai_nen, kaisai_gappi, keibajo_code,
            kyori, track_code, grade_code,
            shiba_babajotai_code, dirt_babajotai_code
        FROM race_shosai
        WHERE kaisai_nen = %s AND data_kubun = '7'{surface_clause}
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


def get_past_stats_batch(
    conn, kettonums: list[str], entries: list[dict] | None = None
) -> dict[str, dict]:
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
                MAX(CASE WHEN rn = 1 THEN kaisai_nen || kaisai_gappi END) as last_race_date,
                -- Temporal decay weighted averages (decay_factor=0.85)
                SUM(CAST(kakutei_chakujun AS INTEGER) * POWER(0.85, rn - 1)) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_avg_rank,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN POWER(0.85, rn - 1) ELSE 0 END) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_win_rate,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN POWER(0.85, rn - 1) ELSE 0 END) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_place_rate,
                SUM(CAST(NULLIF(kohan_3f, '') AS INTEGER) * POWER(0.85, rn - 1)) / NULLIF(SUM(CASE WHEN kohan_3f IS NOT NULL AND kohan_3f != '' THEN POWER(0.85, rn - 1) ELSE 0 END), 0) as weighted_avg_last3f,
                -- Corner position progression (3rd corner -> 4th corner)
                AVG(CAST(NULLIF(corner3_juni, '') AS INTEGER) - CAST(NULLIF(corner4_juni, '') AS INTEGER)) as avg_position_change_3to4,
                STDDEV(CAST(NULLIF(corner3_juni, '') AS INTEGER) - CAST(NULLIF(corner4_juni, '') AS INTEGER)) as std_position_change_3to4,
                -- Performance stability
                STDDEV(CAST(kakutei_chakujun AS INTEGER)) as rank_stddev,
                STDDEV(CAST(NULLIF(soha_time, '') AS INTEGER)) as time_stddev,
                STDDEV(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as last3f_stddev
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
                MAX(CASE WHEN rn = 1 THEN kaisai_nen || kaisai_gappi END) as last_race_date,
                -- Temporal decay weighted averages (decay_factor=0.85)
                SUM(CAST(kakutei_chakujun AS INTEGER) * POWER(0.85, rn - 1)) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_avg_rank,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN POWER(0.85, rn - 1) ELSE 0 END) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_win_rate,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN POWER(0.85, rn - 1) ELSE 0 END) / NULLIF(SUM(POWER(0.85, rn - 1)), 0) as weighted_place_rate,
                SUM(CAST(NULLIF(kohan_3f, '') AS INTEGER) * POWER(0.85, rn - 1)) / NULLIF(SUM(CASE WHEN kohan_3f IS NOT NULL AND kohan_3f != '' THEN POWER(0.85, rn - 1) ELSE 0 END), 0) as weighted_avg_last3f,
                -- Corner position progression (3rd corner -> 4th corner)
                AVG(CAST(NULLIF(corner3_juni, '') AS INTEGER) - CAST(NULLIF(corner4_juni, '') AS INTEGER)) as avg_position_change_3to4,
                STDDEV(CAST(NULLIF(corner3_juni, '') AS INTEGER) - CAST(NULLIF(corner4_juni, '') AS INTEGER)) as std_position_change_3to4,
                -- Performance stability
                STDDEV(CAST(kakutei_chakujun AS INTEGER)) as rank_stddev,
                STDDEV(CAST(NULLIF(soha_time, '') AS INTEGER)) as time_stddev,
                STDDEV(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as last3f_stddev
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
            # Temporal decay weighted (Step 1)
            "weighted_avg_rank": float(row[15]) if row[15] else 8.0,
            "weighted_win_rate": float(row[16]) if row[16] else 0.0,
            "weighted_place_rate": float(row[17]) if row[17] else 0.0,
            "weighted_avg_last3f": float(row[18]) / 10.0 if row[18] else 35.0,
            # Corner position progression (Step 2)
            "avg_position_change_3to4": float(row[19]) if row[19] else 0.0,
            "std_position_change_3to4": float(row[20]) if row[20] else 0.0,
            # Performance stability (Step 3)
            "rank_stddev": float(row[21]) if row[21] else 5.0,
            "time_stddev": float(row[22]) if row[22] else 50.0,
            "last3f_stddev": float(row[23]) / 10.0 if row[23] else 2.0,
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
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()

        result = {}
        for row in rows:
            key = f"{row[0]}_{row[1]}"
            result[key] = {"runs": int(row[2] or 0), "wins": int(row[3] or 0)}
        return result
    except Exception as e:
        logger.debug(f"Jockey-horse combo batch failed: {e}")
        conn.rollback()
        return {}
    finally:
        cur.close()


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
    cur = conn.cursor()
    try:
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

        return result
    except Exception as e:
        logger.debug(f"Training batch failed: {e}")
        conn.rollback()
        return {}
    finally:
        cur.close()


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


def get_detailed_stats_batch(
    conn, kettonums: list[str], entries: list[dict] | None = None
) -> dict[str, dict]:
    """Get distance-category, course-direction stats for each horse.

    Computes from umagoto_race_joho (not kyosoba_master2) to avoid data leakage.
    Uses last 20 races per horse.

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary mapping kettonum to detailed stats
    """
    if not kettonums:
        return {}

    horse_race_map = {}
    if entries:
        for e in entries:
            k = e.get("ketto_toroku_bango", "")
            rc = e.get("race_code", "")
            if k and rc:
                horse_race_map[k] = rc

    placeholders = ",".join(["%s"] * len(kettonums))

    if horse_race_map:
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        sql = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            ),
            ranked AS (
                SELECT
                    u.ketto_toroku_bango,
                    u.kakutei_chakujun,
                    r.kyori,
                    r.track_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code DESC
                    ) as rn
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND u.race_code < hf.current_race_code
            )
            SELECT
                ketto_toroku_bango,
                COUNT(CASE WHEN CAST(kyori AS INT) <= 1400 THEN 1 END) as short_runs,
                SUM(CASE WHEN CAST(kyori AS INT) <= 1400 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as short_places,
                COUNT(CASE WHEN CAST(kyori AS INT) BETWEEN 1401 AND 2000 THEN 1 END) as middle_runs,
                SUM(CASE WHEN CAST(kyori AS INT) BETWEEN 1401 AND 2000 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as middle_places,
                COUNT(CASE WHEN CAST(kyori AS INT) > 2000 THEN 1 END) as long_runs,
                SUM(CASE WHEN CAST(kyori AS INT) > 2000 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as long_places,
                COUNT(CASE WHEN track_code::int IN (11,12,21,22) THEN 1 END) as right_runs,
                SUM(CASE WHEN track_code::int IN (11,12,21,22) AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as right_places,
                COUNT(CASE WHEN track_code::int IN (13,14,23,24) THEN 1 END) as left_runs,
                SUM(CASE WHEN track_code::int IN (13,14,23,24) AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as left_places
            FROM ranked
            WHERE rn <= 20
            GROUP BY ketto_toroku_bango
        """
    else:
        params = kettonums
        sql = f"""
            WITH ranked AS (
                SELECT
                    ketto_toroku_bango,
                    kakutei_chakujun,
                    r.kyori,
                    r.track_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY ketto_toroku_bango ORDER BY u.race_code DESC
                    ) as rn
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code
                WHERE ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
            )
            SELECT
                ketto_toroku_bango,
                COUNT(CASE WHEN CAST(kyori AS INT) <= 1400 THEN 1 END) as short_runs,
                SUM(CASE WHEN CAST(kyori AS INT) <= 1400 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as short_places,
                COUNT(CASE WHEN CAST(kyori AS INT) BETWEEN 1401 AND 2000 THEN 1 END) as middle_runs,
                SUM(CASE WHEN CAST(kyori AS INT) BETWEEN 1401 AND 2000 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as middle_places,
                COUNT(CASE WHEN CAST(kyori AS INT) > 2000 THEN 1 END) as long_runs,
                SUM(CASE WHEN CAST(kyori AS INT) > 2000 AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as long_places,
                COUNT(CASE WHEN track_code::int IN (11,12,21,22) THEN 1 END) as right_runs,
                SUM(CASE WHEN track_code::int IN (11,12,21,22) AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as right_places,
                COUNT(CASE WHEN track_code::int IN (13,14,23,24) THEN 1 END) as left_runs,
                SUM(CASE WHEN track_code::int IN (13,14,23,24) AND kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as left_places
            FROM ranked
            WHERE rn <= 20
            GROUP BY ketto_toroku_bango
        """

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    result = {}
    for row in rows:
        result[row[0]] = {
            "short_runs": int(row[1] or 0),
            "short_places": int(row[2] or 0),
            "middle_runs": int(row[3] or 0),
            "middle_places": int(row[4] or 0),
            "long_runs": int(row[5] or 0),
            "long_places": int(row[6] or 0),
            "right_runs": int(row[7] or 0),
            "right_places": int(row[8] or 0),
            "left_runs": int(row[9] or 0),
            "left_places": int(row[10] or 0),
        }

    logger.info(f"  Detailed stats: {len(result)} horses")
    return result


def get_race_lap_stats_batch(
    conn, kettonums: list[str], entries: list[dict] | None = None
) -> dict[str, dict]:
    """Get pace characteristics of each horse's most recent race from lap times.

    Queries race_shosai for lap_time data of each horse's last race,
    then computes front/back pace ratio.

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary mapping kettonum to pace stats
    """
    if not kettonums:
        return {}

    horse_race_map = {}
    if entries:
        for e in entries:
            k = e.get("ketto_toroku_bango", "")
            rc = e.get("race_code", "")
            if k and rc:
                horse_race_map[k] = rc

    placeholders = ",".join(["%s"] * len(kettonums))

    if horse_race_map:
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        sql = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            ),
            last_race AS (
                SELECT DISTINCT ON (u.ketto_toroku_bango)
                    u.ketto_toroku_bango,
                    u.race_code,
                    u.kakutei_chakujun
                FROM umagoto_race_joho u
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND u.race_code < hf.current_race_code
                ORDER BY u.ketto_toroku_bango, u.race_code DESC
            )
            SELECT
                lr.ketto_toroku_bango,
                lr.kakutei_chakujun,
                r.kyori,
                r.lap_time1, r.lap_time2, r.lap_time3, r.lap_time4, r.lap_time5,
                r.lap_time6, r.lap_time7, r.lap_time8, r.lap_time9, r.lap_time10,
                r.lap_time11, r.lap_time12, r.lap_time13, r.lap_time14, r.lap_time15,
                r.lap_time16, r.lap_time17, r.lap_time18, r.lap_time19
            FROM last_race lr
            JOIN race_shosai r ON lr.race_code = r.race_code
        """
    else:
        params = kettonums
        sql = f"""
            WITH last_race AS (
                SELECT DISTINCT ON (ketto_toroku_bango)
                    ketto_toroku_bango,
                    race_code,
                    kakutei_chakujun
                FROM umagoto_race_joho
                WHERE ketto_toroku_bango IN ({placeholders})
                  AND data_kubun = '7'
                  AND kakutei_chakujun ~ '^[0-9]+$'
                ORDER BY ketto_toroku_bango, race_code DESC
            )
            SELECT
                lr.ketto_toroku_bango,
                lr.kakutei_chakujun,
                r.kyori,
                r.lap_time1, r.lap_time2, r.lap_time3, r.lap_time4, r.lap_time5,
                r.lap_time6, r.lap_time7, r.lap_time8, r.lap_time9, r.lap_time10,
                r.lap_time11, r.lap_time12, r.lap_time13, r.lap_time14, r.lap_time15,
                r.lap_time16, r.lap_time17, r.lap_time18, r.lap_time19
            FROM last_race lr
            JOIN race_shosai r ON lr.race_code = r.race_code
        """

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    result = {}
    for row in rows:
        kettonum = row[0]
        chakujun = int(row[1]) if row[1] else 18
        kyori = int(row[2]) if row[2] else 1600
        laps = []
        for i in range(3, 22):  # lap_time1 through lap_time19
            try:
                val = int(row[i]) if row[i] and str(row[i]).strip() else 0
            except (ValueError, TypeError):
                val = 0
            laps.append(val)

        # Compute pace ratio from laps
        n_laps = kyori // 200
        valid_laps = [l for l in laps[:n_laps] if l > 0]
        if len(valid_laps) >= 4:
            mid = len(valid_laps) // 2
            front_avg = sum(valid_laps[:mid]) / mid
            back_avg = sum(valid_laps[mid:]) / (len(valid_laps) - mid)
            pace_ratio = front_avg / back_avg if back_avg > 0 else 1.0
        else:
            pace_ratio = 1.0

        result[kettonum] = {
            "pace_ratio": pace_ratio,
            "zenso1_chakujun": chakujun,
        }

    logger.info(f"  Lap stats: {len(result)} horses")
    return result
