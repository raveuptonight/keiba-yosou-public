"""
予想関連のAPIルーティング
"""

import logging
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from src.config import (
    API_DEFAULT_LIMIT,
    API_MAX_LIMIT,
)
from src.api.schemas.prediction import (
    PredictionCreate,
    PredictionResponse,
    PredictionListResponse,
    ResultCreate,
    ResultResponse,
)

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


# モックデータ（DB接続前の開発用）
MOCK_PREDICTIONS = [
    {
        "id": 1,
        "race_id": "202412280506",
        "race_name": "有馬記念",
        "race_date": date(2024, 12, 28),
        "venue": "中山",
        "analysis_result": {"race_summary": "GⅠレース、2500m芝"},
        "prediction_result": {
            "win_prediction": {
                "first": {"horse_number": 3, "horse_name": "サンプルホース3"}
            }
        },
        "total_investment": 1000,
        "expected_return": 2000,
        "expected_roi": 2.0,
        "llm_model": "gemini-2.5-flash",
        "created_at": datetime.now(),
    }
]


@router.post("/", response_model=PredictionResponse, status_code=201)
async def create_prediction(prediction: PredictionCreate):
    """
    予想を実行

    Args:
        prediction: 予想リクエスト

    Returns:
        予想結果

    - **race_id**: レースID
    - **temperature**: LLMのtemperature設定
    - **phase**: 実行フェーズ (analyze/predict/all)
    """
    logger.info(f"予想実行リクエスト: race_id={prediction.race_id}, temperature={prediction.temperature}, phase={prediction.phase}")

    try:
        # TODO: 実際のパイプライン実行
        # from src.pipeline import HorsePredictionPipeline
        # pipeline = HorsePredictionPipeline()
        # result = pipeline.run_full_pipeline(race_data)

        # モックレスポンス
        new_prediction = {
            "id": len(MOCK_PREDICTIONS) + 1,
            "race_id": prediction.race_id,
            "race_name": "モックレース",
            "race_date": date.today(),
            "venue": "東京",
            "analysis_result": {"status": "analyzed"},
            "prediction_result": {"status": "predicted"},
            "total_investment": 1000,
            "expected_return": 2000,
            "expected_roi": 2.0,
            "llm_model": "gemini-2.5-flash",
            "created_at": datetime.now(),
        }

        MOCK_PREDICTIONS.append(new_prediction)
        logger.info(f"✅ 予想実行完了: prediction_id={new_prediction['id']}")
        return new_prediction

    except Exception as e:
        logger.error(f"予想実行エラー: {e}")
        raise HTTPException(status_code=500, detail=f"予想実行失敗: {str(e)}")


@router.get("/", response_model=PredictionListResponse)
async def get_predictions(
    limit: int = Query(API_DEFAULT_LIMIT, ge=1, le=API_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    race_date: Optional[date] = None,
):
    """
    予想一覧を取得

    Args:
        limit: 取得件数
        offset: オフセット
        race_date: レース日でフィルター（オプション）

    Returns:
        予想一覧

    - **limit**: 取得件数
    - **offset**: オフセット
    - **race_date**: レース日でフィルター（オプション）
    """
    logger.info(f"予想一覧取得リクエスト: limit={limit}, offset={offset}, race_date={race_date}")

    try:
        # TODO: DBから取得
        # from src.db.results import get_results_db
        # db = get_results_db()
        # predictions = db.get_recent_predictions(limit=limit)

        # モックデータ
        filtered = MOCK_PREDICTIONS
        if race_date:
            filtered = [p for p in filtered if p["race_date"] == race_date]

        total = len(filtered)
        paginated = filtered[offset : offset + limit]

        logger.debug(f"予想一覧取得成功: total={total}, returned={len(paginated)}")

        return {
            "predictions": paginated,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"予想一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"予想一覧取得失敗: {str(e)}")


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: int):
    """
    予想詳細を取得

    Args:
        prediction_id: 予想ID

    Returns:
        予想詳細

    Raises:
        HTTPException: 予想が見つからない場合

    - **prediction_id**: 予想ID
    """
    logger.info(f"予想詳細取得リクエスト: prediction_id={prediction_id}")

    try:
        # TODO: DBから取得
        # from src.db.results import get_results_db
        # db = get_results_db()
        # prediction = db.get_prediction_by_id(prediction_id)

        # モックデータ
        for p in MOCK_PREDICTIONS:
            if p["id"] == prediction_id:
                logger.debug(f"予想詳細取得成功: prediction_id={prediction_id}")
                return p

        logger.warning(f"予想が見つかりません: prediction_id={prediction_id}")
        raise HTTPException(status_code=404, detail="Prediction not found")

    except HTTPException:
        # 既知のエラーは再スロー
        raise
    except Exception as e:
        logger.error(f"予想詳細取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"予想詳細取得失敗: {str(e)}")


@router.post("/{prediction_id}/result", response_model=ResultResponse)
async def create_result(prediction_id: int, result: ResultCreate):
    """
    レース結果を登録して反省を実行

    Args:
        prediction_id: 予想ID
        result: レース結果

    Returns:
        反省結果

    Raises:
        HTTPException: 予想が見つからない場合

    - **prediction_id**: 予想ID
    - **actual_result**: 実際のレース結果
    """
    logger.info(f"結果登録リクエスト: prediction_id={prediction_id}")

    try:
        # TODO: 実際のパイプライン実行
        # from src.pipeline import HorsePredictionPipeline
        # pipeline = HorsePredictionPipeline()
        # reflection = pipeline.reflect(...)

        # モックレスポンス
        result_response = {
            "id": 1,
            "prediction_id": prediction_id,
            "actual_result": result.actual_result,
            "total_return": 1500,
            "profit": 500,
            "actual_roi": 1.5,
            "prediction_accuracy": 0.75,
            "reflection_result": {"status": "reflected"},
            "updated_at": datetime.now(),
        }

        logger.info(f"✅ 結果登録完了: prediction_id={prediction_id}")
        return result_response

    except Exception as e:
        logger.error(f"結果登録エラー: {e}")
        raise HTTPException(status_code=500, detail=f"結果登録失敗: {str(e)}")
