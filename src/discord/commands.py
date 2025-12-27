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
)

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
        await bot.add_cog(HelpCommands(bot))
        logger.info("全Cogの登録完了")
    except Exception as e:
        logger.error(f"Cog登録失敗: {e}")
        raise
