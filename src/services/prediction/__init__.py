"""
Prediction Service Module

Modular components for race prediction generation, adjustment, and persistence.
"""

from src.services.prediction.bias_adjustment import (
    apply_bias_to_scores,
    load_bias_for_date,
)
from src.services.prediction.ml_engine import (
    compute_ml_predictions,
    extract_future_race_features,
)
from src.services.prediction.persistence import (
    get_prediction_by_id,
    get_predictions_by_race,
    save_prediction,
)
from src.services.prediction.result_generator import (
    convert_to_prediction_response,
    generate_ml_only_prediction,
    generate_mock_prediction,
)
from src.services.prediction.track_adjustment import (
    BABA_CONDITION_MAP,
    VENUE_CODE_MAP,
    WEATHER_CODE_MAP,
    apply_track_condition_adjustment,
    get_current_track_condition,
    get_horse_baba_performance,
)

__all__ = [
    # Bias adjustment
    "load_bias_for_date",
    "apply_bias_to_scores",
    # Track adjustment
    "get_current_track_condition",
    "get_horse_baba_performance",
    "apply_track_condition_adjustment",
    "VENUE_CODE_MAP",
    "BABA_CONDITION_MAP",
    "WEATHER_CODE_MAP",
    # ML engine
    "extract_future_race_features",
    "compute_ml_predictions",
    # Result generator
    "generate_mock_prediction",
    "generate_ml_only_prediction",
    "convert_to_prediction_response",
    # Persistence
    "save_prediction",
    "get_prediction_by_id",
    "get_predictions_by_race",
]
