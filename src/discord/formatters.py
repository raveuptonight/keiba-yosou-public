"""
Discord通知フォーマッター

予想完了通知、的中報告などのメッセージをフォーマット
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List

# ロガー設定
logger = logging.getLogger(__name__)


def format_prediction_notification(
    race_name: str,
    race_date: date,
    venue: str,
    race_time: str,
    race_number: str,
    prediction_result: Dict[str, Any],
    total_investment: int,
    expected_return: int,
    expected_roi: float,
    prediction_url: Optional[str] = None,
) -> str:
    """
    予想完了通知をフォーマット

    Args:
        race_name: レース名
        race_date: レース日
        venue: 競馬場
        race_time: レース時刻
        race_number: レース番号
        prediction_result: 予想結果（JSON）
        total_investment: 総投資額
        expected_return: 期待回収額
        expected_roi: 期待ROI
        prediction_url: 予想詳細URL（オプション）

    Returns:
        フォーマット済みメッセージ
    """
    try:
        # 日付フォーマット（2024/12/28 (日)）
        weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
        weekday = weekday_names[race_date.weekday()]
        date_str = f"{race_date.strftime('%Y/%m/%d')} ({weekday})"

        # 予想結果から本命・対抗・穴馬を取得
        win_pred = prediction_result.get("win_prediction", {})
        honmei = win_pred.get("first", {})
        taikou = win_pred.get("second", {})
        ana = win_pred.get("third", {})

        # 推奨馬券を取得
        betting = prediction_result.get("betting_strategy", {})
        tickets = betting.get("recommended_tickets", [])

        # メッセージ構築
        lines = [
            f"🏇 【予想完了】{race_name}",
            "",
            f"📅 {date_str} {race_time} {venue}{race_number}",
            "",
        ]

        # 本命・対抗・穴馬
        if honmei:
            lines.append(
                f"◎本命: {honmei.get('horse_number', '?')}番 {honmei.get('horse_name', '不明')}"
            )
        if taikou:
            lines.append(
                f"○対抗: {taikou.get('horse_number', '?')}番 {taikou.get('horse_name', '不明')}"
            )
        if ana:
            lines.append(
                f"▲単穴: {ana.get('horse_number', '?')}番 {ana.get('horse_name', '不明')}"
            )

        # 推奨馬券
        if tickets:
            lines.append("")
            lines.append("💰 推奨馬券")
            for ticket in tickets[:3]:  # 最大3つまで表示
                ticket_type = ticket.get("ticket_type", "不明")
                numbers = ticket.get("numbers", [])
                amount = ticket.get("amount", 0)
                if isinstance(numbers, list):
                    numbers_str = "-".join(map(str, numbers))
                else:
                    numbers_str = str(numbers)
                lines.append(f"・{ticket_type} [{numbers_str}] {amount:,}円")

        # 投資額・期待回収
        lines.append("")
        lines.append(f"投資額: {total_investment:,}円")
        lines.append(f"期待回収: {expected_return:,}円")
        lines.append(f"期待ROI: {expected_roi:.1f}%")

        # 詳細URL
        if prediction_url:
            lines.append("")
            lines.append(f"📊 詳細: {prediction_url}")

        message = "\n".join(lines)
        logger.debug(f"予想通知フォーマット完了: race_name={race_name}, lines={len(lines)}")
        return message

    except Exception as e:
        logger.error(f"予想通知フォーマットエラー: {e}")
        return f"🏇 【予想完了】{race_name}\n\n❌ フォーマットエラーが発生しました"


def format_result_notification(
    race_name: str,
    hit: bool,
    actual_result: Dict[str, Any],
    total_return: int,
    total_investment: int,
    actual_roi: float,
    monthly_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """
    レース結果報告をフォーマット

    Args:
        race_name: レース名
        hit: 的中フラグ
        actual_result: 実際の結果
        total_return: 総回収額
        total_investment: 総投資額
        actual_roi: 実際のROI
        monthly_stats: 今月の統計（オプション）

    Returns:
        フォーマット済みメッセージ
    """
    try:
        if hit:
            emoji = "🎉"
            title = f"{emoji} 【的中！】{race_name}"
        else:
            emoji = "📊"
            title = f"{emoji} 【結果】{race_name}"

        lines = [title, ""]

        # 的中した馬券を表示
        if hit:
            hit_tickets = actual_result.get("hit_tickets", [])
            for ticket in hit_tickets:
                ticket_type = ticket.get("ticket_type", "不明")
                numbers = ticket.get("numbers", [])
                payout = ticket.get("payout", 0)
                if isinstance(numbers, list):
                    numbers_str = "-".join(map(str, numbers))
                else:
                    numbers_str = str(numbers)
                lines.append(f"{ticket_type} [{numbers_str}] 的中！")
                lines.append(f"払戻: {payout:,}円")
            lines.append("")

        # 収支
        profit = total_return - total_investment
        lines.append(f"投資: {total_investment:,}円")
        lines.append(f"回収: {total_return:,}円")
        if profit > 0:
            lines.append(f"利益: +{profit:,}円 💰")
        elif profit < 0:
            lines.append(f"損失: {profit:,}円")
        else:
            lines.append(f"収支: ±0円")
        lines.append(f"ROI: {actual_roi:.1f}%")

        # 今月の成績
        if monthly_stats:
            lines.append("")
            lines.append("今月の成績:")
            hit_count = monthly_stats.get("hit_count", 0)
            total_races = monthly_stats.get("total_races", 0)
            hit_rate = monthly_stats.get("hit_rate", 0.0)
            roi = monthly_stats.get("roi", 0.0)

            lines.append(f"的中率: {hit_rate*100:.1f}% ({hit_count}/{total_races})")
            lines.append(f"回収率: {roi:.1f}%")

            # 目標達成状況
            if roi >= 200.0:
                lines.append("✅ 目標達成！（回収率200%以上）")
            else:
                remaining = 200.0 - roi
                lines.append(f"目標まであと: +{remaining:.1f}%")

        message = "\n".join(lines)
        logger.debug(f"結果通知フォーマット完了: race_name={race_name}, hit={hit}")
        return message

    except Exception as e:
        logger.error(f"結果通知フォーマットエラー: {e}")
        return f"📊 【結果】{race_name}\n\n❌ フォーマットエラーが発生しました"


def format_stats_message(stats: Dict[str, Any]) -> str:
    """
    統計情報をフォーマット

    Args:
        stats: 統計データ

    Returns:
        フォーマット済みメッセージ
    """
    try:
        period = stats.get("period", "all")
        period_names = {
            "daily": "本日",
            "weekly": "今週",
            "monthly": "今月",
            "all": "全期間",
        }
        period_str = period_names.get(period, period)

        total_races = stats.get("total_races", 0)
        total_investment = stats.get("total_investment", 0)
        total_return = stats.get("total_return", 0)
        total_profit = stats.get("total_profit", 0)
        roi = stats.get("roi", 0.0)
        hit_count = stats.get("hit_count", 0)
        hit_rate = stats.get("hit_rate", 0.0)
        best_roi = stats.get("best_roi", 0.0)
        worst_roi = stats.get("worst_roi", 0.0)

        lines = [
            f"📊 【統計情報】{period_str}",
            "",
            f"レース数: {total_races}",
            f"投資額: {total_investment:,}円",
            f"回収額: {total_return:,}円",
        ]

        if total_profit > 0:
            lines.append(f"収支: +{total_profit:,}円 💰")
        elif total_profit < 0:
            lines.append(f"収支: {total_profit:,}円")
        else:
            lines.append(f"収支: ±0円")

        lines.append("")
        lines.append(f"回収率: {roi:.1f}%")
        lines.append(f"的中率: {hit_rate*100:.1f}% ({hit_count}/{total_races})")
        lines.append("")
        lines.append(f"最高ROI: {best_roi:.1f}%")
        lines.append(f"最低ROI: {worst_roi:.1f}%")

        # 目標達成状況
        lines.append("")
        if roi >= 200.0:
            lines.append("✅ 目標達成！（回収率200%以上）")
        else:
            remaining = 200.0 - roi
            lines.append(f"🎯 目標: 回収率200%")
            lines.append(f"現在: {roi:.1f}% (あと+{remaining:.1f}%)")

        message = "\n".join(lines)
        logger.debug(f"統計情報フォーマット完了: period={period}, total_races={total_races}")
        return message

    except Exception as e:
        logger.error(f"統計情報フォーマットエラー: {e}")
        return "📊 【統計情報】\n\n❌ フォーマットエラーが発生しました"


def format_race_list(races: List[Dict[str, Any]]) -> str:
    """
    レース一覧をフォーマット

    Args:
        races: レースリスト

    Returns:
        フォーマット済みメッセージ
    """
    try:
        if not races:
            logger.debug("レース一覧が空")
            return "📅 本日のレースはありません"

        lines = ["📅 本日のレース一覧", ""]

        for race in races:
            race_id = race.get("race_id", "不明")
            race_name = race.get("race_name", "不明")
            venue = race.get("venue", "")
            race_number = race.get("race_number", "")
            race_time = race.get("race_time", "")

            lines.append(f"🏇 {venue}{race_number} {race_time}")
            lines.append(f"   {race_name}")
            lines.append(f"   ID: `{race_id}`")
            lines.append("")

        message = "\n".join(lines)
        logger.debug(f"レース一覧フォーマット完了: count={len(races)}")
        return message

    except Exception as e:
        logger.error(f"レース一覧フォーマットエラー: {e}")
        return "📅 本日のレース一覧\n\n❌ フォーマットエラーが発生しました"


def format_help_message() -> str:
    """
    ヘルプメッセージをフォーマット

    Returns:
        フォーマット済みメッセージ
    """
    lines = [
        "🤖 競馬予想Bot - コマンド一覧",
        "",
        "**予想関連**",
        "`!predict <race_id>` - 指定レースの予想実行",
        "`!today` - 本日のレース一覧",
        "",
        "**統計関連**",
        "`!stats [期間]` - 統計情報表示",
        "  期間: daily/weekly/monthly/all（省略時: all）",
        "`!roi` - 回収率グラフ表示（未実装）",
        "",
        "**その他**",
        "`!help` - このヘルプを表示",
        "",
        "🎯 目標: 回収率200%達成！",
    ]

    message = "\n".join(lines)
    logger.debug("ヘルプメッセージフォーマット完了")
    return message
