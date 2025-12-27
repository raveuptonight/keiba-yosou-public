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

from src.exceptions import (
    MissingEnvironmentVariableError,
    BotError,
)

# .envファイルを読み込み
load_dotenv()

# ロガー設定
logger = logging.getLogger(__name__)


class KeibaBot(commands.Bot):
    """
    競馬予想Bot

    Discord通知、コマンド実行、予想完了通知などを行います。
    """

    def __init__(self):
        """
        初期化

        Raises:
            MissingEnvironmentVariableError: 必須環境変数が設定されていない場合
        """
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
        channel_id_str = os.getenv("DISCORD_CHANNEL_ID", "0")
        try:
            self.notification_channel_id = int(channel_id_str)
            logger.info(f"KeibaBot初期化: notification_channel_id={self.notification_channel_id}")
        except ValueError as e:
            logger.error(f"DISCORD_CHANNEL_ID が不正な値です: {channel_id_str}")
            raise BotError(f"DISCORD_CHANNEL_ID が不正な値です: {channel_id_str}") from e

    async def setup_hook(self):
        """
        Bot起動時の初期化処理

        Raises:
            BotError: コマンドCogのロードに失敗した場合
        """
        # コマンドCogをロード
        try:
            logger.info("コマンドCogロード開始")
            await self.load_extension("src.discord.commands")
            logger.info("✅ コマンドCogロード完了")
        except Exception as e:
            logger.error(f"コマンドCogのロードに失敗: {e}")
            raise BotError(f"コマンドCogのロードに失敗: {e}") from e

    async def on_ready(self):
        """
        Bot起動完了時の処理
        """
        logger.info(f"✅ Botログイン成功: {self.user.name} (ID: {self.user.id})")
        logger.info(f"接続サーバー数: {len(self.guilds)}")

        try:
            # ステータス設定
            await self.change_presence(
                activity=discord.Game(name="競馬予想 | !help でヘルプ")
            )
            logger.debug("ステータス設定完了")

            # 通知チャンネルに起動メッセージを送信
            if self.notification_channel_id:
                channel = self.get_channel(self.notification_channel_id)
                if channel:
                    await channel.send("🤖 競馬予想Botが起動しました！\n`!help` でコマンド一覧を確認できます。")
                    logger.info(f"起動メッセージ送信完了: channel_id={self.notification_channel_id}")
                else:
                    logger.warning(f"通知チャンネルが見つかりません: channel_id={self.notification_channel_id}")
            else:
                logger.warning("通知チャンネルIDが設定されていません（通知無効）")

        except Exception as e:
            logger.error(f"on_ready処理でエラー発生: {e}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """
        コマンドエラーハンドリング

        Args:
            ctx: コマンドコンテキスト
            error: コマンドエラー
        """
        if isinstance(error, commands.CommandNotFound):
            logger.warning(f"存在しないコマンド実行: user={ctx.author}, message={ctx.message.content}")
            await ctx.send(
                "❌ そのコマンドは存在しません。`!help` でコマンド一覧を確認してください。"
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            logger.warning(f"引数不足: user={ctx.author}, param={error.param.name}")
            await ctx.send(f"❌ 引数が不足しています: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            logger.warning(f"引数型エラー: user={ctx.author}, error={error}")
            await ctx.send(f"❌ 引数の型が正しくありません: {error}")
        else:
            logger.error(f"コマンドエラー: user={ctx.author}, error={error}", exc_info=True)
            await ctx.send(f"❌ エラーが発生しました: {error}")

    async def send_notification(self, message: str, channel_id: Optional[int] = None):
        """
        指定チャンネルに通知を送信

        Args:
            message: 送信メッセージ
            channel_id: チャンネルID（省略時はデフォルト通知チャンネル）

        Raises:
            BotError: 通知送信に失敗した場合
        """
        target_channel_id = channel_id or self.notification_channel_id
        if not target_channel_id:
            logger.warning("通知チャンネルIDが設定されていません")
            return

        try:
            channel = self.get_channel(target_channel_id)
            if channel:
                await channel.send(message)
                logger.info(f"✅ 通知送信完了: channel_id={target_channel_id}, message_len={len(message)}")
            else:
                logger.error(f"チャンネルが見つかりません: channel_id={target_channel_id}")
                raise BotError(f"チャンネルが見つかりません: ID={target_channel_id}")
        except discord.errors.HTTPException as e:
            logger.error(f"Discord API通知送信エラー: {e}")
            raise BotError(f"通知送信失敗: {e}") from e
        except Exception as e:
            logger.error(f"通知送信予期しないエラー: {e}")
            raise BotError(f"通知送信失敗: {e}") from e


def run_bot():
    """
    Botを起動

    Raises:
        MissingEnvironmentVariableError: DISCORD_BOT_TOKENが設定されていない場合
        BotError: Bot起動に失敗した場合
    """
    # Discord Botトークンを取得
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN が設定されていません")
        raise MissingEnvironmentVariableError("DISCORD_BOT_TOKEN")

    # チャンネルID確認
    channel_id = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id:
        logger.warning("DISCORD_CHANNEL_ID が設定されていません。通知機能が無効です。")

    # Bot起動
    try:
        logger.info("Bot起動開始")
        bot = KeibaBot()
        bot.run(token, log_handler=None)  # log_handlerはNoneに設定（独自ロギング使用）
        logger.info("Bot起動完了")
    except discord.errors.LoginFailure as e:
        logger.error(f"Discord Bot トークンが無効です: {e}")
        raise BotError("Discord Bot トークンが無効です") from e
    except Exception as e:
        logger.error(f"Bot起動エラー: {e}")
        raise BotError(f"Bot起動エラー: {e}") from e


if __name__ == "__main__":
    # ロギング設定（直接実行時）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    run_bot()
