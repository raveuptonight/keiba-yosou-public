"""
確率キャリブレーション用バックテスト

過去10年のデータでモデル予測を実行し、
予測確率と実際の結果を比較してキャリブレーションを計算
"""

import argparse
import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import joblib
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CalibrationBacktest:
    """キャリブレーション用バックテスト"""

    def __init__(self, model_path: str = "models/ensemble_model_latest.pkl"):
        self.model_path = Path(model_path)
        self.xgb_model = None
        self.lgb_model = None
        self.feature_names = None
        self._load_model()

        # 結果を格納
        self.predictions = []  # (predicted_prob, actual_result) のリスト

    def _load_model(self):
        """モデルを読み込み"""
        logger.info(f"モデル読み込み: {self.model_path}")
        model_data = joblib.load(self.model_path)

        if 'xgb_model' in model_data:
            self.xgb_model = model_data['xgb_model']
            self.lgb_model = model_data['lgb_model']
        elif 'models' in model_data:
            self.xgb_model = model_data['models'].get('xgboost')
            self.lgb_model = model_data['models'].get('lightgbm')
        else:
            raise ValueError("Invalid model format")

        self.feature_names = model_data.get('feature_names', [])
        logger.info(f"特徴量数: {len(self.feature_names)}")

    def run_year_backtest(self, year: int) -> Dict:
        """1年分のバックテストを実行"""
        logger.info(f"=== {year}年のバックテスト開始 ===")

        db = get_db()
        conn = db.get_connection()

        try:
            extractor = FastFeatureExtractor(conn)

            # 年間データを取得
            df = extractor.extract_year_data(year)

            if df is None or len(df) == 0:
                logger.warning(f"{year}年のデータなし")
                return {'year': year, 'races': 0, 'horses': 0}

            logger.info(f"  データ数: {len(df)}件")

            # レースごとにグループ化して予測
            race_codes = df['race_code'].unique()
            logger.info(f"  レース数: {len(race_codes)}")

            year_results = {
                'win': [],      # (予測確率, 1着フラグ)
                'quinella': [], # (予測確率, 2着以内フラグ)
                'place': [],    # (予測確率, 3着以内フラグ)
            }

            processed_races = 0
            for race_code in race_codes:
                race_df = df[df['race_code'] == race_code].copy()

                if len(race_df) < 2:
                    continue

                # 特徴量を準備
                available_features = [f for f in self.feature_names if f in race_df.columns]
                missing_features = [f for f in self.feature_names if f not in race_df.columns]

                for f in missing_features:
                    race_df[f] = 0

                X = race_df[self.feature_names].fillna(0)

                # アンサンブル予測
                try:
                    xgb_pred = self.xgb_model.predict(X)
                    lgb_pred = self.lgb_model.predict(X)
                    rank_scores = (xgb_pred + lgb_pred) / 2
                except Exception as e:
                    continue

                # スコアを確率に変換（softmax風）
                scores_exp = np.exp(-rank_scores)
                win_probs = scores_exp / scores_exp.sum()

                # 実際の着順を取得
                actual_positions = race_df['target'].values  # targetは着順

                # 各馬の予測と結果を記録
                for i, (prob, pos) in enumerate(zip(win_probs, actual_positions)):
                    try:
                        pos = int(pos)
                    except:
                        continue

                    # 単勝（1着かどうか）
                    year_results['win'].append((float(prob), 1 if pos == 1 else 0))

                    # 連対（2着以内かどうか）
                    # 連対確率は簡易的に単勝確率から推定
                    quinella_prob = min(1.0, prob * 2.5)
                    year_results['quinella'].append((quinella_prob, 1 if pos <= 2 else 0))

                    # 複勝（3着以内かどうか）
                    place_prob = min(1.0, prob * 4.0)
                    year_results['place'].append((place_prob, 1 if pos <= 3 else 0))

                processed_races += 1

                if processed_races % 500 == 0:
                    logger.info(f"    {processed_races}/{len(race_codes)} レース処理完了")

            # 結果を全体に追加
            for key in year_results:
                self.predictions.extend([(key, p, a) for p, a in year_results[key]])

            logger.info(f"  {year}年完了: {processed_races}レース, {len(year_results['win'])}頭")

            return {
                'year': year,
                'races': processed_races,
                'horses': len(year_results['win'])
            }

        finally:
            conn.close()

    def run_multi_year_backtest(self, start_year: int, end_year: int) -> List[Dict]:
        """複数年のバックテストを実行"""
        results = []

        for year in range(start_year, end_year + 1):
            result = self.run_year_backtest(year)
            results.append(result)

        return results

    def calculate_calibration(self) -> Dict:
        """キャリブレーションを計算"""
        logger.info("=== キャリブレーション計算 ===")

        calibration_data = {}

        for bet_type in ['win', 'quinella', 'place']:
            # データを抽出
            data = [(p, a) for t, p, a in self.predictions if t == bet_type]

            if not data:
                continue

            probs = np.array([d[0] for d in data])
            actuals = np.array([d[1] for d in data])

            logger.info(f"\n{bet_type}: {len(data)}件")
            logger.info(f"  予測確率平均: {probs.mean():.4f}")
            logger.info(f"  実際の的中率: {actuals.mean():.4f}")

            # Isotonic Regressionでキャリブレーション
            iso_reg = IsotonicRegression(out_of_bounds='clip')
            iso_reg.fit(probs, actuals)

            # キャリブレーション曲線を計算
            prob_true, prob_pred = calibration_curve(actuals, probs, n_bins=20, strategy='quantile')

            # Brier Scoreを計算
            brier_before = np.mean((probs - actuals) ** 2)
            calibrated_probs = iso_reg.predict(probs)
            brier_after = np.mean((calibrated_probs - actuals) ** 2)

            logger.info(f"  Brier Score (補正前): {brier_before:.4f}")
            logger.info(f"  Brier Score (補正後): {brier_after:.4f}")

            # ビン分割統計
            bins = np.linspace(0, 1, 21)
            bin_stats = []
            for i in range(len(bins) - 1):
                mask = (probs >= bins[i]) & (probs < bins[i+1])
                if mask.sum() > 0:
                    bin_stats.append({
                        'bin_start': float(bins[i]),
                        'bin_end': float(bins[i+1]),
                        'count': int(mask.sum()),
                        'avg_predicted': float(probs[mask].mean()),
                        'avg_actual': float(actuals[mask].mean()),
                        'calibrated': float(iso_reg.predict([probs[mask].mean()])[0])
                    })

            calibration_data[bet_type] = {
                'total_samples': len(data),
                'avg_predicted': float(probs.mean()),
                'avg_actual': float(actuals.mean()),
                'brier_before': float(brier_before),
                'brier_after': float(brier_after),
                'improvement': float((brier_before - brier_after) / brier_before * 100),
                'isotonic_regressor': iso_reg,
                'bin_stats': bin_stats,
                'calibration_curve': {
                    'prob_true': prob_true.tolist(),
                    'prob_pred': prob_pred.tolist()
                }
            }

        return calibration_data

    def save_calibration(self, calibration_data: Dict, output_path: str = "models/calibration.pkl"):
        """キャリブレーションデータを保存"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Isotonic Regressorのみを保存用に抽出
        save_data = {
            'created_at': datetime.now().isoformat(),
            'calibrators': {}
        }

        for bet_type, data in calibration_data.items():
            save_data['calibrators'][bet_type] = data['isotonic_regressor']

            # 統計情報も保存（レポート用）
            save_data[f'{bet_type}_stats'] = {
                'total_samples': data['total_samples'],
                'avg_predicted': data['avg_predicted'],
                'avg_actual': data['avg_actual'],
                'brier_before': data['brier_before'],
                'brier_after': data['brier_after'],
                'improvement': data['improvement'],
                'bin_stats': data['bin_stats']
            }

        joblib.dump(save_data, output_path)
        logger.info(f"キャリブレーションデータ保存: {output_path}")

        # JSONレポートも保存
        report_path = output_path.with_suffix('.json')
        report_data = {k: v for k, v in save_data.items() if k != 'calibrators'}
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        logger.info(f"レポート保存: {report_path}")

        return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="確率キャリブレーション用バックテスト")
    parser.add_argument("--start-year", "-s", type=int, default=2015, help="開始年")
    parser.add_argument("--end-year", "-e", type=int, default=2024, help="終了年")
    parser.add_argument("--model", "-m", default="models/ensemble_model_latest.pkl", help="モデルパス")
    parser.add_argument("--output", "-o", default="models/calibration.pkl", help="出力パス")

    args = parser.parse_args()

    print(f"""
================================================================================
確率キャリブレーション用バックテスト
================================================================================
期間: {args.start_year}年 〜 {args.end_year}年 ({args.end_year - args.start_year + 1}年分)
モデル: {args.model}
出力: {args.output}
================================================================================
""")

    # バックテスト実行
    backtest = CalibrationBacktest(model_path=args.model)

    start_time = datetime.now()
    results = backtest.run_multi_year_backtest(args.start_year, args.end_year)

    # 結果サマリー
    total_races = sum(r['races'] for r in results)
    total_horses = sum(r['horses'] for r in results)

    print(f"\n=== バックテスト完了 ===")
    print(f"処理時間: {datetime.now() - start_time}")
    print(f"総レース数: {total_races:,}")
    print(f"総頭数: {total_horses:,}")

    # キャリブレーション計算
    calibration_data = backtest.calculate_calibration()

    # 保存
    output_path = backtest.save_calibration(calibration_data, args.output)

    # 結果表示
    print("\n=== キャリブレーション結果 ===")
    for bet_type, data in calibration_data.items():
        print(f"\n【{bet_type}】")
        print(f"  サンプル数: {data['total_samples']:,}")
        print(f"  予測確率平均: {data['avg_predicted']:.4f}")
        print(f"  実際の的中率: {data['avg_actual']:.4f}")
        print(f"  Brier Score改善: {data['improvement']:.2f}%")

        print(f"\n  確率帯別の的中率:")
        for bin_stat in data['bin_stats'][:10]:  # 上位10件のみ表示
            print(f"    {bin_stat['bin_start']:.0%}-{bin_stat['bin_end']:.0%}: "
                  f"予測{bin_stat['avg_predicted']:.1%} → 実際{bin_stat['avg_actual']:.1%} "
                  f"({bin_stat['count']:,}件)")

    print(f"\n保存先: {output_path}")


if __name__ == "__main__":
    main()
