"""
Discord Bot スラッシュコマンド

すべてのコマンド結果はコマンド実行者のみに表示（ephemeral）されます。
"""

import os
import logging
from datetime import date
from typing import Optional, List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View
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


# ========================================
# インタラクティブコンポーネント
# ========================================

class HorseSelectView(View):
    """馬選択用のドロップダウンメニュー"""

    def __init__(self, horses: List[Dict[str, Any]], api_base_url: str, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.api_base_url = api_base_url

        # ドロップダウンオプションを作成（最大25件）
        options = []
        for h in horses[:25]:
            birth_year = ""
            if h.get("birth_date"):
                try:
                    birth_year = f" ({str(h['birth_date'])[:4]}年生)"
                except:
                    pass

            options.append(discord.SelectOption(
                label=f"{h.get('name', '不明')}{birth_year}"[:100],
                value=h.get("kettonum", ""),
                description=f"{h.get('runs', 0)}戦{h.get('wins', 0)}勝 {h.get('sex', '')}"[:100]
            ))

        select = Select(
            placeholder="馬を選択してください...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """馬が選択されたときのコールバック"""
        kettonum = interaction.data["values"][0]

        await interaction.response.defer(ephemeral=True)

        try:
            # 馬の詳細情報を取得
            response = requests.get(
                f"{self.api_base_url}/api/horses/{kettonum}",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                msg = format_horse_detail(data)
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"馬情報取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"馬詳細取得エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)


class JockeySelectView(View):
    """騎手選択用のドロップダウンメニュー"""

    def __init__(self, jockeys: List[Dict[str, Any]], api_base_url: str, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.api_base_url = api_base_url

        options = []
        for j in jockeys[:25]:
            win_rate = j.get("win_rate", 0) * 100
            options.append(discord.SelectOption(
                label=f"{j.get('name', '不明')}"[:100],
                value=j.get("code", ""),
                description=f"{j.get('total_rides', 0)}騎乗 {j.get('wins', 0)}勝 勝率{win_rate:.1f}%"[:100]
            ))

        select = Select(
            placeholder="騎手を選択してください...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """騎手が選択されたときのコールバック"""
        code = interaction.data["values"][0]

        # 選択された騎手の情報を表示（現時点では検索結果から取得済みの情報を使用）
        await interaction.response.send_message(
            f"騎手コード: `{code}` の詳細機能は今後実装予定です",
            ephemeral=True
        )


def format_horse_detail(data: Dict[str, Any]) -> str:
    """馬の詳細情報をフォーマット"""
    name = data.get("horse_name", "不明")
    sex = data.get("sex", "不明")
    birth = data.get("birth_date", "不明")
    sire = data.get("sire", "不明")
    dam = data.get("dam", "不明")
    trainer = data.get("trainer", {})
    trainer_name = trainer.get("name", "不明") if isinstance(trainer, dict) else "不明"

    total_races = data.get("total_races", 0)
    wins = data.get("wins", 0)
    win_rate = data.get("win_rate", 0) * 100
    prize = data.get("prize_money", 0)

    lines = [
        f"**{name}** ({sex})",
        f"生年月日: {birth}",
        f"父: {sire} / 母: {dam}",
        f"調教師: {trainer_name}",
        "",
        f"**成績**: {wins}勝 / {total_races}戦 (勝率 {win_rate:.1f}%)",
        f"**獲得賞金**: {prize:,}円",
    ]

    # 直近レースがあれば表示
    recent = data.get("recent_races", [])
    if recent:
        lines.append("")
        lines.append("**直近成績**")
        for r in recent[:5]:
            pos = r.get("finish_position", "?")
            race_name = r.get("race_name", "?")[:15]
            race_date = r.get("race_date", "?")
            lines.append(f"  {race_date} {pos}着 {race_name}")

    return "\n".join(lines)


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
            response = requests.get(
                f"{self.api_base_url}/api/races/today",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                races = data.get("races", [])
                if races:
                    message = format_race_list(races)
                else:
                    message = "本日のレースはありません"
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"レース一覧取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"レース一覧エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="races", description="今後のレース一覧を表示します")
    @app_commands.describe(
        days="何日先まで表示するか（1-14日、デフォルト7日）"
    )
    async def races(self, interaction: discord.Interaction, days: int = 7):
        """今後のレース一覧"""
        await interaction.response.defer(ephemeral=True)

        try:
            response = requests.get(
                f"{self.api_base_url}/api/races/upcoming",
                params={"days": min(days, 14)},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                races = data.get("races", [])
                if races:
                    # 日付ごとにグループ化して表示
                    lines = [f"**今後{days}日間のレース一覧** ({data.get('total', 0)}件)\n"]

                    # 日付でグループ化
                    by_date = {}
                    for race in races:
                        race_date = race.get("race_date", "不明")
                        if race_date not in by_date:
                            by_date[race_date] = []
                        by_date[race_date].append(race)

                    for race_date, date_races in sorted(by_date.items()):
                        lines.append(f"\n**{race_date}**")
                        # 競馬場でグループ化
                        by_venue = {}
                        for race in date_races:
                            venue = race.get("venue", "不明")
                            if venue not in by_venue:
                                by_venue[venue] = []
                            by_venue[venue].append(race)

                        for venue, venue_races in sorted(by_venue.items()):
                            lines.append(f"  [{venue}]")
                            for race in sorted(venue_races, key=lambda x: x.get("race_number", "")):
                                track = "芝" if race.get("track_code", "").startswith("1") else "ダ"
                                grade = f"[{race.get('grade', '')}]" if race.get("grade") else ""
                                lines.append(
                                    f"    {race.get('race_number', '?')} {race.get('race_time', '?')} "
                                    f"{track}{race.get('distance', '?')}m {grade} {race.get('race_name', '?')[:15]}"
                                )

                    message = "\n".join(lines)
                    if len(message) > 1900:
                        message = message[:1900] + "\n... (省略)"
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.followup.send("今後のレースはありません", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"レース一覧取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"今後のレース一覧エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="race", description="レースの詳細情報を表示します")
    @app_commands.describe(
        race_id="レースID（16桁）または指定（例: 京都2r）"
    )
    async def race(self, interaction: discord.Interaction, race_id: str):
        """レース詳細"""
        await interaction.response.defer(ephemeral=True)

        try:
            # レース指定をレースIDに解決
            resolved_id = resolve_race_input(race_id, self.api_base_url)

            response = requests.get(
                f"{self.api_base_url}/api/races/{resolved_id}",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                # 詳細表示用のメッセージ作成
                race_name = data.get("race_name", "不明")
                venue = data.get("venue", "不明")
                race_num = data.get("race_number", "?R")
                race_time = data.get("race_time", "?")
                track = "芝" if data.get("track_code", "").startswith("1") else "ダート"
                distance = data.get("distance", "?")
                grade = f" [{data.get('grade', '')}]" if data.get("grade") else ""

                lines = [
                    f"**{race_name}**{grade}",
                    f"{venue} {race_num} {race_time} {track}{distance}m",
                    "",
                    "**出走馬一覧**",
                    "```",
                    f"{'馬番':>4} {'馬名':<12} {'騎手':<8} {'斤量':>5} {'オッズ':>6}",
                    "-" * 42,
                ]

                entries = data.get("entries", [])
                for e in entries:
                    odds_str = f"{e.get('odds', 0):.1f}" if e.get("odds") else "-"
                    lines.append(
                        f"{e.get('horse_number', '?'):>4} {e.get('horse_name', '?'):<12} "
                        f"{e.get('jockey_name', '?'):<8} {e.get('weight', 0):>5.1f} {odds_str:>6}"
                    )
                lines.append("```")
                lines.append(f"\nレースID: `{resolved_id}`")

                await interaction.followup.send("\n".join(lines), ephemeral=True)
            elif response.status_code == 404:
                await interaction.followup.send(f"レースが見つかりません: {race_id}", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"レース詳細取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"レース詳細エラー: {e}", exc_info=True)
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
                params={"name": name, "limit": 25},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if not data:
                    await interaction.followup.send(
                        f"「{name}」は見つかりませんでした",
                        ephemeral=True
                    )
                elif len(data) == 1:
                    # 1件のみ: 直接詳細を取得して表示
                    horse = data[0]
                    detail_response = requests.get(
                        f"{self.api_base_url}/api/horses/{horse['kettonum']}",
                        timeout=DISCORD_REQUEST_TIMEOUT,
                    )
                    if detail_response.status_code == 200:
                        msg = format_horse_detail(detail_response.json())
                    else:
                        msg = (
                            f"**{horse.get('name', name)}**\n"
                            f"成績: {horse.get('wins', 0)}勝 / {horse.get('runs', 0)}戦"
                        )
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    # 複数件: ドロップダウンメニューを表示
                    view = HorseSelectView(data, self.api_base_url)
                    await interaction.followup.send(
                        f"🔍 「{name}」の検索結果: **{len(data)}件**\n下のメニューから馬を選択してください",
                        view=view,
                        ephemeral=True
                    )
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
                "`/today` - 本日のレース一覧\n"
                "`/races [日数]` - 今後のレース一覧\n"
                "`/race <レースID>` - レースの詳細情報"
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
