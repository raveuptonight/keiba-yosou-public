"""
高速学習スクリプト

DBクエリをバッチ化して大量データを効率的に処理
- レース単位でまとめてデータ取得
- 年単位でバッチ処理
- GPU対応XGBoost学習
"""

import argparse
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.isotonic import IsotonicRegression
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

    # 競馬場コード → 名前マッピング
    VENUE_CODES = {
        '01': 'sapporo', '02': 'hakodate', '03': 'fukushima', '04': 'niigata',
        '05': 'tokyo', '06': 'nakayama', '07': 'chukyo', '08': 'kyoto',
        '09': 'hanshin', '10': 'kokura'
    }
    # 小回りコース
    SMALL_TRACK_VENUES = {'01', '02', '03', '06', '10'}

    def __init__(self, conn):
        self.conn = conn
        self._jockey_cache = {}
        self._trainer_cache = {}
        self._pedigree_cache = {}
        self._sire_stats_cache = {}

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

        # 3. 過去成績を一括取得（直近10走）- 当該レースを除外してデータリーク防止
        kettonums = list(set(e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')))
        past_stats = self._get_past_stats_batch(kettonums, entries=entries)
        logger.info(f"  過去成績取得: {len(past_stats)}頭")

        # 4. 騎手・調教師成績をキャッシュ
        self._cache_jockey_trainer_stats(year)

        # 5. 追加データをバッチ取得
        # 騎手・馬コンビ
        jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                    for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
        jockey_horse_stats = self._get_jockey_horse_combo_batch(jh_pairs)
        logger.info(f"  騎手・馬コンビ: {len(jockey_horse_stats)}件")

        # 芝/ダート成績 - 当該レースを除外してデータリーク防止
        surface_stats = self._get_surface_stats_batch(kettonums, entries=entries)
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

        # 馬場状態別成績 - 当該レースを除外してデータリーク防止
        baba_stats = self._get_baba_stats_batch(kettonums, races, entries=entries)
        logger.info(f"  馬場別成績: {len(baba_stats)}件")

        # 間隔カテゴリ別成績 - 当該レースを除外してデータリーク防止
        interval_stats = self._get_interval_stats_batch(kettonums, entries=entries)
        logger.info(f"  間隔別成績: {len(interval_stats)}件")

        # ===== 拡張特徴量（v2）=====
        # 血統情報
        pedigree_info = self._get_pedigree_batch(kettonums)
        logger.info(f"  血統情報: {len(pedigree_info)}件")

        # 競馬場別成績 - 当該レースを除外してデータリーク防止
        venue_stats = self._get_venue_stats_batch(kettonums, entries=entries)
        logger.info(f"  競馬場別成績: {len(venue_stats)}件")

        # 前走詳細情報 - 当該レースを除外してデータリーク防止
        zenso_info = self._get_zenso_batch(kettonums, race_codes, entries=entries)
        logger.info(f"  前走詳細: {len(zenso_info)}件")

        # 騎手直近成績
        jockey_codes = list(set(e.get('kishu_code', '') for e in entries if e.get('kishu_code')))
        jockey_recent = self._get_jockey_recent_batch(jockey_codes, year)
        logger.info(f"  騎手直近成績: {len(jockey_recent)}件")

        # 種牡馬成績（芝・ダート別）
        sire_ids = [p.get('sire_id', '') for p in pedigree_info.values() if p.get('sire_id')]
        sire_stats_turf = self._get_sire_stats_batch(sire_ids, year, is_turf=True)
        sire_stats_dirt = self._get_sire_stats_batch(sire_ids, year, is_turf=False)
        logger.info(f"  種牡馬成績（芝）: {len(sire_stats_turf)}件, （ダート）: {len(sire_stats_dirt)}件")

        # 種牡馬の新馬・未勝利戦成績
        sire_maiden_stats = self._get_sire_maiden_stats_batch(sire_ids, year)
        logger.info(f"  種牡馬新馬成績: {len(sire_maiden_stats)}件")

        # 騎手の新馬・未勝利戦成績
        jockey_maiden_stats = self._get_jockey_maiden_stats_batch(jockey_codes, year)
        logger.info(f"  騎手新馬成績: {len(jockey_maiden_stats)}件")

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
                entries_by_race=entries_by_race,
                # 拡張特徴量用データ
                pedigree_info=pedigree_info,
                venue_stats=venue_stats,
                zenso_info=zenso_info,
                jockey_recent=jockey_recent,
                sire_stats_turf=sire_stats_turf,
                sire_stats_dirt=sire_stats_dirt,
                sire_maiden_stats=sire_maiden_stats,
                jockey_maiden_stats=jockey_maiden_stats,
                year=year
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

    def _get_past_stats_batch(self, kettonums: List[str], entries: List[Dict] = None) -> Dict[str, Dict]:
        """過去成績をバッチで取得（データリーク防止版）

        Args:
            kettonums: 馬番号リスト
            entries: 出走馬情報リスト（race_codeを含む）- 当該レースを除外するために使用
        """
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        # 各馬の直近10走の詳細統計を計算（当該レースを除外）
        placeholders = ','.join(['%s'] * len(kettonums))

        # 当該レースを除外するための条件を追加
        if horse_race_map:
            # 各馬のrace_codeより前のレースのみを対象とする
            # VALUES句で馬ごとのフィルタを作成
            values_parts = []
            params = list(kettonums)
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')  # 見つからない場合は全て含める
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            sql = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                ),
                ranked AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.race_code,
                        u.kakutei_chakujun,
                        u.soha_time,
                        u.kohan_3f,
                        u.corner3_juni,
                        u.corner4_juni,
                        u.kishu_code,
                        u.kaisai_nen,
                        u.kaisai_gappi,
                        ROW_NUMBER() OVER (
                            PARTITION BY u.ketto_toroku_bango
                            ORDER BY u.race_code DESC
                        ) as rn
                    FROM umagoto_race_joho u
                    JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND u.race_code < hf.current_race_code  -- 当該レースより前のみ
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
        else:
            # entries がない場合は従来の動作（予測時など）
            params = kettonums
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
        cur.execute(sql, params)
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

    def _get_surface_stats_batch(self, kettonums: List[str], entries: List[Dict] = None) -> Dict[str, Dict]:
        """芝/ダート別成績をバッチ取得（データリーク防止版）"""
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        placeholders = ','.join(['%s'] * len(kettonums))

        if horse_race_map:
            # VALUES句で馬ごとのフィルタを作成
            values_parts = []
            params = list(kettonums)
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            # 芝成績
            sql_turf = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                )
                SELECT
                    u.ketto_toroku_bango,
                    COUNT(*) as runs,
                    SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND r.track_code LIKE '1%%'
                  AND u.race_code < hf.current_race_code
                GROUP BY u.ketto_toroku_bango
            """
            # ダート成績
            sql_dirt = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                )
                SELECT
                    u.ketto_toroku_bango,
                    COUNT(*) as runs,
                    SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND r.track_code LIKE '2%%'
                  AND u.race_code < hf.current_race_code
                GROUP BY u.ketto_toroku_bango
            """
        else:
            params = kettonums
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
            cur.execute(sql_turf, params)
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
            cur.execute(sql_dirt, params)
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
        entries_by_race: Dict[str, List[Dict]] = None,
        # 拡張特徴量用データ
        pedigree_info: Dict[str, Dict] = None,
        venue_stats: Dict[str, Dict] = None,
        zenso_info: Dict[str, Dict] = None,
        jockey_recent: Dict[str, Dict] = None,
        sire_stats_turf: Dict[str, Dict] = None,
        sire_stats_dirt: Dict[str, Dict] = None,
        sire_maiden_stats: Dict[str, Dict] = None,
        jockey_maiden_stats: Dict[str, Dict] = None,
        year: int = None
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

        # レース識別情報（グループ化・評価用、特徴量として使用しない）
        features['race_code'] = race_code

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

        # ========================================
        # 拡張特徴量 (v2)
        # ========================================

        # --- 1. 血統特徴量 ---
        pedigree = pedigree_info.get(kettonum, {}) if pedigree_info else {}
        sire_id = pedigree.get('sire_id', '')
        broodmare_sire_id = pedigree.get('broodmare_sire_id', '')

        # 種牡馬IDハッシュ（カテゴリ特徴量）- 安定ハッシュ使用
        features['sire_id_hash'] = self._stable_hash(sire_id) if sire_id else 0
        features['broodmare_sire_id_hash'] = self._stable_hash(broodmare_sire_id) if broodmare_sire_id else 0

        # 種牡馬×芝/ダート成績
        is_turf = track_code.startswith('1') if track_code else True
        if is_turf and sire_stats_turf:
            sire_key = f"{sire_id}_turf"
            sire_stats = sire_stats_turf.get(sire_key, {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0})
        elif sire_stats_dirt:
            sire_key = f"{sire_id}_dirt"
            sire_stats = sire_stats_dirt.get(sire_key, {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0})
        else:
            sire_stats = {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

        features['sire_win_rate'] = sire_stats['win_rate']
        features['sire_place_rate'] = sire_stats['place_rate']
        features['sire_runs'] = min(sire_stats['runs'], 500)

        # 種牡馬の新馬・未勝利戦成績
        if sire_maiden_stats and sire_id:
            sire_m_stats = sire_maiden_stats.get(sire_id, {})
            features['sire_maiden_win_rate'] = sire_m_stats.get('win_rate', 0.10)
            features['sire_maiden_place_rate'] = sire_m_stats.get('place_rate', 0.30)
            features['sire_maiden_runs'] = min(sire_m_stats.get('runs', 0), 300)
        else:
            features['sire_maiden_win_rate'] = 0.10
            features['sire_maiden_place_rate'] = 0.30
            features['sire_maiden_runs'] = 0

        # 馬の出走回数（past_statsから取得、新馬判定用）
        race_count = past.get('race_count', 0)
        features['race_count'] = min(race_count, 20)
        # 経験カテゴリ: 0=新馬, 1=少経験(1-2戦), 2=経験馬(3戦以上)
        if race_count == 0:
            features['experience_category'] = 0
        elif race_count <= 2:
            features['experience_category'] = 1
        else:
            features['experience_category'] = 2

        # --- 2. 前走詳細特徴量 ---
        zenso = zenso_info.get(kettonum, {}) if zenso_info else {}
        features['zenso1_chakujun'] = zenso.get('zenso1_chakujun', 10)
        features['zenso1_ninki'] = zenso.get('zenso1_ninki', 10)
        features['zenso1_agari'] = zenso.get('zenso1_agari', 35.0)
        features['zenso1_corner_avg'] = zenso.get('zenso1_corner_avg', 8.0)
        features['zenso1_distance'] = zenso.get('zenso1_distance', 1600)
        features['zenso1_grade'] = zenso.get('zenso1_grade', 3)
        features['zenso2_chakujun'] = zenso.get('zenso2_chakujun', 10)
        features['zenso3_chakujun'] = zenso.get('zenso3_chakujun', 10)
        features['zenso_chakujun_trend'] = zenso.get('zenso_chakujun_trend', 0)
        features['zenso_agari_trend'] = zenso.get('zenso_agari_trend', 0)

        # 距離差（今回 - 前走）
        current_distance = self._safe_int(race_info.get('kyori'), 1600)
        features['zenso1_distance_diff'] = current_distance - features['zenso1_distance']

        # クラス差（今回 - 前走）
        current_grade = self._determine_class(race_info.get('grade_code', ''))
        features['zenso1_class_diff'] = current_grade - features['zenso1_grade']

        # --- 3. 競馬場別成績 ---
        venue_code = race_info.get('keibajo_code', '')
        surface_name = 'shiba' if is_turf else 'dirt'
        venue_key = f"{kettonum}_{venue_code}_{surface_name}"
        v_stats = venue_stats.get(venue_key, {}) if venue_stats else {}
        features['venue_win_rate'] = v_stats.get('win_rate', 0.0)
        features['venue_place_rate'] = v_stats.get('place_rate', 0.0)
        features['venue_runs'] = min(v_stats.get('runs', 0), 50)

        # 小回り/大回り適性
        features['small_track_rate'] = zenso.get('small_track_rate', 0.25)
        features['large_track_rate'] = zenso.get('large_track_rate', 0.25)

        # 今回のコースタイプに応じた適性
        is_small_track = venue_code in self.SMALL_TRACK_VENUES
        features['track_type_fit'] = features['small_track_rate'] if is_small_track else features['large_track_rate']

        # --- 4. 展開強化特徴量 ---
        umaban = self._safe_int(entry.get('umaban'), 0)
        my_style = running_style

        # 自分より内枠の逃げ・先行馬数
        inner_nige = 0
        inner_senkou = 0
        if entries_by_race and race_code in entries_by_race:
            for e in entries_by_race[race_code]:
                e_umaban = self._safe_int(e.get('umaban'), 0)
                e_kettonum = e.get('ketto_toroku_bango', '')
                e_past = past_stats.get(e_kettonum, {})
                e_style = self._determine_style(e_past.get('avg_corner3', 8))
                if e_umaban < umaban:
                    if e_style == 1:
                        inner_nige += 1
                    elif e_style == 2:
                        inner_senkou += 1

        features['inner_nige_count'] = inner_nige
        features['inner_senkou_count'] = inner_senkou

        # 枠番×脚質の有利不利
        waku_style_score = 0.0
        if my_style in (1, 2):  # 逃げ・先行
            if umaban <= 4:
                waku_style_score = 0.1
            elif umaban >= 13:
                waku_style_score = -0.1
        else:  # 差し・追込
            if umaban <= 4:
                waku_style_score = -0.05
            elif umaban >= 13:
                waku_style_score = 0.05
        features['waku_style_advantage'] = waku_style_score

        # --- 5. 騎手直近成績 ---
        jockey_code = entry.get('kishu_code', '')
        j_recent = jockey_recent.get(jockey_code, {}) if jockey_recent else {}
        features['jockey_recent_win_rate'] = j_recent.get('win_rate', 0.08)
        features['jockey_recent_place_rate'] = j_recent.get('place_rate', 0.25)
        features['jockey_recent_runs'] = min(j_recent.get('runs', 0), 30)

        # 騎手の新馬・未勝利戦成績
        if jockey_maiden_stats and jockey_code:
            j_maiden = jockey_maiden_stats.get(jockey_code, {})
            features['jockey_maiden_win_rate'] = j_maiden.get('win_rate', 0.08)
            features['jockey_maiden_place_rate'] = j_maiden.get('place_rate', 0.25)
            features['jockey_maiden_runs'] = min(j_maiden.get('runs', 0), 200)
        else:
            features['jockey_maiden_win_rate'] = 0.08
            features['jockey_maiden_place_rate'] = 0.25
            features['jockey_maiden_runs'] = 0

        # --- 6. 季節・時期特徴量 ---
        gappi = race_info.get('kaisai_gappi', '0601')
        month = self._safe_int(gappi[:2], 6)
        features['race_month'] = month
        features['month_sin'] = np.sin(2 * np.pi * month / 12)
        features['month_cos'] = np.cos(2 * np.pi * month / 12)

        # 開催週
        nichime = self._safe_int(race_info.get('kaisai_nichiji', '01'), 1)
        if nichime <= 2:
            features['kaisai_week'] = 1
        elif nichime >= 7:
            features['kaisai_week'] = 3
        else:
            features['kaisai_week'] = 2

        # 成長期判定
        horse_age = features['age']
        if horse_age == 3 and 3 <= month <= 8:
            features['growth_period'] = 1
        elif horse_age == 4 and 1 <= month <= 6:
            features['growth_period'] = 1
        else:
            features['growth_period'] = 0

        # 冬場フラグ
        features['is_winter'] = 1 if month in (12, 1, 2) else 0

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

    def _get_baba_stats_batch(self, kettonums: List[str], races: List[Dict], entries: List[Dict] = None) -> Dict[str, Dict]:
        """馬場状態別成績をバッチ取得（データリーク防止版）"""
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        placeholders = ','.join(['%s'] * len(kettonums))
        result = {}

        if horse_race_map:
            # VALUES句で馬ごとのフィルタを作成
            values_parts = []
            params = list(kettonums)
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            # 芝・良
            for track, baba_name in [('1', 'turf'), ('2', 'dirt')]:
                for baba_code, baba_suffix in [('1', 'ryo'), ('2', 'yayaomo'), ('3', 'omo'), ('4', 'furyo')]:
                    sql = f"""
                        WITH horse_filter AS (
                            SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                        )
                        SELECT
                            u.ketto_toroku_bango,
                            COUNT(*) as runs,
                            SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                        FROM umagoto_race_joho u
                        JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                        JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                        WHERE u.ketto_toroku_bango IN ({placeholders})
                          AND u.data_kubun = '7'
                          AND u.kakutei_chakujun ~ '^[0-9]+$'
                          AND r.track_code LIKE '{track}%%'
                          AND (r.shiba_babajotai_code = '{baba_code}' OR r.dirt_babajotai_code = '{baba_code}')
                          AND u.race_code < hf.current_race_code
                        GROUP BY u.ketto_toroku_bango
                    """
                    try:
                        cur = self.conn.cursor()
                        cur.execute(sql, params)
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
        else:
            # entries がない場合は従来の動作
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

    def _get_interval_stats_batch(self, kettonums: List[str], entries: List[Dict] = None) -> Dict[str, Dict]:
        """間隔カテゴリ別成績をバッチ取得（データリーク防止版）"""
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        placeholders = ','.join(['%s'] * len(kettonums))

        # 間隔カテゴリ: 連闘(1-7日), 中1週(8-14日), 中2週(15-21日), 中3週(22-28日), 中4週以上(29日以上)
        result = {}

        if horse_race_map:
            # VALUES句で馬ごとのフィルタを作成
            values_parts = []
            params = list(kettonums)
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            for interval_name, min_days, max_days in [
                ('rentou', 1, 7),
                ('week1', 8, 14),
                ('week2', 15, 21),
                ('week3', 22, 28),
                ('week4plus', 29, 365)
            ]:
                sql = f"""
                    WITH horse_filter AS (
                        SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                    ),
                    race_intervals AS (
                        SELECT
                            u.ketto_toroku_bango,
                            u.race_code,
                            u.kakutei_chakujun,
                            DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2)))
                            - LAG(DATE(CONCAT(u.kaisai_nen, '-', SUBSTRING(u.kaisai_gappi, 1, 2), '-', SUBSTRING(u.kaisai_gappi, 3, 2))))
                              OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) as interval_days
                        FROM umagoto_race_joho u
                        JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                        WHERE u.ketto_toroku_bango IN ({placeholders})
                          AND u.data_kubun = '7'
                          AND u.kakutei_chakujun ~ '^[0-9]+$'
                          AND u.race_code < hf.current_race_code
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
                    cur.execute(sql, params)
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
        else:
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

    # ===== 拡張特徴量バッチメソッド =====

    def _get_pedigree_batch(self, kettonums: List[str]) -> Dict[str, Dict]:
        """血統情報をバッチ取得（父馬・母父馬ID）"""
        if not kettonums:
            return {}

        placeholders = ','.join(['%s'] * len(kettonums))
        sql = f"""
            SELECT
                ketto_toroku_bango,
                ketto1_hanshoku_toroku_bango as sire_id,
                ketto3_hanshoku_toroku_bango as broodmare_sire_id
            FROM kyosoba_master2
            WHERE ketto_toroku_bango IN ({placeholders})
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, kettonums)
            for row in cur.fetchall():
                kettonum, sire_id, bms_id = row
                result[kettonum] = {
                    'sire_id': sire_id or '',
                    'broodmare_sire_id': bms_id or ''
                }
            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Pedigree batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_sire_stats_batch(self, sire_ids: List[str], year: int, is_turf: bool = True) -> Dict[str, Dict]:
        """種牡馬産駒成績をバッチ取得"""
        if not sire_ids:
            return {}

        unique_ids = list(set(s for s in sire_ids if s))
        if not unique_ids:
            return {}

        # 最大1000件に制限
        unique_ids = unique_ids[:1000]
        placeholders = ','.join(['%s'] * len(unique_ids))
        year_from = str(year - 3)

        # 芝/ダートを判定するためにレースコードから取得
        # race_codeの11桁目がトラック種別（10=芝, 20=ダート等）
        # 簡易版：全体成績を取得
        sql = f"""
            SELECT
                k.ketto1_hanshoku_toroku_bango as sire_id,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
            WHERE k.ketto1_hanshoku_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.kaisai_nen >= %s
            GROUP BY k.ketto1_hanshoku_toroku_bango
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, unique_ids + [year_from])
            for row in cur.fetchall():
                sire_id, runs, wins, places = row
                runs = int(runs or 0)
                # 芝・ダート両方に同じ値を設定（簡易版）
                for surface in ['turf', 'dirt']:
                    key = f"{sire_id}_{surface}"
                    result[key] = {
                        'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                        'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                        'runs': runs
                    }
            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Sire stats batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_sire_maiden_stats_batch(self, sire_ids: List[str], year: int) -> Dict[str, Dict]:
        """種牡馬の新馬・未勝利戦成績をバッチ取得"""
        if not sire_ids:
            return {}

        unique_ids = list(set(s for s in sire_ids if s))
        if not unique_ids:
            return {}

        # 最大1000件に制限
        unique_ids = unique_ids[:1000]
        placeholders = ','.join(['%s'] * len(unique_ids))
        year_from = str(year - 5)  # 新馬戦データは5年分取得

        sql = f"""
            SELECT
                k.ketto1_hanshoku_toroku_bango as sire_id,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
            JOIN race_shosai rs ON u.race_code = rs.race_code AND rs.data_kubun = '7'
            WHERE k.ketto1_hanshoku_toroku_bango IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.kaisai_nen >= %s
              AND (rs.kyoso_joken_code_2sai IN ('701', '703')
                   OR rs.kyoso_joken_code_3sai IN ('701', '703'))
            GROUP BY k.ketto1_hanshoku_toroku_bango
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, unique_ids + [year_from])
            for row in cur.fetchall():
                sire_id, runs, wins, places = row
                runs = int(runs or 0)
                if runs >= 5:  # 最低5頭以上のデータがある種牡馬のみ
                    result[sire_id] = {
                        'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                        'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                        'runs': runs
                    }
            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Sire maiden stats batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_venue_stats_batch(self, kettonums: List[str], entries: List[Dict] = None) -> Dict[str, Dict]:
        """競馬場別成績をバッチ取得（データリーク防止版）

        Args:
            kettonums: 馬番号リスト
            entries: 出走馬情報リスト（race_codeを含む）- 当該レースを除外するために使用
        """
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        placeholders = ','.join(['%s'] * len(kettonums))

        # 当該レースを除外するための条件を追加
        if horse_race_map:
            values_parts = []
            params = []  # 空リストから開始
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            sql = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                )
                SELECT
                    u.ketto_toroku_bango,
                    r.keibajo_code,
                    CASE WHEN r.track_code LIKE '1%%' THEN 'shiba' ELSE 'dirt' END as surface,
                    COUNT(*) as runs,
                    SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND u.race_code < hf.current_race_code
                GROUP BY u.ketto_toroku_bango, r.keibajo_code, surface
            """
            params.extend(kettonums)  # WHERE IN用のパラメータを追加
        else:
            # entriesがない場合（予測時など）は全データ使用
            sql = f"""
                SELECT
                    u.ketto_toroku_bango,
                    r.keibajo_code,
                    CASE WHEN r.track_code LIKE '1%%' THEN 'shiba' ELSE 'dirt' END as surface,
                    COUNT(*) as runs,
                    SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code AND r.data_kubun = '7'
                WHERE u.ketto_toroku_bango IN ({placeholders})
                  AND u.data_kubun = '7'
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                GROUP BY u.ketto_toroku_bango, r.keibajo_code, surface
            """
            params = kettonums

        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            for row in cur.fetchall():
                kettonum = row[0]
                venue_code = row[1]
                surface = row[2]
                runs = int(row[3] or 0)
                wins = int(row[4] or 0)
                places = int(row[5] or 0)
                if runs > 0:
                    key = f"{kettonum}_{venue_code}_{surface}"
                    result[key] = {
                        'win_rate': wins / runs,
                        'place_rate': places / runs,
                        'runs': runs
                    }
            cur.close()
        except Exception as e:
            logger.warning(f"Venue stats batch failed: {e}")
            self.conn.rollback()

        return result

    def _get_zenso_batch(self, kettonums: List[str], race_codes: List[str], entries: List[Dict] = None) -> Dict[str, Dict]:
        """前走情報をバッチ取得（データリーク防止版）"""
        if not kettonums:
            return {}

        # 馬ごとの当該race_codeマッピングを作成
        horse_race_map = {}
        if entries:
            for e in entries:
                k = e.get('ketto_toroku_bango', '')
                rc = e.get('race_code', '')
                if k and rc:
                    horse_race_map[k] = rc

        placeholders = ','.join(['%s'] * len(kettonums))

        if horse_race_map:
            # VALUES句で馬ごとのフィルタを作成
            values_parts = []
            params = list(kettonums)
            for k in kettonums:
                rc = horse_race_map.get(k, '9999999999999999')
                values_parts.append("(%s, %s)")
                params.extend([k, rc])

            # 各馬の直近5走を取得（当該レースを除外）
            sql = f"""
                WITH horse_filter AS (
                    SELECT * FROM (VALUES {','.join(values_parts)}) AS t(kettonum, current_race_code)
                ),
                ranked AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.race_code,
                        u.kakutei_chakujun,
                        u.tansho_ninkijun,
                        u.kohan_3f,
                        u.corner3_juni,
                        u.corner4_juni,
                        r.kyori,
                        r.grade_code,
                        r.keibajo_code,
                        ROW_NUMBER() OVER (
                            PARTITION BY u.ketto_toroku_bango
                            ORDER BY u.race_code DESC
                        ) as rn
                    FROM umagoto_race_joho u
                    JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
                    JOIN horse_filter hf ON u.ketto_toroku_bango = hf.kettonum
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                      AND u.race_code < hf.current_race_code
                )
                SELECT * FROM ranked WHERE rn <= 5
            """
        else:
            params = kettonums
            # 各馬の直近5走を取得
            sql = f"""
                WITH ranked AS (
                    SELECT
                        u.ketto_toroku_bango,
                        u.race_code,
                        u.kakutei_chakujun,
                        u.tansho_ninkijun,
                        u.kohan_3f,
                        u.corner3_juni,
                        u.corner4_juni,
                        r.kyori,
                        r.grade_code,
                        r.keibajo_code,
                        ROW_NUMBER() OVER (
                            PARTITION BY u.ketto_toroku_bango
                            ORDER BY u.race_code DESC
                        ) as rn
                    FROM umagoto_race_joho u
                    JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
                    WHERE u.ketto_toroku_bango IN ({placeholders})
                      AND u.data_kubun = '7'
                      AND u.kakutei_chakujun ~ '^[0-9]+$'
                )
                SELECT * FROM ranked WHERE rn <= 5
            """

        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()

            # 馬ごとにグループ化
            horse_races = {}
            for row in rows:
                kettonum = row[0]
                if kettonum not in horse_races:
                    horse_races[kettonum] = []
                horse_races[kettonum].append({
                    'race_code': row[1],
                    'chakujun': self._safe_int(row[2], 10),
                    'ninki': self._safe_int(row[3], 10),
                    'kohan_3f': self._safe_int(row[4], 350) / 10.0,
                    'corner3': self._safe_int(row[5], 8),
                    'corner4': self._safe_int(row[6], 8),
                    'kyori': self._safe_int(row[7], 1600),
                    'grade_code': row[8] or '',
                    'keibajo_code': row[9] or ''
                })

            # 特徴量を計算
            for kettonum, races in horse_races.items():
                # 1走前
                z1 = races[0] if len(races) > 0 else {}
                z2 = races[1] if len(races) > 1 else {}
                z3 = races[2] if len(races) > 2 else {}

                # 着順トレンド
                if len(races) >= 3:
                    c1 = z1.get('chakujun', 10)
                    c3 = z3.get('chakujun', 10)
                    if c1 < c3 - 2:
                        trend = 1
                    elif c1 > c3 + 2:
                        trend = -1
                    else:
                        trend = 0
                else:
                    trend = 0

                # 上がりトレンド
                agaris = [r.get('kohan_3f', 35.0) for r in races[:3] if r.get('kohan_3f', 0) > 0]
                if len(agaris) >= 3:
                    if agaris[0] < agaris[2] - 0.3:
                        agari_trend = 1
                    elif agaris[0] > agaris[2] + 0.3:
                        agari_trend = -1
                    else:
                        agari_trend = 0
                else:
                    agari_trend = 0

                # 小回り/大回り別成績
                small_places = 0
                small_runs = 0
                large_places = 0
                large_runs = 0
                for r in races:
                    venue = r.get('keibajo_code', '')
                    chaku = r.get('chakujun', 99)
                    if venue in self.SMALL_TRACK_VENUES:
                        small_runs += 1
                        if chaku <= 3:
                            small_places += 1
                    else:
                        large_runs += 1
                        if chaku <= 3:
                            large_places += 1

                result[kettonum] = {
                    'zenso1_chakujun': z1.get('chakujun', 10),
                    'zenso1_ninki': z1.get('ninki', 10),
                    'zenso1_agari': z1.get('kohan_3f', 35.0),
                    'zenso1_corner_avg': (z1.get('corner3', 8) + z1.get('corner4', 8)) / 2.0,
                    'zenso1_distance': z1.get('kyori', 1600),
                    'zenso1_grade': self._grade_to_rank(z1.get('grade_code', '')),
                    'zenso2_chakujun': z2.get('chakujun', 10),
                    'zenso3_chakujun': z3.get('chakujun', 10),
                    'zenso_chakujun_trend': trend,
                    'zenso_agari_trend': agari_trend,
                    'small_track_rate': small_places / small_runs if small_runs > 0 else 0.25,
                    'large_track_rate': large_places / large_runs if large_runs > 0 else 0.25
                }

            return result
        except Exception as e:
            logger.debug(f"Zenso batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_jockey_recent_batch(self, jockey_codes: List[str], year: int) -> Dict[str, Dict]:
        """騎手直近成績をバッチ取得"""
        if not jockey_codes:
            return {}

        unique_codes = list(set(c for c in jockey_codes if c))
        if not unique_codes:
            return {}

        placeholders = ','.join(['%s'] * len(unique_codes))
        # 直近14日間の成績
        sql = f"""
            SELECT
                kishu_code,
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE kishu_code IN ({placeholders})
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
              AND kaisai_nen = %s
            GROUP BY kishu_code
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, unique_codes + [str(year)])
            for row in cur.fetchall():
                code, runs, wins, places = row
                runs = int(runs or 0)
                result[code] = {
                    'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                    'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                    'runs': runs
                }
            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Jockey recent batch failed: {e}")
            self.conn.rollback()
            return {}

    def _get_jockey_maiden_stats_batch(self, jockey_codes: List[str], year: int) -> Dict[str, Dict]:
        """騎手の新馬・未勝利戦成績をバッチ取得"""
        if not jockey_codes:
            return {}

        unique_codes = list(set(c for c in jockey_codes if c))
        if not unique_codes:
            return {}

        placeholders = ','.join(['%s'] * len(unique_codes))
        year_from = str(year - 3)  # 3年分のデータ

        sql = f"""
            SELECT
                u.kishu_code,
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN race_shosai rs ON u.race_code = rs.race_code AND rs.data_kubun = '7'
            WHERE u.kishu_code IN ({placeholders})
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.kaisai_nen >= %s
              AND (rs.kyoso_joken_code_2sai IN ('701', '703')
                   OR rs.kyoso_joken_code_3sai IN ('701', '703'))
            GROUP BY u.kishu_code
        """
        result = {}
        try:
            cur = self.conn.cursor()
            cur.execute(sql, unique_codes + [year_from])
            for row in cur.fetchall():
                code, runs, wins, places = row
                runs = int(runs or 0)
                if runs >= 10:  # 最低10騎乗以上
                    result[code] = {
                        'win_rate': int(wins or 0) / runs if runs > 0 else 0.08,
                        'place_rate': int(places or 0) / runs if runs > 0 else 0.25,
                        'runs': runs
                    }
            cur.close()
            return result
        except Exception as e:
            logger.debug(f"Jockey maiden stats batch failed: {e}")
            self.conn.rollback()
            return {}

    def _grade_to_rank(self, grade_code: str) -> int:
        """グレードコードをランクに変換"""
        mapping = {'A': 8, 'B': 7, 'C': 6, 'D': 5, 'E': 4, 'F': 3, 'G': 2, 'H': 1}
        return mapping.get(grade_code, 3)

    def _stable_hash(self, s: str, mod: int = 10000) -> int:
        """安定したハッシュ値を生成（Python実行間で一貫性を保つ）"""
        return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod


def train_model(df: pd.DataFrame, use_gpu: bool = True) -> Tuple[Dict, Dict]:
    """
    モデルを学習（回帰 + 分類 + キャリブレーション）

    3分割構成（時系列順）:
    - train (70%): モデル学習用
    - calib (15%): キャリブレーター学習用（データリーク防止）
    - test  (15%): 最終評価用

    Args:
        df: 特徴量DataFrame（target列含む）
        use_gpu: GPU使用フラグ

    Returns:
        (モデル辞書, 学習結果)
    """
    logger.info(f"モデル学習開始: {len(df)}サンプル")

    # 特徴量とターゲットを分離
    target_col = 'target'
    exclude_cols = {target_col, 'race_code'}  # race_codeは識別用でobject型のため除外
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols].fillna(0)
    y = df[target_col]

    # 分類用ターゲット
    y_win = (y == 1).astype(int)  # 1着かどうか
    y_place = (y <= 3).astype(int)  # 3着以内かどうか

    # ===== 3分割（時系列順）=====
    n = len(X)
    train_end = int(n * 0.70)
    calib_end = int(n * 0.85)

    X_train = X.iloc[:train_end]
    X_calib = X.iloc[train_end:calib_end]  # キャリブレーション用
    X_test = X.iloc[calib_end:]             # 最終評価用
    X_val = X_calib  # early stoppingにはcalibデータを使用

    y_train = y.iloc[:train_end]
    y_calib = y.iloc[train_end:calib_end]
    y_test = y.iloc[calib_end:]
    y_val = y_calib

    y_win_train = y_win.iloc[:train_end]
    y_win_calib = y_win.iloc[train_end:calib_end]
    y_win_test = y_win.iloc[calib_end:]
    y_win_val = y_win_calib

    y_place_train = y_place.iloc[:train_end]
    y_place_calib = y_place.iloc[train_end:calib_end]
    y_place_test = y_place.iloc[calib_end:]
    y_place_val = y_place_calib

    logger.info(f"訓練: {len(X_train)}, キャリブ: {len(X_calib)}, テスト: {len(X_test)}")

    # 共通パラメータ
    base_params = {
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
        base_params['tree_method'] = 'hist'
        base_params['device'] = 'cuda'
        logger.info("GPU学習モード")
    else:
        logger.info("CPU学習モード")

    models = {}

    # ===== 1. 回帰モデル（着順予測）=====
    logger.info("回帰モデル学習中...")
    reg_model = xgb.XGBRegressor(
        objective='reg:squarederror',
        early_stopping_rounds=50,
        **base_params
    )
    reg_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=100
    )
    models['regressor'] = reg_model

    # 回帰モデル検証
    pred_reg = reg_model.predict(X_val)
    rmse = np.sqrt(np.mean((pred_reg - y_val) ** 2))
    logger.info(f"回帰モデル検証RMSE: {rmse:.4f}")

    # ===== 2. 勝利分類モデル =====
    logger.info("勝利分類モデル学習中...")
    win_params = base_params.copy()
    win_params['scale_pos_weight'] = len(y_win_train[y_win_train == 0]) / max(len(y_win_train[y_win_train == 1]), 1)
    win_model = xgb.XGBClassifier(
        objective='binary:logistic',
        early_stopping_rounds=50,
        **win_params
    )
    win_model.fit(
        X_train, y_win_train,
        eval_set=[(X_val, y_win_val)],
        verbose=100
    )
    models['win_classifier'] = win_model

    # 勝利モデル検証
    pred_win_prob = win_model.predict_proba(X_val)[:, 1]
    win_accuracy = ((pred_win_prob > 0.5) == y_win_val).mean()
    logger.info(f"勝利分類モデル精度: {win_accuracy:.4f}")

    # ===== 3. 複勝分類モデル =====
    logger.info("複勝分類モデル学習中...")
    place_params = base_params.copy()
    place_params['scale_pos_weight'] = len(y_place_train[y_place_train == 0]) / max(len(y_place_train[y_place_train == 1]), 1)
    place_model = xgb.XGBClassifier(
        objective='binary:logistic',
        early_stopping_rounds=50,
        **place_params
    )
    place_model.fit(
        X_train, y_place_train,
        eval_set=[(X_val, y_place_val)],
        verbose=100
    )
    models['place_classifier'] = place_model

    # 複勝モデル検証
    pred_place_prob = place_model.predict_proba(X_val)[:, 1]
    place_accuracy = ((pred_place_prob > 0.5) == y_place_val).mean()
    logger.info(f"複勝分類モデル精度: {place_accuracy:.4f}")

    # ===== 4. キャリブレーション（calibデータで学習）=====
    logger.info("キャリブレーション学習中...")

    # calibデータで予測（キャリブレーター学習用）
    pred_win_prob_calib = win_model.predict_proba(X_calib)[:, 1]
    pred_place_prob_calib = place_model.predict_proba(X_calib)[:, 1]

    # 勝利確率のキャリブレーション
    win_calibrator = IsotonicRegression(out_of_bounds='clip')
    win_calibrator.fit(pred_win_prob_calib, y_win_calib)
    models['win_calibrator'] = win_calibrator

    # 複勝確率のキャリブレーション
    place_calibrator = IsotonicRegression(out_of_bounds='clip')
    place_calibrator.fit(pred_place_prob_calib, y_place_calib)
    models['place_calibrator'] = place_calibrator

    # ===== 5. 最終評価（testデータ）=====
    logger.info("最終評価中（testデータ）...")
    from sklearn.metrics import roc_auc_score, brier_score_loss

    # testデータで予測
    pred_win_prob_test = win_model.predict_proba(X_test)[:, 1]
    pred_place_prob_test = place_model.predict_proba(X_test)[:, 1]

    # キャリブレーション適用
    calibrated_win_test = win_calibrator.predict(pred_win_prob_test)
    calibrated_place_test = place_calibrator.predict(pred_place_prob_test)

    # 評価指標（キャリブレーション前）
    win_auc_raw = roc_auc_score(y_win_test, pred_win_prob_test)
    win_brier_raw = brier_score_loss(y_win_test, pred_win_prob_test)
    place_auc_raw = roc_auc_score(y_place_test, pred_place_prob_test)
    place_brier_raw = brier_score_loss(y_place_test, pred_place_prob_test)

    # 評価指標（キャリブレーション後）
    win_auc = roc_auc_score(y_win_test, calibrated_win_test)
    win_brier = brier_score_loss(y_win_test, calibrated_win_test)
    place_auc = roc_auc_score(y_place_test, calibrated_place_test)
    place_brier = brier_score_loss(y_place_test, calibrated_place_test)

    logger.info(f"勝利 AUC: {win_auc:.4f} (raw: {win_auc_raw:.4f})")
    logger.info(f"勝利 Brier: {win_brier:.4f} (raw: {win_brier_raw:.4f}, 改善: {(win_brier_raw - win_brier) / win_brier_raw * 100:.1f}%)")
    logger.info(f"複勝 AUC: {place_auc:.4f} (raw: {place_auc_raw:.4f})")
    logger.info(f"複勝 Brier: {place_brier:.4f} (raw: {place_brier_raw:.4f}, 改善: {(place_brier_raw - place_brier) / place_brier_raw * 100:.1f}%)")
    logger.info(f"キャリブ後 - 勝利確率平均: {calibrated_win_test.mean():.4f}, 複勝確率平均: {calibrated_place_test.mean():.4f}")

    # 特徴量重要度（回帰モデルから）
    importance = dict(sorted(
        zip(feature_cols, reg_model.feature_importances_),
        key=lambda x: x[1],
        reverse=True
    ))

    return models, {
        'feature_names': feature_cols,
        'rmse': rmse,
        'win_accuracy': win_accuracy,
        'place_accuracy': place_accuracy,
        'win_auc': win_auc,
        'win_brier': win_brier,
        'place_auc': place_auc,
        'place_brier': place_brier,
        'importance': importance,
        'train_size': len(X_train),
        'calib_size': len(X_calib),
        'test_size': len(X_test)
    }


def save_model(models: Dict, results: Dict, output_dir: str) -> str:
    """モデルを保存"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = Path(output_dir) / f"xgboost_model_{timestamp}.pkl"
    latest_path = Path(output_dir) / "xgboost_model_latest.pkl"

    model_data = {
        # 後方互換性のため'model'キーにも回帰モデルを保存
        'model': models['regressor'],
        # 新しいモデル群
        'models': models,
        'feature_names': results['feature_names'],
        'feature_importance': results['importance'],
        'trained_at': timestamp,
        'rmse': results['rmse'],
        'win_accuracy': results.get('win_accuracy'),
        'place_accuracy': results.get('place_accuracy'),
        'version': 'v2_enhanced'
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
        models, results = train_model(full_df, use_gpu=not args.no_gpu)

        # 保存
        model_path = save_model(models, results, args.output)

        # 結果表示
        print("\n" + "=" * 60)
        print("学習完了")
        print("=" * 60)
        print(f"サンプル数: {len(full_df)}")
        print(f"特徴量数: {len(results['feature_names'])}")
        print(f"検証RMSE: {results['rmse']:.4f}")
        print(f"勝利分類精度: {results['win_accuracy']:.4f}")
        print(f"複勝分類精度: {results['place_accuracy']:.4f}")
        print(f"モデル: {model_path}")

        print("\n特徴量重要度 TOP15:")
        for i, (name, imp) in enumerate(list(results['importance'].items())[:15], 1):
            print(f"  {i:2d}. {name}: {imp:.4f}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
