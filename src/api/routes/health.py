"""
ヘルスチェックエンドポイント
"""

import logging
from datetime import datetime

from fastapi import APIRouter, status

from src.api.schemas.common import HealthCheckResponse
from src.db.async_connection import test_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="ヘルスチェック",
    description="APIサーバーの稼働状態とDB接続状態を確認"
)
async def health_check() -> HealthCheckResponse:
    """
    ヘルスチェック

    APIサーバーの稼働状態、DB接続、Claude API状態を確認します。

    Returns:
        HealthCheckResponse: ヘルスチェック結果
    """
    logger.debug("Health check requested")

    # DB接続チェック
    db_status = "disconnected"
    try:
        if await test_connection():
            db_status = "connected"
            logger.debug("Database connection: OK")
        else:
            logger.warning("Database connection: Failed")
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        db_status = "error"

    # Claude API状態チェック（現在は常にavailable）
    # TODO: 実際のAPI状態をチェック
    claude_api_status = "available"

    # ステータス判定
    overall_status = "ok" if db_status == "connected" else "degraded"

    response = HealthCheckResponse(
        status=overall_status,
        timestamp=datetime.now(),
        database=db_status,
        claude_api=claude_api_status
    )

    logger.info(
        f"Health check result: status={overall_status}, "
        f"database={db_status}, claude_api={claude_api_status}"
    )

    return response
