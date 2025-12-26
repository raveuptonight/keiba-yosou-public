"""
Discord Botコマンド定義

!predict, !today, !stats などのコマンド実装
"""

import os
from datetime import date
from typing import Optional
import requests
from discord.ext import commands

from src.discord.formatters import (
    format_prediction_notification,
    format_stats_message,
    format_race_list,
    format_help_message,
)


class PredictionCommands(commands.Cog):
    """予想関連コマンド"""

    def __init__(self, bot):
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

    @commands.command(name="predict")
    async def predict_race(self, ctx, race_id: str, temperature: float = 0.3):
        """
        予想実行コマンド

        使用例:
            !predict 202412280506
            !predict 202412280506 0.5
        """
        await ctx.send(f"🔄 予想を実行中... (Race ID: {race_id})")

        try:
            # FastAPI経由で予想実行
            response = requests.post(
                f"{self.api_base_url}/api/predictions/",
                json={"race_id": race_id, "temperature": temperature, "phase": "all"},
                timeout=300,  # 5分タイムアウト
            )

            if response.status_code == 201:
                prediction = response.json()

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

            else:
                await ctx.send(
                    f"❌ エラーが発生しました (Status: {response.status_code})\n{response.text}"
                )

        except requests.exceptions.Timeout:
            await ctx.send("❌ タイムアウトしました。予想に時間がかかっています。")
        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")

    @commands.command(name="today")
    async def today_races(self, ctx):
        """
        本日のレース一覧表示

        使用例:
            !today
        """
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
                {
                    "race_id": "202412260201",
                    "race_name": "京都金杯",
                    "venue": "京都",
                    "race_number": "1R",
                    "race_time": "10:35",
                },
            ]

            message = format_race_list(races)
            await ctx.send(message)

        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")


class StatsCommands(commands.Cog):
    """統計関連コマンド"""

    def __init__(self, bot):
        self.bot = bot
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

    @commands.command(name="stats")
    async def show_stats(self, ctx, period: str = "all"):
        """
        統計情報表示

        使用例:
            !stats
            !stats daily
            !stats weekly
            !stats monthly
        """
        if period not in ["daily", "weekly", "monthly", "all"]:
            await ctx.send(
                "❌ 期間指定が不正です。daily/weekly/monthly/all のいずれかを指定してください。"
            )
            return

        try:
            # FastAPI経由で統計取得
            response = requests.get(
                f"{self.api_base_url}/api/stats/", params={"period": period}, timeout=10
            )

            if response.status_code == 200:
                stats = response.json()
                message = format_stats_message(stats)
                await ctx.send(message)
            else:
                await ctx.send(
                    f"❌ エラーが発生しました (Status: {response.status_code})"
                )

        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")

    @commands.command(name="roi")
    async def show_roi_graph(self, ctx):
        """
        回収率グラフ表示（未実装）

        使用例:
            !roi
        """
        await ctx.send("📊 ROI推移グラフ機能は未実装です。\n`!stats` コマンドで統計情報を確認できます。")


class HelpCommands(commands.Cog):
    """ヘルプコマンド"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def show_help(self, ctx):
        """
        ヘルプ表示

        使用例:
            !help
        """
        message = format_help_message()
        await ctx.send(message)


async def setup(bot):
    """コマンドをBotに登録"""
    await bot.add_cog(PredictionCommands(bot))
    await bot.add_cog(StatsCommands(bot))
    await bot.add_cog(HelpCommands(bot))
