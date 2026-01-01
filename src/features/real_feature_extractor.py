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

        # ※ オッズ・人気は意図的に除外（市場評価に頼らず実力で予測する）

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

        # ===== 騎手・馬コンビ成績 =====
        jockey_horse_stats = self._get_jockey_horse_combo(jockey_code, kettonum)
        features['jockey_horse_runs'] = jockey_horse_stats.get('runs', 0)
        features['jockey_horse_wins'] = jockey_horse_stats.get('wins', 0)
        features['jockey_change'] = 1 if self._is_jockey_changed(past_races, jockey_code) else 0

        # ===== 調教データ =====
        training_data = self._get_training_data(kettonum, race_info.get('race_code', ''))
        features['training_score'] = training_data.get('score', 50.0)
        features['training_time_4f'] = training_data.get('time_4f', 52.0)
        features['training_count'] = training_data.get('count', 0)

        # ===== 距離変更 =====
        features['distance_change'] = self._calc_distance_change(past_races, race_info)

        # ===== 馬場適性 =====
        track_code = race_info.get('track_code', '')
        features['is_turf'] = 1 if track_code.startswith('1') else 0  # 1x = 芝
        features['turf_win_rate'] = self._calc_surface_rate(past_races, is_turf=True)
        features['dirt_win_rate'] = self._calc_surface_rate(past_races, is_turf=False)

        # ===== クラス昇降 =====
        features['class_change'] = self._calc_class_change(past_races, race_info)

        # ===== 着差・タイム差 =====
        features['avg_time_diff'] = self._calc_avg_time_diff(past_races)
        features['best_finish'] = self._get_best_finish(past_races)

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

        # ===== 距離別成績（shussobetsu_kyori）=====
        distance_stats = self._get_distance_stats(
            kettonum, race_info.get('race_code', ''),
            self._safe_int(race_info.get('kyori'), 1600),
            race_info.get('track_code', '')
        )
        features['distance_cat_win_rate'] = distance_stats.get('win_rate', 0.0)
        features['distance_cat_place_rate'] = distance_stats.get('place_rate', 0.0)
        features['distance_cat_runs'] = distance_stats.get('runs', 0)

        # ===== 馬場状態別成績（shussobetsu_baba）=====
        baba_stats = self._get_baba_stats(
            kettonum, race_info.get('race_code', ''),
            race_info.get('track_code', ''),
            race_info.get('shiba_baba_code', '') or race_info.get('dirt_baba_code', '')
        )
        features['baba_win_rate'] = baba_stats.get('win_rate', 0.0)
        features['baba_place_rate'] = baba_stats.get('place_rate', 0.0)
        features['baba_runs'] = baba_stats.get('runs', 0)

        # ===== 調教詳細（坂路/ウッド）=====
        detailed_training = self._get_detailed_training(kettonum, race_info.get('race_code', ''))
        features['training_time_3f'] = detailed_training.get('time_3f', 38.0)
        features['training_lap_1f'] = detailed_training.get('lap_1f', 12.5)
        features['training_days_before'] = detailed_training.get('days_before', 7)

        # ===== コーナー別成績 =====
        features['right_turn_rate'] = self._calc_turn_rate(past_races, is_right=True)
        features['left_turn_rate'] = self._calc_turn_rate(past_races, is_right=False)

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

    def _get_jockey_horse_combo(self, jockey_code: str, kettonum: str) -> Dict:
        """騎手・馬コンビの成績を取得"""
        if not jockey_code or not kettonum:
            return {'runs': 0, 'wins': 0}

        cache_key = f"combo_{jockey_code}_{kettonum}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins
            FROM umagoto_race_joho
            WHERE kishu_code = %s
              AND ketto_toroku_bango = %s
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (jockey_code, kettonum))
            row = cur.fetchone()
            cur.close()

            result = {'runs': row[0] or 0, 'wins': row[1] or 0} if row else {'runs': 0, 'wins': 0}
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Failed to get jockey-horse combo: {e}")
            self.conn.rollback()
            return {'runs': 0, 'wins': 0}

    def _is_jockey_changed(self, past_races: List[Dict], current_jockey: str) -> bool:
        """騎手乗り替わりかどうか"""
        if not past_races or not current_jockey:
            return False
        last_jockey = past_races[0].get('kishu_code', '')
        return last_jockey != current_jockey

    def _get_training_data(self, kettonum: str, race_code: str) -> Dict:
        """調教データを取得"""
        if not kettonum:
            return {'score': 50.0, 'time_4f': 52.0, 'count': 0}

        cache_key = f"training_{kettonum}_{race_code[:8]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # レース日の2週間前までの調教を取得（簡易版）
        sql = """
            SELECT
                COUNT(*) as count,
                AVG(CAST(NULLIF(oikiri_shisu, '') AS INTEGER)) as avg_score
            FROM n_hanro_chokyo
            WHERE ketto_toroku_bango = %s
            LIMIT 10
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                result = {
                    'score': float(row[1]) if row[1] else 50.0,
                    'time_4f': 52.0,  # TODO: 実際のタイムを取得
                    'count': row[0]
                }
            else:
                result = {'score': 50.0, 'time_4f': 52.0, 'count': 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Training data not available: {e}")
            self.conn.rollback()
            return {'score': 50.0, 'time_4f': 52.0, 'count': 0}

    def _calc_distance_change(self, past_races: List[Dict], race_info: Dict) -> int:
        """前走からの距離変化（m）"""
        if not past_races:
            return 0

        current_dist = self._safe_int(race_info.get('kyori'), 0)
        # 過去レースの距離はJOINが必要なため、簡易版では0を返す
        return 0

    def _calc_surface_rate(self, past_races: List[Dict], is_turf: bool) -> float:
        """芝/ダート別の複勝率"""
        if not past_races:
            return 0.25

        # track_codeでフィルタ（1x=芝、2x=ダート）
        # 過去レースにtrack_codeがない場合は全体の複勝率を返す
        places = sum(1 for r in past_races if self._safe_int(r.get('kakutei_chakujun'), 99) <= 3)
        return places / len(past_races) if past_races else 0.25

    def _calc_class_change(self, past_races: List[Dict], race_info: Dict) -> int:
        """クラス昇降（-1:降級, 0:同級, 1:昇級）"""
        # 簡易版：前走との比較は複雑なため0を返す
        return 0

    def _calc_avg_time_diff(self, past_races: List[Dict]) -> float:
        """平均タイム差（勝ち馬との差、秒）"""
        if not past_races:
            return 1.0

        # タイム差データがない場合は着順から推定
        diffs = []
        for race in past_races[:5]:
            chakujun = self._safe_int(race.get('kakutei_chakujun'), 10)
            # 着順からタイム差を推定（1着=0秒、10着=2秒）
            estimated_diff = (chakujun - 1) * 0.2
            diffs.append(min(estimated_diff, 5.0))

        return np.mean(diffs) if diffs else 1.0

    def _get_best_finish(self, past_races: List[Dict]) -> int:
        """過去最高着順"""
        if not past_races:
            return 10

        finishes = [self._safe_int(r.get('kakutei_chakujun'), 99) for r in past_races]
        valid_finishes = [f for f in finishes if f < 99]
        return min(valid_finishes) if valid_finishes else 10

    def _get_distance_stats(self, kettonum: str, race_code: str, distance: int, track_code: str) -> Dict:
        """距離別成績を取得（shussobetsu_kyori）"""
        if not kettonum:
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache_key = f"dist_stats_{kettonum}_{distance}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 距離カテゴリを決定
        is_turf = track_code.startswith('1') if track_code else True
        prefix = 'shiba' if is_turf else 'dirt'

        if distance <= 1200:
            cat = '1200_ika'
        elif distance <= 1400:
            cat = '1201_1400'
        elif distance <= 1600:
            cat = '1401_1600'
        elif distance <= 1800:
            cat = '1601_1800'
        elif distance <= 2000:
            cat = '1801_2000'
        elif distance <= 2200:
            cat = '2001_2200'
        elif distance <= 2400:
            cat = '2201_2400'
        elif distance <= 2800:
            cat = '2401_2800'
        else:
            cat = '2801_ijo'

        col_prefix = f"{prefix}_{cat}"

        sql = f"""
            SELECT
                COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
                COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
                COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
                COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
                COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
                COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
            FROM shussobetsu_kyori
            WHERE ketto_toroku_bango = %s
            ORDER BY data_sakusei_nengappi DESC
            LIMIT 1
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            row = cur.fetchone()
            cur.close()

            if row:
                wins = row[0]
                places = row[0] + row[1] + row[2]
                total = sum(row)
                result = {
                    'win_rate': wins / total if total > 0 else 0.0,
                    'place_rate': places / total if total > 0 else 0.0,
                    'runs': total
                }
            else:
                result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Distance stats not available: {e}")
            self.conn.rollback()
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    def _get_baba_stats(self, kettonum: str, race_code: str, track_code: str, baba_code: str) -> Dict:
        """馬場状態別成績を取得（shussobetsu_baba）"""
        if not kettonum:
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache_key = f"baba_stats_{kettonum}_{baba_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 馬場状態を決定
        is_turf = track_code.startswith('1') if track_code else True
        prefix = 'shiba' if is_turf else 'dirt'

        # 馬場コード: 1=良, 2=稍重, 3=重, 4=不良
        baba_map = {'1': 'ryo', '2': 'yayaomo', '3': 'omo', '4': 'furyo'}
        baba_suffix = baba_map.get(str(baba_code), 'ryo')
        col_prefix = f"{prefix}_{baba_suffix}"

        sql = f"""
            SELECT
                COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
                COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
                COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
                COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
                COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
                COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
            FROM shussobetsu_baba
            WHERE ketto_toroku_bango = %s
            ORDER BY data_sakusei_nengappi DESC
            LIMIT 1
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            row = cur.fetchone()
            cur.close()

            if row:
                wins = row[0]
                places = row[0] + row[1] + row[2]
                total = sum(row)
                result = {
                    'win_rate': wins / total if total > 0 else 0.0,
                    'place_rate': places / total if total > 0 else 0.0,
                    'runs': total
                }
            else:
                result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Baba stats not available: {e}")
            self.conn.rollback()
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    def _get_detailed_training(self, kettonum: str, race_code: str) -> Dict:
        """詳細な調教データを取得（hanro_chokyo）"""
        if not kettonum:
            return {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}

        cache_key = f"detailed_training_{kettonum}_{race_code[:8]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # レース日付を取得してその前の調教を検索
        race_date = race_code[4:12] if len(race_code) >= 12 else ''

        sql = """
            SELECT
                chokyo_nengappi,
                COALESCE(NULLIF(time_gokei_3furlong, '')::int, 0) as time_3f,
                COALESCE(NULLIF(lap_time_1furlong, '')::int, 0) as lap_1f
            FROM hanro_chokyo
            WHERE ketto_toroku_bango = %s
            ORDER BY chokyo_nengappi DESC
            LIMIT 3
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            rows = cur.fetchall()
            cur.close()

            if rows:
                # 直近の調教データを使用
                time_3f = rows[0][1] / 10.0 if rows[0][1] else 38.0
                lap_1f = rows[0][2] / 10.0 if rows[0][2] else 12.5
                # 日数計算は簡易版
                days_before = 3 if rows else 7
                result = {
                    'time_3f': time_3f,
                    'lap_1f': lap_1f,
                    'days_before': days_before
                }
            else:
                result = {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Detailed training not available: {e}")
            self.conn.rollback()
            return {'time_3f': 38.0, 'lap_1f': 12.5, 'days_before': 7}

    def _calc_turn_rate(self, past_races: List[Dict], is_right: bool) -> float:
        """右/左回りコースでの複勝率"""
        if not past_races:
            return 0.25

        # 右回り: 札幌(01), 函館(02), 福島(03), 中山(06), 阪神(09), 小倉(10)
        # 左回り: 新潟(04), 東京(05), 中京(07), 京都(08)
        right_courses = {'01', '02', '03', '06', '09', '10'}
        left_courses = {'04', '05', '07', '08'}

        target_courses = right_courses if is_right else left_courses
        filtered = [r for r in past_races if r.get('keibajo_code') in target_courses]

        if not filtered:
            return 0.25

        places = sum(1 for r in filtered if self._safe_int(r.get('kakutei_chakujun'), 99) <= 3)
        return places / len(filtered)

    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache = {}
