"""
Discord Notification Module

Functions for sending prediction result notifications to Discord.
"""

import logging
import os
from datetime import date
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


def send_discord_notification(analysis: Dict):
    """
    Send Discord notification (EV recommendation and axis horse format).

    Args:
        analysis: Analysis result dictionary
    """
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

    if not bot_token or not channel_id:
        logger.warning("Discord notification settings not configured")
        return

    acc = analysis.get('accuracy', {})
    if 'error' in acc:
        return

    date_str = acc.get('date', 'Unknown')
    n = acc.get('analyzed_races', 0)
    ev_stats = acc.get('ev_stats', {})
    axis_stats = acc.get('axis_stats', {})
    by_track = acc.get('by_track', {})

    # Basic message (EV recommendation and axis horse focused)
    lines = [
        f"📊 **{date_str} Prediction Result Report**",
        f"Analyzed races: {n}R",
        "",
    ]

    # EV recommendation stats
    ev_rec_races = ev_stats.get('ev_rec_races', 0)
    ev_rec_count = ev_stats.get('ev_rec_count', 0)
    if ev_rec_count > 0:
        lines.append("**【Win/Place Recommendation】** (EV >= 1.5)")
        lines.append(f"  Recommended races: {ev_rec_races}R / Horses: {ev_rec_count}")
        lines.append(f"  Win: {ev_stats.get('ev_rec_tansho_hit', 0)} hits ({ev_stats.get('ev_tansho_rate', 0):.1f}%)")
        lines.append(f"  Place: {ev_stats.get('ev_rec_fukusho_hit', 0)} hits ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)")
        lines.append(f"  Win ROI: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**")
        lines.append(f"  Place ROI: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**")
    else:
        lines.append("**【Win/Place Recommendation】**")
        lines.append("  No EV recommendations")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get('axis_races', 0)
    if axis_races > 0:
        lines.append("**【Axis Horse Stats】** (Highest place probability)")
        lines.append(f"  Races: {axis_races}R")
        lines.append(f"  Win: {axis_stats.get('axis_tansho_hit', 0)} hits ({axis_stats.get('axis_tansho_rate', 0):.1f}%)")
        lines.append(f"  Place: {axis_stats.get('axis_fukusho_hit', 0)} hits (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)")
        lines.append(f"  Place ROI: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%")

    # Turf/Dirt (axis horse place rate)
    if by_track:
        lines.append("")
        lines.append("**【Turf/Dirt】** (Axis horse place rate)")
        for track in ['芝', 'ダ']:
            if track in by_track:
                t = by_track[track]
                lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

    message = "\n".join(lines)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }

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
    stats: Dict,
    ranking_stats: Dict = None,
    return_rates: Dict = None,
    popularity_stats: Dict = None,
    confidence_stats: Dict = None,
    by_track: Dict = None,
    daily_data: Dict = None,
    cumulative: Optional[Dict] = None,
    ev_stats: Dict = None,
    axis_stats: Dict = None,
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
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

    if not bot_token or not channel_id:
        logger.warning("Discord notification settings not configured")
        return

    ev_stats = ev_stats or {}
    axis_stats = axis_stats or {}

    lines = [
        f"📊 **Weekend Prediction Result Report**",
        f"Period: {saturday} - {sunday}",
        f"Analyzed races: {stats.get('analyzed_races', 0)}R",
        "",
    ]

    # EV recommendation stats
    ev_rec_count = ev_stats.get('ev_rec_count', 0)
    if ev_rec_count > 0:
        lines.append("**【Win/Place Recommendation】** (EV >= 1.5)")
        lines.append(f"  Recommended races: {ev_stats.get('ev_rec_races', 0)}R / Horses: {ev_rec_count}")
        lines.append(f"  Win: {ev_stats.get('ev_rec_tansho_hit', 0)} hits ({ev_stats.get('ev_tansho_rate', 0):.1f}%)")
        lines.append(f"  Place: {ev_stats.get('ev_rec_fukusho_hit', 0)} hits ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)")
        lines.append(f"  Win ROI: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**")
        lines.append(f"  Place ROI: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**")
    else:
        lines.append("**【Win/Place Recommendation】**")
        lines.append("  No EV recommendations")

    # Axis horse stats
    lines.append("")
    axis_races = axis_stats.get('axis_races', 0)
    if axis_races > 0:
        lines.append("**【Axis Horse Stats】** (Highest place probability)")
        lines.append(f"  Races: {axis_races}R")
        lines.append(f"  Win: {axis_stats.get('axis_tansho_hit', 0)} hits ({axis_stats.get('axis_tansho_rate', 0):.1f}%)")
        lines.append(f"  Place: {axis_stats.get('axis_fukusho_hit', 0)} hits (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)")
        lines.append(f"  Place ROI: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%")

    # Turf/Dirt
    if by_track:
        lines.append("")
        lines.append("**【Turf/Dirt】** (Axis horse place rate)")
        for track in ['芝', 'ダ']:
            if track in by_track:
                t = by_track[track]
                lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

    # Add guide if date select menu is available
    if daily_data:
        lines.append("")
        lines.append("▼ Select a date to view details")

    message = "\n".join(lines)

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }

    # Request body
    payload = {"content": message}

    # Add select menu if daily data exists
    if daily_data and len(daily_data) > 0:
        options = []
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            n = data.get('analyzed_races', 0)
            axis_rate = data.get('axis_stats', {}).get('axis_fukusho_rate', 0)
            options.append({
                "label": f"{date_str} ({n}R)",
                "value": date_str,
                "description": f"Axis place rate: {axis_rate:.0f}%"
            })

        if options:
            payload["components"] = [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 3,  # Select Menu
                            "custom_id": "weekend_result_select",
                            "placeholder": "Select a date to view details...",
                            "options": options
                        }
                    ]
                }
            ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Weekend Discord notification sent")
        else:
            logger.warning(f"Weekend Discord notification failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Weekend Discord notification error: {e}")
