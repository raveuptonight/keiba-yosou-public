"""
Prediction Service Module

Modular components for race prediction generation, adjustment, and persistence.
"""

from src.services.prediction.bias_adjustment import (
    load_bias_for_date,
    apply_bias_to_scores,
)
from src.services.prediction.track_adjustment import (
    get_current_track_condition,
    get_horse_baba_performance,
    apply_track_condition_adjustment,
    VENUE_CODE_MAP,
    BABA_CONDITION_MAP,
    WEATHER_CODE_MAP,
)
from src.services.prediction.ml_engine import (
    extract_future_race_features,
    compute_ml_predictions,
)
from src.services.prediction.result_generator import (
    generate_mock_prediction,
    generate_ml_only_prediction,
    convert_to_prediction_response,
)
from src.services.prediction.persistence import (
    save_prediction,
    get_prediction_by_id,
    get_predictions_by_race,
)

__all__ = [
    # Bias adjustment
    'load_bias_for_date',
    'apply_bias_to_scores',
    # Track adjustment
    'get_current_track_condition',
    'get_horse_baba_performance',
    'apply_track_condition_adjustment',
    'VENUE_CODE_MAP',
    'BABA_CONDITION_MAP',
    'WEATHER_CODE_MAP',
    # ML engine
    'extract_future_race_features',
    'compute_ml_predictions',
    # Result generator
    'generate_mock_prediction',
    'generate_ml_only_prediction',
    'convert_to_prediction_response',
    # Persistence
    'save_prediction',
    'get_prediction_by_id',
    'get_predictions_by_race',
]
