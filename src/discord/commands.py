"""
Discord Botコマンド定義

!predict, !today, !stats などのコマンド実装
"""

import os
import logging
from datetime import date
from typing import Optional, Dict, Any
import requests
from discord.ext import commands

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
    DISCORD_STATS_TIMEOUT,
)
from src.exceptions import (
    APIError,
    ExternalAPIError,
)
from src.discord.formatters import (
    format_prediction_notification,
    format_stats_message,
    format_race_list,
    format_help_message,
    format_betting_recommendation,
)
from src.betting import TicketOptimizer

# ロガー設定
logger = logging.getLogger(__name__)


class PredictionCommands(commands.Cog):
    """
    予想関連コマンド

    !predict, !today コマンドを提供します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        logger.info(f"PredictionCommands初期化: api_base_url={self.api_base_url}")

    @commands.command(name="predict")
    async def predict_race(
        self,
        ctx: commands.Context,
        race_id: str,
        temperature: float = 0.3
    ):
        """
        予想実行コマンド

        Args:
            ctx: コマンドコンテキスト
            race_id: レースID
            temperature: LLM温度パラメータ

        使用例:
            !predict 202412280506
            !predict 202412280506 0.5
        """
        logger.info(f"予想コマンド実行開始: race_id={race_id}, temperature={temperature}, user={ctx.author}")
        await ctx.send(f"🔄 予想を実行中... (Race ID: {race_id})")

        try:
            # FastAPI経由で予想実行
            response = requests.post(
                f"{self.api_base_url}/api/predictions/",
                json={"race_id": race_id, "temperature": temperature, "phase": "all"},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 201:
                prediction = response.json()

                logger.debug(f"予想API成功: prediction_id={prediction.get('id')}")

                # 予想完了通知をフォーマット
                message = format_prediction_notification(
                    race_name=prediction.get("race_name", "不明"),
                    race_date=date.fromisoformat(prediction.get("race_date")),
                    venue=prediction.get("venue", "不明"),
                    race_time="15:25",  # TODO: 実データから取得
                    race_number="11R",  # TODO: 実データから取得
                    prediction_result=prediction.get("prediction_result", {}),
                    total_investment=prediction.get("total_investment", 0),
                    expected_return=prediction.get("expected_return", 0),
                    expected_roi=prediction.get("expected_roi", 0.0) * 100,
                    prediction_url=f"{self.api_base_url}/predictions/{prediction.get('id')}",
                )

                await ctx.send(message)
                logger.info(f"予想コマンド完了: race_id={race_id}")

            else:
                logger.error(f"予想API失敗: status={response.status_code}, text={response.text}")
                await ctx.send(
                    f"❌ エラーが発生しました (Status: {response.status_code})\n{response.text}"
                )

        except requests.exceptions.Timeout as e:
            logger.error(f"予想APIタイムアウト: {e}")
            await ctx.send("❌ タイムアウトしました。予想に時間がかかっています。")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"予想API接続エラー: {e}")
            await ctx.send("❌ APIサーバーに接続できません。サーバーが起動しているか確認してください。")
        except requests.exceptions.RequestException as e:
            logger.error(f"予想APIリクエストエラー: {e}")
            await ctx.send(f"❌ APIリクエストエラーが発生しました: {str(e)}")
        except Exception as e:
            logger.exception(f"予想コマンド予期しないエラー: {e}")
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")

    @commands.command(name="today")
    async def today_races(self, ctx: commands.Context):
        """
        本日のレース一覧表示

        Args:
            ctx: コマンドコンテキスト

        使用例:
            !today
        """
        logger.info(f"本日のレースコマンド実行: user={ctx.author}")

        try:
            # TODO: FastAPI経由でレース一覧取得
            # response = requests.get(
            #     f"{self.api_base_url}/api/races",
            #     params={"date": date.today().isoformat()},
            # )

            # モックデータ
            races = [
                {
                    "race_id": "202412260101",
                    "race_name": "中山金杯",
                    "venue": "中山",
                    "race_number": "1R",
                    "race_time": "10:00",
                },
                {
                    "race_id": "202412260201",
                    "race_name": "京都金杯",
                    "venue": "京都",
                    "race_number": "1R",
                    "race_time": "10:35",
                },
            ]

            logger.debug(f"レース一覧取得成功: count={len(races)}")
            message = format_race_list(races)
            await ctx.send(message)

        except Exception as e:
            logger.exception(f"本日のレースコマンド予期しないエラー: {e}")
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")


class StatsCommands(commands.Cog):
    """
    統計関連コマンド

    !stats, !roi コマンドを提供します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        logger.info(f"StatsCommands初期化: api_base_url={self.api_base_url}")

    @commands.command(name="stats")
    async def show_stats(self, ctx: commands.Context, period: str = "all"):
        """
        統計情報表示

        Args:
            ctx: コマンドコンテキスト
            period: 集計期間

        使用例:
            !stats
            !stats daily
            !stats weekly
            !stats monthly
        """
        if period not in ["daily", "weekly", "monthly", "all"]:
            logger.warning(f"統計コマンド不正な期間指定: period={period}, user={ctx.author}")
            await ctx.send(
                "❌ 期間指定が不正です。daily/weekly/monthly/all のいずれかを指定してください。"
            )
            return

        logger.info(f"統計コマンド実行: period={period}, user={ctx.author}")

        try:
            # FastAPI経由で統計取得
            response = requests.get(
                f"{self.api_base_url}/api/stats/",
                params={"period": period},
                timeout=DISCORD_STATS_TIMEOUT
            )

            if response.status_code == 200:
                stats = response.json()
                logger.debug(f"統計API成功: total_races={stats.get('total_races')}")
                message = format_stats_message(stats)
                await ctx.send(message)
            else:
                logger.error(f"統計API失敗: status={response.status_code}")
                await ctx.send(
                    f"❌ エラーが発生しました (Status: {response.status_code})"
                )

        except requests.exceptions.Timeout as e:
            logger.error(f"統計APIタイムアウト: {e}")
            await ctx.send("❌ タイムアウトしました。")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"統計API接続エラー: {e}")
            await ctx.send("❌ APIサーバーに接続できません。")
        except Exception as e:
            logger.exception(f"統計コマンド予期しないエラー: {e}")
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")

    @commands.command(name="roi")
    async def show_roi_graph(self, ctx: commands.Context):
        """
        回収率グラフ表示（未実装）

        Args:
            ctx: コマンドコンテキスト

        使用例:
            !roi
        """
        logger.info(f"ROIグラフコマンド実行（未実装）: user={ctx.author}")
        await ctx.send("📊 ROI推移グラフ機能は未実装です。\n`!stats` コマンドで統計情報を確認できます。")


class BettingCommands(commands.Cog):
    """
    馬券購入推奨コマンド

    !baken コマンドを提供します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        self.optimizer = TicketOptimizer()
        logger.info(f"BettingCommands初期化: api_base_url={self.api_base_url}")

    @commands.command(name="baken")
    async def recommend_betting(
        self,
        ctx: commands.Context,
        race_id: str,
        budget: int,
        ticket_type: str = None
    ):
        """
        馬券購入推奨コマンド

        Args:
            ctx: コマンドコンテキスト
            race_id: レースID
            budget: 予算（円）
            ticket_type: 馬券タイプ（省略時は選択メニュー表示）

        使用例:
            !baken 202412280506 10000 3連複
            !baken 202412280506 5000 馬連
        """
        logger.info(f"馬券推奨コマンド実行: race_id={race_id}, budget={budget}, ticket_type={ticket_type}, user={ctx.author}")

        # 予算バリデーション
        from src.config import BETTING_MIN_AMOUNT, BETTING_MAX_AMOUNT

        if budget < BETTING_MIN_AMOUNT:
            await ctx.send(f"❌ 予算が少なすぎます。最小{BETTING_MIN_AMOUNT:,}円必要です。")
            return

        if budget > BETTING_MAX_AMOUNT:
            await ctx.send(f"❌ 予算が大きすぎます。最大{BETTING_MAX_AMOUNT:,}円までです。")
            return

        # 馬券タイプが指定されていない場合は選択を促す
        if ticket_type is None:
            from src.config import BETTING_TICKET_TYPES
            ticket_types = "\n".join([f"  - {t}" for t in BETTING_TICKET_TYPES.keys()])
            await ctx.send(
                f"馬券タイプを指定してください：\n{ticket_types}\n\n"
                f"使用例: `!baken {race_id} {budget} 3連複`"
            )
            return

        # 馬券タイプ検証
        from src.config import BETTING_TICKET_TYPES
        if ticket_type not in BETTING_TICKET_TYPES:
            await ctx.send(
                f"❌ 未対応の馬券タイプです: {ticket_type}\n\n"
                f"対応タイプ: {', '.join(BETTING_TICKET_TYPES.keys())}"
            )
            return

        await ctx.send(f"🎯 {race_id}の{ticket_type}買い目を計算中...")

        try:
            # APIから予想結果を取得
            response = requests.get(
                f"{self.api_base_url}/api/predictions/",
                params={"race_id": race_id, "limit": 1},
                timeout=10
            )

            if response.status_code != 200:
                await ctx.send(f"❌ 予想データ取得失敗。先に `!predict {race_id}` で予想を実行してください。")
                return

            predictions = response.json().get("predictions", [])

            if not predictions:
                await ctx.send(f"❌ レース {race_id} の予想が見つかりません。先に `!predict {race_id}` で予想を実行してください。")
                return

            prediction = predictions[0]
            prediction_result = prediction.get("prediction_result", {})

            # 買い目最適化
            logger.debug(f"買い目最適化開始: ticket_type={ticket_type}, budget={budget}")
            result = self.optimizer.optimize(ticket_type, budget, prediction_result)

            # 結果フォーマット
            message = format_betting_recommendation(
                race_name=prediction.get("race_name", "不明"),
                race_id=race_id,
                ticket_type=ticket_type,
                budget=budget,
                result=result
            )

            await ctx.send(message)
            logger.info(f"馬券推奨コマンド完了: race_id={race_id}, tickets={len(result.get('tickets', []))}")

        except ValueError as e:
            logger.error(f"馬券推奨バリデーションエラー: {e}")
            await ctx.send(f"❌ エラー: {str(e)}")
        except requests.exceptions.Timeout as e:
            logger.error(f"馬券推奨APIタイムアウト: {e}")
            await ctx.send("❌ タイムアウトしました。")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"馬券推奨API接続エラー: {e}")
            await ctx.send("❌ APIサーバーに接続できません。")
        except Exception as e:
            logger.exception(f"馬券推奨コマンド予期しないエラー: {e}")
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")


class HelpCommands(commands.Cog):
    """
    ヘルプコマンド

    !help コマンドを提供します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        logger.info("HelpCommands初期化")

    @commands.command(name="help")
    async def show_help(self, ctx: commands.Context):
        """
        ヘルプ表示

        Args:
            ctx: コマンドコンテキスト

        使用例:
            !help
        """
        logger.info(f"ヘルプコマンド実行: user={ctx.author}")
        message = format_help_message()
        await ctx.send(message)


async def setup(bot: commands.Bot):
    """
    コマンドをBotに登録

    Args:
        bot: Discordボットインスタンス

    Raises:
        Exception: Cog追加に失敗した場合
    """
    try:
        await bot.add_cog(PredictionCommands(bot))
        await bot.add_cog(StatsCommands(bot))
        await bot.add_cog(BettingCommands(bot))
        await bot.add_cog(HelpCommands(bot))
        logger.info("全Cogの登録完了")
    except Exception as e:
        logger.error(f"Cog登録失敗: {e}")
        raise
