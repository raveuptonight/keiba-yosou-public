"""
Discord Bot Automatic Prediction Scheduler

Automatically executes final predictions 30 minutes before race (after horse weight announcement)
and notifies via Discord.
"""

import logging
import os
from datetime import date, datetime, time, timedelta, timezone

# Japan Standard Time
JST = timezone(timedelta(hours=9))
from typing import Any

import requests

import discord
from discord.ext import commands, tasks
from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
    SCHEDULER_CHECK_INTERVAL_MINUTES,
    SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE,
    SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES,
)
from src.models.ev_recommender import EVRecommender

# Logger setup
logger = logging.getLogger(__name__)


class PredictionScheduler(commands.Cog):
    """
    Automatic Prediction Scheduler

    Executes final predictions 30 minutes before race (after horse weight announcement)
    and notifies via Discord.
    """

    def __init__(self, bot: commands.Bot, notification_channel_id: int | None = None):
        """
        Args:
            bot: Discord bot instance
            notification_channel_id: Notification channel ID (can be obtained from environment variable)
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        self.notification_channel_id = notification_channel_id or int(
            os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", "0")
        )

        # Executed race IDs (to prevent duplicate predictions)
        self.predicted_race_ids_final: set = set()  # Post-weight predictions completed

        logger.info(f"PredictionScheduler initialized: channel_id={self.notification_channel_id}")

    async def _handle_weekend_result_select(self, interaction: discord.Interaction):
        """Handle weekend result date selection interaction."""
        if interaction.data is None:
            return
        data = interaction.data
        values = data.get("values", []) if hasattr(data, "get") else []  # type: ignore[union-attr]
        if not values:
            return

        selected_date = values[0] if isinstance(values, list) else None
        if selected_date is None:
            return
        logger.info(f"Weekend result detail request: date={selected_date}, user={interaction.user}")

        await interaction.response.defer(ephemeral=True)

        try:
            # Get data for selected date
            from datetime import datetime

            from src.scheduler.result_collector import ResultCollector

            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
            collector = ResultCollector()
            analysis = collector.collect_and_analyze(target_date)

            if analysis["status"] != "success":
                await interaction.followup.send(
                    f"❌ {selected_date}のデータが見つかりません", ephemeral=True
                )
                return

            acc = analysis["accuracy"]

            # Create detail message
            lines = [
                f"📊 **{selected_date} 予想精度レポート**",
                f"分析レース数: {acc['analyzed_races']}R",
                "",
                "**【順位別成績】**",
            ]

            # By ranking
            for rank in [1, 2, 3]:
                if rank in acc.get("ranking_stats", {}):
                    r = acc["ranking_stats"][rank]
                    lines.append(
                        f"  {rank}位予想: 1着:{r['1着']}回 2着:{r['2着']}回 3着:{r['3着']}回 "
                        f"(複勝率:{r['複勝率']:.1f}%)"
                    )

            # By popularity
            if acc.get("popularity_stats"):
                lines.append("")
                lines.append("**【人気別成績】** (1位予想馬)")
                for pop_cat in ["1-3番人気", "4-6番人気", "7-9番人気", "10番人気以下"]:
                    if pop_cat in acc["popularity_stats"]:
                        p = acc["popularity_stats"][pop_cat]
                        lines.append(
                            f"  {pop_cat}: {p['対象']}R → 複勝圏:{p['複勝圏']}回 ({p['複勝率']:.0f}%)"
                        )

            # By confidence
            if acc.get("confidence_stats"):
                lines.append("")
                lines.append("**【信頼度別成績】**")
                for conf_cat in ["高(80%以上)", "中(60-80%)", "低(60%未満)"]:
                    if conf_cat in acc["confidence_stats"]:
                        c = acc["confidence_stats"][conf_cat]
                        lines.append(
                            f"  {conf_cat}: {c['対象']}R → 複勝圏:{c['複勝圏']}回 ({c['複勝率']:.0f}%)"
                        )

            # By track type
            if acc.get("by_track"):
                lines.append("")
                lines.append("**【コース別成績】**")
                for track in ["芝", "ダ"]:
                    if track in acc["by_track"]:
                        t = acc["by_track"][track]
                        track_name = "芝" if track == "芝" else "ダート"
                        lines.append(
                            f"  {track_name}: {t['races']}R → 複勝率:{t['top3_rate']:.0f}%"
                        )

            # Return rates
            rr = acc.get("return_rates", {})
            if rr.get("tansho_investment", 0) > 0:
                lines.append("")
                lines.append("**【回収率】** (1位予想馬に各100円)")
                lines.append(
                    f"  単勝: {rr['tansho_return']:,}円 / {rr['tansho_investment']:,}円 = {rr['tansho_roi']:.1f}%"
                )
                lines.append(
                    f"  複勝: {rr['fukusho_return']:,}円 / {rr['fukusho_investment']:,}円 = {rr['fukusho_roi']:.1f}%"
                )

            message = "\n".join(lines)
            await interaction.followup.send(message, ephemeral=True)
            logger.info(f"Weekend result detail sent: date={selected_date}")

        except Exception as e:
            logger.exception(f"Weekend result detail error: date={selected_date}, error={e}")
            await interaction.followup.send(f"❌ エラー: {str(e)}", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Interaction event handler.

        Handles Select menu interactions for weekend results.
        """
        # Only process Select menu interactions
        if interaction.type != discord.InteractionType.component:
            return

        if interaction.data is None:
            return
        custom_id = interaction.data.get("custom_id") if hasattr(interaction.data, "get") else None  # type: ignore[union-attr]

        # Weekend result date selection
        if custom_id == "weekend_result_select":
            await self._handle_weekend_result_select(interaction)
            return

    async def cog_load(self):
        """Start task when Cog loads."""
        logger.info("Automatic prediction scheduler started")
        self.hourly_check_task.start()

    async def cog_unload(self):
        """Stop task when Cog unloads."""
        logger.info("Automatic prediction scheduler stopped")
        self.hourly_check_task.cancel()

    def get_notification_channel(self) -> discord.TextChannel | None:
        """Get notification channel."""
        if not self.notification_channel_id:
            logger.warning("Notification channel ID is not set")
            return None

        channel = self.bot.get_channel(self.notification_channel_id)
        if not channel:
            logger.error(f"Notification channel not found: {self.notification_channel_id}")
            return None

        if not isinstance(channel, discord.TextChannel):
            logger.error(f"Channel is not a TextChannel: {type(channel)}")
            return None

        return channel

    @tasks.loop(minutes=SCHEDULER_CHECK_INTERVAL_MINUTES)
    async def hourly_check_task(self):
        """
        Periodically check race start times.

        Executes re-prediction 30 minutes before race (after horse weight announcement).
        Horse weights are typically announced about 75 minutes before start,
        so re-prediction is done at 30 minutes before.
        Races with non-matching dates are excluded.
        """
        now = datetime.now(JST)
        logger.debug(f"Race time check: {now}")

        try:
            # Get today's race list (with strict date matching)
            today = datetime.now(JST).date()
            races = await self._fetch_races_for_date(today, strict_date_match=True)

            if not races:
                return

            for race in races:
                race_id = race.get("race_id")
                race_time_str = race.get("race_time")  # "15:25" format

                if not race_id or not race_time_str:
                    continue

                # Parse race time (supports "HH:MM" or "HHMM" format)
                try:
                    if ":" in race_time_str:
                        race_hour, race_minute = map(int, race_time_str.split(":"))
                    elif len(race_time_str) == 4:
                        race_hour = int(race_time_str[:2])
                        race_minute = int(race_time_str[2:])
                    else:
                        raise ValueError(f"Unknown time format: {race_time_str}")
                    race_datetime = datetime.combine(
                        today, time(hour=race_hour, minute=race_minute), tzinfo=JST
                    )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Race time parse failed: {race_time_str} ({e})")
                    continue

                # N minutes before race (with M minutes tolerance)
                minutes_before = SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE
                tolerance_seconds = SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES * 60

                target_time = race_datetime - timedelta(minutes=minutes_before)
                time_diff = abs((now - target_time).total_seconds())

                # Within tolerance and not yet executed
                if time_diff <= tolerance_seconds and race_id not in self.predicted_race_ids_final:
                    venue = race.get("venue", "?")
                    race_num = race.get("race_number", "?")
                    logger.info(
                        f"Executing post-weight prediction: race_id={race_id}, venue={venue}, race_num={race_num}"
                    )

                    # Execute prediction (notification handled in _execute_prediction)
                    success = await self._execute_prediction(race_id, is_final=True)

                    if success:
                        self.predicted_race_ids_final.add(race_id)

        except Exception as e:
            logger.exception(f"Race time check task error: {e}")

    async def _fetch_races_for_date(
        self, target_date: date, strict_date_match: bool = True
    ) -> list[dict[str, Any]]:
        """
        Fetch race list for specified date.

        Args:
            target_date: Target date
            strict_date_match: If True, exclude races with non-matching dates

        Returns:
            List of races
        """
        try:
            response = requests.get(
                f"{self.api_base_url}/api/races/date/{target_date.isoformat()}", timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                races = data.get("races", [])
                logger.info(f"Race list fetch successful: {target_date} -> {len(races)} races")

                # Strict date matching
                if strict_date_match and races:
                    target_date_str = target_date.isoformat()  # "2026-01-10"
                    filtered_races = []
                    for race in races:
                        race_date = race.get("race_date", "")
                        if race_date == target_date_str:
                            filtered_races.append(race)
                        else:
                            logger.warning(
                                f"Excluding race with date mismatch: "
                                f"expected={target_date_str}, actual={race_date}, "
                                f"race_id={race.get('race_id')}"
                            )

                    if len(filtered_races) != len(races):
                        logger.info(
                            f"Date filter applied: {len(races)} -> {len(filtered_races)} races"
                        )
                    return filtered_races

                return races
            else:
                logger.warning(f"Race list fetch failed: status={response.status_code}")
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Race list fetch error: {e}")
            return []

    async def _execute_prediction(
        self, race_id: str, is_final: bool = False, send_notification: bool = True
    ) -> dict | bool | None:
        """
        Execute prediction.

        Args:
            race_id: Race ID
            is_final: Whether this is final prediction (after horse weight)
            send_notification: Whether to send notification (if False, returns prediction result)

        Returns:
            If send_notification=True: True on success, False on failure
            If send_notification=False: Prediction result dict on success, None on failure
        """
        try:
            logger.info(f"Executing prediction: race_id={race_id}, is_final={is_final}")

            # Execute prediction via FastAPI
            response = requests.post(
                f"{self.api_base_url}/api/v1/predictions/generate",
                json={"race_id": race_id, "is_final": is_final},  # Final prediction flag
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                prediction = response.json()
                pred_id = prediction.get("prediction_id")
                logger.info(f"Prediction successful: prediction_id={pred_id}")

                # Return prediction result if notification disabled
                if not send_notification:
                    return prediction

                # Send to notification channel
                channel = self.get_notification_channel()
                if channel:
                    if is_final:
                        # Final prediction: simple expected value based format
                        result = prediction.get("prediction_result", {})
                        ranked = result.get("ranked_horses", [])

                        if ranked:
                            venue = prediction.get("venue", "Unknown")
                            race_number = prediction.get("race_number", "?")
                            race_time = prediction.get("race_time", "")
                            race_name = prediction.get("race_name", "")

                            # Format race number
                            try:
                                race_num_int = int(race_number.replace("R", ""))
                                race_num_formatted = f"{race_num_int}R"
                            except (ValueError, TypeError):
                                race_num_formatted = (
                                    f"{race_number}R"
                                    if not str(race_number).endswith("R")
                                    else race_number
                                )

                            # Format time
                            if race_time and len(race_time) >= 4 and ":" not in race_time:
                                time_formatted = f"{race_time[:2]}:{race_time[2:4]}"
                            else:
                                time_formatted = race_time

                            # === Get expected value based betting recommendations ===
                            race_code = prediction.get("race_code") or race_id
                            ev_recommender = EVRecommender()
                            ev_recs = ev_recommender.get_recommendations(
                                race_code=race_code,
                                ranked_horses=ranked,
                                use_realtime_odds=True,
                            )

                            # Collect recommended horses with EV >= 1.5 (max 3 combined win/place)
                            win_recs = ev_recs.get("win_recommendations", [])
                            place_recs = ev_recs.get("place_recommendations", [])

                            # === Axis horse recommendation (for wide/exacta bets) ===
                            # Axis horse = horse with highest place probability (most likely to finish top 3)
                            axis_horse = (
                                max(ranked, key=lambda h: h.get("place_probability", 0))
                                if ranked
                                else None
                            )

                            # Build message with separate win/place sections
                            lines = [
                                f"🔥 **{venue} {race_num_formatted} {race_name}**",
                                f"{time_formatted}発走",
                                "",
                            ]

                            # Build CI lookup from ranked horses
                            ci_lookup = {}
                            for h in ranked:
                                ci_lower = h.get("win_ci_lower")
                                ci_upper = h.get("win_ci_upper")
                                if ci_lower is not None and ci_upper is not None:
                                    ci_lookup[h["horse_number"]] = (ci_lower, ci_upper)

                            # Win bet section
                            lines.append("🎯 **推奨買い目: 単勝** (期待値ベース)")
                            if win_recs:
                                for rec in win_recs[:3]:
                                    num = rec["horse_number"]
                                    name = rec["horse_name"][:8]
                                    odds = rec.get("odds", 0)
                                    prob = rec.get("win_probability", 0)
                                    ci = ci_lookup.get(num)
                                    if ci:
                                        lines.append(
                                            f"  #{num} {name}  {odds:.1f}倍 (勝率{prob:.1%} [{ci[0]:.1%}-{ci[1]:.1%}])"
                                        )
                                    else:
                                        lines.append(
                                            f"  #{num} {name}  {odds:.1f}倍 (勝率{prob:.1%})"
                                        )
                            else:
                                lines.append("  推奨なし")

                            lines.append("")

                            # Place bet section
                            lines.append("🎯 **推奨買い目: 複勝** (期待値ベース)")
                            if place_recs:
                                for rec in place_recs[:3]:
                                    num = rec["horse_number"]
                                    name = rec["horse_name"][:8]
                                    odds = rec.get("odds", 0)
                                    prob = rec.get("place_probability", 0)
                                    lines.append(
                                        f"  #{num} {name}  {odds:.1f}倍 (複勝率{prob:.1%})"
                                    )
                            else:
                                lines.append("  推奨なし")

                            lines.append("")

                            # Axis horse recommendation
                            if axis_horse:
                                lines.append("📌 **軸馬** (ワイド・馬連)")
                                ah_num = axis_horse.get("horse_number", "?")
                                ah_name = axis_horse.get("horse_name", "?")[:8]
                                ah_place = axis_horse.get("place_probability", 0)
                                lines.append(f"  #{ah_num} {ah_name} (複勝率{ah_place:.1%})")

                            message = "\n".join(lines)
                            await channel.send(message)
                            logger.info(
                                f"Final prediction sent: race_id={race_id}, "
                                f"win_recs={len(win_recs)}, place_recs={len(place_recs)}"
                            )
                        else:
                            # Empty prediction result
                            logger.warning(f"Final prediction result empty: race_id={race_id}")
                            await channel.send(
                                f"🔥 **{prediction.get('venue', '?')} {prediction.get('race_number', '?')}R 確定予想完了**"
                            )
                    else:
                        # Pre-race prediction deprecated - only final predictions notified
                        logger.debug(f"Pre-race prediction skipped (deprecated): race_id={race_id}")

                return True
            else:
                logger.error(
                    f"Prediction API failed: status={response.status_code}, race_id={race_id}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.error(f"Prediction API timeout: race_id={race_id}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Prediction API error: race_id={race_id}, error={e}")
            return False
        except Exception as e:
            logger.exception(f"Prediction execution error: race_id={race_id}, error={e}")
            return False

    @hourly_check_task.before_loop
    async def before_hourly_task(self):
        """Wait for bot to be ready before starting race check task."""
        await self.bot.wait_until_ready()
        logger.info("Race time check task ready")

    @commands.command(name="scheduler-status")
    @commands.has_permissions(administrator=True)
    async def scheduler_status(self, ctx: commands.Context):
        """
        Check scheduler status (admin only).

        Args:
            ctx: Command context
        """
        hourly_running = self.hourly_check_task.is_running()

        lines = [
            "⚙️ 自動予想スケジューラー状態",
            "",
            f"レースチェックタスク: {'🟢 実行中' if hourly_running else '🔴 停止'}",
            f"確定予想完了: {len(self.predicted_race_ids_final)}レース",
            "",
            f"通知チャンネルID: {self.notification_channel_id}",
        ]

        await ctx.send("\n".join(lines))

    @commands.command(name="scheduler-reset")
    @commands.has_permissions(administrator=True)
    async def scheduler_reset(self, ctx: commands.Context):
        """
        Reset scheduler (admin only).

        Args:
            ctx: Command context
        """
        self.predicted_race_ids_final.clear()

        logger.info("Scheduler reset complete")
        await ctx.send("✅ スケジューラーをリセットしました。")


async def setup(bot: commands.Bot):
    """
    Register scheduler to bot.

    Args:
        bot: Discord bot instance

    Raises:
        Exception: If Cog addition fails
    """
    try:
        await bot.add_cog(PredictionScheduler(bot))
        logger.info("PredictionScheduler Cog registered")
    except Exception as e:
        logger.error(f"PredictionScheduler Cog registration failed: {e}")
        raise
