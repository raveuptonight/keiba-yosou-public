"""
Result Generator Module

Functions for generating prediction results in probability-based ranking format.
Converts ML scores to user-friendly prediction responses.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from src.api.schemas.prediction import (
    HorseRankingEntry,
    PositionDistribution,
    PredictionResponse,
    PredictionResult,
)
from src.db.table_names import (
    COL_JYOCD,
    COL_KAISAI_MONTHDAY,
    COL_KAISAI_YEAR,
    COL_RACE_ID,
    COL_RACE_NAME,
)
from src.services.prediction.track_adjustment import VENUE_CODE_MAP

logger = logging.getLogger(__name__)


def generate_mock_prediction(race_id: str, is_final: bool) -> PredictionResponse:
    """
    Generate mock prediction (probability-based ranking format).

    Args:
        race_id: Race ID
        is_final: Whether this is the final prediction

    Returns:
        PredictionResponse with mock data
    """
    logger.info(f"[MOCK] Generating mock prediction for race_id={race_id}")

    # Mock ranking data
    mock_horses: list[dict[str, int | float | str]] = [
        {"rank": 1, "horse_number": 1, "horse_name": "MockHorse1", "win_prob": 0.25},
        {"rank": 2, "horse_number": 5, "horse_name": "MockHorse5", "win_prob": 0.18},
        {"rank": 3, "horse_number": 3, "horse_name": "MockHorse3", "win_prob": 0.12},
        {"rank": 4, "horse_number": 7, "horse_name": "MockHorse7", "win_prob": 0.10},
        {"rank": 5, "horse_number": 2, "horse_name": "MockHorse2", "win_prob": 0.08},
    ]

    ranked_horses = [
        HorseRankingEntry(
            rank=int(h["rank"]),
            horse_number=int(h["horse_number"]),
            horse_name=str(h["horse_name"]),
            horse_sex=None,
            horse_age=None,
            jockey_name=None,
            win_probability=float(h["win_prob"]),
            quinella_probability=min(float(h["win_prob"]) * 1.8, 0.5),
            place_probability=min(float(h["win_prob"]) * 2.5, 0.6),
            position_distribution=PositionDistribution(
                first=float(h["win_prob"]),
                second=float(h["win_prob"]) * 0.8,
                third=float(h["win_prob"]) * 0.6,
                out_of_place=max(0, 1.0 - float(h["win_prob"]) * 2.4),
            ),
            rank_score=float(h["rank"]),
            confidence=0.7 - float(h["rank"]) * 0.05,
        )
        for h in mock_horses
    ]

    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        quinella_ranking=None,
        place_ranking=None,
        dark_horses=None,
        prediction_confidence=0.72,
        model_info="mock_model",
    )

    return PredictionResponse(
        prediction_id=str(uuid.uuid4()),
        race_id=race_id,
        race_name="MockRace",
        race_date=datetime.now().strftime("%Y-%m-%d"),
        venue="Tokyo",
        race_number="11",
        race_time="15:40",
        prediction_result=prediction_result,
        predicted_at=datetime.now(),
        is_final=is_final,
    )


def generate_ml_only_prediction(
    race_data: dict[str, Any], ml_scores: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate probability-based ranking prediction from ML scores.

    Args:
        race_data: Race data
        ml_scores: ML prediction scores

    Returns:
        Dict: Probability-based ranking prediction data
    """
    horses = race_data.get("horses", [])
    n_horses = len(horses)

    # Sort by ML scores (lower score = higher rank)
    scored_horses = []
    for horse in horses:
        umaban_raw = horse.get("umaban", "")
        # Normalize horse number ('01' -> '1', 1 -> '1', etc.)
        try:
            umaban = str(int(umaban_raw))
        except (ValueError, TypeError):
            umaban = str(umaban_raw)
        score_data = ml_scores.get(umaban, {})

        # Sex code conversion
        sex_code = horse.get("seibetsu_code", "")
        sex_map = {"1": "牡", "2": "牝", "3": "セ"}
        horse_sex = sex_map.get(str(sex_code), "")

        # Horse age
        barei = horse.get("barei", "")
        try:
            horse_age = int(barei) if barei else None
        except (ValueError, TypeError):
            horse_age = None

        # Skip horse_number 0 (scratched or registration-only)
        horse_num = int(umaban) if umaban.isdigit() else 0
        if horse_num < 1:
            continue

        scored_horses.append(
            {
                "horse_number": horse_num,
                "horse_name": horse.get("bamei", "Unknown"),
                "horse_sex": horse_sex,
                "horse_age": horse_age,
                "jockey_name": horse.get("kishumei", ""),
                "rank_score": score_data.get("rank_score", 999),
                "win_probability": score_data.get("win_probability", 0.0),
                "quinella_probability": score_data.get(
                    "quinella_probability"
                ),  # Quinella prob from model (if any)
                "place_probability": score_data.get(
                    "place_probability"
                ),  # Place prob from model (if any)
            }
        )

    # Sort by win probability (higher = better)
    # Note: Use win_probability instead of rank_score so displayed probability matches ranking
    scored_horses.sort(key=lambda x: x["win_probability"], reverse=True)

    def calc_position_distribution(
        win_prob: float, quinella_prob: float | None, place_prob: float | None, rank: int, n: int
    ) -> dict[str, float]:
        """
        Estimate position distribution from win/quinella/place probabilities.

        If quinella model exists:
          2nd place prob = quinella prob - win prob
          3rd place prob = place prob - quinella prob
        """
        # 1st place = win probability
        first = win_prob

        if quinella_prob is not None and place_prob is not None:
            # Direct calculation when quinella/place models exist
            second = max(0, quinella_prob - first)
            third = max(0, place_prob - quinella_prob)
        elif place_prob is not None:
            # When quinella model not available (legacy compatibility)
            remaining_place = max(0, place_prob - first)
            if rank <= 3:
                second = remaining_place * 0.55
                third = remaining_place * 0.45
            elif rank <= 6:
                second = remaining_place * 0.5
                third = remaining_place * 0.5
            else:
                second = remaining_place * 0.45
                third = remaining_place * 0.55
        else:
            # Legacy format: estimate from win probability
            second = min(win_prob * 1.5, 0.3) if rank <= 5 else win_prob * 0.5
            third = min(win_prob * 1.8, 0.35) if rank <= 7 else win_prob * 0.3

        # 4th place and below
        out = max(0.0, 1.0 - first - second - third)
        return {
            "first": round(first, 4),
            "second": round(second, 4),
            "third": round(third, 4),
            "out_of_place": round(out, 4),
        }

    # Generate ranking entries
    # Note: Probabilities are already predicted and normalized by model
    # - Win probability: sum to 1.0
    # - Quinella probability: sum to 2.0
    # - Place probability: sum to 3.0
    ranked_horses = []
    for i, h in enumerate(scored_horses):
        rank = i + 1
        win_prob = h["win_probability"]
        model_quinella_prob = h.get("quinella_probability")  # Quinella prob from model
        model_place_prob = h.get("place_probability")  # Place prob from model

        # Calculate position distribution (for display) - using quinella model
        pos_dist = calc_position_distribution(
            win_prob, model_quinella_prob, model_place_prob, rank, n_horses
        )

        # Quinella: prefer model value, otherwise calculate from distribution
        if model_quinella_prob is not None:
            quinella_prob = model_quinella_prob
        else:
            quinella_prob = min(1.0, pos_dist["first"] + pos_dist["second"])

        # Place: prefer model value, otherwise calculate from distribution
        if model_place_prob is not None:
            place_prob = model_place_prob
        else:
            place_prob = min(1.0, pos_dist["first"] + pos_dist["second"] + pos_dist["third"])

        # Individual confidence (based on data completeness and probability separation)
        # Evaluate confidence by gap to next horse
        if i < len(scored_horses) - 1:
            prob_gap = h["win_probability"] - scored_horses[i + 1]["win_probability"]
            # Calculate confidence from probability gap (0.0 to 0.95)
            confidence = min(0.95, max(0.1, 0.5 + prob_gap * 5))
        else:
            confidence = 0.5

        ranked_horses.append(
            {
                "rank": rank,
                "horse_number": h["horse_number"],
                "horse_name": h["horse_name"],
                "horse_sex": h.get("horse_sex", ""),
                "horse_age": h.get("horse_age"),
                "jockey_name": h.get("jockey_name", ""),
                "win_probability": round(win_prob, 4),
                "quinella_probability": round(quinella_prob, 4),
                "place_probability": round(place_prob, 4),
                "position_distribution": pos_dist,
                "rank_score": round(h["rank_score"], 4),
                "confidence": round(confidence, 4),
            }
        )

    # Overall prediction confidence (based on top horse probability and gap to 2nd)
    if len(scored_horses) >= 2:
        top_prob = scored_horses[0]["win_probability"]
        second_prob = scored_horses[1]["win_probability"]
        gap_ratio = (top_prob - second_prob) / max(top_prob, 0.01)
        prediction_confidence = min(0.95, 0.4 + gap_ratio * 0.5 + top_prob)
    else:
        prediction_confidence = 0.5

    # Generate multiple rankings (by purpose)
    # Quinella ranking (for exacta/quinella bets)
    quinella_ranking = sorted(
        [(h["horse_number"], h["quinella_probability"]) for h in ranked_horses],
        key=lambda x: x[1],
        reverse=True,
    )[
        :5
    ]  # Top 5

    # Place ranking (for place bets)
    place_ranking = sorted(
        [(h["horse_number"], h["place_probability"]) for h in ranked_horses],
        key=lambda x: x[1],
        reverse=True,
    )[
        :5
    ]  # Top 5

    # Dark horse candidates (high place prob but low win prob = can't win but makes top 3)
    # Place prob >= 20% and win prob < 10%
    dark_horses = [
        {
            "horse_number": h["horse_number"],
            "win_prob": h["win_probability"],
            "place_prob": h["place_probability"],
        }
        for h in ranked_horses
        if h["place_probability"] >= 0.20 and h["win_probability"] < 0.10
    ][:3]

    return {
        "ranked_horses": ranked_horses,  # Win probability order (for win bets)
        "quinella_ranking": [
            {"rank": i + 1, "horse_number": num, "quinella_prob": round(prob, 4)}
            for i, (num, prob) in enumerate(quinella_ranking)
        ],
        "place_ranking": [
            {"rank": i + 1, "horse_number": num, "place_prob": round(prob, 4)}
            for i, (num, prob) in enumerate(place_ranking)
        ],
        "dark_horses": dark_horses,  # Dark horse candidates
        "prediction_confidence": round(prediction_confidence, 4),
        "model_info": "ensemble_model",
    }


def convert_to_prediction_response(
    race_data: dict[str, Any], ml_result: dict[str, Any], is_final: bool
) -> PredictionResponse:
    """
    Convert ML result to probability-based ranking PredictionResponse.

    Args:
        race_data: Race data
        ml_result: ML prediction result (probability-based ranking format)
        is_final: Final prediction flag

    Returns:
        PredictionResponse: Converted prediction result
    """
    race_info = race_data.get("race", {})

    # Extract race information
    race_id = race_info.get(COL_RACE_ID, "")
    race_name_raw = race_info.get(COL_RACE_NAME)

    # Generate fallback race name from condition codes if empty
    if race_name_raw and race_name_raw.strip():
        race_name = race_name_raw.strip()
    else:
        # Infer race name from race conditions
        kyoso_joken = race_info.get("kyoso_joken_code", "")
        kyoso_shubetsu = race_info.get("kyoso_shubetsu_code", "")

        # JRA-VAN master-based mapping
        joken_map = {
            "005": "1勝クラス",
            "010": "2勝クラス",
            "016": "3勝クラス",
            "701": "新馬",
            "702": "未出走",
            "703": "未勝利",
            "999": "OP",
        }

        # Maiden/unraced: no "以上", class races: add "以上"
        if kyoso_joken in ("701", "702", "703"):
            shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳", "14": "4歳"}
        else:
            shubetsu_map = {"11": "2歳", "12": "3歳", "13": "3歳以上", "14": "4歳以上"}

        shubetsu_name = shubetsu_map.get(kyoso_shubetsu, "")
        joken_name = joken_map.get(kyoso_joken, "条件戦")
        race_name = f"{shubetsu_name}{joken_name}".strip() or "条件戦"

    venue_code = race_info.get(COL_JYOCD, "00")
    venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
    race_number = str(race_info.get("race_bango", "?"))
    race_time = race_info.get("hasso_jikoku", "00:00")

    # Calculate race date
    kaisai_year = race_info.get(COL_KAISAI_YEAR, "")
    kaisai_monthday = race_info.get(COL_KAISAI_MONTHDAY, "")
    if kaisai_year and kaisai_monthday:
        race_date = f"{kaisai_year}-{kaisai_monthday[:2]}-{kaisai_monthday[2:]}"
    else:
        race_date = datetime.now().strftime("%Y-%m-%d")

    # Build ranking entries
    ranked_horses_data = ml_result.get("ranked_horses", [])
    ranked_horses = [
        HorseRankingEntry(
            rank=h["rank"],
            horse_number=h["horse_number"],
            horse_name=h["horse_name"],
            horse_sex=h.get("horse_sex"),
            horse_age=h.get("horse_age"),
            jockey_name=h.get("jockey_name", ""),
            win_probability=h["win_probability"],
            quinella_probability=h["quinella_probability"],
            place_probability=h["place_probability"],
            position_distribution=PositionDistribution(**h["position_distribution"]),
            rank_score=h["rank_score"],
            confidence=h["confidence"],
        )
        for h in ranked_horses_data
    ]

    # Build PredictionResult (probability-based ranking format)
    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        quinella_ranking=ml_result.get("quinella_ranking"),
        place_ranking=ml_result.get("place_ranking"),
        dark_horses=ml_result.get("dark_horses"),
        prediction_confidence=ml_result.get("prediction_confidence", 0.5),
        model_info=ml_result.get("model_info", "ensemble_model"),
    )

    # Build PredictionResponse
    prediction_response = PredictionResponse(
        prediction_id="",  # Set by save_prediction
        race_id=race_id,
        race_name=race_name,
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        race_time=race_time,
        prediction_result=prediction_result,
        predicted_at=datetime.now(),
        is_final=is_final,
    )

    return prediction_response
