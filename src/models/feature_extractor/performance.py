"""
Performance statistics query methods.

Contains batch query methods for:
- Surface (turf/dirt) statistics
- Turn direction statistics
- Track condition (baba) statistics
- Interval (rest period) statistics
"""

import logging

logger = logging.getLogger(__name__)


def get_surface_stats_batch(
    conn, kettonums: list[str], entries: list[dict] = None
) -> dict[str, dict]:
    """Batch fetch turf/dirt performance stats (data leak prevention version).

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary with keys like "kettonum_turf" or "kettonum_dirt"
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

    if horse_race_map:
        # Build VALUES clause for per-horse filtering
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        # Turf stats
        sql_turf = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            )
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '1%%'
              AND u.race_code < hf.current_race_code
            GROUP BY u.ketto_toroku_bango
        """
        # Dirt stats
        sql_dirt = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            )
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '2%%'
              AND u.race_code < hf.current_race_code
            GROUP BY u.ketto_toroku_bango
        """
    else:
        params = kettonums
        # Turf stats
        sql_turf = f"""
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '1%%'
            GROUP BY u.ketto_toroku_bango
        """
        # Dirt stats
        sql_dirt = f"""
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '2%%'
            GROUP BY u.ketto_toroku_bango
        """

    result = {}
    try:
        cur = conn.cursor()

        # Turf
        cur.execute(sql_turf, params)
        for row in cur.fetchall():
            kettonum = row[0]
            runs = int(row[1] or 0)
            wins = int(row[2] or 0)
            places = int(row[3] or 0)
            key = f"{kettonum}_turf"
            result[key] = {
                "runs": runs,
                "win_rate": wins / runs if runs > 0 else 0.0,
                "place_rate": places / runs if runs > 0 else 0.0,
            }

        # Dirt
        cur.execute(sql_dirt, params)
        for row in cur.fetchall():
            kettonum = row[0]
            runs = int(row[1] or 0)
            wins = int(row[2] or 0)
            places = int(row[3] or 0)
            key = f"{kettonum}_dirt"
            result[key] = {
                "runs": runs,
                "win_rate": wins / runs if runs > 0 else 0.0,
                "place_rate": places / runs if runs > 0 else 0.0,
            }

        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Surface stats batch failed: {e}")
        conn.rollback()
        return {}


def get_turn_rates_batch(conn, kettonums: list[str]) -> dict[str, dict]:
    """Batch fetch left/right turn performance stats.

    Right-handed courses: Sapporo(01), Hakodate(02), Fukushima(03),
                          Nakayama(06), Kyoto(08), Hanshin(09), Kokura(10)
    Left-handed courses: Niigata(04), Tokyo(05), Chukyo(07)

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers

    Returns:
        Dictionary mapping kettonum to turn performance stats
    """
    if not kettonums:
        return {}

    placeholders = ",".join(["%s"] * len(kettonums))

    sql = f"""
        SELECT
            u.ketto_toroku_bango,
            r.keibajo_code,
            COUNT(*) as runs,
            SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
        WHERE u.ketto_toroku_bango IN ({placeholders})
          AND u.data_kubun = '7'
          AND u.kakutei_chakujun ~ '^[0-9]+$'
        GROUP BY u.ketto_toroku_bango, r.keibajo_code
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, kettonums)
        rows = cur.fetchall()
        cur.close()

        right_courses = {"01", "02", "03", "06", "08", "09", "10"}
        left_courses = {"04", "05", "07"}

        # Aggregate by horse
        horse_stats = {}
        for row in rows:
            kettonum, keibajo, runs, places = row
            if kettonum not in horse_stats:
                horse_stats[kettonum] = {
                    "right_runs": 0,
                    "right_places": 0,
                    "left_runs": 0,
                    "left_places": 0,
                }
            if keibajo in right_courses:
                horse_stats[kettonum]["right_runs"] += int(runs or 0)
                horse_stats[kettonum]["right_places"] += int(places or 0)
            elif keibajo in left_courses:
                horse_stats[kettonum]["left_runs"] += int(runs or 0)
                horse_stats[kettonum]["left_places"] += int(places or 0)

        result = {}
        for kettonum, stats in horse_stats.items():
            r_runs = stats["right_runs"]
            l_runs = stats["left_runs"]
            result[kettonum] = {
                "right_turn_rate": stats["right_places"] / r_runs if r_runs > 0 else 0.25,
                "left_turn_rate": stats["left_places"] / l_runs if l_runs > 0 else 0.25,
                "right_turn_runs": r_runs,
                "left_turn_runs": l_runs,
            }
        return result
    except Exception as e:
        logger.debug(f"Turn rates batch failed: {e}")
        conn.rollback()
        return {}


def get_baba_stats_batch(
    conn, kettonums: list[str], races: list[dict], entries: list[dict] = None
) -> dict[str, dict]:
    """Batch fetch track condition (baba) performance stats (data leak prevention version).

    Track conditions:
    - 1 (ryo): Good/Firm
    - 2 (yayaomo): Slightly Heavy
    - 3 (omo): Heavy
    - 4 (furyo): Bad/Soft

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        races: Race list (for track info)
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary with keys like "kettonum_turf_ryo"
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
    result = {}

    if horse_race_map:
        # Build VALUES clause for per-horse filtering
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        for track, baba_name in [("1", "turf"), ("2", "dirt")]:
            for baba_code, baba_suffix in [
                ("1", "ryo"),
                ("2", "yayaomo"),
                ("3", "omo"),
                ("4", "furyo"),
            ]:
                sql = f"""
                    WITH horse_filter AS (
                        SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                    )
                    SELECT
                        u.ketto_toroku_bango,
                        COUNT(*) as runs,
                        SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                    FROM umagoto_race_joho u
                    JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                    JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND r.track_code LIKE '{track}%%'
                      AND (r.shiba_babajotai_code = '{baba_code}' OR r.dirt_babajotai_code = '{baba_code}')
                      AND u.race_code < hf.current_race_code
                    GROUP BY u.ketto_toroku_bango
                """
                try:
                    cur = conn.cursor()
                    cur.execute(sql, params)
                    for row in cur.fetchall():
                        kettonum = row[0]
                        runs = int(row[1] or 0)
                        wins = int(row[2] or 0)
                        places = int(row[3] or 0)
                        key = f"{kettonum}_{baba_name}_{baba_suffix}"
                        result[key] = {
                            "runs": runs,
                            "win_rate": wins / runs if runs > 0 else 0.0,
                            "place_rate": places / runs if runs > 0 else 0.0,
                        }
                    cur.close()
                except Exception as e:
                    logger.debug(f"Baba stats batch failed for {baba_name}_{baba_suffix}: {e}")
                    conn.rollback()
    else:
        # Fallback for prediction mode
        for track, baba_name in [("1", "turf"), ("2", "dirt")]:
            for baba_code, baba_suffix in [
                ("1", "ryo"),
                ("2", "yayaomo"),
                ("3", "omo"),
                ("4", "furyo"),
            ]:
                sql = f"""
                    SELECT
                        u.ketto_toroku_bango,
                        COUNT(*) as runs,
                        SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                    FROM umagoto_race_joho u
                    JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND r.track_code LIKE '{track}%%'
                      AND (r.shiba_babajotai_code = '{baba_code}' OR r.dirt_babajotai_code = '{baba_code}')
                    GROUP BY u.ketto_toroku_bango
                """
                try:
                    cur = conn.cursor()
                    cur.execute(sql, kettonums)
                    for row in cur.fetchall():
                        kettonum = row[0]
                        runs = int(row[1] or 0)
                        wins = int(row[2] or 0)
                        places = int(row[3] or 0)
                        key = f"{kettonum}_{baba_name}_{baba_suffix}"
                        result[key] = {
                            "runs": runs,
                            "win_rate": wins / runs if runs > 0 else 0.0,
                            "place_rate": places / runs if runs > 0 else 0.0,
                        }
                    cur.close()
                except Exception as e:
                    logger.debug(f"Baba stats batch failed for {baba_name}_{baba_suffix}: {e}")
                    conn.rollback()

    return result


def get_interval_stats_batch(
    conn, kettonums: list[str], entries: list[dict] = None
) -> dict[str, dict]:
    """Batch fetch rest interval performance stats (data leak prevention version).

    Interval categories:
    - rentou: Back-to-back (1-7 days)
    - week1: 1 week rest (8-14 days)
    - week2: 2 weeks rest (15-21 days)
    - week3: 3 weeks rest (22-28 days)
    - week4plus: 4+ weeks rest (29+ days)

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary with keys like "kettonum_week2"
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
    result = {}

    if horse_race_map:
        # Build VALUES clause for per-horse filtering
        values_parts = []
        params = list(kettonums)
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        for interval_name, min_days, max_days in [
            ("rentou", 1, 7),
            ("week1", 8, 14),
            ("week2", 15, 21),
            ("week3", 22, 28),
            ("week4plus", 29, 365),
        ]:
            sql = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                ),
                race_intervals AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.race_code,
                        u.kakutei_chakujun,
                        DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2)))
                        - LAG(DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2))))
                          OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) as interval_days
                    FROM umagoto_race_joho u
                    JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND u.race_code < hf.current_race_code
                )
                SELECT
                    ketto_toroku_bango,
                    COUNT(*) as runs,
                    SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM race_intervals
                WHERE interval_days >= {min_days} AND interval_days <= {max_days}
                GROUP BY ketto_toroku_bango
            """
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                for row in cur.fetchall():
                    kettonum = row[0]
                    runs = int(row[1] or 0)
                    wins = int(row[2] or 0)
                    places = int(row[3] or 0)
                    key = f"{kettonum}_{interval_name}"
                    result[key] = {
                        "runs": runs,
                        "win_rate": wins / runs if runs > 0 else 0.0,
                        "place_rate": places / runs if runs > 0 else 0.0,
                    }
                cur.close()
            except Exception as e:
                logger.debug(f"Interval stats batch failed for {interval_name}: {e}")
                conn.rollback()
    else:
        for interval_name, min_days, max_days in [
            ("rentou", 1, 7),
            ("week1", 8, 14),
            ("week2", 15, 21),
            ("week3", 22, 28),
            ("week4plus", 29, 365),
        ]:
            sql = f"""
                WITH race_intervals AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.kakutei_chakujun,
                        DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2)))
                        - LAG(DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2))))
                          OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) as interval_days
                    FROM umagoto_race_joho u
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                )
                SELECT
                    ketto_toroku_bango,
                    COUNT(*) as runs,
                    SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM race_intervals
                WHERE interval_days >= {min_days} AND interval_days <= {max_days}
                GROUP BY ketto_toroku_bango
            """
            try:
                cur = conn.cursor()
                cur.execute(sql, kettonums)
                for row in cur.fetchall():
                    kettonum = row[0]
                    runs = int(row[1] or 0)
                    wins = int(row[2] or 0)
                    places = int(row[3] or 0)
                    key = f"{kettonum}_{interval_name}"
                    result[key] = {
                        "runs": runs,
                        "win_rate": wins / runs if runs > 0 else 0.0,
                        "place_rate": places / runs if runs > 0 else 0.0,
                    }
                cur.close()
            except Exception as e:
                logger.debug(f"Interval stats batch failed for {interval_name}: {e}")
                conn.rollback()

    return result
