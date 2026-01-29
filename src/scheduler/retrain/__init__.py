"""
Weekly Model Retrain Module

Components for weekly model retraining, evaluation, and deployment.
"""

from src.scheduler.retrain.evaluator import (
    calculate_composite_score,
    compare_models,
    evaluate_model,
    get_ensemble_proba,
    get_payouts_for_year,
    simulate_returns,
)
from src.scheduler.retrain.manager import (
    backup_current_model,
    deploy_new_model,
)
from src.scheduler.retrain.notifier import (
    send_retrain_notification,
)
from src.scheduler.retrain.trainer import (
    calc_bin_stats,
    save_calibration_to_db,
    train_new_model,
)

__all__ = [
    # Trainer
    'train_new_model',
    'calc_bin_stats',
    'save_calibration_to_db',
    # Evaluator
    'compare_models',
    'evaluate_model',
    'get_ensemble_proba',
    'get_payouts_for_year',
    'simulate_returns',
    'calculate_composite_score',
    # Manager
    'backup_current_model',
    'deploy_new_model',
    # Notifier
    'send_retrain_notification',
]
