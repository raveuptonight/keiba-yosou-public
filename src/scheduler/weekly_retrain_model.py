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
import psycopg2
import psycopg2.extras

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

    def _calc_bin_stats(
        self, predicted: np.ndarray, actual: np.ndarray, calibrated: np.ndarray,
        n_bins: int = 20
    ) -> Dict:
        """キャリブレーション用のビン統計を計算"""
        from sklearn.metrics import brier_score_loss

        bin_stats = []
        bin_edges = np.linspace(0, 1, n_bins + 1)

        for i in range(n_bins):
            bin_start = bin_edges[i]
            bin_end = bin_edges[i + 1]

            mask = (predicted >= bin_start) & (predicted < bin_end)
            count = mask.sum()

            if count > 0:
                bin_stats.append({
                    'bin_start': float(bin_start),
                    'bin_end': float(bin_end),
                    'count': int(count),
                    'avg_predicted': float(predicted[mask].mean()),
                    'avg_actual': float(actual[mask].mean()),
                    'calibrated': float(calibrated[mask].mean())
                })

        brier_before = brier_score_loss(actual, predicted)
        brier_after = brier_score_loss(actual, calibrated)
        improvement = (brier_before - brier_after) / brier_before * 100 if brier_before > 0 else 0

        return {
            'total_samples': int(len(predicted)),
            'avg_predicted': float(predicted.mean()),
            'avg_actual': float(actual.mean()),
            'brier_before': float(brier_before),
            'brier_after': float(brier_after),
            'improvement': float(improvement),
            'bin_stats': bin_stats
        }

    def save_calibration_to_db(self, calibration_data: Dict, model_version: str) -> bool:
        """キャリブレーション統計をDBに保存"""
        try:
            db = get_db()
            conn = db.get_connection()
            cur = conn.cursor()

            # 既存のアクティブなキャリブレーションを非アクティブ化
            cur.execute("UPDATE model_calibration SET is_active = FALSE WHERE is_active = TRUE")

            # 新しいキャリブレーションを保存
            cur.execute('''
                INSERT INTO model_calibration (
                    model_version, calibration_data, created_at, is_active
                ) VALUES (%s, %s, %s, TRUE)
            ''', (
                model_version,
                psycopg2.extras.Json(calibration_data),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"キャリブレーション統計をDBに保存しました（version: {model_version}）")
            return True
        except Exception as e:
            logger.error(f"キャリブレーション保存エラー: {e}")
            return False

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
        import catboost as cb

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
            y_win = (y == 1).astype(int)      # 1着かどうか
            y_quinella = (y <= 2).astype(int)  # 2着以内かどうか（連対）
            y_place = (y <= 3).astype(int)    # 3着以内かどうか（複勝）

            # ===== 3分割（時系列順）=====
            # train (70%): モデル学習用
            # calib (15%): キャリブレーター学習用（データリーク防止）
            # test  (15%): 最終評価用
            n = len(df)
            train_end = int(n * 0.70)
            calib_end = int(n * 0.85)

            X_train = X[:train_end]
            X_calib = X[train_end:calib_end]  # キャリブレーション用
            X_test = X[calib_end:]             # 最終評価用
            X_val = X_calib  # early stoppingにはcalibデータを使用

            y_train = y[:train_end]
            y_calib = y[train_end:calib_end]
            y_test = y[calib_end:]
            y_val = y_calib

            y_win_train = y_win[:train_end]
            y_win_calib = y_win[train_end:calib_end]
            y_win_test = y_win[calib_end:]
            y_win_val = y_win_calib

            y_quinella_train = y_quinella[:train_end]
            y_quinella_calib = y_quinella[train_end:calib_end]
            y_quinella_test = y_quinella[calib_end:]
            y_quinella_val = y_quinella_calib

            y_place_train = y_place[:train_end]
            y_place_calib = y_place[train_end:calib_end]
            y_place_test = y_place[calib_end:]
            y_place_val = y_place_calib

            logger.info(f"訓練: {len(X_train)}, キャリブ: {len(X_calib)}, テスト: {len(X_test)}")

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

            # CatBoost用パラメータ
            cb_params = {
                'iterations': 500,
                'depth': 7,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'random_seed': 42,
                'verbose': False,
                'thread_count': -1
            }

            # アンサンブル重み (XGB:LGB:CB = 30:40:30)
            XGB_WEIGHT = 0.30
            LGB_WEIGHT = 0.40
            CB_WEIGHT = 0.30

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

            # CatBoost回帰
            logger.info("CatBoost回帰モデル学習中...")
            cb_reg = cb.CatBoostRegressor(**cb_params)
            cb_reg.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=50)
            models['cb_regressor'] = cb_reg

            # アンサンブル評価
            xgb_pred = xgb_reg.predict(X_val)
            lgb_pred = lgb_reg.predict(X_val)
            cb_pred = cb_reg.predict(X_val)
            ensemble_pred = xgb_pred * XGB_WEIGHT + lgb_pred * LGB_WEIGHT + cb_pred * CB_WEIGHT
            rmse = np.sqrt(np.mean((ensemble_pred - y_val) ** 2))
            logger.info(f"回帰RMSE (3モデルensemble): {rmse:.4f}")

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

            logger.info("CatBoost勝利分類モデル学習中...")
            cb_win = cb.CatBoostClassifier(**cb_params, scale_pos_weight=win_weight)
            cb_win.fit(X_train, y_win_train, eval_set=(X_val, y_win_val), early_stopping_rounds=50)
            models['cb_win'] = cb_win

            # 勝利アンサンブル確率
            xgb_win_prob = xgb_win.predict_proba(X_val)[:, 1]
            lgb_win_prob = lgb_win.predict_proba(X_val)[:, 1]
            cb_win_prob = cb_win.predict_proba(X_val)[:, 1]
            ensemble_win_prob = xgb_win_prob * XGB_WEIGHT + lgb_win_prob * LGB_WEIGHT + cb_win_prob * CB_WEIGHT
            win_accuracy = ((ensemble_win_prob > 0.5) == y_win_val).mean()
            logger.info(f"勝利分類精度 (3モデルensemble): {win_accuracy:.4f}")

            # ===== 3. 連対分類モデル =====
            quinella_weight = len(y_quinella_train[y_quinella_train == 0]) / max(len(y_quinella_train[y_quinella_train == 1]), 1)

            logger.info("XGBoost連対分類モデル学習中...")
            xgb_quinella = xgb.XGBClassifier(**base_params, scale_pos_weight=quinella_weight)
            xgb_quinella.fit(X_train, y_quinella_train, eval_set=[(X_val, y_quinella_val)], verbose=False)
            models['xgb_quinella'] = xgb_quinella

            logger.info("LightGBM連対分類モデル学習中...")
            lgb_quinella = lgb.LGBMClassifier(**base_params, scale_pos_weight=quinella_weight, verbose=-1)
            lgb_quinella.fit(X_train, y_quinella_train, eval_set=[(X_val, y_quinella_val)])
            models['lgb_quinella'] = lgb_quinella

            logger.info("CatBoost連対分類モデル学習中...")
            cb_quinella = cb.CatBoostClassifier(**cb_params, scale_pos_weight=quinella_weight)
            cb_quinella.fit(X_train, y_quinella_train, eval_set=(X_val, y_quinella_val), early_stopping_rounds=50)
            models['cb_quinella'] = cb_quinella

            # 連対アンサンブル確率
            xgb_quinella_prob = xgb_quinella.predict_proba(X_val)[:, 1]
            lgb_quinella_prob = lgb_quinella.predict_proba(X_val)[:, 1]
            cb_quinella_prob = cb_quinella.predict_proba(X_val)[:, 1]
            ensemble_quinella_prob = xgb_quinella_prob * XGB_WEIGHT + lgb_quinella_prob * LGB_WEIGHT + cb_quinella_prob * CB_WEIGHT
            quinella_accuracy = ((ensemble_quinella_prob > 0.5) == y_quinella_val).mean()
            logger.info(f"連対分類精度 (3モデルensemble): {quinella_accuracy:.4f}")

            # ===== 4. 複勝分類モデル =====
            place_weight = len(y_place_train[y_place_train == 0]) / max(len(y_place_train[y_place_train == 1]), 1)

            logger.info("XGBoost複勝分類モデル学習中...")
            xgb_place = xgb.XGBClassifier(**base_params, scale_pos_weight=place_weight)
            xgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)], verbose=False)
            models['xgb_place'] = xgb_place

            logger.info("LightGBM複勝分類モデル学習中...")
            lgb_place = lgb.LGBMClassifier(**base_params, scale_pos_weight=place_weight, verbose=-1)
            lgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)])
            models['lgb_place'] = lgb_place

            logger.info("CatBoost複勝分類モデル学習中...")
            cb_place = cb.CatBoostClassifier(**cb_params, scale_pos_weight=place_weight)
            cb_place.fit(X_train, y_place_train, eval_set=(X_val, y_place_val), early_stopping_rounds=50)
            models['cb_place'] = cb_place

            # 複勝アンサンブル確率
            xgb_place_prob = xgb_place.predict_proba(X_val)[:, 1]
            lgb_place_prob = lgb_place.predict_proba(X_val)[:, 1]
            cb_place_prob = cb_place.predict_proba(X_val)[:, 1]
            ensemble_place_prob = xgb_place_prob * XGB_WEIGHT + lgb_place_prob * LGB_WEIGHT + cb_place_prob * CB_WEIGHT
            place_accuracy = ((ensemble_place_prob > 0.5) == y_place_val).mean()
            logger.info(f"複勝分類精度 (3モデルensemble): {place_accuracy:.4f}")

            # ===== 5. キャリブレーション（calibデータで学習）=====
            logger.info("キャリブレーション学習中（calibデータ使用）...")

            # calibデータで予測（キャリブレーター学習用）
            xgb_win_prob_calib = xgb_win.predict_proba(X_calib)[:, 1]
            lgb_win_prob_calib = lgb_win.predict_proba(X_calib)[:, 1]
            cb_win_prob_calib = cb_win.predict_proba(X_calib)[:, 1]
            ensemble_win_prob_calib = xgb_win_prob_calib * XGB_WEIGHT + lgb_win_prob_calib * LGB_WEIGHT + cb_win_prob_calib * CB_WEIGHT

            xgb_quinella_prob_calib = xgb_quinella.predict_proba(X_calib)[:, 1]
            lgb_quinella_prob_calib = lgb_quinella.predict_proba(X_calib)[:, 1]
            cb_quinella_prob_calib = cb_quinella.predict_proba(X_calib)[:, 1]
            ensemble_quinella_prob_calib = xgb_quinella_prob_calib * XGB_WEIGHT + lgb_quinella_prob_calib * LGB_WEIGHT + cb_quinella_prob_calib * CB_WEIGHT

            xgb_place_prob_calib = xgb_place.predict_proba(X_calib)[:, 1]
            lgb_place_prob_calib = lgb_place.predict_proba(X_calib)[:, 1]
            cb_place_prob_calib = cb_place.predict_proba(X_calib)[:, 1]
            ensemble_place_prob_calib = xgb_place_prob_calib * XGB_WEIGHT + lgb_place_prob_calib * LGB_WEIGHT + cb_place_prob_calib * CB_WEIGHT

            # キャリブレーター学習
            win_calibrator = IsotonicRegression(out_of_bounds='clip')
            win_calibrator.fit(ensemble_win_prob_calib, y_win_calib)
            models['win_calibrator'] = win_calibrator

            quinella_calibrator = IsotonicRegression(out_of_bounds='clip')
            quinella_calibrator.fit(ensemble_quinella_prob_calib, y_quinella_calib)
            models['quinella_calibrator'] = quinella_calibrator

            place_calibrator = IsotonicRegression(out_of_bounds='clip')
            place_calibrator.fit(ensemble_place_prob_calib, y_place_calib)
            models['place_calibrator'] = place_calibrator

            # ===== 6. 最終評価（testデータ）=====
            logger.info("最終評価中（testデータ使用）...")
            from sklearn.metrics import roc_auc_score, brier_score_loss

            # testデータで予測（3モデルアンサンブル）
            xgb_pred_test = xgb_reg.predict(X_test)
            lgb_pred_test = lgb_reg.predict(X_test)
            cb_pred_test = cb_reg.predict(X_test)
            ensemble_pred_test = xgb_pred_test * XGB_WEIGHT + lgb_pred_test * LGB_WEIGHT + cb_pred_test * CB_WEIGHT

            xgb_win_prob_test = xgb_win.predict_proba(X_test)[:, 1]
            lgb_win_prob_test = lgb_win.predict_proba(X_test)[:, 1]
            cb_win_prob_test = cb_win.predict_proba(X_test)[:, 1]
            ensemble_win_prob_test = xgb_win_prob_test * XGB_WEIGHT + lgb_win_prob_test * LGB_WEIGHT + cb_win_prob_test * CB_WEIGHT

            xgb_quinella_prob_test = xgb_quinella.predict_proba(X_test)[:, 1]
            lgb_quinella_prob_test = lgb_quinella.predict_proba(X_test)[:, 1]
            cb_quinella_prob_test = cb_quinella.predict_proba(X_test)[:, 1]
            ensemble_quinella_prob_test = xgb_quinella_prob_test * XGB_WEIGHT + lgb_quinella_prob_test * LGB_WEIGHT + cb_quinella_prob_test * CB_WEIGHT

            xgb_place_prob_test = xgb_place.predict_proba(X_test)[:, 1]
            lgb_place_prob_test = lgb_place.predict_proba(X_test)[:, 1]
            cb_place_prob_test = cb_place.predict_proba(X_test)[:, 1]
            ensemble_place_prob_test = xgb_place_prob_test * XGB_WEIGHT + lgb_place_prob_test * LGB_WEIGHT + cb_place_prob_test * CB_WEIGHT

            # キャリブレーション適用
            calibrated_win_test = win_calibrator.predict(ensemble_win_prob_test)
            calibrated_quinella_test = quinella_calibrator.predict(ensemble_quinella_prob_test)
            calibrated_place_test = place_calibrator.predict(ensemble_place_prob_test)

            # AUC-ROC（キャリブレーション前後）
            win_auc_raw = roc_auc_score(y_win_test, ensemble_win_prob_test)
            win_auc = roc_auc_score(y_win_test, calibrated_win_test)
            quinella_auc_raw = roc_auc_score(y_quinella_test, ensemble_quinella_prob_test)
            quinella_auc = roc_auc_score(y_quinella_test, calibrated_quinella_test)
            place_auc_raw = roc_auc_score(y_place_test, ensemble_place_prob_test)
            place_auc = roc_auc_score(y_place_test, calibrated_place_test)

            # Brier Score（キャリブレーション前後）
            win_brier_raw = brier_score_loss(y_win_test, ensemble_win_prob_test)
            win_brier = brier_score_loss(y_win_test, calibrated_win_test)
            quinella_brier_raw = brier_score_loss(y_quinella_test, ensemble_quinella_prob_test)
            quinella_brier = brier_score_loss(y_quinella_test, calibrated_quinella_test)
            place_brier_raw = brier_score_loss(y_place_test, ensemble_place_prob_test)
            place_brier = brier_score_loss(y_place_test, calibrated_place_test)

            # Top-3カバー率（testデータで評価）
            top3_coverage = 0.0
            if 'race_code' in df.columns:
                test_df = df.iloc[calib_end:].copy()
                test_df['pred_score'] = ensemble_pred_test
                test_df['win_prob'] = calibrated_win_test

                top3_hits = 0
                total_races = 0
                for race_code, group in test_df.groupby('race_code'):
                    if len(group) < 3:
                        continue
                    winner = group[group['target'] == 1]
                    if len(winner) == 0:
                        continue
                    sorted_group = group.sort_values('pred_score')
                    top3_horses = sorted_group.head(3).index.tolist()
                    if winner.index[0] in top3_horses:
                        top3_hits += 1
                    total_races += 1

                top3_coverage = top3_hits / total_races if total_races > 0 else 0
            else:
                logger.warning("race_codeカラムがないためTop-3カバー率をスキップ")

            # 評価結果をログ出力
            logger.info("=" * 50)
            logger.info("📊 モデル評価指標（testデータ）")
            logger.info("=" * 50)
            logger.info(f"勝利AUC:      {win_auc:.4f} (raw: {win_auc_raw:.4f})  {'✅ 良好' if win_auc >= 0.70 else '⚠️ 要改善'}")
            logger.info(f"連対AUC:      {quinella_auc:.4f} (raw: {quinella_auc_raw:.4f})  {'✅ 良好' if quinella_auc >= 0.68 else '⚠️ 要改善'}")
            logger.info(f"複勝AUC:      {place_auc:.4f} (raw: {place_auc_raw:.4f})  {'✅ 良好' if place_auc >= 0.65 else '⚠️ 要改善'}")
            logger.info(f"勝利Brier:    {win_brier:.4f} (raw: {win_brier_raw:.4f}, 改善: {(win_brier_raw - win_brier) / win_brier_raw * 100:.1f}%)")
            logger.info(f"連対Brier:    {quinella_brier:.4f} (raw: {quinella_brier_raw:.4f}, 改善: {(quinella_brier_raw - quinella_brier) / quinella_brier_raw * 100:.1f}%)")
            logger.info(f"複勝Brier:    {place_brier:.4f} (raw: {place_brier_raw:.4f}, 改善: {(place_brier_raw - place_brier) / place_brier_raw * 100:.1f}%)")
            logger.info(f"Top-3カバー率: {top3_coverage*100:.1f}%  {'✅ 良好' if top3_coverage >= 0.55 else '⚠️ 要改善'}")
            logger.info(f"キャリブ後 - 勝率平均: {calibrated_win_test.mean():.4f}, 連対率平均: {calibrated_quinella_test.mean():.4f}, 複勝率平均: {calibrated_place_test.mean():.4f}")
            logger.info("=" * 50)

            # ===== 7. キャリブレーション統計をDBに保存 =====
            logger.info("キャリブレーション統計を計算中...")
            calibration_stats = {
                'created_at': datetime.now().isoformat(),
                'win_stats': self._calc_bin_stats(
                    ensemble_win_prob_test, y_win_test.values, calibrated_win_test
                ),
                'quinella_stats': self._calc_bin_stats(
                    ensemble_quinella_prob_test, y_quinella_test.values, calibrated_quinella_test
                ),
                'place_stats': self._calc_bin_stats(
                    ensemble_place_prob_test, y_place_test.values, calibrated_place_test
                )
            }

            model_version = f"v4_quinella_ensemble_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.save_calibration_to_db(calibration_stats, model_version)

            # 一時保存
            temp_model_path = self.model_dir / "ensemble_model_new.pkl"
            model_data = {
                # 後方互換性（旧形式）
                'xgb_model': xgb_reg,
                'lgb_model': lgb_reg,
                'cb_model': cb_reg,  # CatBoost追加
                # 新しいモデル群
                'models': models,
                'feature_names': feature_cols,
                'trained_at': datetime.now().isoformat(),
                'training_samples': len(df),
                'train_size': len(X_train),
                'calib_size': len(X_calib),
                'test_size': len(X_test),
                'validation_rmse': float(rmse),
                'win_accuracy': float(win_accuracy),
                'quinella_accuracy': float(quinella_accuracy),
                'place_accuracy': float(place_accuracy),
                # 評価指標（testデータ、キャリブレーション後）
                'win_auc': float(win_auc),
                'quinella_auc': float(quinella_auc),
                'place_auc': float(place_auc),
                'win_brier': float(win_brier),
                'quinella_brier': float(quinella_brier),
                'place_brier': float(place_brier),
                'top3_coverage': float(top3_coverage),
                'years': years,
                # アンサンブル重み
                'ensemble_weights': {
                    'xgb': XGB_WEIGHT,
                    'lgb': LGB_WEIGHT,
                    'cb': CB_WEIGHT
                },
                'version': 'v5_catboost_ensemble'  # CatBoost対応バージョン
            }
            joblib.dump(model_data, temp_model_path)

            return {
                'status': 'success',
                'model_path': str(temp_model_path),
                'rmse': float(rmse),
                'win_accuracy': float(win_accuracy),
                'quinella_accuracy': float(quinella_accuracy),
                'place_accuracy': float(place_accuracy),
                'win_auc': float(win_auc),
                'quinella_auc': float(quinella_auc),
                'place_auc': float(place_auc),
                'win_brier': float(win_brier),
                'quinella_brier': float(quinella_brier),
                'top3_coverage': float(top3_coverage),
                'samples': len(df)
            }

        except Exception as e:
            logger.error(f"学習エラー: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

        finally:
            conn.close()

    def compare_models(self, new_model_path: str, test_year: int = 2022) -> Dict:
        """
        新旧モデルを総合評価で比較

        評価指標:
        - AUC (勝利/連対/複勝)
        - Top-3カバー率
        - 回収率シミュレーション（単勝・複勝）
        - RMSE

        総合スコアで判断（AUC重視、回収率も考慮）

        注意: test_yearは学習データに含まれない年を指定すること
              デフォルト2022年（学習は2023年以降を使用）
        """
        from sklearn.metrics import roc_auc_score

        logger.info(f"モデル総合比較（テスト年: {test_year}）")
        logger.info(f"※学習データ外の年でバックテスト")

        # モデル読み込み
        try:
            old_model_data = joblib.load(self.current_model_path)
            new_model_data = joblib.load(new_model_path)
        except Exception as e:
            logger.error(f"モデル読み込みエラー: {e}")
            return {'status': 'error', 'message': str(e)}

        old_features = old_model_data['feature_names']
        new_features = new_model_data['feature_names']

        # 分類モデル取得
        old_models = old_model_data.get('models', {})
        new_models = new_model_data.get('models', {})

        # テストデータ取得（払戻データも含む）
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

            # 払戻データを取得
            payouts = self._get_payouts_for_year(conn, test_year)

            # 両モデルの評価を実行
            # 特徴量不一致チェック（新しい特徴量セットで旧モデルは評価できない場合がある）
            missing_old_features = set(old_features) - set(df.columns)
            if missing_old_features:
                logger.warning(f"⚠️ 旧モデルの特徴量が不足: {missing_old_features}")
                logger.info("特徴量構成が変更されたため、新モデルのみ評価します")
                old_eval = None
            else:
                old_eval = self._evaluate_model(df, old_model_data, old_features, payouts, "旧モデル")
            new_eval = self._evaluate_model(df, new_model_data, new_features, payouts, "新モデル")

            # 総合スコア計算
            new_score = self._calculate_composite_score(new_eval)

            logger.info("=" * 50)
            logger.info("📊 総合評価結果")
            logger.info("=" * 50)

            if old_eval is not None:
                old_score = self._calculate_composite_score(old_eval)
                improvement = new_score - old_score
                logger.info(f"旧モデル総合スコア: {old_score:.4f}")
                logger.info(f"新モデル総合スコア: {new_score:.4f}")
                logger.info(f"改善: {improvement:+.4f} ({'✅ 新モデル優位' if improvement > 0 else '❌ 旧モデル維持'})")
            else:
                # 特徴量変更時は旧モデル評価なし、新モデルを自動採用
                old_score = 0.0
                improvement = 1.0  # 強制的に新モデル採用
                logger.info("旧モデル: 評価スキップ（特徴量変更）")
                logger.info(f"新モデル総合スコア: {new_score:.4f}")
                logger.info("✅ 特徴量構成変更のため新モデルを採用")

            return {
                'status': 'success',
                'old_eval': old_eval,
                'new_eval': new_eval,
                'old_score': float(old_score),
                'new_score': float(new_score),
                'improvement': float(improvement),
                'test_samples': len(df),
                # 後方互換性のためRMSEも含める
                'old_rmse': old_eval.get('rmse', 0) if old_eval else 0,
                'new_rmse': new_eval.get('rmse', 0)
            }

        finally:
            conn.close()

    def _evaluate_model(self, df: pd.DataFrame, model_data: Dict, features: list,
                        payouts: Dict, model_name: str) -> Dict:
        """モデルの総合評価を実行"""
        from sklearn.metrics import roc_auc_score

        models = model_data.get('models', {})
        weights = model_data.get('ensemble_weights')  # CatBoost対応の重み
        X = df[features].fillna(0)

        # 回帰予測（着順）
        xgb_reg = models.get('xgb_regressor') or model_data.get('xgb_model')
        lgb_reg = models.get('lgb_regressor') or model_data.get('lgb_model')
        cb_reg = models.get('cb_regressor') or model_data.get('cb_model')

        if cb_reg is not None and weights is not None:
            # 3モデルアンサンブル
            reg_pred = (xgb_reg.predict(X) * weights['xgb'] +
                       lgb_reg.predict(X) * weights['lgb'] +
                       cb_reg.predict(X) * weights['cb'])
        else:
            # 2モデル平均（後方互換性）
            reg_pred = (xgb_reg.predict(X) + lgb_reg.predict(X)) / 2

        rmse = float(np.sqrt(np.mean((reg_pred - df['target']) ** 2)))

        # 分類予測（勝利/連対/複勝）
        eval_result = {'rmse': rmse}

        # CatBoost分類モデル
        cb_win = models.get('cb_win')
        cb_quinella = models.get('cb_quinella')
        cb_place = models.get('cb_place')

        # 勝利AUC
        if 'xgb_win' in models and 'lgb_win' in models:
            win_prob = self._get_ensemble_proba(models['xgb_win'], models['lgb_win'], X,
                                                 models.get('win_calibrator'),
                                                 cb_clf=cb_win, weights=weights)
            win_actual = (df['target'] == 1).astype(int)
            try:
                eval_result['win_auc'] = float(roc_auc_score(win_actual, win_prob))
            except:
                eval_result['win_auc'] = 0.5

        # 連対AUC
        if 'xgb_quinella' in models and 'lgb_quinella' in models:
            quinella_prob = self._get_ensemble_proba(models['xgb_quinella'], models['lgb_quinella'], X,
                                                      models.get('quinella_calibrator'),
                                                      cb_clf=cb_quinella, weights=weights)
            quinella_actual = (df['target'] <= 2).astype(int)
            try:
                eval_result['quinella_auc'] = float(roc_auc_score(quinella_actual, quinella_prob))
            except:
                eval_result['quinella_auc'] = 0.5

        # 複勝AUC
        if 'xgb_place' in models and 'lgb_place' in models:
            place_prob = self._get_ensemble_proba(models['xgb_place'], models['lgb_place'], X,
                                                   models.get('place_calibrator'),
                                                   cb_clf=cb_place, weights=weights)
            place_actual = (df['target'] <= 3).astype(int)
            try:
                eval_result['place_auc'] = float(roc_auc_score(place_actual, place_prob))
            except:
                eval_result['place_auc'] = 0.5

        # Top-3カバー率（レースごとに計算）
        df_eval = df.copy()
        df_eval['pred_rank'] = reg_pred

        if 'race_code' in df_eval.columns:
            top3_hits = 0
            total_races = 0

            for race_code, race_df in df_eval.groupby('race_code'):
                race_df_sorted = race_df.sort_values('pred_rank')
                top3_pred = race_df_sorted.head(3)['target'].values
                if any(t == 1 for t in top3_pred):
                    top3_hits += 1
                total_races += 1

            eval_result['top3_coverage'] = float(top3_hits / total_races) if total_races > 0 else 0

        # 回収率シミュレーション
        returns = self._simulate_returns(df_eval, reg_pred, payouts)
        eval_result.update(returns)

        # ログ出力
        logger.info(f"【{model_name}】")
        logger.info(f"  RMSE: {rmse:.4f}")
        logger.info(f"  勝利AUC: {eval_result.get('win_auc', 0):.4f}")
        logger.info(f"  連対AUC: {eval_result.get('quinella_auc', 0):.4f}")
        logger.info(f"  複勝AUC: {eval_result.get('place_auc', 0):.4f}")
        logger.info(f"  Top-3カバー率: {eval_result.get('top3_coverage', 0)*100:.1f}%")
        logger.info(f"  単勝回収率: {eval_result.get('tansho_return', 0)*100:.1f}%")
        logger.info(f"  複勝回収率: {eval_result.get('fukusho_return', 0)*100:.1f}%")

        return eval_result

    def _get_ensemble_proba(self, xgb_clf, lgb_clf, X, calibrator=None, cb_clf=None, weights=None) -> np.ndarray:
        """アンサンブル確率を取得（キャリブレーション適用、CatBoost対応）"""
        xgb_prob = xgb_clf.predict_proba(X)[:, 1]
        lgb_prob = lgb_clf.predict_proba(X)[:, 1]

        if cb_clf is not None and weights is not None:
            # 3モデルアンサンブル
            cb_prob = cb_clf.predict_proba(X)[:, 1]
            raw_prob = xgb_prob * weights['xgb'] + lgb_prob * weights['lgb'] + cb_prob * weights['cb']
        elif weights is not None:
            # 2モデル重み付きアンサンブル
            raw_prob = xgb_prob * weights.get('xgb', 0.5) + lgb_prob * weights.get('lgb', 0.5)
        else:
            # 2モデル単純平均（後方互換性）
            raw_prob = (xgb_prob + lgb_prob) / 2

        if calibrator is not None:
            try:
                return calibrator.predict(raw_prob)
            except:
                pass
        return raw_prob

    def _get_payouts_for_year(self, conn, year: int) -> Dict:
        """年間の払戻データを取得"""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                SELECT race_code,
                       tansho1_umaban, tansho1_haraimodoshikin,
                       fukusho1_umaban, fukusho1_haraimodoshikin,
                       fukusho2_umaban, fukusho2_haraimodoshikin,
                       fukusho3_umaban, fukusho3_haraimodoshikin
                FROM haraimodoshi
                WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
            ''', (year,))

            payouts = {}
            for row in cur.fetchall():
                race_code = row['race_code']

                # 単勝払戻金を安全に取得
                tansho_umaban = row['tansho1_umaban']
                tansho_payout = row['tansho1_haraimodoshikin']
                tansho_umaban_str = str(tansho_umaban).strip() if tansho_umaban else None
                try:
                    tansho_payout_int = int(str(tansho_payout).strip()) if tansho_payout and str(tansho_payout).strip() else 0
                except ValueError:
                    tansho_payout_int = 0

                payouts[race_code] = {
                    'tansho': {
                        'umaban': tansho_umaban_str,
                        'payout': tansho_payout_int
                    },
                    'fukusho': []
                }

                # 複勝払戻金を安全に取得
                for i in range(1, 4):
                    umaban = row.get(f'fukusho{i}_umaban')
                    payout = row.get(f'fukusho{i}_haraimodoshikin')
                    if umaban and str(umaban).strip():
                        try:
                            payout_int = int(str(payout).strip()) if payout and str(payout).strip() else 0
                        except ValueError:
                            payout_int = 0
                        if payout_int > 0:
                            payouts[race_code]['fukusho'].append({
                                'umaban': str(umaban).strip(),
                                'payout': payout_int
                            })
            cur.close()
            logger.info(f"払戻データ取得: {len(payouts)}レース")
            return payouts
        except Exception as e:
            logger.warning(f"払戻データ取得エラー: {e}")
            return {}

    def _simulate_returns(self, df: pd.DataFrame, predictions: np.ndarray, payouts: Dict) -> Dict:
        """回収率シミュレーション（各レース1位予想に100円賭け）"""
        df_sim = df.copy()
        df_sim['pred_rank'] = predictions

        tansho_bet = 0
        tansho_win = 0
        fukusho_bet = 0
        fukusho_win = 0

        # 馬番カラムの確認（umaban または horse_number）
        umaban_col = 'umaban' if 'umaban' in df_sim.columns else 'horse_number'
        if 'race_code' not in df_sim.columns or umaban_col not in df_sim.columns:
            logger.warning(f"回収率計算に必要なカラムがありません: race_code={('race_code' in df_sim.columns)}, {umaban_col}={(umaban_col in df_sim.columns)}")
            return {'tansho_return': 0, 'fukusho_return': 0}

        for race_code, race_df in df_sim.groupby('race_code'):
            race_df_sorted = race_df.sort_values('pred_rank')
            if len(race_df_sorted) == 0:
                continue

            top1 = race_df_sorted.iloc[0]
            pred_umaban = str(int(top1[umaban_col]))

            payout_data = payouts.get(race_code, {})

            # 単勝
            tansho_bet += 100
            tansho_info = payout_data.get('tansho', {})
            if tansho_info.get('umaban') == pred_umaban:
                tansho_win += tansho_info.get('payout', 0)

            # 複勝
            fukusho_bet += 100
            for fuku in payout_data.get('fukusho', []):
                if fuku.get('umaban') == pred_umaban:
                    fukusho_win += fuku.get('payout', 0)
                    break

        return {
            'tansho_return': float(tansho_win / tansho_bet) if tansho_bet > 0 else 0,
            'fukusho_return': float(fukusho_win / fukusho_bet) if fukusho_bet > 0 else 0,
            'tansho_bet': tansho_bet,
            'tansho_win': tansho_win,
            'fukusho_bet': fukusho_bet,
            'fukusho_win': fukusho_win
        }

    def _calculate_composite_score(self, eval_result: Dict) -> float:
        """
        総合スコアを計算

        重み付け:
        - 勝利AUC: 25%（分類精度の核心）
        - 連対AUC: 15%
        - 複勝AUC: 15%
        - Top-3カバー率: 20%（実用性）
        - 単勝回収率: 15%（収益性）
        - 複勝回収率: 10%
        """
        weights = {
            'win_auc': 0.25,
            'quinella_auc': 0.15,
            'place_auc': 0.15,
            'top3_coverage': 0.20,
            'tansho_return': 0.15,
            'fukusho_return': 0.10
        }

        score = 0
        for metric, weight in weights.items():
            value = eval_result.get(metric, 0)
            # AUCは0.5-1.0の範囲なので、0.5を引いて2倍してスケール
            if 'auc' in metric:
                value = (value - 0.5) * 2  # 0-1スケールに変換
            # 回収率は1.0が100%なのでそのまま
            score += value * weight

        return score

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
