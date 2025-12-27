"""
Discord Bot自動予想スケジューラー

開催日9時と馬体重発表後に自動予想を実行
"""

import os
import logging
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
import asyncio
import requests
from discord.ext import tasks, commands
import discord

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
    SCHEDULER_MORNING_PREDICTION_HOUR,
    SCHEDULER_MORNING_PREDICTION_MINUTE,
    SCHEDULER_CHECK_INTERVAL_MINUTES,
    SCHEDULER_FINAL_PREDICTION_HOURS_BEFORE,
    SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES,
)
from src.discord.formatters import format_prediction_notification

# ロガー設定
logger = logging.getLogger(__name__)


class PredictionScheduler(commands.Cog):
    """
    自動予想スケジューラー

    1. 毎日9時: 当日開催レースの初回予想
    2. レース1時間前: 馬体重発表後の再予想
    """

    def __init__(self, bot: commands.Bot, notification_channel_id: Optional[int] = None):
        """
        Args:
            bot: Discordボットインスタンス
            notification_channel_id: 通知先チャンネルID（環境変数から取得可能）
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        self.notification_channel_id = notification_channel_id or int(
            os.getenv("DISCORD_CHANNEL_ID", "0")
        )

        # 実行済みレースID記録（重複予想防止）
        self.predicted_race_ids_morning: set = set()  # 朝9時予想済み
        self.predicted_race_ids_final: set = set()    # 馬体重後予想済み

        logger.info(f"PredictionScheduler初期化: channel_id={self.notification_channel_id}")

    async def cog_load(self):
        """Cog読み込み時にタスク開始"""
        logger.info("自動予想スケジューラー開始")
        self.morning_prediction_task.start()
        self.hourly_check_task.start()

    async def cog_unload(self):
        """Cog削除時にタスク停止"""
        logger.info("自動予想スケジューラー停止")
        self.morning_prediction_task.cancel()
        self.hourly_check_task.cancel()

    def get_notification_channel(self) -> Optional[discord.TextChannel]:
        """通知先チャンネルを取得"""
        if not self.notification_channel_id:
            logger.warning("通知先チャンネルIDが設定されていません")
            return None

        channel = self.bot.get_channel(self.notification_channel_id)
        if not channel:
            logger.error(f"通知先チャンネルが見つかりません: {self.notification_channel_id}")
            return None

        return channel

    @tasks.loop(time=time(hour=SCHEDULER_MORNING_PREDICTION_HOUR, minute=SCHEDULER_MORNING_PREDICTION_MINUTE))
    async def morning_prediction_task(self):
        """
        毎朝9時に当日開催レースの予想を実行

        開催日の朝、全レースの初回予想を実行します。
        """
        logger.info("朝9時予想タスク実行")

        try:
            # 当日のレース一覧を取得
            today = date.today()
            races = await self._fetch_races_for_date(today)

            if not races:
                logger.info(f"本日({today})はレース開催なし")
                return

            logger.info(f"本日のレース数: {len(races)}")
            channel = self.get_notification_channel()

            if channel:
                await channel.send(f"🌅 おはようございます！本日は{len(races)}レースの予想を開始します。")

            # 各レースの予想を実行
            for race in races:
                race_id = race.get("race_id")

                # すでに予想済みならスキップ
                if race_id in self.predicted_race_ids_morning:
                    logger.debug(f"朝予想済みスキップ: {race_id}")
                    continue

                # 予想実行
                success = await self._execute_prediction(race_id, is_final=False)

                if success:
                    self.predicted_race_ids_morning.add(race_id)
                    # レート制限対策で少し待機
                    await asyncio.sleep(2)

            if channel:
                await channel.send("✅ 本日の初回予想が完了しました！")

        except Exception as e:
            logger.exception(f"朝9時予想タスクエラー: {e}")

    @tasks.loop(minutes=SCHEDULER_CHECK_INTERVAL_MINUTES)
    async def hourly_check_task(self):
        """
        定期的にレース開始時刻をチェック

        レース1時間前（馬体重発表後）に再予想を実行します。
        通常、馬体重は発走約75分前に発表されるため、1時間前に再予想。
        """
        now = datetime.now()
        logger.debug(f"レース時刻チェック: {now}")

        try:
            # 当日のレース一覧を取得
            today = date.today()
            races = await self._fetch_races_for_date(today)

            if not races:
                return

            for race in races:
                race_id = race.get("race_id")
                race_time_str = race.get("race_time")  # "15:25"形式

                if not race_time_str:
                    continue

                # レース時刻をパース
                try:
                    race_hour, race_minute = map(int, race_time_str.split(":"))
                    race_datetime = datetime.combine(today, time(hour=race_hour, minute=race_minute))
                except ValueError:
                    logger.warning(f"レース時刻パース失敗: {race_time_str}")
                    continue

                # レースN時間前（±M分の余裕）
                hours_before = SCHEDULER_FINAL_PREDICTION_HOURS_BEFORE
                tolerance_seconds = SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES * 60

                target_time = race_datetime - timedelta(hours=hours_before)
                time_diff = abs((now - target_time).total_seconds())

                # 指定時刻の許容範囲内 かつ 未実行
                if time_diff <= tolerance_seconds and race_id not in self.predicted_race_ids_final:
                    logger.info(f"馬体重発表後の再予想実行: race_id={race_id}, race_time={race_time_str}")

                    channel = self.get_notification_channel()
                    if channel:
                        race_name = race.get("race_name", "不明")
                        await channel.send(
                            f"🐴 馬体重発表！{race_name}の最終予想を実行します。"
                        )

                    # 再予想実行
                    success = await self._execute_prediction(race_id, is_final=True)

                    if success:
                        self.predicted_race_ids_final.add(race_id)

        except Exception as e:
            logger.exception(f"レース時刻チェックタスクエラー: {e}")

    async def _fetch_races_for_date(self, target_date: date) -> List[Dict[str, Any]]:
        """
        指定日のレース一覧を取得

        Args:
            target_date: 対象日

        Returns:
            レースリスト
        """
        try:
            # TODO: APIエンドポイント実装後に修正
            # response = requests.get(
            #     f"{self.api_base_url}/api/races",
            #     params={"date": target_date.isoformat()},
            #     timeout=10
            # )
            #
            # if response.status_code == 200:
            #     return response.json().get("races", [])

            # 暫定: モック（開発中）
            logger.warning("レース一覧APIエンドポイント未実装")
            return []

        except requests.exceptions.RequestException as e:
            logger.error(f"レース一覧取得エラー: {e}")
            return []

    async def _execute_prediction(self, race_id: str, is_final: bool = False) -> bool:
        """
        予想を実行

        Args:
            race_id: レースID
            is_final: 最終予想（馬体重後）かどうか

        Returns:
            成功したらTrue
        """
        try:
            logger.info(f"予想実行: race_id={race_id}, is_final={is_final}")

            # FastAPI経由で予想実行
            response = requests.post(
                f"{self.api_base_url}/api/predictions/",
                json={
                    "race_id": race_id,
                    "temperature": 0.3,
                    "phase": "all",
                    "is_final": is_final  # 最終予想フラグ
                },
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 201:
                prediction = response.json()
                logger.info(f"予想成功: prediction_id={prediction.get('id')}")

                # 通知チャンネルに送信
                channel = self.get_notification_channel()
                if channel:
                    message = format_prediction_notification(
                        race_name=prediction.get("race_name", "不明"),
                        race_date=date.fromisoformat(prediction.get("race_date")),
                        venue=prediction.get("venue", "不明"),
                        race_time=prediction.get("race_time", "不明"),
                        race_number=prediction.get("race_number", "不明"),
                        prediction_result=prediction.get("prediction_result", {}),
                        total_investment=prediction.get("total_investment", 0),
                        expected_return=prediction.get("expected_return", 0),
                        expected_roi=prediction.get("expected_roi", 0.0) * 100,
                        prediction_url=f"{self.api_base_url}/predictions/{prediction.get('id')}",
                    )

                    # 最終予想の場合は強調
                    if is_final:
                        await channel.send("🔥 **【最終予想】馬体重反映済み**")

                    await channel.send(message)

                return True
            else:
                logger.error(f"予想API失敗: status={response.status_code}, race_id={race_id}")
                return False

        except requests.exceptions.Timeout:
            logger.error(f"予想APIタイムアウト: race_id={race_id}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"予想APIエラー: race_id={race_id}, error={e}")
            return False
        except Exception as e:
            logger.exception(f"予想実行エラー: race_id={race_id}, error={e}")
            return False

    @morning_prediction_task.before_loop
    async def before_morning_task(self):
        """朝9時タスク開始前にBot準備完了を待つ"""
        await self.bot.wait_until_ready()
        logger.info("朝9時予想タスク準備完了")

    @hourly_check_task.before_loop
    async def before_hourly_task(self):
        """レースチェックタスク開始前にBot準備完了を待つ"""
        await self.bot.wait_until_ready()
        logger.info("レース時刻チェックタスク準備完了")

    @commands.command(name="scheduler-status")
    @commands.has_permissions(administrator=True)
    async def scheduler_status(self, ctx: commands.Context):
        """
        スケジューラーステータス確認（管理者のみ）

        Args:
            ctx: コマンドコンテキスト
        """
        morning_running = self.morning_prediction_task.is_running()
        hourly_running = self.hourly_check_task.is_running()

        morning_next = self.morning_prediction_task.next_iteration
        morning_next_str = morning_next.strftime("%Y-%m-%d %H:%M:%S") if morning_next else "不明"

        lines = [
            "⚙️ 自動予想スケジューラーステータス",
            "",
            f"朝9時予想タスク: {'🟢 実行中' if morning_running else '🔴 停止中'}",
            f"次回実行: {morning_next_str}",
            f"本日予想済み: {len(self.predicted_race_ids_morning)}レース",
            "",
            f"レースチェックタスク: {'🟢 実行中' if hourly_running else '🔴 停止中'}",
            f"最終予想済み: {len(self.predicted_race_ids_final)}レース",
            "",
            f"通知チャンネルID: {self.notification_channel_id}",
        ]

        await ctx.send("\n".join(lines))

    @commands.command(name="scheduler-reset")
    @commands.has_permissions(administrator=True)
    async def scheduler_reset(self, ctx: commands.Context):
        """
        スケジューラーのリセット（管理者のみ）

        Args:
            ctx: コマンドコンテキスト
        """
        self.predicted_race_ids_morning.clear()
        self.predicted_race_ids_final.clear()

        logger.info("スケジューラーリセット完了")
        await ctx.send("✅ スケジューラーをリセットしました。")


async def setup(bot: commands.Bot):
    """
    スケジューラーをBotに登録

    Args:
        bot: Discordボットインスタンス

    Raises:
        Exception: Cog追加に失敗した場合
    """
    try:
        await bot.add_cog(PredictionScheduler(bot))
        logger.info("PredictionScheduler Cog登録完了")
    except Exception as e:
        logger.error(f"PredictionScheduler Cog登録失敗: {e}")
        raise
