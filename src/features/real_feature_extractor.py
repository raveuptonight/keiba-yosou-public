"""
実データベースからの特徴量抽出モジュール

JRA-VAN mykeibadb から特徴量を取得

拡張特徴量（v2）:
- 血統（父馬/母父馬の産駒成績）
- 前走情報の詳細（着順、人気、上がり3F順位、コーナー通過）
- 競馬場別成績
- 展開予想の強化
- トレンド系（着順推移、騎手の調子）
- 季節・時期
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import date, timedelta
import numpy as np

from src.features.enhanced_features import EnhancedFeatureExtractor

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
        self._enhanced_extractor = EnhancedFeatureExtractor(db_connection)

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

        # 全馬の脚質を事前計算（展開予想用）
        running_styles = {}
        for entry in entries:
            kettonum = entry.get('ketto_toroku_bango', '')
            past_races = self._get_past_races(kettonum, race_code)
            running_styles[kettonum] = self._determine_running_style(past_races)

        # 展開予想を事前計算
        pace_info = self._calc_pace_prediction(entries, race_info)

        features_list = []
        for entry in entries:
            features = self._extract_horse_features(
                entry, race_info, entries, pace_info, running_styles
            )
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
        all_entries: List[Dict],
        pace_info: Dict = None,
        running_styles: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """各馬の特徴量を抽出"""
        features = {}
        kettonum = entry.get('ketto_toroku_bango', '')

        # 脚質辞書がない場合は空辞書
        if running_styles is None:
            running_styles = {}

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
        track_code = race_info.get('track_code', '')
        is_turf = track_code.startswith('1') if track_code else True
        baba_code = race_info.get('shiba_babajotai_code', '1') if is_turf else race_info.get('dirt_babajotai_code', '1')

        baba_stats = self._get_baba_stats(
            kettonum, race_info.get('race_code', ''),
            track_code,
            baba_code
        )
        features['baba_win_rate'] = baba_stats.get('win_rate', 0.0)
        features['baba_place_rate'] = baba_stats.get('place_rate', 0.0)
        features['baba_runs'] = baba_stats.get('runs', 0)

        # 馬場状態エンコーディング（1=良, 2=稍重, 3=重, 4=不良）
        features['baba_condition'] = self._safe_int(baba_code, 1)

        # ===== 調教詳細（坂路/ウッド）=====
        detailed_training = self._get_detailed_training(kettonum, race_info.get('race_code', ''))
        features['training_time_3f'] = detailed_training.get('time_3f', 38.0)
        features['training_lap_1f'] = detailed_training.get('lap_1f', 12.5)
        features['training_days_before'] = detailed_training.get('days_before', 7)

        # ===== コーナー別成績 =====
        features['right_turn_rate'] = self._calc_turn_rate(past_races, is_right=True)
        features['left_turn_rate'] = self._calc_turn_rate(past_races, is_right=False)

        # ===== 間隔カテゴリ別成績 =====
        days_since = features['days_since_last_race']
        interval_cat = self._get_interval_category(days_since)
        interval_stats = self._get_interval_stats(kettonum, interval_cat)
        features['interval_win_rate'] = interval_stats.get('win_rate', features['win_rate'])
        features['interval_place_rate'] = interval_stats.get('place_rate', features['place_rate'])
        features['interval_runs'] = interval_stats.get('runs', 0)

        # 間隔カテゴリ（エンコード: 1=連闘, 2=中1週, 3=中2週, 4=中3週, 5=中4週以上）
        interval_cat_map = {'rentou': 1, 'week1': 2, 'week2': 3, 'week3': 4, 'week4plus': 5}
        features['interval_category'] = interval_cat_map.get(interval_cat, 5)

        # ===== 展開予想 =====
        if pace_info:
            features['pace_maker_count'] = pace_info.get('pace_maker_count', 1)
            features['senkou_count'] = pace_info.get('senkou_count', 3)
            features['sashi_count'] = pace_info.get('sashi_count', 5)
            features['pace_type'] = pace_info.get('pace_type', 2)
        else:
            features['pace_maker_count'] = 1
            features['senkou_count'] = 3
            features['sashi_count'] = 5
            features['pace_type'] = 2

        # ===== 脚質×展開相性 =====
        running_style = features['running_style']
        pace_type = features['pace_type']
        features['style_pace_compatibility'] = self._calc_style_pace_compatibility(running_style, pace_type)

        # ===== 拡張特徴量（v2）=====
        try:
            # 現在の人気（予想時は未確定なのでNone）
            current_ninki = self._safe_int(entry.get('tansho_ninkijun'), None)

            enhanced_features = self._enhanced_extractor.extract_all_enhanced_features(
                entry=entry,
                race_info=race_info,
                all_entries=all_entries,
                running_styles=running_styles,
                current_ninki=current_ninki
            )
            features.update(enhanced_features)
        except Exception as e:
            logger.warning(f"Failed to extract enhanced features: {e}")
            # 拡張特徴量が取得できなくてもデフォルト値で継続
            features.update(self._get_default_enhanced_features())

        return features

    def _get_default_enhanced_features(self) -> Dict[str, Any]:
        """拡張特徴量のデフォルト値"""
        return {
            # 血統
            'sire_id_hash': 0,
            'broodmare_sire_id_hash': 0,
            'sire_distance_win_rate': 0.08,
            'sire_distance_place_rate': 0.25,
            'sire_distance_runs': 0,
            'sire_baba_win_rate': 0.08,
            'sire_baba_place_rate': 0.25,
            'sire_venue_win_rate': 0.08,
            'sire_venue_place_rate': 0.25,
            'broodmare_sire_win_rate': 0.08,
            'broodmare_sire_place_rate': 0.25,
            # 前走情報
            'zenso1_chakujun': 10,
            'zenso1_ninki': 10,
            'zenso1_ninki_diff': 0,
            'zenso1_class_diff': 0,
            'zenso1_agari_rank': 9,
            'zenso1_corner_avg': 8.0,
            'zenso1_distance': 1600,
            'zenso1_distance_diff': 0,
            'zenso2_chakujun': 10,
            'zenso3_chakujun': 10,
            'zenso_chakujun_trend': 0,
            'zenso_agari_trend': 0,
            # 競馬場別
            'venue_win_rate': 0.0,
            'venue_place_rate': 0.0,
            'venue_runs': 0,
            'small_track_place_rate': 0.25,
            'large_track_place_rate': 0.25,
            'track_type_fit': 0.25,
            # 展開強化
            'inner_nige_count': 0,
            'inner_senkou_count': 0,
            'waku_style_advantage': 0.0,
            # トレンド
            'jockey_recent_win_rate': 0.08,
            'jockey_recent_place_rate': 0.25,
            'jockey_recent_runs': 0,
            # 季節・時期
            'race_month': 6,
            'month_sin': 0.0,
            'month_cos': 1.0,
            'kaisai_week': 2,
            'growth_period': 0,
            'is_winter': 0,
        }

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

    def _get_interval_stats(self, kettonum: str, interval_cat: str) -> Dict:
        """間隔カテゴリ別成績を取得"""
        if not kettonum:
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache_key = f"interval_{kettonum}_{interval_cat}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 間隔カテゴリの日数範囲
        interval_ranges = {
            'rentou': (1, 7),
            'week1': (8, 14),
            'week2': (15, 21),
            'week3': (22, 28),
            'week4plus': (29, 365)
        }
        min_days, max_days = interval_ranges.get(interval_cat, (29, 365))

        sql = """
            WITH race_intervals AS (
                SELECT
                    ketto_toroku_bango,
                    kakutei_chakujun,
                    DATE(CONCAT(kaisai_nen, '-', SUBSTRING(kaisai_gappi, 1, 2), '-', SUBSTRING(kaisai_gappi, 3, 2)))
                    - LAG(DATE(CONCAT(kaisai_nen, '-', SUBSTRING(kaisai_gappi, 1, 2), '-', SUBSTRING(kaisai_gappi, 3, 2))))
                      OVER (PARTITION BY ketto_toroku_bango ORDER BY race_code) as interval_days
                FROM umagoto_race_joho
                WHERE ketto_toroku_bango = %s
                  AND data_kubun = '7'
                  AND kakutei_chakujun ~ '^[0-9]+$'
            )
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM race_intervals
            WHERE interval_days >= %s AND interval_days <= %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum, min_days, max_days))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                runs = int(row[0])
                wins = int(row[1] or 0)
                places = int(row[2] or 0)
                result = {
                    'runs': runs,
                    'win_rate': wins / runs if runs > 0 else 0.0,
                    'place_rate': places / runs if runs > 0 else 0.0
                }
            else:
                result = {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Interval stats not available: {e}")
            self.conn.rollback()
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    def _calc_pace_prediction(self, entries: List[Dict], race_info: Dict) -> Dict:
        """
        展開予想を計算

        Returns:
            pace_maker_count: 逃げ馬の数
            senkou_count: 先行馬の数
            sashi_count: 差し馬の数
            pace_type: 1=スロー, 2=ミドル, 3=ハイ
        """
        pace_makers = 0
        senkou_count = 0
        sashi_count = 0
        oikomi_count = 0

        for entry in entries:
            kettonum = entry.get('ketto_toroku_bango', '')
            past_races = self._get_past_races(kettonum, race_info.get('race_code', ''), limit=5)
            style = self._determine_running_style(past_races)

            if style == 1:  # 逃げ
                pace_makers += 1
            elif style == 2:  # 先行
                senkou_count += 1
            elif style == 3:  # 差し
                sashi_count += 1
            else:  # 追込
                oikomi_count += 1

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

    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache = {}
        if self._enhanced_extractor:
            self._enhanced_extractor.clear_cache()

    def inject_bias_features(
        self,
        features_list: List[Dict[str, Any]],
        bias_result: 'DailyBiasResult',
        venue_code: str
    ) -> List[Dict[str, Any]]:
        """
        バイアス特徴量を注入

        Args:
            features_list: 各馬の特徴量リスト
            bias_result: 日次バイアス分析結果
            venue_code: 競馬場コード

        Returns:
            バイアス特徴量が追加された特徴量リスト
        """
        from src.features.daily_bias import DailyBiasResult, VenueBias

        if bias_result is None:
            # バイアスデータがない場合はデフォルト値を設定
            for features in features_list:
                features['bias_waku'] = 0.0
                features['bias_waku_adjusted'] = 0.0
                features['bias_pace'] = 0.0
                features['bias_pace_front'] = 0.0
                features['bias_jockey_today_win'] = 0.0
                features['bias_jockey_today_top3'] = 0.0
            return features_list

        # 競馬場バイアスを取得
        venue_bias = bias_result.venue_biases.get(venue_code)

        for features in features_list:
            wakuban = features.get('wakuban', 0)
            running_style = features.get('running_style', 2)

            # 枠順バイアス
            if venue_bias:
                # 枠番に応じたバイアス値
                if 1 <= wakuban <= 4:
                    # 内枠の馬には内枠有利度を適用
                    features['bias_waku'] = venue_bias.waku_bias
                    features['bias_waku_adjusted'] = venue_bias.inner_waku_win_rate
                else:
                    # 外枠の馬には外枠有利度を適用
                    features['bias_waku'] = -venue_bias.waku_bias
                    features['bias_waku_adjusted'] = venue_bias.outer_waku_win_rate

                # 脚質バイアス
                features['bias_pace'] = venue_bias.pace_bias
                if running_style in (1, 2):  # 逃げ・先行
                    features['bias_pace_front'] = venue_bias.zenso_win_rate
                else:  # 差し・追込
                    features['bias_pace_front'] = venue_bias.koshi_win_rate
            else:
                features['bias_waku'] = 0.0
                features['bias_waku_adjusted'] = 0.0
                features['bias_pace'] = 0.0
                features['bias_pace_front'] = 0.0

            # 騎手当日成績
            # 騎手コードはentryから取得する必要があるが、featuresに含まれていない
            # ここでは別途対応が必要
            features['bias_jockey_today_win'] = 0.0
            features['bias_jockey_today_top3'] = 0.0

        return features_list

    def inject_jockey_bias(
        self,
        features: Dict[str, Any],
        bias_result: 'DailyBiasResult',
        kishu_code: str
    ) -> Dict[str, Any]:
        """
        騎手バイアスを個別に注入

        Args:
            features: 馬の特徴量
            bias_result: 日次バイアス分析結果
            kishu_code: 騎手コード

        Returns:
            バイアスが追加された特徴量
        """
        if bias_result is None or not kishu_code:
            features['bias_jockey_today_win'] = 0.0
            features['bias_jockey_today_top3'] = 0.0
            return features

        jockey_perf = bias_result.jockey_performances.get(kishu_code)
        if jockey_perf:
            features['bias_jockey_today_win'] = jockey_perf.win_rate
            features['bias_jockey_today_top3'] = jockey_perf.top3_rate
        else:
            features['bias_jockey_today_win'] = 0.0
            features['bias_jockey_today_top3'] = 0.0

        return features
