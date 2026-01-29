"""
拡張特徴量モジュール

追加特徴量:
1. 血統（父馬/母父馬の成績）
2. 前走情報の詳細（着順、人気、上がり、コーナー通過）
3. 競馬場別成績
4. 展開予想の強化
5. トレンド系（着順推移、騎手の調子）
6. 季節・時期
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import date
import numpy as np

logger = logging.getLogger(__name__)


class EnhancedFeatureExtractor:
    """拡張特徴量抽出クラス"""

    # 競馬場コード → 名前マッピング
    VENUE_CODES = {
        '01': 'sapporo', '02': 'hakodate', '03': 'fukushima', '04': 'niigata',
        '05': 'tokyo', '06': 'nakayama', '07': 'chukyo', '08': 'kyoto',
        '09': 'hanshin', '10': 'kokura'
    }

    # 小回りコース（内回り中心）
    SMALL_TRACK_VENUES = {'01', '02', '03', '06', '10'}  # 札幌,函館,福島,中山,小倉

    # 右回り/左回り
    RIGHT_TURN_VENUES = {'01', '02', '03', '06', '09', '10'}
    LEFT_TURN_VENUES = {'04', '05', '07', '08'}

    def __init__(self, db_connection):
        self.conn = db_connection
        self._cache = {}
        self._sire_stats_cache = {}

    # ========================================
    # 1. 血統特徴量
    # ========================================

    def get_pedigree_info(self, kettonum: str) -> Dict[str, Any]:
        """血統情報を取得（父馬ID、母父馬ID）"""
        if not kettonum:
            return {'sire_id': '', 'broodmare_sire_id': ''}

        cache_key = f"pedigree_{kettonum}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                ketto1_hanshoku_toroku_bango as sire_id,
                ketto3_hanshoku_toroku_bango as broodmare_sire_id,
                ketto1_bamei as sire_name,
                ketto3_bamei as broodmare_sire_name
            FROM kyosoba_master2
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
                result = {
                    'sire_id': row[0] or '',
                    'broodmare_sire_id': row[1] or '',
                    'sire_name': row[2] or '',
                    'broodmare_sire_name': row[3] or ''
                }
            else:
                result = {'sire_id': '', 'broodmare_sire_id': '', 'sire_name': '', 'broodmare_sire_name': ''}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get pedigree info: {e}")
            self.conn.rollback()
            return {'sire_id': '', 'broodmare_sire_id': '', 'sire_name': '', 'broodmare_sire_name': ''}

    def get_sire_stats(
        self,
        sire_id: str,
        distance: int = None,
        baba_code: str = None,
        venue_code: str = None,
        is_turf: bool = True
    ) -> Dict[str, float]:
        """
        種牡馬の産駒成績を取得

        Args:
            sire_id: 種牡馬の繁殖登録番号
            distance: 距離（m）- 指定時は±200m範囲でフィルタ
            baba_code: 馬場状態コード（1=良, 2=稍重, 3=重, 4=不良）
            venue_code: 競馬場コード
            is_turf: 芝コースかどうか

        Returns:
            勝率、複勝率、出走数を含む辞書
        """
        if not sire_id:
            return {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

        # キャッシュキー生成
        cache_key = f"sire_{sire_id}_{distance}_{baba_code}_{venue_code}_{is_turf}"
        if cache_key in self._sire_stats_cache:
            return self._sire_stats_cache[cache_key]

        # 条件構築
        conditions = ["k.ketto1_hanshoku_toroku_bango = %s"]
        params = [sire_id]

        # 芝/ダート条件
        track_prefix = '1' if is_turf else '2'
        conditions.append(f"r.track_code LIKE '{track_prefix}%'")

        # 距離条件（±200m）
        if distance:
            conditions.append("r.kyori::int BETWEEN %s AND %s")
            params.extend([distance - 200, distance + 200])

        # 馬場状態条件
        if baba_code:
            if is_turf:
                conditions.append("r.shiba_babajotai_code = %s")
            else:
                conditions.append("r.dirt_babajotai_code = %s")
            params.append(baba_code)

        # 競馬場条件
        if venue_code:
            conditions.append("r.keibajo_code = %s")
            params.append(venue_code)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
            JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
            WHERE {where_clause}
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.kaisai_nen >= %s
        """
        params.append(str(date.today().year - 3))  # 直近3年

        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                runs, wins, places = row
                result = {
                    'win_rate': wins / runs if runs > 0 else 0.08,
                    'place_rate': places / runs if runs > 0 else 0.25,
                    'runs': runs
                }
            else:
                result = {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

            self._sire_stats_cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get sire stats: {e}")
            self.conn.rollback()
            return {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

    def extract_pedigree_features(
        self,
        kettonum: str,
        race_info: Dict
    ) -> Dict[str, Any]:
        """血統関連特徴量を抽出"""
        features = {}

        # 血統情報取得
        pedigree = self.get_pedigree_info(kettonum)
        sire_id = pedigree.get('sire_id', '')
        broodmare_sire_id = pedigree.get('broodmare_sire_id', '')

        # IDはハッシュ化してカテゴリ特徴量に
        features['sire_id_hash'] = hash(sire_id) % 10000 if sire_id else 0
        features['broodmare_sire_id_hash'] = hash(broodmare_sire_id) % 10000 if broodmare_sire_id else 0

        # レース条件
        distance = self._safe_int(race_info.get('kyori'), 1600)
        track_code = race_info.get('track_code', '')
        is_turf = track_code.startswith('1') if track_code else True
        baba_code = race_info.get('shiba_babajotai_code', '1') if is_turf else race_info.get('dirt_babajotai_code', '1')
        venue_code = race_info.get('keibajo_code', '')

        # 父馬×距離成績
        sire_dist_stats = self.get_sire_stats(sire_id, distance=distance, is_turf=is_turf)
        features['sire_distance_win_rate'] = sire_dist_stats['win_rate']
        features['sire_distance_place_rate'] = sire_dist_stats['place_rate']
        features['sire_distance_runs'] = min(sire_dist_stats['runs'], 500)  # 上限

        # 父馬×馬場状態成績
        sire_baba_stats = self.get_sire_stats(sire_id, baba_code=baba_code, is_turf=is_turf)
        features['sire_baba_win_rate'] = sire_baba_stats['win_rate']
        features['sire_baba_place_rate'] = sire_baba_stats['place_rate']

        # 父馬×競馬場成績
        sire_venue_stats = self.get_sire_stats(sire_id, venue_code=venue_code, is_turf=is_turf)
        features['sire_venue_win_rate'] = sire_venue_stats['win_rate']
        features['sire_venue_place_rate'] = sire_venue_stats['place_rate']

        # 母父馬の全体成績（簡易版）
        bms_stats = self.get_sire_stats(broodmare_sire_id, is_turf=is_turf)
        features['broodmare_sire_win_rate'] = bms_stats['win_rate']
        features['broodmare_sire_place_rate'] = bms_stats['place_rate']

        return features

    # ========================================
    # 2. 前走情報の詳細
    # ========================================

    def get_past_races_detailed(
        self,
        kettonum: str,
        current_race_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """詳細な過去レース情報を取得（距離、クラス含む）"""
        if not kettonum:
            return []

        cache_key = f"past_detailed_{kettonum}_{current_race_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                u.race_code,
                u.kaisai_nen,
                u.kaisai_gappi,
                u.keibajo_code,
                u.kakutei_chakujun,
                u.tansho_ninkijun,
                u.soha_time,
                u.kohan_3f,
                u.corner1_juni,
                u.corner2_juni,
                u.corner3_juni,
                u.corner4_juni,
                u.futan_juryo,
                u.bataiju,
                u.kishu_code,
                r.kyori,
                r.track_code,
                r.grade_code,
                r.shiba_babajotai_code,
                r.dirt_babajotai_code
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
            WHERE u.ketto_toroku_bango = %s
              AND u.data_kubun = '7'
              AND u.race_code < %s
              AND u.kakutei_chakujun ~ '^[0-9]+$'
            ORDER BY u.race_code DESC
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
            logger.debug(f"Failed to get detailed past races: {e}")
            self.conn.rollback()
            return []

    def calc_agari_3f_rank(self, race_code: str, kohan_3f: str) -> int:
        """上がり3F順位を計算"""
        if not race_code or not kohan_3f:
            return 9

        cache_key = f"agari_rank_{race_code}_{kohan_3f}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT kohan_3f
            FROM umagoto_race_joho
            WHERE race_code = %s
              AND data_kubun = '7'
              AND kohan_3f ~ '^[0-9]+$'
            ORDER BY kohan_3f::int ASC
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (race_code,))
            rows = cur.fetchall()
            cur.close()

            rank = 1
            for row in rows:
                if row[0] == kohan_3f:
                    self._cache[cache_key] = rank
                    return rank
                rank += 1

            self._cache[cache_key] = 9
            return 9
        except Exception as e:
            logger.debug(f"Failed to calc agari rank: {e}")
            self.conn.rollback()
            return 9

    def extract_zenso_features(
        self,
        kettonum: str,
        current_race_code: str,
        race_info: Dict,
        current_ninki: int = None
    ) -> Dict[str, Any]:
        """前走情報特徴量を抽出"""
        features = {}
        past_races = self.get_past_races_detailed(kettonum, current_race_code, limit=5)

        # 前走がない場合のデフォルト
        if not past_races:
            features['zenso1_chakujun'] = 10
            features['zenso1_ninki'] = 10
            features['zenso1_ninki_diff'] = 0
            features['zenso1_class_diff'] = 0
            features['zenso1_agari_rank'] = 9
            features['zenso1_corner_avg'] = 8.0
            features['zenso1_distance'] = 1600
            features['zenso1_distance_diff'] = 0
            features['zenso2_chakujun'] = 10
            features['zenso3_chakujun'] = 10
            features['zenso_chakujun_trend'] = 0  # 0=データなし
            features['zenso_agari_trend'] = 0
            return features

        # 前走（1走前）
        z1 = past_races[0]
        features['zenso1_chakujun'] = self._safe_int(z1.get('kakutei_chakujun'), 10)
        features['zenso1_ninki'] = self._safe_int(z1.get('tansho_ninkijun'), 10)

        # 人気差（今回人気が上がっていれば正）
        if current_ninki:
            features['zenso1_ninki_diff'] = features['zenso1_ninki'] - current_ninki
        else:
            features['zenso1_ninki_diff'] = 0

        # クラス差
        current_class = self._grade_to_rank(race_info.get('grade_code', ''))
        past_class = self._grade_to_rank(z1.get('grade_code', ''))
        features['zenso1_class_diff'] = current_class - past_class  # 正=格上挑戦

        # 上がり3F順位
        features['zenso1_agari_rank'] = self.calc_agari_3f_rank(
            z1.get('race_code', ''),
            z1.get('kohan_3f', '')
        )

        # コーナー通過平均
        corners = []
        for i in [1, 2, 3, 4]:
            c = self._safe_int(z1.get(f'corner{i}_juni'), 0)
            if c > 0:
                corners.append(c)
        features['zenso1_corner_avg'] = np.mean(corners) if corners else 8.0

        # 距離
        features['zenso1_distance'] = self._safe_int(z1.get('kyori'), 1600)
        current_distance = self._safe_int(race_info.get('kyori'), 1600)
        features['zenso1_distance_diff'] = current_distance - features['zenso1_distance']

        # 2走前、3走前の着順
        features['zenso2_chakujun'] = self._safe_int(past_races[1].get('kakutei_chakujun'), 10) if len(past_races) > 1 else 10
        features['zenso3_chakujun'] = self._safe_int(past_races[2].get('kakutei_chakujun'), 10) if len(past_races) > 2 else 10

        # 着順トレンド（直近3走の傾向）
        # 1=上昇（着順が良くなっている）, 0=安定, -1=下降
        if len(past_races) >= 3:
            c1 = features['zenso1_chakujun']
            c2 = features['zenso2_chakujun']
            c3 = features['zenso3_chakujun']
            # 1走前と3走前を比較
            if c1 < c3 - 2:
                features['zenso_chakujun_trend'] = 1  # 上昇
            elif c1 > c3 + 2:
                features['zenso_chakujun_trend'] = -1  # 下降
            else:
                features['zenso_chakujun_trend'] = 0  # 安定
        else:
            features['zenso_chakujun_trend'] = 0

        # 上がり3Fトレンド
        agaris = []
        for i, race in enumerate(past_races[:3]):
            l3f = self._safe_int(race.get('kohan_3f'), 0)
            if l3f > 0:
                agaris.append(l3f / 10.0)

        if len(agaris) >= 3:
            # タイムが短くなっている=改善
            if agaris[0] < agaris[2] - 0.3:
                features['zenso_agari_trend'] = 1
            elif agaris[0] > agaris[2] + 0.3:
                features['zenso_agari_trend'] = -1
            else:
                features['zenso_agari_trend'] = 0
        else:
            features['zenso_agari_trend'] = 0

        return features

    # ========================================
    # 3. 競馬場別成績
    # ========================================

    def get_venue_stats(
        self,
        kettonum: str,
        venue_code: str,
        is_turf: bool = True
    ) -> Dict[str, float]:
        """競馬場別成績を取得（shussobetsu_keibajo）"""
        if not kettonum or not venue_code:
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        cache_key = f"venue_stats_{kettonum}_{venue_code}_{is_turf}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        venue_name = self.VENUE_CODES.get(venue_code, '')
        if not venue_name:
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

        surface = 'shiba' if is_turf else 'dirt'
        col_prefix = f"{venue_name}_{surface}"

        sql = f"""
            SELECT
                COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
                COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
                COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
                COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
                COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
                COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
            FROM shussobetsu_keibajo
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
            logger.debug(f"Failed to get venue stats: {e}")
            self.conn.rollback()
            return {'win_rate': 0.0, 'place_rate': 0.0, 'runs': 0}

    def extract_venue_features(
        self,
        kettonum: str,
        race_info: Dict,
        past_races: List[Dict] = None
    ) -> Dict[str, Any]:
        """競馬場関連特徴量を抽出"""
        features = {}

        venue_code = race_info.get('keibajo_code', '')
        track_code = race_info.get('track_code', '')
        is_turf = track_code.startswith('1') if track_code else True

        # 該当競馬場での成績
        venue_stats = self.get_venue_stats(kettonum, venue_code, is_turf)
        features['venue_win_rate'] = venue_stats['win_rate']
        features['venue_place_rate'] = venue_stats['place_rate']
        features['venue_runs'] = min(venue_stats['runs'], 50)

        # 小回り適性（小回りコースでの成績）
        small_track_stats = {'wins': 0, 'places': 0, 'runs': 0}
        large_track_stats = {'wins': 0, 'places': 0, 'runs': 0}

        if past_races:
            for race in past_races:
                race_venue = race.get('keibajo_code', '')
                chakujun = self._safe_int(race.get('kakutei_chakujun'), 99)
                if chakujun > 18:
                    continue

                if race_venue in self.SMALL_TRACK_VENUES:
                    small_track_stats['runs'] += 1
                    if chakujun == 1:
                        small_track_stats['wins'] += 1
                    if chakujun <= 3:
                        small_track_stats['places'] += 1
                else:
                    large_track_stats['runs'] += 1
                    if chakujun == 1:
                        large_track_stats['wins'] += 1
                    if chakujun <= 3:
                        large_track_stats['places'] += 1

        # 小回り/大回り適性スコア
        if small_track_stats['runs'] > 0:
            features['small_track_place_rate'] = small_track_stats['places'] / small_track_stats['runs']
        else:
            features['small_track_place_rate'] = 0.25

        if large_track_stats['runs'] > 0:
            features['large_track_place_rate'] = large_track_stats['places'] / large_track_stats['runs']
        else:
            features['large_track_place_rate'] = 0.25

        # 今回が小回りかどうかで適性スコアを設定
        is_small_track = venue_code in self.SMALL_TRACK_VENUES
        if is_small_track:
            features['track_type_fit'] = features['small_track_place_rate']
        else:
            features['track_type_fit'] = features['large_track_place_rate']

        return features

    # ========================================
    # 4. 展開予想の強化
    # ========================================

    def extract_pace_features_enhanced(
        self,
        entry: Dict,
        all_entries: List[Dict],
        running_styles: Dict[str, int]
    ) -> Dict[str, Any]:
        """強化された展開特徴量を抽出"""
        features = {}

        umaban = self._safe_int(entry.get('umaban'), 0)
        my_style = running_styles.get(entry.get('ketto_toroku_bango', ''), 2)

        # 自分より内枠の先行馬数
        inner_senkou = 0
        inner_nige = 0
        for e in all_entries:
            e_umaban = self._safe_int(e.get('umaban'), 0)
            e_kettonum = e.get('ketto_toroku_bango', '')
            e_style = running_styles.get(e_kettonum, 2)

            if e_umaban < umaban:
                if e_style == 1:  # 逃げ
                    inner_nige += 1
                elif e_style == 2:  # 先行
                    inner_senkou += 1

        features['inner_nige_count'] = inner_nige
        features['inner_senkou_count'] = inner_senkou

        # 枠番×脚質の有利不利
        # 内枠で逃げ・先行は有利、外枠で差し・追込は不利が小さい
        waku_style_score = 0.0
        if my_style in (1, 2):  # 逃げ・先行
            if umaban <= 4:  # 内枠
                waku_style_score = 0.1
            elif umaban >= 13:  # 外枠
                waku_style_score = -0.1
        else:  # 差し・追込
            if umaban <= 4:
                waku_style_score = -0.05
            elif umaban >= 13:
                waku_style_score = 0.05

        features['waku_style_advantage'] = waku_style_score

        return features

    # ========================================
    # 5. トレンド系（騎手の調子など）
    # ========================================

    def get_jockey_recent_form(self, kishu_code: str, days: int = 14) -> Dict[str, float]:
        """騎手の直近成績（調子）を取得"""
        if not kishu_code:
            return {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

        cache_key = f"jockey_recent_{kishu_code}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE kishu_code = %s
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
              AND TO_DATE(kaisai_nen || kaisai_gappi, 'YYYYMMDD') >= CURRENT_DATE - %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kishu_code, days))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                runs, wins, places = row
                result = {
                    'win_rate': wins / runs,
                    'place_rate': places / runs,
                    'runs': runs
                }
            else:
                result = {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get jockey recent form: {e}")
            self.conn.rollback()
            return {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

    def extract_trend_features(
        self,
        kishu_code: str,
        past_races: List[Dict]
    ) -> Dict[str, Any]:
        """トレンド系特徴量を抽出"""
        features = {}

        # 騎手の直近2週間成績
        jockey_form = self.get_jockey_recent_form(kishu_code, days=14)
        features['jockey_recent_win_rate'] = jockey_form['win_rate']
        features['jockey_recent_place_rate'] = jockey_form['place_rate']
        features['jockey_recent_runs'] = min(jockey_form['runs'], 30)

        return features

    # ========================================
    # 6. 季節・時期
    # ========================================

    def extract_seasonal_features(
        self,
        race_info: Dict,
        horse_age: int
    ) -> Dict[str, Any]:
        """季節・時期特徴量を抽出"""
        features = {}

        # 月（1-12）
        gappi = race_info.get('kaisai_gappi', '0101')
        month = self._safe_int(gappi[:2], 6)
        features['race_month'] = month

        # 季節エンコード（サイン・コサインで周期性を表現）
        features['month_sin'] = np.sin(2 * np.pi * month / 12)
        features['month_cos'] = np.cos(2 * np.pi * month / 12)

        # 開催週（1=開幕週付近, 2=中盤, 3=最終週付近）
        nichime = self._safe_int(race_info.get('kaisai_nichiji', '01'), 1)
        if nichime <= 2:
            features['kaisai_week'] = 1  # 開幕週
        elif nichime >= 7:
            features['kaisai_week'] = 3  # 最終週
        else:
            features['kaisai_week'] = 2  # 中盤

        # 馬齢×月（成長期判定）
        # 3歳馬の春〜夏は成長期
        if horse_age == 3 and 3 <= month <= 8:
            features['growth_period'] = 1
        elif horse_age == 4 and 1 <= month <= 6:
            features['growth_period'] = 1
        else:
            features['growth_period'] = 0

        # 冬場（寒い時期）フラグ
        features['is_winter'] = 1 if month in (12, 1, 2) else 0

        return features

    # ========================================
    # 統合メソッド
    # ========================================

    def extract_all_enhanced_features(
        self,
        entry: Dict,
        race_info: Dict,
        all_entries: List[Dict],
        running_styles: Dict[str, int],
        current_ninki: int = None
    ) -> Dict[str, Any]:
        """全ての拡張特徴量を抽出"""
        features = {}
        kettonum = entry.get('ketto_toroku_bango', '')
        kishu_code = entry.get('kishu_code', '')
        horse_age = self._safe_int(entry.get('barei'), 4)
        current_race_code = race_info.get('race_code', '')

        # 1. 血統特徴量
        pedigree_features = self.extract_pedigree_features(kettonum, race_info)
        features.update(pedigree_features)

        # 2. 前走情報特徴量
        zenso_features = self.extract_zenso_features(
            kettonum, current_race_code, race_info, current_ninki
        )
        features.update(zenso_features)

        # 3. 競馬場別成績
        past_races = self.get_past_races_detailed(kettonum, current_race_code, limit=10)
        venue_features = self.extract_venue_features(kettonum, race_info, past_races)
        features.update(venue_features)

        # 4. 展開予想強化
        pace_features = self.extract_pace_features_enhanced(entry, all_entries, running_styles)
        features.update(pace_features)

        # 5. トレンド系
        trend_features = self.extract_trend_features(kishu_code, past_races)
        features.update(trend_features)

        # 6. 季節・時期
        seasonal_features = self.extract_seasonal_features(race_info, horse_age)
        features.update(seasonal_features)

        return features

    # ========================================
    # ヘルパーメソッド
    # ========================================

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

    def _grade_to_rank(self, grade_code: str) -> int:
        """グレードコードをランク（数値）に変換"""
        mapping = {
            'A': 8, 'B': 7, 'C': 6, 'D': 5, 'E': 4, 'F': 3, 'G': 2, 'H': 1
        }
        return mapping.get(grade_code, 3)

    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache = {}
        self._sire_stats_cache = {}
