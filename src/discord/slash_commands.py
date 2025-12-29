"""
Discord Bot スラッシュコマンド

すべてのコマンド結果はコマンド実行者のみに表示（ephemeral）されます。
"""

import os
import logging
from datetime import date
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
import requests

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
)
from src.discord.formatters import (
    format_prediction_notification,
    format_race_list,
)
from src.services.race_resolver import resolve_race_input

logger = logging.getLogger(__name__)


class SlashCommands(commands.Cog):
    """
    スラッシュコマンド

    すべてのコマンド結果は実行者のみに表示されます（ephemeral）。
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        logger.info(f"SlashCommands初期化: api_base_url={self.api_base_url}")

    # ========================================
    # 予想コマンド
    # ========================================

    @app_commands.command(name="predict", description="レースの予想を実行します")
    @app_commands.describe(
        race="レース指定（例: 京都2r, 中山11R, 202412280506）",
        temperature="LLM温度パラメータ（0.0-1.0、デフォルト0.3）"
    )
    async def predict(
        self,
        interaction: discord.Interaction,
        race: str,
        temperature: float = 0.3
    ):
        """レース予想を実行"""
        # 処理中メッセージ（ephemeral）
        await interaction.response.defer(ephemeral=True)

        try:
            # レース指定をレースIDに解決
            race_id = resolve_race_input(race, self.api_base_url)
            logger.debug(f"レース解決: {race} -> {race_id}")

            # FastAPI経由で予想実行
            response = requests.post(
                f"{self.api_base_url}/api/predictions/",
                json={"race_id": race_id, "temperature": temperature, "phase": "all"},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 201:
                prediction = response.json()
                message = format_prediction_notification(
                    race_name=prediction.get("race_name", "不明"),
                    race_date=date.fromisoformat(prediction.get("race_date")),
                    venue=prediction.get("venue", "不明"),
                    race_time="15:25",
                    race_number="11R",
                    prediction_result=prediction.get("prediction_result", {}),
                    total_investment=prediction.get("total_investment", 0),
                    expected_return=prediction.get("expected_return", 0),
                    expected_roi=prediction.get("expected_roi", 0.0) * 100,
                    prediction_url=f"{self.api_base_url}/predictions/{prediction.get('id')}",
                )
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"エラーが発生しました (Status: {response.status_code})\n{response.text}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"予想コマンドエラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="today", description="本日のレース一覧を表示します")
    async def today(self, interaction: discord.Interaction):
        """本日のレース一覧"""
        await interaction.response.defer(ephemeral=True)

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
            ]

            message = format_race_list(races)
            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logger.error(f"レース一覧エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    # ========================================
    # 統計コマンド
    # ========================================

    @app_commands.command(name="horse", description="馬の成績を表示します")
    @app_commands.describe(name="馬名")
    async def horse(self, interaction: discord.Interaction, name: str):
        """馬の成績照会"""
        await interaction.response.defer(ephemeral=True)

        try:
            response = requests.get(
                f"{self.api_base_url}/api/horses/search",
                params={"name": name},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if data:
                    horse = data[0]
                    msg = (
                        f"**{horse.get('name', name)}**\n"
                        f"成績: {horse.get('wins', 0)}勝 / {horse.get('runs', 0)}戦\n"
                        f"獲得賞金: {horse.get('prize', 0):,}円"
                    )
                else:
                    msg = f"「{name}」は見つかりませんでした"
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"検索エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"馬検索エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="jockey", description="騎手の成績を表示します")
    @app_commands.describe(name="騎手名")
    async def jockey(self, interaction: discord.Interaction, name: str):
        """騎手の成績照会"""
        await interaction.response.defer(ephemeral=True)

        try:
            response = requests.get(
                f"{self.api_base_url}/api/jockeys/search",
                params={"name": name},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if data:
                    jockey = data[0]
                    msg = (
                        f"**{jockey.get('name', name)}**\n"
                        f"勝率: {jockey.get('win_rate', 0):.1%}\n"
                        f"複勝率: {jockey.get('place_rate', 0):.1%}"
                    )
                else:
                    msg = f"「{name}」は見つかりませんでした"
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"検索エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"騎手検索エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    # ========================================
    # 馬券コマンド
    # ========================================

    @app_commands.command(name="odds", description="レースのオッズを表示します")
    @app_commands.describe(race="レース指定（例: 京都2r）")
    async def odds(self, interaction: discord.Interaction, race: str):
        """オッズ表示"""
        await interaction.response.defer(ephemeral=True)

        try:
            race_id = resolve_race_input(race, self.api_base_url)
            response = requests.get(
                f"{self.api_base_url}/api/races/{race_id}/odds",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                lines = [f"**{race} オッズ**\n"]
                for horse in data.get("horses", [])[:10]:
                    lines.append(
                        f"{horse.get('umaban', '?')}. {horse.get('name', '?')}: "
                        f"{horse.get('odds', '?.?')}倍"
                    )
                await interaction.followup.send("\n".join(lines), ephemeral=True)
            else:
                await interaction.followup.send(
                    f"オッズ取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"オッズ取得エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="result", description="レース結果と回収率を表示します")
    @app_commands.describe(race="レース指定（例: 京都2r）")
    async def result(self, interaction: discord.Interaction, race: str):
        """レース結果表示"""
        await interaction.response.defer(ephemeral=True)

        try:
            race_id = resolve_race_input(race, self.api_base_url)
            response = requests.get(
                f"{self.api_base_url}/api/races/{race_id}/result",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                msg = (
                    f"**{race} 結果**\n"
                    f"1着: {data.get('first', '?')}\n"
                    f"2着: {data.get('second', '?')}\n"
                    f"3着: {data.get('third', '?')}"
                )
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"結果取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"結果取得エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    # ========================================
    # ヘルプコマンド
    # ========================================

    @app_commands.command(name="help", description="コマンド一覧を表示します")
    async def help(self, interaction: discord.Interaction):
        """ヘルプ表示"""
        embed = discord.Embed(
            title="競馬予想Bot コマンド一覧",
            description="すべてのコマンド結果はあなただけに表示されます",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="予想",
            value=(
                "`/predict <レース>` - レース予想を実行\n"
                "`/today` - 本日のレース一覧"
            ),
            inline=False
        )

        embed.add_field(
            name="統計",
            value=(
                "`/horse <馬名>` - 馬の成績を表示\n"
                "`/jockey <騎手名>` - 騎手の成績を表示"
            ),
            inline=False
        )

        embed.add_field(
            name="馬券",
            value=(
                "`/odds <レース>` - オッズを表示\n"
                "`/result <レース>` - レース結果を表示"
            ),
            inline=False
        )

        embed.set_footer(text="レース指定例: 京都2r, 中山11R")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """SlashCommandsをBotに登録"""
    await bot.add_cog(SlashCommands(bot))
    logger.info("SlashCommands登録完了")
