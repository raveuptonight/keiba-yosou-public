"""
レース関連のPydanticスキーマ
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from src.api.schemas.common import PrizeMoneyResponse


class RaceBase(BaseModel):
    """レース基本情報"""

    race_id: str = Field(
        ..., min_length=16, max_length=16, description="レースID（16桁）"
    )
    race_name: str = Field(..., description="レース名")
    race_number: str = Field(..., description="レース番号（例: '11R'）")
    race_time: str = Field(..., description="発走時刻（例: '15:25'）")
    venue: str = Field(..., description="競馬場名（例: '中山'）")
    venue_code: str = Field(..., description="競馬場コード（例: '05'）")
    grade: Optional[str] = Field(
        None, description="グレード（例: 'G1', 'G2', 'G3', '○'）"
    )
    distance: int = Field(..., gt=0, description="距離（メートル）")
    track_code: str = Field(..., description="馬場種別コード（10=芝, 20=ダート）")


class RaceEntry(BaseModel):
    """レース出走馬情報"""

    horse_number: int = Field(
        ..., ge=1, le=18, description="馬番（1-18）"
    )
    kettonum: str = Field(
        ..., min_length=10, max_length=10, description="血統登録番号（10桁）"
    )
    horse_name: str = Field(..., description="馬名")
    jockey_code: str = Field(..., description="騎手コード")
    jockey_name: str = Field(..., description="騎手名")
    trainer_code: str = Field(..., description="調教師コード")
    trainer_name: str = Field(..., description="調教師名")
    weight: float = Field(..., description="装着重量（kg）")
    horse_weight: Optional[int] = Field(
        None, description="馬体重（kg）"
    )
    odds: Optional[float] = Field(
        None, ge=0.1, description="単勝オッズ"
    )


class RaceDetail(RaceBase):
    """レース詳細情報"""

    track_condition: Optional[str] = Field(
        None, description="馬場状態（良/稍/重/不）"
    )
    weather: Optional[str] = Field(
        None, description="天気（晴/曇/小雨/雨）"
    )
    prize_money: PrizeMoneyResponse = Field(
        ..., description="賞金情報"
    )
    entries: List[RaceEntry] = Field(
        ..., description="出走馬一覧"
    )


class RaceListResponse(BaseModel):
    """レース一覧レスポンス"""

    date: str = Field(..., description="レース日（YYYY-MM-DD）")
    races: List[RaceBase] = Field(..., description="レース一覧")
    total: int = Field(..., ge=0, description="レース総数")
