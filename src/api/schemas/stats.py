"""
統計情報関連のPydanticスキーマ
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    """統計情報レスポンス"""

    id: int
    period: str = Field(..., description="集計期間 (daily/weekly/monthly/all)")
    start_date: Optional[date]
    end_date: Optional[date]

    # 基本統計
    total_races: int = Field(0, description="予想レース数")
    total_investment: int = Field(0, description="総投資額（円）")
    total_return: int = Field(0, description="総回収額（円）")
    total_profit: int = Field(0, description="総収支（円）")
    roi: Optional[float] = Field(None, description="回収率（％）")

    # 的中率
    hit_count: int = Field(0, description="的中数")
    hit_rate: Optional[float] = Field(None, description="的中率（0-1）")

    # その他
    best_roi: Optional[float] = Field(None, description="最高ROI")
    worst_roi: Optional[float] = Field(None, description="最低ROI")

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ROIHistory(BaseModel):
    """ROI推移データ"""

    race_date: date
    race_name: str
    roi: float
    cumulative_roi: float  # 累積ROI
