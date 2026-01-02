"""
Discord Bot 予想関連コマンド

!predict, !today コマンドを提供
MLモデルによる確率・ランキング・順位分布・信頼度を出力
"""

import os
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import joblib
from discord.ext import commands

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor
from src.discord.formatters import format_ml_prediction, format_race_list
from src.discord.decorators import handle_api_errors, log_command_execution

logger = logging.getLogger(__name__)


class PredictionCommands(commands.Cog):
    """
    予想関連コマンド

    !predict, !today コマンドを提供します。
    MLモデルによる確率・ランキング・順位分布・信頼度を出力。
    """

    def __init__(self, bot: commands.Bot):
        """
        Args:
            bot: Discordボットインスタンス
        """
        self.bot = bot
        self.xgb_model = None
        self.lgb_model = None
        self.feature_names = []
        self.is_ensemble = False
        self._cache = {}  # 年ごとのデータキャッシュ
        self._load_model()
        logger.info("PredictionCommands初期化完了")

    def _load_model(self):
        """最新のモデルをロード"""
        try:
            models_dir = Path("models")
            if not models_dir.exists():
                logger.warning("modelsディレクトリが存在しません")
                return

            # アンサンブルモデルを優先して探す
            ensemble_models = list(models_dir.glob("ensemble_model_*.pkl"))
            single_models = list(models_dir.glob("fast_model_*.pkl"))

            if ensemble_models:
                model_path = sorted(ensemble_models)[-1]
                self.is_ensemble = True
            elif single_models:
                model_path = sorted(single_models)[-1]
                self.is_ensemble = False
            else:
                logger.warning("モデルファイルが見つかりません")
                return

            model_data = joblib.load(model_path)

            if self.is_ensemble and 'models' in model_data:
                models = model_data['models']
                self.xgb_model = models.get('xgboost')
                self.lgb_model = models.get('lightgbm')
            else:
                self.xgb_model = model_data.get('model')
                self.lgb_model = None

            self.feature_names = model_data.get('feature_names', [])
            logger.info(f"モデルロード完了: {model_path} (ensemble={self.is_ensemble}, features={len(self.feature_names)})")

        except Exception as e:
            logger.error(f"モデルロードエラー: {e}")

    def _predict_scores(self, X: np.ndarray) -> np.ndarray:
        """モデルで予測スコアを計算"""
        if self.is_ensemble and self.lgb_model is not None:
            xgb_pred = self.xgb_model.predict(X)
            lgb_pred = self.lgb_model.predict(X)
            return (xgb_pred + lgb_pred) / 2
        else:
            return self.xgb_model.predict(X)

    def _get_year_data(self, year: int) -> pd.DataFrame:
        """指定年のデータを取得（キャッシュ付き）"""
        if year in self._cache:
            return self._cache[year]

        db = get_db()
        conn = db.get_connection()

        try:
            if self.is_ensemble:
                from src.models.advanced_train import AdvancedFeatureExtractor
                extractor = AdvancedFeatureExtractor(conn)
                df = extractor.extract_year_data_advanced(year, max_races=10000)
            else:
                extractor = FastFeatureExtractor(conn)
                df = extractor.extract_year_data(year, max_races=10000)

            self._cache[year] = df
            return df
        finally:
            conn.close()

    def _get_race_info(self, race_code: str) -> Dict[str, Any]:
        """レース情報を取得"""
        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT hondai, kaisai_gappi, keibajo_code
                FROM race_shosai rs
                LEFT JOIN race_info ri ON rs.race_code = ri.race_code
                WHERE rs.race_code = %s
                LIMIT 1
            """, (race_code,))
            row = cur.fetchone()
            cur.close()

            if row:
                keibajo_map = {
                    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
                    '05': '東京', '06': '中山', '07': '中京', '08': '京都',
                    '09': '阪神', '10': '小倉'
                }
                keibajo = keibajo_map.get(row[2], '不明') if row[2] else '不明'
                race_num = race_code[-2:] if len(race_code) >= 2 else '??'

                return {
                    'race_name': row[0].strip() if row[0] else f"レース{race_code}",
                    'kaisai_gappi': row[1],
                    'venue': keibajo,
                    'race_number': f"{int(race_num)}R"
                }
            return {
                'race_name': f"レース{race_code}",
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

        MLモデルによる確率・ランキング・順位分布・信頼度を出力

        Args:
            ctx: コマンドコンテキスト
            race_spec: レース指定（京都2r または 202412280506形式）

        使用例:
            !predict 京都2r
            !predict 中山11R
            !predict 202501050811
        """
        if not self.xgb_model:
            await ctx.send("❌ モデルがロードされていません。")
            return

        await ctx.send(f"🔄 予想を実行中... ({race_spec})")

        try:
            # レースコードを解決
            race_code = self._resolve_race_code(race_spec)
            if not race_code:
                # 直接レースコードとして試す
                race_code = race_spec

            # 年度を取得
            year = int(race_code[:4])

            # レース情報を取得
            race_info = self._get_race_info(race_code)
            race_name = race_info['race_name']

            # 馬情報を取得
            horses_info = self._get_race_horses_info(race_code)
            if not horses_info:
                await ctx.send(f"❌ レースコード {race_code} の出走馬情報が見つかりません。")
                return

            # 年間データを取得
            await ctx.send(f"📊 {year}年のデータを準備中...")
            df = self._get_year_data(year)

            if len(df) == 0:
                await ctx.send(f"❌ {year}年のデータが取得できませんでした。")
                return

            # レースコードでフィルタ
            race_df = df[df['race_code'] == race_code].copy()

            if len(race_df) == 0:
                await ctx.send(f"❌ レースコード {race_code} のデータが見つかりません。")
                return

            # 特徴量で予測
            X = race_df[self.feature_names].fillna(0)
            scores = self._predict_scores(X.values)

            # 馬番リストを取得
            horse_numbers = race_df['umaban'].astype(int).tolist()

            # 馬名をマッピング
            horse_name_map = {h['umaban']: h['bamei'] for h in horses_info}
            horse_names = [horse_name_map.get(n, f'馬{n}') for n in horse_numbers]

            # Discord用にフォーマット
            message = format_ml_prediction(
                race_code=race_code,
                race_name=race_name,
                horse_numbers=horse_numbers,
                horse_names=horse_names,
                model_scores=scores
            )

            await ctx.send(message)
            logger.info(f"予想コマンド完了: race_code={race_code}, horses={len(horse_numbers)}")

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
                SELECT rs.race_code, ri.hondai, rs.keibajo_code
                FROM race_shosai rs
                LEFT JOIN race_info ri ON rs.race_code = ri.race_code
                WHERE rs.kaisai_gappi = %s
                  AND rs.data_kubun = '7'
                ORDER BY rs.race_code
            """, (today.strftime('%Y%m%d'),))
            rows = cur.fetchall()
            cur.close()

            keibajo_map = {
                '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
                '05': '東京', '06': '中山', '07': '中京', '08': '京都',
                '09': '阪神', '10': '小倉'
            }

            races = []
            for row in rows:
                race_code = row[0]
                race_name = row[1].strip() if row[1] else 'レース名不明'
                venue = keibajo_map.get(row[2], '不明') if row[2] else '不明'
                race_num = int(race_code[-2:]) if len(race_code) >= 2 else 0

                races.append({
                    "race_id": race_code,
                    "race_name": race_name,
                    "venue": venue,
                    "race_number": f"{race_num}R",
                    "race_time": "",
                })

            if not races:
                await ctx.send(f"📅 本日({today})のレースはありません。")
                return

            message = format_race_list(races)
            await ctx.send(message)

        except Exception as e:
            logger.exception(f"レース一覧取得エラー: {e}")
            await ctx.send(f"❌ レース一覧取得中にエラーが発生しました: {str(e)}")
        finally:
            conn.close()

    @commands.command(name="model-reload")
    @commands.has_permissions(administrator=True)
    async def reload_model(self, ctx: commands.Context):
        """
        モデルを再ロード（管理者のみ）
        """
        self._load_model()
        self._cache.clear()
        if self.xgb_model:
            await ctx.send(f"✅ モデルを再ロードしました。(ensemble={self.is_ensemble}, features={len(self.feature_names)})")
        else:
            await ctx.send("❌ モデルのロードに失敗しました。")


async def setup(bot: commands.Bot):
    """
    PredictionCommandsをBotに登録

    Args:
        bot: Discordボットインスタンス
    """
    await bot.add_cog(PredictionCommands(bot))
    logger.info("PredictionCommands登録完了")
