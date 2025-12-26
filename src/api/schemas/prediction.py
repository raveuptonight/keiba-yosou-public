"""
予想関連のPydanticスキーマ
"""

from datetime import date, datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class PredictionCreate(BaseModel):
    """予想作成リクエスト"""

    race_id: str = Field(..., description="レースID")
    temperature: float = Field(0.3, ge=0.0, le=1.0, description="LLM temperature")
    phase: str = Field("all", description="実行フェーズ (analyze/predict/all)")


class PredictionResponse(BaseModel):
    """予想レスポンス"""

    id: int
    race_id: str
    race_name: str
    race_date: date
    venue: Optional[str]

    # 予想内容
    analysis_result: Optional[Dict[str, Any]]
    prediction_result: Optional[Dict[str, Any]]

    # 投資・期待値
    total_investment: Optional[int]
    expected_return: Optional[int]
    expected_roi: Optional[float]

    # メタデータ
    llm_model: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    """予想一覧レスポンス"""

    predictions: List[PredictionResponse]
    total: int
    limit: int
    offset: int


class ResultCreate(BaseModel):
    """結果登録リクエスト"""

    prediction_id: int
    actual_result: Dict[str, Any]


class ResultResponse(BaseModel):
    """結果レスポンス"""

    id: int
    prediction_id: int

    # 実際の結果
    actual_result: Optional[Dict[str, Any]]

    # 収支
    total_return: Optional[int]
    profit: Optional[int]
    actual_roi: Optional[float]

    # 精度
    prediction_accuracy: Optional[float]

    # 反省内容
    reflection_result: Optional[Dict[str, Any]]

    updated_at: datetime

    class Config:
        from_attributes = True
