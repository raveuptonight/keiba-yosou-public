"""
日次スケジューラ

毎日実行して：
1. 翌日の開催があるか確認
2. 出馬表データがあれば予想実行
3. 結果を保存・通知
"""

import logging
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from src.scheduler.race_predictor import RacePredictor, save_predictions, print_predictions
from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_race_schedule(target_date: date) -> bool:
    """指定日に開催があるか確認"""
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        kaisai_gappi = target_date.strftime("%m%d")
        kaisai_nen = str(target_date.year)

        cur.execute('''
            SELECT COUNT(*)
            FROM kaisai_schedule
            WHERE kaisai_nen = %s AND kaisai_gappi = %s
        ''', (kaisai_nen, kaisai_gappi))

        count = cur.fetchone()[0]
        cur.close()
        return count > 0

    finally:
        conn.close()


def check_entry_data(target_date: date) -> int:
    """指定日の出馬表データ件数を確認"""
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        kaisai_gappi = target_date.strftime("%m%d")
        kaisai_nen = str(target_date.year)

        # data_kubun: 3=枠順確定, 4=出馬表, 5=開催中, 6=確定前
        cur.execute('''
            SELECT COUNT(DISTINCT race_code)
            FROM race_shosai
            WHERE kaisai_nen = %s
              AND kaisai_gappi = %s
              AND data_kubun IN ('3', '4', '5', '6')
        ''', (kaisai_nen, kaisai_gappi))

        count = cur.fetchone()[0]
        cur.close()
        return count

    finally:
        conn.close()


def send_discord_notification(results: dict, webhook_url: Optional[str] = None):
    """Discord通知を送信"""
    if not webhook_url:
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')

    if not webhook_url:
        logger.info("Discord Webhook URLが設定されていません")
        return

    try:
        import requests

        # メッセージ作成
        if results['status'] == 'no_data':
            content = f"📅 {results['date']}\n出馬表データがまだありません"
        else:
            lines = [f"🏇 **{results['date']} レース予想**\n"]

            for race in results['races'][:10]:  # 最大10レース
                lines.append(f"\n**{race['keibajo']} {race['race_number']}R** ({race['kyori']}m)")
                for p in race['top3']:
                    medal = ['🥇', '🥈', '🥉'][p['rank'] - 1]
                    lines.append(f"{medal} {p['umaban']}番 {p['bamei']}")

            content = "\n".join(lines)

        # 送信
        payload = {"content": content}
        response = requests.post(webhook_url, json=payload, timeout=10)

        if response.status_code == 204:
            logger.info("Discord通知送信完了")
        else:
            logger.warning(f"Discord通知失敗: {response.status_code}")

    except Exception as e:
        logger.error(f"Discord通知エラー: {e}")


def run_daily_job(days_ahead: int = 1):
    """日次ジョブ実行"""
    target_date = date.today() + timedelta(days=days_ahead)

    logger.info("=" * 50)
    logger.info(f"日次スケジューラ実行: {datetime.now()}")
    logger.info(f"対象日: {target_date}")
    logger.info("=" * 50)

    # 1. 開催スケジュール確認
    has_schedule = check_race_schedule(target_date)
    if not has_schedule:
        logger.info(f"{target_date}は開催予定なし")
        return

    logger.info(f"{target_date}は開催予定あり")

    # 2. 出馬表データ確認
    race_count = check_entry_data(target_date)
    if race_count == 0:
        logger.info(f"{target_date}の出馬表データなし（まだ登録されていない可能性）")
        return

    logger.info(f"{target_date}の出馬表: {race_count}レース")

    # 3. 予想実行
    try:
        predictor = RacePredictor()
        results = predictor.run_predictions(target_date)

        # 結果表示
        print_predictions(results)

        # 結果保存
        if results['status'] == 'success' and results['races']:
            save_predictions(results)

            # Discord通知
            send_discord_notification(results)

    except Exception as e:
        logger.error(f"予想実行エラー: {e}")
        raise


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="日次スケジューラ")
    parser.add_argument("--days", "-d", type=int, default=1, help="何日後のレースを予想するか")
    parser.add_argument("--check-only", action="store_true", help="データ確認のみ")

    args = parser.parse_args()

    if args.check_only:
        target_date = date.today() + timedelta(days=args.days)
        print(f"対象日: {target_date}")
        print(f"開催予定: {'あり' if check_race_schedule(target_date) else 'なし'}")
        print(f"出馬表データ: {check_entry_data(target_date)}レース")
    else:
        run_daily_job(args.days)


if __name__ == "__main__":
    main()
