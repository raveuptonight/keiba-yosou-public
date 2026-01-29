"""
Horse Racing Prediction Discord Bot

Handles prediction completion notifications and race result reports.
"""

import logging
import os

from dotenv import load_dotenv

import discord
from discord.ext import commands
from src.exceptions import (
    BotError,
    MissingEnvironmentVariableError,
)

# Load .env file
load_dotenv()

# Logger setup
logger = logging.getLogger(__name__)


class KeibaBot(commands.Bot):
    """
    Horse Racing Prediction Bot

    Handles Discord notifications and prediction completion alerts.
    """

    def __init__(self):
        """
        Initialize the bot.

        Raises:
            MissingEnvironmentVariableError: If required environment variables are not set
        """
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True

        # Initialize bot
        super().__init__(
            command_prefix="!",  # For legacy commands (backward compatibility)
            intents=intents,
            help_command=None,
        )

        # Notification channel ID (for bot auto-notifications)
        channel_id_str = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", "0")
        try:
            self.notification_channel_id = int(channel_id_str)
            logger.info(
                f"KeibaBot initialized: notification_channel_id={self.notification_channel_id}"
            )
        except ValueError as e:
            logger.error(f"DISCORD_NOTIFICATION_CHANNEL_ID has invalid value: {channel_id_str}")
            raise BotError(
                f"DISCORD_NOTIFICATION_CHANNEL_ID has invalid value: {channel_id_str}"
            ) from e

        # Command channel ID
        command_channel_id_str = os.getenv("DISCORD_COMMAND_CHANNEL_ID", "0")
        try:
            self.command_channel_id = int(command_channel_id_str)
            logger.info(f"KeibaBot initialized: command_channel_id={self.command_channel_id}")
        except ValueError:
            self.command_channel_id = 0
            logger.warning(
                f"DISCORD_COMMAND_CHANNEL_ID has invalid value: {command_channel_id_str}"
            )

    async def setup_hook(self):
        """
        Bot startup initialization.

        Raises:
            BotError: If command Cog loading fails
        """
        # Load scheduler Cog
        try:
            logger.info("Starting scheduler Cog load")
            await self.load_extension("src.discord.scheduler")
            logger.info("Scheduler Cog load complete")
        except Exception as e:
            logger.error(f"Failed to load scheduler Cog: {e}")
            raise BotError(f"Failed to load scheduler Cog: {e}") from e

    async def on_ready(self):
        """
        Handler for bot startup completion.
        """
        logger.info(f"Bot login successful: {self.user.name} (ID: {self.user.id})")
        logger.info(f"Connected servers: {len(self.guilds)}")

        try:
            # Set status
            await self.change_presence(activity=discord.Game(name="Horse Racing Prediction"))

            # Verify channels (don't send startup message)
            if self.notification_channel_id:
                channel = self.get_channel(self.notification_channel_id)
                if channel:
                    logger.info(
                        f"Notification channel verified: channel_id={self.notification_channel_id}"
                    )
                else:
                    logger.warning(
                        f"Notification channel not found: channel_id={self.notification_channel_id}"
                    )

            if self.command_channel_id:
                channel = self.get_channel(self.command_channel_id)
                if channel:
                    logger.info(f"Command channel verified: channel_id={self.command_channel_id}")
                else:
                    logger.warning(
                        f"Command channel not found: channel_id={self.command_channel_id}"
                    )

        except Exception as e:
            logger.error(f"Error in on_ready handler: {e}")

    async def send_notification(self, message: str, embed: discord.Embed = None):
        """
        Send message to notification channel (for bot auto-notifications).

        Args:
            message: Message to send
            embed: Embedded message (optional)

        Raises:
            BotError: If notification sending fails
        """
        if not self.notification_channel_id:
            logger.warning("Notification channel ID is not set")
            return

        try:
            channel = self.get_channel(self.notification_channel_id)
            if channel:
                if embed:
                    await channel.send(content=message, embed=embed)
                else:
                    await channel.send(message)
                logger.info(f"Notification sent: channel_id={self.notification_channel_id}")
            else:
                logger.error(f"Channel not found: channel_id={self.notification_channel_id}")
                raise BotError(f"Channel not found: ID={self.notification_channel_id}")
        except discord.errors.HTTPException as e:
            logger.error(f"Discord API notification error: {e}")
            raise BotError(f"Notification sending failed: {e}") from e


def run_bot():
    """
    Start the bot.

    Raises:
        MissingEnvironmentVariableError: If DISCORD_BOT_TOKEN is not set
        BotError: If bot startup fails
    """
    # Get Discord bot token
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set")
        raise MissingEnvironmentVariableError("DISCORD_BOT_TOKEN")

    # Check channel ID
    channel_id = os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID")
    if not channel_id:
        logger.warning("DISCORD_NOTIFICATION_CHANNEL_ID is not set. Notification feature disabled.")

    # Start bot
    try:
        logger.info("Starting bot")
        bot = KeibaBot()
        bot.run(token, log_handler=None)
    except discord.errors.LoginFailure as e:
        logger.error(f"Discord bot token is invalid: {e}")
        raise BotError("Discord bot token is invalid") from e
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
        raise BotError(f"Bot startup error: {e}") from e


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    run_bot()
