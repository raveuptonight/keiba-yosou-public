"""
System-wide Configuration Constants

Centralized management of magic numbers and hardcoded values.
"""

import os
from typing import Final

from dotenv import load_dotenv

# Load .env file
load_dotenv()

# =====================================
# Database Connection Settings
# =====================================
DB_HOST: Final[str] = os.getenv("DB_HOST", "localhost")
DB_PORT: Final[int] = int(os.getenv("DB_PORT", "5432"))
DB_NAME: Final[str] = os.getenv("DB_NAME", "keiba_db")
DB_USER: Final[str] = os.getenv("DB_USER", "postgres")
DB_PASSWORD: Final[str] = os.getenv("DB_PASSWORD", "")

# Connection pool settings
DB_POOL_MIN_SIZE: Final[int] = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE: Final[int] = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# =====================================
# Database Settings
# =====================================
DB_DEFAULT_LEARNING_POINTS_LIMIT: Final[int] = 10
DB_DEFAULT_DAYS_BACK: Final[int] = 30
DB_DEFAULT_STATS_DAYS_BACK: Final[int] = 30
DB_CONNECTION_POOL_MIN: Final[int] = 1
DB_CONNECTION_POOL_MAX: Final[int] = 10

# =====================================
# Machine Learning Settings
# =====================================
# Outlier detection
ML_OUTLIER_THRESHOLD: Final[float] = 3.0  # Consider finish position error >= 3 as outlier
ML_OUTLIER_RATE_THRESHOLD: Final[float] = 0.3  # Recommend retraining if outlier rate > 30%
ML_FEATURE_VARIANCE_THRESHOLD: Final[float] = 0.2  # Feature variance threshold

# Retraining settings
ML_MIN_RETRAIN_SAMPLES: Final[int] = 100  # Minimum samples for retraining

# XGBoost parameters
XGBOOST_N_ESTIMATORS: Final[int] = 100
XGBOOST_MAX_DEPTH: Final[int] = 6
XGBOOST_LEARNING_RATE: Final[float] = 0.1
XGBOOST_SUBSAMPLE: Final[float] = 0.8
XGBOOST_COLSAMPLE_BYTREE: Final[float] = 0.8
XGBOOST_MIN_CHILD_WEIGHT: Final[int] = 1
XGBOOST_GAMMA: Final[float] = 0.0
XGBOOST_REG_ALPHA: Final[float] = 0.0
XGBOOST_REG_LAMBDA: Final[float] = 1.0
XGBOOST_RANDOM_STATE: Final[int] = 42

# =====================================
# API Settings
# =====================================
API_DEFAULT_HOST: Final[str] = "0.0.0.0"
API_DEFAULT_PORT: Final[int] = 8000
API_BASE_URL_DEFAULT: Final[str] = "http://localhost:8000"

# Pagination
API_DEFAULT_LIMIT: Final[int] = 10
API_MAX_LIMIT: Final[int] = 100

# Timeouts
API_REQUEST_TIMEOUT: Final[int] = 300  # 5 minutes
API_STATS_TIMEOUT: Final[int] = 10  # 10 seconds

# =====================================
# Discord Bot Settings
# =====================================
DISCORD_REQUEST_TIMEOUT: Final[int] = 300  # 5 minutes
DISCORD_STATS_TIMEOUT: Final[int] = 10  # 10 seconds
DISCORD_MAX_PREDICTIONS_DISPLAY: Final[int] = 5  # Max predictions to display
DISCORD_MAX_STATS_DISPLAY: Final[int] = 10  # Max stats to display

# Auto prediction scheduler settings
SCHEDULER_EVENING_PREDICTION_HOUR: Final[int] = 21  # Pre-race prediction execution hour
SCHEDULER_EVENING_PREDICTION_MINUTE: Final[int] = 0  # Pre-race prediction execution minute
SCHEDULER_CHECK_INTERVAL_MINUTES: Final[int] = 10  # Race time check interval (minutes)
SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE: Final[int] = (
    30  # Final prediction timing (minutes before race)
)
SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES: Final[int] = (
    5  # Final prediction time tolerance (minutes)
)

# =====================================
# CORS Settings (Security)
# =====================================
CORS_ALLOW_ORIGINS_DEV: Final[list] = ["*"]  # Development environment
CORS_ALLOW_ORIGINS_PROD: Final[list] = [
    "https://yourdomain.com",  # Replace with production domain
]

# =====================================
# Logging Settings
# =====================================
LOG_LEVEL: Final[str] = "INFO"
LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# =====================================
# File Paths
# =====================================
MODEL_DIR: Final[str] = "models"
MIGRATION_DIR: Final[str] = "src/db/migrations"

# =====================================
# Data Retrieval Period Settings
# =====================================
# Data period for ML training (years)
ML_TRAINING_YEARS_BACK: Final[int] = 10  # Use last 10 years of data

# Reference data period for race prediction (years)
PREDICTION_REFERENCE_YEARS: Final[int] = 5  # Mainly reference last 5 years

# Statistical data aggregation period (years)
STATS_MAX_YEARS_BACK: Final[int] = 10  # Aggregate up to 10 years of statistics

# =====================================
# Feature Settings
# =====================================
FEATURE_SPEED_INDEX_MIN: Final[float] = 0.0
FEATURE_SPEED_INDEX_MAX: Final[float] = 100.0
FEATURE_JOCKEY_WIN_RATE_MIN: Final[float] = 0.0
FEATURE_JOCKEY_WIN_RATE_MAX: Final[float] = 1.0

# Mock settings (for development)
FEATURE_MOCK_RANDOM_SEED: Final[int] = 42
