#!/usr/bin/env python3
"""
キャリブレーション再学習スクリプト

予想結果と実際の着順を比較し、Isotonic Regressionで
確率キャリブレーターを再学習する。
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import joblib
from sklearn.isotonic import IsotonicRegression

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import get_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 出力パス
OUTPUT_PATH = Path(__file__).parent.parent / "models" / "calibration.pkl"
BACKUP_PATH = Path(__file__).parent.parent / "models" / "calibration_backup.pkl"


def collect_prediction_results(days_back: int = 30) -> pd.DataFrame:
    """予想と実際の結果を収集"""
    logger.info(f"過去{days_back}日分のデータを収集...")

    cutoff_date = date.today() - timedelta(days=days_back)

    db = get_db()
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        # 予想データと結果を結合
        query = """
        SELECT
            p.race_id,
            p.race_date,
            p.prediction_result,
            u.umaban,
            u.kakutei_chakujun
        FROM predictions p
        JOIN umagoto_race_joho u ON p.race_id = u.race_code
        WHERE p.race_date >= %s
          AND p.race_date < CURRENT_DATE
          AND u.data_kubun IN ('6', '7')  -- 確定データ
          AND u.kakutei_chakujun IS NOT NULL
          AND u.kakutei_chakujun != ''
          AND u.kakutei_chakujun != '00'
        ORDER BY p.race_date, p.race_id, u.umaban
        """
        cur.execute(query, (cutoff_date,))
        rows = cur.fetchall()
    finally:
        conn.close()

    logger.info(f"取得レコード数: {len(rows)}")

    # データを整理
    results = []
    for race_id, race_date, pred_result, umaban, chakujun in rows:
        if not pred_result:
            continue

        try:
            # 着順を数値に変換
            chakujun_int = int(chakujun) if chakujun.isdigit() else 99
            if chakujun_int == 0:
                continue

            # 予想結果からこの馬の確率を取得
            ranked_horses = pred_result.get('ranked_horses', [])
            umaban_int = int(umaban) if umaban.isdigit() else 0

            for horse in ranked_horses:
                if horse.get('horse_number') == umaban_int:
                    results.append({
                        'race_id': race_id,
                        'race_date': race_date,
                        'umaban': umaban_int,
                        'chakujun': chakujun_int,
                        'win_prob': horse.get('win_probability', 0),
                        'quinella_prob': horse.get('quinella_probability', 0),
                        'place_prob': horse.get('place_probability', 0),
                        'is_win': 1 if chakujun_int == 1 else 0,
                        'is_quinella': 1 if chakujun_int <= 2 else 0,
                        'is_place': 1 if chakujun_int <= 3 else 0,
                    })
                    break
        except (ValueError, TypeError, KeyError) as e:
            continue

    df = pd.DataFrame(results)
    logger.info(f"整理後レコード数: {len(df)}")
    return df


def train_calibrators(df: pd.DataFrame) -> Dict:
    """キャリブレーターを学習"""
    logger.info("キャリブレーター学習開始...")

    calibrators = {}
    stats = {}

    # 単勝キャリブレーター
    if len(df) > 0 and 'win_prob' in df.columns:
        X_win = df['win_prob'].values
        y_win = df['is_win'].values

        iso_win = IsotonicRegression(out_of_bounds='clip')
        iso_win.fit(X_win, y_win)
        calibrators['win'] = iso_win

        # 統計情報
        y_pred = iso_win.predict(X_win)
        brier_before = np.mean((X_win - y_win) ** 2)
        brier_after = np.mean((y_pred - y_win) ** 2)

        stats['win'] = {
            'total_samples': len(df),
            'avg_predicted': float(X_win.mean()),
            'avg_actual': float(y_win.mean()),
            'brier_before': float(brier_before),
            'brier_after': float(brier_after),
            'improvement': float((brier_before - brier_after) / brier_before * 100) if brier_before > 0 else 0,
            'bin_stats': compute_bin_stats(X_win, y_win, y_pred),
        }
        logger.info(f"単勝: Brier改善 {stats['win']['improvement']:.2f}%")

    # 連対キャリブレーター
    if len(df) > 0 and 'quinella_prob' in df.columns:
        X_qui = df['quinella_prob'].values
        y_qui = df['is_quinella'].values

        iso_qui = IsotonicRegression(out_of_bounds='clip')
        iso_qui.fit(X_qui, y_qui)
        calibrators['quinella'] = iso_qui

        y_pred = iso_qui.predict(X_qui)
        brier_before = np.mean((X_qui - y_qui) ** 2)
        brier_after = np.mean((y_pred - y_qui) ** 2)

        stats['quinella'] = {
            'total_samples': len(df),
            'avg_predicted': float(X_qui.mean()),
            'avg_actual': float(y_qui.mean()),
            'brier_before': float(brier_before),
            'brier_after': float(brier_after),
            'improvement': float((brier_before - brier_after) / brier_before * 100) if brier_before > 0 else 0,
            'bin_stats': compute_bin_stats(X_qui, y_qui, y_pred),
        }
        logger.info(f"連対: Brier改善 {stats['quinella']['improvement']:.2f}%")

    # 複勝キャリブレーター
    if len(df) > 0 and 'place_prob' in df.columns:
        X_place = df['place_prob'].values
        y_place = df['is_place'].values

        iso_place = IsotonicRegression(out_of_bounds='clip')
        iso_place.fit(X_place, y_place)
        calibrators['place'] = iso_place

        y_pred = iso_place.predict(X_place)
        brier_before = np.mean((X_place - y_place) ** 2)
        brier_after = np.mean((y_pred - y_place) ** 2)

        stats['place'] = {
            'total_samples': len(df),
            'avg_predicted': float(X_place.mean()),
            'avg_actual': float(y_place.mean()),
            'brier_before': float(brier_before),
            'brier_after': float(brier_after),
            'improvement': float((brier_before - brier_after) / brier_before * 100) if brier_before > 0 else 0,
            'bin_stats': compute_bin_stats(X_place, y_place, y_pred),
        }
        logger.info(f"複勝: Brier改善 {stats['place']['improvement']:.2f}%")

    return calibrators, stats


def compute_bin_stats(X: np.ndarray, y: np.ndarray, y_calibrated: np.ndarray, n_bins: int = 10) -> List[Dict]:
    """確率帯別の統計を計算"""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_stats = []

    for i in range(n_bins):
        mask = (X >= bins[i]) & (X < bins[i+1])
        if mask.sum() > 0:
            bin_stats.append({
                'bin_start': float(bins[i]),
                'bin_end': float(bins[i+1]),
                'count': int(mask.sum()),
                'avg_predicted': float(X[mask].mean()),
                'avg_actual': float(y[mask].mean()),
                'calibrated': float(y_calibrated[mask].mean()),
            })

    return bin_stats


def save_calibrators(calibrators: Dict, stats: Dict):
    """キャリブレーターを保存"""
    # バックアップ
    if OUTPUT_PATH.exists():
        import shutil
        shutil.copy(OUTPUT_PATH, BACKUP_PATH)
        logger.info(f"バックアップ作成: {BACKUP_PATH}")

    # 保存
    data = {
        'created_at': datetime.now().isoformat(),
        'calibrators': calibrators,
        'win_stats': stats.get('win', {}),
        'quinella_stats': stats.get('quinella', {}),
        'place_stats': stats.get('place', {}),
    }

    joblib.dump(data, OUTPUT_PATH)
    logger.info(f"キャリブレーター保存: {OUTPUT_PATH}")


def print_calibration_table(calibrators: Dict):
    """キャリブレーション変換テーブルを表示"""
    print("\n" + "=" * 60)
    print("【キャリブレーション変換テーブル】")
    print("=" * 60)

    test_probs = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

    print(f"\n{'予測値':>8} | {'単勝':>8} | {'連対':>8} | {'複勝':>8}")
    print("-" * 45)

    for p in test_probs:
        win_cal = calibrators['win'].predict([[p]])[0] if 'win' in calibrators else p
        qui_cal = calibrators['quinella'].predict([[p]])[0] if 'quinella' in calibrators else p
        place_cal = calibrators['place'].predict([[p]])[0] if 'place' in calibrators else p

        print(f"{p*100:>7.0f}% | {win_cal*100:>7.1f}% | {qui_cal*100:>7.1f}% | {place_cal*100:>7.1f}%")


def main():
    """メイン処理"""
    import argparse
    parser = argparse.ArgumentParser(description='キャリブレーション再学習')
    parser.add_argument('--days', type=int, default=30, help='過去何日分のデータを使用するか')
    parser.add_argument('--dry-run', action='store_true', help='保存せずに結果のみ表示')
    args = parser.parse_args()

    print("=" * 60)
    print("キャリブレーション再学習")
    print("=" * 60)

    # データ収集
    df = collect_prediction_results(days_back=args.days)

    if len(df) == 0:
        logger.error("データが見つかりません")
        return 1

    # サマリー表示
    print(f"\n【データサマリー】")
    print(f"  レース数: {df['race_id'].nunique()}")
    print(f"  馬数: {len(df)}")
    print(f"  期間: {df['race_date'].min()} 〜 {df['race_date'].max()}")
    print(f"  単勝的中率: {df['is_win'].mean()*100:.1f}%")
    print(f"  連対率: {df['is_quinella'].mean()*100:.1f}%")
    print(f"  複勝率: {df['is_place'].mean()*100:.1f}%")

    # キャリブレーター学習
    calibrators, stats = train_calibrators(df)

    # 変換テーブル表示
    print_calibration_table(calibrators)

    # 保存
    if not args.dry_run:
        save_calibrators(calibrators, stats)
        print(f"\n保存完了: {OUTPUT_PATH}")
    else:
        print("\n[DRY RUN] 保存はスキップされました")

    return 0


if __name__ == '__main__':
    sys.exit(main())
