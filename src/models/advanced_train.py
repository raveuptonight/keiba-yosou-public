"""
改良版学習スクリプト

改善点:
1. 血統特徴量（父馬・母父の産駒成績）
2. 時系列クロスバリデーション
3. XGBoost + LightGBM アンサンブル
4. LambdaRank（ランキング学習）オプション
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb
import lightgbm as lgb
import joblib

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AdvancedFeatureExtractor(FastFeatureExtractor):
    """血統特徴量を追加した拡張版"""

    def __init__(self, conn):
        super().__init__(conn)
        self._sire_stats_cache = {}
        self._broodmare_sire_stats_cache = {}
        self._bloodline_cache = {}

    def _get_bloodline_info(self, kettonums: List[str]) -> Dict[str, Dict]:
        """血統情報を取得（父馬・母父）"""
        if not kettonums:
            return {}

        # キャッシュチェック
        uncached = [k for k in kettonums if k not in self._bloodline_cache]

        if uncached:
            placeholders = ','.join(['%s'] * len(uncached))
            cur = self.conn.cursor()
            cur.execute(f'''
                SELECT
                    ketto_toroku_bango,
                    ketto1_hanshoku_toroku_bango,
                    ketto1_bamei,
                    ketto5_hanshoku_toroku_bango,
                    ketto5_bamei
                FROM kyosoba_master2
                WHERE ketto_toroku_bango IN ({placeholders})
                  AND data_kubun = '1'
            ''', uncached)

            for row in cur.fetchall():
                self._bloodline_cache[row[0]] = {
                    'sire_id': row[1],
                    'sire_name': row[2],
                    'broodmare_sire_id': row[3],
                    'broodmare_sire_name': row[4]
                }
            cur.close()

        return {k: self._bloodline_cache.get(k, {}) for k in kettonums}

    def _get_sire_stats(self, year: int) -> Dict[str, Dict]:
        """父馬別産駒成績を取得（指定年より前のデータのみ）"""
        cache_key = year
        if cache_key in self._sire_stats_cache:
            return self._sire_stats_cache[cache_key]

        cur = self.conn.cursor()
        cur.execute('''
            WITH sire_results AS (
                SELECT
                    k.ketto1_hanshoku_toroku_bango as sire_id,
                    r.track_code,
                    CASE
                        WHEN u.kakutei_chakujun = '1' THEN 1 ELSE 0
                    END as is_win,
                    CASE
                        WHEN u.kakutei_chakujun IN ('1','2','3') THEN 1 ELSE 0
                    END as is_place
                FROM umagoto_race_joho u
                JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
                JOIN race_shosai r ON u.race_code = r.race_code
                WHERE u.data_kubun = '7'
                  AND u.kaisai_nen::int < %s
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND k.ketto1_hanshoku_toroku_bango IS NOT NULL
                  AND k.ketto1_hanshoku_toroku_bango != ''
            )
            SELECT
                sire_id,
                COUNT(*) as runs,
                SUM(is_win) as wins,
                SUM(is_place) as places,
                SUM(CASE WHEN track_code LIKE '1%%' THEN 1 ELSE 0 END) as turf_runs,
                SUM(CASE WHEN track_code LIKE '1%%' AND is_win = 1 THEN 1 ELSE 0 END) as turf_wins,
                SUM(CASE WHEN track_code LIKE '2%%' THEN 1 ELSE 0 END) as dirt_runs,
                SUM(CASE WHEN track_code LIKE '2%%' AND is_win = 1 THEN 1 ELSE 0 END) as dirt_wins
            FROM sire_results
            GROUP BY sire_id
            HAVING COUNT(*) >= 10
        ''', (year,))

        stats = {}
        for row in cur.fetchall():
            sire_id = row[0]
            runs = row[1] or 1
            stats[sire_id] = {
                'runs': runs,
                'win_rate': (row[2] or 0) / runs,
                'place_rate': (row[3] or 0) / runs,
                'turf_win_rate': (row[5] or 0) / max(row[4] or 1, 1),
                'dirt_win_rate': (row[7] or 0) / max(row[6] or 1, 1),
            }
        cur.close()

        self._sire_stats_cache[cache_key] = stats
        return stats

    def _get_broodmare_sire_stats(self, year: int) -> Dict[str, Dict]:
        """母父別産駒成績を取得"""
        cache_key = year
        if cache_key in self._broodmare_sire_stats_cache:
            return self._broodmare_sire_stats_cache[cache_key]

        cur = self.conn.cursor()
        cur.execute('''
            WITH bms_results AS (
                SELECT
                    k.ketto5_hanshoku_toroku_bango as bms_id,
                    r.track_code,
                    CASE
                        WHEN u.kakutei_chakujun = '1' THEN 1 ELSE 0
                    END as is_win,
                    CASE
                        WHEN u.kakutei_chakujun IN ('1','2','3') THEN 1 ELSE 0
                    END as is_place
                FROM umagoto_race_joho u
                JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
                JOIN race_shosai r ON u.race_code = r.race_code
                WHERE u.data_kubun = '7'
                  AND u.kaisai_nen::int < %s
                  AND u.kakutei_chakujun ~ '^[0-9]+$'
                  AND k.ketto5_hanshoku_toroku_bango IS NOT NULL
                  AND k.ketto5_hanshoku_toroku_bango != ''
            )
            SELECT
                bms_id,
                COUNT(*) as runs,
                SUM(is_win) as wins,
                SUM(is_place) as places,
                SUM(CASE WHEN track_code LIKE '1%%' THEN 1 ELSE 0 END) as turf_runs,
                SUM(CASE WHEN track_code LIKE '1%%' AND is_win = 1 THEN 1 ELSE 0 END) as turf_wins,
                SUM(CASE WHEN track_code LIKE '2%%' THEN 1 ELSE 0 END) as dirt_runs,
                SUM(CASE WHEN track_code LIKE '2%%' AND is_win = 1 THEN 1 ELSE 0 END) as dirt_wins
            FROM bms_results
            GROUP BY bms_id
            HAVING COUNT(*) >= 10
        ''', (year,))

        stats = {}
        for row in cur.fetchall():
            bms_id = row[0]
            runs = row[1] or 1
            stats[bms_id] = {
                'runs': runs,
                'win_rate': (row[2] or 0) / runs,
                'place_rate': (row[3] or 0) / runs,
                'turf_win_rate': (row[5] or 0) / max(row[4] or 1, 1),
                'dirt_win_rate': (row[7] or 0) / max(row[6] or 1, 1),
            }
        cur.close()

        self._broodmare_sire_stats_cache[cache_key] = stats
        return stats

    def extract_year_data_advanced(self, year: int, max_races: int = 5000) -> pd.DataFrame:
        """血統特徴量を含む1年分のデータ取得"""
        # 基本特徴量を取得
        df = self.extract_year_data(year, max_races)
        if len(df) == 0:
            return df

        logger.info(f"  血統特徴量を追加中...")

        # 血統情報を取得
        kettonums = df['kettonum'].unique().tolist() if 'kettonum' in df.columns else []

        # kettonumがない場合は基本DFを返す
        if not kettonums:
            # デフォルト血統特徴量を追加
            df['sire_win_rate'] = 0.1
            df['sire_place_rate'] = 0.3
            df['sire_turf_win_rate'] = 0.1
            df['sire_dirt_win_rate'] = 0.1
            df['bms_win_rate'] = 0.1
            df['bms_place_rate'] = 0.3
            df['bms_turf_win_rate'] = 0.1
            df['bms_dirt_win_rate'] = 0.1
            return df

        bloodline = self._get_bloodline_info(kettonums)
        sire_stats = self._get_sire_stats(year)
        bms_stats = self._get_broodmare_sire_stats(year)

        logger.info(f"  父馬成績: {len(sire_stats)}頭, 母父成績: {len(bms_stats)}頭")

        # 血統特徴量を追加
        sire_win_rates = []
        sire_place_rates = []
        sire_turf_win_rates = []
        sire_dirt_win_rates = []
        bms_win_rates = []
        bms_place_rates = []
        bms_turf_win_rates = []
        bms_dirt_win_rates = []

        for _, row in df.iterrows():
            kettonum = row.get('kettonum', '')
            blood = bloodline.get(kettonum, {})

            # 父馬成績
            sire_id = blood.get('sire_id', '')
            s_stats = sire_stats.get(sire_id, {})
            sire_win_rates.append(s_stats.get('win_rate', 0.1))
            sire_place_rates.append(s_stats.get('place_rate', 0.3))
            sire_turf_win_rates.append(s_stats.get('turf_win_rate', 0.1))
            sire_dirt_win_rates.append(s_stats.get('dirt_win_rate', 0.1))

            # 母父成績
            bms_id = blood.get('broodmare_sire_id', '')
            b_stats = bms_stats.get(bms_id, {})
            bms_win_rates.append(b_stats.get('win_rate', 0.1))
            bms_place_rates.append(b_stats.get('place_rate', 0.3))
            bms_turf_win_rates.append(b_stats.get('turf_win_rate', 0.1))
            bms_dirt_win_rates.append(b_stats.get('dirt_win_rate', 0.1))

        df['sire_win_rate'] = sire_win_rates
        df['sire_place_rate'] = sire_place_rates
        df['sire_turf_win_rate'] = sire_turf_win_rates
        df['sire_dirt_win_rate'] = sire_dirt_win_rates
        df['bms_win_rate'] = bms_win_rates
        df['bms_place_rate'] = bms_place_rates
        df['bms_turf_win_rate'] = bms_turf_win_rates
        df['bms_dirt_win_rate'] = bms_dirt_win_rates

        return df


def train_with_timeseries_cv(
    df: pd.DataFrame,
    n_splits: int = 5,
    use_gpu: bool = True
) -> Tuple[Any, Dict]:
    """時系列クロスバリデーションで学習"""

    feature_cols = [c for c in df.columns if c not in ['target', 'kettonum', 'race_code']]
    X = df[feature_cols].fillna(0)
    y = df['target']

    # 時系列CV
    tscv = TimeSeriesSplit(n_splits=n_splits)

    xgb_scores = []
    lgb_scores = []

    logger.info(f"時系列CV開始: {n_splits}分割")

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # XGBoost
        xgb_params = {
            'n_estimators': 500,
            'max_depth': 6,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 0.1,
            'reg_lambda': 1.0,
            'random_state': 42,
            'n_jobs': -1,
            'early_stopping_rounds': 30,
        }
        if use_gpu:
            xgb_params['tree_method'] = 'hist'
            xgb_params['device'] = 'cuda'

        xgb_model = xgb.XGBRegressor(objective='reg:squarederror', **xgb_params)
        xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        xgb_pred = xgb_model.predict(X_val)
        xgb_rmse = np.sqrt(np.mean((xgb_pred - y_val) ** 2))
        xgb_scores.append(xgb_rmse)

        # LightGBM (CPUのみ - OpenCL環境依存のため)
        lgb_params = {
            'n_estimators': 500,
            'max_depth': 6,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 0.1,
            'reg_lambda': 1.0,
            'random_state': 42,
            'n_jobs': -1,
            'verbose': -1,
        }

        lgb_model = lgb.LGBMRegressor(objective='regression', **lgb_params)
        lgb_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(30, verbose=False)]
        )
        lgb_pred = lgb_model.predict(X_val)
        lgb_rmse = np.sqrt(np.mean((lgb_pred - y_val) ** 2))
        lgb_scores.append(lgb_rmse)

        logger.info(f"  Fold {fold+1}: XGB={xgb_rmse:.4f}, LGB={lgb_rmse:.4f}")

    logger.info(f"CV平均: XGB={np.mean(xgb_scores):.4f}, LGB={np.mean(lgb_scores):.4f}")

    return {
        'xgb_cv_scores': xgb_scores,
        'lgb_cv_scores': lgb_scores,
        'xgb_cv_mean': np.mean(xgb_scores),
        'lgb_cv_mean': np.mean(lgb_scores),
    }


def train_ensemble(
    df: pd.DataFrame,
    use_gpu: bool = True,
    use_lambdarank: bool = False
) -> Tuple[Dict, Dict]:
    """XGBoost + LightGBM アンサンブルモデルを学習"""

    feature_cols = [c for c in df.columns if c not in ['target', 'kettonum', 'race_code']]
    X = df[feature_cols].fillna(0)
    y = df['target']

    # 時系列分割（最後の10%を検証用）
    split_idx = int(len(X) * 0.9)
    X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"学習データ: {len(X_train)}, 検証データ: {len(X_val)}")

    models = {}

    # XGBoost
    logger.info("XGBoost学習中...")
    xgb_params = {
        'n_estimators': 800,
        'max_depth': 7,
        'learning_rate': 0.03,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'random_state': 42,
        'n_jobs': -1,
        'early_stopping_rounds': 50,
    }
    if use_gpu:
        xgb_params['tree_method'] = 'hist'
        xgb_params['device'] = 'cuda'

    xgb_model = xgb.XGBRegressor(objective='reg:squarederror', **xgb_params)
    xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=100)
    models['xgboost'] = xgb_model

    # LightGBM
    logger.info("LightGBM学習中...")
    lgb_params = {
        'n_estimators': 800,
        'max_depth': 7,
        'learning_rate': 0.03,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'random_state': 42,
        'n_jobs': -1,
        'verbose': -1,
    }

    lgb_model = lgb.LGBMRegressor(objective='regression', **lgb_params)
    lgb_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)]
    )
    models['lightgbm'] = lgb_model

    # LambdaRank（オプション）
    if use_lambdarank:
        logger.info("LambdaRank学習中...")
        # レースごとのグループを作成
        if 'race_code' in df.columns:
            train_df = df.iloc[:split_idx]
            val_df = df.iloc[split_idx:]

            # グループサイズを計算
            train_groups = train_df.groupby('race_code').size().values
            val_groups = val_df.groupby('race_code').size().values

            ranker = lgb.LGBMRanker(
                objective='lambdarank',
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )

            # ランキング用のラベル（着順を反転：1着が最高スコア）
            y_train_rank = (20 - y_train.clip(1, 18)).values
            y_val_rank = (20 - y_val.clip(1, 18)).values

            ranker.fit(
                X_train.values, y_train_rank,
                group=train_groups,
                eval_set=[(X_val.values, y_val_rank)],
                eval_group=[val_groups],
                callbacks=[lgb.early_stopping(30, verbose=False)]
            )
            models['lambdarank'] = ranker

    # 検証
    xgb_pred = models['xgboost'].predict(X_val)
    lgb_pred = models['lightgbm'].predict(X_val)
    ensemble_pred = (xgb_pred + lgb_pred) / 2

    xgb_rmse = np.sqrt(np.mean((xgb_pred - y_val) ** 2))
    lgb_rmse = np.sqrt(np.mean((lgb_pred - y_val) ** 2))
    ensemble_rmse = np.sqrt(np.mean((ensemble_pred - y_val) ** 2))

    logger.info(f"検証RMSE: XGB={xgb_rmse:.4f}, LGB={lgb_rmse:.4f}, Ensemble={ensemble_rmse:.4f}")

    # 特徴量重要度（XGBoost）
    importance = dict(sorted(
        zip(feature_cols, models['xgboost'].feature_importances_),
        key=lambda x: x[1],
        reverse=True
    ))

    results = {
        'feature_names': feature_cols,
        'xgb_rmse': xgb_rmse,
        'lgb_rmse': lgb_rmse,
        'ensemble_rmse': ensemble_rmse,
        'importance': importance,
        'train_size': len(X_train),
        'val_size': len(X_val),
    }

    return models, results


def save_ensemble_model(models: Dict, results: Dict, output_dir: str) -> str:
    """アンサンブルモデルを保存"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = Path(output_dir) / f"ensemble_model_{timestamp}.pkl"
    latest_path = Path(output_dir) / "ensemble_model_latest.pkl"

    model_data = {
        'models': models,
        'feature_names': results['feature_names'],
        'feature_importance': results['importance'],
        'trained_at': timestamp,
        'xgb_rmse': results['xgb_rmse'],
        'lgb_rmse': results['lgb_rmse'],
        'ensemble_rmse': results['ensemble_rmse'],
    }

    joblib.dump(model_data, model_path)
    logger.info(f"モデル保存: {model_path}")

    # 最新版リンク更新
    if latest_path.exists() or latest_path.is_symlink():
        latest_path.unlink()
    latest_path.symlink_to(model_path.name)

    return str(model_path)


def main():
    parser = argparse.ArgumentParser(description="改良版学習スクリプト")
    parser.add_argument("--start-year", type=int, default=2015, help="開始年")
    parser.add_argument("--end-year", type=int, default=2025, help="終了年（学習用）")
    parser.add_argument("--max-races", type=int, default=5000, help="年間最大レース数")
    parser.add_argument("--output", default="models", help="出力ディレクトリ")
    parser.add_argument("--no-gpu", action="store_true", help="GPUを使用しない")
    parser.add_argument("--cv-only", action="store_true", help="CVのみ実行")
    parser.add_argument("--lambdarank", action="store_true", help="LambdaRankも学習")
    parser.add_argument("--cv-splits", type=int, default=5, help="CV分割数")

    args = parser.parse_args()

    print("=" * 60)
    print("改良版学習スクリプト")
    print("=" * 60)
    print(f"期間: {args.start_year}年 ~ {args.end_year}年")
    print(f"年間最大レース数: {args.max_races}")
    print(f"GPU: {'無効' if args.no_gpu else '有効'}")
    print(f"LambdaRank: {'有効' if args.lambdarank else '無効'}")
    print("=" * 60)

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        extractor = AdvancedFeatureExtractor(conn)

        # 年ごとにデータ収集
        all_data = []
        for year in range(args.start_year, args.end_year + 1):
            df = extractor.extract_year_data_advanced(year, args.max_races)
            if len(df) > 0:
                all_data.append(df)

        if not all_data:
            logger.error("データがありません")
            return

        # 結合
        full_df = pd.concat(all_data, ignore_index=True)
        logger.info(f"全データ: {len(full_df)}サンプル, {len(full_df.columns)}特徴量")

        # 時系列CV
        cv_results = train_with_timeseries_cv(
            full_df,
            n_splits=args.cv_splits,
            use_gpu=not args.no_gpu
        )

        print("\n" + "=" * 60)
        print("クロスバリデーション結果")
        print("=" * 60)
        print(f"XGBoost CV平均RMSE: {cv_results['xgb_cv_mean']:.4f}")
        print(f"LightGBM CV平均RMSE: {cv_results['lgb_cv_mean']:.4f}")

        if args.cv_only:
            return

        # アンサンブル学習
        models, results = train_ensemble(
            full_df,
            use_gpu=not args.no_gpu,
            use_lambdarank=args.lambdarank
        )

        # 保存
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_ensemble_model(models, results, str(output_dir))

        # 結果表示
        print("\n" + "=" * 60)
        print("学習完了")
        print("=" * 60)
        print(f"サンプル数: {len(full_df)}")
        print(f"特徴量数: {len(results['feature_names'])}")
        print(f"検証RMSE:")
        print(f"  XGBoost:  {results['xgb_rmse']:.4f}")
        print(f"  LightGBM: {results['lgb_rmse']:.4f}")
        print(f"  Ensemble: {results['ensemble_rmse']:.4f}")
        print(f"モデル: {model_path}")

        print("\n特徴量重要度 TOP20:")
        for i, (name, imp) in enumerate(list(results['importance'].items())[:20], 1):
            print(f"  {i:2d}. {name}: {imp*100:.2f}%")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
