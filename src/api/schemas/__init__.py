"""
API スキーマモジュール
"""

# 共通スキーマ
from src.api.schemas.common import (
    PrizeMoneyResponse,
    ErrorDetail,
    ErrorResponse,
    HealthCheckResponse,
)

# レース関連スキーマ
from src.api.schemas.race import (
    RaceBase,
    RaceEntry,
    RaceDetail,
    RaceListResponse,
)

# 予想関連スキーマ（確率ベース・ランキング形式）
from src.api.schemas.prediction import (
    PositionDistribution,
    HorseRankingEntry,
    PredictionResult,
    PredictionRequest,
    PredictionResponse,
    PredictionHistoryItem,
    PredictionHistoryResponse,
)

# 馬情報関連スキーマ
from src.api.schemas.horse import (
    Trainer,
    Pedigree,
    RecentRace,
    HorseDetail,
)

# 統計関連スキーマ
from src.api.schemas.stats import (
    StatsBase,
    VenueStats,
    DistanceStats,
    JockeyStatsResponse,
    TrainerStatsResponse,
    ROIHistory,
)

# オッズ関連スキーマ
from src.api.schemas.odds import (
    SingleOdds,
    CombinationOdds,
    OddsResponse,
)

__all__ = [
    # 共通スキーマ
    "PrizeMoneyResponse",
    "ErrorDetail",
    "ErrorResponse",
    "HealthCheckResponse",
    # レース関連
    "RaceBase",
    "RaceEntry",
    "RaceDetail",
    "RaceListResponse",
    # 予想関連（確率ベース・ランキング形式）
    "PositionDistribution",
    "HorseRankingEntry",
    "PredictionResult",
    "PredictionRequest",
    "PredictionResponse",
    "PredictionHistoryItem",
    "PredictionHistoryResponse",
    # 馬情報関連
    "Trainer",
    "Pedigree",
    "RecentRace",
    "HorseDetail",
    # 統計関連
    "StatsBase",
    "VenueStats",
    "DistanceStats",
    "JockeyStatsResponse",
    "TrainerStatsResponse",
    "ROIHistory",
    # オッズ関連
    "SingleOdds",
    "CombinationOdds",
    "OddsResponse",
]
