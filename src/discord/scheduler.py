"""
Discord Bot自動予想スケジューラー

開催日9時と馬体重発表後に自動予想を実行
"""

import os
import logging
from datetime import datetime, date, time, timedelta, timezone

# 日本標準時
JST = timezone(timedelta(hours=9))
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
from src.discord.formatters import format_prediction_notification, format_final_prediction_notification
from src.models.ev_recommender import EVRecommender, format_ev_recommendations

# ロガー設定
logger = logging.getLogger(__name__)


class RankingSelectView(View):
    """ランキング表示選択ビュー（最終予想用）"""

    def __init__(
        self,
        race_id: str,
        prediction_data: Dict,
        timeout: float = 3600  # 1時間有効
    ):
        super().__init__(timeout=timeout)
        self.race_id = race_id
        self.prediction_data = prediction_data

    @discord.ui.button(label="勝率順", style=discord.ButtonStyle.primary, custom_id="ranking_win", emoji="🏆")
    async def win_ranking_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """勝率順ランキングを表示"""
        await self._show_ranking(interaction, "win")

    @discord.ui.button(label="連対率順", style=discord.ButtonStyle.secondary, custom_id="ranking_quinella", emoji="🥈")
    async def quinella_ranking_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """連対率順ランキングを表示"""
        await self._show_ranking(interaction, "quinella")

    @discord.ui.button(label="複勝率順", style=discord.ButtonStyle.secondary, custom_id="ranking_place", emoji="🥉")
    async def place_ranking_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """複勝率順ランキングを表示"""
        await self._show_ranking(interaction, "place")

    @discord.ui.button(label="穴馬候補", style=discord.ButtonStyle.success, custom_id="ranking_dark", emoji="🐴")
    async def dark_horses_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """穴馬候補を表示"""
        await self._show_ranking(interaction, "dark")

    async def _show_ranking(self, interaction: discord.Interaction, ranking_type: str):
        """指定タイプのランキングを表示"""
        await interaction.response.defer(ephemeral=True)

        result = self.prediction_data.get("prediction_result", {})
        ranked = result.get("ranked_horses", [])
        venue = self.prediction_data.get("venue", "?")
        race_num = self.prediction_data.get("race_number", "?")
        race_name = self.prediction_data.get("race_name", "")

        # レース番号フォーマット
        try:
            race_num_int = int(race_num)
            race_num_formatted = f"{race_num_int}R"
        except (ValueError, TypeError):
            race_num_formatted = f"{race_num}R" if not str(race_num).endswith("R") else race_num

        header = f"**{venue} {race_num_formatted}** {race_name}\n"

        if ranking_type == "win":
            # 勝率順（全馬表示）
            lines = [header, "**勝率順ランキング（単勝向け）**\n"]
            marks = ['◎', '○', '▲', '△', '△', '×', '×', '×', '☆', '☆']
            for h in ranked[:10]:
                rank = h.get('rank', 0)
                mark = marks[rank - 1] if rank <= len(marks) else '☆'
                num = h.get('horse_number', '?')
                name = h.get('horse_name', '?')[:8]
                win = h.get('win_probability', 0)
                quinella = h.get('quinella_probability', 0)
                place = h.get('place_probability', 0)
                lines.append(f"{mark} {rank}位 {num}番 {name} (単{win:.1%} 連{quinella:.1%} 複{place:.1%})")
            message = "\n".join(lines)

        elif ranking_type == "quinella":
            # 連対率順Top5
            quinella_ranking = result.get("quinella_ranking", [])
            lines = [header, "**連対率順 Top5（馬連・ワイド向け）**\n"]
            if quinella_ranking:
                for entry in quinella_ranking[:5]:
                    rank = entry.get('rank', 0)
                    num = entry.get('horse_number', '?')
                    prob = entry.get('quinella_prob', 0)
                    # 馬名を取得
                    horse_name = next((h.get('horse_name', '?') for h in ranked
                                      if h.get('horse_number') == num), '?')[:8]
                    lines.append(f"{rank}位 {num}番 {horse_name} 連対率: {prob:.1%}")
            else:
                lines.append("データなし")
            message = "\n".join(lines)

        elif ranking_type == "place":
            # 複勝率順Top5
            place_ranking = result.get("place_ranking", [])
            lines = [header, "**複勝率順 Top5（複勝向け）**\n"]
            if place_ranking:
                for entry in place_ranking[:5]:
                    rank = entry.get('rank', 0)
                    num = entry.get('horse_number', '?')
                    prob = entry.get('place_prob', 0)
                    # 馬名を取得
                    horse_name = next((h.get('horse_name', '?') for h in ranked
                                      if h.get('horse_number') == num), '?')[:8]
                    lines.append(f"{rank}位 {num}番 {horse_name} 複勝率: {prob:.1%}")
            else:
                lines.append("データなし")
            message = "\n".join(lines)

        elif ranking_type == "dark":
            # 穴馬候補
            dark_horses = result.get("dark_horses", [])
            lines = [header, "**穴馬候補（複勝率>=20%かつ勝率<10%）**\n"]
            if dark_horses:
                for entry in dark_horses[:3]:
                    num = entry.get('horse_number', '?')
                    win = entry.get('win_prob', 0)
                    place = entry.get('place_prob', 0)
                    # 馬名を取得
                    horse_name = next((h.get('horse_name', '?') for h in ranked
                                      if h.get('horse_number') == num), '?')[:8]
                    lines.append(f"🐴 {num}番 {horse_name}: 勝率{win:.1%} → 複勝率{place:.1%}")
                lines.append("")
                lines.append("_勝ち切れないが3着には来る可能性が高い馬_")
            else:
                lines.append("該当馬なし")
            message = "\n".join(lines)
        else:
            message = "不明なランキングタイプ"

        await interaction.followup.send(message, ephemeral=True)


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
            os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", "0")
        )

        # 実行済みレースID記録（重複予想防止）
        self.predicted_race_ids_initial: set = set()  # 前日21時予想済み
        self.predicted_race_ids_final: set = set()    # 馬体重後予想済み

        logger.info(f"PredictionScheduler初期化: channel_id={self.notification_channel_id}")

    async def _handle_weekend_result_select(self, interaction: discord.Interaction):
        """週末結果の日付選択インタラクションを処理"""
        values = interaction.data.get("values", [])
        if not values:
            return

        selected_date = values[0]
        logger.info(f"週末結果詳細リクエスト: date={selected_date}, user={interaction.user}")

        await interaction.response.defer(ephemeral=True)

        try:
            # 選択された日付のデータを取得
            from datetime import datetime
            from src.scheduler.result_collector import ResultCollector

            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
            collector = ResultCollector()
            analysis = collector.collect_and_analyze(target_date)

            if analysis['status'] != 'success':
                await interaction.followup.send(f"❌ {selected_date} のデータが見つかりません", ephemeral=True)
                return

            acc = analysis['accuracy']

            # 詳細メッセージを作成
            lines = [
                f"📊 **{selected_date} 予想精度レポート**",
                f"分析レース数: {acc['analyzed_races']}R",
                "",
                "**【ランキング別成績】**",
            ]

            # ランキング別
            for rank in [1, 2, 3]:
                if rank in acc.get('ranking_stats', {}):
                    r = acc['ranking_stats'][rank]
                    lines.append(
                        f"  {rank}位予想: 1着{r['1着']}回 2着{r['2着']}回 3着{r['3着']}回 "
                        f"(複勝率{r['複勝率']:.1f}%)"
                    )

            # 人気別
            if acc.get('popularity_stats'):
                lines.append("")
                lines.append("**【人気別成績】** (1位予想馬)")
                for pop_cat in ['1-3番人気', '4-6番人気', '7-9番人気', '10番人気以下']:
                    if pop_cat in acc['popularity_stats']:
                        p = acc['popularity_stats'][pop_cat]
                        lines.append(f"  {pop_cat}: {p['対象']}R → 複勝圏{p['複勝圏']}回 ({p['複勝率']:.0f}%)")

            # 信頼度別
            if acc.get('confidence_stats'):
                lines.append("")
                lines.append("**【信頼度別成績】**")
                for conf_cat in ['高(80%以上)', '中(60-80%)', '低(60%未満)']:
                    if conf_cat in acc['confidence_stats']:
                        c = acc['confidence_stats'][conf_cat]
                        lines.append(f"  {conf_cat}: {c['対象']}R → 複勝圏{c['複勝圏']}回 ({c['複勝率']:.0f}%)")

            # 芝/ダート別
            if acc.get('by_track'):
                lines.append("")
                lines.append("**【芝/ダート別】**")
                for track in ['芝', 'ダ']:
                    if track in acc['by_track']:
                        t = acc['by_track'][track]
                        lines.append(f"  {track}: {t['races']}R → 複勝率{t['top3_rate']:.0f}%")

            # 回収率
            rr = acc.get('return_rates', {})
            if rr.get('tansho_investment', 0) > 0:
                lines.append("")
                lines.append("**【回収率】** (1位予想に各100円)")
                lines.append(f"  単勝: {rr['tansho_return']:,}円 / {rr['tansho_investment']:,}円 = {rr['tansho_roi']:.1f}%")
                lines.append(f"  複勝: {rr['fukusho_return']:,}円 / {rr['fukusho_investment']:,}円 = {rr['fukusho_roi']:.1f}%")

            message = "\n".join(lines)
            await interaction.followup.send(message, ephemeral=True)
            logger.info(f"週末結果詳細送信完了: date={selected_date}")

        except Exception as e:
            logger.exception(f"週末結果詳細取得エラー: date={selected_date}, error={e}")
            await interaction.followup.send(f"❌ エラー: {str(e)}", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        インタラクションイベントハンドラ

        daily_scheduler.pyから送信されたSelectメニューのインタラクションを処理
        """
        logger.info(f"インタラクション受信: type={interaction.type}, data={interaction.data}")

        # Selectメニューのインタラクションのみ処理
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")
        logger.info(f"コンポーネントインタラクション: custom_id={custom_id}")

        # 週末結果の日付選択
        if custom_id == "weekend_result_select":
            await self._handle_weekend_result_select(interaction)
            return

        # prediction_selectのみ処理
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

            # レース番号フォーマット（"01" -> "1R"）
            try:
                race_num_int = int(race_num)
                race_num_formatted = f"{race_num_int}R"
            except (ValueError, TypeError):
                race_num_formatted = f"{race_num}R" if not str(race_num).endswith("R") else race_num

            # ヘッダー
            header = f"**{venue} {race_num_formatted}** {time_str} {race_name}"
            lines = [header, ""]

            # 全馬表示（印なし、騎手名あり）
            for h in ranked:
                rank = h.get('rank', 0)
                num = h.get('horse_number', '?')
                name = h.get('horse_name', '?')
                sex = h.get('horse_sex') or ''
                age = h.get('horse_age')
                sex_age = f"{sex}{age}" if sex and age else ""
                jockey = (h.get('jockey_name') or '').replace('　', ' ')[:6]  # 全角→半角スペース
                # 性別年齢と騎手の組み合わせ
                if sex_age and jockey:
                    info_str = f"[{sex_age}/{jockey}]"
                elif sex_age:
                    info_str = f"[{sex_age}]"
                elif jockey:
                    info_str = f"[{jockey}]"
                else:
                    info_str = ""
                win_prob = h.get('win_probability', 0)
                quinella_prob = h.get('quinella_probability', 0)
                place_prob = h.get('place_probability', 0)

                lines.append(
                    f"{rank}位 {num}番 {name} {info_str} "
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
        日付が一致しないレースは除外されます。
        """
        logger.info("21時予想タスク実行")

        try:
            # 翌日のレース一覧を取得（日付厳密チェック有効）
            tomorrow = datetime.now(JST).date() + timedelta(days=1)
            races = await self._fetch_races_for_date(tomorrow, strict_date_match=True)

            if not races:
                logger.info(f"明日({tomorrow})はレース開催なし - 予想スキップ")
                # 通知チャンネルにも通知（オプション）
                channel = self.get_notification_channel()
                if channel:
                    await channel.send(f"📅 明日({tomorrow})は中央競馬の開催がありません。")
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

        レース30分前（馬体重発表後）に再予想を実行します。
        通常、馬体重は発走約75分前に発表されるため、30分前に再予想。
        日付が一致しないレースは除外されます。
        """
        now = datetime.now(JST)
        logger.debug(f"レース時刻チェック: {now}")

        try:
            # 当日のレース一覧を取得（日付厳密チェック有効）
            today = datetime.now(JST).date()
            races = await self._fetch_races_for_date(today, strict_date_match=True)

            if not races:
                return

            for race in races:
                race_id = race.get("race_id")
                race_time_str = race.get("race_time")  # "15:25"形式

                if not race_time_str:
                    continue

                # レース時刻をパース（"HH:MM" または "HHMM" 形式に対応）
                try:
                    if ":" in race_time_str:
                        race_hour, race_minute = map(int, race_time_str.split(":"))
                    elif len(race_time_str) == 4:
                        race_hour = int(race_time_str[:2])
                        race_minute = int(race_time_str[2:])
                    else:
                        raise ValueError(f"Unknown time format: {race_time_str}")
                    race_datetime = datetime.combine(today, time(hour=race_hour, minute=race_minute), tzinfo=JST)
                except (ValueError, IndexError) as e:
                    logger.warning(f"レース時刻パース失敗: {race_time_str} ({e})")
                    continue

                # レースN分前（±M分の余裕）
                minutes_before = SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE
                tolerance_seconds = SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES * 60

                target_time = race_datetime - timedelta(minutes=minutes_before)
                time_diff = abs((now - target_time).total_seconds())

                # 指定時刻の許容範囲内 かつ 未実行
                if time_diff <= tolerance_seconds and race_id not in self.predicted_race_ids_final:
                    venue = race.get("venue", "?")
                    race_num = race.get("race_number", "?")
                    logger.info(f"馬体重発表後の再予想実行: race_id={race_id}, venue={venue}, race_num={race_num}")

                    # 再予想実行（通知は_execute_prediction内で行う）
                    success = await self._execute_prediction(race_id, is_final=True)

                    if success:
                        self.predicted_race_ids_final.add(race_id)

        except Exception as e:
            logger.exception(f"レース時刻チェックタスクエラー: {e}")

    async def _fetch_races_for_date(
        self, target_date: date, strict_date_match: bool = True
    ) -> List[Dict[str, Any]]:
        """
        指定日のレース一覧を取得

        Args:
            target_date: 対象日
            strict_date_match: Trueの場合、対象日と一致しないレースを除外

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

                # 日付の厳密チェック
                if strict_date_match and races:
                    target_date_str = target_date.isoformat()  # "2026-01-10"
                    filtered_races = []
                    for race in races:
                        race_date = race.get("race_date", "")
                        if race_date == target_date_str:
                            filtered_races.append(race)
                        else:
                            logger.warning(
                                f"日付不一致のレースを除外: "
                                f"expected={target_date_str}, actual={race_date}, "
                                f"race_id={race.get('race_id')}"
                            )

                    if len(filtered_races) != len(races):
                        logger.info(
                            f"日付フィルタ適用: {len(races)}件 -> {len(filtered_races)}件"
                        )
                    return filtered_races

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
                f"{self.api_base_url}/api/v1/predictions/generate",
                json={
                    "race_id": race_id,
                    "is_final": is_final  # 最終予想フラグ
                },
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                prediction = response.json()
                pred_id = prediction.get('prediction_id')
                logger.info(f"予想成功: prediction_id={pred_id}")

                # 通知チャンネルに送信
                channel = self.get_notification_channel()
                if channel:
                    if is_final:
                        # 最終予想: コンパクトサマリー + ボタンで詳細表示
                        result = prediction.get("prediction_result", {})
                        ranked = result.get("ranked_horses", [])

                        if ranked:
                            # コンパクトサマリーを生成
                            venue = prediction.get("venue", "不明")
                            race_number = prediction.get("race_number", "?")
                            race_time = prediction.get("race_time", "")
                            race_name = prediction.get("race_name", "")

                            # レース番号フォーマット
                            try:
                                race_num_int = int(race_number.replace("R", ""))
                                race_num_formatted = f"{race_num_int}R"
                            except (ValueError, TypeError):
                                race_num_formatted = f"{race_number}R" if not str(race_number).endswith("R") else race_number

                            # 時刻フォーマット
                            if race_time and len(race_time) >= 4 and ":" not in race_time:
                                time_formatted = f"{race_time[:2]}:{race_time[2:4]}"
                            else:
                                time_formatted = race_time

                            # サマリーメッセージ（Top3のみ表示）
                            lines = [
                                f"🔥 **{venue} {race_num_formatted} 最終予想**",
                                f"{time_formatted}発走 {race_name}",
                                "",
                                "**予想 Top3**",
                            ]

                            marks = ['◎', '○', '▲']
                            for i, h in enumerate(ranked[:3]):
                                mark = marks[i]
                                num = h.get('horse_number', '?')
                                name = h.get('horse_name', '?')[:8]
                                win = h.get('win_probability', 0)
                                lines.append(f"{mark} {num}番 {name} (勝率 {win:.1%})")

                            # 穴馬候補があれば表示
                            dark_horses = result.get("dark_horses", [])
                            if dark_horses:
                                lines.append("")
                                lines.append(f"🐴 穴馬候補: {len(dark_horses)}頭")

                            lines.append("")
                            lines.append("▼ ボタンを押してランキング詳細を表示")

                            message = "\n".join(lines)

                            # RankingSelectViewを作成
                            view = RankingSelectView(
                                race_id=race_id,
                                prediction_data=prediction,
                                timeout=3600  # 1時間有効
                            )

                            await channel.send(message, view=view)

                            # 期待値ベース馬券推奨を取得・送信
                            try:
                                race_code = prediction.get("race_code") or race_id
                                ev_recommender = EVRecommender()
                                ev_recs = ev_recommender.get_recommendations(
                                    race_code=race_code,
                                    ranked_horses=ranked,
                                    use_realtime_odds=True,
                                )
                                ev_message = format_ev_recommendations(ev_recs)
                                await channel.send(ev_message)
                                logger.info(f"EV推奨送信完了: race_id={race_id}")
                            except Exception as ev_err:
                                logger.error(f"EV推奨取得エラー: race_id={race_id}, error={ev_err}")
                        else:
                            # 予想結果が空の場合
                            logger.warning(f"最終予想結果が空: race_id={race_id}")
                            await channel.send(
                                f"🔥 **{prediction.get('venue', '?')} {prediction.get('race_number', '?')}R 最終予想完了**"
                            )
                    else:
                        # 前日予想: 従来のフォーマット
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
                            prediction_url=f"{self.api_base_url}/predictions/{pred_id}",
                        )
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
