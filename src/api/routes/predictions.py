"""
予想生成エンドポイント
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
    description="MLモデルによる競馬予想を生成します。"
)
async def generate_prediction(
    request: PredictionRequest
) -> PredictionResponse:
    """
    予想を生成

    機械学習モデルを使用してレース予想を生成します。
    データ集約、ML推論、DB保存を実行します。

    Args:
        request: 予想生成リクエスト

    Returns:
        PredictionResponse: 予想結果

    Raises:
        RaceNotFoundException: レースが見つからない
        DatabaseErrorException: DB接続エラー
    """
    logger.info(
        f"POST /predictions/generate: race_id={request.race_id}, is_final={request.is_final}"
    )

    try:
        response = await prediction_service.generate_prediction(
            race_id=request.race_id,
            is_final=request.is_final,
            bias_date=request.bias_date
        )
        logger.info(f"Prediction generated successfully: {response.prediction_id}")
        return response

    except ValueError as e:
        # レースが見つからない
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
    description="保存済み予想結果を取得します。"
)
async def get_prediction(
    prediction_id: str = Path(
        ...,
        description="予想ID（UUID）"
    )
) -> PredictionResponse:
    """
    保存済み予想を取得

    Args:
        prediction_id: 予想ID

    Returns:
        PredictionResponse: 予想結果

    Raises:
        PredictionNotFoundException: 予想が見つからない
        DatabaseErrorException: DB接続エラー
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
    description="特定レースの予想履歴を取得します。"
)
async def get_race_predictions(
    race_id: str = Path(
        ...,
        min_length=16,
        max_length=16,
        description="レースID（16桁）"
    ),
    is_final: bool | None = Query(
        None,
        description="最終予想のみ取得（true/false）"
    )
) -> PredictionHistoryResponse:
    """
    レースの予想履歴を取得

    Args:
        race_id: レースID（16桁）
        is_final: 最終予想フラグでフィルタ（オプション）

    Returns:
        PredictionHistoryResponse: 予想履歴

    Raises:
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /predictions/race/{race_id}?is_final={is_final}")

    try:
        # get_predictions_by_race は既に PredictionHistoryItem のリストを返す
        predictions = await prediction_service.get_predictions_by_race(
            race_id,
            is_final=is_final
        )

        response = PredictionHistoryResponse(
            race_id=race_id,
            predictions=predictions
        )

        logger.info(f"Found {len(predictions)} predictions for race {race_id}")
        return response

    except Exception as e:
        logger.error(f"Failed to get race predictions: {e}")
        raise DatabaseErrorException(str(e)) from e
