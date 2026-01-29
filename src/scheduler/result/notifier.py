"""
Discord Notification Module

Functions for sending prediction result notifications to Discord.
"""

import logging
import os
from datetime import date

import requests

logger = logging.getLogger(__name__)


def send_discord_notification(analysis: dict):
    """
    Send Discord notification (EV recommendation and axis horse format).

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
    by_track = acc.get("by_track", {})

    # Basic message (EV recommendation and axis horse focused)
    lines = [
        f"📊 **{date_str} 予想結果レポート**",
        f"分析レース数: {n}R",
        "",
    ]

    # EV recommendation stats
    ev_rec_races = ev_stats.get("ev_rec_races", 0)
    ev_rec_count = ev_stats.get("ev_rec_count", 0)
    if ev_rec_count > 0:
        lines.append("**【単複推奨】** (EV >= 1.5)")
        lines.append(f"  推奨レース: {ev_rec_races}R / 推奨頭数: {ev_rec_count}")
        lines.append(
            f"  単勝: {ev_stats.get('ev_rec_tansho_hit', 0)}的中 ({ev_stats.get('ev_tansho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  複勝: {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  単勝回収: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**"
        )
        lines.append(
            f"  複勝回収: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**"
        )
    else:
        lines.append("**【単複推奨】**")
        lines.append("  EV推奨なし")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get("axis_races", 0)
    if axis_races > 0:
        lines.append("**【軸馬成績】** (複勝率最高馬)")
        lines.append(f"  レース数: {axis_races}R")
        lines.append(
            f"  単勝: {axis_stats.get('axis_tansho_hit', 0)}的中 ({axis_stats.get('axis_tansho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  複勝: {axis_stats.get('axis_fukusho_hit', 0)}的中 (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)"
        )
        lines.append(
            f"  複勝回収: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%"
        )

    # Turf/Dirt (axis horse place rate)
    if by_track:
        lines.append("")
        lines.append("**【芝・ダート別】** (軸馬複勝率)")
        for track in ["芝", "ダ"]:
            if track in by_track:
                t = by_track[track]
                lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

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
    ranking_stats: dict = None,
    return_rates: dict = None,
    popularity_stats: dict = None,
    confidence_stats: dict = None,
    by_track: dict = None,
    daily_data: dict = None,
    cumulative: dict | None = None,
    ev_stats: dict = None,
    axis_stats: dict = None,
):
    """
    Send weekend total Discord notification (EV recommendation and axis horse format).

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

    # EV recommendation stats
    ev_rec_count = ev_stats.get("ev_rec_count", 0)
    if ev_rec_count > 0:
        lines.append("**【単複推奨】** (EV >= 1.5)")
        lines.append(f"  推奨レース: {ev_stats.get('ev_rec_races', 0)}R / 推奨頭数: {ev_rec_count}")
        lines.append(
            f"  単勝: {ev_stats.get('ev_rec_tansho_hit', 0)}的中 ({ev_stats.get('ev_tansho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  複勝: {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  単勝回収: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**"
        )
        lines.append(
            f"  複勝回収: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**"
        )
    else:
        lines.append("**【単複推奨】**")
        lines.append("  EV推奨なし")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get("axis_races", 0)
    if axis_races > 0:
        lines.append("**【軸馬成績】** (複勝率最高馬)")
        lines.append(f"  レース数: {axis_races}R")
        lines.append(
            f"  単勝: {axis_stats.get('axis_tansho_hit', 0)}的中 ({axis_stats.get('axis_tansho_rate', 0):.1f}%)"
        )
        lines.append(
            f"  複勝: {axis_stats.get('axis_fukusho_hit', 0)}的中 (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)"
        )
        lines.append(
            f"  複勝回収: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%"
        )

    # Turf/Dirt
    if by_track:
        lines.append("")
        lines.append("**【芝・ダート別】** (軸馬複勝率)")
        for track in ["芝", "ダ"]:
            if track in by_track:
                t = by_track[track]
                lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

    # Add guide if date select menu is available
    if daily_data:
        lines.append("")
        lines.append("▼ 日付を選択して詳細を表示")

    message = "\n".join(lines)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    # Request body
    payload = {"content": message}

    # Add select menu if daily data exists
    if daily_data and len(daily_data) > 0:
        options = []
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            n = data.get("analyzed_races", 0)
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
