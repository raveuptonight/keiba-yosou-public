"""
Prediction Service

Service layer for generating, saving, and retrieving race predictions.
Uses ML ensemble models (XGBoost + LightGBM + CatBoost) for probability-based ranking.
"""

import logging
import os

from src.api.schemas.prediction import (
    EVRecommendationEntry,
    EVRecommendations,
    PredictionResponse,
)
from src.exceptions import (
    MissingDataError,
    PredictionError,
)
from src.models.ev_recommender import EVRecommender
from src.services.prediction.ml_engine import compute_ml_predictions
from src.services.prediction.persistence import (
    get_prediction_by_id,
    get_predictions_by_race,
    save_prediction,
)
from src.services.prediction.result_generator import (
    convert_to_prediction_response,
    generate_ml_only_prediction,
    generate_mock_prediction,
)

logger = logging.getLogger(__name__)


def _is_mock_mode() -> bool:
    """Check if running in mock mode."""
    return os.getenv("DB_MODE", "local") == "mock"


async def generate_prediction(
    race_id: str, is_final: bool = False, bias_date: str | None = None
) -> PredictionResponse:
    """
    Main prediction generation function (ML model only, no LLM).
    Outputs probability-based ranking with position distribution and confidence scores.

    Args:
        race_id: Race ID (16 digits)
        is_final: Final prediction flag (after body weight announcement)
        bias_date: Bias application date (YYYY-MM-DD format, auto-detect if omitted)

    Returns:
        PredictionResponse: Prediction result (probability-based ranking format)

    Raises:
        PredictionError: If prediction generation fails
    """
    logger.info(f"Starting ML prediction: race_id={race_id}, is_final={is_final}")

    # Mock mode
    if _is_mock_mode():
        return generate_mock_prediction(race_id, is_final)

    try:
        # Lazy imports (not needed in mock mode)
        from src.db.async_connection import get_connection
        from src.db.queries import (
            check_race_exists,
            get_race_prediction_data,
        )

        # 1. Fetch data
        async with get_connection() as conn:
            # Check race exists
            exists = await check_race_exists(conn, race_id)
            if not exists:
                raise MissingDataError(f"Race not found: race_id={race_id}")

            # Get prediction data
            logger.debug(f"Fetching race prediction data: race_id={race_id}")
            race_data = await get_race_prediction_data(conn, race_id)

            if not race_data or not race_data.get("horses"):
                raise MissingDataError(f"Insufficient race data: race_id={race_id}")

        # 2. Compute ML predictions
        ml_scores = {}
        try:
            ml_scores = compute_ml_predictions(
                race_id, race_data.get("horses", []), bias_date, is_final=is_final
            )
            if ml_scores:
                logger.info(f"ML predictions computed: {len(ml_scores)} horses")
            else:
                raise PredictionError("ML prediction not available")
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            raise PredictionError(f"ML prediction failed: {e}") from e

        # 3. Generate probability-based ranking prediction from ML scores
        logger.debug("Generating probability-based ranking prediction")
        ml_result = generate_ml_only_prediction(race_data=race_data, ml_scores=ml_scores)

        # 4. Convert prediction result to Pydantic model
        logger.debug("Converting ML result to PredictionResponse")
        prediction_response = convert_to_prediction_response(
            race_data=race_data, ml_result=ml_result, is_final=is_final
        )

        # 5. Calculate EV recommendations (using realtime odds for final predictions)
        if is_final:
            try:
                ev_recommender = EVRecommender()
                ranked_horses = [
                    {
                        "horse_number": h.horse_number,
                        "horse_name": h.horse_name,
                        "win_probability": h.win_probability,
                        "place_probability": h.place_probability,
                        "rank": h.rank,
                    }
                    for h in prediction_response.prediction_result.ranked_horses
                ]
                ev_recs = ev_recommender.get_recommendations(
                    race_code=race_id,
                    ranked_horses=ranked_horses,
                    use_realtime_odds=True,
                )

                # Convert to schema format
                win_recs = [
                    EVRecommendationEntry(
                        horse_number=r["horse_number"],
                        horse_name=r["horse_name"],
                        bet_type="win",
                        probability=r["win_probability"],
                        odds=r["odds"],
                        expected_value=r["expected_value"],
                    )
                    for r in ev_recs.get("win_recommendations", [])
                ]
                place_recs = [
                    EVRecommendationEntry(
                        horse_number=r["horse_number"],
                        horse_name=r["horse_name"],
                        bet_type="place",
                        probability=r["place_probability"],
                        odds=r["odds"],
                        expected_value=r["expected_value"],
                    )
                    for r in ev_recs.get("place_recommendations", [])
                ]

                prediction_response.prediction_result.ev_recommendations = EVRecommendations(
                    win_recommendations=win_recs,
                    place_recommendations=place_recs,
                    odds_source=ev_recs.get("odds_source", "realtime"),
                    odds_time=ev_recs.get("odds_time"),
                )
                logger.info(
                    f"EV recommendations calculated: win={len(win_recs)}, place={len(place_recs)}"
                )
            except Exception as e:
                logger.warning(f"EV recommendation calculation failed (skipped): {e}")

        # 6. Save to DB
        prediction_id = await save_prediction(prediction_response)
        prediction_response.prediction_id = prediction_id

        logger.info(f"ML prediction completed: prediction_id={prediction_id}")
        return prediction_response

    except MissingDataError:
        raise
    except PredictionError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during prediction generation: {e}")
        raise PredictionError(f"Error during prediction generation: {e}") from e


# Re-export persistence functions for backward compatibility
__all__ = [
    "generate_prediction",
    "save_prediction",
    "get_prediction_by_id",
    "get_predictions_by_race",
]


if __name__ == "__main__":
    # Logging setup
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    import asyncio

    async def test_prediction():
        """Test prediction generation."""
        # Test race ID (replace with existing race ID)
        test_race_id = "2024031005011112"

        try:
            prediction = await generate_prediction(race_id=test_race_id, is_final=False)

            print("\nPrediction Result (probability-based ranking):")
            print(f"Prediction ID: {prediction.prediction_id}")
            print(f"Race: {prediction.race_name}")
            print(
                f"Prediction confidence: {prediction.prediction_result.prediction_confidence:.2%}"
            )
            print("\nFull ranking:")
            for h in prediction.prediction_result.ranked_horses:
                print(
                    f"  Rank {h.rank}: #{h.horse_number} {h.horse_name} "
                    f"(Win: {h.win_probability:.1%}, Place: {h.place_probability:.1%})"
                )

        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(test_prediction())
