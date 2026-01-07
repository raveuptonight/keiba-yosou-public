"""
期待値ベース馬券推奨モジュール

予測確率 × オッズ = 期待値 (EV)
EV > 閾値 の馬を馬券候補として推奨
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

import psycopg2.extras

from src.db.connection import get_db

# 日本標準時
JST = timezone(timedelta(hours=9))

# ロガー設定
logger = logging.getLogger(__name__)

# デフォルト閾値
DEFAULT_WIN_EV_THRESHOLD = 1.2   # 単勝期待値閾値
DEFAULT_PLACE_EV_THRESHOLD = 1.2  # 複勝期待値閾値


class EVRecommender:
    """期待値ベースの馬券推奨クラス"""

    def __init__(
        self,
        win_ev_threshold: float = DEFAULT_WIN_EV_THRESHOLD,
        place_ev_threshold: float = DEFAULT_PLACE_EV_THRESHOLD,
    ):
        """
        Args:
            win_ev_threshold: 単勝推奨の期待値閾値
            place_ev_threshold: 複勝推奨の期待値閾値
        """
        self.win_ev_threshold = win_ev_threshold
        self.place_ev_threshold = place_ev_threshold
        self.db = get_db()

    def get_recommendations(
        self,
        race_code: str,
        ranked_horses: List[Dict],
        use_realtime_odds: bool = True,
    ) -> Dict:
        """
        期待値ベースの馬券推奨を取得

        Args:
            race_code: レースコード
            ranked_horses: 予想結果（win_probability, place_probability を含む）
            use_realtime_odds: True=時系列オッズ（最新）、False=確定オッズ

        Returns:
            {
                "win_recommendations": [...],  # 単勝推奨リスト
                "place_recommendations": [...],  # 複勝推奨リスト
                "odds_source": "realtime" or "final",
                "odds_time": "YYYY-MM-DD HH:MM" or None,
            }
        """
        try:
            conn = self.db.get_connection()

            # オッズを取得
            if use_realtime_odds:
                tansho_odds, odds_time = self._get_realtime_tansho_odds(conn, race_code)
                fukusho_odds, _ = self._get_realtime_fukusho_odds(conn, race_code)
                odds_source = "realtime"
            else:
                tansho_odds = self._get_final_tansho_odds(conn, race_code)
                fukusho_odds = self._get_final_fukusho_odds(conn, race_code)
                odds_source = "final"
                odds_time = None

            conn.close()

            # オッズがない場合
            if not tansho_odds and not fukusho_odds:
                logger.warning(f"オッズデータなし: race_code={race_code}")
                return {
                    "win_recommendations": [],
                    "place_recommendations": [],
                    "odds_source": odds_source,
                    "odds_time": odds_time,
                    "error": "オッズデータがありません",
                }

            # 期待値計算と推奨生成
            win_recommendations = []
            place_recommendations = []

            for horse in ranked_horses:
                umaban = str(int(horse.get("horse_number", 0)))
                horse_name = horse.get("horse_name", "不明")
                win_prob = horse.get("win_probability", 0)
                place_prob = horse.get("place_probability", 0)

                # 単勝期待値
                tansho_odd = tansho_odds.get(umaban, 0)
                if tansho_odd > 0 and win_prob > 0:
                    win_ev = win_prob * tansho_odd
                    if win_ev >= self.win_ev_threshold:
                        win_recommendations.append({
                            "horse_number": int(umaban),
                            "horse_name": horse_name,
                            "win_probability": win_prob,
                            "odds": tansho_odd,
                            "expected_value": win_ev,
                        })

                # 複勝期待値
                fukusho_odd = fukusho_odds.get(umaban, 0)
                if fukusho_odd > 0 and place_prob > 0:
                    place_ev = place_prob * fukusho_odd
                    if place_ev >= self.place_ev_threshold:
                        place_recommendations.append({
                            "horse_number": int(umaban),
                            "horse_name": horse_name,
                            "place_probability": place_prob,
                            "odds": fukusho_odd,
                            "expected_value": place_ev,
                        })

            # 期待値順でソート
            win_recommendations.sort(key=lambda x: x["expected_value"], reverse=True)
            place_recommendations.sort(key=lambda x: x["expected_value"], reverse=True)

            logger.info(
                f"EV推奨: race_code={race_code}, "
                f"win={len(win_recommendations)}件, place={len(place_recommendations)}件"
            )

            return {
                "win_recommendations": win_recommendations,
                "place_recommendations": place_recommendations,
                "odds_source": odds_source,
                "odds_time": odds_time,
            }

        except Exception as e:
            logger.exception(f"EV推奨取得エラー: race_code={race_code}, error={e}")
            return {
                "win_recommendations": [],
                "place_recommendations": [],
                "odds_source": "error",
                "odds_time": None,
                "error": str(e),
            }

    def _get_realtime_tansho_odds(
        self, conn, race_code: str
    ) -> Tuple[Dict[str, float], Optional[str]]:
        """時系列から最新の単勝オッズを取得"""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # 最新の発表時刻を取得
            cur.execute('''
                SELECT MAX(happyo_tsukihi_jifun) as latest_time
                FROM odds1_tansho_jikeiretsu
                WHERE race_code = %s
            ''', (race_code,))
            row = cur.fetchone()
            latest_time = row['latest_time'] if row else None

            if not latest_time:
                cur.close()
                return {}, None

            # その時刻のオッズを取得
            cur.execute('''
                SELECT umaban, odds
                FROM odds1_tansho_jikeiretsu
                WHERE race_code = %s AND happyo_tsukihi_jifun = %s
            ''', (race_code, latest_time))

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row['umaban']).strip()
                try:
                    odds = float(row['odds']) / 10  # 10倍で格納されている
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()

            # 発表時刻をフォーマット
            odds_time_str = None
            if latest_time and len(latest_time) >= 8:
                # MMDDHHMMSS or MMDDHHMM 形式
                try:
                    month = latest_time[0:2]
                    day = latest_time[2:4]
                    hour = latest_time[4:6]
                    minute = latest_time[6:8]
                    now = datetime.now(JST)
                    year = now.year
                    # 12月だが発表が1月の場合は翌年
                    if now.month == 12 and month == "01":
                        year += 1
                    odds_time_str = f"{year}-{month}-{day} {hour}:{minute}"
                except:
                    pass

            logger.debug(f"時系列単勝オッズ取得: race_code={race_code}, 件数={len(odds_dict)}, time={latest_time}")
            return odds_dict, odds_time_str

        except Exception as e:
            logger.error(f"時系列単勝オッズ取得エラー: {e}")
            return {}, None

    def _get_realtime_fukusho_odds(
        self, conn, race_code: str
    ) -> Tuple[Dict[str, float], Optional[str]]:
        """時系列から最新の複勝オッズを取得（最低オッズ使用）"""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # 複勝の時系列テーブルがあるか確認
            cur.execute('''
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'odds1_fukusho_jikeiretsu'
            ''')
            has_jikeiretsu = cur.fetchone() is not None

            if has_jikeiretsu:
                # 時系列テーブルから取得
                cur.execute('''
                    SELECT MAX(happyo_tsukihi_jifun) as latest_time
                    FROM odds1_fukusho_jikeiretsu
                    WHERE race_code = %s
                ''', (race_code,))
                row = cur.fetchone()
                latest_time = row['latest_time'] if row else None

                if latest_time:
                    cur.execute('''
                        SELECT umaban, odds_saitei
                        FROM odds1_fukusho_jikeiretsu
                        WHERE race_code = %s AND happyo_tsukihi_jifun = %s
                    ''', (race_code, latest_time))
                else:
                    # 時系列がなければ確定オッズにフォールバック
                    cur.execute('''
                        SELECT umaban, odds_saitei
                        FROM odds1_fukusho
                        WHERE race_code = %s
                    ''', (race_code,))
            else:
                # 確定オッズから取得
                cur.execute('''
                    SELECT umaban, odds_saitei
                    FROM odds1_fukusho
                    WHERE race_code = %s
                ''', (race_code,))

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row['umaban']).strip()
                try:
                    odds = float(row['odds_saitei']) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()

            logger.debug(f"時系列複勝オッズ取得: race_code={race_code}, 件数={len(odds_dict)}")
            return odds_dict, None

        except Exception as e:
            logger.error(f"時系列複勝オッズ取得エラー: {e}")
            return {}, None

    def _get_final_tansho_odds(self, conn, race_code: str) -> Dict[str, float]:
        """確定単勝オッズを取得"""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                SELECT umaban, odds
                FROM odds1_tansho
                WHERE race_code = %s
            ''', (race_code,))

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row['umaban']).strip()
                try:
                    odds = float(row['odds']) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()
            logger.debug(f"確定単勝オッズ取得: race_code={race_code}, 件数={len(odds_dict)}")
            return odds_dict

        except Exception as e:
            logger.error(f"確定単勝オッズ取得エラー: {e}")
            return {}

    def _get_final_fukusho_odds(self, conn, race_code: str) -> Dict[str, float]:
        """確定複勝オッズを取得（最低オッズ使用）"""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                SELECT umaban, odds_saitei
                FROM odds1_fukusho
                WHERE race_code = %s
            ''', (race_code,))

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row['umaban']).strip()
                try:
                    odds = float(row['odds_saitei']) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()
            logger.debug(f"確定複勝オッズ取得: race_code={race_code}, 件数={len(odds_dict)}")
            return odds_dict

        except Exception as e:
            logger.error(f"確定複勝オッズ取得エラー: {e}")
            return {}


def format_ev_recommendations(recommendations: Dict) -> str:
    """
    EV推奨をDiscord用にフォーマット

    Args:
        recommendations: get_recommendations()の戻り値

    Returns:
        フォーマット済み文字列
    """
    lines = []

    win_recs = recommendations.get("win_recommendations", [])
    place_recs = recommendations.get("place_recommendations", [])
    odds_time = recommendations.get("odds_time")
    error = recommendations.get("error")

    if error:
        return f"⚠️ オッズ取得エラー: {error}"

    if not win_recs and not place_recs:
        return "📊 期待値推奨: 該当馬なし（EV >= 1.2 の馬がいません）"

    lines.append("💰 **期待値ベース馬券推奨**")
    if odds_time:
        lines.append(f"_オッズ時刻: {odds_time}_")
    lines.append("")

    # 単勝推奨
    if win_recs:
        lines.append("**【単勝】** (EV = 勝率 × オッズ)")
        for rec in win_recs[:3]:  # 最大3頭
            num = rec["horse_number"]
            name = rec["horse_name"][:6]
            prob = rec["win_probability"]
            odds = rec["odds"]
            ev = rec["expected_value"]
            lines.append(f"  🎯 {num}番 {name}: EV={ev:.2f} (確率{prob:.1%} × {odds:.1f}倍)")
    else:
        lines.append("**【単勝】** 推奨なし")

    lines.append("")

    # 複勝推奨
    if place_recs:
        lines.append("**【複勝】** (EV = 複勝率 × オッズ)")
        for rec in place_recs[:3]:  # 最大3頭
            num = rec["horse_number"]
            name = rec["horse_name"][:6]
            prob = rec["place_probability"]
            odds = rec["odds"]
            ev = rec["expected_value"]
            lines.append(f"  🎯 {num}番 {name}: EV={ev:.2f} (確率{prob:.1%} × {odds:.1f}倍)")
    else:
        lines.append("**【複勝】** 推奨なし")

    lines.append("")
    lines.append("_※EV(期待値) >= 1.2 の馬を推奨（1.0=損益分岐点）_")

    return "\n".join(lines)
