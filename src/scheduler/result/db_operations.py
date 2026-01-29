"""
Database Operations Module

Functions for retrieving race results, payouts, and predictions from database,
and saving analysis results.
"""

import json
import logging
from datetime import date, timedelta

from src.db.connection import get_db

logger = logging.getLogger(__name__)

# Venue code mapping
KEIBAJO_NAMES = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
    '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
}


def get_race_results(target_date: date) -> list[dict]:
    """
    Get race results for a specific date.

    Args:
        target_date: Target date

    Returns:
        List of race result dictionaries
    """
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        kaisai_gappi = target_date.strftime("%m%d")
        kaisai_nen = str(target_date.year)

        # Get races with confirmed or provisional results
        # data_kubun: 6=provisional (all horses+passing order), 7=confirmed results
        cur.execute('''
            SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                   r.kyori, r.track_code
            FROM race_shosai r
            WHERE r.kaisai_nen = %s
              AND r.kaisai_gappi = %s
              AND r.data_kubun IN ('6', '7')
            ORDER BY r.race_code
        ''', (kaisai_nen, kaisai_gappi))

        races = []
        for row in cur.fetchall():
            race_code = row[0]

            # Get finishing position and popularity for each race
            cur.execute('''
                SELECT umaban, kakutei_chakujun, bamei, tansho_ninkijun
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('6', '7')
                ORDER BY kakutei_chakujun::int
            ''', (race_code,))

            results = []
            for r in cur.fetchall():
                ninki = None
                if r[3] and r[3].strip():
                    try:
                        ninki = int(r[3])
                    except:
                        pass
                results.append({
                    'umaban': r[0],
                    'chakujun': int(r[1]) if r[1] else 99,
                    'bamei': r[2],
                    'ninki': ninki,  # Win popularity rank
                })

            races.append({
                'race_code': race_code,
                'keibajo': KEIBAJO_NAMES.get(row[1], row[1]),
                'race_number': row[2],
                'kyori': row[3],
                'track': '芝' if row[4] and row[4].startswith('1') else 'ダ',
                'results': results
            })

        cur.close()
        return races

    finally:
        conn.close()


def get_payouts(target_date: date) -> dict[str, dict]:
    """
    Get payout data for a specific date.

    Args:
        target_date: Target date

    Returns:
        Dict mapping race_code to payout data
    """
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        kaisai_gappi = target_date.strftime("%m%d")
        kaisai_nen = str(target_date.year)

        # Get payouts (win and place only)
        # data_kubun: '1'=registration/provisional, '2'=provisional, '7'=confirmed (prefer confirmed)
        cur.execute('''
            SELECT DISTINCT ON (race_code) race_code,
                   tansho1_umaban, tansho1_haraimodoshikin,
                   fukusho1_umaban, fukusho1_haraimodoshikin,
                   fukusho2_umaban, fukusho2_haraimodoshikin,
                   fukusho3_umaban, fukusho3_haraimodoshikin
            FROM haraimodoshi
            WHERE kaisai_nen = %s
              AND kaisai_gappi = %s
              AND data_kubun IN ('1', '2', '7')
            ORDER BY race_code, data_kubun DESC
        ''', (kaisai_nen, kaisai_gappi))

        payouts = {}
        for row in cur.fetchall():
            race_code = row[0]

            # Win payout
            tansho_umaban = row[1].strip() if row[1] else None
            tansho_payout = int(row[2]) if row[2] and row[2].strip() else 0

            # Place payouts (up to 3 horses)
            fukusho = []
            for i in range(3):
                umaban = row[3 + i * 2]
                payout = row[4 + i * 2]
                if umaban and umaban.strip():
                    fukusho.append({
                        'umaban': umaban.strip(),
                        'payout': int(payout) if payout and payout.strip() else 0
                    })

            payouts[race_code] = {
                'tansho_umaban': tansho_umaban,
                'tansho_payout': tansho_payout,
                'fukusho': fukusho,
            }

        cur.close()
        logger.info(f"Payout data retrieved: {len(payouts)} races")
        return payouts

    except Exception as e:
        logger.error(f"Error retrieving payout data: {e}")
        return {}
    finally:
        conn.close()


def load_predictions_from_db(target_date: date) -> dict | None:
    """
    Load prediction results from database.

    Args:
        target_date: Target date

    Returns:
        Predictions dictionary or None if not found
    """
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()

        # Get predictions for the specified date (prefer latest)
        cur.execute('''
            SELECT DISTINCT ON (race_id)
                prediction_id,
                race_id,
                race_date,
                is_final,
                prediction_result,
                predicted_at
            FROM predictions
            WHERE race_date = %s
            ORDER BY race_id, predicted_at DESC
        ''', (target_date,))

        rows = cur.fetchall()
        cur.close()

        if not rows:
            logger.warning(f"No prediction data found: {target_date}")
            return None

        predictions = {
            'date': str(target_date),
            'races': []
        }

        for row in rows:
            prediction_id = row[0]
            race_id = row[1]
            is_final = row[3]
            prediction_result = row[4]

            # Parse JSON string if needed
            if isinstance(prediction_result, str):
                try:
                    prediction_result = json.loads(prediction_result)
                except json.JSONDecodeError:
                    prediction_result = {}

            # Extract TOP3 from ranked_horses
            ranked_horses = prediction_result.get('ranked_horses', [])
            top3 = []
            for h in ranked_horses[:3]:
                top3.append({
                    'rank': h.get('rank', 0),
                    'umaban': str(h.get('horse_number', '')).zfill(2),
                    'bamei': h.get('horse_name', ''),
                    'win_prob': h.get('win_probability', 0),
                })

            predictions['races'].append({
                'prediction_id': prediction_id,
                'race_code': race_id,
                'is_final': is_final,
                'top3': top3,
                'all_horses': ranked_horses,
            })

        logger.info(f"Loaded predictions from DB: {len(predictions['races'])} races")
        return predictions

    except Exception as e:
        logger.error(f"Error loading predictions: {e}")
        return None
    finally:
        conn.close()


def save_analysis_to_db(analysis: dict) -> bool:
    """
    Save analysis results to database.

    Args:
        analysis: Analysis result dictionary

    Returns:
        True if successful, False otherwise
    """
    if analysis.get('status') != 'success':
        return False

    acc = analysis.get('accuracy', {})
    if 'error' in acc:
        return False

    db = get_db()
    conn = db.get_connection()
    if not conn:
        logger.error("DB connection failed")
        return False

    try:
        cur = conn.cursor()
        analysis_date = acc.get('date')
        raw_stats = acc.get('raw_stats', {})
        accuracy = acc.get('accuracy', {})

        # UPSERT (ON CONFLICT UPDATE)
        cur.execute('''
            INSERT INTO analysis_results (
                analysis_date, total_races, analyzed_races,
                tansho_hit, fukusho_hit, umaren_hit, sanrenpuku_hit, top3_cover,
                tansho_rate, fukusho_rate, umaren_rate, sanrenpuku_rate, top3_cover_rate, mrr,
                detail_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (analysis_date) DO UPDATE SET
                total_races = EXCLUDED.total_races,
                analyzed_races = EXCLUDED.analyzed_races,
                tansho_hit = EXCLUDED.tansho_hit,
                fukusho_hit = EXCLUDED.fukusho_hit,
                umaren_hit = EXCLUDED.umaren_hit,
                sanrenpuku_hit = EXCLUDED.sanrenpuku_hit,
                top3_cover = EXCLUDED.top3_cover,
                tansho_rate = EXCLUDED.tansho_rate,
                fukusho_rate = EXCLUDED.fukusho_rate,
                umaren_rate = EXCLUDED.umaren_rate,
                sanrenpuku_rate = EXCLUDED.sanrenpuku_rate,
                top3_cover_rate = EXCLUDED.top3_cover_rate,
                mrr = EXCLUDED.mrr,
                detail_data = EXCLUDED.detail_data,
                analyzed_at = CURRENT_TIMESTAMP
        ''', (
            analysis_date,
            acc.get('total_races', 0),
            acc.get('analyzed_races', 0),
            raw_stats.get('tansho_hit', 0),
            raw_stats.get('fukusho_hit', 0),
            raw_stats.get('umaren_hit', 0),
            raw_stats.get('sanrenpuku_hit', 0),
            raw_stats.get('top3_cover', 0),
            accuracy.get('tansho_hit_rate'),
            accuracy.get('fukusho_hit_rate'),
            accuracy.get('umaren_hit_rate'),
            accuracy.get('sanrenpuku_hit_rate'),
            accuracy.get('top3_cover_rate'),
            accuracy.get('mrr'),
            json.dumps({
                'by_venue': acc.get('by_venue', {}),
                'by_distance': acc.get('by_distance', {}),
                'by_track': acc.get('by_track', {}),
                'calibration': acc.get('calibration', {}),
                'misses': acc.get('misses', [])
            }, ensure_ascii=False)
        ))

        conn.commit()
        logger.info(f"Analysis saved to DB: {analysis_date}")
        return True

    except Exception as e:
        logger.error(f"Error saving analysis to DB: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def update_accuracy_tracking(stats: dict) -> bool:
    """
    Update cumulative accuracy tracking.

    Args:
        stats: Statistics dictionary with counts

    Returns:
        True if successful, False otherwise
    """
    db = get_db()
    conn = db.get_connection()
    if not conn:
        logger.error("DB connection failed")
        return False

    try:
        cur = conn.cursor()

        # Get current cumulative values
        cur.execute('SELECT * FROM accuracy_tracking LIMIT 1')
        row = cur.fetchone()

        if row:
            # Update
            new_total = row[1] + stats.get('analyzed_races', 0)
            new_tansho = row[2] + stats.get('tansho_hit', 0)
            new_fukusho = row[3] + stats.get('fukusho_hit', 0)
            new_umaren = row[4] + stats.get('umaren_hit', 0)
            new_sanrenpuku = row[5] + stats.get('sanrenpuku_hit', 0)

            cur.execute('''
                UPDATE accuracy_tracking SET
                    total_races = %s,
                    total_tansho_hit = %s,
                    total_fukusho_hit = %s,
                    total_umaren_hit = %s,
                    total_sanrenpuku_hit = %s,
                    cumulative_tansho_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                    cumulative_fukusho_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                    cumulative_umaren_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                    cumulative_sanrenpuku_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (
                new_total, new_tansho, new_fukusho, new_umaren, new_sanrenpuku,
                new_total, new_tansho, new_total,
                new_total, new_fukusho, new_total,
                new_total, new_umaren, new_total,
                new_total, new_sanrenpuku, new_total,
                row[0]
            ))
        else:
            # Initial insert
            n = stats.get('analyzed_races', 0)
            cur.execute('''
                INSERT INTO accuracy_tracking (
                    total_races, total_tansho_hit, total_fukusho_hit,
                    total_umaren_hit, total_sanrenpuku_hit
                ) VALUES (%s, %s, %s, %s, %s)
            ''', (
                n,
                stats.get('tansho_hit', 0),
                stats.get('fukusho_hit', 0),
                stats.get('umaren_hit', 0),
                stats.get('sanrenpuku_hit', 0)
            ))

        conn.commit()
        logger.info("Cumulative tracking updated")
        return True

    except Exception as e:
        logger.error(f"Error updating cumulative tracking: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def get_cumulative_stats() -> dict | None:
    """
    Get cumulative statistics.

    Returns:
        Cumulative stats dictionary or None
    """
    db = get_db()
    conn = db.get_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute('SELECT * FROM accuracy_tracking LIMIT 1')
        row = cur.fetchone()

        if row:
            return {
                'total_races': row[1],
                'tansho_hit': row[2],
                'fukusho_hit': row[3],
                'umaren_hit': row[4],
                'sanrenpuku_hit': row[5],
                'tansho_rate': row[6],
                'fukusho_rate': row[7],
                'umaren_rate': row[8],
                'sanrenpuku_rate': row[9],
                'last_updated': row[10]
            }
        return None

    except Exception as e:
        logger.error(f"Error getting cumulative stats: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_recent_race_dates(days_back: int = 7) -> list:
    """
    Get recent race dates (dates with prediction data).

    Args:
        days_back: Number of days to look back

    Returns:
        List of dates
    """
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT DISTINCT race_date
            FROM predictions
            WHERE race_date >= %s AND race_date < %s
            ORDER BY race_date
        ''', (date.today() - timedelta(days=days_back), date.today()))

        dates = [row[0] for row in cur.fetchall()]
        cur.close()
        return dates
    finally:
        conn.close()
