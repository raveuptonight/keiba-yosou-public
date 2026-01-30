"""
Prediction generation endpoints.
"""

import logging

from fastapi import APIRouter, Path, Query, status

from src.api.exceptions import (
    DatabaseErrorException,
    PredictionNotFoundException,
    RaceNotFoundException,
)
from src.api.schemas.prediction import (
    PredictionHistoryResponse,
    PredictionRequest,
    PredictionResponse,
)
from src.services import prediction_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/predictions/generate",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="予想生成",
    description="MLモデルによる競馬予想を生成します。",
)
async def generate_prediction(request: PredictionRequest) -> PredictionResponse:
    """
    Generate prediction.

    Generates race predictions using machine learning models.
    Performs data aggregation, ML inference, and database storage.

    Args:
        request: Prediction generation request.

    Returns:
        PredictionResponse: Prediction result.

    Raises:
        RaceNotFoundException: Race not found.
        DatabaseErrorException: Database connection error.
    """
    logger.info(
        f"POST /predictions/generate: race_id={request.race_id}, is_final={request.is_final}"
    )

    try:
        response = await prediction_service.generate_prediction(
            race_id=request.race_id, is_final=request.is_final, bias_date=request.bias_date
        )
        logger.info(f"Prediction generated successfully: {response.prediction_id}")
        return response

    except ValueError as e:
        # Race not found
        logger.warning(f"Race not found: {e}")
        raise RaceNotFoundException(request.race_id) from e
    except Exception as e:
        logger.error(f"Failed to generate prediction: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/predictions/{prediction_id}",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="予想取得",
    description="保存済み予想結果を取得します。",
)
async def get_prediction(
    prediction_id: str = Path(..., description="予想ID（UUID）")
) -> PredictionResponse:
    """
    Get saved prediction.

    Args:
        prediction_id: Prediction ID.

    Returns:
        PredictionResponse: Prediction result.

    Raises:
        PredictionNotFoundException: Prediction not found.
        DatabaseErrorException: Database connection error.
    """
    logger.info(f"GET /predictions/{prediction_id}")

    try:
        response = await prediction_service.get_prediction_by_id(prediction_id)

        if not response:
            logger.warning(f"Prediction not found: {prediction_id}")
            raise PredictionNotFoundException(prediction_id)

        logger.info(f"Prediction retrieved: {prediction_id}")
        return response

    except PredictionNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Failed to get prediction: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/predictions/race/{race_id}",
    response_model=PredictionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="レース予想履歴取得",
    description="特定レースの予想履歴を取得します。",
)
async def get_race_predictions(
    race_id: str = Path(..., min_length=16, max_length=16, description="レースID（16桁）"),
    is_final: bool | None = Query(None, description="最終予想のみ取得（true/false）"),
) -> PredictionHistoryResponse:
    """
    Get prediction history for a race.

    Args:
        race_id: Race ID (16 digits).
        is_final: Filter by final prediction flag (optional).

    Returns:
        PredictionHistoryResponse: Prediction history.

    Raises:
        DatabaseErrorException: Database connection error.
    """
    logger.info(f"GET /predictions/race/{race_id}?is_final={is_final}")

    try:
        # get_predictions_by_race already returns a list of PredictionHistoryItem
        predictions = await prediction_service.get_predictions_by_race(race_id, is_final=is_final)

        response = PredictionHistoryResponse(race_id=race_id, predictions=predictions)

        logger.info(f"Found {len(predictions)} predictions for race {race_id}")
        return response

    except Exception as e:
        logger.error(f"Failed to get race predictions: {e}")
        raise DatabaseErrorException(str(e)) from e
