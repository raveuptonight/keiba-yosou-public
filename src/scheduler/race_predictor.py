"""
レース予想スケジューラ

開催前日に自動で：
1. 出馬表データの確認
2. 機械学習モデルで予想
3. 結果を保存/通知
"""

import argparse
import logging
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
import joblib

from src.db.connection import get_db
from src.models.fast_train import FastFeatureExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RacePredictor:
    """レース予想クラス（ensemble_model対応）"""

    def __init__(self, model_path: str = "/app/models/ensemble_model_latest.pkl"):
        self.model_path = model_path
        self.xgb_model = None
        self.lgb_model = None
        self.feature_names = None
        self._load_model()

    def _load_model(self):
        """ensemble_modelを読み込み"""
        try:
            model_data = joblib.load(self.model_path)
            self.xgb_model = model_data['xgb_model']
            self.lgb_model = model_data['lgb_model']
            self.feature_names = model_data['feature_names']
            logger.info(f"ensemble_model読み込み完了: {len(self.feature_names)}特徴量")
        except Exception as e:
            logger.error(f"モデル読み込み失敗: {e}")
            raise

    def get_upcoming_races(self, target_date: date = None) -> List[Dict]:
        """指定日の出馬表を取得"""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # 対象日のレースを取得
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # まず出馬表データがあるか確認
            cur.execute('''
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.kyori, r.track_code, r.grade_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun IN ('3', '4', '5', '6')
                ORDER BY r.race_code
            ''', (kaisai_nen, kaisai_gappi))

            races = []
            keibajo_names = {
                '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
                '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
            }

            for row in cur.fetchall():
                races.append({
                    'race_code': row[0],
                    'keibajo_code': row[1],
                    'keibajo_name': keibajo_names.get(row[1], row[1]),
                    'race_bango': row[2],
                    'kyori': row[3],
                    'track_code': row[4],
                    'grade_code': row[5]
                })

            cur.close()
            return races

        finally:
            conn.close()

    def get_race_entries(self, race_code: str) -> List[Dict]:
        """レースの出走馬情報を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT
                    umaban, wakuban, ketto_toroku_bango, bamei,
                    kishu_code, futan_juryo, barei, seibetsu_code
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('3', '4', '5', '6')
                ORDER BY umaban::int
            ''', (race_code,))

            entries = []
            for row in cur.fetchall():
                entries.append({
                    'umaban': row[0],
                    'wakuban': row[1],
                    'ketto_toroku_bango': row[2],
                    'bamei': row[3],
                    'kishu_code': row[4],
                    'futan_juryo': row[5],
                    'barei': row[6],
                    'seibetsu_code': row[7]
                })

            cur.close()
            return entries

        finally:
            conn.close()

    def predict_race(self, race_code: str) -> List[Dict]:
        """レースの予想を実行"""
        db = get_db()
        conn = db.get_connection()

        try:
            # FastFeatureExtractorを使用
            extractor = FastFeatureExtractor(conn)

            # レース情報を取得
            cur = conn.cursor()
            cur.execute('''
                SELECT kaisai_nen, keibajo_code, race_bango
                FROM race_shosai
                WHERE race_code = %s
                LIMIT 1
            ''', (race_code,))
            race_info = cur.fetchone()
            if not race_info:
                return []

            year = int(race_info[0])

            # 特徴量抽出（1レース分）
            cur.execute('''
                SELECT race_code FROM race_shosai
                WHERE race_code = %s
            ''', (race_code,))

            # 出走馬データを取得
            cur.execute('''
                SELECT
                    race_code, umaban, wakuban, ketto_toroku_bango,
                    seibetsu_code, barei, futan_juryo,
                    blinker_shiyo_kubun, kishu_code, chokyoshi_code,
                    bataiju, zogen_sa, bamei
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('3', '4', '5', '6')
                ORDER BY umaban::int
            ''', (race_code,))

            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            entries = [dict(zip(cols, row)) for row in rows]

            if not entries:
                logger.warning(f"出走馬データなし: {race_code}")
                return []

            # レース情報取得
            cur.execute('''
                SELECT race_code, kaisai_nen, kaisai_gappi, keibajo_code,
                       kyori, track_code, grade_code,
                       shiba_babajotai_code, dirt_babajotai_code
                FROM race_shosai
                WHERE race_code = %s
            ''', (race_code,))
            race_row = cur.fetchone()
            race_cols = [d[0] for d in cur.description]
            races = [dict(zip(race_cols, race_row))] if race_row else []

            # 過去成績を取得
            kettonums = [e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')]
            past_stats = extractor._get_past_stats_batch(kettonums)

            # 騎手・調教師キャッシュ
            extractor._cache_jockey_trainer_stats(year)

            # 追加データ
            jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                        for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
            jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
            surface_stats = extractor._get_surface_stats_batch(kettonums)
            turn_stats = extractor._get_turn_rates_batch(kettonums)
            for kettonum, stats in turn_stats.items():
                if kettonum in past_stats:
                    past_stats[kettonum]['right_turn_rate'] = stats['right_turn_rate']
                    past_stats[kettonum]['left_turn_rate'] = stats['left_turn_rate']
            training_stats = extractor._get_training_stats_batch(kettonums)

            # 特徴量生成
            features_list = []
            for entry in entries:
                # kakutei_chakujunがない場合はダミー値を設定
                entry['kakutei_chakujun'] = '01'  # 予測用ダミー

                features = extractor._build_features(
                    entry, races, past_stats,
                    jockey_horse_stats=jockey_horse_stats,
                    distance_stats=surface_stats,
                    training_stats=training_stats
                )
                if features:
                    features['bamei'] = entry.get('bamei', '')
                    features_list.append(features)

            if not features_list:
                return []

            # 予測（ensemble: XGBoost + LightGBM の平均）
            df = pd.DataFrame(features_list)
            X = df[self.feature_names].fillna(0)
            xgb_pred = self.xgb_model.predict(X)
            lgb_pred = self.lgb_model.predict(X)
            predictions = (xgb_pred + lgb_pred) / 2

            # 結果を整形
            results = []
            for i, pred in enumerate(predictions):
                results.append({
                    'umaban': features_list[i]['umaban'],
                    'bamei': features_list[i].get('bamei', ''),
                    'pred_score': float(pred),
                    'pred_rank': 0  # 後で設定
                })

            # 予測順位を設定（スコアが低いほど上位）
            results.sort(key=lambda x: x['pred_score'])
            for i, r in enumerate(results):
                r['pred_rank'] = i + 1

            # 馬番順に戻す
            results.sort(key=lambda x: int(x['umaban']))

            cur.close()
            return results

        finally:
            conn.close()

    def run_predictions(self, target_date: date = None) -> Dict[str, Any]:
        """指定日の全レース予想を実行"""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        logger.info(f"予想実行: {target_date}")

        # 出馬表確認
        races = self.get_upcoming_races(target_date)

        if not races:
            logger.info(f"{target_date}の出馬表データがありません")
            return {
                'date': str(target_date),
                'status': 'no_data',
                'races': []
            }

        logger.info(f"{len(races)}レースの出馬表を確認")

        results = {
            'date': str(target_date),
            'status': 'success',
            'generated_at': datetime.now().isoformat(),
            'races': []
        }

        for race in races:
            race_code = race['race_code']
            logger.info(f"予想中: {race['keibajo_name']} {race['race_bango']}R")

            try:
                predictions = self.predict_race(race_code)

                if predictions:
                    # TOP3を抽出
                    top3 = sorted(predictions, key=lambda x: x['pred_rank'])[:3]

                    race_result = {
                        'race_code': race_code,
                        'keibajo': race['keibajo_name'],
                        'race_number': race['race_bango'],
                        'kyori': race['kyori'],
                        'predictions': predictions,
                        'top3': [
                            {'rank': p['pred_rank'], 'umaban': p['umaban'], 'bamei': p['bamei']}
                            for p in top3
                        ]
                    }
                    results['races'].append(race_result)
                    logger.info(f"  TOP3: {[f\"{p['umaban']}番{p['bamei']}\" for p in top3]}")

            except Exception as e:
                logger.error(f"予想失敗 {race_code}: {e}")

        return results


def save_predictions(results: Dict, output_dir: str = "/app/predictions"):
    """予想結果を保存"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    date_str = results['date'].replace('-', '')
    output_path = Path(output_dir) / f"predictions_{date_str}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"予想結果保存: {output_path}")
    return str(output_path)


def print_predictions(results: Dict):
    """予想結果を表示"""
    print("\n" + "=" * 60)
    print(f"【{results['date']} レース予想】")
    print("=" * 60)

    if results['status'] == 'no_data':
        print("出馬表データがありません")
        return

    for race in results['races']:
        print(f"\n■ {race['keibajo']} {race['race_number']}R ({race['kyori']}m)")
        print("-" * 40)
        print("予想順位:")
        for p in race['top3']:
            print(f"  {p['rank']}位: {p['umaban']}番 {p['bamei']}")

    print("\n" + "=" * 60)
    print(f"生成日時: {results['generated_at']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="レース予想スケジューラ")
    parser.add_argument("--date", "-d", help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--tomorrow", "-t", action="store_true", help="明日のレースを予想")
    parser.add_argument("--output", "-o", default="/app/predictions", help="出力ディレクトリ")
    parser.add_argument("--model", "-m", default="/app/models/ensemble_model_latest.pkl")

    args = parser.parse_args()

    # 対象日を決定
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.tomorrow:
        target_date = date.today() + timedelta(days=1)
    else:
        target_date = date.today() + timedelta(days=1)

    print(f"対象日: {target_date}")

    # 予想実行
    predictor = RacePredictor(args.model)
    results = predictor.run_predictions(target_date)

    # 結果表示
    print_predictions(results)

    # 結果保存
    if results['status'] == 'success' and results['races']:
        save_predictions(results, args.output)


if __name__ == "__main__":
    main()
