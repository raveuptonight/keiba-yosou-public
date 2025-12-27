"""
機械学習モデルの継続的学習

予想結果と実際の結果を比較し、外れ値を分析してモデルを再学習
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import pickle
from datetime import datetime
from pathlib import Path

from src.models.xgboost_model import HorseRacingXGBoost


class IncrementalLearner:
    """継続的学習マネージャー"""

    def __init__(self, model: HorseRacingXGBoost, data_dir: str = "data/learning"):
        """
        Args:
            model: 学習対象のXGBoostモデル
            data_dir: 学習データ保存ディレクトリ
        """
        self.model = model
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 学習データの蓄積
        self.training_data_file = self.data_dir / "incremental_training_data.pkl"
        self.load_training_data()

    def load_training_data(self):
        """過去の学習データを読み込み"""
        if self.training_data_file.exists():
            with open(self.training_data_file, 'rb') as f:
                data = pickle.load(f)
                self.X_accumulated = data['X']
                self.y_accumulated = data['y']
        else:
            self.X_accumulated = pd.DataFrame()
            self.y_accumulated = pd.Series()

    def save_training_data(self):
        """学習データを保存"""
        with open(self.training_data_file, 'wb') as f:
            pickle.dump({
                'X': self.X_accumulated,
                'y': self.y_accumulated,
                'updated_at': datetime.now()
            }, f)

    def analyze_outliers(
        self,
        prediction_data: Dict,
        actual_result: Dict
    ) -> Dict:
        """
        外れ値を分析

        Args:
            prediction_data: 予想時のデータ（特徴量、予測値）
            actual_result: 実際の結果

        Returns:
            dict: 外れ値分析結果
        """
        ml_scores = prediction_data['ml_scores']
        outliers = []

        for horse_data in ml_scores:
            horse_number = horse_data['horse_number']
            predicted_rank = horse_data['rank_score']

            # 実際の着順を取得
            actual_rank = actual_result.get('rankings', {}).get(horse_number)

            if actual_rank is None:
                continue

            # 予測誤差
            error = abs(predicted_rank - actual_rank)

            # 外れ値判定（誤差が3着以上）
            is_outlier = error >= 3.0

            outlier_info = {
                'horse_number': horse_number,
                'horse_name': horse_data['horse_name'],
                'predicted_rank': predicted_rank,
                'actual_rank': actual_rank,
                'error': error,
                'is_outlier': is_outlier,
                'features': horse_data['features'],
                'outlier_type': self._classify_outlier(predicted_rank, actual_rank)
            }

            if is_outlier:
                outliers.append(outlier_info)

        # 外れ値の分析
        analysis = {
            'total_horses': len(ml_scores),
            'outlier_count': len(outliers),
            'outlier_rate': len(outliers) / len(ml_scores) if ml_scores else 0,
            'outliers': outliers,
            'avg_error': np.mean([abs(h['predicted_rank'] - actual_result.get('rankings', {}).get(h['horse_number'], h['predicted_rank']))
                                  for h in ml_scores if actual_result.get('rankings', {}).get(h['horse_number']) is not None]),
            'feature_importance_issues': self._analyze_feature_issues(outliers)
        }

        return analysis

    def _classify_outlier(self, predicted: float, actual: int) -> str:
        """
        外れ値のタイプを分類

        Args:
            predicted: 予測着順
            actual: 実際の着順

        Returns:
            str: 外れ値タイプ
        """
        if predicted < actual:
            # 予測より悪い結果（過大評価）
            if predicted <= 3 and actual > 8:
                return "major_overestimate"  # 上位予想が大きく外れ
            else:
                return "overestimate"
        else:
            # 予測より良い結果（過小評価）
            if predicted > 8 and actual <= 3:
                return "major_underestimate"  # 穴馬を見逃し
            else:
                return "underestimate"

    def _analyze_feature_issues(self, outliers: List[Dict]) -> Dict:
        """
        外れ値の特徴量を分析して問題点を特定

        Args:
            outliers: 外れ値リスト

        Returns:
            dict: 特徴量の問題点
        """
        if not outliers:
            return {}

        # 過大評価と過小評価を分ける
        overestimated = [o for o in outliers if 'overestimate' in o['outlier_type']]
        underestimated = [o for o in outliers if 'underestimate' in o['outlier_type']]

        issues = {}

        # 過大評価された馬の共通特徴
        if overestimated:
            over_features = pd.DataFrame([o['features'] for o in overestimated])
            issues['overestimate_patterns'] = {
                'count': len(overestimated),
                'avg_features': over_features.mean().to_dict(),
                'common_characteristics': self._find_common_characteristics(over_features)
            }

        # 過小評価された馬の共通特徴
        if underestimated:
            under_features = pd.DataFrame([o['features'] for o in underestimated])
            issues['underestimate_patterns'] = {
                'count': len(underestimated),
                'avg_features': under_features.mean().to_dict(),
                'common_characteristics': self._find_common_characteristics(under_features)
            }

        return issues

    def _find_common_characteristics(self, features_df: pd.DataFrame) -> List[str]:
        """共通の特徴を見つける"""
        characteristics = []

        # 各特徴量の平均と標準偏差を計算
        for col in features_df.columns:
            mean_val = features_df[col].mean()
            std_val = features_df[col].std()

            # 特徴的な値（平均から大きく外れている）を特定
            if std_val < mean_val * 0.2:  # 分散が小さい = 共通して高い/低い
                if mean_val > 0.7:  # 高い値
                    characteristics.append(f"{col}: 高い ({mean_val:.2f})")
                elif mean_val < 0.3:  # 低い値
                    characteristics.append(f"{col}: 低い ({mean_val:.2f})")

        return characteristics

    def add_training_sample(
        self,
        features: pd.DataFrame,
        actual_ranks: pd.Series
    ):
        """
        新しい学習サンプルを追加

        Args:
            features: 特徴量（DataFrame）
            actual_ranks: 実際の着順（Series）
        """
        # データを蓄積
        if self.X_accumulated.empty:
            self.X_accumulated = features
            self.y_accumulated = actual_ranks
        else:
            self.X_accumulated = pd.concat([self.X_accumulated, features], ignore_index=True)
            self.y_accumulated = pd.concat([self.y_accumulated, actual_ranks], ignore_index=True)

        # 保存
        self.save_training_data()

        print(f"学習サンプル追加: 合計 {len(self.X_accumulated)} サンプル")

    def retrain_model(self, min_samples: int = 100) -> Dict:
        """
        モデルを再学習

        Args:
            min_samples: 最小サンプル数（これ以下なら学習しない）

        Returns:
            dict: 再学習結果
        """
        if len(self.X_accumulated) < min_samples:
            return {
                'status': 'skipped',
                'reason': f'サンプル数不足 ({len(self.X_accumulated)}/{min_samples})',
                'current_samples': len(self.X_accumulated)
            }

        print(f"\n===== モデル再学習開始 =====")
        print(f"学習サンプル数: {len(self.X_accumulated)}")

        # 旧モデルの精度を記録
        old_feature_importance = self.model.get_feature_importance()

        # 再学習
        metrics = self.model.train(self.X_accumulated, self.y_accumulated)

        # 新モデルの精度
        new_feature_importance = self.model.get_feature_importance()

        # モデル保存
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_path = f"models/xgboost_retrained_{timestamp}.pkl"
        self.model.save(model_path)

        # 特徴量重要度の変化を分析
        importance_changes = self._analyze_importance_changes(
            old_feature_importance,
            new_feature_importance
        )

        return {
            'status': 'success',
            'samples_used': len(self.X_accumulated),
            'metrics': metrics,
            'model_saved': model_path,
            'importance_changes': importance_changes
        }

    def _analyze_importance_changes(
        self,
        old_importance: Dict,
        new_importance: Dict
    ) -> Dict:
        """特徴量重要度の変化を分析"""
        changes = {}

        for feature, new_value in new_importance.items():
            old_value = old_importance.get(feature, 0)
            change = new_value - old_value
            change_rate = (change / old_value * 100) if old_value > 0 else 0

            changes[feature] = {
                'old': old_value,
                'new': new_value,
                'change': change,
                'change_rate': change_rate
            }

        # 変化が大きい順にソート
        sorted_changes = sorted(
            changes.items(),
            key=lambda x: abs(x[1]['change']),
            reverse=True
        )

        return {
            'top_increased': [
                {'feature': k, **v}
                for k, v in sorted_changes[:5]
                if v['change'] > 0
            ],
            'top_decreased': [
                {'feature': k, **v}
                for k, v in sorted_changes[:5]
                if v['change'] < 0
            ]
        }

    def suggest_improvements(self, outlier_analysis: Dict) -> List[Dict]:
        """
        外れ値分析から改善提案を生成

        Args:
            outlier_analysis: 外れ値分析結果

        Returns:
            list: 改善提案リスト
        """
        suggestions = []

        # 外れ値が多い場合
        if outlier_analysis['outlier_rate'] > 0.3:
            suggestions.append({
                'type': 'model_retrain',
                'priority': 'high',
                'suggestion': 'モデル再学習を推奨（外れ値率30%超）'
            })

        # 特徴量の問題
        feature_issues = outlier_analysis.get('feature_importance_issues', {})

        if 'overestimate_patterns' in feature_issues:
            patterns = feature_issues['overestimate_patterns']
            suggestions.append({
                'type': 'feature_weight',
                'priority': 'medium',
                'suggestion': f'過大評価パターン検出（{patterns["count"]}頭）',
                'details': patterns['common_characteristics']
            })

        if 'underestimate_patterns' in feature_issues:
            patterns = feature_issues['underestimate_patterns']
            suggestions.append({
                'type': 'feature_addition',
                'priority': 'high',
                'suggestion': f'過小評価パターン検出（{patterns["count"]}頭） - 新特徴量追加を検討',
                'details': patterns['common_characteristics']
            })

        return suggestions


# 使用例
if __name__ == "__main__":
    # モデル読み込み
    model = HorseRacingXGBoost()
    model.load('models/xgboost_v1.pkl')

    # 継続学習マネージャー
    learner = IncrementalLearner(model)

    # モック: 予想データと実際の結果
    prediction_data = {
        'ml_scores': [
            {
                'horse_number': 1,
                'horse_name': 'Horse1',
                'rank_score': 2.5,
                'features': {'speed_index_avg': 85, 'jockey_win_rate': 0.15}
            },
            {
                'horse_number': 2,
                'horse_name': 'Horse2',
                'rank_score': 1.2,
                'features': {'speed_index_avg': 90, 'jockey_win_rate': 0.20}
            }
        ]
    }

    actual_result = {
        'rankings': {1: 8, 2: 1}  # 1番は8着、2番は1着
    }

    # 外れ値分析
    analysis = learner.analyze_outliers(prediction_data, actual_result)
    print("外れ値分析結果:")
    print(analysis)

    # 改善提案
    suggestions = learner.suggest_improvements(analysis)
    print("\n改善提案:")
    for s in suggestions:
        print(f"- {s['suggestion']}")
