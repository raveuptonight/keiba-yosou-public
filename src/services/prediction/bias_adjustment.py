"""
Bias Adjustment Module

Functions for loading and applying daily bias data to ML predictions.
Bias includes venue-specific waku (post position) bias and jockey performance bias.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cache for bias data by date
_bias_cache: dict[str, dict] = {}


def load_bias_for_date(target_date: str) -> dict | None:
    """
    Load bias data for a specific date from DB.

    Args:
        target_date: Date in YYYY-MM-DD format

    Returns:
        Bias data dictionary, or None if not found
    """
    from datetime import datetime

    from src.features.daily_bias import DailyBiasAnalyzer

    if target_date in _bias_cache:
        return _bias_cache[target_date]

    try:
        # Convert date string to date object
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Load bias from DB
        analyzer = DailyBiasAnalyzer()
        bias_result = analyzer.load_bias(date_obj)

        if bias_result:
            data = bias_result.to_dict()
            _bias_cache[target_date] = data
            logger.info(f"Loaded bias data from DB: {target_date}")
            return data

    except Exception as e:
        logger.error(f"Error loading bias data: {e}")

    return None


def apply_bias_to_scores(
    ml_scores: dict[str, Any], race_id: str, horses: list[dict], bias_data: dict
) -> dict[str, Any]:
    """
    Apply bias adjustment to ML scores.

    Args:
        ml_scores: Original ML scores {horse_number: {rank_score, win_probability}}
        race_id: Race ID
        horses: List of horse information
        bias_data: Bias data dictionary

    Returns:
        Adjusted scores dictionary
    """
    # Extract venue code from race_id (digits 9-10 are venue code: YYYY+MM+kai+venue)
    venue_code = race_id[8:10]

    venue_biases = bias_data.get("venue_biases", {})
    jockey_performances = bias_data.get("jockey_performances", {})

    if venue_code not in venue_biases:
        logger.info(f"No venue bias found: venue_code={venue_code}")
        return ml_scores

    vb = venue_biases[venue_code]
    waku_bias = vb.get("waku_bias", 0)
    pace_bias = vb.get("pace_bias", 0)

    logger.info(
        f"Applying bias: {vb.get('venue_name', venue_code)}, "
        f"waku={waku_bias:.3f}, pace={pace_bias:.3f}"
    )

    adjusted_scores = {}

    for umaban_str, score_data in ml_scores.items():
        try:
            umaban = int(umaban_str)
        except ValueError:
            adjusted_scores[umaban_str] = score_data
            continue

        # Find horse info
        horse_info = None
        for h in horses:
            h_umaban = h.get("umaban", "")
            try:
                if int(h_umaban) == umaban:
                    horse_info = h
                    break
            except (ValueError, TypeError):
                pass

        # Calculate adjustment coefficient
        adjustment = 0.0

        # 1. Waku (post position) bias
        if horse_info:
            wakuban = horse_info.get("wakuban", "")
            try:
                waku = int(wakuban)
                if 1 <= waku <= 4:
                    # Inner post: add points if inner is advantageous
                    adjustment += waku_bias * 0.02
                elif 5 <= waku <= 8:
                    # Outer post: add points if outer is advantageous (= inner disadvantageous)
                    adjustment -= waku_bias * 0.02
            except (ValueError, TypeError):
                pass

        # 2. Jockey daily performance bias
        if horse_info:
            kishu_code = horse_info.get("kishu_code", "")
            if kishu_code and kishu_code in jockey_performances:
                jp = jockey_performances[kishu_code]
                jockey_win_rate = jp.get("win_rate", 0)
                jockey_top3_rate = jp.get("top3_rate", 0)

                # Add points for jockeys performing well today
                adjustment += jockey_win_rate * 0.03
                adjustment += jockey_top3_rate * 0.01

        # Adjust score (rank_score: lower is better)
        new_rank_score = score_data.get("rank_score", 999) - adjustment

        # Adjust probability (positive adjustment increases probability)
        factor = 1 + adjustment * 2
        new_prob = max(0.001, min(0.99, score_data.get("win_probability", 0) * factor))

        new_score = {
            "rank_score": new_rank_score,
            "win_probability": new_prob,
            "bias_adjustment": adjustment,
        }

        # Preserve and adjust quinella/place probabilities with same factor
        if "quinella_probability" in score_data:
            new_score["quinella_probability"] = max(
                0.001, min(0.99, score_data["quinella_probability"] * factor)
            )
        if "place_probability" in score_data:
            new_score["place_probability"] = max(
                0.001, min(0.99, score_data["place_probability"] * factor)
            )

        # Preserve CI fields
        if "win_ci_lower" in score_data:
            new_score["win_ci_lower"] = max(0, score_data["win_ci_lower"] * factor)
        if "win_ci_upper" in score_data:
            new_score["win_ci_upper"] = min(1, score_data["win_ci_upper"] * factor)

        adjusted_scores[umaban_str] = new_score

    # Normalize win probabilities (don't normalize quinella/place - they're independent)
    total_prob = sum(s.get("win_probability", 0) for s in adjusted_scores.values())
    if total_prob > 0:
        for umaban_str in adjusted_scores:
            adjusted_scores[umaban_str]["win_probability"] /= total_prob

    return adjusted_scores
