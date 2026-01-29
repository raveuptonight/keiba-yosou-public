"""
Result Collector Module

Modular components for collecting race results, analyzing prediction accuracy,
and sending notifications.
"""

from src.scheduler.result.analyzer import (
    calculate_accuracy,
    compare_results,
)
from src.scheduler.result.db_operations import (
    get_cumulative_stats,
    get_payouts,
    get_race_results,
    get_recent_race_dates,
    load_predictions_from_db,
    save_analysis_to_db,
    update_accuracy_tracking,
)
from src.scheduler.result.notifier import (
    send_discord_notification,
    send_weekend_notification,
)

__all__ = [
    # DB operations
    "get_race_results",
    "get_payouts",
    "load_predictions_from_db",
    "save_analysis_to_db",
    "update_accuracy_tracking",
    "get_cumulative_stats",
    "get_recent_race_dates",
    # Analyzer
    "compare_results",
    "calculate_accuracy",
    # Notifier
    "send_discord_notification",
    "send_weekend_notification",
]
