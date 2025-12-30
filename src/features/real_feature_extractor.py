"""
実データベースからの特徴量抽出モジュール

JRA-VAN mykeibadb から特徴量を取得
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import date, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class RealFeatureExtractor:
    """JRA-VAN実データから特徴量を抽出"""

    def __init__(self, db_connection):
        """
        Args:
            db_connection: psycopg2接続オブジェクト
        """
        self.conn = db_connection
        self._cache = {}  # キャッシュ用

    def extract_features_for_race(
        self,
        race_code: str,
        data_kubun: str = "7"
    ) -> List[Dict[str, Any]]:
        """
        レース全馬の特徴量を抽出

        Args:
            race_code: レースコード（16桁）
            data_kubun: データ区分（7=確定）

        Returns:
            List[Dict]: 各馬の特徴量辞書リスト
        """
        # 出走馬一覧を取得
        entries = self._get_race_entries(race_code, data_kubun)
        if not entries:
            logger.warning(f"No entries found for race: {race_code}")
            return []

        # レース情報を取得
        race_info = self._get_race_info(race_code, data_kubun)

        features_list = []
        for entry in entries:
            features = self._extract_horse_features(entry, race_info, entries)
            features_list.append(features)

        return features_list

    def _get_race_entries(self, race_code: str, data_kubun: str) -> List[Dict]:
        """出走馬一覧を取得"""
        sql = """
            SELECT
                umaban,
                wakuban,
                ketto_toroku_bango,
                bamei,
                seibetsu_code,
                barei,
                futan_juryo,
                blinker_shiyo_kubun,
                kishu_code,
                chokyoshi_code,
                bataiju,
                zogen_sa,
                tansho_odds,
                tansho_ninkijun,
                kakutei_chakujun,
                soha_time,
                corner1_juni,
                corner2_juni,
                corner3_juni,
                corner4_juni,
                kohan_3f,
                kohan_4f,
                kyakushitsu_hantei
            FROM umagoto_race_joho
            WHERE race_code = %s
              AND data_kubun = %s
            ORDER BY umaban::int
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (race_code, data_kubun))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            cur.close()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get race entries: {e}")
            self.conn.rollback()
            return []

    def _get_race_info(self, race_code: str, data_kubun: str) -> Dict:
        """レース基本情報を取得"""
        sql = """
            SELECT
                race_code,
                kaisai_nen,
                kaisai_gappi,
                keibajo_code,
                race_bango,
                kyori,
                track_code,
                shiba_babajotai_code,
                dirt_babajotai_code,
                tenko_code,
                grade_code
            FROM race_shosai
            WHERE race_code = %s
              AND data_kubun = %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (race_code, data_kubun))
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            cur.close()
            return dict(zip(columns, row)) if row else {}
        except Exception as e:
            logger.error(f"Failed to get race info: {e}")
            self.conn.rollback()
            return {}

    def _extract_horse_features(
        self,
        entry: Dict,
        race_info: Dict,
        all_entries: List[Dict]
    ) -> Dict[str, Any]:
        """各馬の特徴量を抽出"""
        features = {}
        kettonum = entry.get('ketto_toroku_bango', '')

        # ===== 基本情報 =====
        features['umaban'] = self._safe_int(entry.get('umaban'), 0)
        features['wakuban'] = self._safe_int(entry.get('wakuban'), 0)
        features['age'] = self._safe_int(entry.get('barei'), 4)
        features['sex'] = self._encode_sex(entry.get('seibetsu_code', ''))
        features['kinryo'] = self._safe_float(entry.get('futan_juryo'), 55.0) / 10.0

        # ===== 馬体重 =====
        features['horse_weight'] = self._safe_int(entry.get('bataiju'), 480)
        features['weight_diff'] = self._safe_int(entry.get('zogen_sa'), 0)

        # ===== ブリンカー =====
        blinker = entry.get('blinker_shiyo_kubun', '0')
        features['blinker'] = 1 if blinker == '1' else 0

        # ===== オッズ・人気 =====
        features['odds_win'] = self._safe_float(entry.get('tansho_odds'), 50.0) / 10.0
        features['popularity'] = self._safe_int(entry.get('tansho_ninkijun'), 10)

        # ===== 過去成績から計算 =====
        past_races = self._get_past_races(kettonum, race_info.get('race_code', ''))

        # スピード指数（過去5走平均）
        features['speed_index_avg'] = self._calc_speed_index_avg(past_races)
        features['speed_index_max'] = self._calc_speed_index_max(past_races)
        features['speed_index_recent'] = self._calc_speed_index_recent(past_races)

        # 上がり3F
        features['last3f_time_avg'] = self._calc_last3f_avg(past_races)
        features['last3f_rank_avg'] = self._calc_last3f_rank_avg(past_races)

        # 脚質
        features['running_style'] = self._determine_running_style(past_races)
        features['position_avg_3f'] = self._calc_corner_avg(past_races, 'corner3_juni')
        features['position_avg_4f'] = self._calc_corner_avg(past_races, 'corner4_juni')

        # 勝率・複勝率
        features['win_rate'] = self._calc_win_rate(past_races)
        features['place_rate'] = self._calc_place_rate(past_races)
        features['win_count'] = self._count_wins(past_races)

        # 休養日数
        features['days_since_last_race'] = self._calc_days_since_last(past_races, race_info)

        # ===== 騎手成績 =====
        jockey_code = entry.get('kishu_code', '')
        jockey_stats = self._get_jockey_stats(jockey_code)
        features['jockey_win_rate'] = jockey_stats.get('win_rate', 0.08)
        features['jockey_place_rate'] = jockey_stats.get('place_rate', 0.25)

        # ===== 調教師成績 =====
        trainer_code = entry.get('chokyoshi_code', '')
        trainer_stats = self._get_trainer_stats(trainer_code)
        features['trainer_win_rate'] = trainer_stats.get('win_rate', 0.08)
        features['trainer_place_rate'] = trainer_stats.get('place_rate', 0.25)

        # ===== コース・距離適性 =====
        features['course_fit_score'] = self._calc_course_fit(
            past_races, race_info.get('keibajo_code', '')
        )
        features['distance_fit_score'] = self._calc_distance_fit(
            past_races, self._safe_int(race_info.get('kyori'), 1600)
        )

        # ===== クラス =====
        features['class_rank'] = self._determine_class_rank(race_info)

        # ===== 出走頭数 =====
        features['field_size'] = len(all_entries)

        # ===== 枠順バイアス（簡易版）=====
        features['waku_bias'] = self._calc_waku_bias(features['wakuban'], race_info)

        return features

    def _get_past_races(self, kettonum: str, current_race_code: str, limit: int = 10) -> List[Dict]:
        """過去レース成績を取得"""
        if not kettonum:
            return []

        cache_key = f"past_{kettonum}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                race_code,
                kaisai_nen,
                kaisai_gappi,
                keibajo_code,
                kakutei_chakujun,
                soha_time,
                kohan_3f,
                kohan_4f,
                corner1_juni,
                corner2_juni,
                corner3_juni,
                corner4_juni,
                tansho_ninkijun,
                futan_juryo,
                bataiju
            FROM umagoto_race_joho
            WHERE ketto_toroku_bango = %s
              AND data_kubun = '7'
              AND race_code < %s
              AND kakutei_chakujun ~ '^[0-9]+$'
            ORDER BY kaisai_nen DESC, kaisai_gappi DESC
            LIMIT %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum, current_race_code, limit))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            cur.close()
            result = [dict(zip(columns, row)) for row in rows]
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Failed to get past races: {e}")
            self.conn.rollback()
            return []

    def _get_jockey_stats(self, jockey_code: str) -> Dict:
        """騎手成績を取得"""
        if not jockey_code:
            return {'win_rate': 0.08, 'place_rate': 0.25}

        cache_key = f"jockey_{jockey_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 直近1年の成績を集計
        sql = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01', '02', '03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE kishu_code = %s
              AND data_kubun = '7'
              AND kaisai_nen >= %s
              AND kakutei_chakujun ~ '^[0-9]+$'
        """
        try:
            cur = self.conn.cursor()
            year_back = str(date.today().year - 1)
            cur.execute(sql, (jockey_code, year_back))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                total, wins, places = row
                result = {
                    'win_rate': wins / total if total > 0 else 0.08,
                    'place_rate': places / total if total > 0 else 0.25
                }
            else:
                result = {'win_rate': 0.08, 'place_rate': 0.25}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Failed to get jockey stats: {e}")
            self.conn.rollback()
            return {'win_rate': 0.08, 'place_rate': 0.25}

    def _get_trainer_stats(self, trainer_code: str) -> Dict:
        """調教師成績を取得"""
        if not trainer_code:
            return {'win_rate': 0.08, 'place_rate': 0.25}

        cache_key = f"trainer_{trainer_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01', '02', '03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE chokyoshi_code = %s
              AND data_kubun = '7'
              AND kaisai_nen >= %s
              AND kakutei_chakujun ~ '^[0-9]+$'
        """
        try:
            cur = self.conn.cursor()
            year_back = str(date.today().year - 1)
            cur.execute(sql, (trainer_code, year_back))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                total, wins, places = row
                result = {
                    'win_rate': wins / total if total > 0 else 0.08,
                    'place_rate': places / total if total > 0 else 0.25
                }
            else:
                result = {'win_rate': 0.08, 'place_rate': 0.25}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Failed to get trainer stats: {e}")
            self.conn.rollback()
            return {'win_rate': 0.08, 'place_rate': 0.25}

    # ===== ヘルパーメソッド =====

    def _safe_int(self, val, default: int = 0) -> int:
        """安全にintに変換"""
        try:
            if val is None or val == '':
                return default
            return int(val)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, val, default: float = 0.0) -> float:
        """安全にfloatに変換"""
        try:
            if val is None or val == '':
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    def _encode_sex(self, sex_code: str) -> int:
        """性別エンコード（0: 牡, 1: 牝, 2: セン）"""
        mapping = {'1': 0, '2': 1, '3': 2}  # 1:牡, 2:牝, 3:セン
        return mapping.get(sex_code, 0)

    def _calc_speed_index_avg(self, past_races: List[Dict], n: int = 5) -> float:
        """スピード指数平均（簡易版：タイム基準）"""
        if not past_races:
            return 80.0

        times = []
        for race in past_races[:n]:
            time_str = race.get('soha_time', '')
            if time_str and time_str.isdigit():
                # タイムを秒に変換（MMSSs形式）
                time_val = int(time_str)
                minutes = time_val // 1000
                seconds = (time_val % 1000) / 10
                total_seconds = minutes * 60 + seconds
                # 簡易スピード指数（基準タイム90秒として）
                speed_index = 100 - (total_seconds - 90) * 2
                times.append(max(50, min(120, speed_index)))

        return np.mean(times) if times else 80.0

    def _calc_speed_index_max(self, past_races: List[Dict], n: int = 5) -> float:
        """スピード指数最高値"""
        if not past_races:
            return 85.0

        times = []
        for race in past_races[:n]:
            time_str = race.get('soha_time', '')
            if time_str and time_str.isdigit():
                time_val = int(time_str)
                minutes = time_val // 1000
                seconds = (time_val % 1000) / 10
                total_seconds = minutes * 60 + seconds
                speed_index = 100 - (total_seconds - 90) * 2
                times.append(max(50, min(120, speed_index)))

        return max(times) if times else 85.0

    def _calc_speed_index_recent(self, past_races: List[Dict]) -> float:
        """直近レースのスピード指数"""
        if not past_races:
            return 80.0
        return self._calc_speed_index_avg(past_races[:1], 1)

    def _calc_last3f_avg(self, past_races: List[Dict], n: int = 5) -> float:
        """上がり3F平均タイム"""
        if not past_races:
            return 35.0

        times = []
        for race in past_races[:n]:
            l3f = race.get('kohan_3f', '')
            if l3f and l3f.isdigit():
                times.append(int(l3f) / 10.0)

        return np.mean(times) if times else 35.0

    def _calc_last3f_rank_avg(self, past_races: List[Dict], n: int = 5) -> float:
        """上がり3F順位平均（簡易版）"""
        # 実際のデータには上がり順位がないため、タイムから推定
        return 5.0  # デフォルト値

    def _determine_running_style(self, past_races: List[Dict]) -> int:
        """脚質判定（1:逃げ, 2:先行, 3:差し, 4:追込）"""
        if not past_races:
            return 2  # デフォルト：先行

        avg_pos = []
        for race in past_races[:5]:
            c3 = self._safe_int(race.get('corner3_juni'), 0)
            if c3 > 0:
                avg_pos.append(c3)

        if not avg_pos:
            return 2

        avg = np.mean(avg_pos)
        if avg <= 2:
            return 1  # 逃げ
        elif avg <= 5:
            return 2  # 先行
        elif avg <= 10:
            return 3  # 差し
        else:
            return 4  # 追込

    def _calc_corner_avg(self, past_races: List[Dict], corner_col: str) -> float:
        """コーナー通過順位平均"""
        if not past_races:
            return 8.0

        positions = []
        for race in past_races[:5]:
            pos = self._safe_int(race.get(corner_col), 0)
            if pos > 0:
                positions.append(pos)

        return np.mean(positions) if positions else 8.0

    def _calc_win_rate(self, past_races: List[Dict]) -> float:
        """勝率"""
        if not past_races:
            return 0.0

        wins = sum(1 for r in past_races if self._safe_int(r.get('kakutei_chakujun'), 99) == 1)
        return wins / len(past_races)

    def _calc_place_rate(self, past_races: List[Dict]) -> float:
        """複勝率"""
        if not past_races:
            return 0.0

        places = sum(1 for r in past_races if self._safe_int(r.get('kakutei_chakujun'), 99) <= 3)
        return places / len(past_races)

    def _count_wins(self, past_races: List[Dict]) -> int:
        """勝利数"""
        return sum(1 for r in past_races if self._safe_int(r.get('kakutei_chakujun'), 99) == 1)

    def _calc_days_since_last(self, past_races: List[Dict], race_info: Dict) -> int:
        """前走からの日数"""
        if not past_races:
            return 60  # デフォルト

        try:
            current_year = race_info.get('kaisai_nen', '')
            current_date = race_info.get('kaisai_gappi', '')
            last_year = past_races[0].get('kaisai_nen', '')
            last_date = past_races[0].get('kaisai_gappi', '')

            if not all([current_year, current_date, last_year, last_date]):
                return 60

            current = date(int(current_year), int(current_date[:2]), int(current_date[2:]))
            last = date(int(last_year), int(last_date[:2]), int(last_date[2:]))
            return (current - last).days
        except Exception:
            return 60

    def _calc_course_fit(self, past_races: List[Dict], keibajo_code: str) -> float:
        """コース適性（同競馬場での成績）"""
        if not past_races or not keibajo_code:
            return 0.5

        same_course = [r for r in past_races if r.get('keibajo_code') == keibajo_code]
        if not same_course:
            return 0.5

        places = sum(1 for r in same_course if self._safe_int(r.get('kakutei_chakujun'), 99) <= 3)
        return places / len(same_course)

    def _calc_distance_fit(self, past_races: List[Dict], target_distance: int) -> float:
        """距離適性（±200m以内での成績）"""
        if not past_races:
            return 0.5

        # 距離データはrace_infoからJOINが必要だが、簡易版では省略
        return 0.5  # デフォルト

    def _determine_class_rank(self, race_info: Dict) -> int:
        """クラスランク（1-8）"""
        grade = race_info.get('grade_code', '')
        mapping = {
            'A': 8,  # G1
            'B': 7,  # G2
            'C': 6,  # G3
            'D': 5,  # Listed
            'E': 4,  # OP
            'F': 3,  # 3勝
            'G': 2,  # 2勝
            'H': 1,  # 1勝
        }
        return mapping.get(grade, 3)

    def _calc_waku_bias(self, wakuban: int, race_info: Dict) -> float:
        """枠順バイアス（簡易版）"""
        # 内枠有利を仮定（-0.1〜0.1）
        return (wakuban - 4.5) * 0.02

    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache = {}
