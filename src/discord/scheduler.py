"""
Discord Bot自動予想スケジューラー

レース30分前（馬体重発表後）に最終予想を自動実行し、Discordに通知
"""

import os
import logging
from datetime import datetime, date, time, timedelta, timezone

# 日本標準時
JST = timezone(timedelta(hours=9))
from typing import List, Dict, Any, Optional
import requests
from discord.ext import tasks, commands
import discord

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
    SCHEDULER_CHECK_INTERVAL_MINUTES,
    SCHEDULER_FINAL_PREDICTION_MINUTES_BEFORE,
    SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES,
)
from src.models.ev_recommender import EVRecommender

# ロガー設定
logger = logging.getLogger(__name__)


class PredictionScheduler(commands.Cog):
    """
    自動予想スケジューラー

    レース30分前（馬体重発表後）に最終予想を自動実行し、Discordに通知
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

        週末結果のSelectメニューのインタラクションを処理
        """
        # Selectメニューのインタラクションのみ処理
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")

        # 週末結果の日付選択
        if custom_id == "weekend_result_select":
            await self._handle_weekend_result_select(interaction)
            return

    async def cog_load(self):
        """Cog読み込み時にタスク開始"""
        logger.info("自動予想スケジューラー開始")
        self.hourly_check_task.start()

    async def cog_unload(self):
        """Cog削除時にタスク停止"""
        logger.info("自動予想スケジューラー停止")
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

    async def _execute_prediction(self, race_id: str, is_final: bool = False, send_notification: bool = True) -> Optional[Dict]:
        """
        予想を実行

        Args:
            race_id: レースID
            is_final: 最終予想（馬体重後）かどうか
            send_notification: 通知を送信するかどうか（Falseの場合は予想結果を返す）

        Returns:
            send_notification=Trueの場合: 成功したらTrue、失敗したらFalse
            send_notification=Falseの場合: 成功したら予想結果Dict、失敗したらNone
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

                # 通知なしモードの場合、予想結果を返す
                if not send_notification:
                    return prediction

                # 通知チャンネルに送信
                channel = self.get_notification_channel()
                if channel:
                    if is_final:
                        # 最終予想: シンプルな期待値ベース形式
                        result = prediction.get("prediction_result", {})
                        ranked = result.get("ranked_horses", [])

                        if ranked:
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

                            # === 期待値ベース馬券推奨を取得 ===
                            race_code = prediction.get("race_code") or race_id
                            ev_recommender = EVRecommender()
                            ev_recs = ev_recommender.get_recommendations(
                                race_code=race_code,
                                ranked_horses=ranked,
                                use_realtime_odds=True,
                            )

                            # EV >= 1.5 の推奨馬を収集（単勝・複勝合わせて最大3頭）
                            win_recs = ev_recs.get("win_recommendations", [])
                            place_recs = ev_recs.get("place_recommendations", [])

                            # 推奨馬を統合（重複排除）
                            recommended = {}
                            for rec in win_recs:
                                num = rec["horse_number"]
                                if num not in recommended:
                                    recommended[num] = {
                                        "horse_number": num,
                                        "horse_name": rec["horse_name"],
                                        "win_ev": rec["expected_value"],
                                        "win_odds": rec["odds"],
                                        "place_ev": None,
                                        "place_odds": None,
                                    }
                                else:
                                    recommended[num]["win_ev"] = rec["expected_value"]
                                    recommended[num]["win_odds"] = rec["odds"]

                            for rec in place_recs:
                                num = rec["horse_number"]
                                if num not in recommended:
                                    recommended[num] = {
                                        "horse_number": num,
                                        "horse_name": rec["horse_name"],
                                        "win_ev": None,
                                        "win_odds": None,
                                        "place_ev": rec["expected_value"],
                                        "place_odds": rec["odds"],
                                    }
                                else:
                                    recommended[num]["place_ev"] = rec["expected_value"]
                                    recommended[num]["place_odds"] = rec["odds"]

                            # EV順でソート（win_evとplace_evの最大値で）
                            rec_list = sorted(
                                recommended.values(),
                                key=lambda x: max(x.get("win_ev") or 0, x.get("place_ev") or 0),
                                reverse=True
                            )[:3]  # 最大3頭

                            # === 軸馬推奨（ワイド・連系用）===
                            # 軸馬 = 複勝確率が最も高い馬（3着以内に来る確率が最も高い）
                            axis_horse = max(ranked, key=lambda h: h.get("place_probability", 0)) if ranked else None

                            # シンプルなメッセージ構築
                            lines = [
                                f"🔥 **{venue} {race_num_formatted} 最終予想**",
                                f"{time_formatted}発走 {race_name}",
                                "",
                            ]

                            if rec_list:
                                lines.append("**単複推奨** (EV >= 1.5)")
                                for rec in rec_list:
                                    num = rec["horse_number"]
                                    name = rec["horse_name"][:8]
                                    ev_parts = []
                                    if rec["win_ev"]:
                                        ev_parts.append(f"単{rec['win_ev']:.2f}")
                                    if rec["place_ev"]:
                                        ev_parts.append(f"複{rec['place_ev']:.2f}")
                                    ev_str = "/".join(ev_parts)
                                    lines.append(f"  {num}番 {name} (EV {ev_str})")
                            else:
                                lines.append("**単複推奨なし** (EV >= 1.5 の馬なし)")

                            lines.append("")

                            # 軸馬推奨
                            if axis_horse:
                                lines.append("**軸馬** (ワイド・連系用)")
                                ah_num = axis_horse.get("horse_number", "?")
                                ah_name = axis_horse.get("horse_name", "?")[:8]
                                ah_place = axis_horse.get("place_probability", 0)
                                lines.append(f"  🎯 {ah_num}番 {ah_name} (複勝率 {ah_place:.0%})")

                            message = "\n".join(lines)
                            await channel.send(message)
                            logger.info(f"最終予想送信完了: race_id={race_id}, 推奨馬={len(rec_list)}頭")
                        else:
                            # 予想結果が空の場合
                            logger.warning(f"最終予想結果が空: race_id={race_id}")
                            await channel.send(
                                f"🔥 **{prediction.get('venue', '?')} {prediction.get('race_number', '?')}R 最終予想完了**"
                            )
                    else:
                        # 前日予想は廃止 - 当日最終予想のみ通知
                        logger.debug(f"前日予想スキップ（廃止）: race_id={race_id}")

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
        hourly_running = self.hourly_check_task.is_running()

        lines = [
            "⚙️ 自動予想スケジューラーステータス",
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
