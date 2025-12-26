"""
特徴量抽出パイプライン

JRA-VANデータから各馬の特徴量を抽出
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class FeatureExtractor:
    """JRA-VANデータから特徴量を抽出"""

    def __init__(self, db_connection=None):
        """
        Args:
            db_connection: PostgreSQL接続（オプション、現在はモックデータ使用）
        """
        self.db_connection = db_connection

    def extract_features(self, race_id: str, horse_number: int) -> Dict:
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

        # 1. 基本情報
        features['age'] = self._get_horse_age(horse_number)
        features['weight'] = self._get_weight(horse_number)
        features['sex'] = self._encode_sex(horse_number)

        # 2. スピード指数（過去5走平均）
        features['speed_index_avg'] = self._calculate_speed_index(horse_number, n=5)
        features['speed_index_max'] = self._calculate_speed_index_max(horse_number, n=5)
        features['speed_index_recent'] = self._calculate_speed_index(horse_number, n=1)

        # 3. 上がり3F順位（過去5走平均）
        features['last3f_rank_avg'] = self._get_last3f_rank(horse_number, n=5)
        features['last3f_rank_best'] = self._get_last3f_rank_best(horse_number, n=5)

        # 4. 騎手成績
        features['jockey_win_rate'] = self._get_jockey_win_rate(horse_number)
        features['jockey_place_rate'] = self._get_jockey_place_rate(horse_number)

        # 5. 調教師成績
        features['trainer_win_rate'] = self._get_trainer_win_rate(horse_number)
        features['trainer_place_rate'] = self._get_trainer_place_rate(horse_number)

        # 6. コース適性
        features['course_fit_score'] = self._get_course_fit(horse_number)

        # 7. 距離適性
        features['distance_fit_score'] = self._get_distance_fit(horse_number)

        # 8. 馬場適性
        features['track_condition_score'] = self._get_track_condition_fit(horse_number)

        # 9. 休養明け
        features['days_since_last_race'] = self._get_days_since_last_race(horse_number)

        # 10. クラス
        features['class_rank'] = self._get_class_rank(horse_number)

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
