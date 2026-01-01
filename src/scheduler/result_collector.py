"""
結果収集モジュール

レース終了後に結果を収集し、予想との比較を行う
"""

import logging
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResultCollector:
    """レース結果収集クラス"""

    def __init__(self, predictions_dir: str = "/app/predictions"):
        self.predictions_dir = Path(predictions_dir)
        self.keibajo_names = {
            '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
            '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
        }

    def get_race_results(self, target_date: date) -> List[Dict]:
        """指定日のレース結果を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # 確定結果のあるレースを取得
            cur.execute('''
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.kyori, r.track_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun = '7'
                ORDER BY r.race_code
            ''', (kaisai_nen, kaisai_gappi))

            races = []
            for row in cur.fetchall():
                race_code = row[0]

                # 各レースの着順を取得
                cur.execute('''
                    SELECT umaban, kakutei_chakujun, bamei
                    FROM umagoto_race_joho
                    WHERE race_code = %s
                      AND data_kubun = '7'
                    ORDER BY kakutei_chakujun::int
                ''', (race_code,))

                results = []
                for r in cur.fetchall():
                    results.append({
                        'umaban': r[0],
                        'chakujun': int(r[1]) if r[1] else 99,
                        'bamei': r[2]
                    })

                races.append({
                    'race_code': race_code,
                    'keibajo': self.keibajo_names.get(row[1], row[1]),
                    'race_number': row[2],
                    'kyori': row[3],
                    'track': '芝' if row[4] and row[4].startswith('1') else 'ダ',
                    'results': results
                })

            cur.close()
            return races

        finally:
            conn.close()

    def load_predictions(self, target_date: date) -> Optional[Dict]:
        """予想結果を読み込み"""
        date_str = target_date.strftime("%Y%m%d")
        pred_file = self.predictions_dir / f"predictions_{date_str}.json"

        if not pred_file.exists():
            logger.warning(f"予想ファイルが見つかりません: {pred_file}")
            return None

        with open(pred_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def compare_results(self, predictions: Dict, results: List[Dict]) -> Dict:
        """予想と結果を比較"""
        comparison = {
            'date': predictions['date'],
            'total_races': 0,
            'analyzed_races': 0,
            'stats': {
                'top1_hit': 0,  # 1位予想が1着
                'top1_in_top3': 0,  # 1位予想が3着以内
                'top3_hit': 0,  # TOP3予想が1-2-3着
                'tansho_hit': 0,  # 単勝的中
                'fukusho_hit': 0,  # 複勝的中
                'umaren_hit': 0,  # 馬連的中
                'sanrenpuku_hit': 0,  # 三連複的中
            },
            'races': []
        }

        # レースコードでマッピング
        results_map = {r['race_code']: r for r in results}

        for pred_race in predictions.get('races', []):
            race_code = pred_race['race_code']
            comparison['total_races'] += 1

            if race_code not in results_map:
                continue

            actual = results_map[race_code]
            comparison['analyzed_races'] += 1

            # 予想TOP3を取得
            pred_top3 = pred_race.get('top3', [])
            pred_top3_umaban = [str(p['umaban']) for p in pred_top3]

            # 実際の着順（TOP3）
            actual_top3 = [str(r['umaban']) for r in actual['results'][:3] if r['chakujun'] <= 3]

            # 統計計算
            race_result = {
                'race_code': race_code,
                'keibajo': actual['keibajo'],
                'race_number': actual['race_number'],
                'pred_top3': pred_top3_umaban,
                'actual_top3': actual_top3,
                'hits': {}
            }

            # 1位予想が1着
            if pred_top3_umaban and actual_top3:
                if pred_top3_umaban[0] == actual_top3[0]:
                    comparison['stats']['top1_hit'] += 1
                    comparison['stats']['tansho_hit'] += 1
                    race_result['hits']['tansho'] = True

                # 1位予想が3着以内
                if pred_top3_umaban[0] in actual_top3:
                    comparison['stats']['top1_in_top3'] += 1
                    comparison['stats']['fukusho_hit'] += 1
                    race_result['hits']['fukusho'] = True

            # TOP3予想が全て3着以内
            if len(pred_top3_umaban) >= 3 and len(actual_top3) >= 3:
                if set(pred_top3_umaban[:3]) == set(actual_top3[:3]):
                    comparison['stats']['top3_hit'] += 1
                    comparison['stats']['sanrenpuku_hit'] += 1
                    race_result['hits']['sanrenpuku'] = True

            # 馬連（1-2位予想が1-2着）
            if len(pred_top3_umaban) >= 2 and len(actual_top3) >= 2:
                if set(pred_top3_umaban[:2]) == set(actual_top3[:2]):
                    comparison['stats']['umaren_hit'] += 1
                    race_result['hits']['umaren'] = True

            comparison['races'].append(race_result)

        return comparison

    def calculate_accuracy(self, comparison: Dict) -> Dict:
        """精度指標を計算"""
        n = comparison['analyzed_races']
        if n == 0:
            return {'error': 'no_data'}

        stats = comparison['stats']

        return {
            'date': comparison['date'],
            'total_races': comparison['total_races'],
            'analyzed_races': n,
            'accuracy': {
                'top1_hit_rate': stats['top1_hit'] / n * 100,
                'top1_in_top3_rate': stats['top1_in_top3'] / n * 100,
                'tansho_hit_rate': stats['tansho_hit'] / n * 100,
                'fukusho_hit_rate': stats['fukusho_hit'] / n * 100,
                'umaren_hit_rate': stats['umaren_hit'] / n * 100,
                'sanrenpuku_hit_rate': stats['sanrenpuku_hit'] / n * 100,
            },
            'raw_stats': stats
        }

    def collect_and_analyze(self, target_date: date) -> Dict:
        """結果収集と分析を実行"""
        logger.info(f"結果収集開始: {target_date}")

        # 予想を読み込み
        predictions = self.load_predictions(target_date)
        if not predictions:
            return {'status': 'no_predictions', 'date': str(target_date)}

        # 結果を取得
        results = self.get_race_results(target_date)
        if not results:
            logger.info(f"{target_date}の結果データがありません")
            return {'status': 'no_results', 'date': str(target_date)}

        logger.info(f"{len(results)}レースの結果を取得")

        # 比較
        comparison = self.compare_results(predictions, results)

        # 精度計算
        accuracy = self.calculate_accuracy(comparison)

        return {
            'status': 'success',
            'comparison': comparison,
            'accuracy': accuracy
        }

    def save_analysis(self, analysis: Dict, output_dir: str = "/app/analysis"):
        """分析結果を保存"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        date_str = analysis.get('accuracy', {}).get('date', 'unknown')
        if date_str == 'unknown' and 'comparison' in analysis:
            date_str = analysis['comparison'].get('date', 'unknown')

        output_path = Path(output_dir) / f"analysis_{date_str.replace('-', '')}.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        logger.info(f"分析結果保存: {output_path}")
        return str(output_path)


def collect_yesterday_results():
    """昨日のレース結果を収集"""
    collector = ResultCollector()
    yesterday = date.today() - timedelta(days=1)

    analysis = collector.collect_and_analyze(yesterday)

    if analysis['status'] == 'success':
        collector.save_analysis(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} 予想精度 ===")
        print(f"分析レース数: {acc['analyzed_races']}")
        print(f"単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"複勝的中率: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"馬連的中率: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"三連複的中率: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"結果収集失敗: {analysis['status']}")


def main():
    """テスト実行"""
    import argparse

    parser = argparse.ArgumentParser(description="結果収集")
    parser.add_argument("--date", "-d", help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--yesterday", "-y", action="store_true", help="昨日の結果を収集")

    args = parser.parse_args()

    collector = ResultCollector()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.yesterday:
        target_date = date.today() - timedelta(days=1)
    else:
        target_date = date.today() - timedelta(days=1)

    analysis = collector.collect_and_analyze(target_date)

    if analysis['status'] == 'success':
        collector.save_analysis(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} 予想精度 ===")
        print(f"分析レース数: {acc['analyzed_races']}")
        print(f"単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"複勝的中率: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"馬連的中率: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"三連複的中率: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"結果収集: {analysis['status']}")


if __name__ == "__main__":
    main()
