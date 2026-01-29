"""
Notification Functions

Functions for sending retrain result notifications to Discord.
"""

import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


def send_retrain_notification(result: Dict) -> None:
    """
    Send retrain result notification to Discord.

    Args:
        result: Retrain result dictionary
    """
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return

    try:
        import requests

        training = result.get('training', {})

        # Get evaluation metrics
        win_auc = training.get('win_auc', 0)
        place_auc = training.get('place_auc', 0)
        win_brier = training.get('win_brier', 0)
        top3_coverage = training.get('top3_coverage', 0)

        # Evaluation icon helper
        def get_icon(value, good, excellent, lower_is_better=False):
            if lower_is_better:
                if value <= excellent:
                    return "🌟"
                elif value <= good:
                    return "✅"
                else:
                    return "⚠️"
            else:
                if value >= excellent:
                    return "🌟"
                elif value >= good:
                    return "✅"
                else:
                    return "⚠️"

        if result.get('deployed'):
            lines = [
                "🔄 **Weekly Model Retrain Complete**",
                "",
                f"Training samples: {training.get('samples', 0):,}",
                "",
                "📊 **Evaluation Metrics:**",
                f"```",
                f"Win AUC:       {win_auc:.4f} {get_icon(win_auc, 0.70, 0.80)}",
                f"Place AUC:     {place_auc:.4f} {get_icon(place_auc, 0.65, 0.75)}",
                f"Brier (win):   {win_brier:.4f} {get_icon(win_brier, 0.07, 0.05, True)}",
                f"Top-3 coverage: {top3_coverage*100:.1f}% {get_icon(top3_coverage, 0.55, 0.65)}",
                f"```",
                "",
                "✅ New model deployed"
            ]
        else:
            lines = [
                "🔄 **Weekly Model Retrain Complete**",
                "",
                f"Training samples: {training.get('samples', 0):,}",
                "",
                "📊 **Evaluation Metrics:**",
                f"```",
                f"Win AUC:       {win_auc:.4f} {get_icon(win_auc, 0.70, 0.80)}",
                f"Place AUC:     {place_auc:.4f} {get_icon(place_auc, 0.65, 0.75)}",
                f"Brier (win):   {win_brier:.4f} {get_icon(win_brier, 0.07, 0.05, True)}",
                f"Top-3 coverage: {top3_coverage*100:.1f}% {get_icon(top3_coverage, 0.55, 0.65)}",
                f"```",
                "",
                "⚠️ No improvement, keeping current model"
            ]

        payload = {"content": "\n".join(lines)}
        requests.post(webhook_url, json=payload, timeout=10)

    except Exception as e:
        logger.error(f"Notification error: {e}")
