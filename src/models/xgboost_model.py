"""
XGBoost競馬予想モデル

着順予測と勝率予測を行う
"""

import numpy as np
import pandas as pd
import pickle
from typing import Optional, Dict
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("Warning: xgboost not installed. Model training will not be available.")


class HorseRacingXGBoost:
    """競馬予想XGBoostモデル"""

    def __init__(self):
        self.model = None
        self.feature_names = None
        self.is_trained = False

    def train(self, X: pd.DataFrame, y: pd.Series, test_size: float = 0.2):
        """
        モデル訓練

        Args:
            X: 特徴量（DataFrame）
            y: 目的変数（着順）
            test_size: テストデータの割合
        """
        if not XGBOOST_AVAILABLE:
            raise ImportError("xgboost is not installed. Run: pip install xgboost")

        print("モデル訓練開始...")

        # データ分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        # XGBoostモデル
        self.model = xgb.XGBRegressor(
            objective='reg:squarederror',
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            early_stopping_rounds=50
        )

        # 訓練
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=100
        )

        # 特徴量名を保存
        self.feature_names = X.columns.tolist()
        self.is_trained = True

        # 評価
        y_pred = self.model.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)

        print(f"\n訓練完了!")
        print(f"Test RMSE: {rmse:.4f}")
        print(f"Test MAE: {mae:.4f}")

        return {
            'rmse': rmse,
            'mae': mae
        }

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        着順予測

        Args:
            X: 特徴量（DataFrame）

        Returns:
            array: 予測着順（1-18の範囲）
        """
        if not self.is_trained and self.model is None:
            # モデル未訓練の場合、モックデータを返す
            return self._mock_predict(len(X))

        predictions = self.model.predict(X)
        # 1-18の範囲にクリップ
        return np.clip(predictions, 1, 18)

    def predict_win_probability(self, X: pd.DataFrame) -> np.ndarray:
        """
        勝率予測

        Args:
            X: 特徴量（DataFrame）

        Returns:
            array: 勝率（0-1の範囲）
        """
        predictions = self.predict(X)
        # 着順予測を勝率に変換（1着予測 = 高勝率）
        # シグモイド関数で変換: 1 / (1 + exp(rank - 1))
        return 1 / (1 + np.exp(predictions - 1))

    def get_feature_importance(self) -> Dict[str, float]:
        """
        特徴量重要度を取得

        Returns:
            dict: {特徴量名: 重要度}
        """
        if not self.is_trained or self.model is None:
            return {}

        importance = self.model.feature_importances_
        return dict(sorted(
            zip(self.feature_names, importance),
            key=lambda x: x[1],
            reverse=True
        ))

    def save(self, filepath: str):
        """
        モデル保存

        Args:
            filepath: 保存先パス
        """
        if not self.is_trained:
            raise ValueError("モデルが訓練されていません")

        with open(filepath, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'feature_names': self.feature_names,
                'is_trained': self.is_trained
            }, f)

        print(f"モデル保存完了: {filepath}")

    def load(self, filepath: str):
        """
        モデル読み込み

        Args:
            filepath: モデルファイルパス
        """
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.feature_names = data['feature_names']
                self.is_trained = data.get('is_trained', True)

            print(f"モデル読み込み完了: {filepath}")
            print(f"特徴量数: {len(self.feature_names)}")
        except FileNotFoundError:
            print(f"Warning: モデルファイルが見つかりません: {filepath}")
            print("モックモードで動作します")
            self.is_trained = False

    def _mock_predict(self, n: int) -> np.ndarray:
        """
        モック予測（モデル未訓練時）

        Args:
            n: 予測数

        Returns:
            array: モック着順
        """
        # ランダムな着順（1-18）
        np.random.seed(42)
        return np.random.uniform(1, 18, n)
