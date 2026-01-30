"""
API schema module.
"""

# Common schemas
from src.api.schemas.common import (
    ErrorDetail,
    ErrorResponse,
    HealthCheckResponse,
    PrizeMoneyResponse,
)

# Horse information schemas
from src.api.schemas.horse import (
    HorseDetail,
    Pedigree,
    RecentRace,
    Trainer,
)

# Odds-related schemas
from src.api.schemas.odds import (
    CombinationOdds,
    OddsResponse,
    SingleOdds,
)

# Prediction schemas (probability-based ranking format)
from src.api.schemas.prediction import (
    HorseRankingEntry,
    PositionDistribution,
    PredictionHistoryItem,
    PredictionHistoryResponse,
    PredictionRequest,
    PredictionResponse,
    PredictionResult,
)

# Race-related schemas
from src.api.schemas.race import (
    RaceBase,
    RaceDetail,
    RaceEntry,
    RaceListResponse,
)

# Statistics schemas
from src.api.schemas.stats import (
    DistanceStats,
    JockeyStatsResponse,
    ROIHistory,
    StatsBase,
    TrainerStatsResponse,
    VenueStats,
)

__all__ = [
    # Common schemas
    "PrizeMoneyResponse",
    "ErrorDetail",
    "ErrorResponse",
    "HealthCheckResponse",
    # Race-related
    "RaceBase",
    "RaceEntry",
    "RaceDetail",
    "RaceListResponse",
    # Prediction (probability-based ranking format)
    "PositionDistribution",
    "HorseRankingEntry",
    "PredictionResult",
    "PredictionRequest",
    "PredictionResponse",
    "PredictionHistoryItem",
    "PredictionHistoryResponse",
    # Horse information
    "Trainer",
    "Pedigree",
    "RecentRace",
    "HorseDetail",
    # Statistics
    "StatsBase",
    "VenueStats",
    "DistanceStats",
    "JockeyStatsResponse",
    "TrainerStatsResponse",
    "ROIHistory",
    # Odds-related
    "SingleOdds",
    "CombinationOdds",
    "OddsResponse",
]
