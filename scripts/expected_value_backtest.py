"""
期待値ベース馬券推奨のバックテスト

予測確率 × オッズ > 閾値 の馬だけを買った場合の回収率を検証
"""

import logging
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import joblib
import psycopg2.extras
from collections import defaultdict

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_expected_value_backtest(test_year: int = 2022, model_path: str = None):
    """期待値ベースのバックテストを実行"""

    if model_path is None:
        model_path = Path(__file__).parent.parent / "models" / "ensemble_model_latest.pkl"

    logger.info(f"期待値バックテスト開始: {test_year}年")

    # モデル読み込み
    model_data = joblib.load(model_path)
    models = model_data['models']
    features = model_data['feature_names']

    xgb_reg = models.get('xgb_regressor') or model_data.get('xgb_model')
    lgb_reg = models.get('lgb_regressor') or model_data.get('lgb_model')

    # 勝利確率モデル
    xgb_win = models.get('xgb_win')
    lgb_win = models.get('lgb_win')
    win_calibrator = models.get('win_calibrator')

    # 複勝確率モデル
    xgb_place = models.get('xgb_place')
    lgb_place = models.get('lgb_place')
    place_calibrator = models.get('place_calibrator')

    db = get_db()
    conn = db.get_connection()

    try:
        # テストデータ取得
        extractor = FastFeatureExtractor(conn)
        test_data = extractor.extract_year_data(test_year)
        df = pd.DataFrame(test_data)

        logger.info(f"テストデータ: {len(df)}件")

        # 予測
        X = df[features].fillna(0)

        # 着順予測
        pred_rank = (xgb_reg.predict(X) + lgb_reg.predict(X)) / 2
        df['pred_rank'] = pred_rank

        # 勝利確率
        if xgb_win and lgb_win:
            win_prob = (xgb_win.predict_proba(X)[:, 1] + lgb_win.predict_proba(X)[:, 1]) / 2
            if win_calibrator:
                win_prob = win_calibrator.predict(win_prob)
            df['win_prob'] = win_prob

        # 複勝確率
        if xgb_place and lgb_place:
            place_prob = (xgb_place.predict_proba(X)[:, 1] + lgb_place.predict_proba(X)[:, 1]) / 2
            if place_calibrator:
                place_prob = place_calibrator.predict(place_prob)
            df['place_prob'] = place_prob

        # オッズデータ取得
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 単勝オッズ
        cur.execute('''
            SELECT race_code, umaban, odds
            FROM odds1_tansho
            WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
        ''', (test_year,))

        tansho_odds = {}
        for row in cur.fetchall():
            race_code = row['race_code']
            umaban = str(row['umaban']).strip()
            try:
                odds = float(row['odds']) / 10  # オッズは10倍で格納されている
            except:
                odds = 0
            tansho_odds[(race_code, umaban)] = odds

        logger.info(f"単勝オッズ: {len(tansho_odds)}件")

        # 複勝オッズ
        cur.execute('''
            SELECT race_code, umaban, odds_saitei, odds_saikou
            FROM odds1_fukusho
            WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
        ''', (test_year,))

        fukusho_odds = {}
        for row in cur.fetchall():
            race_code = row['race_code']
            umaban = str(row['umaban']).strip()
            try:
                # 複勝は最低オッズを使用
                odds = float(row['odds_saitei']) / 10
            except:
                odds = 0
            fukusho_odds[(race_code, umaban)] = odds

        logger.info(f"複勝オッズ: {len(fukusho_odds)}件")

        # 払戻データ取得
        cur.execute('''
            SELECT race_code,
                   tansho1_umaban, tansho1_haraimodoshikin,
                   fukusho1_umaban, fukusho1_haraimodoshikin,
                   fukusho2_umaban, fukusho2_haraimodoshikin,
                   fukusho3_umaban, fukusho3_haraimodoshikin
            FROM haraimodoshi
            WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
        ''', (test_year,))

        payouts = {}
        for row in cur.fetchall():
            payouts[row['race_code']] = row

        logger.info(f"払戻データ: {len(payouts)}件")
        cur.close()

        # オッズと期待値をDataFrameに追加
        df['tansho_odds'] = df.apply(
            lambda r: tansho_odds.get((r['race_code'], str(int(r['umaban']))), 0), axis=1
        )
        df['fukusho_odds'] = df.apply(
            lambda r: fukusho_odds.get((r['race_code'], str(int(r['umaban']))), 0), axis=1
        )

        # 期待値計算
        df['win_ev'] = df['win_prob'] * df['tansho_odds']
        df['place_ev'] = df['place_prob'] * df['fukusho_odds']

        # 閾値別の回収率を計算
        thresholds = [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]

        print("\n" + "=" * 70)
        print("期待値フィルタ バックテスト結果")
        print("=" * 70)

        # 単勝の分析
        print("\n【単勝】期待値 = 勝利確率 × 単勝オッズ")
        print("-" * 70)
        print(f"{'閾値':>6} | {'対象数':>8} | {'的中数':>6} | {'的中率':>8} | {'投資':>10} | {'回収':>10} | {'回収率':>8}")
        print("-" * 70)

        for threshold in thresholds:
            result = calculate_return_with_ev_filter(
                df, payouts, 'tansho', 'win_ev', threshold
            )
            print(f"{threshold:>6.1f} | {result['bets']:>8} | {result['hits']:>6} | "
                  f"{result['hit_rate']*100:>7.1f}% | {result['investment']:>10} | "
                  f"{result['payout']:>10} | {result['roi']*100:>7.1f}%")

        # 複勝の分析
        print("\n【複勝】期待値 = 複勝確率 × 複勝オッズ")
        print("-" * 70)
        print(f"{'閾値':>6} | {'対象数':>8} | {'的中数':>6} | {'的中率':>8} | {'投資':>10} | {'回収':>10} | {'回収率':>8}")
        print("-" * 70)

        for threshold in thresholds:
            result = calculate_return_with_ev_filter(
                df, payouts, 'fukusho', 'place_ev', threshold
            )
            print(f"{threshold:>6.1f} | {result['bets']:>8} | {result['hits']:>6} | "
                  f"{result['hit_rate']*100:>7.1f}% | {result['investment']:>10} | "
                  f"{result['payout']:>10} | {result['roi']*100:>7.1f}%")

        # 1位予想 + 期待値フィルタの組み合わせ
        print("\n【1位予想 + 期待値フィルタ】")
        print("-" * 70)

        for threshold in [1.0, 1.2, 1.5]:
            result = calculate_return_top1_with_ev(
                df, payouts, 'tansho', 'win_ev', threshold
            )
            print(f"単勝 EV>{threshold}: 対象{result['bets']}R, 的中{result['hits']}, "
                  f"回収率{result['roi']*100:.1f}%")

        print()
        for threshold in [1.0, 1.2, 1.5]:
            result = calculate_return_top1_with_ev(
                df, payouts, 'fukusho', 'place_ev', threshold
            )
            print(f"複勝 EV>{threshold}: 対象{result['bets']}R, 的中{result['hits']}, "
                  f"回収率{result['roi']*100:.1f}%")

        print("\n" + "=" * 70)

    finally:
        conn.close()


def calculate_return_with_ev_filter(df, payouts, bet_type, ev_col, threshold):
    """期待値フィルタで回収率を計算（全馬対象）"""

    # 期待値が閾値以上の馬を抽出
    filtered = df[df[ev_col] >= threshold].copy()

    bets = 0
    hits = 0
    investment = 0
    payout = 0

    for _, row in filtered.iterrows():
        race_code = row['race_code']
        umaban = str(int(row['umaban']))

        payout_data = payouts.get(race_code)
        if not payout_data:
            continue

        investment += 100
        bets += 1

        if bet_type == 'tansho':
            # 単勝チェック
            win_umaban = str(payout_data['tansho1_umaban']).strip() if payout_data['tansho1_umaban'] else None
            if win_umaban == umaban:
                hits += 1
                try:
                    payout += int(str(payout_data['tansho1_haraimodoshikin']).strip())
                except:
                    pass
        else:
            # 複勝チェック
            for i in range(1, 4):
                fuku_umaban = payout_data.get(f'fukusho{i}_umaban')
                fuku_payout = payout_data.get(f'fukusho{i}_haraimodoshikin')
                if fuku_umaban and str(fuku_umaban).strip() == umaban:
                    hits += 1
                    try:
                        payout += int(str(fuku_payout).strip())
                    except:
                        pass
                    break

    return {
        'bets': bets,
        'hits': hits,
        'hit_rate': hits / bets if bets > 0 else 0,
        'investment': investment,
        'payout': payout,
        'roi': payout / investment if investment > 0 else 0
    }


def calculate_return_top1_with_ev(df, payouts, bet_type, ev_col, threshold):
    """1位予想 + 期待値フィルタで回収率を計算"""

    bets = 0
    hits = 0
    investment = 0
    payout_total = 0

    for race_code, race_df in df.groupby('race_code'):
        # 1位予想を取得
        race_df_sorted = race_df.sort_values('pred_rank')
        top1 = race_df_sorted.iloc[0]

        # 期待値チェック
        if top1[ev_col] < threshold:
            continue

        umaban = str(int(top1['umaban']))

        payout_data = payouts.get(race_code)
        if not payout_data:
            continue

        investment += 100
        bets += 1

        if bet_type == 'tansho':
            win_umaban = str(payout_data['tansho1_umaban']).strip() if payout_data['tansho1_umaban'] else None
            if win_umaban == umaban:
                hits += 1
                try:
                    payout_total += int(str(payout_data['tansho1_haraimodoshikin']).strip())
                except:
                    pass
        else:
            for i in range(1, 4):
                fuku_umaban = payout_data.get(f'fukusho{i}_umaban')
                fuku_payout = payout_data.get(f'fukusho{i}_haraimodoshikin')
                if fuku_umaban and str(fuku_umaban).strip() == umaban:
                    hits += 1
                    try:
                        payout_total += int(str(fuku_payout).strip())
                    except:
                        pass
                    break

    return {
        'bets': bets,
        'hits': hits,
        'hit_rate': hits / bets if bets > 0 else 0,
        'investment': investment,
        'payout': payout_total,
        'roi': payout_total / investment if investment > 0 else 0
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="期待値ベース馬券推奨のバックテスト")
    parser.add_argument("--year", "-y", type=int, default=2022, help="テスト年（デフォルト: 2022）")

    args = parser.parse_args()

    run_expected_value_backtest(test_year=args.year)
