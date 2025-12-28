"""
システム全体の設定定数

マジックナンバーやハードコード値を集約管理
"""

import os
from typing import Final

# =====================================
# データベース接続設定
# =====================================
DB_HOST: Final[str] = os.getenv("DB_HOST", "localhost")
DB_PORT: Final[int] = int(os.getenv("DB_PORT", "5432"))
DB_NAME: Final[str] = os.getenv("DB_NAME", "keiba_db")
DB_USER: Final[str] = os.getenv("DB_USER", "postgres")
DB_PASSWORD: Final[str] = os.getenv("DB_PASSWORD", "")

# 接続プール設定
DB_POOL_MIN_SIZE: Final[int] = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE: Final[int] = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# =====================================
# データベース設定
# =====================================
DB_DEFAULT_LEARNING_POINTS_LIMIT: Final[int] = 10
DB_DEFAULT_DAYS_BACK: Final[int] = 30
DB_DEFAULT_STATS_DAYS_BACK: Final[int] = 30
DB_CONNECTION_POOL_MIN: Final[int] = 1
DB_CONNECTION_POOL_MAX: Final[int] = 10

# =====================================
# 機械学習設定
# =====================================
# 外れ値判定
ML_OUTLIER_THRESHOLD: Final[float] = 3.0  # 着順誤差3着以上を外れ値とする
ML_OUTLIER_RATE_THRESHOLD: Final[float] = 0.3  # 外れ値率30%超で再学習推奨
ML_FEATURE_VARIANCE_THRESHOLD: Final[float] = 0.2  # 特徴量の分散閾値

# 再学習設定
ML_MIN_RETRAIN_SAMPLES: Final[int] = 100  # 最小再学習サンプル数

# XGBoostパラメータ
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
# LLM設定
# =====================================
LLM_DEFAULT_TEMPERATURE: Final[float] = 0.3
LLM_ANALYSIS_TEMPERATURE: Final[float] = 0.2  # Phase 1: データ分析
LLM_PREDICTION_TEMPERATURE: Final[float] = 0.3  # Phase 2: 予想生成
LLM_REFLECTION_TEMPERATURE: Final[float] = 0.2  # Phase 3: 失敗分析

# トークン制限
LLM_MAX_TOKENS: Final[int] = 8000

# Gemini設定
GEMINI_DEFAULT_MODEL: Final[str] = "gemini-2.0-flash-exp"
GEMINI_API_TIMEOUT: Final[int] = 60  # 60秒

# Claude設定
CLAUDE_DEFAULT_MODEL: Final[str] = "claude-3-5-sonnet-20241022"
CLAUDE_API_TIMEOUT: Final[int] = 60  # 60秒

# リトライ設定
LLM_MAX_RETRIES: Final[int] = 3
LLM_RETRY_DELAY: Final[float] = 1.0  # 秒

# =====================================
# プロンプト設定
# =====================================
# 学習ポイント取得設定
PROMPT_LEARNING_POINTS_LIMIT: Final[int] = 5  # 最大5レース分の学習ポイント
PROMPT_LEARNING_POINTS_PER_RACE: Final[int] = 2  # 各レースから最大2ポイント
PROMPT_LEARNING_POINTS_DAYS_BACK: Final[int] = 30  # 直近30日分

# ML予想表示設定
PROMPT_ML_TOP_HORSES_PHASE1: Final[int] = 3  # Phase 1で表示する上位頭数
PROMPT_ML_TOP_HORSES_PHASE2: Final[int] = 5  # Phase 2で表示する上位頭数

# =====================================
# API設定
# =====================================
API_DEFAULT_HOST: Final[str] = "0.0.0.0"
API_DEFAULT_PORT: Final[int] = 8000
API_BASE_URL_DEFAULT: Final[str] = "http://localhost:8000"

# ページネーション
API_DEFAULT_LIMIT: Final[int] = 10
API_MAX_LIMIT: Final[int] = 100

# タイムアウト
API_REQUEST_TIMEOUT: Final[int] = 300  # 5分
API_STATS_TIMEOUT: Final[int] = 10  # 10秒

# =====================================
# Discord Bot設定
# =====================================
DISCORD_REQUEST_TIMEOUT: Final[int] = 300  # 5分
DISCORD_STATS_TIMEOUT: Final[int] = 10  # 10秒
DISCORD_MAX_PREDICTIONS_DISPLAY: Final[int] = 5  # 予想表示最大件数
DISCORD_MAX_STATS_DISPLAY: Final[int] = 10  # 統計表示最大件数

# 自動予想スケジューラー設定
SCHEDULER_MORNING_PREDICTION_HOUR: Final[int] = 9  # 朝予想の実行時刻（時）
SCHEDULER_MORNING_PREDICTION_MINUTE: Final[int] = 0  # 朝予想の実行時刻（分）
SCHEDULER_CHECK_INTERVAL_MINUTES: Final[int] = 10  # レース時刻チェック間隔（分）
SCHEDULER_FINAL_PREDICTION_HOURS_BEFORE: Final[int] = 1  # 最終予想のタイミング（レース何時間前）
SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES: Final[int] = 5  # 最終予想の時刻許容範囲（分）

# =====================================
# 馬券設定
# =====================================
# 馬券タイプ定義
BETTING_TICKET_TYPES: Final[dict] = {
    "単勝": {"code": "WIN", "min_horses": 1, "max_horses": 1},
    "複勝": {"code": "PLACE", "min_horses": 1, "max_horses": 1},
    "枠連": {"code": "BRACKET_QUINELLA", "min_horses": 2, "max_horses": 2},
    "馬連": {"code": "QUINELLA", "min_horses": 2, "max_horses": 2},
    "ワイド": {"code": "WIDE", "min_horses": 2, "max_horses": 2},
    "馬単": {"code": "EXACTA", "min_horses": 2, "max_horses": 2},
    "3連複": {"code": "TRIO", "min_horses": 3, "max_horses": 3},
    "3連単": {"code": "TRIFECTA", "min_horses": 3, "max_horses": 3},
}

# 馬券購入設定
BETTING_MIN_AMOUNT: Final[int] = 100  # 最小購入金額（円）
BETTING_MAX_AMOUNT: Final[int] = 1000000  # 最大購入金額（円）
BETTING_UNIT_AMOUNT: Final[int] = 100  # 購入単位（円）
BETTING_MAX_COMBINATIONS: Final[int] = 50  # 最大組み合わせ数
BETTING_DEFAULT_BUDGET: Final[int] = 10000  # デフォルト予算（円）

# 買い目選定設定
BETTING_TOP_HORSES_COUNT: Final[int] = 8  # 買い目候補の馬数（上位N頭）
BETTING_MIN_CONFIDENCE: Final[float] = 0.3  # 最小信頼度（30%以上）

# =====================================
# CORS設定（セキュリティ）
# =====================================
CORS_ALLOW_ORIGINS_DEV: Final[list] = ["*"]  # 開発環境
CORS_ALLOW_ORIGINS_PROD: Final[list] = [
    "https://yourdomain.com",  # 本番環境のドメインに置き換える
]

# =====================================
# ロギング設定
# =====================================
LOG_LEVEL: Final[str] = "INFO"
LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# =====================================
# ファイルパス
# =====================================
DATA_DIR: Final[str] = "data"
LEARNING_DATA_DIR: Final[str] = "data/learning"
MODEL_DIR: Final[str] = "models"
MIGRATION_DIR: Final[str] = "src/db/migrations"

# =====================================
# データ取得期間設定
# =====================================
# 機械学習の訓練に使用するデータ期間（年）
ML_TRAINING_YEARS_BACK: Final[int] = 10  # 直近10年分のデータを使用

# レース予測時の参考データ期間（年）
PREDICTION_REFERENCE_YEARS: Final[int] = 5  # 直近5年分を主に参照

# 統計情報の集計期間（年）
STATS_MAX_YEARS_BACK: Final[int] = 10  # 最大10年分の統計を集計

# =====================================
# 特徴量設定
# =====================================
FEATURE_SPEED_INDEX_MIN: Final[float] = 0.0
FEATURE_SPEED_INDEX_MAX: Final[float] = 100.0
FEATURE_JOCKEY_WIN_RATE_MIN: Final[float] = 0.0
FEATURE_JOCKEY_WIN_RATE_MAX: Final[float] = 1.0

# モック設定（開発用）
FEATURE_MOCK_RANDOM_SEED: Final[int] = 42
