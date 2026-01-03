#!/usr/bin/env python3
"""
予想実行＆Discord通知スクリプト

明日のレース予想を実行し、Discord通知チャンネルに結果を送信
"""

import asyncio
import os
import sys
import requests
import discord
from datetime import date, timedelta
from typing import List, Dict, Any
import logging

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 設定
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_NOTIFICATION_CHANNEL_ID = int(os.getenv("DISCORD_NOTIFICATION_CHANNEL_ID", "0"))


def get_races_for_date(target_date: date) -> List[Dict[str, Any]]:
    """指定日のレース一覧を取得"""
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


def generate_prediction(race_id: str) -> Dict[str, Any]:
    """予想を生成"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/predictions/generate",
            json={"race_id": race_id},
            timeout=120
        )
        if response.status_code in (200, 201):
            return response.json()
        else:
            logger.error(f"予想失敗: race_id={race_id}, status={response.status_code}")
            return None
    except Exception as e:
        logger.error(f"予想エラー: race_id={race_id}, error={e}")
        return None


def format_prediction_message(predictions: List[Dict[str, Any]], target_date: date) -> str:
    """予想結果をDiscordメッセージにフォーマット"""
    lines = [
        f"🏇 **{target_date.strftime('%Y年%m月%d日')} レース予想**",
        f"━━━━━━━━━━━━━━━━━━",
        f"予想レース数: {len(predictions)}件",
        ""
    ]

    # グレード順にソート
    grade_priority = {"G1": 0, "G2": 1, "G3": 2, "L": 3, "OP": 4}
    sorted_preds = sorted(
        predictions,
        key=lambda p: (
            grade_priority.get(p.get("prediction_result", {}).get("model_info", "").split()[0] if p.get("prediction_result") else "", 99),
            p.get("venue", ""),
            int(p.get("race_number", "0R").replace("R", "").replace("?", "0") or 0)
        )
    )

    for pred in sorted_preds:
        venue = pred.get("venue", "?")
        race_num = pred.get("race_number", "?")
        race_name = pred.get("race_name", "")[:20]
        result = pred.get("prediction_result", {})
        ranked = result.get("ranked_horses", [])[:3]

        # グレード表示
        grade = ""
        for horse in ranked:
            if horse.get("rank") == 1:
                break

        lines.append(f"**{venue} {race_num}** {race_name}")

        medals = ['🥇', '🥈', '🥉']
        for i, horse in enumerate(ranked[:3]):
            medal = medals[i]
            horse_num = horse.get("horse_number", "?")
            horse_name = horse.get("horse_name", "?")[:8]
            win_prob = horse.get("win_probability", 0)
            lines.append(f"  {medal} {horse_num}番 {horse_name} (勝率{win_prob:.1%})")

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("※ ML予想（XGBoost + LightGBM アンサンブル）")

    return "\n".join(lines)


def send_discord_message(message: str) -> bool:
    """Discord REST APIでメッセージを送信"""
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN が設定されていません")
        return False

    if not DISCORD_NOTIFICATION_CHANNEL_ID:
        logger.error("DISCORD_NOTIFICATION_CHANNEL_ID が設定されていません")
        return False

    url = f"https://discord.com/api/v10/channels/{DISCORD_NOTIFICATION_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    # メッセージを2000文字以下に分割
    messages = []
    current = ""
    for line in message.split("\n"):
        if len(current) + len(line) + 1 > 1900:
            messages.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        messages.append(current)

    success = True
    for msg in messages:
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"content": msg},
                timeout=10
            )
            if response.status_code in (200, 201):
                logger.info(f"Discord送信成功")
            else:
                logger.error(f"Discord送信失敗: {response.status_code} - {response.text}")
                success = False
            import time
            time.sleep(1)  # レート制限対策
        except Exception as e:
            logger.error(f"Discord送信エラー: {e}")
            success = False

    return success


async def main():
    """メイン処理"""
    # 明日のレースを対象
    target_date = date.today() + timedelta(days=1)

    logger.info("=" * 50)
    logger.info(f"予想実行＆Discord通知")
    logger.info(f"対象日: {target_date}")
    logger.info("=" * 50)

    # 1. レース一覧を取得
    races = get_races_for_date(target_date)

    if not races:
        logger.info(f"{target_date}はレースなし")
        return

    logger.info(f"対象レース: {len(races)}件")

    # 2. 各レースの予想を実行
    predictions = []
    for race in races:
        race_id = race.get("race_id")
        venue = race.get("venue", "?")
        race_num = race.get("race_number", "?")

        logger.info(f"予想中: {venue} {race_num} ({race_id})")

        result = generate_prediction(race_id)
        if result:
            predictions.append(result)
            logger.info(f"  → 成功")
        else:
            logger.warning(f"  → 失敗")

    logger.info(f"予想完了: {len(predictions)}/{len(races)}件")

    if not predictions:
        logger.warning("予想結果がありません")
        return

    # 3. メッセージをフォーマット
    message = format_prediction_message(predictions, target_date)
    print("\n" + message + "\n")

    # 4. Discord通知
    logger.info("Discord通知送信中...")
    await send_discord_notification(message)

    logger.info("完了！")


if __name__ == "__main__":
    asyncio.run(main())
