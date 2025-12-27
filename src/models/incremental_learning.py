"""
機械学習モデルの継続的学習

予想結果と実際の結果を比較し、外れ値を分析してモデルを再学習

主な機能：
- 外れ値検出（予測誤差≥3着）
- 外れ値パターン分析
- 学習データの蓄積
- モデルの自動再学習
- 特徴量重要度変化の追跡
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import pickle
from datetime import datetime
from pathlib import Path

from src.models.xgboost_model import HorseRacingXGBoost
from src.config import (
    ML_OUTLIER_THRESHOLD,
    ML_OUTLIER_RATE_THRESHOLD,
    ML_FEATURE_VARIANCE_THRESHOLD,
    LEARNING_DATA_DIR,
)
from src.exceptions import (
    ModelTrainError,
    InsufficientDataError,
    DataError,
)

# ロガー設定
logger = logging.getLogger(__name__)


class IncrementalLearner:
    """
    継続的学習マネージャー

    予想結果と実際の結果を比較し、外れ値を分析してモデルを再学習します。

    Attributes:
        model: 学習対象のXGBoostモデル
        data_dir: 学習データ保存ディレクトリ
        training_data_file: 学習データファイルパス
        X_accumulated: 蓄積された特徴量データ
        y_accumulated: 蓄積されたラベルデータ
    """

    def __init__(
        self,
        model: HorseRacingXGBoost,
        data_dir: str = LEARNING_DATA_DIR
    ):
        """
        Args:
            model: 学習対象のXGBoostモデル
            data_dir: 学習データ保存ディレクトリ（デフォルトは設定値）

        Raises:
            DataError: データディレクトリ作成に失敗した場合
        """
        self.model = model
        self.data_dir = Path(data_dir)

        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"学習データディレクトリ: {self.data_dir}")
        except Exception as e:
            logger.error(f"データディレクトリ作成失敗: {e}")
            raise DataError(f"データディレクトリ作成失敗: {e}") from e

        # 学習データの蓄積
        self.training_data_file = self.data_dir / "incremental_training_data.pkl"
        self.load_training_data()

    def load_training_data(self) -> None:
        """
        過去の学習データを読み込み

        Raises:
            DataError: データ読み込みに失敗した場合
        """
        if self.training_data_file.exists():
            try:
                with open(self.training_data_file, 'rb') as f:
                    data = pickle.load(f)
                    self.X_accumulated = data['X']
                    self.y_accumulated = data['y']

                logger.info(
                    f"学習データ読み込み成功: "
                    f"{len(self.X_accumulated)}サンプル"
                )
            except Exception as e:
                logger.error(f"学習データ読み込み失敗: {e}")
                # 読み込み失敗時は空データで初期化
                self.X_accumulated = pd.DataFrame()
                self.y_accumulated = pd.Series(dtype=float)
        else:
            logger.info("学習データファイルが存在しないため、新規作成")
            self.X_accumulated = pd.DataFrame()
            self.y_accumulated = pd.Series(dtype=float)

    def save_training_data(self) -> None:
        """
        学習データを保存

        Raises:
            DataError: データ保存に失敗した場合
        """
        try:
            with open(self.training_data_file, 'wb') as f:
                pickle.dump({
                    'X': self.X_accumulated,
                    'y': self.y_accumulated,
                    'updated_at': datetime.now()
                }, f)

            logger.debug(f"学習データ保存成功: {len(self.X_accumulated)}サンプル")
        except Exception as e:
            logger.error(f"学習データ保存失敗: {e}")
            raise DataError(f"学習データ保存失敗: {e}") from e

    def analyze_outliers(
        self,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        外れ値を分析

        Args:
            prediction_data: 予想時のデータ（ml_scores含む）
            actual_result: 実際の結果（rankings含む）

        Returns:
            外れ値分析結果（以下のキーを含む）:
                - total_horses: 総頭数
                - outlier_count: 外れ値数
                - outlier_rate: 外れ値率
                - outliers: 外れ値リスト
                - avg_error: 平均誤差
                - feature_importance_issues: 特徴量の問題点

        Raises:
            DataError: 分析に失敗した場合
        """
        try:
            ml_scores = prediction_data['ml_scores']
            rankings = actual_result.get('rankings', {})
            outliers: List[Dict[str, Any]] = []
            all_errors: List[float] = []

            for horse_data in ml_scores:
                horse_number = horse_data['horse_number']
                predicted_rank = horse_data['rank_score']

                # 実際の着順を取得
                actual_rank = rankings.get(horse_number)

                if actual_rank is None:
                    continue

                # 予測誤差
                error = abs(predicted_rank - actual_rank)
                all_errors.append(error)

                # 外れ値判定
                is_outlier = error >= ML_OUTLIER_THRESHOLD

                outlier_info: Dict[str, Any] = {
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
            analysis: Dict[str, Any] = {
                'total_horses': len(ml_scores),
                'outlier_count': len(outliers),
                'outlier_rate': len(outliers) / len(ml_scores) if ml_scores else 0,
                'outliers': sorted(outliers, key=lambda x: x['error'], reverse=True),
                'avg_error': float(np.mean(all_errors)) if all_errors else 0.0,
                'feature_importance_issues': self._analyze_feature_issues(outliers)
            }

            logger.info(
                f"外れ値分析完了: {analysis['outlier_count']}/{analysis['total_horses']}頭 "
                f"({analysis['outlier_rate']:.1%})"
            )

            return analysis

        except Exception as e:
            logger.error(f"外れ値分析失敗: {e}")
            raise DataError(f"外れ値分析失敗: {e}") from e

    def _classify_outlier(self, predicted: float, actual: int) -> str:
        """
        外れ値のタイプを分類

        Args:
            predicted: 予測着順
            actual: 実際の着順

        Returns:
            外れ値タイプ（major_overestimate, overestimate, major_underestimate, underestimate）
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

    def _analyze_feature_issues(
        self,
        outliers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        外れ値の特徴量を分析して問題点を特定

        Args:
            outliers: 外れ値リスト

        Returns:
            特徴量の問題点
        """
        if not outliers:
            return {}

        # 過大評価と過小評価を分ける
        overestimated = [
            o for o in outliers
            if 'overestimate' in o['outlier_type']
        ]
        underestimated = [
            o for o in outliers
            if 'underestimate' in o['outlier_type']
        ]

        issues: Dict[str, Any] = {}

        # 過大評価された馬の共通特徴
        if overestimated:
            try:
                over_features = pd.DataFrame([o['features'] for o in overestimated])
                issues['overestimate_patterns'] = {
                    'count': len(overestimated),
                    'avg_features': over_features.mean().to_dict(),
                    'common_characteristics': self._find_common_characteristics(over_features)
                }
            except Exception as e:
                logger.warning(f"過大評価パターン分析で警告: {e}")

        # 過小評価された馬の共通特徴
        if underestimated:
            try:
                under_features = pd.DataFrame([o['features'] for o in underestimated])
                issues['underestimate_patterns'] = {
                    'count': len(underestimated),
                    'avg_features': under_features.mean().to_dict(),
                    'common_characteristics': self._find_common_characteristics(under_features)
                }
            except Exception as e:
                logger.warning(f"過小評価パターン分析で警告: {e}")

        return issues

    def _find_common_characteristics(self, features_df: pd.DataFrame) -> List[str]:
        """
        共通の特徴を見つける

        Args:
            features_df: 特徴量DataFrame

        Returns:
            共通特徴のリスト
        """
        characteristics: List[str] = []

        try:
            # 各特徴量の平均と標準偏差を計算
            for col in features_df.columns:
                mean_val = features_df[col].mean()
                std_val = features_df[col].std()

                # 特徴的な値（分散が小さい = 共通して高い/低い）を特定
                if std_val < mean_val * ML_FEATURE_VARIANCE_THRESHOLD:
                    if mean_val > 0.7:  # 高い値
                        characteristics.append(f"{col}: 高い ({mean_val:.2f})")
                    elif mean_val < 0.3:  # 低い値
                        characteristics.append(f"{col}: 低い ({mean_val:.2f})")

        except Exception as e:
            logger.warning(f"共通特徴抽出で警告: {e}")

        return characteristics

    def add_training_sample(
        self,
        features: pd.DataFrame,
        actual_ranks: pd.Series
    ) -> None:
        """
        新しい学習サンプルを追加

        Args:
            features: 特徴量（DataFrame）
            actual_ranks: 実際の着順（Series）

        Raises:
            DataError: データ追加に失敗した場合
        """
        try:
            # データを蓄積
            if self.X_accumulated.empty:
                self.X_accumulated = features.copy()
                self.y_accumulated = actual_ranks.copy()
            else:
                self.X_accumulated = pd.concat(
                    [self.X_accumulated, features],
                    ignore_index=True
                )
                self.y_accumulated = pd.concat(
                    [self.y_accumulated, actual_ranks],
                    ignore_index=True
                )

            # 保存
            self.save_training_data()

            logger.info(f"学習サンプル追加: 合計 {len(self.X_accumulated)} サンプル")
            print(f"学習サンプル追加: 合計 {len(self.X_accumulated)} サンプル")

        except Exception as e:
            logger.error(f"学習サンプル追加失敗: {e}")
            raise DataError(f"学習サンプル追加失敗: {e}") from e

    def retrain_model(self, min_samples: int = 100) -> Dict[str, Any]:
        """
        モデルを再学習

        Args:
            min_samples: 最小サンプル数（これ以下なら学習しない）

        Returns:
            再学習結果（以下のキーを含む）:
                - status: 'success', 'skipped', 'failed'
                - reason: スキップ/失敗理由（該当する場合）
                - current_samples: 現在のサンプル数
                - samples_used: 学習に使用したサンプル数（成功時）
                - metrics: 学習メトリクス（成功時）
                - model_saved: 保存したモデルパス（成功時）
                - importance_changes: 特徴量重要度の変化（成功時）

        Raises:
            InsufficientDataError: サンプル数が不足している場合
            ModelTrainError: 再学習に失敗した場合
        """
        # サンプル数チェック
        if len(self.X_accumulated) < min_samples:
            logger.info(
                f"サンプル数不足でスキップ: "
                f"{len(self.X_accumulated)}/{min_samples}"
            )
            return {
                'status': 'skipped',
                'reason': f'サンプル数不足 ({len(self.X_accumulated)}/{min_samples})',
                'current_samples': len(self.X_accumulated)
            }

        try:
            logger.info("=" * 50)
            logger.info("モデル再学習開始")
            logger.info("=" * 50)
            logger.info(f"学習サンプル数: {len(self.X_accumulated)}")
            print(f"\n===== モデル再学習開始 =====")
            print(f"学習サンプル数: {len(self.X_accumulated)}")

            # 旧モデルの特徴量重要度を記録
            old_feature_importance = self.model.get_feature_importance()

            # 再学習
            metrics = self.model.train(self.X_accumulated, self.y_accumulated)

            # 新モデルの特徴量重要度
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

            logger.info(f"モデル再学習成功: {model_path}")
            logger.info("=" * 50)

            return {
                'status': 'success',
                'samples_used': len(self.X_accumulated),
                'metrics': metrics,
                'model_saved': model_path,
                'importance_changes': importance_changes
            }

        except Exception as e:
            logger.error(f"モデル再学習失敗: {e}")
            raise ModelTrainError(f"モデル再学習失敗: {e}") from e

    def _analyze_importance_changes(
        self,
        old_importance: Dict[str, float],
        new_importance: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        特徴量重要度の変化を分析

        Args:
            old_importance: 旧特徴量重要度
            new_importance: 新特徴量重要度

        Returns:
            重要度変化の分析結果
        """
        changes: Dict[str, Dict[str, float]] = {}

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

    def suggest_improvements(
        self,
        outlier_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        外れ値分析から改善提案を生成

        Args:
            outlier_analysis: 外れ値分析結果

        Returns:
            改善提案リスト
        """
        suggestions: List[Dict[str, Any]] = []

        try:
            # 外れ値が多い場合
            if outlier_analysis['outlier_rate'] > ML_OUTLIER_RATE_THRESHOLD:
                suggestions.append({
                    'type': 'model_retrain',
                    'priority': 'high',
                    'suggestion': f'モデル再学習を推奨（外れ値率{ML_OUTLIER_RATE_THRESHOLD:.0%}超）'
                })

            # 特徴量の問題
            feature_issues = outlier_analysis.get('feature_importance_issues', {})

            if 'overestimate_patterns' in feature_issues:
                patterns = feature_issues['overestimate_patterns']
                suggestions.append({
                    'type': 'feature_weight',
                    'priority': 'medium',
                    'suggestion': f'過大評価パターン検出（{patterns["count"]}頭）',
                    'details': patterns.get('common_characteristics', [])
                })

            if 'underestimate_patterns' in feature_issues:
                patterns = feature_issues['underestimate_patterns']
                suggestions.append({
                    'type': 'feature_addition',
                    'priority': 'high',
                    'suggestion': f'過小評価パターン検出（{patterns["count"]}頭） - 新特徴量追加を検討',
                    'details': patterns.get('common_characteristics', [])
                })

        except Exception as e:
            logger.warning(f"改善提案生成で警告: {e}")

        return suggestions


# 使用例
if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # モデル読み込み
    model = HorseRacingXGBoost()

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
    try:
        analysis = learner.analyze_outliers(prediction_data, actual_result)
        print("\n外れ値分析結果:")
        print(analysis)

        # 改善提案
        suggestions = learner.suggest_improvements(analysis)
        print("\n改善提案:")
        for s in suggestions:
            print(f"- {s['suggestion']}")
    except (DataError, ModelTrainError) as e:
        logger.error(f"分析失敗: {e}")
