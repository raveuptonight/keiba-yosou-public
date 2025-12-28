"""
予想関連のPydanticスキーマ
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class HorseRanking(BaseModel):
    """予想馬情報（本命・対抗・単穴等）"""

    horse_number: int = Field(
        ..., ge=1, le=18, description="馬番（1-18）"
    )
    horse_name: str = Field(..., description="馬名")
    expected_odds: Optional[float] = Field(
        None, ge=0.1, description="予想オッズ"
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="信頼度（0.0-1.0）"
    )


class ExcludedHorse(BaseModel):
    """消し馬情報"""

    horse_number: int = Field(
        ..., ge=1, le=18, description="馬番（1-18）"
    )
    horse_name: str = Field(..., description="馬名")
    reason: Optional[str] = Field(
        None, description="消す理由"
    )


class WinPrediction(BaseModel):
    """1着予想情報"""

    first: HorseRanking = Field(
        ..., description="◎本命"
    )
    second: HorseRanking = Field(
        ..., description="○対抗"
    )
    third: HorseRanking = Field(
        ..., description="▲単穴"
    )
    fourth: Optional[HorseRanking] = Field(
        None, description="△連下"
    )
    fifth: Optional[HorseRanking] = Field(
        None, description="☆注目馬"
    )
    excluded: Optional[List[ExcludedHorse]] = Field(
        None, description="✕消し馬リスト"
    )


class RecommendedTicket(BaseModel):
    """推奨馬券情報"""

    ticket_type: str = Field(
        ..., description="馬券タイプ（単勝、馬連、3連複等）"
    )
    numbers: List[int] = Field(
        ..., min_items=1, description="馬番リスト"
    )
    amount: int = Field(
        ..., gt=0, description="購入金額（円）"
    )
    expected_payout: Optional[int] = Field(
        None, ge=0, description="期待払戻額（円）"
    )


class BettingStrategy(BaseModel):
    """投資戦略情報"""

    recommended_tickets: List[RecommendedTicket] = Field(
        ..., description="推奨馬券リスト"
    )


class PredictionResult(BaseModel):
    """予想結果本体"""

    win_prediction: WinPrediction = Field(
        ..., description="1着予想"
    )
    betting_strategy: BettingStrategy = Field(
        ..., description="投資戦略"
    )


class PredictionRequest(BaseModel):
    """予想生成リクエスト"""

    race_id: str = Field(
        ..., min_length=16, max_length=16, description="レースID（16桁）"
    )
    is_final: bool = Field(
        False, description="最終予想フラグ（馬体重後）"
    )
    total_investment: int = Field(
        10000, gt=0, description="総投資額（円）"
    )


class PredictionResponse(BaseModel):
    """予想生成レスポンス"""

    prediction_id: str = Field(
        ..., description="予想ID"
    )
    race_id: str = Field(
        ..., description="レースID"
    )
    race_name: str = Field(
        ..., description="レース名"
    )
    race_date: str = Field(
        ..., description="レース日（YYYY-MM-DD）"
    )
    venue: str = Field(
        ..., description="競馬場名"
    )
    race_number: str = Field(
        ..., description="レース番号"
    )
    race_time: str = Field(
        ..., description="発走時刻"
    )
    prediction_result: PredictionResult = Field(
        ..., description="予想結果本体"
    )
    total_investment: int = Field(
        ..., gt=0, description="総投資額（円）"
    )
    expected_return: int = Field(
        ..., ge=0, description="期待回収額（円）"
    )
    expected_roi: float = Field(
        ..., ge=0.0, description="期待ROI（倍率）"
    )
    predicted_at: datetime = Field(
        ..., description="予想実行日時"
    )
    is_final: bool = Field(
        ..., description="最終予想フラグ"
    )


class PredictionHistoryItem(BaseModel):
    """予想履歴アイテム"""

    prediction_id: str = Field(
        ..., description="予想ID"
    )
    predicted_at: datetime = Field(
        ..., description="予想実行日時"
    )
    is_final: bool = Field(
        ..., description="最終予想フラグ"
    )
    expected_roi: float = Field(
        ..., description="期待ROI（倍率）"
    )


class PredictionHistoryResponse(BaseModel):
    """予想履歴レスポンス"""

    race_id: str = Field(
        ..., description="レースID"
    )
    predictions: List[PredictionHistoryItem] = Field(
        ..., description="予想履歴一覧"
    )
