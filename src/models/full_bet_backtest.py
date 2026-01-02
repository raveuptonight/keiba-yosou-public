"""
全馬券種別バックテスト

2015-2025年の全レースで各馬券種の的中率・回収率を計算
"""

import argparse
import logging
from typing import Dict, List, Any, Tuple
import numpy as np
import joblib
from collections import defaultdict

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


def get_payoffs_for_year(conn, year: int) -> Dict[str, Dict]:
    """指定年の全レース払戻データを取得"""
    cur = conn.cursor()

    # haraimodoshiテーブルから取得
    cur.execute('''
        SELECT
            race_code,
            -- 単勝
            tansho1_umaban, tansho1_haraimodoshikin,
            tansho2_umaban, tansho2_haraimodoshikin,
            tansho3_umaban, tansho3_haraimodoshikin,
            -- 複勝
            fukusho1_umaban, fukusho1_haraimodoshikin,
            fukusho2_umaban, fukusho2_haraimodoshikin,
            fukusho3_umaban, fukusho3_haraimodoshikin,
            fukusho4_umaban, fukusho4_haraimodoshikin,
            fukusho5_umaban, fukusho5_haraimodoshikin,
            -- 馬連
            umaren1_kumiban1, umaren1_kumiban2, umaren1_haraimodoshikin,
            umaren2_kumiban1, umaren2_kumiban2, umaren2_haraimodoshikin,
            umaren3_kumiban1, umaren3_kumiban2, umaren3_haraimodoshikin,
            -- ワイド
            wide1_kumiban1, wide1_kumiban2, wide1_haraimodoshikin,
            wide2_kumiban1, wide2_kumiban2, wide2_haraimodoshikin,
            wide3_kumiban1, wide3_kumiban2, wide3_haraimodoshikin,
            -- 馬単
            umatan1_kumiban1, umatan1_kumiban2, umatan1_haraimodoshikin,
            umatan2_kumiban1, umatan2_kumiban2, umatan2_haraimodoshikin,
            umatan3_kumiban1, umatan3_kumiban2, umatan3_haraimodoshikin,
            -- 三連複
            sanrenpuku1_kumiban1, sanrenpuku1_kumiban2, sanrenpuku1_kumiban3, sanrenpuku1_haraimodoshikin,
            sanrenpuku2_kumiban1, sanrenpuku2_kumiban2, sanrenpuku2_kumiban3, sanrenpuku2_haraimodoshikin,
            sanrenpuku3_kumiban1, sanrenpuku3_kumiban2, sanrenpuku3_kumiban3, sanrenpuku3_haraimodoshikin,
            -- 三連単
            sanrentan1_kumiban1, sanrentan1_kumiban2, sanrentan1_kumiban3, sanrentan1_haraimodoshikin,
            sanrentan2_kumiban1, sanrentan2_kumiban2, sanrentan2_kumiban3, sanrentan2_haraimodoshikin,
            sanrentan3_kumiban1, sanrentan3_kumiban2, sanrentan3_kumiban3, sanrentan3_haraimodoshikin
        FROM haraimodoshi
        WHERE kaisai_nen = %s
          AND data_kubun = '2'
    ''', (str(year),))

    payoffs = {}
    for row in cur.fetchall():
        race_code = row[0]
        payoffs[race_code] = {
            'tansho': [],
            'fukusho': [],
            'umaren': [],
            'wide': [],
            'umatan': [],
            'sanrenpuku': [],
            'sanrentan': []
        }

        idx = 1

        def parse_int(val):
            """文字列から整数を抽出（0埋め対応）"""
            if val is None:
                return None
            try:
                return int(str(val).strip())
            except:
                return None

        # 単勝 (3組)
        for _ in range(3):
            uma, kin = row[idx], row[idx + 1]
            idx += 2
            uma_int = parse_int(uma)
            kin_int = parse_int(kin)
            if uma_int and kin_int:
                payoffs[race_code]['tansho'].append({
                    'umaban': uma_int,
                    'amount': kin_int  # 払戻金額（円）
                })

        # 複勝 (5組)
        for _ in range(5):
            uma, kin = row[idx], row[idx + 1]
            idx += 2
            uma_int = parse_int(uma)
            kin_int = parse_int(kin)
            if uma_int and kin_int:
                payoffs[race_code]['fukusho'].append({
                    'umaban': uma_int,
                    'amount': kin_int
                })

        # 馬連 (3組)
        for _ in range(3):
            k1, k2, kin = row[idx], row[idx + 1], row[idx + 2]
            idx += 3
            k1_int = parse_int(k1)
            k2_int = parse_int(k2)
            kin_int = parse_int(kin)
            if k1_int and k2_int and kin_int:
                payoffs[race_code]['umaren'].append({
                    'uma1': k1_int,
                    'uma2': k2_int,
                    'amount': kin_int
                })

        # ワイド (3組)
        for _ in range(3):
            k1, k2, kin = row[idx], row[idx + 1], row[idx + 2]
            idx += 3
            k1_int = parse_int(k1)
            k2_int = parse_int(k2)
            kin_int = parse_int(kin)
            if k1_int and k2_int and kin_int:
                payoffs[race_code]['wide'].append({
                    'uma1': k1_int,
                    'uma2': k2_int,
                    'amount': kin_int
                })

        # 馬単 (3組)
        for _ in range(3):
            k1, k2, kin = row[idx], row[idx + 1], row[idx + 2]
            idx += 3
            k1_int = parse_int(k1)
            k2_int = parse_int(k2)
            kin_int = parse_int(kin)
            if k1_int and k2_int and kin_int:
                payoffs[race_code]['umatan'].append({
                    'uma1': k1_int,
                    'uma2': k2_int,
                    'amount': kin_int
                })

        # 三連複 (3組)
        for _ in range(3):
            k1, k2, k3, kin = row[idx], row[idx + 1], row[idx + 2], row[idx + 3]
            idx += 4
            k1_int = parse_int(k1)
            k2_int = parse_int(k2)
            k3_int = parse_int(k3)
            kin_int = parse_int(kin)
            if k1_int and k2_int and k3_int and kin_int:
                payoffs[race_code]['sanrenpuku'].append({
                    'uma1': k1_int,
                    'uma2': k2_int,
                    'uma3': k3_int,
                    'amount': kin_int
                })

        # 三連単 (3組)
        for _ in range(3):
            k1, k2, k3, kin = row[idx], row[idx + 1], row[idx + 2], row[idx + 3]
            idx += 4
            k1_int = parse_int(k1)
            k2_int = parse_int(k2)
            k3_int = parse_int(k3)
            kin_int = parse_int(kin)
            if k1_int and k2_int and k3_int and kin_int:
                payoffs[race_code]['sanrentan'].append({
                    'uma1': k1_int,
                    'uma2': k2_int,
                    'uma3': k3_int,
                    'amount': kin_int
                })

    cur.close()
    return payoffs


def get_race_results_for_year(conn, year: int) -> Dict[str, List[Tuple[int, int]]]:
    """指定年の全レース着順データを取得 (馬番, 着順)"""
    cur = conn.cursor()

    cur.execute('''
        SELECT race_code, umaban, kakutei_chakujun
        FROM umagoto_race_joho
        WHERE kaisai_nen = %s
          AND data_kubun = '7'
          AND kakutei_chakujun ~ '^[0-9]+$'
        ORDER BY race_code, kakutei_chakujun::int
    ''', (str(year),))

    results = {}
    for row in cur.fetchall():
        race_code, umaban, chakujun = row
        if race_code not in results:
            results[race_code] = []
        try:
            results[race_code].append((int(umaban), int(chakujun)))
        except:
            pass

    cur.close()
    return results


def run_full_backtest(
    model_path: str,
    start_year: int = 2015,
    end_year: int = 2025,
    bet_unit: int = 100
) -> Dict[str, Any]:
    """
    全馬券種別バックテスト実行
    """
    print(f"=" * 60)
    print(f"全馬券種別バックテスト: {start_year}-{end_year}年")
    print(f"賭け金単位: {bet_unit}円")
    print(f"=" * 60)

    # モデル読み込み
    model_data = joblib.load(model_path)
    model = model_data['model']
    feature_names = model_data['feature_names']
    print(f"モデル読み込み完了: {len(feature_names)}特徴量")

    # DB接続
    db = get_db()
    conn = db.get_connection()

    # 結果集計用
    stats = {
        'tansho': {'hits': 0, 'bets': 0, 'return': 0},      # 単勝
        'fukusho': {'hits': 0, 'bets': 0, 'return': 0},     # 複勝
        'umaren': {'hits': 0, 'bets': 0, 'return': 0},      # 馬連
        'wide': {'hits': 0, 'bets': 0, 'return': 0},        # ワイド
        'umatan': {'hits': 0, 'bets': 0, 'return': 0},      # 馬単
        'sanrenpuku': {'hits': 0, 'bets': 0, 'return': 0},  # 三連複
        'sanrentan': {'hits': 0, 'bets': 0, 'return': 0},   # 三連単
    }

    total_races = 0

    try:
        extractor = FastFeatureExtractor(conn)

        for year in range(start_year, end_year + 1):
            print(f"\n[{year}年] 処理中...", flush=True)

            # 特徴量データ取得
            df = extractor.extract_year_data(year, max_races=10000)
            if len(df) == 0:
                print(f"  {year}年: データなし")
                continue

            # 払戻・着順データ取得
            payoffs = get_payoffs_for_year(conn, year)
            race_results = get_race_results_for_year(conn, year)

            # レースコード一覧
            cur = conn.cursor()
            cur.execute('''
                SELECT DISTINCT race_code
                FROM umagoto_race_joho
                WHERE kaisai_nen = %s AND data_kubun = '7'
                  AND kakutei_chakujun ~ '^[0-9]+$'
                ORDER BY race_code
            ''', (str(year),))
            race_codes = [r[0] for r in cur.fetchall()]
            cur.close()

            # 予測実行
            X = df[feature_names].fillna(0)
            df['pred_score'] = model.predict(X)

            year_races = 0
            sample_idx = 0

            for race_code in race_codes:
                results_list = race_results.get(race_code, [])
                if len(results_list) < 3:
                    continue

                num_horses = len(results_list)

                if sample_idx + num_horses > len(df):
                    break

                race_df = df.iloc[sample_idx:sample_idx + num_horses].copy()
                sample_idx += num_horses

                if len(race_df) < 3:
                    continue

                # 予測スコアでソート（小さい=速い）
                race_df = race_df.sort_values('pred_score')
                pred_top3 = race_df.iloc[:3]['umaban'].astype(int).tolist()

                # 実際の着順
                actual = {uma: rank for uma, rank in results_list}
                actual_1st = [uma for uma, rank in results_list if rank == 1]
                actual_top2 = sorted([uma for uma, rank in results_list if rank <= 2])
                actual_top3 = sorted([uma for uma, rank in results_list if rank <= 3])

                if not actual_1st:
                    continue

                race_payoffs = payoffs.get(race_code, {})
                year_races += 1

                # === 単勝 ===
                pred_1st = pred_top3[0]
                stats['tansho']['bets'] += 1
                if pred_1st in actual_1st:
                    stats['tansho']['hits'] += 1
                    for p in race_payoffs.get('tansho', []):
                        if p['umaban'] == pred_1st:
                            stats['tansho']['return'] += p['amount']
                            break

                # === 複勝 (1着予想馬) ===
                stats['fukusho']['bets'] += 1
                if pred_1st in actual_top3:
                    stats['fukusho']['hits'] += 1
                    for p in race_payoffs.get('fukusho', []):
                        if p['umaban'] == pred_1st:
                            stats['fukusho']['return'] += p['amount']
                            break

                # === 馬連 (TOP2予想) ===
                pred_pair = sorted(pred_top3[:2])
                stats['umaren']['bets'] += 1
                if len(actual_top2) >= 2 and pred_pair == actual_top2[:2]:
                    stats['umaren']['hits'] += 1
                    for p in race_payoffs.get('umaren', []):
                        if sorted([p['uma1'], p['uma2']]) == pred_pair:
                            stats['umaren']['return'] += p['amount']
                            break

                # === ワイド (TOP2予想) ===
                stats['wide']['bets'] += 1
                # ワイドは3着以内の2頭の組み合わせ
                if pred_top3[0] in actual_top3 and pred_top3[1] in actual_top3:
                    stats['wide']['hits'] += 1
                    for p in race_payoffs.get('wide', []):
                        if sorted([p['uma1'], p['uma2']]) == pred_pair:
                            stats['wide']['return'] += p['amount']
                            break

                # === 馬単 (1-2着順予想) ===
                pred_1st_uma = pred_top3[0]
                pred_2nd_uma = pred_top3[1]
                stats['umatan']['bets'] += 1
                if len(actual_top2) >= 2:
                    act_1st = actual_1st[0]
                    act_2nd_list = [uma for uma, rank in results_list if rank == 2]
                    if act_2nd_list and pred_1st_uma == act_1st and pred_2nd_uma == act_2nd_list[0]:
                        stats['umatan']['hits'] += 1
                        for p in race_payoffs.get('umatan', []):
                            if p['uma1'] == pred_1st_uma and p['uma2'] == pred_2nd_uma:
                                stats['umatan']['return'] += p['amount']
                                break

                # === 三連複 (TOP3予想、順不同) ===
                pred_trio = sorted(pred_top3)
                stats['sanrenpuku']['bets'] += 1
                if len(actual_top3) >= 3 and pred_trio == actual_top3[:3]:
                    stats['sanrenpuku']['hits'] += 1
                    for p in race_payoffs.get('sanrenpuku', []):
                        if sorted([p['uma1'], p['uma2'], p['uma3']]) == pred_trio:
                            stats['sanrenpuku']['return'] += p['amount']
                            break

                # === 三連単 (1-2-3着順予想) ===
                stats['sanrentan']['bets'] += 1
                if len(actual_top3) >= 3:
                    act_1st = actual_1st[0]
                    act_2nd_list = [uma for uma, rank in results_list if rank == 2]
                    act_3rd_list = [uma for uma, rank in results_list if rank == 3]
                    if (act_2nd_list and act_3rd_list and
                        pred_top3[0] == act_1st and
                        pred_top3[1] == act_2nd_list[0] and
                        pred_top3[2] == act_3rd_list[0]):
                        stats['sanrentan']['hits'] += 1
                        for p in race_payoffs.get('sanrentan', []):
                            if (p['uma1'] == pred_top3[0] and
                                p['uma2'] == pred_top3[1] and
                                p['uma3'] == pred_top3[2]):
                                stats['sanrentan']['return'] += p['amount']
                                break

            total_races += year_races
            print(f"  {year}年: {year_races}レース処理完了")

    finally:
        conn.close()

    # 結果表示
    print(f"\n{'=' * 70}")
    print(f"【バックテスト結果】{start_year}-{end_year}年 計{total_races:,}レース")
    print(f"{'=' * 70}")
    print(f"{'馬券種':^10} {'的中数':>12} {'的中率':>10} {'投資額':>14} {'回収額':>14} {'回収率':>10}")
    print(f"{'-' * 70}")

    results = {}
    for bet_type, name in [
        ('tansho', '単勝'),
        ('fukusho', '複勝'),
        ('umaren', '馬連'),
        ('wide', 'ワイド'),
        ('umatan', '馬単'),
        ('sanrenpuku', '三連複'),
        ('sanrentan', '三連単'),
    ]:
        s = stats[bet_type]
        bets = s['bets']
        hits = s['hits']
        ret = s['return']

        if bets > 0:
            hit_rate = hits / bets * 100
            investment = bets * bet_unit
            roi = ret / investment * 100 if investment > 0 else 0
        else:
            hit_rate = 0
            investment = 0
            roi = 0

        print(f"{name:^10} {hits:>8,}/{bets:<8,} {hit_rate:>8.2f}% {investment:>12,}円 {ret:>12,}円 {roi:>8.1f}%")

        results[bet_type] = {
            'name': name,
            'hits': hits,
            'bets': bets,
            'hit_rate': hit_rate,
            'investment': investment,
            'return': ret,
            'roi': roi
        }

    print(f"{'=' * 70}")

    return results


def main():
    parser = argparse.ArgumentParser(description="全馬券種別バックテスト")
    parser.add_argument("--model", "-m", default="models/xgboost_model_latest.pkl")
    parser.add_argument("--start-year", "-s", type=int, default=2015)
    parser.add_argument("--end-year", "-e", type=int, default=2025)
    parser.add_argument("--bet-unit", "-u", type=int, default=100)

    args = parser.parse_args()

    run_full_backtest(
        args.model,
        args.start_year,
        args.end_year,
        args.bet_unit
    )


if __name__ == "__main__":
    main()
