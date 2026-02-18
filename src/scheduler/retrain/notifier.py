"""
Notification Functions

Functions for sending retrain result notifications to Discord.
"""

import logging
import os

logger = logging.getLogger(__name__)


def send_retrain_notification(result: dict) -> None:
    """
    Send retrain result notification to Discord.

    Args:
        result: Retrain result dictionary
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    try:
        import requests

        training = result.get("training", {})

        # Get evaluation metrics
        win_auc = training.get("win_auc", 0)
        place_auc = training.get("place_auc", 0)
        win_brier = training.get("win_brier", 0)
        top3_coverage = training.get("top3_coverage", 0)

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

        deploy_label = "✅ 新モデルをデプロイしました" if result.get("deployed") else "⚠️ 改善なし、現行モデルを維持"

        lines = [
            "🔄 **週次モデル再学習完了**",
            "",
            "**混合モデル:**",
            f"学習サンプル数: {training.get('samples', 0):,}",
            "```",
            f"単勝AUC:     {win_auc:.4f} {get_icon(win_auc, 0.70, 0.80)}",
            f"複勝AUC:     {place_auc:.4f} {get_icon(place_auc, 0.65, 0.75)}",
            f"Brier(単勝): {win_brier:.4f} {get_icon(win_brier, 0.07, 0.05, True)}",
            f"Top-3カバー: {top3_coverage*100:.1f}% {get_icon(top3_coverage, 0.55, 0.65)}",
            "```",
            deploy_label,
        ]

        # Surface model results
        surface_models = result.get("surface_models", {})
        surface_names = {"turf": "芝", "dirt": "ダート"}
        for surface, label in surface_names.items():
            sr = surface_models.get(surface, {})
            st = sr.get("training", {})
            if st.get("status") == "success":
                s_deployed = "✅ デプロイ" if sr.get("deployed") else "⚠️ 維持"
                s_win_auc = st.get("win_auc", 0)
                s_place_auc = st.get("place_auc", 0)
                s_top3 = st.get("top3_coverage", 0)
                lines.extend([
                    "",
                    f"**{label}モデル:** {s_deployed}",
                    "```",
                    f"単勝AUC: {s_win_auc:.4f}  複勝AUC: {s_place_auc:.4f}  Top-3: {s_top3*100:.1f}%",
                    f"サンプル: {st.get('samples', 0):,}",
                    "```",
                ])
            elif st.get("status") == "error":
                lines.extend(["", f"**{label}モデル:** ❌ 学習失敗"])

        payload = {"content": "\n".join(lines)}
        requests.post(webhook_url, json=payload, timeout=10)

    except Exception as e:
        logger.error(f"Notification error: {e}")
