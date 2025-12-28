"""
Discord Bot 予想関連コマンド

!predict, !today コマンドを提供
"""

import os
import logging
from datetime import date
from typing import Dict, Any
import requests
from discord.ext import commands

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
)
from src.discord.formatters import (
    format_prediction_notification,
    format_race_list,
)
from src.discord.decorators import handle_api_errors, log_command_execution
from src.services.race_resolver import resolve_race_input

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
    @handle_api_errors
    @log_command_execution
    async def predict_race(
        self,
        ctx: commands.Context,
        race_spec: str,
        temperature: float = 0.3
    ):
        """
        予想実行コマンド

        Args:
            ctx: コマンドコンテキスト
            race_spec: レース指定（京都2r または 202412280506形式）
            temperature: LLM温度パラメータ

        使用例:
            !predict 京都2r
            !predict 中山11R
            !predict 202412280506 0.5
        """
        # レース指定をレースIDに解決
        race_id = resolve_race_input(race_spec, self.api_base_url)
        logger.debug(f"レース解決: {race_spec} -> {race_id}")
        await ctx.send(f"🔄 予想を実行中... ({race_spec})")

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

    @commands.command(name="today")
    @handle_api_errors
    @log_command_execution
    async def today_races(self, ctx: commands.Context):
        """
        本日のレース一覧表示

        Args:
            ctx: コマンドコンテキスト

        使用例:
            !today
        """
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


async def setup(bot: commands.Bot):
    """
    PredictionCommandsをBotに登録

    Args:
        bot: Discordボットインスタンス
    """
    await bot.add_cog(PredictionCommands(bot))
    logger.info("PredictionCommands登録完了")
