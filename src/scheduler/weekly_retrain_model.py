"""
週次モデル再学習モジュール

毎週火曜23:00に実行して：
1. 最新データでensemble_model（XGBoost + LightGBM）を再学習
2. 新旧モデルのバックテスト比較
3. 改善があれば新モデルをデプロイ
"""

import logging
import json
import os
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional
import joblib
import numpy as np
import pandas as pd

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeeklyRetrain:
    """週次再学習クラス（ensemble_model用）"""

    def __init__(
        self,
        model_dir: str = "/app/models",
        backup_dir: str = "/app/models/backup"
    ):
        self.model_dir = Path(model_dir)
        self.backup_dir = Path(backup_dir)
        self.current_model_path = self.model_dir / "ensemble_model_latest.pkl"

    def backup_current_model(self) -> Optional[str]:
        """現在のモデルをバックアップ"""
        if not self.current_model_path.exists():
            logger.warning("現在のモデルが見つかりません")
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"ensemble_model_{timestamp}.pkl"

        shutil.copy(self.current_model_path, backup_path)
        logger.info(f"モデルバックアップ: {backup_path}")

        return str(backup_path)

    def train_new_model(self, years: int = 3) -> Dict:
        """新しいensemble_modelを学習"""
        import xgboost as xgb
        import lightgbm as lgb

        logger.info(f"ensemble_model学習開始（過去{years}年）")

        db = get_db()
        conn = db.get_connection()

        try:
            extractor = FastFeatureExtractor(conn)

            # データ抽出
            current_year = date.today().year
            all_data = []

            for year in range(current_year - years, current_year + 1):
                logger.info(f"  {year}年データ抽出中...")
                year_data = extractor.extract_year_data(year)
                if year_data is not None and len(year_data) > 0:
                    if isinstance(year_data, pd.DataFrame):
                        all_data.append(year_data)
                    else:
                        all_data.append(pd.DataFrame(year_data))
                    logger.info(f"    {len(year_data)}件")

            if not all_data:
                logger.error("学習データなし")
                return {'status': 'error', 'message': 'no_training_data'}

            # DataFrame結合
            df = pd.concat(all_data, ignore_index=True)
            logger.info(f"総サンプル数: {len(df)}")

            # 特徴量とターゲット
            exclude_cols = ['race_code', 'umaban', 'bamei', 'target', 'kakutei_chakujun']
            feature_cols = [c for c in df.columns if c not in exclude_cols]

            X = df[feature_cols].fillna(0)
            y = df['target']

            # 時系列分割
            split_idx = int(len(df) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            # XGBoostモデル
            logger.info("XGBoostモデル学習中...")
            xgb_model = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1
            )
            xgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )

            # LightGBMモデル
            logger.info("LightGBMモデル学習中...")
            lgb_model = lgb.LGBMRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                verbose=-1
            )
            lgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )

            # アンサンブル評価
            xgb_pred = xgb_model.predict(X_val)
            lgb_pred = lgb_model.predict(X_val)
            ensemble_pred = (xgb_pred + lgb_pred) / 2

            rmse = np.sqrt(np.mean((ensemble_pred - y_val) ** 2))
            logger.info(f"検証RMSE (ensemble): {rmse:.4f}")

            # 一時保存
            temp_model_path = self.model_dir / "ensemble_model_new.pkl"
            model_data = {
                'xgb_model': xgb_model,
                'lgb_model': lgb_model,
                'feature_names': feature_cols,
                'trained_at': datetime.now().isoformat(),
                'training_samples': len(df),
                'validation_rmse': float(rmse),
                'years': years
            }
            joblib.dump(model_data, temp_model_path)

            return {
                'status': 'success',
                'model_path': str(temp_model_path),
                'rmse': float(rmse),
                'samples': len(df)
            }

        except Exception as e:
            logger.error(f"学習エラー: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

        finally:
            conn.close()

    def compare_models(self, new_model_path: str, test_year: int = None) -> Dict:
        """新旧モデルを比較"""
        if test_year is None:
            test_year = date.today().year

        logger.info(f"モデル比較（テスト年: {test_year}）")

        # モデル読み込み
        try:
            old_model_data = joblib.load(self.current_model_path)
            new_model_data = joblib.load(new_model_path)
        except Exception as e:
            logger.error(f"モデル読み込みエラー: {e}")
            return {'status': 'error', 'message': str(e)}

        old_xgb = old_model_data['xgb_model']
        old_lgb = old_model_data['lgb_model']
        old_features = old_model_data['feature_names']

        new_xgb = new_model_data['xgb_model']
        new_lgb = new_model_data['lgb_model']
        new_features = new_model_data['feature_names']

        # テストデータ取得
        db = get_db()
        conn = db.get_connection()

        try:
            extractor = FastFeatureExtractor(conn)
            test_data = extractor.extract_year_data(test_year)

            if test_data is None or len(test_data) == 0:
                return {'status': 'error', 'message': 'no_test_data'}

            if isinstance(test_data, list):
                df = pd.DataFrame(test_data)
            else:
                df = test_data

            logger.info(f"テストサンプル数: {len(df)}")

            # 旧モデルで予測（アンサンブル）
            X_old = df[old_features].fillna(0)
            old_pred = (old_xgb.predict(X_old) + old_lgb.predict(X_old)) / 2
            old_rmse = np.sqrt(np.mean((old_pred - df['target']) ** 2))

            # 新モデルで予測（アンサンブル）
            X_new = df[new_features].fillna(0)
            new_pred = (new_xgb.predict(X_new) + new_lgb.predict(X_new)) / 2
            new_rmse = np.sqrt(np.mean((new_pred - df['target']) ** 2))

            improvement = (old_rmse - new_rmse) / old_rmse * 100

            logger.info(f"旧モデル RMSE: {old_rmse:.4f}")
            logger.info(f"新モデル RMSE: {new_rmse:.4f}")
            logger.info(f"改善率: {improvement:.2f}%")

            return {
                'status': 'success',
                'old_rmse': float(old_rmse),
                'new_rmse': float(new_rmse),
                'improvement': float(improvement),
                'test_samples': len(df)
            }

        finally:
            conn.close()

    def deploy_new_model(self, new_model_path: str):
        """新モデルをデプロイ"""
        # 現在のモデルをバックアップ
        self.backup_current_model()

        # 新モデルを本番に配置
        shutil.move(new_model_path, self.current_model_path)
        logger.info(f"新モデルデプロイ完了: {self.current_model_path}")

    def send_notification(self, result: Dict):
        """再学習結果を通知"""
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        if not webhook_url:
            return

        try:
            import requests

            if result.get('deployed'):
                lines = [
                    "🔄 **週次モデル再学習完了**",
                    "",
                    f"モデル: ensemble_model (XGBoost + LightGBM)",
                    f"学習サンプル数: {result['training'].get('samples', 0):,}",
                    f"新モデルRMSE: {result['comparison'].get('new_rmse', 0):.4f}",
                    f"改善率: {result['comparison'].get('improvement', 0):.2f}%",
                    "",
                    "✅ 新モデルをデプロイしました"
                ]
            else:
                lines = [
                    "🔄 **週次モデル再学習完了**",
                    "",
                    f"モデル: ensemble_model (XGBoost + LightGBM)",
                    f"学習サンプル数: {result['training'].get('samples', 0):,}",
                    f"新モデルRMSE: {result['comparison'].get('new_rmse', 0):.4f}",
                    f"改善率: {result['comparison'].get('improvement', 0):.2f}%",
                    "",
                    "⚠️ 改善なしのため現行モデルを維持"
                ]

            payload = {"content": "\n".join(lines)}
            requests.post(webhook_url, json=payload, timeout=10)

        except Exception as e:
            logger.error(f"通知エラー: {e}")

    def run_weekly_job(self, force_deploy: bool = False, notify: bool = True):
        """週次ジョブを実行"""
        logger.info("=" * 50)
        logger.info(f"週次モデル再学習開始: {datetime.now()}")
        logger.info("=" * 50)

        result = {
            'date': date.today().isoformat(),
            'deployed': False
        }

        # 1. 新モデル学習
        training_result = self.train_new_model(years=3)
        result['training'] = training_result

        if training_result['status'] != 'success':
            logger.error(f"学習失敗: {training_result}")
            return result

        new_model_path = training_result['model_path']

        # 2. 比較（現行モデルがある場合）
        if self.current_model_path.exists():
            comparison = self.compare_models(new_model_path)
            result['comparison'] = comparison

            if comparison['status'] == 'success':
                # 改善があればデプロイ（または強制デプロイ）
                if comparison['improvement'] > 0 or force_deploy:
                    self.deploy_new_model(new_model_path)
                    result['deployed'] = True
                    logger.info("新モデルをデプロイしました")
                else:
                    logger.info("改善なし、現行モデルを維持")
                    # 一時ファイル削除
                    Path(new_model_path).unlink()
        else:
            # 現行モデルがない場合はそのままデプロイ
            shutil.move(new_model_path, self.current_model_path)
            result['deployed'] = True
            result['comparison'] = {'note': 'initial_deployment'}
            logger.info("初回デプロイ完了")

        # 3. 通知
        if notify:
            self.send_notification(result)

        # 結果保存
        result_path = self.model_dir / f"retrain_result_{date.today().strftime('%Y%m%d')}.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="週次モデル再学習（ensemble_model）")
    parser.add_argument("--force", "-f", action="store_true", help="改善なしでもデプロイ")
    parser.add_argument("--no-notify", action="store_true", help="Discord通知しない")

    args = parser.parse_args()

    retrain = WeeklyRetrain()
    result = retrain.run_weekly_job(
        force_deploy=args.force,
        notify=not args.no_notify
    )

    print("\n=== 再学習結果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
