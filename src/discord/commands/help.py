"""
Discord Bot ヘルプコマンド

!help コマンドを提供
"""

import logging
from discord.ext import commands

from src.discord.formatters import format_help_message
from src.discord.decorators import log_command_execution

logger = logging.getLogger(__name__)


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
    @log_command_execution
    async def show_help(self, ctx: commands.Context):
        """
        ヘルプ表示

        Args:
            ctx: コマンドコンテキスト

        使用例:
            !help
        """
        message = format_help_message()
        await ctx.send(message)


async def setup(bot: commands.Bot):
    """
    HelpCommandsをBotに登録

    Args:
        bot: Discordボットインスタンス
    """
    await bot.add_cog(HelpCommands(bot))
    logger.info("HelpCommands登録完了")
