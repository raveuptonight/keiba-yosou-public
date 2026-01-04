"""
Discord通知フォーマッター

予想完了通知、的中報告などのメッセージをフォーマット
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List
import numpy as np

from src.models.prediction_output import (
    RacePrediction,
    HorsePrediction,
    create_race_prediction,
    format_prediction_for_discord,
)

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

        # 予想結果から本命・対抗・穴馬等を取得
        win_pred = prediction_result.get("win_prediction", {})
        honmei = win_pred.get("first", {})
        taikou = win_pred.get("second", {})
        ana = win_pred.get("third", {})
        renka = win_pred.get("fourth", {})
        chumoku = win_pred.get("fifth", {})
        excluded = win_pred.get("excluded", [])

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

        # 本命・対抗・穴馬・連下・注目馬
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
        if renka:
            lines.append(
                f"△連下: {renka.get('horse_number', '?')}番 {renka.get('horse_name', '不明')}"
            )
        if chumoku:
            lines.append(
                f"☆注目: {chumoku.get('horse_number', '?')}番 {chumoku.get('horse_name', '不明')}"
            )

        # 消し馬
        if excluded:
            lines.append("")
            excluded_list = []
            for horse in excluded[:3]:  # 最大3頭まで表示
                horse_num = horse.get('horse_number', '?')
                horse_name = horse.get('horse_name', '不明')
                excluded_list.append(f"{horse_num}番{horse_name}")
            lines.append(f"✕消し馬: {', '.join(excluded_list)}")

        # 推奨馬券
        if tickets:
            lines.append("")
            lines.append("💰 推奨買い目")
            for ticket in tickets[:6]:  # 最大6つまで表示
                ticket_type = ticket.get("ticket_type", "不明")
                numbers = ticket.get("numbers", [])
                confidence = ticket.get("confidence", 0.0)
                if isinstance(numbers, list):
                    numbers_str = "-".join(map(str, numbers))
                else:
                    numbers_str = str(numbers)
                lines.append(f"・{ticket_type} [{numbers_str}] 信頼度:{confidence:.0f}%")

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


def format_betting_recommendation(
    race_name: str,
    race_id: str,
    ticket_type: str,
    budget: int,
    result: Dict[str, Any]
) -> str:
    """
    馬券購入推奨をフォーマット

    Args:
        race_name: レース名
        race_id: レースID
        ticket_type: 馬券タイプ
        budget: 予算（円）
        result: 最適化結果

    Returns:
        フォーマット済みメッセージ
    """
    try:
        tickets = result.get("tickets", [])
        total_cost = result.get("total_cost", 0)
        expected_return = result.get("expected_return", 0)
        expected_roi = result.get("expected_roi", 0.0)
        message_text = result.get("message", "")

        lines = [
            f"🎯 【馬券購入推奨】{race_name}",
            "",
            f"馬券タイプ: {ticket_type}",
            f"予算: {budget:,}円",
            "",
        ]

        # 買い目がない場合
        if not tickets:
            lines.append("❌ 買い目を生成できませんでした")
            lines.append(f"理由: {message_text}")
            return "\n".join(lines)

        # 買い目一覧
        lines.append(f"💰 推奨買い目（{len(tickets)}通り）")
        lines.append("")

        for i, ticket in enumerate(tickets, start=1):
            numbers = ticket.get("numbers", [])
            horse_names = ticket.get("horse_names", [])
            amount = ticket.get("amount", 0)
            expected_payout = ticket.get("expected_payout", 0)

            # 馬番と馬名の表示
            if horse_names and len(horse_names) == len(numbers):
                # 馬番 馬名形式
                horses_str = " - ".join([
                    f"{num}番{name}" for num, name in zip(numbers, horse_names)
                ])
            else:
                # 馬番のみ
                horses_str = " - ".join(map(str, numbers))

            lines.append(f"{i}. {horses_str}")
            lines.append(f"   金額: {amount:,}円 / 期待払戻: {expected_payout:,}円")

            # 最大10件まで表示（それ以上は省略）
            if i >= 10 and i < len(tickets):
                remaining = len(tickets) - 10
                lines.append("")
                lines.append(f"... 他{remaining}通り")
                break

        # 合計
        lines.append("")
        lines.append("📊 合計")
        lines.append(f"総投資額: {total_cost:,}円")
        lines.append(f"期待回収: {expected_return:,}円")
        lines.append(f"期待ROI: {expected_roi:.1f}%")

        # ROI評価
        lines.append("")
        if expected_roi >= 150:
            lines.append("✅ 期待値が高い買い目です！")
        elif expected_roi >= 100:
            lines.append("⚠️ トントン程度の期待値です")
        else:
            lines.append("⚠️ 期待値が低めです。慎重に判断してください")

        lines.append("")
        lines.append(f"💡 {message_text}")

        message = "\n".join(lines)
        logger.debug(f"馬券推奨フォーマット完了: race_id={race_id}, tickets={len(tickets)}")
        return message

    except Exception as e:
        logger.error(f"馬券推奨フォーマットエラー: {e}")
        return f"🎯 【馬券購入推奨】{race_name}\n\n❌ フォーマットエラーが発生しました"


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
        "`!predict <レース> [temperature]` - 指定レースの予想実行",
        "  例: `!predict 京都2r`, `!predict 中山11R`",
        "`!ml <レースコード>` - ML予測（確率・順位分布・信頼度）",
        "  例: `!ml 202501050811`",
        "`!today` - 本日のレース一覧",
        "",
        "**馬券購入**",
        "`!baken <レース> <予算> <馬券タイプ>` - 馬券購入推奨",
        "  例: `!baken 京都2r 10000 3連複`",
        "  例: `!baken 中山11R 5000 馬連`",
        "  馬券タイプ: 単勝/複勝/馬連/ワイド/馬単/3連複/3連単",
        "",
        "**統計関連**",
        "`!stats [期間]` - 統計情報表示",
        "  期間: daily/weekly/monthly/all（省略時: all）",
        "`!roi` - 回収率グラフ表示（未実装）",
        "",
        "**その他**",
        "`!help` - このヘルプを表示",
        "",
        "💡 レース指定: 競馬場名+レース番号（例: 京都2r, 中山11R）",
        "🎯 目標: 回収率200%達成！",
    ]

    message = "\n".join(lines)
    logger.debug("ヘルプメッセージフォーマット完了")
    return message


def format_final_prediction_notification(
    venue: str,
    race_number: str,
    race_time: str,
    race_name: str,
    ranked_horses: List[Dict[str, Any]],
) -> str:
    """
    最終予想通知をフォーマット（馬体重発表後の詳細形式）

    前日予想と同じ形式で全馬のランキングを表示

    Args:
        venue: 競馬場名
        race_number: レース番号（"01"形式または"1R"形式）
        race_time: 発走時刻（"HHMM"形式または"HH:MM"形式）
        race_name: レース名
        ranked_horses: 予想順位順の馬リスト

    Returns:
        フォーマット済みメッセージ
    """
    try:
        # レース番号フォーマット（"01" -> "1R"）
        try:
            race_num_int = int(race_number.replace("R", ""))
            race_num_formatted = f"{race_num_int}R"
        except (ValueError, TypeError):
            race_num_formatted = f"{race_number}R" if not str(race_number).endswith("R") else race_number

        # 発走時刻フォーマット（"1420" -> "14:20"）
        if race_time and len(race_time) >= 4 and ":" not in race_time:
            time_formatted = f"{race_time[:2]}:{race_time[2:4]}"
        else:
            time_formatted = race_time

        # ヘッダー（2行）
        lines = [
            f"🔥 **{venue} {race_num_formatted} 最終予想を通知します**",
            "",
            f"{venue} {race_num_formatted} {time_formatted}発走 {race_name}",
            "",
        ]

        # 全馬表示
        for h in ranked_horses:
            rank = h.get('rank', 0)
            num = h.get('horse_number', '?')
            name = h.get('horse_name', '?')

            # 性別・年齢
            sex = h.get('horse_sex') or ''
            age = h.get('horse_age')
            sex_age = f"{sex}{age}" if sex and age else ""

            # 騎手名
            jockey = (h.get('jockey_name') or '').replace('　', ' ')

            # [性齢/騎手]形式
            if sex_age and jockey:
                info_str = f"[{sex_age}/{jockey}]"
            elif sex_age:
                info_str = f"[{sex_age}]"
            elif jockey:
                info_str = f"[{jockey}]"
            else:
                info_str = ""

            # 確率
            win_prob = h.get('win_probability', 0)
            quinella_prob = h.get('quinella_probability', 0)
            place_prob = h.get('place_probability', 0)

            lines.append(
                f"{rank}位 {num}番 {name} {info_str} "
                f"(単勝{win_prob:.1%} 連対{quinella_prob:.1%} 複勝{place_prob:.1%})"
            )

        message = "\n".join(lines)
        logger.debug(f"最終予想通知フォーマット完了: venue={venue}, race_number={race_number}")
        return message

    except Exception as e:
        logger.error(f"最終予想通知フォーマットエラー: {e}")
        return f"🔥 **{venue} {race_number}R 最終予想**\n\n❌ フォーマットエラーが発生しました"


def format_ml_prediction(
    race_code: str,
    race_name: str,
    horse_numbers: List[int],
    horse_names: List[str],
    model_scores: np.ndarray,
    pace_info: Dict = None
) -> str:
    """
    MLモデル予測結果をDiscord用にフォーマット

    4つの指標を出力:
    1. 勝率（確率ベース）
    2. 予測順位（ランキング形式）
    3. 順位分布（1着/2着/3着/4着以下）
    4. 信頼度スコア

    Args:
        race_code: レースコード
        race_name: レース名
        horse_numbers: 馬番リスト
        horse_names: 馬名リスト
        model_scores: モデルの予測スコア
        pace_info: 展開予想情報

    Returns:
        フォーマット済みメッセージ
    """
    try:
        # RacePrediction オブジェクトを作成
        prediction = create_race_prediction(
            race_code=race_code,
            race_name=race_name,
            horse_numbers=horse_numbers,
            horse_names=horse_names,
            model_scores=model_scores,
            pace_info=pace_info
        )

        # Discord用フォーマット
        message = format_prediction_for_discord(prediction)
        logger.debug(f"ML予測フォーマット完了: race_code={race_code}")
        return message

    except Exception as e:
        logger.error(f"ML予測フォーマットエラー: {e}")
        return f"🏇 【ML予測】{race_name}\n\n❌ フォーマットエラーが発生しました"
