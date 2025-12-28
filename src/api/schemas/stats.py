"""
統計情報関連のPydanticスキーマ
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class StatsBase(BaseModel):
    """統計情報基本"""

    total_races: int = Field(..., ge=0, description="総出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    places: int = Field(..., ge=0, description="2着数")
    shows: int = Field(..., ge=0, description="3着数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")
    place_rate: float = Field(..., ge=0.0, le=1.0, description="入着率")
    prize_money: int = Field(..., ge=0, description="獲得賞金（円）")


class VenueStats(BaseModel):
    """競馬場別統計"""

    venue: str = Field(..., description="競馬場名")
    races: int = Field(..., ge=0, description="出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")


class DistanceStats(BaseModel):
    """距離別統計"""

    range: str = Field(
        ..., description="距離範囲（例: '1200-1600'）"
    )
    races: int = Field(..., ge=0, description="出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")


class JockeyStatsResponse(BaseModel):
    """騎手成績統計"""

    jockey_code: str = Field(..., description="騎手コード")
    jockey_name: str = Field(..., description="騎手名")
    year: int = Field(..., description="集計年")
    stats: StatsBase = Field(..., description="統計情報")
    by_venue: List[VenueStats] = Field(
        ..., description="競馬場別統計"
    )
    by_distance: List[DistanceStats] = Field(
        ..., description="距離別統計"
    )


class TrainerStatsResponse(BaseModel):
    """調教師成績統計"""

    trainer_code: str = Field(..., description="調教師コード")
    trainer_name: str = Field(..., description="調教師名")
    year: int = Field(..., description="集計年")
    stats: StatsBase = Field(..., description="統計情報")
    by_venue: List[VenueStats] = Field(
        ..., description="競馬場別統計"
    )
    by_distance: List[DistanceStats] = Field(
        ..., description="距離別統計"
    )


class ROIHistory(BaseModel):
    """ROI推移データ"""

    race_date: date
    race_name: str
    roi: float
    cumulative_roi: float
