"""
Prediction Service

Service layer for generating, saving, and retrieving race predictions.
Uses ML ensemble models (XGBoost + LightGBM + CatBoost) for probability-based ranking.
"""

import logging
import os
from typing import Optional, List

from src.api.schemas.prediction import (
    PredictionResponse,
    PredictionHistoryItem,
)
from src.exceptions import (
    PredictionError,
    MissingDataError,
)
from src.services.prediction.ml_engine import compute_ml_predictions
from src.services.prediction.result_generator import (
    generate_mock_prediction,
    generate_ml_only_prediction,
    convert_to_prediction_response,
)
from src.services.prediction.persistence import (
    save_prediction,
    get_prediction_by_id,
    get_predictions_by_race,
)

logger = logging.getLogger(__name__)


def _is_mock_mode() -> bool:
    """Check if running in mock mode."""
    return os.getenv("DB_MODE", "local") == "mock"


async def generate_prediction(
    race_id: str,
    is_final: bool = False,
    bias_date: Optional[str] = None
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
            get_race_prediction_data,
            check_race_exists,
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
                raise MissingDataError(
                    f"Insufficient race data: race_id={race_id}"
                )

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
        ml_result = generate_ml_only_prediction(
            race_data=race_data,
            ml_scores=ml_scores
        )

        # 4. Convert prediction result to Pydantic model
        logger.debug("Converting ML result to PredictionResponse")
        prediction_response = convert_to_prediction_response(
            race_data=race_data,
            ml_result=ml_result,
            is_final=is_final
        )

        # 5. Save to DB
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
    'generate_prediction',
    'save_prediction',
    'get_prediction_by_id',
    'get_predictions_by_race',
]


if __name__ == "__main__":
    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    import asyncio

    async def test_prediction():
        """Test prediction generation."""
        # Test race ID (replace with existing race ID)
        test_race_id = "2024031005011112"

        try:
            prediction = await generate_prediction(
                race_id=test_race_id,
                is_final=False
            )

            print("\nPrediction Result (probability-based ranking):")
            print(f"Prediction ID: {prediction.prediction_id}")
            print(f"Race: {prediction.race_name}")
            print(f"Prediction confidence: {prediction.prediction_result.prediction_confidence:.2%}")
            print(f"\nFull ranking:")
            for h in prediction.prediction_result.ranked_horses:
                print(f"  Rank {h.rank}: #{h.horse_number} {h.horse_name} "
                      f"(Win: {h.win_probability:.1%}, Place: {h.place_probability:.1%})")

        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(test_prediction())
