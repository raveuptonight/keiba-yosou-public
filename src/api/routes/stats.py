"""
統計情報関連のAPIルーティング
"""

import logging
from datetime import datetime, date
from typing import List
from fastapi import APIRouter, Query, HTTPException

from src.config import (
    API_DEFAULT_LIMIT,
    API_MAX_LIMIT,
)
from src.api.schemas.stats import StatsResponse, ROIHistory

# ロガー設定
logger = logging.getLogger(__name__)

router = APIRouter()


# モックデータ
MOCK_STATS = {
    "id": 1,
    "period": "all",
    "start_date": None,
    "end_date": None,
    "total_races": 10,
    "total_investment": 10000,
    "total_return": 18000,
    "total_profit": 8000,
    "roi": 180.0,  # 目標は200%！
    "hit_count": 6,
    "hit_rate": 0.60,
    "best_roi": 5.0,
    "worst_roi": 0.0,
    "created_at": datetime.now(),
    "updated_at": datetime.now(),
}

MOCK_ROI_HISTORY = [
    {
        "race_date": date(2024, 12, 20),
        "race_name": "モックレース1",
        "roi": 2.5,
        "cumulative_roi": 2.5,
    },
    {
        "race_date": date(2024, 12, 21),
        "race_name": "モックレース2",
        "roi": 1.8,
        "cumulative_roi": 2.15,
    },
    {
        "race_date": date(2024, 12, 22),
        "race_name": "モックレース3",
        "roi": 0.5,
        "cumulative_roi": 1.6,
    },
]


@router.get("/", response_model=StatsResponse)
async def get_stats(
    period: str = Query("all", description="集計期間 (daily/weekly/monthly/all)")
):
    """
    統計情報を取得

    Args:
        period: 集計期間

    Returns:
        統計情報

    Raises:
        HTTPException: 統計取得に失敗した場合

    - **period**: 集計期間
      - `daily`: 日次
      - `weekly`: 週次
      - `monthly`: 月次
      - `all`: 全期間
    """
    logger.info(f"統計情報取得リクエスト: period={period}")

    try:
        # TODO: DBから取得
        # from src.db.results import get_results_db
        # db = get_results_db()
        # stats = db.get_stats(period)

        # モックデータ
        logger.debug(f"統計情報取得成功: total_races={MOCK_STATS['total_races']}, roi={MOCK_STATS['roi']}")
        return MOCK_STATS

    except Exception as e:
        logger.error(f"統計情報取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"統計情報取得失敗: {str(e)}")


@router.get("/roi-history", response_model=List[ROIHistory])
async def get_roi_history(
    limit: int = Query(30, ge=1, le=API_MAX_LIMIT, description="取得件数")
):
    """
    ROI推移を取得

    Args:
        limit: 取得件数

    Returns:
        ROI推移リスト

    Raises:
        HTTPException: ROI推移取得に失敗した場合

    - **limit**: 取得件数（デフォルト: 30件）
    """
    logger.info(f"ROI推移取得リクエスト: limit={limit}")

    try:
        # TODO: DBから取得
        # SELECT race_date, race_name, actual_roi,
        #        AVG(actual_roi) OVER (ORDER BY race_date) as cumulative_roi
        # FROM predictions JOIN results ...

        # モックデータ
        result = MOCK_ROI_HISTORY[:limit]
        logger.debug(f"ROI推移取得成功: count={len(result)}")
        return result

    except Exception as e:
        logger.error(f"ROI推移取得エラー: {e}")
        raise HTTPException(status_code=500, detail=f"ROI推移取得失敗: {str(e)}")


@router.post("/update")
async def update_stats(period: str = "all"):
    """
    統計情報を更新

    Args:
        period: 更新する集計期間

    Returns:
        更新結果

    Raises:
        HTTPException: 統計更新に失敗した場合

    - **period**: 更新する集計期間
    """
    logger.info(f"統計情報更新リクエスト: period={period}")

    try:
        # TODO: 統計を再計算
        # from src.db.results import get_results_db
        # db = get_results_db()
        # db.update_stats(period, start_date, end_date)

        response = {
            "status": "updated",
            "period": period,
            "message": "統計情報を更新しました（モック）",
        }

        logger.info(f"✅ 統計情報更新完了（モック）: period={period}")
        return response

    except Exception as e:
        logger.error(f"統計情報更新エラー: {e}")
        raise HTTPException(status_code=500, detail=f"統計情報更新失敗: {str(e)}")
