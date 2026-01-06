"""
Discord Bot コマンドモジュール

全てのCogを一括登録するためのエントリーポイント
"""

import logging
from discord.ext import commands

logger = logging.getLogger(__name__)


async def setup(bot: commands.Bot):
    """
    全てのコマンドCogをBotに登録

    Args:
        bot: Discordボットインスタンス

    Raises:
        Exception: Cog追加に失敗した場合
    """
    try:
        # 各Cogモジュールをロード
        await bot.load_extension("src.discord.commands.prediction")
        await bot.load_extension("src.discord.commands.stats")
        await bot.load_extension("src.discord.commands.help")

        logger.info("全Cogの登録完了")

    except Exception as e:
        logger.error(f"Cog登録失敗: {e}")
        raise
