"""
FastAPI メインアプリケーション

競馬予想システムのREST API
目標: 回収率200%達成
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

# FastAPIアプリケーション作成
app = FastAPI(
    title="競馬予想API",
    description="回収率200%を目指す競馬予想システムのREST API",
    version="1.0.0",
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
from src.api.routes import predictions, stats

app.include_router(
    predictions.router, prefix="/api/predictions", tags=["predictions"]
)
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "競馬予想API - 回収率200%を目指す",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "healthy",
        "database": "not_connected",  # 後で実装
        "llm": os.getenv("LLM_PROVIDER", "gemini"),
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(app, host=host, port=port, reload=True)
