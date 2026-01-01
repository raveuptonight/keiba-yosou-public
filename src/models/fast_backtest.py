"""
高速バックテストスクリプト

バッチ化されたDBクエリで高速に処理
"""

import argparse
import logging
from datetime import datetime
from typing import Dict, List, Any
import numpy as np
import pandas as pd
import joblib

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


def run_backtest(
    model_path: str,
    year: int = 2025,
    max_races: int = 500
) -> Dict[str, Any]:
    """
    高速バックテスト実行
    """
    print(f"[1/4] バックテスト開始: {year}年, 最大{max_races}レース", flush=True)

    # モデル読み込み
    model_data = joblib.load(model_path)
    model = model_data['model']
    feature_names = model_data['feature_names']
    print(f"[2/4] モデル読み込み完了: {len(feature_names)}特徴量", flush=True)

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        # 高速特徴量抽出
        extractor = FastFeatureExtractor(conn)
        df = extractor.extract_year_data(year, max_races)

        if len(df) == 0:
            return {"error": "データがありません"}

        print(f"[3/4] データ取得完了: {len(df)}サンプル", flush=True)

        # レースごとにグループ化して評価
        # race_codeを取得するためにDBから再取得
        cur = conn.cursor()
        cur.execute('''
            SELECT race_code, umaban, kakutei_chakujun, tansho_odds
            FROM umagoto_race_joho
            WHERE kaisai_nen = %s AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
            ORDER BY race_code, umaban::int
        ''', (str(year),))
        rows = cur.fetchall()
        cur.close()

        # レースごとの実績データを構築
        race_data = {}
        for row in rows:
            rc, umaban, chakujun, odds = row
            if rc not in race_data:
                race_data[rc] = {}
            try:
                race_data[rc][int(umaban)] = {
                    'rank': int(chakujun),
                    'odds': float(odds) / 10 if odds else 10.0
                }
            except:
                pass

        # 特徴量から予測
        X = df[feature_names].fillna(0)
        predictions = model.predict(X)
        df['pred_score'] = predictions

        # umabanでマッチング
        results = {
            'win': 0, 'place': 0, 'top3': 0,
            'total': 0, 'win_return': 0
        }

        # レースコードを推定（データに含まれていないので、順序で対応）
        race_codes = list(race_data.keys())[:max_races]

        # 各レースについて評価
        processed_races = set()
        sample_idx = 0
        total_races = len(race_codes)

        for i, race_code in enumerate(race_codes):
            if i % 100 == 0:
                print(f"進捗: {i}/{total_races} レース処理中...", flush=True)
            if race_code in processed_races:
                continue

            race_actual = race_data.get(race_code, {})
            if not race_actual:
                continue

            num_horses = len(race_actual)

            # このレースのサンプルを取得
            if sample_idx + num_horses > len(df):
                break

            race_df = df.iloc[sample_idx:sample_idx + num_horses].copy()
            sample_idx += num_horses

            if len(race_df) < 2:
                continue

            # 予測順位でソート
            race_df = race_df.sort_values('pred_score')
            pred_1st_umaban = int(race_df.iloc[0]['umaban'])

            if pred_1st_umaban not in race_actual:
                continue

            pred_1st_actual = race_actual[pred_1st_umaban]['rank']
            pred_1st_odds = race_actual[pred_1st_umaban]['odds']

            results['total'] += 1

            if pred_1st_actual == 1:
                results['win'] += 1
                results['win_return'] += pred_1st_odds * 1000

            if pred_1st_actual <= 3:
                results['place'] += 1

            # TOP3に1着が含まれるか
            top3_umabans = race_df.iloc[:3]['umaban'].astype(int).tolist()
            for uma in top3_umabans:
                if uma in race_actual and race_actual[uma]['rank'] == 1:
                    results['top3'] += 1
                    break

            processed_races.add(race_code)

        print(f"[4/4] 評価完了: {results['total']}レース", flush=True)

        # 結果計算
        total = results['total']
        if total == 0:
            return {"error": "評価可能なレースがありません"}

        return {
            "year": year,
            "total_races": total,
            "accuracy": {
                "win_rate": f"{results['win']/total*100:.1f}%",
                "win_count": f"{results['win']}/{total}",
                "place_rate": f"{results['place']/total*100:.1f}%",
                "place_count": f"{results['place']}/{total}",
                "top3_rate": f"{results['top3']/total*100:.1f}%",
                "top3_count": f"{results['top3']}/{total}",
            },
            "roi": {
                "win_roi": f"{results['win_return']/(total*1000)*100:.1f}%",
                "win_return": f"¥{results['win_return']:,.0f}",
                "bet_total": f"¥{total*1000:,}"
            }
        }

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="高速バックテスト")
    parser.add_argument("--model", "-m", default="/app/models/xgboost_model_latest.pkl")
    parser.add_argument("--year", "-y", type=int, default=2025)
    parser.add_argument("--max-races", "-n", type=int, default=500)

    args = parser.parse_args()

    print("=" * 50)
    print("高速バックテスト")
    print("=" * 50)
    print(f"モデル: {args.model}")
    print(f"対象年: {args.year}年")
    print(f"最大レース数: {args.max_races}")
    print("=" * 50)

    results = run_backtest(args.model, args.year, args.max_races)

    print()
    if "error" in results:
        print(f"エラー: {results['error']}")
        return

    print("【結果】")
    print(f"対象: {results['total_races']}レース")
    print()
    print("■ 的中率")
    acc = results['accuracy']
    print(f"  単勝: {acc['win_rate']} ({acc['win_count']})")
    print(f"  複勝: {acc['place_rate']} ({acc['place_count']})")
    print(f"  TOP3: {acc['top3_rate']} ({acc['top3_count']})")
    print()
    print("■ 回収率")
    roi = results['roi']
    print(f"  単勝: {roi['win_roi']} ({roi['win_return']} / {roi['bet_total']})")
    print("=" * 50)


if __name__ == "__main__":
    main()
