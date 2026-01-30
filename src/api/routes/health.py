"""
Health check endpoints.
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
    description="APIサーバーの稼働状態とDB接続状態を確認",
)
async def health_check() -> HealthCheckResponse:
    """
    Health check.

    Checks API server status, database connection, and Claude API status.

    Returns:
        HealthCheckResponse: Health check result.
    """
    logger.debug("Health check requested")

    # Database connection check
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

    # Claude API status check (currently always available)
    # TODO: Check actual API status
    claude_api_status = "available"

    # Status determination
    overall_status = "ok" if db_status == "connected" else "degraded"

    response = HealthCheckResponse(
        status=overall_status,
        timestamp=datetime.now(),
        database=db_status,
        claude_api=claude_api_status,
    )

    logger.info(
        f"Health check result: status={overall_status}, "
        f"database={db_status}, claude_api={claude_api_status}"
    )

    return response
