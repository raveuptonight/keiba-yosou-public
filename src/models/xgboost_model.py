"""
XGBoost競馬予想モデル

着順予測と勝率予測を行う
"""

import logging
import numpy as np
import pandas as pd
import pickle
from pathlib import Path
from typing import Optional, Dict, Any
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

from src.config import (
    XGBOOST_N_ESTIMATORS,
    XGBOOST_MAX_DEPTH,
    XGBOOST_LEARNING_RATE,
    XGBOOST_SUBSAMPLE,
    XGBOOST_COLSAMPLE_BYTREE,
    XGBOOST_MIN_CHILD_WEIGHT,
    XGBOOST_GAMMA,
    XGBOOST_REG_ALPHA,
    XGBOOST_REG_LAMBDA,
    XGBOOST_RANDOM_STATE,
    ML_MIN_RETRAIN_SAMPLES,
    FEATURE_MOCK_RANDOM_SEED,
)
from src.exceptions import (
    ModelNotFoundError,
    ModelLoadError,
    ModelTrainError,
    ModelPredictionError,
    InsufficientDataError,
)

# ロガー設定
logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
    logger.info("XGBoost インポート成功")
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost がインストールされていません。モデル訓練は利用できません")


class HorseRacingXGBoost:
    """
    競馬予想XGBoostモデル

    着順予測と勝率予測を行います。
    """

    def __init__(self):
        """初期化"""
        self.model = None
        self.feature_names = None
        self.is_trained = False
        logger.debug("HorseRacingXGBoost初期化完了")

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        early_stopping_rounds: int = 50,
        verbose: int = 100
    ) -> Dict[str, float]:
        """
        モデル訓練

        Args:
            X: 特徴量（DataFrame）
            y: 目的変数（着順）
            test_size: テストデータの割合
            early_stopping_rounds: Early Stopping ラウンド数
            verbose: ログ出力頻度

        Returns:
            評価メトリクス（rmse, mae）

        Raises:
            ImportError: XGBoostがインストールされていない場合
            InsufficientDataError: 訓練データが不足している場合
            ModelTrainError: モデル訓練に失敗した場合
        """
        if not XGBOOST_AVAILABLE:
            raise ImportError("xgboost is not installed. Run: pip install xgboost")

        # データ検証
        if len(X) < ML_MIN_RETRAIN_SAMPLES:
            raise InsufficientDataError(
                f"訓練データ不足: {len(X)}件 (最低{ML_MIN_RETRAIN_SAMPLES}件必要)"
            )

        if len(X) != len(y):
            raise ModelTrainError(f"特徴量とラベルの件数が一致しません: X={len(X)}, y={len(y)}")

        try:
            logger.info(f"モデル訓練開始: samples={len(X)}, features={len(X.columns)}")

            # データ分割
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=XGBOOST_RANDOM_STATE
            )

            logger.debug(f"データ分割完了: train={len(X_train)}, test={len(X_test)}")

            # XGBoostモデル
            self.model = xgb.XGBRegressor(
                objective='reg:squarederror',
                n_estimators=XGBOOST_N_ESTIMATORS,
                learning_rate=XGBOOST_LEARNING_RATE,
                max_depth=XGBOOST_MAX_DEPTH,
                subsample=XGBOOST_SUBSAMPLE,
                colsample_bytree=XGBOOST_COLSAMPLE_BYTREE,
                min_child_weight=XGBOOST_MIN_CHILD_WEIGHT,
                gamma=XGBOOST_GAMMA,
                reg_alpha=XGBOOST_REG_ALPHA,
                reg_lambda=XGBOOST_REG_LAMBDA,
                random_state=XGBOOST_RANDOM_STATE,
                early_stopping_rounds=early_stopping_rounds
            )

            # 訓練
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=verbose
            )

            # 特徴量名を保存
            self.feature_names = X.columns.tolist()
            self.is_trained = True

            # 評価
            y_pred = self.model.predict(X_test)
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))

            logger.info(f"訓練完了: RMSE={rmse:.4f}, MAE={mae:.4f}")
            print(f"✅ モデル訓練完了: RMSE={rmse:.4f}, MAE={mae:.4f}")

            return {
                'rmse': rmse,
                'mae': mae
            }

        except InsufficientDataError:
            # 既知のエラーは再スロー
            raise
        except Exception as e:
            logger.error(f"モデル訓練失敗: {e}")
            raise ModelTrainError(f"モデル訓練失敗: {e}") from e

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        着順予測

        Args:
            X: 特徴量（DataFrame）

        Returns:
            予測着順（1-18の範囲）

        Raises:
            ModelPredictionError: 予測に失敗した場合
        """
        if not self.is_trained and self.model is None:
            # モデル未訓練の場合、モックデータを返す
            logger.warning(f"モデル未訓練、モック予測を返却: n={len(X)}")
            return self._mock_predict(len(X))

        try:
            # 特徴量の整合性チェック
            if self.feature_names is not None:
                if list(X.columns) != self.feature_names:
                    logger.warning(
                        f"特徴量の順序が異なる可能性: expected={self.feature_names[:3]}..., got={list(X.columns)[:3]}..."
                    )

            predictions = self.model.predict(X)
            # 1-18の範囲にクリップ
            predictions_clipped = np.clip(predictions, 1, 18)

            logger.debug(f"予測完了: n={len(X)}, range=[{predictions_clipped.min():.2f}, {predictions_clipped.max():.2f}]")
            return predictions_clipped

        except Exception as e:
            logger.error(f"予測失敗: {e}")
            raise ModelPredictionError(f"予測失敗: {e}") from e

    def predict_win_probability(self, X: pd.DataFrame) -> np.ndarray:
        """
        勝率予測

        Args:
            X: 特徴量（DataFrame）

        Returns:
            勝率（0-1の範囲）

        Raises:
            ModelPredictionError: 予測に失敗した場合
        """
        try:
            predictions = self.predict(X)
            # 着順予測を勝率に変換（1着予測 = 高勝率）
            # シグモイド関数で変換: 1 / (1 + exp(rank - 1))
            win_probs = 1 / (1 + np.exp(predictions - 1))

            logger.debug(f"勝率予測完了: n={len(X)}, mean_prob={win_probs.mean():.4f}")
            return win_probs

        except ModelPredictionError:
            # 既知のエラーは再スロー
            raise
        except Exception as e:
            logger.error(f"勝率予測失敗: {e}")
            raise ModelPredictionError(f"勝率予測失敗: {e}") from e

    def get_feature_importance(self) -> Dict[str, float]:
        """
        特徴量重要度を取得

        Returns:
            {特徴量名: 重要度}（重要度降順）

        Raises:
            ModelPredictionError: 重要度取得に失敗した場合
        """
        if not self.is_trained or self.model is None:
            logger.warning("モデル未訓練、空の重要度辞書を返却")
            return {}

        try:
            importance = self.model.feature_importances_
            importance_dict = dict(sorted(
                zip(self.feature_names, importance),
                key=lambda x: x[1],
                reverse=True
            ))

            logger.debug(f"特徴量重要度取得: top_feature={list(importance_dict.keys())[0]}")
            return importance_dict

        except Exception as e:
            logger.error(f"特徴量重要度取得失敗: {e}")
            raise ModelPredictionError(f"特徴量重要度取得失敗: {e}") from e

    def save(self, filepath: str) -> None:
        """
        モデル保存

        Args:
            filepath: 保存先パス

        Raises:
            ModelTrainError: モデルが訓練されていない場合
            ModelLoadError: ファイル保存に失敗した場合
        """
        if not self.is_trained:
            raise ModelTrainError("モデルが訓練されていません")

        try:
            # ディレクトリ作成
            filepath_obj = Path(filepath)
            filepath_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'feature_names': self.feature_names,
                    'is_trained': self.is_trained
                }, f)

            logger.info(f"モデル保存完了: {filepath}")
            print(f"✅ モデル保存完了: {filepath}")

        except Exception as e:
            logger.error(f"モデル保存失敗: {e}")
            raise ModelLoadError(f"モデル保存失敗: {e}") from e

    def load(self, filepath: str) -> None:
        """
        モデル読み込み

        Args:
            filepath: モデルファイルパス

        Raises:
            ModelNotFoundError: モデルファイルが見つからない場合
            ModelLoadError: モデル読み込みに失敗した場合
        """
        filepath_obj = Path(filepath)

        if not filepath_obj.exists():
            logger.warning(f"モデルファイル未発見、モックモードで動作: {filepath}")
            self.is_trained = False
            raise ModelNotFoundError(f"モデルファイルが見つかりません: {filepath}")

        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.feature_names = data['feature_names']
                self.is_trained = data.get('is_trained', True)

            logger.info(f"モデル読み込み完了: {filepath}, features={len(self.feature_names)}")
            print(f"✅ モデル読み込み完了: {filepath} (特徴量数: {len(self.feature_names)})")

        except Exception as e:
            logger.error(f"モデル読み込み失敗: {e}")
            self.is_trained = False
            raise ModelLoadError(f"モデル読み込み失敗: {e}") from e

    def _mock_predict(self, n: int) -> np.ndarray:
        """
        モック予測（モデル未訓練時）

        Args:
            n: 予測数

        Returns:
            モック着順（1-18の範囲）
        """
        # ランダムな着順（1-18）
        np.random.seed(FEATURE_MOCK_RANDOM_SEED)
        mock_predictions = np.random.uniform(1, 18, n)

        logger.debug(f"モック予測生成: n={n}")
        return mock_predictions
