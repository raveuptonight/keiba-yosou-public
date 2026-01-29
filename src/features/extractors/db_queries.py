"""
Database Query Functions for Feature Extraction

Functions for retrieving race, horse, jockey, and training data from the database.
"""

import logging
from datetime import date
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def get_race_entries(conn, race_code: str, data_kubun: str, cache: Dict = None) -> List[Dict]:
    """
    Get list of race entries.

    Args:
        conn: Database connection
        race_code: Race code (16 digits)
        data_kubun: Data classification
        cache: Optional cache dictionary

    Returns:
        List of entry dictionaries
    """
    sql = """
        SELECT
            umaban,
            wakuban,
            ketto_toroku_bango,
            bamei,
            seibetsu_code,
            barei,
            futan_juryo,
            blinker_shiyo_kubun,
            kishu_code,
            chokyoshi_code,
            bataiju,
            zogen_sa,
            tansho_odds,
            tansho_ninkijun,
            kakutei_chakujun,
            soha_time,
            corner1_juni,
            corner2_juni,
            corner3_juni,
            corner4_juni,
            kohan_3f,
            kohan_4f,
            kyakushitsu_hantei
        FROM umagoto_race_joho
        WHERE race_code = %s
          AND data_kubun = %s
        ORDER BY umaban::int
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (race_code, data_kubun))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        cur.close()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get race entries: {e}")
        conn.rollback()
        return []


def get_race_info(conn, race_code: str, data_kubun: str) -> Dict:
    """
    Get basic race information.

    Args:
        conn: Database connection
        race_code: Race code
        data_kubun: Data classification

    Returns:
        Race info dictionary
    """
    sql = """
        SELECT
            race_code,
            kaisai_nen,
            kaisai_gappi,
            keibajo_code,
            race_bango,
            kyori,
            track_code,
            shiba_babajotai_code,
            dirt_babajotai_code,
            tenko_code,
            grade_code
        FROM race_shosai
        WHERE race_code = %s
          AND data_kubun = %s
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (race_code, data_kubun))
        columns = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        cur.close()
        return dict(zip(columns, row)) if row else {}
    except Exception as e:
        logger.error(f"Failed to get race info: {e}")
        conn.rollback()
        return {}


def get_past_races(
    conn,
    kettonum: str,
    current_race_code: str,
    cache: Dict,
    limit: int = 10
) -> List[Dict]:
    """
    Get past race results for a horse.

    Args:
        conn: Database connection
        kettonum: Horse registration number
        current_race_code: Current race code (exclude from results)
        cache: Cache dictionary
        limit: Maximum number of past races

    Returns:
        List of past race dictionaries
    """
    if not kettonum:
        return []

    cache_key = f"past_{kettonum}"
    if cache_key in cache:
        return cache[cache_key]

    sql = """
        SELECT
            race_code,
            kaisai_nen,
            kaisai_gappi,
            keibajo_code,
            kakutei_chakujun,
            soha_time,
            kohan_3f,
            kohan_4f,
            corner1_juni,
            corner2_juni,
            corner3_juni,
            corner4_juni,
            tansho_ninkijun,
            futan_juryo,
            bataiju
        FROM umagoto_race_joho
        WHERE ketto_toroku_bango = %s
          AND data_kubun = '7'
          AND race_code < %s
          AND kakutei_chakujun ~ '^[0-9]+$'
        ORDER BY kaisai_nen DESC, kaisai_gappi DESC
        LIMIT %s
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum, current_race_code, limit))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        cur.close()
        result = [dict(zip(columns, row)) for row in rows]
        cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Failed to get past races: {e}")
        conn.rollback()
        return []


def get_jockey_stats(conn, jockey_code: str, cache: Dict) -> Dict:
    """
    Get jockey statistics.

    Args:
        conn: Database connection
        jockey_code: Jockey code
        cache: Cache dictionary

    Returns:
        Dictionary with win_rate and place_rate
    """
    if not jockey_code:
        return {'win_rate': 0.08, 'place_rate': 0.25}

    cache_key = f"jockey_{jockey_code}"
    if cache_key in cache:
        return cache[cache_key]

    # Aggregate results from past year
    sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01', '02', '03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho
        WHERE kishu_code = %s
          AND data_kubun = '7'
          AND kaisai_nen >= %s
          AND kakutei_chakujun ~ '^[0-9]+$'
    """
    try:
        cur = conn.cursor()
        year_back = str(date.today().year - 1)
        cur.execute(sql, (jockey_code, year_back))
        row = cur.fetchone()
        cur.close()

        if row and row[0] > 0:
            total, wins, places = row
            result = {
                'win_rate': wins / total if total > 0 else 0.08,
                'place_rate': places / total if total > 0 else 0.25
            }
        else:
            result = {'win_rate': 0.08, 'place_rate': 0.25}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Failed to get jockey stats: {e}")
        conn.rollback()
        return {'win_rate': 0.08, 'place_rate': 0.25}


def get_trainer_stats(conn, trainer_code: str, cache: Dict) -> Dict:
    """
    Get trainer statistics.

    Args:
        conn: Database connection
        trainer_code: Trainer code
        cache: Cache dictionary

    Returns:
        Dictionary with win_rate and place_rate
    """
    if not trainer_code:
        return {'win_rate': 0.08, 'place_rate': 0.25}

    cache_key = f"trainer_{trainer_code}"
    if cache_key in cache:
        return cache[cache_key]

    sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01', '02', '03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho
        WHERE chokyoshi_code = %s
          AND data_kubun = '7'
          AND kaisai_nen >= %s
          AND kakutei_chakujun ~ '^[0-9]+$'
    """
    try:
        cur = conn.cursor()
        year_back = str(date.today().year - 1)
        cur.execute(sql, (trainer_code, year_back))
        row = cur.fetchone()
        cur.close()

        if row and row[0] > 0:
            total, wins, places = row
            result = {
                'win_rate': wins / total if total > 0 else 0.08,
                'place_rate': places / total if total > 0 else 0.25
            }
        else:
            result = {'win_rate': 0.08, 'place_rate': 0.25}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Failed to get trainer stats: {e}")
        conn.rollback()
        return {'win_rate': 0.08, 'place_rate': 0.25}


def get_jockey_horse_combo(conn, jockey_code: str, kettonum: str, cache: Dict) -> Dict:
    """
    Get jockey-horse combination statistics.

    Args:
        conn: Database connection
        jockey_code: Jockey code
        kettonum: Horse registration number
        cache: Cache dictionary

    Returns:
        Dictionary with runs and wins
    """
    if not jockey_code or not kettonum:
        return {'runs': 0, 'wins': 0}

    cache_key = f"combo_{jockey_code}_{kettonum}"
    if cache_key in cache:
        return cache[cache_key]

    sql = """
        SELECT
            COUNT(*) as runs,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins
        FROM umagoto_race_joho
        WHERE kishu_code = %s
          AND ketto_toroku_bango = %s
          AND data_kubun = '7'
          AND kakutei_chakujun ~ '^[0-9]+$'
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (jockey_code, kettonum))
        row = cur.fetchone()
        cur.close()

        result = {'runs': row[0] or 0, 'wins': row[1] or 0} if row else {'runs': 0, 'wins': 0}
        cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Failed to get jockey-horse combo: {e}")
        conn.rollback()
        return {'runs': 0, 'wins': 0}


def get_training_data(conn, kettonum: str, race_code: str, cache: Dict) -> Dict:
    """
    Get training data for a horse.

    Args:
        conn: Database connection
        kettonum: Horse registration number
        race_code: Race code
        cache: Cache dictionary

    Returns:
        Dictionary with score, time_4f, and count
    """
    if not kettonum:
        return {'score': 50.0, 'time_4f': 52.0, 'count': 0}

    cache_key = f"training_{kettonum}_{race_code[:8]}"
    if cache_key in cache:
        return cache[cache_key]

    # Get training data within 2 weeks before the race (simplified version)
    sql = """
        SELECT
            COUNT(*) as count,
            AVG(CAST(NULLIF(oikiri_shisu, '') AS INTEGER)) as avg_score
        FROM n_hanro_chokyo
        WHERE ketto_toroku_bango = %s
        LIMIT 10
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum,))
        row = cur.fetchone()
        cur.close()

        if row and row[0] > 0:
            result = {
                'score': float(row[1]) if row[1] else 50.0,
                'time_4f': 52.0,  # TODO: Get actual time
                'count': row[0]
            }
        else:
            result = {'score': 50.0, 'time_4f': 52.0, 'count': 0}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Training data not available: {e}")
        conn.rollback()
        return {'score': 50.0, 'time_4f': 52.0, 'count': 0}


def get_distance_stats(
    conn,
    kettonum: str,
    race_code: str,
    distance: int,
    track_code: str,
    cache: Dict
) -> Dict:
    """
    Get distance-specific statistics (from shussobetsu_kyori table).

    Args:
        conn: Database connection
        kettonum: Horse registration number
        race_code: Race code
        distance: Race distance in meters
        track_code: Track code (1x=turf, 2x=dirt)
        cache: Cache dictionary

    Returns:
        Dictionary with win_rate, place_rate, and runs
    """
    if not kettonum:
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    cache_key = f"dist_stats_{kettonum}_{distance}"
    if cache_key in cache:
        return cache[cache_key]

    # Determine distance category
    is_turf = track_code.startswith('1') if track_code else True
    prefix = 'shiba' if is_turf else 'dirt'

    if distance <= 1200:
        cat = '1200_ika'
    elif distance <= 1400:
        cat = '1201_1400'
    elif distance <= 1600:
        cat = '1401_1600'
    elif distance <= 1800:
        cat = '1601_1800'
    elif distance <= 2000:
        cat = '1801_2000'
    elif distance <= 2200:
        cat = '2001_2200'
    elif distance <= 2400:
        cat = '2201_2400'
    elif distance <= 2800:
        cat = '2401_2800'
    else:
        cat = '2801_ijo'

    col_prefix = f"{prefix}_{cat}"

    sql = f"""
        SELECT
            COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
            COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
            COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
            COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
            COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
            COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
        FROM shussobetsu_kyori
        WHERE ketto_toroku_bango = %s
        ORDER BY data_sakusei_nengappi DESC
        LIMIT 1
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum,))
        row = cur.fetchone()
        cur.close()

        if row:
            wins = row[0]
            places = row[0] + row[1] + row[2]
            total = sum(row)
            result = {
                'win_rate': wins / total if total > 0 else 0.0,
                'place_rate': places / total if total > 0 else 0.0,
                'runs': total
            }
        else:
            result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Distance stats not available: {e}")
        conn.rollback()
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}


def get_baba_stats(
    conn,
    kettonum: str,
    race_code: str,
    track_code: str,
    baba_code: str,
    cache: Dict
) -> Dict:
    """
    Get track condition statistics (from shussobetsu_baba table).

    Args:
        conn: Database connection
        kettonum: Horse registration number
        race_code: Race code
        track_code: Track code (1x=turf, 2x=dirt)
        baba_code: Track condition code (1=good, 2=slightly heavy, 3=heavy, 4=bad)
        cache: Cache dictionary

    Returns:
        Dictionary with win_rate, place_rate, and runs
    """
    if not kettonum:
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    cache_key = f"baba_stats_{kettonum}_{baba_code}"
    if cache_key in cache:
        return cache[cache_key]

    # Determine track condition
    is_turf = track_code.startswith('1') if track_code else True
    prefix = 'shiba' if is_turf else 'dirt'

    # Baba code: 1=good, 2=slightly heavy, 3=heavy, 4=bad
    baba_map = {'1': 'ryo', '2': 'yayaomo', '3': 'omo', '4': 'furyo'}
    baba_suffix = baba_map.get(str(baba_code), 'ryo')
    col_prefix = f"{prefix}_{baba_suffix}"

    sql = f"""
        SELECT
            COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
            COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
            COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
            COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
            COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
            COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
        FROM shussobetsu_baba
        WHERE ketto_toroku_bango = %s
        ORDER BY data_sakusei_nengappi DESC
        LIMIT 1
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum,))
        row = cur.fetchone()
        cur.close()

        if row:
            wins = row[0]
            places = row[0] + row[1] + row[2]
            total = sum(row)
            result = {
                'win_rate': wins / total if total > 0 else 0.0,
                'place_rate': places / total if total > 0 else 0.0,
                'runs': total
            }
        else:
            result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Baba stats not available: {e}")
        conn.rollback()
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}


def get_detailed_training(conn, kettonum: str, race_code: str, cache: Dict) -> Dict:
    """
    Get detailed training data (from hanro_chokyo table).

    Args:
        conn: Database connection
        kettonum: Horse registration number
        race_code: Race code
        cache: Cache dictionary

    Returns:
        Dictionary with time_3f, lap_1f, and days_before
    """
    if not kettonum:
        return {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}

    cache_key = f"detailed_training_{kettonum}_{race_code[:8]}"
    if cache_key in cache:
        return cache[cache_key]

    # Get race date and search for training before that
    race_date = race_code[4:12] if len(race_code) >= 12 else ''

    sql = """
        SELECT
            chokyo_nengappi,
            COALESCE(NULLIF(time_gokei_3furlong, '')::int, 0) as time_3f,
            COALESCE(NULLIF(lap_time_1furlong, '')::int, 0) as lap_1f
        FROM hanro_chokyo
        WHERE ketto_toroku_bango = %s
        ORDER BY chokyo_nengappi DESC
        LIMIT 3
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum,))
        rows = cur.fetchall()
        cur.close()

        if rows:
            # Use most recent training data
            time_3f = rows[0][1] / 10.0 if rows[0][1] else 38.0
            lap_1f = rows[0][2] / 10.0 if rows[0][2] else 12.5
            # Simplified days calculation
            days_before = 3 if rows else 7
            result = {
                'time_3f': time_3f,
                'lap_1f': lap_1f,
                'days_before': days_before
            }
        else:
            result = {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Detailed training not available: {e}")
        conn.rollback()
        return {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}


def get_interval_stats(conn, kettonum: str, interval_cat: str, cache: Dict) -> Dict:
    """
    Get statistics by race interval category.

    Args:
        conn: Database connection
        kettonum: Horse registration number
        interval_cat: Interval category (rentou, week1, week2, week3, week4plus)
        cache: Cache dictionary

    Returns:
        Dictionary with win_rate, place_rate, and runs
    """
    if not kettonum:
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    cache_key = f"interval_{kettonum}_{interval_cat}"
    if cache_key in cache:
        return cache[cache_key]

    # Interval category day ranges
    interval_ranges = {
        'rentou': (1, 7),
        'week1': (8, 14),
        'week2': (15, 21),
        'week3': (22, 28),
        'week4plus': (29, 365)
    }
    min_days, max_days = interval_ranges.get(interval_cat, (29, 365))

    sql = """
        WITH race_intervals AS (
            SELECT
                ketto_toroku_bango,
                kakutei_chakujun,
                DATE(CONCAT(kaisai_nen, '-', SUBSTRING(kaisai_gappi, 1, 2), '-', SUBSTRING(kaisai_gappi, 3, 2)))
                - LAG(DATE(CONCAT(kaisai_nen, '-', SUBSTRING(kaisai_gappi, 1, 2), '-', SUBSTRING(kaisai_gappi, 3, 2))))
                  OVER (PARTITION BY ketto_toroku_bango ORDER BY race_code) as interval_days
            FROM umagoto_race_joho
            WHERE ketto_toroku_bango = %s
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
        )
        SELECT
            COUNT(*) as runs,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM race_intervals
        WHERE interval_days >= %s AND interval_days <= %s
    """
    try:
        cur = conn.cursor()
        cur.execute(sql, (kettonum, min_days, max_days))
        row = cur.fetchone()
        cur.close()

        if row and row[0] > 0:
            runs = int(row[0])
            wins = int(row[1] or 0)
            places = int(row[2] or 0)
            result = {
                'runs': runs,
                'win_rate': wins / runs if runs > 0 else 0.0,
                'place_rate': places / runs if runs > 0 else 0.0
            }
        else:
            result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache[cache_key] = result
        return result
    except Exception as e:
        logger.debug(f"Interval stats not available: {e}")
        conn.rollback()
        return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}
