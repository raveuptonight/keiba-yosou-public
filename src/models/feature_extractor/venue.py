"""
Venue and previous race (zenso) query methods.

Contains batch query methods for:
- Venue-specific performance statistics
- Previous race (zenso) detailed information
- Jockey recent performance
- Jockey maiden race performance
"""

import logging
from typing import Any

from .utils import grade_to_rank, safe_int

logger = logging.getLogger(__name__)

# Small track venues (tighter turns)
SMALL_TRACK_VENUES = {"01", "02", "03", "06", "10"}


def get_venue_stats_batch(
    conn, kettonums: list[str], entries: list[dict] | None = None
) -> dict[str, dict]:
    """Batch fetch venue-specific performance stats (data leak prevention version).

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary with keys like "kettonum_05_shiba" (venue_code + surface)
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
        values_parts = []
        params = []  # Start with empty list
        for k in kettonums:
            rc = horse_race_map.get(k, "9999999999999999")
            values_parts.append("(%s, %s)")
            params.extend([k, rc])

        sql = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            )
            SELECT
                u.ketto_toroku_bango,
                r.keibajo_code,
                CASE WHEN r.track_code LIKE '1%%' THEN 'shiba' ELSE 'dirt' END as surface,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.race_code < hf.current_race_code
            GROUP BY u.ketto_toroku_bango, r.keibajo_code, surface
        """
        params.extend(kettonums)  # Add params for WHERE IN
    else:
        # Fallback for prediction mode (use all data)
        sql = f"""
            SELECT
                u.ketto_toroku_bango,
                r.keibajo_code,
                CASE WHEN r.track_code LIKE '1%%' THEN 'shiba' ELSE 'dirt' END as surface,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
            GROUP BY u.ketto_toroku_bango, r.keibajo_code, surface
        """
        params = kettonums

    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        for row in cur.fetchall():
            kettonum = row[0]
            venue_code = row[1]
            surface = row[2]
            runs = int(row[3] or 0)
            wins = int(row[4] or 0)
            places = int(row[5] or 0)
            if runs > 0:
                key = f"{kettonum}_{venue_code}_{surface}"
                result[key] = {"win_rate": wins / runs, "place_rate": places / runs, "runs": runs}
        cur.close()
    except Exception as e:
        logger.warning(f"Venue stats batch failed: {e}")
        conn.rollback()

    return result


def get_zenso_batch(
    conn, kettonums: list[str], race_codes: list[str], entries: list[dict] | None = None
) -> dict[str, dict]:
    """Batch fetch previous race (zenso) information (data leak prevention version).

    Retrieves detailed information about the last 5 races for each horse.

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers
        race_codes: List of current race codes
        entries: Entry list containing race_code (for leak prevention)

    Returns:
        Dictionary mapping kettonum to zenso features
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

        # Get last 5 races for each horse (excluding current race)
        sql = f"""
            WITH horse_filter AS (
                SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
            ),
            with_agari_rank AS (
                SELECT
                    u.ketto_toroku_bango,
                    u.race_code,
                    u.kakutei_chakujun,
                    u.tansho_ninkijun,
                    u.kohan_3f,
                    u.corner1_juni,
                    u.corner2_juni,
                    u.corner3_juni,
                    u.corner4_juni,
                    r.kyori,
                    r.grade_code,
                    r.keibajo_code,
                    RANK() OVER (
                        PARTITION BY u.race_code
                        ORDER BY CAST(NULLIF(u.kohan_3f, '') AS INTEGER)
                    ) as agari_rank
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND u.race_code < hf.current_race_code
            ),
            ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY ketto_toroku_bango
                        ORDER BY race_code DESC
                    ) as rn
                FROM with_agari_rank
            )
            SELECT * FROM ranked WHERE rn <= 5
        """
    else:
        params = kettonums
        # Get last 5 races for each horse
        sql = f"""
            WITH with_agari_rank AS (
                SELECT
                    u.ketto_toroku_bango,
                    u.race_code,
                    u.kakutei_chakujun,
                    u.tansho_ninkijun,
                    u.kohan_3f,
                    u.corner1_juni,
                    u.corner2_juni,
                    u.corner3_juni,
                    u.corner4_juni,
                    r.kyori,
                    r.grade_code,
                    r.keibajo_code,
                    RANK() OVER (
                        PARTITION BY u.race_code
                        ORDER BY CAST(NULLIF(u.kohan_3f, '') AS INTEGER)
                    ) as agari_rank
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
            ),
            ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY ketto_toroku_bango
                        ORDER BY race_code DESC
                    ) as rn
                FROM with_agari_rank
            )
            SELECT * FROM ranked WHERE rn <= 5
        """

    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()

        # Group by horse
        horse_races: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            kettonum = row[0]
            if kettonum not in horse_races:
                horse_races[kettonum] = []
            horse_races[kettonum].append(
                {
                    "race_code": row[1],
                    "chakujun": safe_int(row[2], 10),
                    "ninki": safe_int(row[3], 10),
                    "kohan_3f": safe_int(row[4], 350) / 10.0,
                    "corner1": safe_int(row[5], 8),
                    "corner2": safe_int(row[6], 8),
                    "corner3": safe_int(row[7], 8),
                    "corner4": safe_int(row[8], 8),
                    "kyori": safe_int(row[9], 1600),
                    "grade_code": row[10] or "",
                    "keibajo_code": row[11] or "",
                    "agari_rank": safe_int(row[12], 9),
                }
            )

        # Calculate features for each horse
        for kettonum, races in horse_races.items():
            # Previous races (1st, 2nd, 3rd)
            z1 = races[0] if len(races) > 0 else {}
            z2 = races[1] if len(races) > 1 else {}
            z3 = races[2] if len(races) > 2 else {}

            # Finishing position trend
            if len(races) >= 3:
                c1 = z1.get("chakujun", 10)
                c3 = z3.get("chakujun", 10)
                if c1 < c3 - 2:
                    trend = 1  # Improving
                elif c1 > c3 + 2:
                    trend = -1  # Declining
                else:
                    trend = 0  # Stable
            else:
                trend = 0

            # Final 3F time trend
            agaris = [r.get("kohan_3f", 35.0) for r in races[:3] if r.get("kohan_3f", 0) > 0]
            if len(agaris) >= 3:
                if agaris[0] < agaris[2] - 0.3:
                    agari_trend = 1  # Faster
                elif agaris[0] > agaris[2] + 0.3:
                    agari_trend = -1  # Slower
                else:
                    agari_trend = 0  # Stable
            else:
                agari_trend = 0

            # Small/large track performance
            small_places = 0
            small_runs = 0
            large_places = 0
            large_runs = 0
            for r in races:
                venue = r.get("keibajo_code", "")
                chaku = r.get("chakujun", 99)
                if venue in SMALL_TRACK_VENUES:
                    small_runs += 1
                    if chaku <= 3:
                        small_places += 1
                else:
                    large_runs += 1
                    if chaku <= 3:
                        large_places += 1

            # Final 3F ranking
            zenso1_agari_rank = z1.get("agari_rank", 9)
            zenso2_agari_rank = z2.get("agari_rank", 9)
            z3.get("agari_rank", 9) if len(races) > 2 else 9
            agari_ranks = [r.get("agari_rank", 9) for r in races[:3] if r.get("agari_rank", 0) > 0]
            avg_agari_rank_3 = sum(agari_ranks) / len(agari_ranks) if agari_ranks else 9.0

            # Corner position progression
            def calc_position_changes(race_data):
                c1 = race_data.get("corner1", 8)
                c2 = race_data.get("corner2", 8)
                c3 = race_data.get("corner3", 8)
                c4 = race_data.get("corner4", 8)
                return {
                    "up_1to2": c1 - c2,  # Positive = moved forward
                    "up_2to3": c2 - c3,
                    "up_3to4": c3 - c4,
                    "early_avg": (c1 + c2) / 2.0,
                    "late_avg": (c3 + c4) / 2.0,
                }

            z1_pos = calc_position_changes(z1) if z1 else {}
            calc_position_changes(z2) if z2 else {}

            # Late closing tendency (moved up 3+ positions from corner 3 to 4)
            late_push_count = 0
            for r in races[:5]:
                if r.get("corner3", 8) - r.get("corner4", 8) >= 3:
                    late_push_count += 1
            late_push_tendency = late_push_count / len(races) if races else 0.0

            result[kettonum] = {
                "zenso1_chakujun": z1.get("chakujun", 10),
                "zenso1_ninki": z1.get("ninki", 10),
                "zenso1_agari": z1.get("kohan_3f", 35.0),
                "zenso1_corner_avg": (z1.get("corner3", 8) + z1.get("corner4", 8)) / 2.0,
                "zenso1_distance": z1.get("kyori", 1600),
                "zenso1_grade": grade_to_rank(z1.get("grade_code", "")),
                "zenso2_chakujun": z2.get("chakujun", 10),
                "zenso3_chakujun": z3.get("chakujun", 10),
                "zenso_chakujun_trend": trend,
                "zenso_agari_trend": agari_trend,
                "small_track_rate": small_places / small_runs if small_runs > 0 else 0.25,
                "large_track_rate": large_places / large_runs if large_runs > 0 else 0.25,
                # Final 3F ranking
                "zenso1_agari_rank": zenso1_agari_rank,
                "zenso2_agari_rank": zenso2_agari_rank,
                "avg_agari_rank_3": avg_agari_rank_3,
                # Corner position progression
                "zenso1_position_up_1to2": z1_pos.get("up_1to2", 0),
                "zenso1_position_up_2to3": z1_pos.get("up_2to3", 0),
                "zenso1_position_up_3to4": z1_pos.get("up_3to4", 0),
                "zenso1_early_position_avg": z1_pos.get("early_avg", 8.0),
                "zenso1_late_position_avg": z1_pos.get("late_avg", 8.0),
                "late_push_tendency": late_push_tendency,
            }

        return result
    except Exception as e:
        logger.debug(f"Zenso batch failed: {e}")
        conn.rollback()
        return {}


def get_jockey_recent_batch(conn, jockey_codes: list[str], year: int) -> dict[str, dict]:
    """Batch fetch jockey recent performance (current year).

    Args:
        conn: Database connection
        jockey_codes: List of jockey codes
        year: Target year

    Returns:
        Dictionary mapping jockey_code to recent performance stats
    """
    if not jockey_codes:
        return {}

    unique_codes = list({c for c in jockey_codes if c})
    if not unique_codes:
        return {}

    placeholders = ",".join(["%s"] * len(unique_codes))
    # Current year stats
    sql = f"""
        SELECT
            kishu_code,
            COUNT(*) as runs,
            SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho
        WHERE kishu_code IN ({placeholders})
          AND data_kubun = '7'
          AND kakutei_chakujun ~ '^[0-9]+$'
          AND kaisai_nen = %s
        GROUP BY kishu_code
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, unique_codes + [str(year)])
        for row in cur.fetchall():
            code, runs, wins, places = row
            runs = int(runs or 0)
            result[code] = {
                "win_rate": int(wins or 0) / runs if runs > 0 else 0.08,
                "place_rate": int(places or 0) / runs if runs > 0 else 0.25,
                "runs": runs,
            }
        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Jockey recent batch failed: {e}")
        conn.rollback()
        return {}


def get_jockey_maiden_stats_batch(conn, jockey_codes: list[str], year: int) -> dict[str, dict]:
    """Batch fetch jockey performance in maiden and newcomer races.

    Retrieves jockey performance in maiden/newcomer races from the last 3 years.

    Args:
        conn: Database connection
        jockey_codes: List of jockey codes
        year: Target year

    Returns:
        Dictionary mapping jockey_code to maiden race performance stats
    """
    if not jockey_codes:
        return {}

    unique_codes = list({c for c in jockey_codes if c})
    if not unique_codes:
        return {}

    placeholders = ",".join(["%s"] * len(unique_codes))
    year_from = str(year - 3)  # 3 years of data

    sql = f"""
        SELECT
            u.kishu_code,
            COUNT(*) as runs,
            SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho u
        JOIN race_shosai rs ON u.race_code = rs.race_code AND rs.data_kubun = '7'
        WHERE u.kishu_code IN ({placeholders})
          AND u.data_kubun = '7'
          AND u.kakutei_chakujun ~ '^[0-9]+$'
          AND u.kaisai_nen >= %s
          AND (rs.kyoso_joken_code_2sai IN ('701', '703')
               OR rs.kyoso_joken_code_3sai IN ('701', '703'))
        GROUP BY u.kishu_code
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, unique_codes + [year_from])
        for row in cur.fetchall():
            code, runs, wins, places = row
            runs = int(runs or 0)
            if runs >= 10:  # Minimum 10 rides
                result[code] = {
                    "win_rate": int(wins or 0) / runs if runs > 0 else 0.08,
                    "place_rate": int(places or 0) / runs if runs > 0 else 0.25,
                    "runs": runs,
                }
        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Jockey maiden stats batch failed: {e}")
        conn.rollback()
        return {}
