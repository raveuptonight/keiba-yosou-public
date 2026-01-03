"""
日次スケジューラ

毎日実行して：
1. 翌日の開催があるか確認
2. API経由で予想実行
3. 結果を通知
"""

import logging
import os
import requests
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API設定
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = 120  # 予想には時間がかかる場合がある


def get_races_for_date(target_date: date) -> List[Dict[str, Any]]:
    """指定日のレース一覧をAPIから取得"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/races/date/{target_date.isoformat()}",
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("races", [])
        else:
            logger.error(f"レース一覧取得失敗: status={response.status_code}")
            return []
    except Exception as e:
        logger.error(f"レース一覧取得エラー: {e}")
        return []


def execute_prediction(race_id: str) -> Optional[Dict[str, Any]]:
    """API経由で予想を実行"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/predictions/generate",
            json={"race_id": race_id},
            timeout=API_TIMEOUT
        )
        if response.status_code in (200, 201):
            return response.json()
        else:
            logger.error(f"予想失敗: race_id={race_id}, status={response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"予想タイムアウト: race_id={race_id}")
        return None
    except Exception as e:
        logger.error(f"予想エラー: race_id={race_id}, error={e}")
        return None


def send_discord_notification(
    target_date: date,
    predictions: List[Dict[str, Any]],
    webhook_url: Optional[str] = None
):
    """Discord通知を送信"""
    if not webhook_url:
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')

    if not webhook_url:
        logger.info("Discord Webhook URLが設定されていません")
        return

    try:
        if not predictions:
            content = f"📅 {target_date}\n予想データがありません"
        else:
            lines = [f"🏇 **{target_date} レース予想完了**\n"]
            lines.append(f"予想レース数: {len(predictions)}件\n")

            # 重賞・OPを優先して表示
            grade_priority = {"G1": 0, "G2": 1, "G3": 2, "L": 3, "OP": 4}
            sorted_preds = sorted(
                predictions,
                key=lambda p: (
                    grade_priority.get(p.get("prediction_result", {}).get("grade"), 99),
                    p.get("venue", ""),
                    p.get("race_number", "")
                )
            )

            for pred in sorted_preds[:10]:  # 最大10レース
                venue = pred.get("venue", "?")
                race_num = pred.get("race_number", "?")
                race_name = pred.get("race_name", "")[:15]
                result = pred.get("prediction_result", {})
                ranked = result.get("ranked_horses", [])[:3]

                lines.append(f"\n**{venue} {race_num}R** {race_name}")
                for i, h in enumerate(ranked):
                    medal = ['🥇', '🥈', '🥉'][i]
                    lines.append(
                        f"{medal} {h.get('horse_number', '?')}番 {h.get('horse_name', '?')[:8]} "
                        f"(単{h.get('win_probability', 0):.1%})"
                    )

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

    # 1. レース一覧を取得
    races = get_races_for_date(target_date)

    if not races:
        logger.info(f"{target_date}はレースなし、または取得失敗")
        return

    logger.info(f"{target_date}のレース: {len(races)}件")

    # 2. 各レースの予想を実行
    predictions = []
    for race in races:
        race_id = race.get("race_id")
        venue = race.get("venue", "?")
        race_num = race.get("race_number", "?")

        logger.info(f"予想中: {venue} {race_num} (race_id={race_id})")

        result = execute_prediction(race_id)
        if result:
            predictions.append(result)
            logger.info(f"  → 成功")
        else:
            logger.warning(f"  → 失敗")

    logger.info(f"予想完了: {len(predictions)}/{len(races)}件")

    # 3. Discord通知
    if predictions:
        send_discord_notification(target_date, predictions)

    # 4. 結果サマリー
    print("\n" + "=" * 50)
    print(f"【{target_date} 予想結果サマリー】")
    print(f"成功: {len(predictions)}/{len(races)}件")
    print("=" * 50)

    for pred in predictions:
        venue = pred.get("venue", "?")
        race_num = pred.get("race_number", "?")
        race_name = pred.get("race_name", "")[:20]
        result = pred.get("prediction_result", {})
        ranked = result.get("ranked_horses", [])[:3]

        print(f"\n{venue} {race_num}R {race_name}")
        for h in ranked:
            print(f"  {h.get('rank')}位: {h.get('horse_number')}番 {h.get('horse_name')} "
                  f"(単勝{h.get('win_probability', 0):.1%})")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="日次スケジューラ（API経由）")
    parser.add_argument("--days", "-d", type=int, default=1, help="何日後のレースを予想するか")
    parser.add_argument("--check-only", action="store_true", help="レース確認のみ")

    args = parser.parse_args()

    if args.check_only:
        target_date = date.today() + timedelta(days=args.days)
        races = get_races_for_date(target_date)
        print(f"対象日: {target_date}")
        print(f"レース数: {len(races)}件")
        for r in races:
            grade = f"[{r.get('grade')}]" if r.get('grade') else ""
            print(f"  {r.get('venue')} {r.get('race_number')} {r.get('race_name', '')[:20]} {grade}")
    else:
        run_daily_job(args.days)


if __name__ == "__main__":
    main()
