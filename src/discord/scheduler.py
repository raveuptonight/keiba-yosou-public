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
from discord.ui import View, Select
import discord

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
    SCHEDULER_EVENING_PREDICTION_HOUR,
    SCHEDULER_EVENING_PREDICTION_MINUTE,
    SCHEDULER_CHECK_INTERVAL_MINUTES,
    SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE,
    SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES,
)
from src.discord.formatters import format_prediction_notification

# ロガー設定
logger = logging.getLogger(__name__)


class PredictionSummaryView(View):
    """予想完了後のレース選択ビュー"""

    def __init__(self, races: List[Dict], api_base_url: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.api_base_url = api_base_url
        self.races = races

        # 日付→競馬場→レース番号（降順）でソート
        sorted_races = sorted(
            races,
            key=lambda r: (
                r.get("race_date", ""),
                r.get("venue", ""),
                int(r.get("race_number", "0R").replace("R", "") or 0)
            ),
            reverse=True
        )

        options = []
        for race in sorted_races[:25]:
            race_date = race.get("race_date", "")
            venue = race.get("venue", "")
            race_num = race.get("race_number", "?R")
            race_name = race.get("race_name", "")[:20]
            race_id = race.get("race_id", "")
            grade = race.get("grade", "")
            grade_str = f" [{grade}]" if grade else ""

            label = f"{race_date} {venue} {race_num} {race_name}{grade_str}"[:100]
            description = f"{race.get('distance', '?')}m"[:100]

            options.append(discord.SelectOption(
                label=label,
                value=race_id,
                description=description
            ))

        if options:
            select = Select(
                placeholder="レースを選択して詳細を表示...",
                options=options,
                min_values=1,
                max_values=1
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """レースが選択されたときのコールバック"""
        race_id = interaction.data["values"][0]

        await interaction.response.defer(ephemeral=True)

        try:
            # 予想結果を取得
            response = requests.get(
                f"{self.api_base_url}/api/v1/predictions/race/{race_id}",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                predictions = response.json()
                if predictions:
                    # 最新の予想を取得
                    latest = predictions[0] if isinstance(predictions, list) else predictions

                    # 予想詳細を取得
                    pred_id = latest.get("prediction_id")
                    detail_response = requests.get(
                        f"{self.api_base_url}/api/v1/predictions/{pred_id}",
                        timeout=DISCORD_REQUEST_TIMEOUT,
                    )

                    if detail_response.status_code == 200:
                        data = detail_response.json()
                        result = data.get("prediction_result", {})
                        ranked = result.get("ranked_horses", [])

                        # Embed作成
                        embed = discord.Embed(
                            title=f"🏇 {data.get('race_name', '?')}",
                            description=f"{data.get('venue', '?')} {data.get('race_number', '?')}R | {data.get('race_date', '?')}",
                            color=discord.Color.blue()
                        )

                        # 上位10頭を表示
                        marks = ['◎', '○', '▲', '△', '△', '×', '×', '×', '☆', '☆']
                        lines = []
                        for h in ranked[:10]:
                            rank = h.get('rank', 0)
                            mark = marks[rank - 1] if rank <= len(marks) else '☆'
                            lines.append(
                                f"{mark} {rank}位 {h.get('horse_number', '?')}番 {h.get('horse_name', '?')[:8]} "
                                f"(単{h.get('win_probability', 0):.1%} 連{h.get('quinella_probability', 0):.1%} 複{h.get('place_probability', 0):.1%})"
                            )

                        embed.add_field(name="予想順位", value="\n".join(lines), inline=False)
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return

            await interaction.followup.send("予想データの取得に失敗しました", ephemeral=True)

        except Exception as e:
            logger.error(f"予想詳細取得エラー: {e}")
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)


class PredictionScheduler(commands.Cog):
    """
    自動予想スケジューラー

    1. 毎日21時: 翌日開催レースの初回予想
    2. レース1時間前: 馬体重発表後の再予想
    3. prediction_selectインタラクション処理
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
        self.predicted_race_ids_initial: set = set()  # 前日21時予想済み
        self.predicted_race_ids_final: set = set()    # 馬体重後予想済み

        logger.info(f"PredictionScheduler初期化: channel_id={self.notification_channel_id}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        インタラクションイベントハンドラ

        daily_scheduler.pyから送信されたSelectメニューのインタラクションを処理
        """
        # Selectメニューのインタラクションのみ処理
        if interaction.type != discord.InteractionType.component:
            return

        # prediction_selectのみ処理
        custom_id = interaction.data.get("custom_id")
        if custom_id != "prediction_select":
            return

        # 選択されたレースIDを取得
        values = interaction.data.get("values", [])
        if not values:
            return

        race_id = values[0]
        logger.info(f"予想詳細リクエスト: race_id={race_id}, user={interaction.user}")

        await interaction.response.defer(ephemeral=True)

        try:
            # 予想履歴を取得
            history_response = requests.get(
                f"{self.api_base_url}/api/v1/predictions/race/{race_id}",
                timeout=30,
            )

            if history_response.status_code != 200:
                await interaction.followup.send("予想データが見つかりません", ephemeral=True)
                return

            history = history_response.json()
            predictions = history.get("predictions", [])

            if not predictions:
                await interaction.followup.send("このレースの予想はまだありません", ephemeral=True)
                return

            # 最新の予想を取得
            latest = predictions[0]
            pred_id = latest.get("prediction_id")

            # 予想詳細を取得
            detail_response = requests.get(
                f"{self.api_base_url}/api/v1/predictions/{pred_id}",
                timeout=30,
            )

            if detail_response.status_code != 200:
                await interaction.followup.send("予想詳細の取得に失敗しました", ephemeral=True)
                return

            data = detail_response.json()
            result = data.get("prediction_result", {})
            ranked = result.get("ranked_horses", [])

            if not ranked:
                await interaction.followup.send("予想データがありません", ephemeral=True)
                return

            # 予想詳細フォーマット
            venue = data.get("venue", "?")
            race_num = data.get("race_number", "?")
            race_name = data.get("race_name", "")
            race_time = data.get("race_time", "")

            # 発走時刻フォーマット
            time_str = ""
            if race_time and len(race_time) >= 4:
                time_str = f"{race_time[:2]}:{race_time[2:4]}発走"

            # ヘッダー
            header = f"**{venue}{race_num}** {time_str} {race_name}"
            lines = [header, ""]

            # 全馬表示
            marks = ['◎', '○', '▲', '△', '△', '×', '×', '×'] + ['☆'] * 10
            for h in ranked:
                rank = h.get('rank', 0)
                num = h.get('horse_number', '?')
                name = h.get('horse_name', '?')[:10]
                win_prob = h.get('win_probability', 0)
                quinella_prob = h.get('quinella_probability', 0)
                place_prob = h.get('place_probability', 0)
                mark = marks[rank - 1] if rank <= len(marks) else '消'

                lines.append(
                    f"{mark} {rank}位 {num}番 {name} "
                    f"(単勝{win_prob:.1%} 連対{quinella_prob:.1%} 複勝{place_prob:.1%})"
                )

            # モデル情報
            model_info = result.get("model_info", "")
            confidence = result.get("prediction_confidence", 0)
            lines.append("")
            lines.append(f"_{model_info} / 信頼度 {confidence:.1%}_")

            message = "\n".join(lines)

            # 2000文字を超える場合は分割
            if len(message) > 2000:
                message = message[:1950] + "\n...(省略)"

            await interaction.followup.send(message, ephemeral=True)
            logger.info(f"予想詳細送信完了: race_id={race_id}")

        except requests.exceptions.Timeout:
            logger.error(f"予想詳細取得タイムアウト: race_id={race_id}")
            await interaction.followup.send("タイムアウト: APIの応答がありません", ephemeral=True)
        except Exception as e:
            logger.exception(f"予想詳細取得エラー: race_id={race_id}, error={e}")
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    async def cog_load(self):
        """Cog読み込み時にタスク開始"""
        logger.info("自動予想スケジューラー開始")
        self.evening_prediction_task.start()
        self.hourly_check_task.start()

    async def cog_unload(self):
        """Cog削除時にタスク停止"""
        logger.info("自動予想スケジューラー停止")
        self.evening_prediction_task.cancel()
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

    @tasks.loop(time=time(hour=SCHEDULER_EVENING_PREDICTION_HOUR, minute=SCHEDULER_EVENING_PREDICTION_MINUTE))
    async def evening_prediction_task(self):
        """
        毎日21時に翌日開催レースの予想を実行

        開催日前日の夜、全レースの初回予想を実行します。
        """
        logger.info("21時予想タスク実行")

        try:
            # 翌日のレース一覧を取得
            tomorrow = date.today() + timedelta(days=1)
            races = await self._fetch_races_for_date(tomorrow)

            if not races:
                logger.info(f"明日({tomorrow})はレース開催なし")
                return

            logger.info(f"明日のレース数: {len(races)}")
            channel = self.get_notification_channel()

            if channel:
                await channel.send(f"🌙 明日は{len(races)}レースの予想を開始します。")

            # 各レースの予想を実行
            for race in races:
                race_id = race.get("race_id")

                # すでに予想済みならスキップ
                if race_id in self.predicted_race_ids_initial:
                    logger.debug(f"前日予想済みスキップ: {race_id}")
                    continue

                # 予想実行
                success = await self._execute_prediction(race_id, is_final=False)

                if success:
                    self.predicted_race_ids_initial.add(race_id)
                    # レート制限対策で少し待機
                    await asyncio.sleep(2)

            if channel:
                # 予想完了メッセージとレース選択ドロップダウンを送信
                view = PredictionSummaryView(races, self.api_base_url, timeout=3600)
                await channel.send(
                    f"✅ 明日の初回予想が完了しました！（{len(races)}レース）\n"
                    "▼ レースを選択して詳細を確認できます",
                    view=view
                )

        except Exception as e:
            logger.exception(f"21時予想タスクエラー: {e}")

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

                # レースN分前（±M分の余裕）
                minutes_before = SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE
                tolerance_seconds = SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES * 60

                target_time = race_datetime - timedelta(minutes=minutes_before)
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
            response = requests.get(
                f"{self.api_base_url}/api/races/date/{target_date.isoformat()}",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                races = data.get("races", [])
                logger.info(f"レース一覧取得成功: {target_date} -> {len(races)}件")
                return races
            else:
                logger.warning(f"レース一覧取得失敗: status={response.status_code}")
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

    @evening_prediction_task.before_loop
    async def before_evening_task(self):
        """21時タスク開始前にBot準備完了を待つ"""
        await self.bot.wait_until_ready()
        logger.info("21時予想タスク準備完了")

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
        evening_running = self.evening_prediction_task.is_running()
        hourly_running = self.hourly_check_task.is_running()

        evening_next = self.evening_prediction_task.next_iteration
        evening_next_str = evening_next.strftime("%Y-%m-%d %H:%M:%S") if evening_next else "不明"

        lines = [
            "⚙️ 自動予想スケジューラーステータス",
            "",
            f"21時予想タスク: {'🟢 実行中' if evening_running else '🔴 停止中'}",
            f"次回実行: {evening_next_str}",
            f"前日予想済み: {len(self.predicted_race_ids_initial)}レース",
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
        self.predicted_race_ids_initial.clear()
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
