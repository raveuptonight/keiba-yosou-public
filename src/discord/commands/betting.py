"""
Discord Bot 馬券購入推奨コマンド

!baken コマンドを提供
"""

import os
import logging
import requests
from discord.ext import commands

from src.config import (
    API_BASE_URL_DEFAULT,
    BETTING_MIN_AMOUNT,
    BETTING_MAX_AMOUNT,
    BETTING_TICKET_TYPES,
)
from src.discord.formatters import format_betting_recommendation
from src.discord.decorators import handle_api_errors, log_command_execution
from src.betting import TicketOptimizer
from src.services.race_resolver import resolve_race_input

logger = logging.getLogger(__name__)


class BettingCommands(commands.Cog):
    """
    馬券購入推奨コマンド

    !baken コマンドを提供します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_DEFAULT)
        self.optimizer = TicketOptimizer()
        logger.info(f"BettingCommands初期化: api_base_url={self.api_base_url}")

    @commands.command(name="baken")
    @handle_api_errors
    @log_command_execution
    async def recommend_betting(
        self,
        ctx: commands.Context,
        race_spec: str,
        budget: int,
        ticket_type: str = None
    ):
        """
        馬券購入推奨コマンド

        Args:
            ctx: コマンドコンテキスト
            race_spec: レース指定（京都2r または 202412280506形式）
            budget: 予算（円）
            ticket_type: 馬券タイプ（省略時は選択メニュー表示）

        使用例:
            !baken 京都2r 10000 3連複
            !baken 中山11R 5000 馬連
        """
        # 予算バリデーション
        if budget < BETTING_MIN_AMOUNT:
            await ctx.send(f"❌ 予算が少なすぎます。最小{BETTING_MIN_AMOUNT:,}円必要です。")
            return

        if budget > BETTING_MAX_AMOUNT:
            await ctx.send(f"❌ 予算が大きすぎます。最大{BETTING_MAX_AMOUNT:,}円までです。")
            return

        # レース指定をレースIDに解決
        race_id = resolve_race_input(race_spec, self.api_base_url)
        logger.debug(f"レース解決: {race_spec} -> {race_id}")

        # 馬券タイプが指定されていない場合は選択を促す
        if ticket_type is None:
            ticket_types = "\n".join([f"  - {t}" for t in BETTING_TICKET_TYPES.keys()])
            await ctx.send(
                f"馬券タイプを指定してください：\n{ticket_types}\n\n"
                f"使用例: `!baken {race_spec} {budget} 3連複`"
            )
            return

        # 馬券タイプ検証
        if ticket_type not in BETTING_TICKET_TYPES:
            await ctx.send(
                f"❌ 未対応の馬券タイプです: {ticket_type}\n\n"
                f"対応タイプ: {', '.join(BETTING_TICKET_TYPES.keys())}"
            )
            return

        await ctx.send(f"🎯 {race_spec}の{ticket_type}買い目を計算中...")

        # APIから予想結果を取得
        response = requests.get(
            f"{self.api_base_url}/api/predictions/",
            params={"race_id": race_id, "limit": 1},
            timeout=10
        )

        if response.status_code != 200:
            await ctx.send(f"❌ 予想データ取得失敗。先に `!predict {race_spec}` で予想を実行してください。")
            return

        predictions = response.json().get("predictions", [])

        if not predictions:
            await ctx.send(f"❌ レース {race_spec} の予想が見つかりません。先に `!predict {race_spec}` で予想を実行してください。")
            return

        prediction = predictions[0]
        prediction_result = prediction.get("prediction_result", {})

        # 買い目最適化
        logger.debug(f"買い目最適化開始: ticket_type={ticket_type}, budget={budget}")
        result = self.optimizer.optimize(ticket_type, budget, prediction_result)

        # 結果フォーマット
        message = format_betting_recommendation(
            race_name=prediction.get("race_name", "不明"),
            race_id=race_id,
            ticket_type=ticket_type,
            budget=budget,
            result=result
        )

        await ctx.send(message)
        logger.info(f"馬券推奨コマンド完了: race_spec={race_spec}, race_id={race_id}, tickets={len(result.get('tickets', []))}")


async def setup(bot: commands.Bot):
    """
    BettingCommandsをBotに登録

    Args:
        bot: Discordボットインスタンス
    """
    await bot.add_cog(BettingCommands(bot))
    logger.info("BettingCommands登録完了")
