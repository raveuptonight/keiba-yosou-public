"""
FastAPI メインアプリケーション

競馬予想システムのREST API
目標: 回収率200%達成
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.db.async_connection import init_db_pool, close_db_pool

# .envファイルを読み込み
load_dotenv()

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル管理"""
    # 起動時
    logger.info("Starting FastAPI application...")
    try:
        await init_db_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

    yield

    # シャットダウン時
    logger.info("Shutting down FastAPI application...")
    try:
        await close_db_pool()
        logger.info("Database pool closed")
    except Exception as e:
        logger.error(f"Failed to close database pool: {e}")


# FastAPIアプリケーション作成
app = FastAPI(
    title="競馬予想API",
    description="回収率200%を目指す競馬予想システムのREST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS設定（開発用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切に設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ルーター登録
from src.api.routes import health, races, horses, odds, predictions, jockeys

app.include_router(health.router, tags=["health"])

# /api/v1 プレフィックス (バージョニング用)
app.include_router(races.router, prefix="/api/v1", tags=["races-v1"])
app.include_router(horses.router, prefix="/api/v1", tags=["horses-v1"])
app.include_router(jockeys.router, prefix="/api/v1", tags=["jockeys-v1"])
app.include_router(odds.router, prefix="/api/v1", tags=["odds-v1"])
app.include_router(predictions.router, prefix="/api/v1", tags=["predictions-v1"])

# /api プレフィックス (後方互換性 & Discord Bot用)
app.include_router(races.router, prefix="/api", tags=["races"])
app.include_router(horses.router, prefix="/api", tags=["horses"])
app.include_router(jockeys.router, prefix="/api", tags=["jockeys"])
app.include_router(odds.router, prefix="/api", tags=["odds"])
app.include_router(predictions.router, prefix="/api", tags=["predictions"])


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "競馬予想API - 回収率200%を目指す",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(app, host=host, port=port, reload=True)
