"""
Common schemas (error responses, etc.).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PrizeMoneyResponse(BaseModel):
    """Prize money information."""

    first: int = Field(..., description="1着賞金（円）")
    second: int = Field(..., description="2着賞金（円）")
    third: int = Field(..., description="3着賞金（円）")
    fourth: int = Field(..., description="4着賞金（円）")
    fifth: int = Field(..., description="5着賞金（円）")


class ErrorDetail(BaseModel):
    """Error response detail."""

    code: str = Field(..., description="エラーコード")
    message: str = Field(..., description="エラーメッセージ")
    details: dict[str, Any] | None = Field(None, description="詳細情報")


class ErrorResponse(BaseModel):
    """Error response."""

    error: ErrorDetail


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="ステータス (ok/ng)")
    timestamp: datetime = Field(..., description="チェック実行日時")
    database: str | None = Field(None, description="DB接続状態 (connected/disconnected)")
    claude_api: str | None = Field(None, description="Claude API状態 (available/unavailable)")
