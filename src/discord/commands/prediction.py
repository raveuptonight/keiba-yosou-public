"""
Discord Bot 予想関連コマンド

!predict, !today コマンドを提供
APIを呼び出してML予測結果を取得・表示
"""

import os
import logging
from datetime import date
from typing import Dict, Any, List, Optional
import requests
from discord.ext import commands

from src.db.connection import get_db
from src.discord.formatters import format_ml_prediction, format_race_list
from src.discord.decorators import handle_api_errors, log_command_execution

logger = logging.getLogger(__name__)

# API設定
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
API_TIMEOUT = 120  # 予測に時間がかかる場合があるため長めに設定


class PredictionCommands(commands.Cog):
    """
    予想関連コマンド

    !predict, !today コマンドを提供します。
    APIを呼び出してML予測結果を取得・表示します。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        logger.info("PredictionCommands初期化完了")

    def _resolve_race_code(self, race_spec: str) -> Optional[str]:
        """レース指定をレースコードに解決"""
        # 数字のみの場合はレースコードとして扱う
        if race_spec.isdigit() and len(race_spec) >= 10:
            return race_spec

        # 競馬場名+レース番号形式（例: 京都2r, 中山11R）
        import re
        match = re.match(r'(.+?)(\d+)[rR]?', race_spec)
        if not match:
            return None

        venue_name = match.group(1)
        race_num = int(match.group(2))

        venue_code_map = {
            '札幌': '01', '函館': '02', '福島': '03', '新潟': '04',
            '東京': '05', '中山': '06', '中京': '07', '京都': '08',
            '阪神': '09', '小倉': '10'
        }
        venue_code = venue_code_map.get(venue_name)
        if not venue_code:
            return None

        # 本日の日付で検索
        today = date.today()
        year = today.year

        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            # 本日または直近のレースを検索
            cur.execute("""
                SELECT race_code FROM race_shosai
                WHERE keibajo_code = %s
                  AND kaisai_nen = %s
                  AND race_code LIKE %s
                ORDER BY race_code DESC
                LIMIT 1
            """, (venue_code, str(year), f'%{race_num:02d}'))
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            conn.close()

    def _get_race_info(self, race_code: str) -> Dict[str, Any]:
        """レース情報を取得"""
        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT kyosomei_hondai, keibajo_code, kaisai_gappi
                FROM race_shosai
                WHERE race_code = %s
            """, (race_code,))
            row = cur.fetchone()
            cur.close()

            if row:
                keibajo_map = {
                    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
                    '05': '東京', '06': '中山', '07': '中京', '08': '京都',
                    '09': '阪神', '10': '小倉'
                }
                race_num = race_code[-2:]
                return {
                    'race_name': row[0].strip() if row[0] else f'{race_num}R',
                    'venue': keibajo_map.get(row[1], '不明'),
                    'kaisai_gappi': row[2],
                    'race_number': f'{int(race_num)}R'
                }
            return {
                'race_name': '不明',
                'kaisai_gappi': None,
                'venue': '不明',
                'race_number': '??R'
            }
        finally:
            conn.close()

    def _get_race_horses_info(self, race_code: str) -> List[Dict]:
        """レースの出走馬基本情報を取得"""
        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT umaban, bamei
                FROM race_uma
                WHERE race_code = %s
                ORDER BY umaban::int
            """, (race_code,))
            rows = cur.fetchall()
            cur.close()
            return [
                {'umaban': int(r[0]), 'bamei': r[1].strip() if r[1] else '不明'}
                for r in rows
            ]
        except Exception as e:
            logger.error(f"馬情報取得エラー: {e}")
            return []
        finally:
            conn.close()

    @commands.command(name="predict")
    @handle_api_errors
    @log_command_execution
    async def predict_race(
        self,
        ctx: commands.Context,
        race_spec: str
    ):
        """
        予想実行コマンド

        APIを呼び出してML予測結果を取得・表示

        Args:
            ctx: コマンドコンテキスト
            race_spec: レース指定（京都2r または 202412280506形式）

        使用例:
            !predict 京都2r
            !predict 中山11R
            !predict 202501050811
        """
        await ctx.send(f"🔄 予想を実行中... ({race_spec})")

        try:
            # レースコードを解決
            race_code = self._resolve_race_code(race_spec)
            if not race_code:
                race_code = race_spec

            # レース情報を取得
            race_info = self._get_race_info(race_code)
            race_name = race_info['race_name']

            # 馬情報を取得（表示用）
            horses_info = self._get_race_horses_info(race_code)
            if not horses_info:
                await ctx.send(f"❌ レースコード {race_code} の出走馬情報が見つかりません。")
                return

            # API呼び出しで予測実行
            await ctx.send(f"📊 APIで予測を実行中...")

            response = requests.post(
                f"{API_BASE_URL}/api/predictions/generate",
                json={"race_id": race_code, "is_final": False},
                timeout=API_TIMEOUT
            )

            if response.status_code != 200:
                error_detail = response.json().get('detail', {})
                error_msg = error_detail.get('message', str(response.text))
                await ctx.send(f"❌ 予測エラー: {error_msg}")
                return

            prediction = response.json()
            pred_result = prediction.get('prediction_result', {})
            ranked_horses = pred_result.get('ranked_horses', [])
            pred_confidence = pred_result.get('prediction_confidence', 0)
            model_info = pred_result.get('model_info', 'unknown')

            # 予測結果をフォーマット（確率ベース・ランキング形式）
            lines = [
                f"🏇 **{race_info['venue']} {race_info['race_number']}** {race_name}",
                f"📊 予測信頼度: {pred_confidence:.1%} | モデル: {model_info}",
                ""
            ]

            # 全馬ランキング
            marks = ['◎', '○', '▲', '△', '△', '×', '×', '☆', '☆', '☆']
            lines.append("**予測ランキング**")
            for h in ranked_horses:
                rank = h.get('rank', 0)
                num = h.get('horse_number', '?')
                name = h.get('horse_name', '不明')
                win_prob = h.get('win_probability', 0)
                place_prob = h.get('place_probability', 0)
                mark = marks[rank - 1] if rank <= len(marks) else '消'
                lines.append(
                    f"{mark} {rank}位 {num}番 {name} "
                    f"(勝率{win_prob:.1%} 複勝{place_prob:.1%})"
                )

            # 順位分布（上位3頭のみ詳細表示）
            if ranked_horses:
                lines.append("")
                lines.append("**順位分布（上位3頭）**")
                for h in ranked_horses[:3]:
                    num = h.get('horse_number', '?')
                    name = h.get('horse_name', '不明')
                    pos_dist = h.get('position_distribution', {})
                    lines.append(
                        f"  {num}番 {name}: "
                        f"1着{pos_dist.get('first', 0):.1%} "
                        f"2着{pos_dist.get('second', 0):.1%} "
                        f"3着{pos_dist.get('third', 0):.1%}"
                    )

            message = "\n".join(lines)
            await ctx.send(message)
            logger.info(f"予想コマンド完了: race_code={race_code}")

        except requests.Timeout:
            await ctx.send("❌ APIタイムアウト: 予測に時間がかかりすぎています")
        except requests.RequestException as e:
            logger.exception(f"API通信エラー: {e}")
            await ctx.send(f"❌ API通信エラー: {str(e)}")
        except Exception as e:
            logger.exception(f"予想エラー: {e}")
            await ctx.send(f"❌ 予想中にエラーが発生しました: {str(e)}")

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
        db = get_db()
        conn = db.get_connection()
        try:
            today = date.today()
            cur = conn.cursor()
            cur.execute("""
                SELECT rs.race_code, rs.kyosomei_hondai, rs.keibajo_code
                FROM race_shosai rs
                WHERE rs.kaisai_gappi = %s
                  AND rs.data_kubun = '7'
                ORDER BY rs.race_code
            """, (today.strftime('%m%d'),))
            rows = cur.fetchall()
            cur.close()

            keibajo_map = {
                '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
                '05': '東京', '06': '中山', '07': '中京', '08': '京都',
                '09': '阪神', '10': '小倉'
            }

            if not rows:
                await ctx.send(f"📅 本日 ({today.strftime('%Y/%m/%d')}) のレースはありません。")
                return

            races = []
            for row in rows:
                race_code = row[0]
                race_name = row[1].strip() if row[1] else f'{race_code[-2:]}R'
                venue = keibajo_map.get(row[2], '不明')
                race_num = int(race_code[-2:])
                races.append({
                    'race_code': race_code,
                    'race_name': race_name,
                    'venue': venue,
                    'race_number': f'{race_num}R'
                })

            message = format_race_list(races)
            await ctx.send(message)

        finally:
            conn.close()


async def setup(bot: commands.Bot):
    """Cogをボットに登録"""
    await bot.add_cog(PredictionCommands(bot))
    logger.info("PredictionCommands登録完了")
