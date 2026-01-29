"""
FastAPI Main Application

REST API for horse racing prediction system.
Goal: Achieve 200% return rate.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.db.async_connection import init_db_pool, close_db_pool, get_connection
from src.db.code_master import initialize_code_cache

# Load .env file
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    logger.info("Starting FastAPI application...")
    try:
        await init_db_pool()
        logger.info("Database pool initialized")

        # Initialize code master cache
        async with get_connection() as conn:
            await initialize_code_cache(conn)
        logger.info("Code master cache initialized")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down FastAPI application...")
    try:
        await close_db_pool()
        logger.info("Database pool closed")
    except Exception as e:
        logger.error(f"Failed to close database pool: {e}")


# Create FastAPI application
app = FastAPI(
    title="Horse Racing Prediction API",
    description="REST API for horse racing prediction system aiming for 200% ROI",
    version="1.0.0",
    lifespan=lifespan
)

# CORS settings (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
from src.api.routes import health, races, horses, odds, predictions, jockeys, debug

app.include_router(health.router, tags=["health"])
app.include_router(debug.router, prefix="/api", tags=["debug"])

# /api/v1 prefix (for versioning)
app.include_router(races.router, prefix="/api/v1", tags=["races-v1"])
app.include_router(horses.router, prefix="/api/v1", tags=["horses-v1"])
app.include_router(jockeys.router, prefix="/api/v1", tags=["jockeys-v1"])
app.include_router(odds.router, prefix="/api/v1", tags=["odds-v1"])
app.include_router(predictions.router, prefix="/api/v1", tags=["predictions-v1"])

# /api prefix (backward compatibility & Discord Bot)
app.include_router(races.router, prefix="/api", tags=["races"])
app.include_router(horses.router, prefix="/api", tags=["horses"])
app.include_router(jockeys.router, prefix="/api", tags=["jockeys"])
app.include_router(odds.router, prefix="/api", tags=["odds"])
app.include_router(predictions.router, prefix="/api", tags=["predictions"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Horse Racing Prediction API - Aiming for 200% ROI",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(app, host=host, port=port, reload=True)
