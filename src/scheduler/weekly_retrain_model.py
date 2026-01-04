"""
週次モデル再学習モジュール

毎週火曜23:00に実行して：
1. 最新データでensemble_model（XGBoost + LightGBM）を再学習
2. 分類モデル（勝利/複勝）+ キャリブレーション
3. 新旧モデルのバックテスト比較
4. 改善があれば新モデルをデプロイ
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
from sklearn.isotonic import IsotonicRegression

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
        model_dir: str = None,
        backup_dir: str = None
    ):
        # デフォルトパス: ローカル環境とDocker環境の両方に対応
        if model_dir is None:
            if Path("/app/models").exists():
                model_dir = "/app/models"
            else:
                model_dir = str(Path(__file__).parent.parent.parent / "models")
        if backup_dir is None:
            backup_dir = str(Path(model_dir) / "backup")
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
        """新しいensemble_modelを学習（回帰 + 分類 + キャリブレーション）"""
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

            # 特徴量とターゲット（文字列型カラムを除外）
            exclude_cols = ['race_code', 'umaban', 'bamei', 'target', 'kakutei_chakujun', 'kettonum']
            # 数値型のみ抽出
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            feature_cols = [c for c in numeric_cols if c not in exclude_cols]

            X = df[feature_cols].fillna(0)
            y = df['target']

            # 分類用ターゲット
            y_win = (y == 1).astype(int)
            y_place = (y <= 3).astype(int)

            # 時系列分割
            split_idx = int(len(df) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            y_win_train, y_win_val = y_win[:split_idx], y_win[split_idx:]
            y_place_train, y_place_val = y_place[:split_idx], y_place[split_idx:]

            logger.info(f"訓練: {len(X_train)}, 検証: {len(X_val)}")

            # 共通パラメータ
            base_params = {
                'n_estimators': 500,
                'max_depth': 7,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': 42,
                'n_jobs': -1
            }

            models = {}

            # ===== 1. 回帰モデル =====
            # XGBoost回帰
            logger.info("XGBoost回帰モデル学習中...")
            xgb_reg = xgb.XGBRegressor(**base_params)
            xgb_reg.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            models['xgb_regressor'] = xgb_reg

            # LightGBM回帰
            logger.info("LightGBM回帰モデル学習中...")
            lgb_reg = lgb.LGBMRegressor(**base_params, verbose=-1)
            lgb_reg.fit(X_train, y_train, eval_set=[(X_val, y_val)])
            models['lgb_regressor'] = lgb_reg

            # アンサンブル評価
            xgb_pred = xgb_reg.predict(X_val)
            lgb_pred = lgb_reg.predict(X_val)
            ensemble_pred = (xgb_pred + lgb_pred) / 2
            rmse = np.sqrt(np.mean((ensemble_pred - y_val) ** 2))
            logger.info(f"回帰RMSE (ensemble): {rmse:.4f}")

            # ===== 2. 勝利分類モデル =====
            win_weight = len(y_win_train[y_win_train == 0]) / max(len(y_win_train[y_win_train == 1]), 1)

            logger.info("XGBoost勝利分類モデル学習中...")
            xgb_win = xgb.XGBClassifier(**base_params, scale_pos_weight=win_weight)
            xgb_win.fit(X_train, y_win_train, eval_set=[(X_val, y_win_val)], verbose=False)
            models['xgb_win'] = xgb_win

            logger.info("LightGBM勝利分類モデル学習中...")
            lgb_win = lgb.LGBMClassifier(**base_params, scale_pos_weight=win_weight, verbose=-1)
            lgb_win.fit(X_train, y_win_train, eval_set=[(X_val, y_win_val)])
            models['lgb_win'] = lgb_win

            # 勝利アンサンブル確率
            xgb_win_prob = xgb_win.predict_proba(X_val)[:, 1]
            lgb_win_prob = lgb_win.predict_proba(X_val)[:, 1]
            ensemble_win_prob = (xgb_win_prob + lgb_win_prob) / 2
            win_accuracy = ((ensemble_win_prob > 0.5) == y_win_val).mean()
            logger.info(f"勝利分類精度 (ensemble): {win_accuracy:.4f}")

            # ===== 3. 複勝分類モデル =====
            place_weight = len(y_place_train[y_place_train == 0]) / max(len(y_place_train[y_place_train == 1]), 1)

            logger.info("XGBoost複勝分類モデル学習中...")
            xgb_place = xgb.XGBClassifier(**base_params, scale_pos_weight=place_weight)
            xgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)], verbose=False)
            models['xgb_place'] = xgb_place

            logger.info("LightGBM複勝分類モデル学習中...")
            lgb_place = lgb.LGBMClassifier(**base_params, scale_pos_weight=place_weight, verbose=-1)
            lgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)])
            models['lgb_place'] = lgb_place

            # 複勝アンサンブル確率
            xgb_place_prob = xgb_place.predict_proba(X_val)[:, 1]
            lgb_place_prob = lgb_place.predict_proba(X_val)[:, 1]
            ensemble_place_prob = (xgb_place_prob + lgb_place_prob) / 2
            place_accuracy = ((ensemble_place_prob > 0.5) == y_place_val).mean()
            logger.info(f"複勝分類精度 (ensemble): {place_accuracy:.4f}")

            # ===== 評価指標の計算 =====
            from sklearn.metrics import roc_auc_score, brier_score_loss

            # AUC-ROC
            win_auc = roc_auc_score(y_win_val, ensemble_win_prob)
            place_auc = roc_auc_score(y_place_val, ensemble_place_prob)

            # Brier Score（勝利予測）
            win_brier = brier_score_loss(y_win_val, ensemble_win_prob)

            # Top-3カバー率（レースごとに勝ち馬が予測TOP3に入っているか）
            val_df = df.iloc[split_idx:].copy()
            val_df['pred_score'] = ensemble_pred
            val_df['win_prob'] = ensemble_win_prob

            top3_hits = 0
            total_races = 0
            for race_code, group in val_df.groupby('race_code'):
                if len(group) < 3:
                    continue
                # 勝ち馬を特定
                winner = group[group['target'] == 1]
                if len(winner) == 0:
                    continue
                # 予測スコアでソート（低いほど上位）
                sorted_group = group.sort_values('pred_score')
                top3_horses = sorted_group.head(3).index.tolist()
                # 勝ち馬がTOP3に含まれるか
                if winner.index[0] in top3_horses:
                    top3_hits += 1
                total_races += 1

            top3_coverage = top3_hits / total_races if total_races > 0 else 0

            # 評価結果をログ出力
            logger.info("=" * 50)
            logger.info("📊 モデル評価指標")
            logger.info("=" * 50)
            logger.info(f"勝利AUC:      {win_auc:.4f}  {'✅ 良好' if win_auc >= 0.70 else '⚠️ 要改善'} {'🌟 優秀' if win_auc >= 0.80 else ''}")
            logger.info(f"複勝AUC:      {place_auc:.4f}  {'✅ 良好' if place_auc >= 0.65 else '⚠️ 要改善'} {'🌟 優秀' if place_auc >= 0.75 else ''}")
            logger.info(f"Brier(勝利):  {win_brier:.4f}  {'✅ 良好' if win_brier <= 0.07 else '⚠️ 要改善'} {'🌟 優秀' if win_brier <= 0.05 else ''}")
            logger.info(f"Top-3カバー率: {top3_coverage*100:.1f}%  {'✅ 良好' if top3_coverage >= 0.55 else '⚠️ 要改善'} {'🌟 優秀' if top3_coverage >= 0.65 else ''}")
            logger.info("=" * 50)

            # ===== 4. キャリブレーション =====
            logger.info("キャリブレーション学習中...")
            win_calibrator = IsotonicRegression(out_of_bounds='clip')
            win_calibrator.fit(ensemble_win_prob, y_win_val)
            models['win_calibrator'] = win_calibrator

            place_calibrator = IsotonicRegression(out_of_bounds='clip')
            place_calibrator.fit(ensemble_place_prob, y_place_val)
            models['place_calibrator'] = place_calibrator

            calibrated_win = win_calibrator.predict(ensemble_win_prob)
            calibrated_place = place_calibrator.predict(ensemble_place_prob)
            logger.info(f"キャリブレーション後 - 勝率平均: {calibrated_win.mean():.4f}, 複勝率平均: {calibrated_place.mean():.4f}")

            # 一時保存
            temp_model_path = self.model_dir / "ensemble_model_new.pkl"
            model_data = {
                # 後方互換性
                'xgb_model': xgb_reg,
                'lgb_model': lgb_reg,
                # 新しいモデル群
                'models': models,
                'feature_names': feature_cols,
                'trained_at': datetime.now().isoformat(),
                'training_samples': len(df),
                'validation_rmse': float(rmse),
                'win_accuracy': float(win_accuracy),
                'place_accuracy': float(place_accuracy),
                # 評価指標
                'win_auc': float(win_auc),
                'place_auc': float(place_auc),
                'win_brier': float(win_brier),
                'top3_coverage': float(top3_coverage),
                'years': years,
                'version': 'v2_enhanced_ensemble'
            }
            joblib.dump(model_data, temp_model_path)

            return {
                'status': 'success',
                'model_path': str(temp_model_path),
                'rmse': float(rmse),
                'win_accuracy': float(win_accuracy),
                'place_accuracy': float(place_accuracy),
                'win_auc': float(win_auc),
                'place_auc': float(place_auc),
                'win_brier': float(win_brier),
                'top3_coverage': float(top3_coverage),
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

            training = result.get('training', {})

            # 評価指標を取得
            win_auc = training.get('win_auc', 0)
            place_auc = training.get('place_auc', 0)
            win_brier = training.get('win_brier', 0)
            top3_coverage = training.get('top3_coverage', 0)

            # 評価アイコン
            def get_icon(value, good, excellent, lower_is_better=False):
                if lower_is_better:
                    if value <= excellent:
                        return "🌟"
                    elif value <= good:
                        return "✅"
                    else:
                        return "⚠️"
                else:
                    if value >= excellent:
                        return "🌟"
                    elif value >= good:
                        return "✅"
                    else:
                        return "⚠️"

            if result.get('deployed'):
                lines = [
                    "🔄 **週次モデル再学習完了**",
                    "",
                    f"学習サンプル数: {training.get('samples', 0):,}",
                    "",
                    "📊 **評価指標:**",
                    f"```",
                    f"勝利AUC:       {win_auc:.4f} {get_icon(win_auc, 0.70, 0.80)}",
                    f"複勝AUC:       {place_auc:.4f} {get_icon(place_auc, 0.65, 0.75)}",
                    f"Brier(勝利):   {win_brier:.4f} {get_icon(win_brier, 0.07, 0.05, True)}",
                    f"Top-3カバー率: {top3_coverage*100:.1f}% {get_icon(top3_coverage, 0.55, 0.65)}",
                    f"```",
                    "",
                    "✅ 新モデルをデプロイしました"
                ]
            else:
                lines = [
                    "🔄 **週次モデル再学習完了**",
                    "",
                    f"学習サンプル数: {training.get('samples', 0):,}",
                    "",
                    "📊 **評価指標:**",
                    f"```",
                    f"勝利AUC:       {win_auc:.4f} {get_icon(win_auc, 0.70, 0.80)}",
                    f"複勝AUC:       {place_auc:.4f} {get_icon(place_auc, 0.65, 0.75)}",
                    f"Brier(勝利):   {win_brier:.4f} {get_icon(win_brier, 0.07, 0.05, True)}",
                    f"Top-3カバー率: {top3_coverage*100:.1f}% {get_icon(top3_coverage, 0.55, 0.65)}",
                    f"```",
                    "",
                    "⚠️ 改善なしのため現行モデルを維持"
                ]

            payload = {"content": "\n".join(lines)}
            requests.post(webhook_url, json=payload, timeout=10)

        except Exception as e:
            logger.error(f"通知エラー: {e}")

    def run_weekly_job(self, force_deploy: bool = False, notify: bool = True, years: int = 3):
        """週次ジョブを実行"""
        logger.info("=" * 50)
        logger.info(f"週次モデル再学習開始: {datetime.now()}")
        logger.info("=" * 50)

        result = {
            'date': date.today().isoformat(),
            'deployed': False
        }

        # 1. 新モデル学習
        training_result = self.train_new_model(years=years)
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
            elif force_deploy:
                # 比較失敗でも強制デプロイ
                self.deploy_new_model(new_model_path)
                result['deployed'] = True
                logger.info("強制デプロイしました（比較失敗）")
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
    parser.add_argument("--years", "-y", type=int, default=3, help="学習に使用する年数（デフォルト: 3年）")

    args = parser.parse_args()

    retrain = WeeklyRetrain()
    result = retrain.run_weekly_job(
        force_deploy=args.force,
        notify=not args.no_notify,
        years=args.years
    )

    print("\n=== 再学習結果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
