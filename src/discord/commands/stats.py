"""
Discord Bot 統計関連コマンド

!stats, !roi コマンドを提供
"""

import os
import logging
import requests
from discord.ext import commands

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_STATS_TIMEOUT,
)
from src.discord.formatters import format_stats_message
from src.discord.decorators import handle_api_errors, log_command_execution

logger = logging.getLogger(__name__)


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
    @handle_api_errors
    @log_command_execution
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

    @commands.command(name="roi")
    @log_command_execution
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


async def setup(bot: commands.Bot):
    """
    StatsCommandsをBotに登録

    Args:
        bot: Discordボットインスタンス
    """
    await bot.add_cog(StatsCommands(bot))
    logger.info("StatsCommands登録完了")
