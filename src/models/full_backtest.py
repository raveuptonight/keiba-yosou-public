"""
全馬券式別バックテストスクリプト

単勝、複勝、馬連、ワイド、馬単、三連複、三連単の
的中率・回収率を計算
"""

import argparse
import logging
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
import joblib

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


def run_full_backtest(
    model_path: str,
    year: int = 2025,
    max_races: int = 500
) -> Dict[str, Any]:
    """
    全馬券式別バックテスト実行
    """
    print(f"[1/5] バックテスト開始: {year}年, 最大{max_races}レース", flush=True)

    # モデル読み込み
    model_data = joblib.load(model_path)
    model = model_data['model']
    feature_names = model_data['feature_names']
    print(f"[2/5] モデル読み込み完了: {len(feature_names)}特徴量", flush=True)

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        # 特徴量抽出
        extractor = FastFeatureExtractor(conn)
        df = extractor.extract_year_data(year, max_races)

        if len(df) == 0:
            return {"error": "データがありません"}

        print(f"[3/5] 特徴量生成完了: {len(df)}サンプル", flush=True)

        # 払い戻しデータを取得
        payouts = _get_payouts(conn, year, max_races)
        print(f"[4/5] 払い戻しデータ取得: {len(payouts)}レース", flush=True)

        # レースごとの出走馬データを取得
        race_entries = _get_race_entries(conn, year, max_races)

        # 予測実行
        X = df[feature_names].fillna(0)
        predictions = model.predict(X)
        df['pred_score'] = predictions

        # レースごとに評価
        results = evaluate_all_bets(df, race_entries, payouts)

        print(f"[5/5] 評価完了: {results['total_races']}レース", flush=True)

        return results

    finally:
        conn.close()


def _get_payouts(conn, year: int, max_races: int) -> Dict[str, Dict]:
    """払い戻しデータを取得"""
    sql = """
        SELECT
            race_code,
            tansho1_umaban, tansho1_haraimodoshikin,
            fukusho1_umaban, fukusho1_haraimodoshikin,
            fukusho2_umaban, fukusho2_haraimodoshikin,
            fukusho3_umaban, fukusho3_haraimodoshikin,
            umaren1_kumiban1, umaren1_kumiban2, umaren1_haraimodoshikin,
            wide1_kumiban1, wide1_kumiban2, wide1_haraimodoshikin,
            wide2_kumiban1, wide2_kumiban2, wide2_haraimodoshikin,
            wide3_kumiban1, wide3_kumiban2, wide3_haraimodoshikin,
            umatan1_kumiban1, umatan1_kumiban2, umatan1_haraimodoshikin,
            sanrenpuku1_kumiban1, sanrenpuku1_kumiban2, sanrenpuku1_kumiban3, sanrenpuku1_haraimodoshikin,
            sanrentan1_kumiban1, sanrentan1_kumiban2, sanrentan1_kumiban3, sanrentan1_haraimodoshikin
        FROM haraimodoshi
        WHERE kaisai_nen = %s
        ORDER BY race_code
        LIMIT %s
    """
    cur = conn.cursor()
    cur.execute(sql, (str(year), max_races))
    rows = cur.fetchall()
    cur.close()

    payouts = {}
    for row in rows:
        race_code = row[0]
        payouts[race_code] = {
            'tansho': {
                'umaban': _safe_int(row[1]),
                'payout': _safe_int(row[2])
            },
            'fukusho': [
                {'umaban': _safe_int(row[3]), 'payout': _safe_int(row[4])},
                {'umaban': _safe_int(row[5]), 'payout': _safe_int(row[6])},
                {'umaban': _safe_int(row[7]), 'payout': _safe_int(row[8])},
            ],
            'umaren': {
                'uma1': _safe_int(row[9]),
                'uma2': _safe_int(row[10]),
                'payout': _safe_int(row[11])
            },
            'wide': [
                {'uma1': _safe_int(row[12]), 'uma2': _safe_int(row[13]), 'payout': _safe_int(row[14])},
                {'uma1': _safe_int(row[15]), 'uma2': _safe_int(row[16]), 'payout': _safe_int(row[17])},
                {'uma1': _safe_int(row[18]), 'uma2': _safe_int(row[19]), 'payout': _safe_int(row[20])},
            ],
            'umatan': {
                'uma1': _safe_int(row[21]),
                'uma2': _safe_int(row[22]),
                'payout': _safe_int(row[23])
            },
            'sanrenpuku': {
                'uma1': _safe_int(row[24]),
                'uma2': _safe_int(row[25]),
                'uma3': _safe_int(row[26]),
                'payout': _safe_int(row[27])
            },
            'sanrentan': {
                'uma1': _safe_int(row[28]),
                'uma2': _safe_int(row[29]),
                'uma3': _safe_int(row[30]),
                'payout': _safe_int(row[31])
            }
        }

    return payouts


def _get_race_entries(conn, year: int, max_races: int) -> Dict[str, List[Dict]]:
    """レースごとの出走馬データを取得"""
    sql = """
        SELECT race_code, umaban, kakutei_chakujun
        FROM umagoto_race_joho
        WHERE kaisai_nen = %s AND data_kubun = '7'
          AND kakutei_chakujun ~ '^[0-9]+$'
        ORDER BY race_code, umaban::int
    """
    cur = conn.cursor()
    cur.execute(sql, (str(year),))
    rows = cur.fetchall()
    cur.close()

    entries = {}
    for row in rows:
        race_code, umaban, chakujun = row
        if race_code not in entries:
            entries[race_code] = []
        entries[race_code].append({
            'umaban': _safe_int(umaban),
            'rank': _safe_int(chakujun)
        })

    return entries


def _safe_int(val, default: int = 0) -> int:
    """文字列を整数に変換（払い戻し金額も対応）"""
    try:
        if val is None or val == '' or val == '00':
            return default
        # 先頭のゼロを除去して変換
        return int(str(val).lstrip('0') or '0')
    except (ValueError, TypeError):
        return default


def evaluate_all_bets(
    df: pd.DataFrame,
    race_entries: Dict[str, List[Dict]],
    payouts: Dict[str, Dict]
) -> Dict[str, Any]:
    """全馬券式別の評価"""

    results = {
        'tansho': {'hits': 0, 'return': 0, 'bet': 0},
        'fukusho': {'hits': 0, 'return': 0, 'bet': 0},
        'umaren': {'hits': 0, 'return': 0, 'bet': 0},
        'wide': {'hits': 0, 'return': 0, 'bet': 0},
        'umatan': {'hits': 0, 'return': 0, 'bet': 0},
        'sanrenpuku': {'hits': 0, 'return': 0, 'bet': 0},
        'sanrentan': {'hits': 0, 'return': 0, 'bet': 0},
    }

    processed_races = 0

    # レースコードでグループ化
    race_codes = list(payouts.keys())

    # dfにrace_codeがないので、順序でマッチング
    # まずrace_entriesのレースコード順に処理
    sample_idx = 0

    for race_code in race_codes:
        if race_code not in race_entries:
            continue

        entries = race_entries[race_code]
        num_horses = len(entries)

        if sample_idx + num_horses > len(df):
            break

        # このレースのデータを取得
        race_df = df.iloc[sample_idx:sample_idx + num_horses].copy()
        sample_idx += num_horses

        if len(race_df) < 2:
            continue

        payout = payouts.get(race_code)
        if not payout:
            continue

        # 予測順位でソート（スコアが低いほど上位予測）
        race_df = race_df.sort_values('pred_score')
        pred_ranks = race_df['umaban'].astype(int).tolist()

        if len(pred_ranks) < 3:
            continue

        pred_1st = pred_ranks[0]
        pred_2nd = pred_ranks[1]
        pred_3rd = pred_ranks[2]

        # 実際の結果
        actual = {e['umaban']: e['rank'] for e in entries}

        # === 単勝 ===
        results['tansho']['bet'] += 100
        if payout['tansho']['umaban'] == pred_1st:
            results['tansho']['hits'] += 1
            results['tansho']['return'] += payout['tansho']['payout']

        # === 複勝（1位予測馬が3着以内） ===
        results['fukusho']['bet'] += 100
        for f in payout['fukusho']:
            if f['umaban'] == pred_1st and f['payout'] > 0:
                results['fukusho']['hits'] += 1
                results['fukusho']['return'] += f['payout']
                break

        # === 馬連（1-2位予測） ===
        results['umaren']['bet'] += 100
        uma = payout['umaren']
        pred_pair = {pred_1st, pred_2nd}
        actual_pair = {uma['uma1'], uma['uma2']}
        if pred_pair == actual_pair and uma['payout'] > 0:
            results['umaren']['hits'] += 1
            results['umaren']['return'] += uma['payout']

        # === ワイド（1-2位予測がTOP3に含まれる） ===
        results['wide']['bet'] += 100
        for w in payout['wide']:
            if w['payout'] > 0:
                wide_pair = {w['uma1'], w['uma2']}
                if pred_pair == wide_pair:
                    results['wide']['hits'] += 1
                    results['wide']['return'] += w['payout']
                    break

        # === 馬単（1→2位予測、順番も一致） ===
        results['umatan']['bet'] += 100
        ut = payout['umatan']
        if ut['uma1'] == pred_1st and ut['uma2'] == pred_2nd and ut['payout'] > 0:
            results['umatan']['hits'] += 1
            results['umatan']['return'] += ut['payout']

        # === 三連複（1-2-3位予測） ===
        results['sanrenpuku']['bet'] += 100
        sp = payout['sanrenpuku']
        pred_trio = {pred_1st, pred_2nd, pred_3rd}
        actual_trio = {sp['uma1'], sp['uma2'], sp['uma3']}
        if pred_trio == actual_trio and sp['payout'] > 0:
            results['sanrenpuku']['hits'] += 1
            results['sanrenpuku']['return'] += sp['payout']

        # === 三連単（1→2→3位予測、順番も一致） ===
        results['sanrentan']['bet'] += 100
        st = payout['sanrentan']
        if st['uma1'] == pred_1st and st['uma2'] == pred_2nd and st['uma3'] == pred_3rd and st['payout'] > 0:
            results['sanrentan']['hits'] += 1
            results['sanrentan']['return'] += st['payout']

        processed_races += 1

    # 結果を整形
    output = {
        'total_races': processed_races,
        'year': year if 'year' in dir() else 2025,
        'bets': {}
    }

    for bet_type, data in results.items():
        total_bet = data['bet']
        total_return = data['return']
        hits = data['hits']

        if total_bet > 0:
            output['bets'][bet_type] = {
                'hits': hits,
                'total': processed_races,
                'hit_rate': f"{hits/processed_races*100:.1f}%",
                'return': total_return,
                'bet': total_bet,
                'roi': f"{total_return/total_bet*100:.1f}%"
            }

    return output


def main():
    parser = argparse.ArgumentParser(description="全馬券式別バックテスト")
    parser.add_argument("--model", "-m", default="/app/models/xgboost_model_latest.pkl")
    parser.add_argument("--year", "-y", type=int, default=2025)
    parser.add_argument("--max-races", "-n", type=int, default=500)

    args = parser.parse_args()

    print("=" * 60)
    print("全馬券式別バックテスト")
    print("=" * 60)
    print(f"モデル: {args.model}")
    print(f"対象年: {args.year}年")
    print(f"最大レース数: {args.max_races}")
    print("=" * 60)

    results = run_full_backtest(args.model, args.year, args.max_races)

    print()
    if "error" in results:
        print(f"エラー: {results['error']}")
        return

    print("【バックテスト結果】")
    print(f"対象: {results['total_races']}レース")
    print()
    print("=" * 60)
    print(f"{'馬券種別':<12} {'的中':>6} {'的中率':>8} {'回収率':>10} {'収支':>12}")
    print("=" * 60)

    bet_names = {
        'tansho': '単勝',
        'fukusho': '複勝',
        'umaren': '馬連',
        'wide': 'ワイド',
        'umatan': '馬単',
        'sanrenpuku': '三連複',
        'sanrentan': '三連単'
    }

    for bet_type in ['tansho', 'fukusho', 'umaren', 'wide', 'umatan', 'sanrenpuku', 'sanrentan']:
        data = results['bets'].get(bet_type, {})
        if data:
            hits = f"{data['hits']}/{data['total']}"
            profit = data['return'] - data['bet']
            profit_str = f"¥{profit:+,}"
            print(f"{bet_names[bet_type]:<12} {hits:>6} {data['hit_rate']:>8} {data['roi']:>10} {profit_str:>12}")

    print("=" * 60)

    # 総合収支
    total_bet = sum(d.get('bet', 0) for d in results['bets'].values())
    total_return = sum(d.get('return', 0) for d in results['bets'].values())
    total_profit = total_return - total_bet
    total_roi = total_return / total_bet * 100 if total_bet > 0 else 0

    print(f"\n【総合】")
    print(f"  総投資: ¥{total_bet:,}")
    print(f"  総回収: ¥{total_return:,}")
    print(f"  総収支: ¥{total_profit:+,}")
    print(f"  総合回収率: {total_roi:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
