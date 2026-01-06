"""
日次スケジューラ

毎日21時に実行：
1. 当日レースがあったか確認 → あればバイアス分析・保存
2. 翌日レースがあるか確認 → あれば予想実行
3. 予想時のバイアス選択：
   - 当週のバイアスがあれば使用
   - なければ前週最後の開催日のバイアスを使用

週の定義: 土曜始まり（競馬開催の基本単位）
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


def execute_prediction(race_id: str, bias_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """API経由で予想を実行

    Args:
        race_id: レースID
        bias_date: バイアス適用日（YYYY-MM-DD形式）
    """
    try:
        payload = {"race_id": race_id}
        if bias_date:
            payload["bias_date"] = bias_date

        response = requests.post(
            f"{API_BASE_URL}/api/v1/predictions/generate",
            json=payload,
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


def run_saturday_bias_analysis() -> bool:
    """
    土曜日のレース結果からバイアス分析を実行

    Returns:
        True: バイアス分析成功
        False: 失敗または対象レースなし
    """
    import importlib.util
    from pathlib import Path
    # パッケージ経由のインポートを回避（直接モジュールロード）
    module_path = Path(__file__).parent.parent / "features" / "daily_bias.py"
    spec = importlib.util.spec_from_file_location("daily_bias", module_path)
    daily_bias = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(daily_bias)
    DailyBiasAnalyzer = daily_bias.DailyBiasAnalyzer
    print_bias_report = daily_bias.print_bias_report

    target_date = date.today()

    logger.info("=" * 50)
    logger.info(f"土曜バイアス分析開始: {target_date}")
    logger.info("=" * 50)

    try:
        analyzer = DailyBiasAnalyzer()
        result = analyzer.analyze(target_date)

        if not result:
            logger.warning(f"バイアス分析対象レースなし: {target_date}")
            return False

        # 分析結果を保存
        output_path = analyzer.save_bias(result)
        logger.info(f"バイアス結果保存: {output_path}")

        # レポート表示
        print_bias_report(result)

        # Discord通知（簡易版）
        _send_bias_notification(result)

        return True

    except Exception as e:
        logger.error(f"土曜バイアス分析エラー: {e}")
        return False


def _send_bias_notification(bias_result):
    """バイアス分析結果をDiscord通知"""
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

    if not bot_token or not channel_id:
        return

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }

    lines = [f"📊 **{bias_result.target_date} 土曜バイアス分析完了**\n"]
    lines.append(f"分析レース数: {bias_result.total_races}\n")

    for venue_code, vb in sorted(bias_result.venue_biases.items()):
        waku_indicator = "内枠有利" if vb.waku_bias > 0.05 else ("外枠有利" if vb.waku_bias < -0.05 else "中立")
        pace_indicator = "前有利" if vb.pace_bias > 0.05 else ("後有利" if vb.pace_bias < -0.05 else "中立")
        lines.append(f"**{vb.venue_name}** ({vb.race_count}R): 枠順→{waku_indicator}, 脚質→{pace_indicator}")

    lines.append("\n✨ 日曜予想にバイアスを反映します")

    try:
        requests.post(url, headers=headers, json={"content": "\n".join(lines)}, timeout=10)
        logger.info("バイアス分析Discord通知送信完了")
    except Exception as e:
        logger.error(f"Discord通知エラー: {e}")


def check_races_today() -> bool:
    """
    当日レースがあったかDBから確認

    Returns:
        True: レースあり, False: レースなし
    """
    from src.db.connection import get_db

    target_date = date.today()
    kaisai_nen = str(target_date.year)
    kaisai_gappi = target_date.strftime("%m%d")

    try:
        db = get_db()
        conn = db.get_connection()
        cur = conn.cursor()

        # 確定または速報データがあるかチェック
        cur.execute('''
            SELECT COUNT(*) FROM race_shosai
            WHERE kaisai_nen = %s
              AND kaisai_gappi = %s
              AND data_kubun IN ('6', '7')
        ''', (kaisai_nen, kaisai_gappi))

        count = cur.fetchone()[0]
        cur.close()
        conn.close()

        logger.info(f"当日レース確認: {target_date} → {count}レース")
        return count > 0

    except Exception as e:
        logger.error(f"当日レース確認エラー: {e}")
        return False


def find_latest_bias(target_date: date) -> Optional[str]:
    """
    適切なバイアスをDBから検索

    今週のバイアスのみ検索（土曜始まり）
    - 土曜の傾向 → 日曜に反映
    - 週をまたいだ傾向反映は行わない

    Args:
        target_date: 予想対象日

    Returns:
        バイアスの日付（YYYY-MM-DD）、見つからなければNone
    """
    from src.db.connection import get_db

    # 今週の土曜日を計算（土曜始まり）
    # weekday(): 月=0, 火=1, 水=2, 木=3, 金=4, 土=5, 日=6
    days_since_saturday = (target_date.weekday() - 5) % 7
    this_week_saturday = target_date - timedelta(days=days_since_saturday)

    logger.info(f"バイアス検索: 対象日={target_date}, 今週土曜={this_week_saturday}")

    try:
        db = get_db()
        conn = db.get_connection()
        if not conn:
            logger.error("DB接続失敗")
            return None

        cur = conn.cursor()

        # 今週のバイアスをDBから検索（今週土曜から予想対象日の前日まで）
        cur.execute('''
            SELECT target_date
            FROM daily_bias
            WHERE target_date >= %s AND target_date < %s
            ORDER BY target_date DESC
            LIMIT 1
        ''', (this_week_saturday.isoformat(), target_date.isoformat()))

        row = cur.fetchone()
        conn.close()

        if row:
            bias_date = str(row[0])
            logger.info(f"今週のバイアス発見: {bias_date}")
            return bias_date

        logger.info(f"今週のバイアスなし → 通常予想")
        return None

    except Exception as e:
        logger.error(f"バイアス検索エラー: {e}")
        return None


def set_bias_for_prediction(bias_date: str):
    """
    予想で使用するバイアス日付を環境変数に設定

    Args:
        bias_date: バイアスファイルの日付（YYYY-MM-DD）
    """
    os.environ['KEIBA_BIAS_DATE'] = bias_date
    logger.info(f"バイアス設定: KEIBA_BIAS_DATE={bias_date}")


def run_result_analysis():
    """
    当日のレース結果を分析・通知

    Returns:
        True: 分析成功, False: データなし/エラー
    """
    from src.scheduler.result_collector import ResultCollector
    from pathlib import Path

    today = date.today()
    logger.info(f"結果分析開始: {today}")

    try:
        collector = ResultCollector()
        analysis = collector.collect_and_analyze(today)

        if analysis['status'] == 'success':
            collector.save_analysis_to_db(analysis)
            collector.send_discord_notification(analysis)

            acc = analysis['accuracy']
            logger.info(f"結果分析完了: {acc['analyzed_races']}R")
            logger.info(f"  単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
            logger.info(f"  Top3カバー率: {acc['accuracy']['top3_cover_rate']:.1f}%")
            logger.info(f"  MRR: {acc['accuracy']['mrr']:.3f}")
            return True
        else:
            logger.info(f"結果分析: {analysis['status']}")
            return False

    except Exception as e:
        logger.error(f"結果分析エラー: {e}")
        return False


def run_nightly_job():
    """
    毎晩21時の統合ジョブ

    1. 当日レースがあったか確認 → あれば結果分析・通知 + バイアス分析
    2. 翌日レースがあるか確認 → あれば予想実行（バイアス反映）
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)

    logger.info("=" * 60)
    logger.info(f"【21時統合ジョブ開始】 {datetime.now()}")
    logger.info(f"  当日: {today} ({['月','火','水','木','金','土','日'][today.weekday()]})")
    logger.info(f"  翌日: {tomorrow} ({['月','火','水','木','金','土','日'][tomorrow.weekday()]})")
    logger.info("=" * 60)

    # 1. 当日レースがあったか確認
    if check_races_today():
        logger.info("当日レースあり")

        # 1a. 結果分析・通知
        logger.info("→ 結果分析実行")
        run_result_analysis()

        # 1b. バイアス分析
        logger.info("→ バイアス分析実行")
        run_saturday_bias_analysis()
    else:
        logger.info("当日レースなし → 分析スキップ")

    # 2. 翌日レースがあるか確認
    tomorrow_races = get_races_for_date(tomorrow)
    if not tomorrow_races:
        logger.info(f"翌日({tomorrow})はレースなし → 予想スキップ")
        return

    logger.info(f"翌日レースあり: {len(tomorrow_races)}レース → 予想実行")

    # 3. バイアス検索と設定
    bias_date = find_latest_bias(tomorrow)
    if bias_date:
        logger.info(f"バイアス適用: {bias_date} のデータを使用")
    else:
        logger.warning("適用可能なバイアスなし → 通常予想")

    # 4. 予想実行（バイアス日をAPIに渡す）
    run_daily_job(days_ahead=1, bias_date=bias_date)


def run_sunday_prediction_with_bias():
    """
    後方互換性のため残す（run_nightly_jobを呼び出し）
    """
    run_nightly_job()


def run_daily_job(days_ahead: int = 1, bias_date: Optional[str] = None):
    """日次ジョブ実行

    Args:
        days_ahead: 何日先のレースを予想するか
        bias_date: バイアス適用日（YYYY-MM-DD形式）
    """
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

        result = execute_prediction(race_id, bias_date=bias_date)
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
    parser.add_argument("--nightly", action="store_true",
                        help="21時統合ジョブ: 結果分析 + バイアス分析 + 翌日予想（推奨）")
    parser.add_argument("--sunday-with-bias", action="store_true",
                        help="（非推奨）--nightlyを使用してください")
    parser.add_argument("--bias-only", action="store_true",
                        help="バイアス分析のみ実行（当日レース対象）")
    parser.add_argument("--result-only", action="store_true",
                        help="結果分析のみ実行（当日レース対象）")

    args = parser.parse_args()

    if args.nightly or args.sunday_with_bias:
        # 21時統合ジョブ
        run_nightly_job()
    elif args.result_only:
        # 結果分析のみ
        run_result_analysis()
    elif args.bias_only:
        # バイアス分析のみ
        run_saturday_bias_analysis()
    elif args.check_only:
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
