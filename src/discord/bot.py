"""
競馬予想Discord Bot

予想完了通知、レース結果報告などを行う
"""

import os
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

    Discord通知、予想完了通知などを行います。
    """

    def __init__(self):
        """
        初期化

        Raises:
            MissingEnvironmentVariableError: 必須環境変数が設定されていない場合
        """
        # Intentsの設定
        intents = discord.Intents.default()
        intents.message_content = True

        # Botの初期化
        super().__init__(
            command_prefix="!",  # 従来コマンド用（後方互換性）
            intents=intents,
            help_command=None,
        )

        # 通知チャンネルID（Bot自動通知用）
        channel_id_str = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", "0")
        try:
            self.notification_channel_id = int(channel_id_str)
            logger.info(f"KeibaBot初期化: notification_channel_id={self.notification_channel_id}")
        except ValueError as e:
            logger.error(f"DISCORD_NOTIFICATION_CHANNEL_ID が不正な値です: {channel_id_str}")
            raise BotError(f"DISCORD_NOTIFICATION_CHANNEL_ID が不正な値です: {channel_id_str}") from e

        # コマンド用チャンネルID
        command_channel_id_str = os.getenv("DISCORD_COMMAND_CHANNEL_ID", "0")
        try:
            self.command_channel_id = int(command_channel_id_str)
            logger.info(f"KeibaBot初期化: command_channel_id={self.command_channel_id}")
        except ValueError:
            self.command_channel_id = 0
            logger.warning(f"DISCORD_COMMAND_CHANNEL_ID が不正な値です: {command_channel_id_str}")

    async def setup_hook(self):
        """
        Bot起動時の初期化処理

        Raises:
            BotError: コマンドCogのロードに失敗した場合
        """
        # スケジューラーCogをロード
        try:
            logger.info("スケジューラーCogロード開始")
            await self.load_extension("src.discord.scheduler")
            logger.info("スケジューラーCogロード完了")
        except Exception as e:
            logger.error(f"スケジューラーCogのロードに失敗: {e}")
            raise BotError(f"スケジューラーCogのロードに失敗: {e}") from e

    async def on_ready(self):
        """
        Bot起動完了時の処理
        """
        logger.info(f"Botログイン成功: {self.user.name} (ID: {self.user.id})")
        logger.info(f"接続サーバー数: {len(self.guilds)}")

        try:
            # ステータス設定
            await self.change_presence(
                activity=discord.Game(name="競馬予想")
            )

            # チャンネル確認（起動メッセージは送信しない）
            if self.notification_channel_id:
                channel = self.get_channel(self.notification_channel_id)
                if channel:
                    logger.info(f"通知チャンネル確認完了: channel_id={self.notification_channel_id}")
                else:
                    logger.warning(f"通知チャンネルが見つかりません: channel_id={self.notification_channel_id}")

            if self.command_channel_id:
                channel = self.get_channel(self.command_channel_id)
                if channel:
                    logger.info(f"コマンドチャンネル確認完了: channel_id={self.command_channel_id}")
                else:
                    logger.warning(f"コマンドチャンネルが見つかりません: channel_id={self.command_channel_id}")

        except Exception as e:
            logger.error(f"on_ready処理でエラー発生: {e}")

    async def send_notification(self, message: str, embed: discord.Embed = None):
        """
        通知チャンネルにメッセージを送信（Bot自動通知用）

        Args:
            message: 送信メッセージ
            embed: 埋め込みメッセージ（オプション）

        Raises:
            BotError: 通知送信に失敗した場合
        """
        if not self.notification_channel_id:
            logger.warning("通知チャンネルIDが設定されていません")
            return

        try:
            channel = self.get_channel(self.notification_channel_id)
            if channel:
                if embed:
                    await channel.send(content=message, embed=embed)
                else:
                    await channel.send(message)
                logger.info(f"通知送信完了: channel_id={self.notification_channel_id}")
            else:
                logger.error(f"チャンネルが見つかりません: channel_id={self.notification_channel_id}")
                raise BotError(f"チャンネルが見つかりません: ID={self.notification_channel_id}")
        except discord.errors.HTTPException as e:
            logger.error(f"Discord API通知送信エラー: {e}")
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
    channel_id = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID")
    if not channel_id:
        logger.warning("DISCORD_NOTIFICATION_CHANNEL_ID が設定されていません。通知機能が無効です。")

    # Bot起動
    try:
        logger.info("Bot起動開始")
        bot = KeibaBot()
        bot.run(token, log_handler=None)
    except discord.errors.LoginFailure as e:
        logger.error(f"Discord Bot トークンが無効です: {e}")
        raise BotError("Discord Bot トークンが無効です") from e
    except Exception as e:
        logger.error(f"Bot起動エラー: {e}")
        raise BotError(f"Bot起動エラー: {e}") from e


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    run_bot()
