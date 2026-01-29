"""
オッズ関連のPydanticスキーマ
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SingleOdds(BaseModel):
    """単一馬番オッズ（単勝・複勝等）"""

    horse_number: int = Field(
        ..., ge=1, le=18, description="馬番（1-18）"
    )
    odds: float = Field(..., ge=0.1, description="オッズ")


class CombinationOdds(BaseModel):
    """複数馬番組み合わせオッズ（馬連・3連複等）"""

    numbers: list[int] = Field(
        ..., min_items=2, description="馬番リスト"
    )
    odds: float = Field(..., ge=0.1, description="オッズ")


class OddsResponse(BaseModel):
    """オッズ情報レスポンス"""

    race_id: str = Field(
        ..., min_length=16, max_length=16, description="レースID"
    )
    ticket_type: str = Field(
        ..., description="券種（win/place/quinella/exacta/trio/trifecta）"
    )
    updated_at: datetime = Field(
        ..., description="オッズ更新日時"
    )
    odds: list[SingleOdds | CombinationOdds] = Field(
        ..., description="オッズリスト"
    )
