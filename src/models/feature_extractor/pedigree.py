"""
Pedigree and sire statistics query methods.

Contains batch query methods for:
- Pedigree information (sire, broodmare sire)
- Sire offspring performance statistics
- Sire maiden race statistics
"""

import logging

logger = logging.getLogger(__name__)


def get_pedigree_batch(conn, kettonums: list[str]) -> dict[str, dict]:
    """Batch fetch pedigree information (sire and broodmare sire IDs).

    Args:
        conn: Database connection
        kettonums: List of horse registration numbers

    Returns:
        Dictionary mapping kettonum to pedigree info {sire_id, broodmare_sire_id}
    """
    if not kettonums:
        return {}

    placeholders = ','.join(['%s'] * len(kettonums))
    sql = f"""
        SELECT
            ketto_toroku_bango,
            ketto1_hanshoku_toroku_bango as sire_id,
            ketto3_hanshoku_toroku_bango as broodmare_sire_id
        FROM kyosoba_master2
        WHERE ketto_toroku_bango IN ({placeholders})
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, kettonums)
        for row in cur.fetchall():
            kettonum, sire_id, bms_id = row
            result[kettonum] = {
                'sire_id': sire_id or '',
                'broodmare_sire_id': bms_id or ''
            }
        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Pedigree batch failed: {e}")
        conn.rollback()
        return {}


def get_sire_stats_batch(conn, sire_ids: list[str], year: int, is_turf: bool = True) -> dict[str, dict]:
    """Batch fetch sire offspring performance statistics.

    Retrieves aggregated performance of sire's offspring from the last 3 years.

    Args:
        conn: Database connection
        sire_ids: List of sire IDs
        year: Target year
        is_turf: Whether querying turf or dirt stats (currently returns same data for both)

    Returns:
        Dictionary with keys like "sire_id_turf" or "sire_id_dirt"
    """
    if not sire_ids:
        return {}

    unique_ids = list({s for s in sire_ids if s})
    if not unique_ids:
        return {}

    # Limit to 1000 sires
    unique_ids = unique_ids[:1000]
    placeholders = ','.join(['%s'] * len(unique_ids))
    year_from = str(year - 3)

    sql = f"""
        SELECT
            k.ketto1_hanshoku_toroku_bango as sire_id,
            COUNT(*) as runs,
            SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho u
        JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
        WHERE k.ketto1_hanshoku_toroku_bango IN ({placeholders})
          AND u.data_kubun = '7'
          AND u.kakutei_chakujun ~ '^[0-9]+$'
          AND u.kaisai_nen >= %s
        GROUP BY k.ketto1_hanshoku_toroku_bango
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, unique_ids + [year_from])
        for row in cur.fetchall():
            sire_id, runs, wins, places = row
            runs = int(runs or 0)
            # Set same value for both turf and dirt (simplified version)
            for surface in ['turf', 'dirt']:
                key = f"{sire_id}_{surface}"
                result[key] = {
                    'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                    'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                    'runs': runs
                }
        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Sire stats batch failed: {e}")
        conn.rollback()
        return {}


def get_sire_maiden_stats_batch(conn, sire_ids: list[str], year: int) -> dict[str, dict]:
    """Batch fetch sire performance in maiden and newcomer races.

    Retrieves aggregated performance of sire's offspring in maiden/newcomer races
    from the last 5 years.

    Args:
        conn: Database connection
        sire_ids: List of sire IDs
        year: Target year

    Returns:
        Dictionary mapping sire_id to performance stats
    """
    if not sire_ids:
        return {}

    unique_ids = list({s for s in sire_ids if s})
    if not unique_ids:
        return {}

    # Limit to 1000 sires
    unique_ids = unique_ids[:1000]
    placeholders = ','.join(['%s'] * len(unique_ids))
    year_from = str(year - 5)  # 5 years of maiden race data

    sql = f"""
        SELECT
            k.ketto1_hanshoku_toroku_bango as sire_id,
            COUNT(*) as runs,
            SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
        FROM umagoto_race_joho u
        JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
        JOIN race_shosai rs ON u.race_code = rs.race_code AND rs.data_kubun = '7'
        WHERE k.ketto1_hanshoku_toroku_bango IN ({placeholders})
          AND u.data_kubun = '7'
          AND u.kakutei_chakujun ~ '^[0-9]+$'
          AND u.kaisai_nen >= %s
          AND (rs.kyoso_joken_code_2sai IN ('701', '703')
               OR rs.kyoso_joken_code_3sai IN ('701', '703'))
        GROUP BY k.ketto1_hanshoku_toroku_bango
    """
    result = {}
    try:
        cur = conn.cursor()
        cur.execute(sql, unique_ids + [year_from])
        for row in cur.fetchall():
            sire_id, runs, wins, places = row
            runs = int(runs or 0)
            if runs >= 5:  # Only include sires with 5+ offspring runners
                result[sire_id] = {
                    'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                    'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                    'runs': runs
                }
        cur.close()
        return result
    except Exception as e:
        logger.debug(f"Sire maiden stats batch failed: {e}")
        conn.rollback()
        return {}
