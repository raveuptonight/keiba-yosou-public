"""
統計情報関連のAPIルーティング
"""

from datetime import datetime, date
from typing import List
from fastapi import APIRouter, Query

from src.api.schemas.stats import StatsResponse, ROIHistory

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

    - **period**: 集計期間
      - `daily`: 日次
      - `weekly`: 週次
      - `monthly`: 月次
      - `all`: 全期間
    """
    # TODO: DBから取得
    # from src.db.results import get_results_db
    # db = get_results_db()
    # stats = db.get_stats(period)

    # モックデータ
    return MOCK_STATS


@router.get("/roi-history", response_model=List[ROIHistory])
async def get_roi_history(
    limit: int = Query(30, ge=1, le=100, description="取得件数")
):
    """
    ROI推移を取得

    - **limit**: 取得件数（デフォルト: 30件）
    """
    # TODO: DBから取得
    # SELECT race_date, race_name, actual_roi,
    #        AVG(actual_roi) OVER (ORDER BY race_date) as cumulative_roi
    # FROM predictions JOIN results ...

    # モックデータ
    return MOCK_ROI_HISTORY[:limit]


@router.post("/update")
async def update_stats(period: str = "all"):
    """
    統計情報を更新

    - **period**: 更新する集計期間
    """
    # TODO: 統計を再計算
    # from src.db.results import get_results_db
    # db = get_results_db()
    # db.update_stats(period, start_date, end_date)

    return {
        "status": "updated",
        "period": period,
        "message": "統計情報を更新しました（モック）",
    }
