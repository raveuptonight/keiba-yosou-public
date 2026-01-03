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


def _format_track(track_code: str, distance: int) -> str:
    """トラックコードと距離をフォーマット"""
    if track_code and track_code.startswith("1"):
        return f"芝{distance}m"
    elif track_code and track_code.startswith("2"):
        return f"ダ{distance}m"
    return f"{distance}m"


def _format_race_number(race_num: str) -> str:
    """レース番号をフォーマット（"01" -> "1R", "11R" -> "11R"）"""
    if not race_num or race_num == "?":
        return "?R"
    # 既に "R" が付いている場合はそのまま
    if race_num.upper().endswith("R"):
        return race_num
    # 数字のみの場合は先頭のゼロを除去して"R"を付ける
    try:
        num = int(race_num)
        return f"{num}R"
    except ValueError:
        return f"{race_num}R"


def _format_race_header(pred: Dict[str, Any], races_info: Dict[str, Dict]) -> str:
    """レースヘッダーをフォーマット（例: 中山1R 09:55発走 3歳未勝利 芝1200m 16頭）"""
    venue = pred.get("venue", "?")
    race_num_raw = pred.get("race_number", "?")
    race_num = _format_race_number(race_num_raw)
    race_time = pred.get("race_time", "")
    race_name = pred.get("race_name", "")
    race_id = pred.get("race_id", "")
    result = pred.get("prediction_result", {})
    ranked = result.get("ranked_horses", [])
    entry_count = len(ranked)

    # レース情報から距離・トラック取得
    race_info = races_info.get(race_id, {})
    distance = race_info.get("distance", 0)
    track_code = race_info.get("track_code", "")
    track_str = _format_track(track_code, distance) if distance else ""

    # 発走時刻フォーマット（HHMM -> HH:MM）
    time_str = ""
    if race_time and len(race_time) >= 4:
        time_str = f"{race_time[:2]}:{race_time[2:4]}発走"

    # ヘッダー構築
    parts = [f"**{venue} {race_num}**"]
    if time_str:
        parts.append(time_str)
    if race_name:
        parts.append(race_name[:20])
    if track_str:
        parts.append(track_str)
    if entry_count:
        parts.append(f"{entry_count}頭")

    return " ".join(parts)


def send_discord_notification(
    target_date: date,
    predictions: List[Dict[str, Any]],
    races_info: Dict[str, Dict] = None
):
    """Discord Bot経由で通知を送信（インタラクティブ形式）"""
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

    if not bot_token:
        logger.warning("DISCORD_BOT_TOKEN が設定されていません")
        return

    if not channel_id:
        logger.warning("DISCORD_NOTIFICATION_CHANNEL_ID が設定されていません")
        return

    if races_info is None:
        races_info = {}

    # Discord REST API設定
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }

    try:
        if not predictions:
            content = f"📅 {target_date}\n予想データがありません"
            requests.post(url, headers=headers, json={"content": content}, timeout=10)
            return

        # 重賞・OPを優先してソート
        grade_priority = {"G1": 0, "G2": 1, "G3": 2, "L": 3, "OP": 4}
        sorted_preds = sorted(
            predictions,
            key=lambda p: (
                grade_priority.get(p.get("prediction_result", {}).get("grade"), 99),
                p.get("venue", ""),
                int(p.get("race_number", "0R").replace("R", "").replace("?", "0") or 0)
            )
        )

        # レースリスト作成
        lines = [f"🏇 **{target_date} レース予想完了** ({len(predictions)}レース)\n"]
        lines.append("▼ 詳細を見たいレースをドロップダウンから選択してください\n")
        lines.append("━━━━━━━━━━━━━━━━")

        for pred in sorted_preds:
            result = pred.get("prediction_result", {})
            ranked = result.get("ranked_horses", [])

            # レースヘッダー（詳細形式）
            header = _format_race_header(pred, races_info)

            # 本命馬を簡潔に表示
            honmei = ""
            if ranked:
                top = ranked[0]
                honmei = f"→ {top.get('horse_number', '?')}番 {top.get('horse_name', '')}"

            lines.append(f"{header} {honmei}")

        content = "\n".join(lines)

        # Selectメニュー用オプション作成（最大25個）
        options = []
        for i, pred in enumerate(sorted_preds[:25]):
            venue = pred.get("venue", "?")
            race_num = pred.get("race_number", "?")
            race_name = pred.get("race_name", "")
            race_time = pred.get("race_time", "")
            race_id = pred.get("race_id", f"race_{i}")

            # レース情報から距離・トラック取得
            race_info = races_info.get(race_id, {})
            distance = race_info.get("distance", 0)
            track_code = race_info.get("track_code", "")
            track_str = _format_track(track_code, distance) if distance else ""

            # 発走時刻フォーマット
            time_str = ""
            if race_time and len(race_time) >= 4:
                time_str = f"{race_time[:2]}:{race_time[2:]}"

            # ラベル構築（最大100文字）
            race_num_formatted = _format_race_number(race_num)
            label_parts = [f"{venue} {race_num_formatted}"]
            if time_str:
                label_parts.append(time_str)
            if race_name:
                label_parts.append(race_name[:30])
            label = " ".join(label_parts)[:100]

            # 説明（最大100文字）
            desc_parts = []
            if track_str:
                desc_parts.append(track_str)
            desc_parts.append("詳細予想を表示")
            description = " / ".join(desc_parts)[:100]

            options.append({
                "label": label,
                "value": race_id,
                "description": description
            })

        # Selectコンポーネント付きメッセージ送信
        payload = {
            "content": content,
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 3,  # Select Menu
                            "custom_id": "prediction_select",
                            "placeholder": "レースを選択して詳細を見る",
                            "options": options
                        }
                    ]
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info(f"Discord通知送信成功: {len(predictions)}レース")
        else:
            logger.warning(f"Discord通知失敗: {response.status_code} - {response.text[:200]}")

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

    # レース情報をマップに格納（通知用）
    races_info = {}
    for race in races:
        race_id = race.get("race_id")
        races_info[race_id] = {
            "distance": race.get("distance", 0),
            "track_code": race.get("track_code", ""),
            "grade": race.get("grade"),
        }

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
        send_discord_notification(target_date, predictions, races_info)

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
            jockey = h.get('jockey_name', '')[:6] if h.get('jockey_name') else ''
            jockey_str = f" [{jockey}]" if jockey else ""
            print(f"  {h.get('rank')}位: {h.get('horse_number')}番 {h.get('horse_name')}{jockey_str} "
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
