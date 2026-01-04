"""
週次バックテスト・精度トラッキングモジュール

毎週日曜夜に実行して：
1. 今週の予想精度を集計
2. 累積精度を更新
3. レポート生成・通知
"""

import logging
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.db.connection import get_db
from src.scheduler.result_collector import ResultCollector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeeklyBacktest:
    """週次バックテストクラス"""

    def __init__(
        self,
        analysis_dir: str = "/app/analysis",
        tracking_file: str = "/app/analysis/accuracy_tracking.json"
    ):
        self.analysis_dir = Path(analysis_dir)
        self.tracking_file = Path(tracking_file)
        self.collector = ResultCollector(analysis_dir)

    def get_week_dates(self, end_date: date = None) -> List[date]:
        """今週の日付リストを取得（土日のレース日）"""
        if end_date is None:
            end_date = date.today()

        # 直近の日曜日を取得
        days_since_sunday = end_date.weekday() + 1
        if days_since_sunday == 7:
            days_since_sunday = 0
        last_sunday = end_date - timedelta(days=days_since_sunday)

        # 土曜と日曜
        saturday = last_sunday - timedelta(days=1)
        sunday = last_sunday

        return [saturday, sunday]

    def run_weekly_analysis(self, week_end: date = None) -> Dict:
        """週次分析を実行"""
        week_dates = self.get_week_dates(week_end)
        logger.info(f"週次分析: {week_dates[0]} - {week_dates[-1]}")

        weekly_stats = {
            'week_start': str(week_dates[0]),
            'week_end': str(week_dates[-1]),
            'generated_at': datetime.now().isoformat(),
            'days_analyzed': 0,
            'total_races': 0,
            'stats': {
                'tansho_hit': 0,
                'fukusho_hit': 0,
                'umaren_hit': 0,
                'sanrenpuku_hit': 0,
            },
            'daily_results': []
        }

        for target_date in week_dates:
            analysis = self.collector.collect_and_analyze(target_date)

            if analysis['status'] == 'success':
                weekly_stats['days_analyzed'] += 1
                acc = analysis['accuracy']
                weekly_stats['total_races'] += acc['analyzed_races']

                # 統計を加算
                for key in weekly_stats['stats']:
                    weekly_stats['stats'][key] += acc['raw_stats'].get(key, 0)

                weekly_stats['daily_results'].append({
                    'date': str(target_date),
                    'races': acc['analyzed_races'],
                    'accuracy': acc['accuracy']
                })

                # 個別分析も保存
                self.collector.save_analysis(analysis, str(self.analysis_dir))

        # 週間精度を計算
        n = weekly_stats['total_races']
        if n > 0:
            weekly_stats['weekly_accuracy'] = {
                'tansho_hit_rate': weekly_stats['stats']['tansho_hit'] / n * 100,
                'fukusho_hit_rate': weekly_stats['stats']['fukusho_hit'] / n * 100,
                'umaren_hit_rate': weekly_stats['stats']['umaren_hit'] / n * 100,
                'sanrenpuku_hit_rate': weekly_stats['stats']['sanrenpuku_hit'] / n * 100,
            }

        return weekly_stats

    def load_tracking_data(self) -> Dict:
        """累積トラッキングデータを読み込み"""
        if self.tracking_file.exists():
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        return {
            'created_at': datetime.now().isoformat(),
            'total_races': 0,
            'total_stats': {
                'tansho_hit': 0,
                'fukusho_hit': 0,
                'umaren_hit': 0,
                'sanrenpuku_hit': 0,
            },
            'weekly_history': []
        }

    def update_tracking(self, weekly_stats: Dict) -> Dict:
        """累積トラッキングを更新"""
        tracking = self.load_tracking_data()

        # 累積統計を更新
        tracking['total_races'] += weekly_stats['total_races']
        for key in tracking['total_stats']:
            tracking['total_stats'][key] += weekly_stats['stats'].get(key, 0)

        # 累積精度を計算
        n = tracking['total_races']
        if n > 0:
            tracking['cumulative_accuracy'] = {
                'tansho_hit_rate': tracking['total_stats']['tansho_hit'] / n * 100,
                'fukusho_hit_rate': tracking['total_stats']['fukusho_hit'] / n * 100,
                'umaren_hit_rate': tracking['total_stats']['umaren_hit'] / n * 100,
                'sanrenpuku_hit_rate': tracking['total_stats']['sanrenpuku_hit'] / n * 100,
            }

        # 週次履歴に追加
        tracking['weekly_history'].append({
            'week_start': weekly_stats['week_start'],
            'week_end': weekly_stats['week_end'],
            'races': weekly_stats['total_races'],
            'accuracy': weekly_stats.get('weekly_accuracy', {})
        })

        tracking['last_updated'] = datetime.now().isoformat()

        # 保存
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tracking_file, 'w', encoding='utf-8') as f:
            json.dump(tracking, f, ensure_ascii=False, indent=2)

        logger.info(f"トラッキング更新: {self.tracking_file}")
        return tracking

    def generate_report(self, weekly_stats: Dict, tracking: Dict) -> str:
        """週次レポートを生成"""
        lines = [
            "=" * 50,
            f"【週次予想精度レポート】",
            f"期間: {weekly_stats['week_start']} - {weekly_stats['week_end']}",
            "=" * 50,
            "",
            "■ 今週の成績",
            f"  分析レース数: {weekly_stats['total_races']}R",
        ]

        if 'weekly_accuracy' in weekly_stats:
            wa = weekly_stats['weekly_accuracy']
            lines.extend([
                f"  単勝的中率: {wa['tansho_hit_rate']:.1f}%",
                f"  複勝的中率: {wa['fukusho_hit_rate']:.1f}%",
                f"  馬連的中率: {wa['umaren_hit_rate']:.1f}%",
                f"  三連複的中率: {wa['sanrenpuku_hit_rate']:.1f}%",
            ])

        lines.extend([
            "",
            "■ 累積成績",
            f"  総分析レース数: {tracking['total_races']}R",
        ])

        if 'cumulative_accuracy' in tracking:
            ca = tracking['cumulative_accuracy']
            lines.extend([
                f"  単勝的中率: {ca['tansho_hit_rate']:.1f}%",
                f"  複勝的中率: {ca['fukusho_hit_rate']:.1f}%",
                f"  馬連的中率: {ca['umaren_hit_rate']:.1f}%",
                f"  三連複的中率: {ca['sanrenpuku_hit_rate']:.1f}%",
            ])

        # 精度推移（直近4週）
        if tracking['weekly_history']:
            lines.extend(["", "■ 精度推移（直近4週）"])
            for week in tracking['weekly_history'][-4:]:
                if 'accuracy' in week and week['accuracy']:
                    lines.append(
                        f"  {week['week_end']}: "
                        f"単{week['accuracy'].get('tansho_hit_rate', 0):.0f}% "
                        f"複{week['accuracy'].get('fukusho_hit_rate', 0):.0f}% "
                        f"馬{week['accuracy'].get('umaren_hit_rate', 0):.0f}%"
                    )

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)

    def send_discord_notification(self, report: str):
        """Discordに週次レポートを通知"""
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        if not webhook_url:
            logger.info("Discord Webhook URLが未設定")
            return

        try:
            import requests
            payload = {"content": f"```\n{report}\n```"}
            response = requests.post(webhook_url, json=payload, timeout=10)

            if response.status_code == 204:
                logger.info("Discord通知送信完了")
            else:
                logger.warning(f"Discord通知失敗: {response.status_code}")
        except Exception as e:
            logger.error(f"Discord通知エラー: {e}")

    def retrain_calibration(self, days_back: int = 30) -> Optional[Dict]:
        """キャリブレーションを再学習"""
        logger.info(f"キャリブレーション再学習: 過去{days_back}日分")

        try:
            import numpy as np
            import joblib
            from sklearn.isotonic import IsotonicRegression

            cutoff_date = date.today() - timedelta(days=days_back)

            db = get_db()
            conn = db.get_connection()
            try:
                cur = conn.cursor()
                query = """
                SELECT
                    p.race_id,
                    p.prediction_result,
                    u.umaban,
                    u.kakutei_chakujun
                FROM predictions p
                JOIN umagoto_race_joho u ON p.race_id = u.race_code
                WHERE p.race_date >= %s
                  AND p.race_date < CURRENT_DATE
                  AND u.data_kubun IN ('6', '7')
                  AND u.kakutei_chakujun IS NOT NULL
                  AND u.kakutei_chakujun != ''
                  AND u.kakutei_chakujun != '00'
                """
                cur.execute(query, (cutoff_date,))
                rows = cur.fetchall()
            finally:
                conn.close()

            if len(rows) < 100:
                logger.warning(f"データ不足: {len(rows)}件 < 100件")
                return None

            # データ整理
            results = []
            for race_id, pred_result, umaban, chakujun in rows:
                if not pred_result:
                    continue
                try:
                    chakujun_int = int(chakujun) if chakujun.isdigit() else 99
                    if chakujun_int == 0:
                        continue
                    umaban_int = int(umaban) if umaban.isdigit() else 0
                    for horse in pred_result.get('ranked_horses', []):
                        if horse.get('horse_number') == umaban_int:
                            results.append({
                                'win_prob': horse.get('win_probability', 0),
                                'quinella_prob': horse.get('quinella_probability', 0),
                                'place_prob': horse.get('place_probability', 0),
                                'is_win': 1 if chakujun_int == 1 else 0,
                                'is_quinella': 1 if chakujun_int <= 2 else 0,
                                'is_place': 1 if chakujun_int <= 3 else 0,
                            })
                            break
                except (ValueError, TypeError):
                    continue

            if len(results) < 100:
                logger.warning(f"整理後データ不足: {len(results)}件")
                return None

            import pandas as pd
            df = pd.DataFrame(results)

            # キャリブレーター学習
            calibrators = {}
            stats = {}

            for target, col in [('win', 'is_win'), ('quinella', 'is_quinella'), ('place', 'is_place')]:
                X = df[f'{target}_prob'].values
                y = df[col].values
                iso = IsotonicRegression(out_of_bounds='clip')
                iso.fit(X, y)
                calibrators[target] = iso

                # 確率上限を計算（95パーセンタイルの実績値）
                high_prob_mask = X >= 0.3
                if high_prob_mask.sum() > 10:
                    max_prob = float(np.percentile(y[high_prob_mask], 95))
                else:
                    max_prob = float(y.mean() * 3)  # フォールバック

                stats[target] = {
                    'samples': len(df),
                    'actual_rate': float(y.mean()),
                    'calculated_max_prob': min(max_prob, 0.7),  # 上限70%
                }

            # 保存
            output_path = Path(__file__).parent.parent.parent / "models" / "calibration.pkl"
            backup_path = output_path.with_suffix('.backup.pkl')

            if output_path.exists():
                import shutil
                shutil.copy(output_path, backup_path)

            data = {
                'created_at': datetime.now().isoformat(),
                'calibrators': calibrators,
                'win_stats': stats.get('win', {}),
                'quinella_stats': stats.get('quinella', {}),
                'place_stats': stats.get('place', {}),
                'max_probs': {
                    'win': stats['win']['calculated_max_prob'],
                    'quinella': stats['quinella']['calculated_max_prob'],
                    'place': stats['place']['calculated_max_prob'],
                }
            }
            joblib.dump(data, output_path)
            logger.info(f"キャリブレーション保存: {output_path}")
            logger.info(f"  単勝上限: {data['max_probs']['win']*100:.1f}%")
            logger.info(f"  連対上限: {data['max_probs']['quinella']*100:.1f}%")
            logger.info(f"  複勝上限: {data['max_probs']['place']*100:.1f}%")

            return data

        except Exception as e:
            logger.error(f"キャリブレーション再学習失敗: {e}")
            return None

    def run_weekly_job(self, week_end: date = None, notify: bool = True):
        """週次ジョブを実行"""
        logger.info("=" * 50)
        logger.info(f"週次バックテスト開始: {datetime.now()}")
        logger.info("=" * 50)

        # 週次分析
        weekly_stats = self.run_weekly_analysis(week_end)

        if weekly_stats['total_races'] == 0:
            logger.info("分析対象レースなし")
            return

        # トラッキング更新
        tracking = self.update_tracking(weekly_stats)

        # キャリブレーション再学習
        logger.info("キャリブレーション再学習...")
        calibration_result = self.retrain_calibration(days_back=30)
        if calibration_result:
            logger.info("キャリブレーション更新完了")
        else:
            logger.info("キャリブレーション更新スキップ（データ不足）")

        # レポート生成
        report = self.generate_report(weekly_stats, tracking)
        print(report)

        # Discord通知
        if notify:
            self.send_discord_notification(report)

        # レポート保存
        report_path = self.analysis_dir / f"weekly_report_{weekly_stats['week_end'].replace('-', '')}.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"レポート保存: {report_path}")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="週次バックテスト")
    parser.add_argument("--date", "-d", help="週末日 (YYYY-MM-DD)")
    parser.add_argument("--no-notify", action="store_true", help="Discord通知しない")

    args = parser.parse_args()

    backtest = WeeklyBacktest()

    if args.date:
        week_end = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        week_end = None

    backtest.run_weekly_job(week_end, notify=not args.no_notify)


if __name__ == "__main__":
    main()
