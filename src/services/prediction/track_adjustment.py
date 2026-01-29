"""
Track Condition Adjustment Module

Functions for adjusting predictions based on current track conditions
(weather, turf/dirt condition) and horse performance on specific track states.
"""

import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Venue code mapping
VENUE_CODE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉"
}

# Track condition code mapping
BABA_CONDITION_MAP = {
    "1": "良", "2": "稍重", "3": "重", "4": "不良"
}

# Weather code mapping
WEATHER_CODE_MAP = {
    "1": "晴", "2": "曇", "3": "雨", "4": "小雨", "5": "雪", "6": "小雪"
}


def get_current_track_condition(conn, race_id: str) -> Optional[Dict]:
    """
    Get current track condition and weather for a race.

    Args:
        conn: DB connection
        race_id: Race ID

    Returns:
        {'track_type': 'shiba'|'dirt', 'condition': 1-4, 'condition_name': '良',
         'weather': 1-6, 'weather_name': '晴'}
    """
    cur = conn.cursor()
    try:
        # 1. Get track type for the race
        cur.execute('''
            SELECT track_code
            FROM race_shosai
            WHERE race_code = %s
              AND data_kubun IN ('1', '2', '3', '4', '5', '6')
            LIMIT 1
        ''', (race_id,))
        row = cur.fetchone()
        if not row:
            return None

        track_code = row[0] or ''
        # track_code: 10-19=turf, 20-29=dirt
        if track_code.startswith('1'):
            track_type = 'shiba'
        elif track_code.startswith('2'):
            track_type = 'dirt'
        else:
            track_type = 'shiba'  # Default

        # 2. Get current track condition and weather
        # race_id format: YYYYMMDD(8) + keibajo(2) + kai(2) + nichime(2) + race(2) = 16 digits
        # tenko_baba_jotai.race_code format: YYYYMMDD(8) + keibajo(2) + kai(2) + nichime(2) = 14 digits
        # Example: 2026010506010201 -> 20260105060102
        baba_race_code = race_id[:14]  # Remove last 2 digits (race number)

        cur.execute('''
            SELECT
                tenko_jotai_genzai,
                baba_jotai_shiba_genzai,
                baba_jotai_dirt_genzai
            FROM tenko_baba_jotai
            WHERE race_code = %s
            ORDER BY insert_timestamp DESC
            LIMIT 1
        ''', (baba_race_code,))
        baba_row = cur.fetchone()

        if not baba_row:
            logger.debug(f"No track condition data: race_id={race_id}")
            return None

        weather_code = baba_row[0] or '0'
        shiba_condition = baba_row[1] or '0'
        dirt_condition = baba_row[2] or '0'

        condition_code = shiba_condition if track_type == 'shiba' else dirt_condition

        result = {
            'track_type': track_type,
            'condition': int(condition_code) if condition_code.isdigit() else 0,
            'condition_name': BABA_CONDITION_MAP.get(condition_code, '不明'),
            'weather': int(weather_code) if weather_code.isdigit() else 0,
            'weather_name': WEATHER_CODE_MAP.get(weather_code, '不明'),
        }

        logger.info(f"Track condition: {result['track_type']}・{result['condition_name']}, weather: {result['weather_name']}")
        return result

    except Exception as e:
        logger.error(f"Error getting track condition: {e}")
        return None
    finally:
        cur.close()


def get_horse_baba_performance(conn, kettonums: List[str], track_type: str, condition: int) -> Dict[str, Dict]:
    """
    Get each horse's performance record on specific track conditions.

    Args:
        conn: DB connection
        kettonums: List of horse registration numbers
        track_type: 'shiba' or 'dirt'
        condition: 1=good, 2=slightly heavy, 3=heavy, 4=bad

    Returns:
        {kettonum: {'runs': N, 'wins': N, 'top3': N, 'win_rate': 0.xx, 'top3_rate': 0.xx}}
    """
    if not kettonums or condition == 0:
        return {}

    # Column name mapping
    condition_map = {
        1: 'ryo',       # Good
        2: 'yayaomo',   # Slightly heavy
        3: 'omo',       # Heavy
        4: 'furyo',     # Bad
    }
    condition_suffix = condition_map.get(condition, 'ryo')
    prefix = f"{track_type}_{condition_suffix}"  # e.g., 'shiba_ryo', 'dirt_omo'

    cur = conn.cursor()
    try:
        # Get performance from shussobetsu_baba table
        placeholders = ','.join(['%s'] * len(kettonums))
        cur.execute(f'''
            SELECT
                ketto_toroku_bango,
                {prefix}_1chaku,
                {prefix}_2chaku,
                {prefix}_3chaku,
                {prefix}_4chaku,
                {prefix}_5chaku,
                {prefix}_chakugai
            FROM shussobetsu_baba
            WHERE ketto_toroku_bango IN ({placeholders})
              AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        ''', kettonums)

        results = {}
        for row in cur.fetchall():
            kettonum = row[0]
            wins = int(row[1] or 0)
            sec = int(row[2] or 0)
            third = int(row[3] or 0)
            fourth = int(row[4] or 0)
            fifth = int(row[5] or 0)
            out = int(row[6] or 0)

            runs = wins + sec + third + fourth + fifth + out
            top3 = wins + sec + third

            if runs > 0:
                results[kettonum] = {
                    'runs': runs,
                    'wins': wins,
                    'top3': top3,
                    'win_rate': wins / runs,
                    'top3_rate': top3 / runs,
                }

        logger.info(f"Track performance fetched: {len(results)}/{len(kettonums)} horses ({prefix})")
        return results

    except Exception as e:
        logger.error(f"Error getting track performance: {e}")
        return {}
    finally:
        cur.close()


def apply_track_condition_adjustment(
    ml_scores: Dict[str, Any],
    horses: List[Dict],
    track_condition: Dict,
    baba_performance: Dict[str, Dict]
) -> Dict[str, Any]:
    """
    Adjust scores based on track condition.

    Args:
        ml_scores: Original ML scores
        horses: List of horse information
        track_condition: Current track condition
        baba_performance: Each horse's performance on this track condition

    Returns:
        Adjusted scores dictionary
    """
    if not track_condition or not baba_performance:
        return ml_scores

    condition = track_condition.get('condition', 1)
    condition_name = track_condition.get('condition_name', '良')

    adjusted_scores = {}

    for umaban_str, score_data in ml_scores.items():
        adjustment = 0.0

        # Get horse info
        horse_info = None
        for h in horses:
            if str(h.get('umaban', '')).zfill(2) == umaban_str.zfill(2):
                horse_info = h
                break

        if horse_info:
            kettonum = horse_info.get('ketto_toroku_bango', '')
            if kettonum in baba_performance:
                perf = baba_performance[kettonum]
                runs = perf.get('runs', 0)
                win_rate = perf.get('win_rate', 0)
                top3_rate = perf.get('top3_rate', 0)

                # Only adjust for horses with experience
                if runs >= 2:
                    # Evaluate performance on non-good track
                    if condition >= 2:  # Slightly heavy or worse
                        # Add points for horses with good wet track record
                        if win_rate > 0.15:  # Win rate > 15%
                            adjustment += 0.03
                        elif win_rate > 0.05:
                            adjustment += 0.01

                        if top3_rate > 0.4:  # Top 3 rate > 40%
                            adjustment += 0.02
                        elif top3_rate > 0.2:
                            adjustment += 0.01

                        # Extra points for extensive experience
                        if runs >= 5:
                            adjustment += 0.01

                    # Penalize horses with no wet track experience
                    if condition >= 2 and runs == 0:
                        # No runs on this track condition
                        adjustment -= 0.02

        # Adjust scores
        new_rank_score = score_data.get('rank_score', 999) - adjustment
        old_prob = score_data.get('win_probability', 0)
        new_prob = old_prob * (1 + adjustment * 3)
        new_prob = max(0.001, min(0.99, new_prob))

        adjusted_scores[umaban_str] = {
            'rank_score': new_rank_score,
            'win_probability': new_prob,
            'track_adjustment': adjustment,
        }

        # Adjust quinella_probability
        if 'quinella_probability' in score_data:
            old_quinella = score_data['quinella_probability']
            new_quinella = old_quinella * (1 + adjustment * 2.5)
            new_quinella = max(0.005, min(0.99, new_quinella))
            adjusted_scores[umaban_str]['quinella_probability'] = new_quinella

        # Adjust place_probability
        if 'place_probability' in score_data:
            old_place = score_data['place_probability']
            new_place = old_place * (1 + adjustment * 2)
            new_place = max(0.01, min(0.99, new_place))
            adjusted_scores[umaban_str]['place_probability'] = new_place

    # Return original scores if no adjustments were made
    adjusted_count = len([a for a in adjusted_scores.values() if a.get('track_adjustment', 0) != 0])
    logger.info(f"Track condition adjustment complete: {condition_name}, adjusted horses={adjusted_count}")

    if adjusted_count == 0:
        return ml_scores

    # Re-normalize probabilities
    n_horses = len(adjusted_scores)

    # Win probability: sum to 1.0
    win_sum = sum(s.get('win_probability', 0) for s in adjusted_scores.values())
    if win_sum > 0:
        for umaban_str in adjusted_scores:
            adjusted_scores[umaban_str]['win_probability'] /= win_sum

    # Quinella probability: sum to 2.0
    quinella_sum = sum(s.get('quinella_probability', 0) for s in adjusted_scores.values())
    if quinella_sum > 0:
        expected_quinella = min(2.0, n_horses)  # Always 2.0 if 2+ horses
        for umaban_str in adjusted_scores:
            if 'quinella_probability' in adjusted_scores[umaban_str]:
                adjusted_scores[umaban_str]['quinella_probability'] *= expected_quinella / quinella_sum

    # Place probability: sum to 3.0
    place_sum = sum(s.get('place_probability', 0) for s in adjusted_scores.values())
    if place_sum > 0:
        expected_place = min(3.0, n_horses)  # Always 3.0 if 3+ horses
        for umaban_str in adjusted_scores:
            if 'place_probability' in adjusted_scores[umaban_str]:
                adjusted_scores[umaban_str]['place_probability'] *= expected_place / place_sum

    return adjusted_scores
