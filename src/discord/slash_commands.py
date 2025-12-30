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
from discord.ui import Select, View, Button
import requests

from src.config import (
    API_BASE_URL_DEFAULT,
    DISCORD_REQUEST_TIMEOUT,
)
from src.discord.formatters import (
    format_prediction_notification,
    format_race_list,
)
from src.services.race_resolver import resolve_race_input, MultipleRacesFoundException

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
        self.jockeys = jockeys  # 選択時に詳細を取得するため保存

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

        # 選択された騎手を検索結果から取得
        selected_jockey = next((j for j in self.jockeys if j.get("code") == code), None)

        if selected_jockey:
            msg = (
                f"**{selected_jockey.get('name', '不明')}**\n"
                f"騎乗数: {selected_jockey.get('total_rides', 0):,}回\n"
                f"勝利数: {selected_jockey.get('wins', 0):,}回\n"
                f"勝率: {selected_jockey.get('win_rate', 0):.1%}\n"
                f"複勝率: {selected_jockey.get('place_rate', 0):.1%}"
            )
        else:
            msg = f"騎手コード: `{code}` の情報取得に失敗しました"

        await interaction.response.send_message(msg, ephemeral=True)


class RaceSelectView(View):
    """レース選択用のドロップダウンメニュー"""

    def __init__(self, races: List[Dict[str, Any]], api_base_url: str, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.api_base_url = api_base_url
        self.races = races

        options = []
        for race in races[:25]:
            race_date = race.get("race_date", "")
            race_name = race.get("race_name", "不明")
            venue = race.get("venue", "")
            race_num = race.get("race_number", "?R")
            grade = race.get("grade", "")
            grade_str = f" [{grade}]" if grade else ""

            label = f"{race_date} {venue} {race_num} {race_name}{grade_str}"[:100]
            description = f"{race.get('distance', '?')}m"[:100]

            options.append(discord.SelectOption(
                label=label,
                value=race.get("race_id", ""),
                description=description
            ))

        select = Select(
            placeholder="レースを選択してください...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """レースが選択されたときのコールバック"""
        race_id = interaction.data["values"][0]

        await interaction.response.defer(ephemeral=True)

        try:
            # レースの詳細情報を取得
            response = requests.get(
                f"{self.api_base_url}/api/races/{race_id}",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()

                # レース情報のEmbedを作成（raceコマンドと同じ処理）
                race_name = data.get("race_name", "不明")
                venue = data.get("venue", "不明")
                race_num = data.get("race_number", "?R")
                race_time = data.get("race_time", "?")
                track = "芝" if data.get("track_code", "").startswith("1") else "ダート"
                distance = data.get("distance", "?")
                grade_code = data.get("grade")
                grade = f" [{grade_code}]" if grade_code else ""

                # 過去レースかチェック
                is_past_race = data.get("results") is not None

                if is_past_race:
                    # 過去レース：結果表示
                    embed = discord.Embed(
                        title=f"🏆 {race_name}{grade} [終了]",
                        description=f"{venue} {race_num} {race_time} | {track}{distance}m",
                        color=discord.Color.blue()
                    )

                    # レース結果（上位5着）
                    results = data.get("results", [])[:5]
                    if results:
                        result_text = ""
                        for r in results:
                            pos = r['finish_position']
                            num = r['horse_number']
                            name = r['horse_name']
                            time = r['finish_time']
                            kohan_3f = r.get('kohan_3f')

                            # タイムを秒に変換して表示
                            if time and len(time) >= 3:
                                minutes = int(time[:-2]) if len(time) > 2 else 0
                                seconds = int(time[-2:]) if len(time) >= 2 else 0
                                time_str = f"{minutes}:{seconds:02d}.{time[-1] if len(time) > 3 else '0'}"
                            else:
                                time_str = time

                            # 上がり3Fを秒に変換
                            agari_str = ""
                            if kohan_3f and len(kohan_3f) >= 3:
                                agari_sec = int(kohan_3f) / 10.0
                                agari_str = f" (上り{agari_sec:.1f})"

                            result_text += f"{pos}着: {num}番 {name} {time_str}{agari_str}\n"
                        embed.add_field(name="🏁 レース結果", value=result_text, inline=False)

                    # 払戻金
                    payoffs = data.get("payoffs", {})
                    if payoffs:
                        payoff_text = ""
                        if payoffs.get("win"):
                            win = payoffs['win']
                            payoff_text += f"単勝: {win['kumi']}番 {win['payoff']:,}円\n"
                        if payoffs.get("quinella"):
                            q = payoffs['quinella']
                            payoff_text += f"馬連: {q['kumi']} {q['payoff']:,}円\n"
                        if payoffs.get("trifecta"):
                            tf = payoffs['trifecta']
                            payoff_text += f"3連単: {tf['kumi']} {tf['payoff']:,}円\n"

                        if payoff_text:
                            embed.add_field(name="💰 払戻金", value=payoff_text, inline=False)

                    # ラップタイム
                    lap_times = data.get("lap_times", [])
                    if lap_times:
                        # 200m毎のラップを秒に変換して表示
                        lap_str = " - ".join([f"{int(lap)/10:.1f}" for lap in lap_times[:10]])  # 最初の10ラップのみ
                        if len(lap_times) > 10:
                            lap_str += " ..."
                        embed.add_field(name="⏱️ ラップタイム (200m毎)", value=lap_str, inline=False)

                    # 馬同士の対戦表
                    head_to_head = data.get("head_to_head", [])
                    if head_to_head:
                        h2h_text = ""
                        for matchup in head_to_head[:5]:  # 最新5レースのみ
                            race_name = matchup.get("race_name", "不明")[:12]
                            race_date = matchup.get("race_date", "")[:10]
                            horses = matchup.get("horses", [])

                            # 馬名と着順を表示
                            horse_results = ", ".join([
                                f"{h['finish_position']}着:{h['name'][:6]}"
                                for h in horses[:4]  # 最大4頭まで
                            ])
                            h2h_text += f"**{race_date}** {race_name}\n└ {horse_results}\n"

                        if h2h_text:
                            embed.add_field(name="🔄 過去対戦成績", value=h2h_text, inline=False)

                    embed.set_footer(text=f"レースID: {race_id}")

                    # インタラクティブ出馬表ビューも作成
                    view = RaceCardView(data, self.api_base_url)

                    await interaction.followup.send(
                        embed=embed,
                        view=view,
                        ephemeral=True
                    )
                else:
                    # 未来レース：コンパクト表形式の出馬表
                    embed = discord.Embed(
                        title=f"🏇 {race_name}{grade}",
                        description=f"{venue} {race_num} {race_time} | {track}{distance}m",
                        color=discord.Color.gold()
                    )

                    # 出馬表をコンパクトな表形式で作成
                    entries = data.get("entries", [])
                    if entries:
                        # ヘッダー
                        table_text = "```\n"
                        table_text += "馬番 馬名              騎手         斤量  オッズ\n"
                        table_text += "─────────────────────────────────────────\n"

                        # 各馬の情報
                        for entry in entries[:16]:  # 最大16頭まで
                            num = entry.get('horse_number', 0)
                            name = entry.get('horse_name', '不明')[:10]  # 10文字まで
                            jockey = entry.get('jockey_name', '不明')[:8]  # 8文字まで
                            weight = entry.get('weight', 0)
                            odds = entry.get('odds', 0)

                            # 等幅フォントで整形
                            table_text += f"{num:>3} {name:<10} {jockey:<8} {weight:>5.1f} {odds:>6.1f}\n"

                        table_text += "```"
                        embed.add_field(name="📋 出馬表", value=table_text, inline=False)

                    # 馬同士の対戦表
                    head_to_head = data.get("head_to_head", [])
                    if head_to_head:
                        h2h_text = ""
                        for matchup in head_to_head[:5]:  # 最新5レースのみ
                            race_name = matchup.get("race_name", "不明")[:12]
                            race_date = matchup.get("race_date", "")[:10]
                            horses = matchup.get("horses", [])

                            # 馬名と着順を表示
                            horse_results = ", ".join([
                                f"{h['finish_position']}着:{h['name'][:6]}"
                                for h in horses[:4]  # 最大4頭まで
                            ])
                            h2h_text += f"**{race_date}** {race_name}\n└ {horse_results}\n"

                        if h2h_text:
                            embed.add_field(name="🔄 過去対戦成績", value=h2h_text, inline=False)

                    # インタラクティブビュー（血統・調教データ表示用）
                    view = RaceCardView(data, self.api_base_url)

                    await interaction.followup.send(
                        embed=embed,
                        view=view,
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    f"レース情報取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"レース詳細取得エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)


class RaceCardView(View):
    """出馬表のインタラクティブビュー"""

    def __init__(self, race_data: Dict[str, Any], api_base_url: str, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.race_data = race_data
        self.api_base_url = api_base_url
        self.entries = race_data.get("entries", [])

        # 馬選択ドロップダウン（最大25頭）
        if self.entries:
            options = []
            for entry in self.entries[:25]:
                umaban = entry.get("horse_number", "?")
                horse_name = entry.get("horse_name", "不明")[:30]
                odds = entry.get("odds")
                odds_str = f"{odds:.1f}" if odds else "-"

                options.append(discord.SelectOption(
                    label=f"{umaban}番 {horse_name}"[:100],
                    value=str(umaban),
                    description=f"オッズ: {odds_str}倍 | 騎手: {entry.get('jockey_name', '?')[:20]}"[:100]
                ))

            select = Select(
                placeholder="馬を選択して詳細を表示...",
                options=options,
                min_values=1,
                max_values=1
            )
            select.callback = self.horse_selected
            self.add_item(select)

    async def horse_selected(self, interaction: discord.Interaction):
        """馬が選択されたときのコールバック"""
        umaban = int(interaction.data["values"][0])

        # 選択された馬の情報を取得
        selected_horse = next((e for e in self.entries if e.get("horse_number") == umaban), None)

        if not selected_horse:
            await interaction.response.send_message("馬情報の取得に失敗しました", ephemeral=True)
            return

        # 馬の詳細情報をAPIから取得
        await interaction.response.defer(ephemeral=True)

        kettonum = selected_horse.get("kettonum")
        horse_name = selected_horse.get("horse_name", "不明")

        try:
            response = requests.get(
                f"{self.api_base_url}/api/horses/{kettonum}",
                timeout=10,
            )

            if response.status_code == 200:
                horse_data = response.json()
                # 詳細ボタン付きビューを作成
                detail_view = HorseDetailButtonView(horse_data, selected_horse, self.api_base_url)
                embed = create_horse_summary_embed(horse_data, selected_horse)
                await interaction.followup.send(embed=embed, view=detail_view, ephemeral=True)
            else:
                # API失敗時は基本情報のみ表示
                msg = (
                    f"**{umaban}番 {horse_name}**\n"
                    f"騎手: {selected_horse.get('jockey_name', '不明')}\n"
                    f"斤量: {selected_horse.get('weight', 0)}kg\n"
                    f"オッズ: {selected_horse.get('odds', '-')}倍"
                )
                await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            logger.error(f"馬詳細取得エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)


class HorseDetailButtonView(View):
    """馬詳細情報のボタン付きビュー"""

    def __init__(self, horse_data: Dict[str, Any], race_entry: Dict[str, Any], api_base_url: str, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.horse_data = horse_data
        self.race_entry = race_entry
        self.api_base_url = api_base_url

        # ボタンを追加
        self.add_item(Button(label="📊 過去成績", style=discord.ButtonStyle.primary, custom_id="past_races"))
        self.add_item(Button(label="🧬 血統表", style=discord.ButtonStyle.secondary, custom_id="pedigree"))
        self.add_item(Button(label="🏃 調教データ", style=discord.ButtonStyle.secondary, custom_id="training"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """ボタンクリック時の処理"""
        custom_id = interaction.data.get("custom_id")

        if custom_id == "past_races":
            await self.show_past_races(interaction)
        elif custom_id == "pedigree":
            await self.show_pedigree(interaction)
        elif custom_id == "training":
            await self.show_training(interaction)

        return True

    async def show_past_races(self, interaction: discord.Interaction):
        """過去成績を表示"""
        await interaction.response.defer(ephemeral=True)

        recent_races = self.horse_data.get("recent_races", [])[:10]

        if not recent_races:
            await interaction.followup.send("過去成績データがありません", ephemeral=True)
            return

        lines = [f"**{self.horse_data.get('horse_name', '不明')} - 過去10走**\n"]
        lines.append("```")
        lines.append(f"{'日付':<12} {'着順':>4} {'競馬場':<6} {'距離':>6} {'タイム':>8}")
        lines.append("-" * 50)

        for race in recent_races:
            race_date = str(race.get("race_date", ""))[:10]
            pos = race.get("finish_position", "?")
            venue = race.get("venue", "?")[:4]
            distance = race.get("distance", "?")
            time_val = race.get("time", "?")

            lines.append(f"{race_date:<12} {pos:>4}着 {venue:<6} {distance:>6}m {time_val:>8}")

        lines.append("```")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    async def show_pedigree(self, interaction: discord.Interaction):
        """血統表を表示"""
        await interaction.response.defer(ephemeral=True)

        pedigree = self.horse_data.get("pedigree", {})

        embed = discord.Embed(
            title=f"🧬 {self.horse_data.get('horse_name', '不明')} - 血統表",
            color=discord.Color.green()
        )

        # 父系
        embed.add_field(
            name="父系",
            value=(
                f"**父**: {pedigree.get('sire', '不明')}\n"
                f"├ 父父: {pedigree.get('sire_sire', '不明')}\n"
                f"└ 父母: {pedigree.get('sire_dam', '不明')}"
            ),
            inline=False
        )

        # 母系
        embed.add_field(
            name="母系",
            value=(
                f"**母**: {pedigree.get('dam', '不明')}\n"
                f"├ 母父: {pedigree.get('dam_sire', '不明')}\n"
                f"└ 母母: {pedigree.get('dam_dam', '不明')}"
            ),
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def show_training(self, interaction: discord.Interaction):
        """調教データを表示"""
        await interaction.response.defer(ephemeral=True)

        kettonum = self.horse_data.get("kettonum")
        if not kettonum:
            await interaction.followup.send("血統登録番号が取得できませんでした", ephemeral=True)
            return

        # 調教データを取得
        response = requests.get(
            f"{self.api_base_url}/api/horses/{kettonum}/training?days_back=30",
            timeout=10
        )

        if response.status_code != 200:
            await interaction.followup.send(
                f"調教データ取得エラー (Status: {response.status_code})",
                ephemeral=True
            )
            return

        training_list = response.json()

        if not training_list:
            msg = f"**{self.horse_data.get('horse_name', '不明')} - 調教データ**\n\n調教データがありません"
        else:
            msg = f"**{self.horse_data.get('horse_name', '不明')} - 調教データ**\n\n"
            for t in training_list[:10]:  # 最新10件
                t_type = t.get("training_type", "不明")
                t_date = t.get("training_date", "")
                formatted_date = f"{t_date[:4]}/{t_date[4:6]}/{t_date[6:8]}" if len(t_date) == 8 else t_date
                time_4f = t.get("time_4f", "-")
                time_3f = t.get("time_3f", "-")
                msg += f"**{formatted_date}** [{t_type}] 4F: {time_4f} / 3F: {time_3f}\n"

        await interaction.followup.send(msg, ephemeral=True)


def create_horse_summary_embed(horse_data: Dict[str, Any], race_entry: Dict[str, Any]) -> discord.Embed:
    """馬のサマリーEmbedを作成（血統・近走・調教データ含む）"""
    horse_name = horse_data.get("horse_name", "不明")

    embed = discord.Embed(
        title=f"🐴 {race_entry.get('horse_number', '?')}番 {horse_name}",
        description="馬の詳細情報",
        color=discord.Color.blue()
    )

    # 基本情報
    sex = horse_data.get("sex", "?")
    birth_date = horse_data.get("birth_date", "?")
    trainer = horse_data.get("trainer", {})
    trainer_name = trainer.get("name", "不明") if isinstance(trainer, dict) else "不明"

    embed.add_field(
        name="📋 基本情報",
        value=(
            f"性別: {sex}\n"
            f"生年月日: {birth_date}\n"
            f"調教師: {trainer_name}"
        ),
        inline=True
    )

    # 今回のレース情報
    embed.add_field(
        name="🏇 今回",
        value=(
            f"騎手: {race_entry.get('jockey_name', '不明')}\n"
            f"斤量: {race_entry.get('weight', 0)}kg\n"
            f"オッズ: {race_entry.get('odds', '-')}倍"
        ),
        inline=True
    )

    # 通算成績
    total_races = horse_data.get("total_races", 0)
    wins = horse_data.get("wins", 0)
    win_rate = horse_data.get("win_rate", 0) * 100

    embed.add_field(
        name="📊 通算成績",
        value=(
            f"{wins}勝 / {total_races}戦\n"
            f"勝率: {win_rate:.1f}%\n"
            f"賞金: {horse_data.get('prize_money', 0):,}円"
        ),
        inline=True
    )

    # 血統情報（3代血統）
    pedigree = horse_data.get("pedigree", {})
    if isinstance(pedigree, dict):
        sire = pedigree.get("sire", "不明")
        dam = pedigree.get("dam", "不明")
        sire_sire = pedigree.get("sire_sire", "不明")
        sire_dam = pedigree.get("sire_dam", "不明")
        dam_sire = pedigree.get("dam_sire", "不明")
        dam_dam = pedigree.get("dam_dam", "不明")

        embed.add_field(
            name="🧬 血統情報",
            value=(
                f"父: **{sire}** ({sire_sire} × {sire_dam})\n"
                f"母: **{dam}** ({dam_sire} × {dam_dam})"
            ),
            inline=False
        )
    else:
        # フォールバック（pedigreeオブジェクトがない場合）
        sire = horse_data.get("sire", "不明")
        dam = horse_data.get("dam", "不明")
        embed.add_field(
            name="🧬 血統情報",
            value=f"父: {sire}\n母: {dam}",
            inline=False
        )

    # 近走5走
    recent_races = horse_data.get("recent_races", [])[:5]
    if recent_races:
        race_text = ""
        for race in recent_races:
            race_name = race.get("race_name", "不明")[:10]  # 長すぎる場合は短縮
            finish = race.get("finish_position", "?")
            distance = race.get("distance", "?")
            time = race.get("time", "?")
            time_diff = race.get("time_diff")
            winner_name = race.get("winner_name")
            weight = race.get("weight", 0)  # 斤量
            jockey = race.get("jockey", "不明")[:6]  # 騎手名（短縮）

            # タイム差と勝ち馬を表示（1着以外の場合）
            diff_str = ""
            if finish != 1:
                # タイム差
                if time_diff:
                    try:
                        diff_val = float(time_diff)
                        diff_str = f" +{diff_val:.1f}秒"
                    except (ValueError, TypeError):
                        pass

                # 勝ち馬名
                if winner_name:
                    winner_short = winner_name[:8]  # 8文字まで
                    diff_str += f" (1着:{winner_short})"

            # 斤量と騎手を追加
            weight_str = f" {jockey}({weight:.0f}kg)" if weight > 0 else ""

            # 調教データを追加
            training = race.get("training")
            training_str = ""
            if training:
                training_type = training.get("training_type", "")[:2]  # 坂路/ウッド
                time_4f = training.get("time_4f")
                if time_4f and len(time_4f) >= 3:
                    # タイムを秒に変換（例: 523 → 52.3秒）
                    time_sec = int(time_4f) / 10.0
                    training_str = f" [{training_type}{time_sec:.1f}]"

            race_text += f"{finish}着 {race_name} {distance}m ({time}){diff_str}{weight_str}{training_str}\n"

        embed.add_field(
            name="📅 近走5走",
            value=race_text or "データなし",
            inline=False
        )

    # 調教データ（近日中に実装予定のプレースホルダー）
    embed.add_field(
        name="🏃 調教データ",
        value="準備中（坂路・ウッドチップの調教タイム）",
        inline=False
    )

    return embed


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
                    await interaction.followup.send("今後のレースは未登録です。", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"レース一覧取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"今後のレース一覧エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="race", description="レースの出馬表を表示します（インタラクティブ）")
    @app_commands.describe(
        query="レース指定（例: 京都2r, 2025-12-28, 有馬記念, レースID）"
    )
    async def race(self, interaction: discord.Interaction, query: str):
        """レース詳細（インタラクティブ出馬表）"""
        await interaction.response.defer(ephemeral=True)

        try:
            # レース指定をレースIDに解決
            resolved_id = resolve_race_input(query, self.api_base_url)

            response = requests.get(
                f"{self.api_base_url}/api/races/{resolved_id}",
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()

                # レース情報のEmbedを作成
                race_name = data.get("race_name", "不明")
                venue = data.get("venue", "不明")
                race_num = data.get("race_number", "?R")
                race_time = data.get("race_time", "?")
                track = "芝" if data.get("track_code", "").startswith("1") else "ダート"
                distance = data.get("distance", "?")
                grade_code = data.get("grade")
                grade = f" [{grade_code}]" if grade_code else ""

                # 過去レースかチェック
                is_past_race = data.get("results") is not None

                if is_past_race:
                    # 過去レース：結果表示
                    embed = discord.Embed(
                        title=f"🏆 {race_name}{grade} [終了]",
                        description=f"{venue} {race_num} {race_time} | {track}{distance}m",
                        color=discord.Color.blue()
                    )

                    # レース結果（上位5着）
                    results = data.get("results", [])[:5]
                    if results:
                        result_text = ""
                        for r in results:
                            pos = r['finish_position']
                            num = r['horse_number']
                            name = r['horse_name']
                            time = r['finish_time']
                            kohan_3f = r.get('kohan_3f')

                            # タイムを秒に変換して表示
                            if time and len(time) >= 3:
                                minutes = int(time[:-2]) if len(time) > 2 else 0
                                seconds = int(time[-2:]) if len(time) >= 2 else 0
                                time_str = f"{minutes}:{seconds:02d}.{time[-1] if len(time) > 3 else '0'}"
                            else:
                                time_str = time

                            # 上がり3Fを秒に変換
                            agari_str = ""
                            if kohan_3f and len(kohan_3f) >= 3:
                                agari_sec = int(kohan_3f) / 10.0
                                agari_str = f" (上り{agari_sec:.1f})"

                            result_text += f"{pos}着: {num}番 {name} {time_str}{agari_str}\n"
                        embed.add_field(name="🏁 レース結果", value=result_text, inline=False)

                    # 払戻金
                    payoffs = data.get("payoffs", {})
                    if payoffs:
                        payoff_text = ""
                        if payoffs.get("win"):
                            win = payoffs['win']
                            payoff_text += f"単勝: {win['kumi']}番 {win['payoff']:,}円\n"
                        if payoffs.get("place"):
                            places = payoffs['place']
                            place_str = " / ".join([f"{p['kumi']}番 {p['payoff']:,}円" for p in places])
                            payoff_text += f"複勝: {place_str}\n"
                        if payoffs.get("quinella"):
                            q = payoffs['quinella']
                            payoff_text += f"馬連: {q['kumi']} {q['payoff']:,}円\n"
                        if payoffs.get("exacta"):
                            e = payoffs['exacta']
                            payoff_text += f"馬単: {e['kumi']} {e['payoff']:,}円\n"
                        if payoffs.get("wide"):
                            wides = payoffs['wide']
                            wide_str = " / ".join([f"{w['kumi']} {w['payoff']:,}円" for w in wides])
                            payoff_text += f"ワイド: {wide_str}\n"
                        if payoffs.get("trio"):
                            t = payoffs['trio']
                            payoff_text += f"3連複: {t['kumi']} {t['payoff']:,}円\n"
                        if payoffs.get("trifecta"):
                            tf = payoffs['trifecta']
                            payoff_text += f"3連単: {tf['kumi']} {tf['payoff']:,}円\n"

                        if payoff_text:
                            embed.add_field(name="💰 払戻金", value=payoff_text, inline=False)

                    # ラップタイム
                    lap_times = data.get("lap_times", [])
                    if lap_times:
                        # 200m毎のラップを秒に変換して表示
                        lap_str = " - ".join([f"{int(lap)/10:.1f}" for lap in lap_times[:10]])  # 最初の10ラップのみ
                        if len(lap_times) > 10:
                            lap_str += " ..."
                        embed.add_field(name="⏱️ ラップタイム (200m毎)", value=lap_str, inline=False)

                    embed.set_footer(text=f"レースID: {resolved_id}")

                    # インタラクティブ出馬表ビューも作成（馬詳細確認用）
                    view = RaceCardView(data, self.api_base_url)

                    await interaction.followup.send(
                        embed=embed,
                        view=view,
                        ephemeral=True
                    )
                else:
                    # 未来レース：コンパクト表形式の出馬表
                    embed = discord.Embed(
                        title=f"🏇 {race_name}{grade}",
                        description=f"{venue} {race_num} {race_time} | {track}{distance}m",
                        color=discord.Color.gold()
                    )

                    # 賞金情報
                    prize = data.get("prize_money", {})
                    if isinstance(prize, dict):
                        prize_text = f"1着: {prize.get('first', 0):,}万円"
                        embed.add_field(name="💰 賞金", value=prize_text, inline=False)

                    # 出馬表をコンパクトな表形式で作成
                    entries = data.get("entries", [])
                    if entries:
                        # ヘッダー
                        table_text = "```\n"
                        table_text += "馬番 馬名              騎手         斤量  オッズ\n"
                        table_text += "─────────────────────────────────────────\n"

                        # 各馬の情報
                        for entry in entries[:16]:  # 最大16頭まで
                            num = entry.get('horse_number', 0)
                            name = entry.get('horse_name', '不明')[:10]  # 10文字まで
                            jockey = entry.get('jockey_name', '不明')[:8]  # 8文字まで
                            weight = entry.get('weight', 0)
                            odds = entry.get('odds', 0)

                            # 等幅フォントで整形
                            table_text += f"{num:>3} {name:<10} {jockey:<8} {weight:>5.1f} {odds:>6.1f}\n"

                        table_text += "```"
                        embed.add_field(name="📋 出馬表", value=table_text, inline=False)

                    embed.set_footer(text=f"レースID: {resolved_id}")

                    # インタラクティブ出馬表ビュー（血統・調教データ表示用）
                    view = RaceCardView(data, self.api_base_url)

                    await interaction.followup.send(
                        embed=embed,
                        view=view,
                        ephemeral=True
                    )
            elif response.status_code == 404:
                await interaction.followup.send(f"レースが見つかりません: {query}", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"レース詳細取得エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except MultipleRacesFoundException as e:
            # 複数レースが見つかった場合は選択メニューを表示
            logger.info(f"複数レース発見: {len(e.races)}件 - {query}")
            view = RaceSelectView(e.races, self.api_base_url)
            await interaction.followup.send(
                f"🔍 '{query}' の検索結果: **{len(e.races)}件**\n下のメニューからレースを選択してください",
                view=view,
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

    @app_commands.command(name="jockey", description="騎手の詳細成績を表示します")
    @app_commands.describe(name="騎手名")
    async def jockey(self, interaction: discord.Interaction, name: str):
        """騎手の詳細成績照会"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 騎手検索
            response = requests.get(
                f"{self.api_base_url}/api/jockeys/search",
                params={"name": name, "limit": 10},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if not data:
                    await interaction.followup.send(
                        f"「{name}」は見つかりませんでした",
                        ephemeral=True
                    )
                    return

                # 最初の騎手の詳細を取得
                jockey_code = data[0]["kishu_code"]
                detail_response = requests.get(
                    f"{self.api_base_url}/api/jockeys/{jockey_code}",
                    timeout=DISCORD_REQUEST_TIMEOUT,
                )

                if detail_response.status_code == 200:
                    stats = detail_response.json()
                    basic = stats["basic_info"]
                    overall = stats["overall_stats"]
                    surface = stats["surface_stats"]
                    distance_stats = stats["distance_stats"]
                    venue_stats = stats["venue_stats"]

                    embed = discord.Embed(
                        title=f"🏇 {basic['name']} ({basic['affiliation']})",
                        color=discord.Color.green()
                    )

                    # 通算成績
                    embed.add_field(
                        name="📊 通算成績",
                        value=(
                            f"{overall['wins']:,}勝 / {overall['total_races']:,}戦\n"
                            f"勝率: {overall['win_rate']:.1%}\n"
                            f"連対率: {overall['top2_rate']:.1%}\n"
                            f"複勝率: {overall['top3_rate']:.1%}"
                        ),
                        inline=True
                    )

                    # 芝/ダート
                    embed.add_field(
                        name="🌱/🏜️ 芝/ダート",
                        value=(
                            f"芝: {surface['turf_wins']:,}/{surface['turf_races']:,} ({surface['turf_win_rate']:.1%})\n"
                            f"ダ: {surface['dirt_wins']:,}/{surface['dirt_races']:,} ({surface['dirt_win_rate']:.1%})"
                        ),
                        inline=True
                    )

                    # 距離別
                    if distance_stats:
                        dist_text = "\n".join([
                            f"{d['category'][:8]}: {d['win_rate']:.1%}"
                            for d in distance_stats
                        ])
                        embed.add_field(
                            name="📏 距離別勝率",
                            value=dist_text,
                            inline=False
                        )

                    # 得意競馬場
                    if venue_stats:
                        venue_text = "\n".join([
                            f"{v['venue']}: {v['wins']:,}/{v['races']:,} ({v['win_rate']:.1%})"
                            for v in venue_stats[:3]
                        ])
                        embed.add_field(
                            name="🏟️ 得意競馬場 TOP3",
                            value=venue_text,
                            inline=False
                        )

                    embed.set_footer(text=f"騎手コード: {jockey_code}")

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        f"詳細取得エラー (Status: {detail_response.status_code})",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    f"検索エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"騎手検索エラー: {e}", exc_info=True)
            await interaction.followup.send(f"エラー: {str(e)}", ephemeral=True)

    @app_commands.command(name="trainer", description="調教師の詳細成績を表示します")
    @app_commands.describe(name="調教師名")
    async def trainer(self, interaction: discord.Interaction, name: str):
        """調教師の詳細成績照会"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 調教師検索
            response = requests.get(
                f"{self.api_base_url}/api/trainers/search",
                params={"name": name, "limit": 10},
                timeout=DISCORD_REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if not data:
                    await interaction.followup.send(
                        f"「{name}」は見つかりませんでした",
                        ephemeral=True
                    )
                    return

                # 最初の調教師の詳細を取得
                trainer_code = data[0]["chokyoshi_code"]
                detail_response = requests.get(
                    f"{self.api_base_url}/api/trainers/{trainer_code}",
                    timeout=DISCORD_REQUEST_TIMEOUT,
                )

                if detail_response.status_code == 200:
                    stats = detail_response.json()
                    basic = stats["basic_info"]
                    overall = stats["overall_stats"]
                    surface = stats["surface_stats"]
                    distance_stats = stats["distance_stats"]
                    venue_stats = stats["venue_stats"]
                    top_jockeys = stats["top_jockeys"]

                    embed = discord.Embed(
                        title=f"👔 {basic['name']} ({basic['affiliation']})",
                        color=discord.Color.blue()
                    )

                    # 通算成績
                    embed.add_field(
                        name="📊 通算成績",
                        value=(
                            f"{overall['wins']:,}勝 / {overall['total_races']:,}戦\n"
                            f"勝率: {overall['win_rate']:.1%}\n"
                            f"連対率: {overall['top2_rate']:.1%}\n"
                            f"複勝率: {overall['top3_rate']:.1%}"
                        ),
                        inline=True
                    )

                    # 芝/ダート
                    embed.add_field(
                        name="🌱/🏜️ 芝/ダート",
                        value=(
                            f"芝: {surface['turf_wins']:,}/{surface['turf_races']:,} ({surface['turf_win_rate']:.1%})\n"
                            f"ダ: {surface['dirt_wins']:,}/{surface['dirt_races']:,} ({surface['dirt_win_rate']:.1%})"
                        ),
                        inline=True
                    )

                    # 主戦騎手
                    if top_jockeys:
                        jockey_text = "\n".join([
                            f"{j['jockey_name'][:8]}: {j['wins']:,}/{j['rides']:,} ({j['win_rate']:.1%})"
                            for j in top_jockeys[:3]
                        ])
                        embed.add_field(
                            name="🏇 主戦騎手 TOP3",
                            value=jockey_text,
                            inline=False
                        )

                    # 得意競馬場
                    if venue_stats:
                        venue_text = "\n".join([
                            f"{v['venue']}: {v['wins']:,}/{v['races']:,} ({v['win_rate']:.1%})"
                            for v in venue_stats[:3]
                        ])
                        embed.add_field(
                            name="🏟️ 得意競馬場 TOP3",
                            value=venue_text,
                            inline=False
                        )

                    embed.set_footer(text=f"調教師コード: {trainer_code}")

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        f"詳細取得エラー (Status: {detail_response.status_code})",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    f"検索エラー (Status: {response.status_code})",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"調教師検索エラー: {e}", exc_info=True)
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
