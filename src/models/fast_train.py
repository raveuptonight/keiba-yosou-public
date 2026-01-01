"""
高速学習スクリプト

DBクエリをバッチ化して大量データを効率的に処理
- レース単位でまとめてデータ取得
- 年単位でバッチ処理
- GPU対応XGBoost学習
"""

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import xgboost as xgb
import joblib

from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FastFeatureExtractor:
    """高速バッチ特徴量抽出"""

    def __init__(self, conn):
        self.conn = conn
        self._jockey_cache = {}
        self._trainer_cache = {}

    def extract_year_data(self, year: int, max_races: int = 5000) -> pd.DataFrame:
        """
        1年分のデータをバッチで取得

        Args:
            year: 対象年
            max_races: 最大レース数

        Returns:
            特徴量DataFrame（着順含む）
        """
        logger.info(f"{year}年のデータを取得中...")

        # 1. レース一覧を取得
        races = self._get_races(year, max_races)
        logger.info(f"  対象レース数: {len(races)}")

        if not races:
            return pd.DataFrame()

        race_codes = [r['race_code'] for r in races]

        # 2. 出走馬データを一括取得
        entries = self._get_all_entries(race_codes)
        logger.info(f"  出走馬数: {len(entries)}")

        # 3. 過去成績を一括取得（直近10走）
        kettonums = list(set(e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')))
        past_stats = self._get_past_stats_batch(kettonums)
        logger.info(f"  過去成績取得: {len(past_stats)}頭")

        # 4. 騎手・調教師成績をキャッシュ
        self._cache_jockey_trainer_stats(year)

        # 5. 追加データをバッチ取得
        # 騎手・馬コンビ
        jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                    for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
        jockey_horse_stats = self._get_jockey_horse_combo_batch(jh_pairs)
        logger.info(f"  騎手・馬コンビ: {len(jockey_horse_stats)}件")

        # 芝/ダート成績
        surface_stats = self._get_surface_stats_batch(kettonums)
        logger.info(f"  芝/ダート成績: {len(surface_stats)}件")

        # 左右回り成績
        turn_stats = self._get_turn_rates_batch(kettonums)
        # past_statsにマージ
        for kettonum, stats in turn_stats.items():
            if kettonum in past_stats:
                past_stats[kettonum]['right_turn_rate'] = stats['right_turn_rate']
                past_stats[kettonum]['left_turn_rate'] = stats['left_turn_rate']

        # 調教データ
        training_stats = self._get_training_stats_batch(kettonums)
        logger.info(f"  調教データ: {len(training_stats)}件")

        # 馬場状態別成績
        baba_stats = self._get_baba_stats_batch(kettonums, races)
        logger.info(f"  馬場別成績: {len(baba_stats)}件")

        # 間隔カテゴリ別成績
        interval_stats = self._get_interval_stats_batch(kettonums)
        logger.info(f"  間隔別成績: {len(interval_stats)}件")

        # 6. レースごとにグループ化して展開予想を計算
        entries_by_race = {}
        for entry in entries:
            rc = entry['race_code']
            if rc not in entries_by_race:
                entries_by_race[rc] = []
            entries_by_race[rc].append(entry)

        pace_predictions = {}
        for rc, race_entries in entries_by_race.items():
            pace_predictions[rc] = self._calc_pace_prediction(race_entries, past_stats)

        # 7. 特徴量に変換
        features_list = []
        for entry in entries:
            features = self._build_features(
                entry, races, past_stats,
                jockey_horse_stats=jockey_horse_stats,
                distance_stats=surface_stats,
                baba_stats=baba_stats,
                training_stats=training_stats,
                interval_stats=interval_stats,
                pace_predictions=pace_predictions,
                entries_by_race=entries_by_race
            )
            if features:
                features_list.append(features)

        df = pd.DataFrame(features_list)
        logger.info(f"  特徴量生成完了: {len(df)}サンプル")

        return df

    def _get_races(self, year: int, max_races: int) -> List[Dict]:
        """レース一覧取得"""
        sql = """
            SELECT
                race_code, kaisai_nen, kaisai_gappi, keibajo_code,
                kyori, track_code, grade_code,
                shiba_babajotai_code, dirt_babajotai_code
            FROM race_shosai
            WHERE kaisai_nen = %s AND data_kubun = '7'
            ORDER BY race_code
            LIMIT %s
        """
        cur = self.conn.cursor()
        cur.execute(sql, (str(year), max_races))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        return [dict(zip(cols, row)) for row in rows]

    def _get_all_entries(self, race_codes: List[str]) -> List[Dict]:
        """出走馬データを一括取得"""
        if not race_codes:
            return []

        placeholders = ','.join(['%s'] * len(race_codes))
        sql = f"""
            SELECT
                race_code, umaban, wakuban, ketto_toroku_bango,
                seibetsu_code, barei, futan_juryo,
                blinker_shiyo_kubun, kishu_code, chokyoshi_code,
                bataiju, zogen_sa, kakutei_chakujun,
                soha_time, kohan_3f, kohan_4f,
                corner1_juni, corner2_juni, corner3_juni, corner4_juni
            FROM umagoto_race_joho
            WHERE race_code IN ({placeholders})
              AND data_kubun = '7'
            ORDER BY race_code, umaban::int
        """
        cur = self.conn.cursor()
        cur.execute(sql, race_codes)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        return [dict(zip(cols, row)) for row in rows]

    def _get_past_stats_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """過去成績をバッチで取得（改善版）"""
        if not kettonums:
            return {}

        # 各馬の直近10走の詳細統計を計算
        placeholders = ','.join(['%s'] * len(kettonums))
        sql = f"""
            WITH ranked AS (
                SELECT
                    ketto_toroku_bango,
                    kakutei_chakujun,
                    soha_time,
                    kohan_3f,
                    corner3_juni,
                    corner4_juni,
                    kishu_code,
                    kaisai_nen,
                    kaisai_gappi,
                    ROW_NUMBER() OVER (
                        PARTITION BY ketto_toroku_bango
                        ORDER BY race_code DESC
                    ) as rn
                FROM umagoto_race_joho
                WHERE ketto_toroku_bango IN ({placeholders})
                  AND data_kubun = '7'
                  AND kakutei_chakujun ~ '^[0-9]+$'
            )
            SELECT
                ketto_toroku_bango,
                COUNT(*) as race_count,
                AVG(CAST(kakutei_chakujun AS INTEGER)) as avg_rank,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as place_count,
                AVG(CAST(NULLIF(soha_time, '') AS INTEGER)) as avg_time,
                MIN(CAST(NULLIF(soha_time, '') AS INTEGER)) as best_time,
                MAX(CASE WHEN rn = 1 THEN CAST(NULLIF(soha_time, '') AS INTEGER) END) as recent_time,
                AVG(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as avg_last3f,
                MIN(CAST(NULLIF(kohan_3f, '') AS INTEGER)) as best_last3f,
                AVG(CAST(NULLIF(corner3_juni, '') AS INTEGER)) as avg_corner3,
                AVG(CAST(NULLIF(corner4_juni, '') AS INTEGER)) as avg_corner4,
                MIN(CAST(kakutei_chakujun AS INTEGER)) as best_finish,
                MAX(CASE WHEN rn = 1 THEN kishu_code END) as last_jockey,
                MAX(CASE WHEN rn = 1 THEN kaisai_nen || kaisai_gappi END) as last_race_date
            FROM ranked
            WHERE rn <= 10
            GROUP BY ketto_toroku_bango
        """
        cur = self.conn.cursor()
        cur.execute(sql, kettonums)
        rows = cur.fetchall()
        cur.close()

        result = {}
        for row in rows:
            kettonum = row[0]
            race_count = int(row[1] or 0)
            avg_time = float(row[5]) if row[5] else None
            best_time = float(row[6]) if row[6] else None
            recent_time = float(row[7]) if row[7] else None

            result[kettonum] = {
                'race_count': race_count,
                'avg_rank': float(row[2]) if row[2] else 8.0,
                'win_rate': int(row[3] or 0) / race_count if race_count > 0 else 0,
                'place_rate': int(row[4] or 0) / race_count if race_count > 0 else 0,
                'win_count': int(row[3] or 0),
                'avg_time': avg_time,
                'best_time': best_time,
                'recent_time': recent_time,
                'avg_last3f': float(row[8] or 350) / 10.0,
                'best_last3f': float(row[9] or 350) / 10.0 if row[9] else 35.0,
                'avg_corner3': float(row[10]) if row[10] else 8.0,
                'avg_corner4': float(row[11]) if row[11] else 8.0,
                'best_finish': int(row[12]) if row[12] else 10,
                'last_jockey': row[13],
                'last_race_date': row[14]
            }

        return result

    def _cache_jockey_trainer_stats(self, year: int):
        """騎手・調教師の成績をキャッシュ"""
        # 対象年の1年前までの成績を集計
        year_back = str(year - 1)

        # 騎手成績
        sql = """
            SELECT
                kishu_code,
                COUNT(*) as total,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE data_kubun = '7'
              AND kaisai_nen >= %s
              AND kaisai_nen < %s
              AND kakutei_chakujun ~ '^[0-9]+$'
            GROUP BY kishu_code
        """
        cur = self.conn.cursor()
        cur.execute(sql, (year_back, str(year)))
        for row in cur.fetchall():
            code, total, wins, places = row
            if code and total > 0:
                self._jockey_cache[code] = {
                    'win_rate': wins / total,
                    'place_rate': places / total
                }
        cur.close()

        # 調教師成績
        sql = """
            SELECT
                chokyoshi_code,
                COUNT(*) as total,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE data_kubun = '7'
              AND kaisai_nen >= %s
              AND kaisai_nen < %s
              AND kakutei_chakujun ~ '^[0-9]+$'
            GROUP BY chokyoshi_code
        """
        cur = self.conn.cursor()
        cur.execute(sql, (year_back, str(year)))
        for row in cur.fetchall():
            code, total, wins, places = row
            if code and total > 0:
                self._trainer_cache[code] = {
                    'win_rate': wins / total,
                    'place_rate': places / total
                }
        cur.close()

        logger.info(f"  騎手キャッシュ: {len(self._jockey_cache)}, 調教師キャッシュ: {len(self._trainer_cache)}")

    def _get_jockey_horse_combo_batch(self, pairs: List[Tuple[str, str]]) -> Dict[str, Dict]:
        """騎手・馬コンビの成績をバッチ取得"""
        if not pairs:
            return {}

        # クエリ用にデータを整理
        unique_pairs = list(set(pairs))
        if len(unique_pairs) == 0:
            return {}

        # 複数のOR条件でクエリ
        conditions = []
        params = []
        for jockey, kettonum in unique_pairs[:1000]:  # 最大1000ペア
            if jockey and kettonum:
                conditions.append("(kishu_code = %s AND ketto_toroku_bango = %s)")
                params.extend([jockey, kettonum])

        if not conditions:
            return {}

        sql = f"""
            SELECT
                kishu_code,
                ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins
            FROM umagoto_race_joho
            WHERE ({' OR '.join(conditions)})
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
            GROUP BY kishu_code, ketto_toroku_bango
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()

            result = {}
            for row in rows:
                key = f"{row[0]}_{row[1]}"
                result[key] = {'runs': int(row[2] or 0), 'wins': int(row[3] or 0)}
            return result
        except Exception as e:
            logger.debug(f"Jockey-horse combo batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_training_stats_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """調教データをバッチ取得（hanro_chokyo + woodchip_chokyo）"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))

        # 坂路調教データ
        sql_hanro = f"""
            SELECT
                ketto_toroku_bango,
                COUNT(*) as count,
                AVG(CAST(NULLIF(time_gokei_4furlong, '') AS INTEGER)) as avg_4f,
                AVG(CAST(NULLIF(time_gokei_3furlong, '') AS INTEGER)) as avg_3f,
                AVG(CAST(NULLIF(lap_time_1furlong, '') AS INTEGER)) as avg_1f
            FROM hanro_chokyo
            WHERE ketto_toroku_bango IN ({placeholders})
            GROUP BY ketto_toroku_bango
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql_hanro, kettonums)
            rows = cur.fetchall()

            for row in rows:
                kettonum = row[0]
                count = int(row[1] or 0)
                avg_4f = float(row[2]) / 10.0 if row[2] else 52.0
                avg_3f = float(row[3]) / 10.0 if row[3] else 38.0
                avg_1f = float(row[4]) / 10.0 if row[4] else 12.5

                # 調教スコア（4Fタイムから算出: 速いほど高スコア）
                # 基準: 52秒=50点, 1秒速いと+5点
                score = 50.0 + (52.0 - avg_4f) * 5.0
                score = max(30.0, min(80.0, score))

                result[kettonum] = {
                    'count': count,
                    'score': score,
                    'time_4f': avg_4f,
                    'time_3f': avg_3f,
                    'lap_1f': avg_1f,
                    'days_before': 7
                }

            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Training batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_surface_stats_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """芝/ダート別成績をバッチ取得"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))

        # 芝成績
        sql_turf = f"""
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '1%%'
            GROUP BY u.ketto_toroku_bango
        """
        # ダート成績
        sql_dirt = f"""
            SELECT
                u.ketto_toroku_bango,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND r.track_code LIKE '2%%'
            GROUP BY u.ketto_toroku_bango
        """
        result = {}
        try:
            cur = self.conn.cursor()

            # 芝
            cur.execute(sql_turf, kettonums)
            for row in cur.fetchall():
                kettonum = row[0]
                runs = int(row[1] or 0)
                wins = int(row[2] or 0)
                places = int(row[3] or 0)
                key = f"{kettonum}_turf"
                result[key] = {
                    'runs': runs,
                    'win_rate': wins / runs if runs > 0 else 0.0,
                    'place_rate': places / runs if runs > 0 else 0.0
                }

            # ダート
            cur.execute(sql_dirt, kettonums)
            for row in cur.fetchall():
                kettonum = row[0]
                runs = int(row[1] or 0)
                wins = int(row[2] or 0)
                places = int(row[3] or 0)
                key = f"{kettonum}_dirt"
                result[key] = {
                    'runs': runs,
                    'win_rate': wins / runs if runs > 0 else 0.0,
                    'place_rate': places / runs if runs > 0 else 0.0
                }

            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Surface stats batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_turn_rates_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """左右回り成績をバッチ取得"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))

        # 右回り: 札幌(01), 函館(02), 福島(03), 中山(06), 阪神(09), 小倉(10)
        # 左回り: 新潟(04), 東京(05), 中京(07), 京都(08)
        sql = f"""
            SELECT
                u.ketto_toroku_bango,
                r.keibajo_code,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
            WHERE u.ketto_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
            GROUP BY u.ketto_toroku_bango, r.keibajo_code
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, kettonums)
            rows = cur.fetchall()
            cur.close()

            right_courses = {'01', '02', '03', '06', '09', '10'}
            left_courses = {'04', '05', '07', '08'}

            # 集計
            horse_stats = {}
            for row in rows:
                kettonum, keibajo, runs, places = row
                if kettonum not in horse_stats:
                    horse_stats[kettonum] = {
                        'right_runs': 0, 'right_places': 0,
                        'left_runs': 0, 'left_places': 0
                    }
                if keibajo in right_courses:
                    horse_stats[kettonum]['right_runs'] += int(runs or 0)
                    horse_stats[kettonum]['right_places'] += int(places or 0)
                elif keibajo in left_courses:
                    horse_stats[kettonum]['left_runs'] += int(runs or 0)
                    horse_stats[kettonum]['left_places'] += int(places or 0)

            result = {}
            for kettonum, stats in horse_stats.items():
                r_runs = stats['right_runs']
                l_runs = stats['left_runs']
                result[kettonum] = {
                    'right_turn_rate': stats['right_places'] / r_runs if r_runs > 0 else 0.25,
                    'left_turn_rate': stats['left_places'] / l_runs if l_runs > 0 else 0.25
                }
            return result
        except Exception as e:
            logger.debug(f"Turn rates batch failed: {e}")
            self.conn.rollback()
            return {}

    def _build_features(
        self,
        entry: Dict,
        races: List[Dict],
        past_stats: Dict[str, Dict],
        jockey_horse_stats: Dict[str, Dict] = None,
        distance_stats: Dict[str, Dict] = None,
        baba_stats: Dict[str, Dict] = None,
        training_stats: Dict[str, Dict] = None,
        interval_stats: Dict[str, Dict] = None,
        pace_predictions: Dict[str, Dict] = None,
        entries_by_race: Dict[str, List[Dict]] = None
    ) -> Optional[Dict]:
        """特徴量を構築（改善版）"""
        # 着順がないレコードはスキップ
        chakujun_str = entry.get('kakutei_chakujun', '')
        if not chakujun_str or not chakujun_str.isdigit():
            return None

        chakujun = int(chakujun_str)
        if chakujun > 18:
            return None

        # レース情報を取得
        race_code = entry['race_code']
        race_info = next((r for r in races if r['race_code'] == race_code), {})

        kettonum = entry.get('ketto_toroku_bango', '')
        jockey_code = entry.get('kishu_code', '')
        past = past_stats.get(kettonum, {})

        features = {}

        # 基本情報
        features['umaban'] = self._safe_int(entry.get('umaban'), 0)
        features['wakuban'] = self._safe_int(entry.get('wakuban'), 0)
        features['age'] = self._safe_int(entry.get('barei'), 4)
        features['sex'] = self._encode_sex(entry.get('seibetsu_code', ''))
        features['kinryo'] = self._safe_float(entry.get('futan_juryo'), 550) / 10.0
        features['horse_weight'] = self._safe_int(entry.get('bataiju'), 480)
        features['weight_diff'] = self._safe_int(entry.get('zogen_sa'), 0)
        features['blinker'] = 1 if entry.get('blinker_shiyo_kubun') == '1' else 0

        # 過去成績（改善版）
        features['speed_index_avg'] = self._calc_speed_index(past.get('avg_time'))
        features['speed_index_max'] = self._calc_speed_index(past.get('best_time'))
        features['speed_index_recent'] = self._calc_speed_index(past.get('recent_time'))
        features['last3f_time_avg'] = past.get('avg_last3f', 35.0)
        features['last3f_rank_avg'] = 5.0  # デフォルト
        features['running_style'] = self._determine_style(past.get('avg_corner3', 8))
        features['position_avg_3f'] = past.get('avg_corner3', 8.0)
        features['position_avg_4f'] = past.get('avg_corner4', 8.0)
        features['win_rate'] = past.get('win_rate', 0.0)
        features['place_rate'] = past.get('place_rate', 0.0)
        features['win_count'] = past.get('win_count', 0)

        # 休養日数（改善版）
        features['days_since_last_race'] = self._calc_days_since_last(
            past.get('last_race_date'),
            race_info.get('kaisai_nen', ''),
            race_info.get('kaisai_gappi', '')
        )

        # 騎手・調教師
        jockey_stats = self._jockey_cache.get(jockey_code, {'win_rate': 0.08, 'place_rate': 0.25})
        features['jockey_win_rate'] = jockey_stats['win_rate']
        features['jockey_place_rate'] = jockey_stats['place_rate']

        trainer_code = entry.get('chokyoshi_code', '')
        trainer_stats = self._trainer_cache.get(trainer_code, {'win_rate': 0.08, 'place_rate': 0.25})
        features['trainer_win_rate'] = trainer_stats['win_rate']
        features['trainer_place_rate'] = trainer_stats['place_rate']

        # 騎手・馬コンビ成績（改善版）
        combo_key = f"{jockey_code}_{kettonum}"
        combo = jockey_horse_stats.get(combo_key, {}) if jockey_horse_stats else {}
        features['jockey_horse_runs'] = combo.get('runs', 0)
        features['jockey_horse_wins'] = combo.get('wins', 0)

        # 騎手乗り替わり判定（改善版）
        last_jockey = past.get('last_jockey', '')
        features['jockey_change'] = 1 if last_jockey and last_jockey != jockey_code else 0

        # 調教データ（改善版）
        train = training_stats.get(kettonum, {}) if training_stats else {}
        features['training_score'] = train.get('score', 50.0)
        features['training_time_4f'] = train.get('time_4f', 52.0)
        features['training_count'] = train.get('count', 0)
        features['distance_change'] = 0

        # コース情報
        track_code = race_info.get('track_code', '')
        features['is_turf'] = 1 if track_code.startswith('1') else 0

        # 芝/ダート別成績（改善版）
        turf_key = f"{kettonum}_turf"
        dirt_key = f"{kettonum}_dirt"
        if distance_stats:
            turf_stats = distance_stats.get(turf_key, {})
            dirt_stats = distance_stats.get(dirt_key, {})
            features['turf_win_rate'] = turf_stats.get('win_rate', past.get('win_rate', 0.0))
            features['dirt_win_rate'] = dirt_stats.get('win_rate', past.get('win_rate', 0.0))
        else:
            features['turf_win_rate'] = past.get('win_rate', 0.0)
            features['dirt_win_rate'] = past.get('win_rate', 0.0)

        features['class_change'] = 0
        features['avg_time_diff'] = (past.get('avg_rank', 8) - 1) * 0.2
        features['best_finish'] = past.get('best_finish', 10)
        features['course_fit_score'] = 0.5
        features['distance_fit_score'] = 0.5
        features['class_rank'] = self._determine_class(race_info.get('grade_code', ''))

        # 出走頭数（同じレースの馬数をカウント）
        features['field_size'] = 14  # 平均値として

        features['waku_bias'] = (features['wakuban'] - 4.5) * 0.02

        # 距離カテゴリ別成績（改善版）
        distance = self._safe_int(race_info.get('kyori'), 1600)
        dist_key = f"{kettonum}_{self._get_distance_category(distance)}"
        if distance_stats:
            d_stats = distance_stats.get(dist_key, {})
            features['distance_cat_win_rate'] = d_stats.get('win_rate', 0.0)
            features['distance_cat_place_rate'] = d_stats.get('place_rate', 0.0)
            features['distance_cat_runs'] = d_stats.get('runs', 0)
        else:
            features['distance_cat_win_rate'] = past.get('win_rate', 0.0)
            features['distance_cat_place_rate'] = past.get('place_rate', 0.0)
            features['distance_cat_runs'] = past.get('race_count', 0)

        # 馬場状態別成績（改善版）- 当日の馬場状態を考慮
        is_turf = track_code.startswith('1') if track_code else True
        baba_name = 'turf' if is_turf else 'dirt'
        baba_code = race_info.get('shiba_babajotai_code', '1') if is_turf else race_info.get('dirt_babajotai_code', '1')
        baba_suffix_map = {'1': 'ryo', '2': 'yayaomo', '3': 'omo', '4': 'furyo'}
        baba_suffix = baba_suffix_map.get(str(baba_code), 'ryo')
        baba_key = f"{kettonum}_{baba_name}_{baba_suffix}"

        if baba_stats and baba_key in baba_stats:
            b_stats = baba_stats.get(baba_key, {})
            features['baba_win_rate'] = b_stats.get('win_rate', 0.0)
            features['baba_place_rate'] = b_stats.get('place_rate', 0.0)
            features['baba_runs'] = b_stats.get('runs', 0)
        else:
            features['baba_win_rate'] = past.get('win_rate', 0.0)
            features['baba_place_rate'] = past.get('place_rate', 0.0)
            features['baba_runs'] = past.get('race_count', 0)

        # 馬場状態エンコーディング（1=良, 2=稍重, 3=重, 4=不良）
        features['baba_condition'] = self._safe_int(baba_code, 1)

        # 調教詳細
        features['training_time_3f'] = train.get('time_3f', 38.0)
        features['training_lap_1f'] = train.get('lap_1f', 12.5)
        features['training_days_before'] = train.get('days_before', 7)

        # コーナー別成績
        features['right_turn_rate'] = past.get('right_turn_rate', 0.25)
        features['left_turn_rate'] = past.get('left_turn_rate', 0.25)

        # ===== 新規特徴量 =====

        # 間隔カテゴリ別成績
        days_since = features['days_since_last_race']
        interval_cat = self._get_interval_category(days_since)
        interval_key = f"{kettonum}_{interval_cat}"
        if interval_stats and interval_key in interval_stats:
            i_stats = interval_stats.get(interval_key, {})
            features['interval_win_rate'] = i_stats.get('win_rate', 0.0)
            features['interval_place_rate'] = i_stats.get('place_rate', 0.0)
            features['interval_runs'] = i_stats.get('runs', 0)
        else:
            features['interval_win_rate'] = past.get('win_rate', 0.0)
            features['interval_place_rate'] = past.get('place_rate', 0.0)
            features['interval_runs'] = 0

        # 間隔カテゴリ（エンコード: 1=連闘, 2=中1週, 3=中2週, 4=中3週, 5=中4週以上）
        interval_cat_map = {'rentou': 1, 'week1': 2, 'week2': 3, 'week3': 4, 'week4plus': 5}
        features['interval_category'] = interval_cat_map.get(interval_cat, 5)

        # 展開予想（先行馬数・ペース）
        race_code = entry['race_code']
        pace_info = pace_predictions.get(race_code, {}) if pace_predictions else {}
        features['pace_maker_count'] = pace_info.get('pace_maker_count', 1)
        features['senkou_count'] = pace_info.get('senkou_count', 3)
        features['sashi_count'] = pace_info.get('sashi_count', 5)
        features['pace_type'] = pace_info.get('pace_type', 2)  # 1=スロー, 2=ミドル, 3=ハイ

        # 出走頭数（実際の値）
        if entries_by_race and race_code in entries_by_race:
            features['field_size'] = len(entries_by_race[race_code])
        else:
            features['field_size'] = 14

        # 脚質×展開相性
        running_style = features['running_style']
        pace_type = features['pace_type']
        features['style_pace_compatibility'] = self._calc_style_pace_compatibility(running_style, pace_type)

        # ターゲット
        features['target'] = chakujun

        return features

    def _calc_days_since_last(self, last_race_date: str, current_year: str, current_gappi: str) -> int:
        """前走からの日数を計算"""
        if not last_race_date or not current_year or not current_gappi:
            return 60

        try:
            from datetime import date as dt_date
            last_year = int(last_race_date[:4])
            last_month = int(last_race_date[4:6])
            last_day = int(last_race_date[6:8])
            curr_year = int(current_year)
            curr_month = int(current_gappi[:2])
            curr_day = int(current_gappi[2:4])

            last = dt_date(last_year, last_month, last_day)
            curr = dt_date(curr_year, curr_month, curr_day)
            return max(0, (curr - last).days)
        except Exception:
            return 60

    def _get_distance_category(self, distance: int) -> str:
        """距離カテゴリを返す"""
        if distance <= 1200:
            return 'sprint'
        elif distance <= 1600:
            return 'mile'
        elif distance <= 2000:
            return 'middle'
        elif distance <= 2400:
            return 'classic'
        else:
            return 'long'

    def _safe_int(self, val, default: int = 0) -> int:
        try:
            if val is None or val == '':
                return default
            return int(val)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, val, default: float = 0.0) -> float:
        try:
            if val is None or val == '':
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    def _encode_sex(self, sex_code: str) -> int:
        mapping = {'1': 0, '2': 1, '3': 2}
        return mapping.get(sex_code, 0)

    def _calc_speed_index(self, avg_time) -> float:
        if not avg_time:
            return 80.0
        minutes = avg_time // 1000
        seconds = (avg_time % 1000) / 10
        total = minutes * 60 + seconds
        return max(50, min(120, 100 - (total - 90) * 2))

    def _determine_style(self, avg_corner3: float) -> int:
        if avg_corner3 <= 2:
            return 1
        elif avg_corner3 <= 5:
            return 2
        elif avg_corner3 <= 10:
            return 3
        return 4

    def _determine_class(self, grade_code: str) -> int:
        mapping = {'A': 8, 'B': 7, 'C': 6, 'D': 5, 'E': 4, 'F': 3, 'G': 2, 'H': 1}
        return mapping.get(grade_code, 3)

    def _get_baba_stats_batch(self, kettonums: List[str], races: List[Dict]) -> Dict[str, Dict]:
        """馬場状態別成績をバッチ取得"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))
        result = {}

        # 芝・良
        for track, baba_name in [('1', 'turf'), ('2', 'dirt')]:
            for baba_code, baba_suffix in [('1', 'ryo'), ('2', 'yayaomo'), ('3', 'omo'), ('4', 'furyo')]:
                sql = f"""
                    SELECT
                        u.ketto_toroku_bango,
                        COUNT(*) as runs,
                        SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                    FROM umagoto_race_joho u
                    JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND r.track_code LIKE '{track}%%'
                      AND (r.shiba_babajotai_code = '{baba_code}' OR r.dirt_babajotai_code = '{baba_code}')
                    GROUP BY u.ketto_toroku_bango
                """
                try:
                    cur = self.conn.cursor()
                    cur.execute(sql, kettonums)
                    for row in cur.fetchall():
                        kettonum = row[0]
                        runs = int(row[1] or 0)
                        wins = int(row[2] or 0)
                        places = int(row[3] or 0)
                        key = f"{kettonum}_{baba_name}_{baba_suffix}"
                        result[key] = {
                            'runs': runs,
                            'win_rate': wins / runs if runs > 0 else 0.0,
                            'place_rate': places / runs if runs > 0 else 0.0
                        }
                    cur.close()
                except Exception as e:
                    logger.debug(f"Baba stats batch failed for {baba_name}_{baba_suffix}: {e}")
                    self.conn.rollback()

        return result

    def _get_interval_stats_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """間隔カテゴリ別成績をバッチ取得"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))

        # 間隔カテゴリ: 連闘(1-7日), 中1週(8-14日), 中2週(15-21日), 中3週(22-28日), 中4週以上(29日以上)
        result = {}

        for interval_name, min_days, max_days in [
            ('rentou', 1, 7),
            ('week1', 8, 14),
            ('week2', 15, 21),
            ('week3', 22, 28),
            ('week4plus', 29, 365)
        ]:
            sql = f"""
                WITH race_intervals AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.kakutei_chakujun,
                        DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2)))
                        - LAG(DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2))))
                          OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) as interval_days
                    FROM umagoto_race_joho u
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                )
                SELECT
                    ketto_toroku_bango,
                    COUNT(*) as runs,
                    SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM race_intervals
                WHERE interval_days >= {min_days} AND interval_days <= {max_days}
                GROUP BY ketto_toroku_bango
            """
            try:
                cur = self.conn.cursor()
                cur.execute(sql, kettonums)
                for row in cur.fetchall():
                    kettonum = row[0]
                    runs = int(row[1] or 0)
                    wins = int(row[2] or 0)
                    places = int(row[3] or 0)
                    key = f"{kettonum}_{interval_name}"
                    result[key] = {
                        'runs': runs,
                        'win_rate': wins / runs if runs > 0 else 0.0,
                        'place_rate': places / runs if runs > 0 else 0.0
                    }
                cur.close()
            except Exception as e:
                logger.debug(f"Interval stats batch failed for {interval_name}: {e}")
                self.conn.rollback()

        return result

    def _get_interval_category(self, days: int) -> str:
        """日数から間隔カテゴリを返す"""
        if days <= 7:
            return 'rentou'
        elif days <= 14:
            return 'week1'
        elif days <= 21:
            return 'week2'
        elif days <= 28:
            return 'week3'
        else:
            return 'week4plus'

    def _calc_pace_prediction(self, entries: List[Dict], past_stats: Dict[str, Dict]) -> Dict[str, Any]:
        """
        展開予想を計算

        Returns:
            pace_maker_count: 先行馬（逃げ・先行）の数
            pace_type: 1=スロー, 2=ミドル, 3=ハイ
        """
        pace_makers = 0
        senkou_count = 0
        sashi_count = 0

        for entry in entries:
            kettonum = entry.get('ketto_toroku_bango', '')
            past = past_stats.get(kettonum, {})
            style = self._determine_style(past.get('avg_corner3', 8))
            if style == 1:  # 逃げ
                pace_makers += 1
            elif style == 2:  # 先行
                senkou_count += 1
            elif style == 3:  # 差し
                sashi_count += 1

        # ペース予測：逃げ馬が2頭以上→ハイペース、逃げ馬0頭→スローペース
        if pace_makers >= 2:
            pace_type = 3  # ハイペース
        elif pace_makers == 0:
            pace_type = 1  # スローペース
        else:
            pace_type = 2  # ミドル

        return {
            'pace_maker_count': pace_makers,
            'senkou_count': senkou_count,
            'sashi_count': sashi_count,
            'pace_type': pace_type
        }

    def _calc_style_pace_compatibility(self, running_style: int, pace_type: int) -> float:
        """
        脚質×ペースの相性スコア

        ハイペースでは差し・追込が有利
        スローペースでは逃げ・先行が有利
        """
        compatibility_matrix = {
            # (running_style, pace_type): compatibility_score
            (1, 1): 0.8,   # 逃げ×スロー = 有利
            (1, 2): 0.5,   # 逃げ×ミドル = 普通
            (1, 3): 0.2,   # 逃げ×ハイ = 不利
            (2, 1): 0.7,   # 先行×スロー = やや有利
            (2, 2): 0.5,   # 先行×ミドル = 普通
            (2, 3): 0.4,   # 先行×ハイ = やや不利
            (3, 1): 0.3,   # 差し×スロー = やや不利
            (3, 2): 0.5,   # 差し×ミドル = 普通
            (3, 3): 0.7,   # 差し×ハイ = やや有利
            (4, 1): 0.2,   # 追込×スロー = 不利
            (4, 2): 0.5,   # 追込×ミドル = 普通
            (4, 3): 0.8,   # 追込×ハイ = 有利
        }
        return compatibility_matrix.get((running_style, pace_type), 0.5)


def train_model(df: pd.DataFrame, use_gpu: bool = True) -> Tuple[xgb.XGBRegressor, Dict]:
    """
    モデルを学習

    Args:
        df: 特徴量DataFrame（target列含む）
        use_gpu: GPU使用フラグ

    Returns:
        (学習済みモデル, 学習結果)
    """
    logger.info(f"モデル学習開始: {len(df)}サンプル")

    # 特徴量とターゲットを分離
    target_col = 'target'
    feature_cols = [c for c in df.columns if c != target_col]

    X = df[feature_cols].fillna(0)
    y = df[target_col]

    # 訓練/検証分割（時系列を考慮して後ろ20%を検証用）
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"訓練データ: {len(X_train)}, 検証データ: {len(X_val)}")

    # XGBoostパラメータ
    params = {
        'n_estimators': 800,
        'max_depth': 7,
        'learning_rate': 0.03,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'random_state': 42,
        'n_jobs': -1
    }

    # GPU使用設定
    if use_gpu:
        params['tree_method'] = 'hist'
        params['device'] = 'cuda'
        logger.info("GPU学習モード")
    else:
        logger.info("CPU学習モード")

    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        early_stopping_rounds=50,
        **params
    )

    # 学習
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=100
    )

    # 検証
    pred = model.predict(X_val)
    rmse = np.sqrt(np.mean((pred - y_val) ** 2))
    logger.info(f"検証RMSE: {rmse:.4f}")

    # 特徴量重要度
    importance = dict(sorted(
        zip(feature_cols, model.feature_importances_),
        key=lambda x: x[1],
        reverse=True
    ))

    return model, {
        'feature_names': feature_cols,
        'rmse': rmse,
        'importance': importance,
        'train_size': len(X_train),
        'val_size': len(X_val)
    }


def save_model(model: xgb.XGBRegressor, results: Dict, output_dir: str) -> str:
    """モデルを保存"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = Path(output_dir) / f"xgboost_model_{timestamp}.pkl"
    latest_path = Path(output_dir) / "xgboost_model_latest.pkl"

    model_data = {
        'model': model,
        'feature_names': results['feature_names'],
        'feature_importance': results['importance'],
        'trained_at': timestamp,
        'rmse': results['rmse']
    }

    joblib.dump(model_data, model_path)
    logger.info(f"モデル保存: {model_path}")

    # シンボリックリンク更新
    if latest_path.exists() or latest_path.is_symlink():
        latest_path.unlink()
    latest_path.symlink_to(model_path.name)

    return str(model_path)


def main():
    parser = argparse.ArgumentParser(description="高速学習スクリプト")
    parser.add_argument("--start-year", type=int, default=2015, help="開始年")
    parser.add_argument("--end-year", type=int, default=2025, help="終了年")
    parser.add_argument("--max-races", type=int, default=5000, help="年間最大レース数")
    parser.add_argument("--output", default="/app/models", help="出力ディレクトリ")
    parser.add_argument("--no-gpu", action="store_true", help="GPUを使用しない")

    args = parser.parse_args()

    print("=" * 60)
    print("高速学習スクリプト")
    print("=" * 60)
    print(f"期間: {args.start_year}年 ~ {args.end_year}年")
    print(f"年間最大レース数: {args.max_races}")
    print(f"GPU: {'無効' if args.no_gpu else '有効'}")
    print("=" * 60)

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        extractor = FastFeatureExtractor(conn)

        # 年ごとにデータ収集
        all_data = []
        for year in range(args.start_year, args.end_year + 1):
            df = extractor.extract_year_data(year, args.max_races)
            if len(df) > 0:
                all_data.append(df)

        if not all_data:
            logger.error("データがありません")
            return

        # 結合
        full_df = pd.concat(all_data, ignore_index=True)
        logger.info(f"全データ: {len(full_df)}サンプル")

        # 学習
        model, results = train_model(full_df, use_gpu=not args.no_gpu)

        # 保存
        model_path = save_model(model, results, args.output)

        # 結果表示
        print("\n" + "=" * 60)
        print("学習完了")
        print("=" * 60)
        print(f"サンプル数: {len(full_df)}")
        print(f"検証RMSE: {results['rmse']:.4f}")
        print(f"モデル: {model_path}")

        print("\n特徴量重要度 TOP15:")
        for i, (name, imp) in enumerate(list(results['importance'].items())[:15], 1):
            print(f"  {i:2d}. {name}: {imp:.4f}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
