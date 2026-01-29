"""
Expected Value Based Betting Recommendation Module

Predicted probability × Odds = Expected Value (EV)
Recommends horses with EV > threshold as betting candidates.
"""

import logging
from datetime import datetime, timedelta, timezone

import psycopg2.extras

from src.db.connection import get_db

# Japan Standard Time
JST = timezone(timedelta(hours=9))

# Logger setup
logger = logging.getLogger(__name__)

# Default thresholds (backtest result: 417% return rate with EV>=1.5)
DEFAULT_WIN_EV_THRESHOLD = 1.5  # Win bet EV threshold
DEFAULT_PLACE_EV_THRESHOLD = 1.5  # Place bet EV threshold
# Loose thresholds (for candidates)
LOOSE_WIN_EV_THRESHOLD = 1.2
LOOSE_PLACE_EV_THRESHOLD = 1.2


class EVRecommender:
    """Expected value based betting recommendation class."""

    def __init__(
        self,
        win_ev_threshold: float = DEFAULT_WIN_EV_THRESHOLD,
        place_ev_threshold: float = DEFAULT_PLACE_EV_THRESHOLD,
    ):
        """
        Args:
            win_ev_threshold: EV threshold for win bet recommendations
            place_ev_threshold: EV threshold for place bet recommendations
        """
        self.win_ev_threshold = win_ev_threshold
        self.place_ev_threshold = place_ev_threshold
        self.db = get_db()

    def get_recommendations(
        self,
        race_code: str,
        ranked_horses: list[dict],
        use_realtime_odds: bool = True,
    ) -> dict:
        """
        Get expected value based betting recommendations.

        Args:
            race_code: Race code
            ranked_horses: Prediction results (containing win_probability, place_probability)
            use_realtime_odds: True=time-series odds (latest), False=final odds

        Returns:
            {
                "win_recommendations": [...],  # Win bet recommendation list
                "place_recommendations": [...],  # Place bet recommendation list
                "odds_source": "realtime" or "final",
                "odds_time": "YYYY-MM-DD HH:MM" or None,
            }
        """
        try:
            conn = self.db.get_connection()

            # Get odds
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

            # No odds available
            if not tansho_odds and not fukusho_odds:
                logger.warning(f"No odds data: race_code={race_code}")
                return {
                    "win_recommendations": [],
                    "place_recommendations": [],
                    "odds_source": odds_source,
                    "odds_time": odds_time,
                    "error": "No odds data available",
                }

            # Calculate EV and generate recommendations
            win_recommendations = []  # EV >= 1.5 (strong recommendation)
            place_recommendations = []  # EV >= 1.5 (strong recommendation)
            win_candidates = []  # EV >= 1.2 (candidate)
            place_candidates = []  # EV >= 1.2 (candidate)
            top1_win_rec = None  # Rank 1 + EV condition
            top1_place_rec = None  # Rank 1 + EV condition

            for horse in ranked_horses:
                umaban = str(int(horse.get("horse_number", 0)))
                horse_name = horse.get("horse_name", "Unknown")
                win_prob = horse.get("win_probability", 0)
                place_prob = horse.get("place_probability", 0)
                rank = horse.get("rank", 99)

                # Win bet expected value
                tansho_odd = tansho_odds.get(umaban, 0)
                if tansho_odd > 0 and win_prob > 0:
                    win_ev = win_prob * tansho_odd
                    rec = {
                        "horse_number": int(umaban),
                        "horse_name": horse_name,
                        "win_probability": win_prob,
                        "odds": tansho_odd,
                        "expected_value": win_ev,
                        "rank": rank,
                    }
                    if win_ev >= self.win_ev_threshold:
                        win_recommendations.append(rec)
                    elif win_ev >= LOOSE_WIN_EV_THRESHOLD:
                        win_candidates.append(rec)
                    # Rank 1 + EV >= 1.0
                    if rank == 1 and win_ev >= 1.0 and top1_win_rec is None:
                        top1_win_rec = rec

                # Place bet expected value
                fukusho_odd = fukusho_odds.get(umaban, 0)
                if fukusho_odd > 0 and place_prob > 0:
                    place_ev = place_prob * fukusho_odd
                    rec = {
                        "horse_number": int(umaban),
                        "horse_name": horse_name,
                        "place_probability": place_prob,
                        "odds": fukusho_odd,
                        "expected_value": place_ev,
                        "rank": rank,
                    }
                    if place_ev >= self.place_ev_threshold:
                        place_recommendations.append(rec)
                    elif place_ev >= LOOSE_PLACE_EV_THRESHOLD:
                        place_candidates.append(rec)
                    # Rank 1 + EV >= 1.0
                    if rank == 1 and place_ev >= 1.0 and top1_place_rec is None:
                        top1_place_rec = rec

            # Sort by expected value
            win_recommendations.sort(key=lambda x: x["expected_value"], reverse=True)
            place_recommendations.sort(key=lambda x: x["expected_value"], reverse=True)
            win_candidates.sort(key=lambda x: x["expected_value"], reverse=True)
            place_candidates.sort(key=lambda x: x["expected_value"], reverse=True)

            logger.info(
                f"EV recommendations: race_code={race_code}, "
                f"win={len(win_recommendations)}(candidates={len(win_candidates)}), "
                f"place={len(place_recommendations)}(candidates={len(place_candidates)})"
            )

            return {
                "win_recommendations": win_recommendations,  # EV >= 1.5
                "place_recommendations": place_recommendations,  # EV >= 1.5
                "win_candidates": win_candidates,  # 1.2 <= EV < 1.5
                "place_candidates": place_candidates,  # 1.2 <= EV < 1.5
                "top1_win": top1_win_rec,  # Rank 1 + EV >= 1.0
                "top1_place": top1_place_rec,  # Rank 1 + EV >= 1.0
                "odds_source": odds_source,
                "odds_time": odds_time,
            }

        except Exception as e:
            logger.exception(f"EV recommendation error: race_code={race_code}, error={e}")
            return {
                "win_recommendations": [],
                "place_recommendations": [],
                "odds_source": "error",
                "odds_time": None,
                "error": str(e),
            }

    def _get_realtime_tansho_odds(
        self, conn, race_code: str
    ) -> tuple[dict[str, float], str | None]:
        """Get latest win odds from time-series data."""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Get latest announcement time
            cur.execute(
                """
                SELECT MAX(happyo_tsukihi_jifun) as latest_time
                FROM odds1_tansho_jikeiretsu
                WHERE race_code = %s
            """,
                (race_code,),
            )
            row = cur.fetchone()
            latest_time = row["latest_time"] if row else None

            if not latest_time:
                cur.close()
                return {}, None

            # Get odds at that time
            cur.execute(
                """
                SELECT umaban, odds
                FROM odds1_tansho_jikeiretsu
                WHERE race_code = %s AND happyo_tsukihi_jifun = %s
            """,
                (race_code, latest_time),
            )

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row["umaban"]).strip()
                try:
                    odds = float(row["odds"]) / 10  # Stored as 10x value
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()

            # Format announcement time
            odds_time_str = None
            if latest_time and len(latest_time) >= 8:
                # MMDDHHMMSS or MMDDHHMM format
                try:
                    month = latest_time[0:2]
                    day = latest_time[2:4]
                    hour = latest_time[4:6]
                    minute = latest_time[6:8]
                    now = datetime.now(JST)
                    year = now.year
                    # If December but announcement is January, use next year
                    if now.month == 12 and month == "01":
                        year += 1
                    odds_time_str = f"{year}-{month}-{day} {hour}:{minute}"
                except Exception:
                    pass

            logger.debug(
                f"Time-series win odds retrieved: race_code={race_code}, count={len(odds_dict)}, time={latest_time}"
            )
            return odds_dict, odds_time_str

        except Exception as e:
            logger.error(f"Time-series win odds retrieval error: {e}")
            return {}, None

    def _get_realtime_fukusho_odds(
        self, conn, race_code: str
    ) -> tuple[dict[str, float], str | None]:
        """Get latest place odds from time-series data (using minimum odds)."""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Check if place time-series table exists
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'odds1_fukusho_jikeiretsu'
            """
            )
            has_jikeiretsu = cur.fetchone() is not None

            if has_jikeiretsu:
                # Get from time-series table
                cur.execute(
                    """
                    SELECT MAX(happyo_tsukihi_jifun) as latest_time
                    FROM odds1_fukusho_jikeiretsu
                    WHERE race_code = %s
                """,
                    (race_code,),
                )
                row = cur.fetchone()
                latest_time = row["latest_time"] if row else None

                if latest_time:
                    cur.execute(
                        """
                        SELECT umaban, odds_saitei
                        FROM odds1_fukusho_jikeiretsu
                        WHERE race_code = %s AND happyo_tsukihi_jifun = %s
                    """,
                        (race_code, latest_time),
                    )
                else:
                    # Fall back to final odds if no time-series
                    cur.execute(
                        """
                        SELECT umaban, odds_saitei
                        FROM odds1_fukusho
                        WHERE race_code = %s
                    """,
                        (race_code,),
                    )
            else:
                # Get from final odds
                cur.execute(
                    """
                    SELECT umaban, odds_saitei
                    FROM odds1_fukusho
                    WHERE race_code = %s
                """,
                    (race_code,),
                )

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row["umaban"]).strip()
                try:
                    odds = float(row["odds_saitei"]) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()

            logger.debug(
                f"Time-series place odds retrieved: race_code={race_code}, count={len(odds_dict)}"
            )
            return odds_dict, None

        except Exception as e:
            logger.error(f"Time-series place odds retrieval error: {e}")
            return {}, None

    def _get_final_tansho_odds(self, conn, race_code: str) -> dict[str, float]:
        """Get final win odds."""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                """
                SELECT umaban, odds
                FROM odds1_tansho
                WHERE race_code = %s
            """,
                (race_code,),
            )

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row["umaban"]).strip()
                try:
                    odds = float(row["odds"]) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()
            logger.debug(f"Final win odds retrieved: race_code={race_code}, count={len(odds_dict)}")
            return odds_dict

        except Exception as e:
            logger.error(f"Final win odds retrieval error: {e}")
            return {}

    def _get_final_fukusho_odds(self, conn, race_code: str) -> dict[str, float]:
        """Get final place odds (using minimum odds)."""
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                """
                SELECT umaban, odds_saitei
                FROM odds1_fukusho
                WHERE race_code = %s
            """,
                (race_code,),
            )

            odds_dict = {}
            for row in cur.fetchall():
                umaban = str(row["umaban"]).strip()
                try:
                    odds = float(row["odds_saitei"]) / 10
                except (ValueError, TypeError):
                    odds = 0
                if odds > 0:
                    odds_dict[umaban] = odds

            cur.close()
            logger.debug(
                f"Final place odds retrieved: race_code={race_code}, count={len(odds_dict)}"
            )
            return odds_dict

        except Exception as e:
            logger.error(f"Final place odds retrieval error: {e}")
            return {}
