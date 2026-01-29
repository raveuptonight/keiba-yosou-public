"""
Persistence Module

Database operations for saving and retrieving predictions.
"""

import json
import logging
import os
import uuid
from datetime import date as date_type
from typing import Optional, List

import asyncpg

from src.api.schemas.prediction import (
    PredictionResponse,
    PredictionResult,
    HorseRankingEntry,
    PositionDistribution,
    PredictionHistoryItem,
)
from src.db.table_names import (
    COL_RACE_NAME,
    COL_JYOCD,
)
from src.exceptions import DatabaseQueryError
from src.services.prediction.track_adjustment import VENUE_CODE_MAP

logger = logging.getLogger(__name__)


def _is_mock_mode() -> bool:
    """Check if running in mock mode."""
    return os.getenv("DB_MODE", "local") == "mock"


async def save_prediction(prediction_data: PredictionResponse) -> str:
    """
    Save prediction result to database.

    Args:
        prediction_data: Prediction result

    Returns:
        str: Prediction ID

    Raises:
        DatabaseQueryError: If DB save fails
    """
    logger.debug(f"Saving prediction: race_id={prediction_data.race_id}")

    # Return generated UUID in mock mode
    if _is_mock_mode():
        prediction_id = str(uuid.uuid4())
        logger.info(f"[MOCK] Prediction saved: prediction_id={prediction_id}")
        return prediction_id

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            # Save to predictions table (UPSERT: unique on race_id + is_final)
            sql = """
                INSERT INTO predictions (
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (race_id, is_final) DO UPDATE SET
                    prediction_result = EXCLUDED.prediction_result,
                    predicted_at = EXCLUDED.predicted_at
                RETURNING prediction_id;
            """

            # Generate prediction_id (UUID based)
            prediction_id = str(uuid.uuid4())

            # Get prediction_result as dict (asyncpg auto-converts to JSONB)
            prediction_result_dict = prediction_data.prediction_result.model_dump()

            # Convert race_date to date type
            if isinstance(prediction_data.race_date, str):
                race_date = date_type.fromisoformat(prediction_data.race_date)
            else:
                race_date = prediction_data.race_date

            result = await conn.fetchrow(
                sql,
                prediction_id,
                prediction_data.race_id,
                race_date,
                prediction_data.is_final,
                json.dumps(prediction_result_dict),  # JSON string for asyncpg JSONB
                prediction_data.predicted_at,
            )

            if not result:
                raise DatabaseQueryError("Failed to save prediction result")

            saved_id = result["prediction_id"]
            logger.info(f"Prediction saved/updated: prediction_id={saved_id}")
            return saved_id

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while saving prediction: {e}")
        raise DatabaseQueryError(f"Failed to save prediction result: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while saving prediction: {e}")
        raise DatabaseQueryError(f"Error while saving prediction result: {e}") from e


async def get_prediction_by_id(prediction_id: str) -> Optional[PredictionResponse]:
    """
    Get saved prediction by ID.

    Args:
        prediction_id: Prediction ID

    Returns:
        PredictionResponse: Prediction result (None if not found)

    Raises:
        DatabaseQueryError: If DB retrieval fails
    """
    logger.debug(f"Fetching prediction: prediction_id={prediction_id}")

    # Mock mode
    if _is_mock_mode():
        logger.info(f"[MOCK] Prediction not found (mock mode): prediction_id={prediction_id}")
        return None

    try:
        from src.db.async_connection import get_connection
        from src.db.queries import get_race_info

        async with get_connection() as conn:
            sql = """
                SELECT
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                FROM predictions
                WHERE prediction_id = $1;
            """

            row = await conn.fetchrow(sql, prediction_id)

            if not row:
                logger.debug(f"Prediction not found: prediction_id={prediction_id}")
                return None

            # Get race info (race_name, etc.)
            race_info = await get_race_info(conn, row["race_id"])

            if not race_info:
                logger.warning(
                    f"Race info not found for prediction: race_id={row['race_id']}"
                )
                # Use default values
                race_name = "Unknown"
                venue = "Unknown"
                race_number = "?"
                race_time = "00:00"
            else:
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
                        "005": "1勝クラス", "010": "2勝クラス", "016": "3勝クラス",
                        "701": "新馬", "702": "未出走", "703": "未勝利", "999": "OP"
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

            # Convert to PredictionResponse
            prediction_result_data = row["prediction_result"]
            # Parse if stored as string
            if isinstance(prediction_result_data, str):
                try:
                    prediction_result_data = json.loads(prediction_result_data)
                except json.JSONDecodeError:
                    prediction_result_data = {"ranked_horses": [], "prediction_confidence": 0.5, "model_info": "unknown"}

            # Build ranking entries
            ranked_horses = [
                HorseRankingEntry(
                    rank=h["rank"],
                    horse_number=h["horse_number"],
                    horse_name=h["horse_name"],
                    horse_sex=h.get("horse_sex"),
                    horse_age=h.get("horse_age"),
                    jockey_name=h.get("jockey_name"),
                    win_probability=h["win_probability"],
                    quinella_probability=h.get("quinella_probability", h["win_probability"] + h.get("position_distribution", {}).get("second", 0)),
                    place_probability=h["place_probability"],
                    position_distribution=PositionDistribution(**h["position_distribution"]),
                    rank_score=h["rank_score"],
                    confidence=h["confidence"],
                )
                for h in prediction_result_data.get("ranked_horses", [])
            ]
            prediction_result = PredictionResult(
                ranked_horses=ranked_horses,
                quinella_ranking=prediction_result_data.get("quinella_ranking"),
                place_ranking=prediction_result_data.get("place_ranking"),
                dark_horses=prediction_result_data.get("dark_horses"),
                prediction_confidence=prediction_result_data.get("prediction_confidence", 0.5),
                model_info=prediction_result_data.get("model_info", "unknown"),
            )

            # Convert race_date to string
            race_date_raw = row["race_date"]
            if hasattr(race_date_raw, 'isoformat'):
                race_date_str = race_date_raw.isoformat()
            else:
                race_date_str = str(race_date_raw)

            prediction_response = PredictionResponse(
                prediction_id=row["prediction_id"],
                race_id=row["race_id"],
                race_name=race_name,
                race_date=race_date_str,
                venue=venue,
                race_number=race_number,
                race_time=race_time,
                prediction_result=prediction_result,
                predicted_at=row["predicted_at"],
                is_final=row["is_final"],
            )

            logger.info(f"Prediction fetched: prediction_id={prediction_id}")
            return prediction_response

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching prediction: {e}")
        raise DatabaseQueryError(f"Failed to retrieve prediction result: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching prediction: {e}")
        raise DatabaseQueryError(f"Error while retrieving prediction result: {e}") from e


async def get_predictions_by_race(
    race_id: str,
    is_final: Optional[bool] = None
) -> List[PredictionHistoryItem]:
    """
    Get prediction history for a race.

    Args:
        race_id: Race ID
        is_final: Filter by final prediction flag (None returns all)

    Returns:
        List[PredictionHistoryItem]: Prediction history list

    Raises:
        DatabaseQueryError: If DB retrieval fails
    """
    logger.debug(f"Fetching predictions by race: race_id={race_id}, is_final={is_final}")

    # Mock mode
    if _is_mock_mode():
        logger.info(f"[MOCK] No predictions (mock mode): race_id={race_id}")
        return []

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            if is_final is None:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        prediction_result
                    FROM predictions
                    WHERE race_id = $1
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id)
            else:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        prediction_result
                    FROM predictions
                    WHERE race_id = $1 AND is_final = $2
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id, is_final)

            predictions = []
            for row in rows:
                pred_result = row["prediction_result"]
                # Parse if stored as string
                if isinstance(pred_result, str):
                    try:
                        pred_result = json.loads(pred_result)
                    except json.JSONDecodeError:
                        pred_result = {}
                confidence = pred_result.get("prediction_confidence", 0.5) if pred_result else 0.5
                predictions.append(
                    PredictionHistoryItem(
                        prediction_id=row["prediction_id"],
                        predicted_at=row["predicted_at"],
                        is_final=row["is_final"],
                        prediction_confidence=confidence,
                    )
                )

            logger.info(
                f"Predictions fetched: race_id={race_id}, count={len(predictions)}"
            )
            return predictions

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching predictions: {e}")
        raise DatabaseQueryError(f"Failed to retrieve prediction history: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching predictions: {e}")
        raise DatabaseQueryError(f"Error while retrieving prediction history: {e}") from e
