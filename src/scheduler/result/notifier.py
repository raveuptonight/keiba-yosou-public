"""
Discord Notification Module

Functions for sending prediction result notifications to Discord.
"""

import logging
import os
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)


def send_discord_notification(analysis: dict):
    """
    Send Discord notification with EV recommendation and axis horse stats.

    Args:
        analysis: Analysis result dictionary
    """
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID")

    if not bot_token or not channel_id:
        logger.warning("Discord notification settings not configured")
        return

    acc = analysis.get("accuracy", {})
    if "error" in acc:
        return

    date_str = acc.get("date", "Unknown")
    n = acc.get("analyzed_races", 0)
    ev_stats = acc.get("ev_stats", {})
    axis_stats = acc.get("axis_stats", {})
    by_venue = acc.get("by_venue", {})

    # Basic message header
    lines = [
        f"📊 **{date_str} 予想結果レポート**",
        f"分析レース数: {n}R",
        "",
    ]

    # EV recommendation stats (separate for win/place)
    ev_tansho_count = ev_stats.get("ev_rec_count", 0)  # Win EV count
    ev_fukusho_count = ev_stats.get("ev_rec_fukusho_count", 0)  # Place EV count

    if ev_tansho_count > 0 or ev_fukusho_count > 0:
        lines.append("**【EV推奨】** (EV >= 1.5)")
        # Win EV recommendations
        if ev_tansho_count > 0:
            lines.append(f"  **単勝**: {ev_tansho_count}頭")
            lines.append(
                f"    {ev_stats.get('ev_rec_tansho_hit', 0)}的中 "
                f"({ev_stats.get('ev_tansho_rate', 0):.0f}%) "
                f"ROI {ev_stats.get('ev_tansho_roi', 0):.0f}%"
            )
            lines.append(
                f"    回収: {ev_stats.get('ev_tansho_return', 0):,}円 / "
                f"{ev_stats.get('ev_tansho_investment', 0):,}円"
            )
        else:
            lines.append("  **単勝**: 推奨なし")
        # Place EV recommendations
        if ev_fukusho_count > 0:
            lines.append(f"  **複勝**: {ev_fukusho_count}頭")
            lines.append(
                f"    {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 "
                f"({ev_stats.get('ev_fukusho_rate', 0):.0f}%) "
                f"ROI {ev_stats.get('ev_fukusho_roi', 0):.0f}%"
            )
            lines.append(
                f"    回収: {ev_stats.get('ev_fukusho_return', 0):,}円 / "
                f"{ev_stats.get('ev_fukusho_investment', 0):,}円"
            )
        else:
            lines.append("  **複勝**: 推奨なし")
    else:
        lines.append("**【EV推奨】** (EV >= 1.5)")
        lines.append("  推奨なし")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get("axis_races", 0)
    if axis_races > 0:
        lines.append("**【軸馬成績】** (複勝率最高馬)")
        lines.append(
            f"  着順: 1着 {axis_stats.get('axis_tansho_hit', 0)}回({axis_stats.get('axis_tansho_rate', 0):.0f}%) / "
            f"2着 {axis_stats.get('axis_2nd_hit', 0)}回({axis_stats.get('axis_2nd_rate', 0):.0f}%) / "
            f"3着 {axis_stats.get('axis_3rd_hit', 0)}回({axis_stats.get('axis_3rd_rate', 0):.0f}%) "
            f"**着内率 {axis_stats.get('axis_fukusho_rate', 0):.0f}%**"
        )
        lines.append(
            f"  単勝: ROI {axis_stats.get('axis_tansho_roi', 0):.0f}% "
            f"(回収 {axis_stats.get('axis_tansho_return', 0):,}円 / "
            f"{axis_stats.get('axis_tansho_investment', 0):,}円)"
        )
        lines.append(
            f"  複勝: ROI {axis_stats.get('axis_fukusho_roi', 0):.0f}% "
            f"(回収 {axis_stats.get('axis_fukusho_return', 0):,}円 / "
            f"{axis_stats.get('axis_fukusho_investment', 0):,}円)"
        )

    # By venue stats
    if by_venue:
        lines.append("")
        lines.append("**【競馬場別】**")
        for venue, data in sorted(by_venue.items(), key=lambda x: -x[1].get("races", 0)):
            r = data.get("races", 0)
            lines.append(
                f"  {venue} {r}R: "
                f"単勝{data.get('top1_rate', 0):.0f}% ROI {data.get('tansho_roi', 0):.0f}% / "
                f"複勝{data.get('top3_rate', 0):.0f}% ROI {data.get('fukusho_roi', 0):.0f}%"
            )

    # Failure analysis section
    failure = acc.get("failure_analysis", {})
    if failure and failure.get("total_misses", 0) > 0:
        lines.append("")
        lines.append("**【的外し分析】**")
        lines.append(
            f"  大穴: {failure.get('upset', 0)}件 / "
            f"惜しい: {failure.get('close_call', 0)}件 / "
            f"見落とし: {failure.get('blind_spot', 0)}件"
        )
        for bs in failure.get("blind_spot_details", []):
            lines.append(
                f"    → {bs['winner_name']}({bs['winner_ninki']}人気) "
                f"予測{bs['predicted_rank']}位 勝率{bs['win_prob']:.1%}"
            )
        for w in failure.get("weaknesses", []):
            lines.append(
                f"  ⚠ {w['category']}:{w['value']} "
                f"Top3率{w['cover_rate']:.0%} (平均{w['avg_cover_rate']:.0%})"
            )

    message = "\n".join(lines)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, headers=headers, json={"content": message}, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Discord notification sent")
        else:
            logger.warning(f"Discord notification failed: {response.status_code}")
    except Exception as e:
        logger.error(f"Discord notification error: {e}")


def send_weekend_notification(
    saturday: date,
    sunday: date,
    stats: dict,
    ranking_stats: dict | None = None,
    return_rates: dict | None = None,
    popularity_stats: dict | None = None,
    confidence_stats: dict | None = None,
    by_track: dict | None = None,
    daily_data: dict | None = None,
    cumulative: dict | None = None,
    ev_stats: dict | None = None,
    axis_stats: dict | None = None,
    by_venue: dict | None = None,
    failure_analysis: dict | None = None,
):
    """
    Send weekend total Discord notification with EV recommendation and axis horse stats.

    Args:
        saturday: Saturday date
        sunday: Sunday date
        stats: Statistics dictionary
        ranking_stats: Optional ranking stats
        return_rates: Optional return rate data
        popularity_stats: Optional popularity stats
        confidence_stats: Optional confidence stats
        by_track: Optional turf/dirt stats
        daily_data: Optional daily data for interaction
        cumulative: Optional cumulative stats
        ev_stats: Optional EV stats
        axis_stats: Optional axis horse stats
    """
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID")

    if not bot_token or not channel_id:
        logger.warning("Discord notification settings not configured")
        return

    ev_stats = ev_stats or {}
    axis_stats = axis_stats or {}

    lines = [
        "📊 **週末予想結果レポート**",
        f"期間: {saturday} - {sunday}",
        f"分析レース数: {stats.get('analyzed_races', 0)}R",
        "",
    ]

    # EV recommendation stats (separate for win/place)
    ev_tansho_count = ev_stats.get("ev_rec_count", 0)  # Win EV count
    ev_fukusho_count = ev_stats.get("ev_rec_fukusho_count", 0)  # Place EV count

    if ev_tansho_count > 0 or ev_fukusho_count > 0:
        lines.append("**【EV推奨】** (EV >= 1.5)")
        # Win EV recommendations
        if ev_tansho_count > 0:
            lines.append(f"  **単勝**: {ev_tansho_count}頭")
            lines.append(
                f"    {ev_stats.get('ev_rec_tansho_hit', 0)}的中 "
                f"({ev_stats.get('ev_tansho_rate', 0):.0f}%) "
                f"ROI {ev_stats.get('ev_tansho_roi', 0):.0f}%"
            )
            lines.append(
                f"    回収: {ev_stats.get('ev_tansho_return', 0):,}円 / "
                f"{ev_stats.get('ev_tansho_investment', 0):,}円"
            )
        else:
            lines.append("  **単勝**: 推奨なし")
        # Place EV recommendations
        if ev_fukusho_count > 0:
            lines.append(f"  **複勝**: {ev_fukusho_count}頭")
            lines.append(
                f"    {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 "
                f"({ev_stats.get('ev_fukusho_rate', 0):.0f}%) "
                f"ROI {ev_stats.get('ev_fukusho_roi', 0):.0f}%"
            )
            lines.append(
                f"    回収: {ev_stats.get('ev_fukusho_return', 0):,}円 / "
                f"{ev_stats.get('ev_fukusho_investment', 0):,}円"
            )
        else:
            lines.append("  **複勝**: 推奨なし")
    else:
        lines.append("**【EV推奨】** (EV >= 1.5)")
        lines.append("  推奨なし")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get("axis_races", 0)
    if axis_races > 0:
        lines.append("**【軸馬成績】** (複勝率最高馬)")
        lines.append(
            f"  着順: 1着 {axis_stats.get('axis_tansho_hit', 0)}回({axis_stats.get('axis_tansho_rate', 0):.0f}%) / "
            f"2着 {axis_stats.get('axis_2nd_hit', 0)}回({axis_stats.get('axis_2nd_rate', 0):.0f}%) / "
            f"3着 {axis_stats.get('axis_3rd_hit', 0)}回({axis_stats.get('axis_3rd_rate', 0):.0f}%) "
            f"**着内率 {axis_stats.get('axis_fukusho_rate', 0):.0f}%**"
        )
        lines.append(
            f"  単勝: ROI {axis_stats.get('axis_tansho_roi', 0):.0f}% "
            f"(回収 {axis_stats.get('axis_tansho_return', 0):,}円 / "
            f"{axis_stats.get('axis_tansho_investment', 0):,}円)"
        )
        lines.append(
            f"  複勝: ROI {axis_stats.get('axis_fukusho_roi', 0):.0f}% "
            f"(回収 {axis_stats.get('axis_fukusho_return', 0):,}円 / "
            f"{axis_stats.get('axis_fukusho_investment', 0):,}円)"
        )

    # By venue stats
    by_venue = by_venue or {}
    if by_venue:
        lines.append("")
        lines.append("**【競馬場別】**")
        for venue, data in sorted(by_venue.items(), key=lambda x: -x[1].get("races", 0)):
            r = data.get("races", 0)
            lines.append(
                f"  {venue} {r}R: "
                f"単勝{data.get('top1_rate', 0):.0f}% ROI {data.get('tansho_roi', 0):.0f}% / "
                f"複勝{data.get('top3_rate', 0):.0f}% ROI {data.get('fukusho_roi', 0):.0f}%"
            )

    # Failure analysis section
    failure_analysis = failure_analysis or {}
    if failure_analysis and failure_analysis.get("total_misses", 0) > 0:
        lines.append("")
        lines.append("**【的外し分析】**")
        lines.append(
            f"  大穴: {failure_analysis.get('upset', 0)}件 / "
            f"惜しい: {failure_analysis.get('close_call', 0)}件 / "
            f"見落とし: {failure_analysis.get('blind_spot', 0)}件"
        )
        for bs in failure_analysis.get("blind_spot_details", []):
            lines.append(
                f"    → {bs['winner_name']}({bs['winner_ninki']}人気) "
                f"予測{bs['predicted_rank']}位 勝率{bs['win_prob']:.1%}"
            )
        for w in failure_analysis.get("weaknesses", []):
            lines.append(
                f"  ⚠ {w['category']}:{w['value']} "
                f"Top3率{w['cover_rate']:.0%} (平均{w['avg_cover_rate']:.0%})"
            )

    # Add guide if date select menu is available
    if daily_data:
        lines.append("")
        lines.append("▼ 日付を選択して詳細を表示")

    message = "\n".join(lines)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    # Request body
    payload: dict[str, Any] = {"content": message}

    # Add select menu if daily data exists
    if daily_data and len(daily_data) > 0:
        options = []
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            n = data.get("analyzed_races", 0)
            # Use axis stats for description
            axis_rate = data.get("axis_stats", {}).get("axis_fukusho_rate", 0)
            options.append(
                {
                    "label": f"{date_str} ({n}R)",
                    "value": date_str,
                    "description": f"軸馬複勝率: {axis_rate:.0f}%",
                }
            )

        if options:
            payload["components"] = [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 3,  # Select Menu
                            "custom_id": "weekend_result_select",
                            "placeholder": "日付を選択して詳細を表示...",
                            "options": options,
                        }
                    ],
                }
            ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Weekend Discord notification sent")
        else:
            logger.warning(
                f"Weekend Discord notification failed: {response.status_code} - {response.text}"
            )
    except Exception as e:
        logger.error(f"Weekend Discord notification error: {e}")
