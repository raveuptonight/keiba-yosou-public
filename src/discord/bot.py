"""
競馬予想Discord Bot

予想完了通知、レース結果報告、コマンド実行などを行う
"""

import os
import asyncio
import logging
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

# ロギング設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KeibaBot(commands.Bot):
    """競馬予想Bot"""

    def __init__(self):
        # Intentsの設定
        intents = discord.Intents.default()
        intents.message_content = True  # メッセージ内容を読み取るために必要

        # Botの初期化
        super().__init__(
            command_prefix="!",  # コマンドプレフィックス
            intents=intents,
            help_command=None,  # デフォルトのhelpコマンドを無効化（カスタムhelpを使用）
        )

        # 通知チャンネルID
        self.notification_channel_id = int(
            os.getenv("DISCORD_CHANNEL_ID", "0")
        )  # 環境変数から取得

    async def setup_hook(self):
        """Bot起動時の初期化処理"""
        # コマンドCogをロード
        try:
            await self.load_extension("src.discord.commands")
            logger.info("コマンドCogをロード しました")
        except Exception as e:
            logger.error(f"コマンドCogのロードに失敗: {e}")

    async def on_ready(self):
        """Bot起動完了時の処理"""
        logger.info(f"Botがログインしました: {self.user.name} (ID: {self.user.id})")
        logger.info(f"接続サーバー数: {len(self.guilds)}")

        # ステータス設定
        await self.change_presence(
            activity=discord.Game(name="競馬予想 | !help でヘルプ")
        )

        # 通知チャンネルに起動メッセージを送信
        if self.notification_channel_id:
            channel = self.get_channel(self.notification_channel_id)
            if channel:
                await channel.send("🤖 競馬予想Botが起動しました！\n`!help` でコマンド一覧を確認できます。")

    async def on_command_error(self, ctx, error):
        """コマンドエラーハンドリング"""
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(
                "❌ そのコマンドは存在しません。`!help` でコマンド一覧を確認してください。"
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ 引数が不足しています: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ 引数の型が正しくありません: {error}")
        else:
            logger.error(f"コマンドエラー: {error}")
            await ctx.send(f"❌ エラーが発生しました: {error}")

    async def send_notification(self, message: str, channel_id: Optional[int] = None):
        """
        指定チャンネルに通知を送信

        Args:
            message: 送信メッセージ
            channel_id: チャンネルID（省略時はデフォルト通知チャンネル）
        """
        target_channel_id = channel_id or self.notification_channel_id
        if not target_channel_id:
            logger.warning("通知チャンネルIDが設定されていません")
            return

        channel = self.get_channel(target_channel_id)
        if channel:
            await channel.send(message)
            logger.info(f"通知を送信しました (Channel ID: {target_channel_id})")
        else:
            logger.error(f"チャンネルが見つかりません (ID: {target_channel_id})")


def run_bot():
    """Botを起動"""
    # Discord Botトークンを取得
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN が設定されていません")
        raise ValueError("環境変数 DISCORD_BOT_TOKEN を設定してください")

    # チャンネルID確認
    channel_id = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id:
        logger.warning("DISCORD_CHANNEL_ID が設定されていません。通知機能が無効です。")

    # Bot起動
    bot = KeibaBot()
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        logger.error("Discord Bot トークンが無効です")
        raise
    except Exception as e:
        logger.error(f"Bot起動エラー: {e}")
        raise


if __name__ == "__main__":
    run_bot()
