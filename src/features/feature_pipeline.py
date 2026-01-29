"""
特徴量抽出パイプライン

JRA-VANデータから各馬の特徴量を抽出
"""


import numpy as np
import pandas as pd


class FeatureExtractor:
    """JRA-VANデータから特徴量を抽出"""

    def __init__(self, db_connection=None):
        """
        Args:
            db_connection: PostgreSQL接続（オプション、現在はモックデータ使用）
        """
        self.db_connection = db_connection

    def extract_features(self, race_id: str, horse_number: int) -> dict:
        """
        各馬の特徴量を抽出

        Args:
            race_id: レースID
            horse_number: 馬番

        Returns:
            dict: 特徴量辞書
        """
        features = {}

        # TODO: 実際のDB接続実装後に置き換え
        # 現在はモックデータを返す

        # ===== 基本情報 =====
        features['age'] = self._get_horse_age(horse_number)
        features['sex'] = self._encode_sex(horse_number)
        features['kinryo'] = self._get_weight(horse_number)  # 斤量

        # ===== 枠順・馬番 =====
        features['wakuban'] = self._get_wakuban(horse_number)  # 枠番（1-8）
        features['umaban'] = horse_number  # 馬番

        # ===== 馬体重 =====
        features['horse_weight'] = self._get_horse_weight(horse_number)  # 馬体重
        features['weight_diff'] = self._get_weight_diff(horse_number)  # 前走比増減

        # ===== 馬具（ブリンカー等） =====
        features['blinker'] = self._get_blinker(horse_number)  # ブリンカー装着（0/1）
        features['blinker_first'] = self._get_blinker_first(horse_number)  # 初ブリンカー（0/1）
        features['horse_gear_changed'] = self._get_gear_changed(horse_number)  # 馬具変更あり（0/1）

        # ===== 脚質 =====
        features['running_style'] = self._get_running_style(horse_number)  # 脚質（1:逃げ,2:先行,3:差し,4:追込）
        features['position_avg_3f'] = self._get_position_avg_3f(horse_number)  # 3角平均位置
        features['position_avg_4f'] = self._get_position_avg_4f(horse_number)  # 4角平均位置

        # ===== スピード指数（過去5走） =====
        features['speed_index_avg'] = self._calculate_speed_index(horse_number, n=5)
        features['speed_index_max'] = self._calculate_speed_index_max(horse_number, n=5)
        features['speed_index_recent'] = self._calculate_speed_index(horse_number, n=1)

        # ===== 上がり3F（過去5走） =====
        features['last3f_rank_avg'] = self._get_last3f_rank(horse_number, n=5)
        features['last3f_rank_best'] = self._get_last3f_rank_best(horse_number, n=5)
        features['last3f_time_avg'] = self._get_last3f_time_avg(horse_number)  # 上がり3Fタイム平均

        # ===== 調教（直近） =====
        features['training_score'] = self._get_training_score(horse_number)  # 調教評価スコア
        features['training_time'] = self._get_training_time(horse_number)  # 調教タイム
        features['training_rank'] = self._get_training_rank(horse_number)  # 調教ランク（A/B/C→数値）

        # ===== 血統 =====
        features['sire_win_rate'] = self._get_sire_win_rate(horse_number)  # 父系勝率
        features['sire_distance_apt'] = self._get_sire_distance_apt(horse_number)  # 父系距離適性
        features['sire_track_apt'] = self._get_sire_track_apt(horse_number)  # 父系芝/ダート適性
        features['broodmare_sire_win_rate'] = self._get_bms_win_rate(horse_number)  # 母父勝率

        # ===== 騎手成績 =====
        features['jockey_win_rate'] = self._get_jockey_win_rate(horse_number)
        features['jockey_place_rate'] = self._get_jockey_place_rate(horse_number)
        features['jockey_course_win_rate'] = self._get_jockey_course_win_rate(horse_number)  # コース別勝率

        # ===== 調教師成績 =====
        features['trainer_win_rate'] = self._get_trainer_win_rate(horse_number)
        features['trainer_place_rate'] = self._get_trainer_place_rate(horse_number)

        # ===== 適性 =====
        features['course_fit_score'] = self._get_course_fit(horse_number)
        features['distance_fit_score'] = self._get_distance_fit(horse_number)
        features['track_condition_score'] = self._get_track_condition_fit(horse_number)

        # ===== その他 =====
        features['days_since_last_race'] = self._get_days_since_last_race(horse_number)
        features['class_rank'] = self._get_class_rank(horse_number)
        features['win_count'] = self._get_win_count(horse_number)  # 通算勝利数
        features['place_count'] = self._get_place_count(horse_number)  # 通算複勝数

        # ===== オッズ系（市場の評価） =====
        features['odds_win'] = self._get_odds_win(horse_number)  # 単勝オッズ
        features['odds_place'] = self._get_odds_place(horse_number)  # 複勝オッズ
        features['odds_change'] = self._get_odds_change(horse_number)  # 前日比オッズ変動率
        features['odds_win_place_ratio'] = self._get_odds_win_place_ratio(horse_number)  # 単複オッズ比
        features['popularity'] = self._get_popularity(horse_number)  # 人気順位
        features['odds_anomaly'] = self._get_odds_anomaly(horse_number)  # オッズ異常スコア

        # ===== ペース・ラップ系 =====
        features['first_3f_avg'] = self._get_first_3f_avg(horse_number)  # 前半3F平均タイム
        features['last_3f_diff'] = self._get_last_3f_diff(horse_number)  # 後半3Fタイム差
        features['corner_1_avg'] = self._get_corner_position(horse_number, 1)  # 1角平均位置
        features['corner_2_avg'] = self._get_corner_position(horse_number, 2)  # 2角平均位置
        features['corner_3_avg'] = self._get_corner_position(horse_number, 3)  # 3角平均位置
        features['corner_4_avg'] = self._get_corner_position(horse_number, 4)  # 4角平均位置
        features['position_up_3to4'] = self._get_position_up(horse_number)  # 3→4角位置上げ
        features['pace_type'] = self._get_pace_type(horse_number)  # ペースタイプ適性

        # ===== 馬場・天候系 =====
        features['baba_code'] = self._get_baba_code(horse_number)  # 馬場状態（1:良,2:稍,3:重,4:不）
        features['baba_diff'] = self._get_baba_diff(horse_number)  # 馬場差（基準タイムとの差）
        features['weather'] = self._get_weather(horse_number)  # 天候（1:晴,2:曇,3:雨,4:雪）
        features['good_baba_rate'] = self._get_good_baba_rate(horse_number)  # 良馬場時の勝率
        features['heavy_baba_rate'] = self._get_heavy_baba_rate(horse_number)  # 重馬場時の勝率

        # ===== 騎手乗り替わり =====
        features['jockey_change'] = self._get_jockey_change(horse_number)  # 乗り替わり(0:継続,1:変更)
        features['jockey_combo_wins'] = self._get_jockey_combo_wins(horse_number)  # 同コンビ勝利数
        features['jockey_combo_rate'] = self._get_jockey_combo_rate(horse_number)  # 同コンビ勝率
        features['jockey_rank'] = self._get_jockey_rank(horse_number)  # 騎手リーディング順位
        features['jockey_change_to_top'] = self._get_jockey_change_to_top(horse_number)  # トップ騎手への乗替

        # ===== 負担重量変更 =====
        features['kinryo_diff'] = self._get_kinryo_diff(horse_number)  # 前走からの斤量変化
        features['kinryo_vs_avg'] = self._get_kinryo_vs_avg(horse_number)  # 出走馬平均斤量との差
        features['kinryo_handicap'] = self._get_kinryo_handicap(horse_number)  # ハンデ戦斤量差

        # ===== 出走間隔・ローテーション =====
        features['interval_category'] = self._get_interval_category(horse_number)  # 間隔区分(1:連闘,2:中1週...)
        features['is_fresh'] = self._get_is_fresh(horse_number)  # 放牧明け(0/1)
        features['distance_diff'] = self._get_distance_diff(horse_number)  # 前走からの距離変化(m)
        features['distance_category_change'] = self._get_distance_category_change(horse_number)  # 距離カテゴリ変更
        features['same_course_runs'] = self._get_same_course_runs(horse_number)  # 同コース出走回数

        # ===== 血統の深堀り =====
        features['family_graded_wins'] = self._get_family_graded_wins(horse_number)  # 牝系重賞勝ち数
        features['sibling_win_rate'] = self._get_sibling_win_rate(horse_number)  # 兄弟勝率
        features['inbreed_coefficient'] = self._get_inbreed_coefficient(horse_number)  # インブリード係数
        features['sire_2nd_gen_score'] = self._get_sire_2nd_gen_score(horse_number)  # 父父の影響度
        features['dam_sire_distance_apt'] = self._get_dam_sire_distance_apt(horse_number)  # 母父距離適性
        features['pedigree_class_score'] = self._get_pedigree_class_score(horse_number)  # 血統クラススコア

        # ===== 競馬場・コース特性 =====
        features['course_direction'] = self._get_course_direction(horse_number)  # 回り(1:右,2:左,3:直線)
        features['course_slope'] = self._get_course_slope(horse_number)  # 坂(0:平坦,1:急坂)
        features['waku_bias'] = self._get_waku_bias(horse_number)  # 枠順バイアス値
        features['time_vs_record'] = self._get_time_vs_record(horse_number)  # レコードとのタイム差
        features['course_win_rate'] = self._get_course_win_rate(horse_number)  # 該当コース勝率
        features['venue_win_rate'] = self._get_venue_win_rate(horse_number)  # 該当競馬場勝率

        # ===== 出走別着度数（適性） =====
        features['turf_win_rate'] = self._get_surface_win_rate(horse_number, 'turf')  # 芝勝率
        features['dirt_win_rate'] = self._get_surface_win_rate(horse_number, 'dirt')  # ダート勝率
        features['sprint_win_rate'] = self._get_distance_range_win_rate(horse_number, 'sprint')  # 短距離勝率
        features['mile_win_rate'] = self._get_distance_range_win_rate(horse_number, 'mile')  # マイル勝率
        features['middle_win_rate'] = self._get_distance_range_win_rate(horse_number, 'middle')  # 中距離勝率
        features['long_win_rate'] = self._get_distance_range_win_rate(horse_number, 'long')  # 長距離勝率
        features['venue_specific_rate'] = self._get_venue_specific_rate(horse_number)  # 競馬場別複勝率

        # ===== 調教データ詳細 =====
        features['training_partner_result'] = self._get_training_partner_result(horse_number)  # 併せ馬結果
        features['training_intensity'] = self._get_training_intensity(horse_number)  # 追い切り強度
        features['training_course_type'] = self._get_training_course_type(horse_number)  # 調教コース(1:坂路,2:ウッド,3:ポリ)
        features['training_1week_time'] = self._get_training_1week_time(horse_number)  # 1週前追い切りタイム
        features['training_final_time'] = self._get_training_final_time(horse_number)  # 最終追い切りタイム
        features['training_count'] = self._get_training_count(horse_number)  # 調教本数
        features['training_improvement'] = self._get_training_improvement(horse_number)  # 調教タイム向上率

        # ===== レース当日の変化 =====
        features['late_scratch_rate'] = self._get_late_scratch_rate(horse_number)  # 取消馬の影響
        features['field_size'] = self._get_field_size(horse_number)  # 出走頭数
        features['favorite_count'] = self._get_favorite_count(horse_number)  # 上位人気馬数

        return features

    def extract_all_features(self, race_id: str, num_horses: int = 18) -> pd.DataFrame:
        """
        レース全馬の特徴量を抽出

        Args:
            race_id: レースID
            num_horses: 出走馬数

        Returns:
            DataFrame: 全馬の特徴量
        """
        all_features = []

        for horse_number in range(1, num_horses + 1):
            features = self.extract_features(race_id, horse_number)
            features['horse_number'] = horse_number
            all_features.append(features)

        return pd.DataFrame(all_features)

    # ===== モックデータ生成メソッド（実装後に削除） =====

    def _get_horse_age(self, horse_number: int) -> int:
        """馬齢（モック）"""
        ages = [4, 5, 3, 6, 4, 5, 3, 4, 5, 6, 4, 3, 5, 4, 6, 3, 5, 4]
        return ages[horse_number - 1] if horse_number <= len(ages) else 4

    def _get_weight(self, horse_number: int) -> int:
        """負担重量（モック）"""
        return 54 + (horse_number % 4)

    def _encode_sex(self, horse_number: int) -> int:
        """性別エンコード（0: 牡, 1: 牝, 2: セン）"""
        return horse_number % 3

    def _calculate_speed_index(self, horse_number: int, n: int = 5) -> float:
        """
        スピード指数（過去n走平均）

        スピード指数 = (基準タイム - 走破タイム) × 距離係数 + 馬場補正
        """
        # モックデータ: 70-90の範囲でランダム
        np.random.seed(horse_number)
        return 70 + np.random.random() * 20

    def _calculate_speed_index_max(self, horse_number: int, n: int = 5) -> float:
        """スピード指数（過去n走の最高値）"""
        return self._calculate_speed_index(horse_number, n) + 5

    def _get_last3f_rank(self, horse_number: int, n: int = 5) -> float:
        """上がり3F順位平均（過去n走）"""
        np.random.seed(horse_number + 100)
        return 1 + np.random.random() * 8

    def _get_last3f_rank_best(self, horse_number: int, n: int = 5) -> float:
        """上がり3F順位（過去n走の最良）"""
        return max(1, self._get_last3f_rank(horse_number, n) - 2)

    def _get_jockey_win_rate(self, horse_number: int) -> float:
        """騎手勝率"""
        np.random.seed(horse_number + 200)
        return 0.05 + np.random.random() * 0.15

    def _get_jockey_place_rate(self, horse_number: int) -> float:
        """騎手複勝率"""
        return self._get_jockey_win_rate(horse_number) * 3

    def _get_trainer_win_rate(self, horse_number: int) -> float:
        """調教師勝率"""
        np.random.seed(horse_number + 300)
        return 0.05 + np.random.random() * 0.12

    def _get_trainer_place_rate(self, horse_number: int) -> float:
        """調教師複勝率"""
        return self._get_trainer_win_rate(horse_number) * 2.8

    def _get_course_fit(self, horse_number: int) -> float:
        """コース適性スコア（0-1）"""
        np.random.seed(horse_number + 400)
        return 0.3 + np.random.random() * 0.6

    def _get_distance_fit(self, horse_number: int) -> float:
        """距離適性スコア（0-1）"""
        np.random.seed(horse_number + 500)
        return 0.4 + np.random.random() * 0.5

    def _get_track_condition_fit(self, horse_number: int) -> float:
        """馬場適性スコア（0-1）"""
        np.random.seed(horse_number + 600)
        return 0.3 + np.random.random() * 0.6

    def _get_days_since_last_race(self, horse_number: int) -> int:
        """休養日数"""
        np.random.seed(horse_number + 700)
        return int(14 + np.random.random() * 60)

    def _get_class_rank(self, horse_number: int) -> int:
        """クラスランク（1: 新馬, 2: 未勝利, 3: 1勝クラス, ..., 8: G1）"""
        return 3 + (horse_number % 4)

    # ===== 追加特徴量のモックメソッド =====

    def _get_wakuban(self, horse_number: int) -> int:
        """枠番（1-8）"""
        return min(8, (horse_number - 1) // 2 + 1)

    def _get_horse_weight(self, horse_number: int) -> int:
        """馬体重（kg）"""
        np.random.seed(horse_number + 800)
        return int(440 + np.random.random() * 80)

    def _get_weight_diff(self, horse_number: int) -> int:
        """前走比馬体重増減（kg）"""
        np.random.seed(horse_number + 810)
        return int(np.random.random() * 20) - 10  # -10 ~ +10

    def _get_blinker(self, horse_number: int) -> int:
        """ブリンカー装着（0: なし, 1: あり）"""
        np.random.seed(horse_number + 820)
        return 1 if np.random.random() < 0.15 else 0  # 15%がブリンカー装着

    def _get_blinker_first(self, horse_number: int) -> int:
        """初ブリンカー（0: 該当なし, 1: 初ブリンカー）"""
        np.random.seed(horse_number + 830)
        # ブリンカー装着馬の20%が初ブリンカー
        if self._get_blinker(horse_number) == 1:
            return 1 if np.random.random() < 0.2 else 0
        return 0

    def _get_gear_changed(self, horse_number: int) -> int:
        """馬具変更あり（0: なし, 1: あり）"""
        np.random.seed(horse_number + 840)
        return 1 if np.random.random() < 0.1 else 0  # 10%が馬具変更

    def _get_running_style(self, horse_number: int) -> int:
        """脚質（1: 逃げ, 2: 先行, 3: 差し, 4: 追込）"""
        np.random.seed(horse_number + 850)
        return int(1 + np.random.random() * 4)

    def _get_position_avg_3f(self, horse_number: int) -> float:
        """3角平均位置（過去5走）"""
        np.random.seed(horse_number + 860)
        return 1 + np.random.random() * 12

    def _get_position_avg_4f(self, horse_number: int) -> float:
        """4角平均位置（過去5走）"""
        np.random.seed(horse_number + 870)
        return 1 + np.random.random() * 12

    def _get_last3f_time_avg(self, horse_number: int) -> float:
        """上がり3Fタイム平均（秒）"""
        np.random.seed(horse_number + 880)
        return 33.5 + np.random.random() * 3  # 33.5 ~ 36.5秒

    def _get_training_score(self, horse_number: int) -> float:
        """調教評価スコア（0-100）"""
        np.random.seed(horse_number + 890)
        return 50 + np.random.random() * 50

    def _get_training_time(self, horse_number: int) -> float:
        """調教タイム（坂路/ウッド 4F, 秒）"""
        np.random.seed(horse_number + 900)
        return 50 + np.random.random() * 6  # 50 ~ 56秒

    def _get_training_rank(self, horse_number: int) -> int:
        """調教ランク（1: A, 2: B, 3: C）"""
        np.random.seed(horse_number + 910)
        return int(1 + np.random.random() * 3)

    def _get_sire_win_rate(self, horse_number: int) -> float:
        """父系勝率（産駒の勝率）"""
        np.random.seed(horse_number + 920)
        return 0.05 + np.random.random() * 0.15

    def _get_sire_distance_apt(self, horse_number: int) -> float:
        """父系距離適性スコア（0-1）"""
        np.random.seed(horse_number + 930)
        return 0.3 + np.random.random() * 0.6

    def _get_sire_track_apt(self, horse_number: int) -> float:
        """父系芝/ダート適性（0: ダート向き, 0.5: 万能, 1: 芝向き）"""
        np.random.seed(horse_number + 940)
        return np.random.random()

    def _get_bms_win_rate(self, horse_number: int) -> float:
        """母父勝率（母父産駒の勝率）"""
        np.random.seed(horse_number + 950)
        return 0.05 + np.random.random() * 0.12

    def _get_jockey_course_win_rate(self, horse_number: int) -> float:
        """騎手コース別勝率"""
        np.random.seed(horse_number + 960)
        return 0.03 + np.random.random() * 0.17

    def _get_win_count(self, horse_number: int) -> int:
        """通算勝利数"""
        np.random.seed(horse_number + 970)
        return int(np.random.random() * 8)

    def _get_place_count(self, horse_number: int) -> int:
        """通算複勝数（3着以内回数）"""
        np.random.seed(horse_number + 980)
        return int(np.random.random() * 15)

    # ===== オッズ系モックメソッド =====

    def _get_odds_win(self, horse_number: int) -> float:
        """単勝オッズ"""
        np.random.seed(horse_number + 1000)
        return round(1.5 + np.random.exponential(10), 1)

    def _get_odds_place(self, horse_number: int) -> float:
        """複勝オッズ"""
        return round(self._get_odds_win(horse_number) / 3, 1)

    def _get_odds_change(self, horse_number: int) -> float:
        """前日比オッズ変動率（-1.0〜1.0、負=人気上昇）"""
        np.random.seed(horse_number + 1010)
        return round(np.random.uniform(-0.5, 0.5), 2)

    def _get_odds_win_place_ratio(self, horse_number: int) -> float:
        """単複オッズ比（異常に低いと穴馬の可能性）"""
        win = self._get_odds_win(horse_number)
        place = self._get_odds_place(horse_number)
        return round(win / place if place > 0 else 3.0, 2)

    def _get_popularity(self, horse_number: int) -> int:
        """人気順位"""
        np.random.seed(horse_number + 1020)
        return int(1 + np.random.random() * 17)

    def _get_odds_anomaly(self, horse_number: int) -> float:
        """オッズ異常スコア（0-1、高いほど異常）"""
        np.random.seed(horse_number + 1030)
        return round(np.random.random() * 0.3, 2)  # 通常は低い

    # ===== ペース・ラップ系モックメソッド =====

    def _get_first_3f_avg(self, horse_number: int) -> float:
        """前半3F平均タイム（秒）"""
        np.random.seed(horse_number + 1100)
        return round(33.5 + np.random.random() * 3, 1)

    def _get_last_3f_diff(self, horse_number: int) -> float:
        """後半3Fタイム差（前半との差、負=尻上がり）"""
        np.random.seed(horse_number + 1110)
        return round(np.random.uniform(-2, 3), 1)

    def _get_corner_position(self, horse_number: int, corner: int) -> float:
        """コーナー通過位置（1-18）"""
        np.random.seed(horse_number + 1120 + corner * 10)
        return round(1 + np.random.random() * 12, 1)

    def _get_position_up(self, horse_number: int) -> float:
        """3→4角での位置上げ（負=上げ、正=下げ）"""
        c3 = self._get_corner_position(horse_number, 3)
        c4 = self._get_corner_position(horse_number, 4)
        return round(c4 - c3, 1)

    def _get_pace_type(self, horse_number: int) -> int:
        """ペースタイプ適性（1:ハイペース向き、2:平均、3:スロー向き）"""
        np.random.seed(horse_number + 1150)
        return int(1 + np.random.random() * 3)

    # ===== 馬場・天候系モックメソッド =====

    def _get_baba_code(self, horse_number: int) -> int:
        """馬場状態（1:良、2:稍重、3:重、4:不良）"""
        np.random.seed(horse_number + 1200)
        weights = [0.6, 0.25, 0.1, 0.05]  # 良が多い
        return int(np.random.choice([1, 2, 3, 4], p=weights))

    def _get_baba_diff(self, horse_number: int) -> float:
        """馬場差（基準タイムとの差、秒）"""
        np.random.seed(horse_number + 1210)
        return round(np.random.uniform(-1.5, 1.5), 1)

    def _get_weather(self, horse_number: int) -> int:
        """天候（1:晴、2:曇、3:雨、4:雪）"""
        np.random.seed(horse_number + 1220)
        weights = [0.5, 0.3, 0.15, 0.05]
        return int(np.random.choice([1, 2, 3, 4], p=weights))

    def _get_good_baba_rate(self, horse_number: int) -> float:
        """良馬場時の勝率"""
        np.random.seed(horse_number + 1230)
        return round(0.05 + np.random.random() * 0.15, 3)

    def _get_heavy_baba_rate(self, horse_number: int) -> float:
        """重馬場時の勝率"""
        np.random.seed(horse_number + 1240)
        return round(0.03 + np.random.random() * 0.12, 3)

    # ===== 騎手乗り替わりモックメソッド =====

    def _get_jockey_change(self, horse_number: int) -> int:
        """乗り替わり（0:継続、1:変更）"""
        np.random.seed(horse_number + 1300)
        return 1 if np.random.random() < 0.3 else 0

    def _get_jockey_combo_wins(self, horse_number: int) -> int:
        """同コンビ勝利数"""
        np.random.seed(horse_number + 1310)
        return int(np.random.random() * 5)

    def _get_jockey_combo_rate(self, horse_number: int) -> float:
        """同コンビ勝率"""
        np.random.seed(horse_number + 1320)
        return round(0.05 + np.random.random() * 0.2, 3)

    def _get_jockey_rank(self, horse_number: int) -> int:
        """騎手リーディング順位"""
        np.random.seed(horse_number + 1330)
        return int(1 + np.random.exponential(30))

    def _get_jockey_change_to_top(self, horse_number: int) -> int:
        """トップ騎手（TOP10）への乗り替わり（0/1）"""
        if self._get_jockey_change(horse_number) == 1 and self._get_jockey_rank(horse_number) <= 10:
            return 1
        return 0

    # ===== 負担重量変更モックメソッド =====

    def _get_kinryo_diff(self, horse_number: int) -> float:
        """前走からの斤量変化（kg）"""
        np.random.seed(horse_number + 1400)
        return round(np.random.uniform(-2, 2), 1)

    def _get_kinryo_vs_avg(self, horse_number: int) -> float:
        """出走馬平均斤量との差（kg）"""
        np.random.seed(horse_number + 1410)
        return round(np.random.uniform(-3, 3), 1)

    def _get_kinryo_handicap(self, horse_number: int) -> float:
        """ハンデ戦での最軽量馬との斤量差（kg）"""
        np.random.seed(horse_number + 1420)
        return round(np.random.random() * 6, 1)

    # ===== 出走間隔・ローテーションモックメソッド =====

    def _get_interval_category(self, horse_number: int) -> int:
        """間隔区分（1:連闘、2:中1週、3:中2週、4:中3週、5:1ヶ月以上、6:3ヶ月以上）"""
        np.random.seed(horse_number + 1500)
        weights = [0.02, 0.08, 0.2, 0.25, 0.35, 0.1]
        return int(np.random.choice([1, 2, 3, 4, 5, 6], p=weights))

    def _get_is_fresh(self, horse_number: int) -> int:
        """放牧明け（3ヶ月以上の休養明け）（0/1）"""
        return 1 if self._get_interval_category(horse_number) >= 6 else 0

    def _get_distance_diff(self, horse_number: int) -> int:
        """前走からの距離変化（m）"""
        np.random.seed(horse_number + 1520)
        return int(np.random.choice([-400, -200, 0, 200, 400], p=[0.1, 0.2, 0.4, 0.2, 0.1]))

    def _get_distance_category_change(self, horse_number: int) -> int:
        """距離カテゴリ変更（-1:短縮、0:同距離、1:延長）"""
        diff = self._get_distance_diff(horse_number)
        if diff < -100:
            return -1
        elif diff > 100:
            return 1
        return 0

    def _get_same_course_runs(self, horse_number: int) -> int:
        """同コース出走回数"""
        np.random.seed(horse_number + 1540)
        return int(np.random.random() * 10)

    # ===== 血統の深堀りモックメソッド =====

    def _get_family_graded_wins(self, horse_number: int) -> int:
        """牝系重賞勝ち数"""
        np.random.seed(horse_number + 1600)
        return int(np.random.exponential(2))

    def _get_sibling_win_rate(self, horse_number: int) -> float:
        """兄弟勝率"""
        np.random.seed(horse_number + 1610)
        return round(0.05 + np.random.random() * 0.15, 3)

    def _get_inbreed_coefficient(self, horse_number: int) -> float:
        """インブリード係数（0-1、高いほど近親）"""
        np.random.seed(horse_number + 1620)
        return round(np.random.random() * 0.15, 3)

    def _get_sire_2nd_gen_score(self, horse_number: int) -> float:
        """父父の影響度スコア（0-1）"""
        np.random.seed(horse_number + 1630)
        return round(0.3 + np.random.random() * 0.5, 2)

    def _get_dam_sire_distance_apt(self, horse_number: int) -> float:
        """母父距離適性スコア（0-1）"""
        np.random.seed(horse_number + 1640)
        return round(0.3 + np.random.random() * 0.6, 2)

    def _get_pedigree_class_score(self, horse_number: int) -> float:
        """血統クラススコア（0-100）"""
        np.random.seed(horse_number + 1650)
        return round(30 + np.random.random() * 60, 1)

    # ===== 競馬場・コース特性モックメソッド =====

    def _get_course_direction(self, horse_number: int) -> int:
        """回り（1:右、2:左、3:直線）"""
        np.random.seed(horse_number + 1700)
        return int(np.random.choice([1, 2, 3], p=[0.6, 0.35, 0.05]))

    def _get_course_slope(self, horse_number: int) -> int:
        """坂（0:平坦、1:急坂）"""
        np.random.seed(horse_number + 1710)
        return 1 if np.random.random() < 0.4 else 0

    def _get_waku_bias(self, horse_number: int) -> float:
        """枠順バイアス値（-1:内有利、0:フラット、1:外有利）"""
        np.random.seed(horse_number + 1720)
        return round(np.random.uniform(-0.5, 0.5), 2)

    def _get_time_vs_record(self, horse_number: int) -> float:
        """レコードとのタイム差（秒）"""
        np.random.seed(horse_number + 1730)
        return round(1 + np.random.random() * 5, 1)

    def _get_course_win_rate(self, horse_number: int) -> float:
        """該当コース勝率"""
        np.random.seed(horse_number + 1740)
        return round(0.03 + np.random.random() * 0.15, 3)

    def _get_venue_win_rate(self, horse_number: int) -> float:
        """該当競馬場勝率"""
        np.random.seed(horse_number + 1750)
        return round(0.05 + np.random.random() * 0.15, 3)

    # ===== 出走別着度数モックメソッド =====

    def _get_surface_win_rate(self, horse_number: int, surface: str) -> float:
        """芝/ダート別勝率"""
        seed_offset = 1800 if surface == 'turf' else 1810
        np.random.seed(horse_number + seed_offset)
        return round(0.03 + np.random.random() * 0.15, 3)

    def _get_distance_range_win_rate(self, horse_number: int, distance_type: str) -> float:
        """距離別勝率"""
        offsets = {'sprint': 1820, 'mile': 1830, 'middle': 1840, 'long': 1850}
        np.random.seed(horse_number + offsets.get(distance_type, 1820))
        return round(0.03 + np.random.random() * 0.15, 3)

    def _get_venue_specific_rate(self, horse_number: int) -> float:
        """競馬場別複勝率"""
        np.random.seed(horse_number + 1860)
        return round(0.1 + np.random.random() * 0.3, 3)

    # ===== 調教データ詳細モックメソッド =====

    def _get_training_partner_result(self, horse_number: int) -> int:
        """併せ馬結果（1:先着、2:同入、3:遅れ、0:単走）"""
        np.random.seed(horse_number + 1900)
        return int(np.random.choice([0, 1, 2, 3], p=[0.3, 0.35, 0.25, 0.1]))

    def _get_training_intensity(self, horse_number: int) -> int:
        """追い切り強度（1:一杯、2:強め、3:馬なり）"""
        np.random.seed(horse_number + 1910)
        return int(np.random.choice([1, 2, 3], p=[0.2, 0.4, 0.4]))

    def _get_training_course_type(self, horse_number: int) -> int:
        """調教コース（1:坂路、2:ウッド、3:ポリトラック）"""
        np.random.seed(horse_number + 1920)
        return int(np.random.choice([1, 2, 3], p=[0.4, 0.45, 0.15]))

    def _get_training_1week_time(self, horse_number: int) -> float:
        """1週前追い切りタイム（4F、秒）"""
        np.random.seed(horse_number + 1930)
        return round(50 + np.random.random() * 6, 1)

    def _get_training_final_time(self, horse_number: int) -> float:
        """最終追い切りタイム（4F、秒）"""
        np.random.seed(horse_number + 1940)
        return round(49 + np.random.random() * 7, 1)

    def _get_training_count(self, horse_number: int) -> int:
        """調教本数（直近1ヶ月）"""
        np.random.seed(horse_number + 1950)
        return int(3 + np.random.random() * 10)

    def _get_training_improvement(self, horse_number: int) -> float:
        """調教タイム向上率（1週前→最終の改善率）"""
        t1 = self._get_training_1week_time(horse_number)
        t2 = self._get_training_final_time(horse_number)
        return round((t1 - t2) / t1 * 100, 2) if t1 > 0 else 0

    # ===== レース当日モックメソッド =====

    def _get_late_scratch_rate(self, horse_number: int) -> float:
        """取消馬の影響（0-1、高いほど有利に働く可能性）"""
        np.random.seed(horse_number + 2000)
        return round(np.random.random() * 0.2, 2)

    def _get_field_size(self, horse_number: int) -> int:
        """出走頭数"""
        np.random.seed(horse_number + 2010)
        return int(8 + np.random.random() * 10)

    def _get_favorite_count(self, horse_number: int) -> int:
        """上位人気馬数（5番人気以内の頭数）"""
        return min(5, self._get_field_size(horse_number))
