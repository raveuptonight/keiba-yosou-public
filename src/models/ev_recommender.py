"""
Expected Value Based Betting Recommendation Module

Predicted probability × Odds = Expected Value (EV)
Recommends horses with EV > threshold as betting candidates.
"""

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
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

# Dynamic threshold adjustment
CONFIDENCE_ALPHA = 0.5  # Max threshold adjustment range


def _calculate_race_confidence(win_probs: list[float]) -> float:
    """Calculate model confidence for a race based on prediction entropy.

    Low entropy (one horse dominates) = high confidence.
    High entropy (all horses similar) = low confidence.

    Args:
        win_probs: List of win probabilities for all horses in the race.

    Returns:
        Confidence score in [0, 1]. Higher = more confident.
    """
    if not win_probs or len(win_probs) < 2:
        return 0.5

    probs = np.array(win_probs, dtype=np.float64)
    probs = probs[probs > 0]
    if len(probs) < 2:
        return 0.5

    # Normalize to sum to 1
    total = probs.sum()
    if total <= 0:
        return 0.5
    probs = probs / total

    # Shannon entropy
    entropy = -np.sum(probs * np.log(probs))
    # Maximum entropy for uniform distribution
    max_entropy = np.log(len(probs))

    if max_entropy <= 0:
        return 0.5

    # Normalized entropy: 0 = perfectly concentrated, 1 = uniform
    norm_entropy = entropy / max_entropy
    # Confidence = 1 - normalized entropy
    return float(1.0 - norm_entropy)


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

            # Dynamic threshold adjustment based on model confidence
            win_probs = [h.get("win_probability", 0) for h in ranked_horses]
            confidence = _calculate_race_confidence(win_probs)
            # High confidence -> lower threshold, low confidence -> higher threshold
            threshold_adj = CONFIDENCE_ALPHA * (1.0 - confidence)
            effective_win_threshold = self.win_ev_threshold + threshold_adj
            effective_place_threshold = self.place_ev_threshold + threshold_adj
            effective_loose_win = LOOSE_WIN_EV_THRESHOLD + threshold_adj * 0.5
            effective_loose_place = LOOSE_PLACE_EV_THRESHOLD + threshold_adj * 0.5

            logger.debug(
                f"Dynamic threshold: confidence={confidence:.3f}, "
                f"win_ev_th={effective_win_threshold:.2f}, place_ev_th={effective_place_threshold:.2f}"
            )

            # Calculate EV and generate recommendations
            win_recommendations = []
            place_recommendations = []
            win_candidates = []
            place_candidates = []
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
                        "confidence": confidence,
                    }
                    if win_ev >= effective_win_threshold:
                        win_recommendations.append(rec)
                    elif win_ev >= effective_loose_win:
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
                        "confidence": confidence,
                    }
                    if place_ev >= effective_place_threshold:
                        place_recommendations.append(rec)
                    elif place_ev >= effective_loose_place:
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
                f"confidence={confidence:.3f}, "
                f"thresholds=win:{effective_win_threshold:.2f}/place:{effective_place_threshold:.2f}, "
                f"win={len(win_recommendations)}(candidates={len(win_candidates)}), "
                f"place={len(place_recommendations)}(candidates={len(place_candidates)})"
            )

            return {
                "win_recommendations": win_recommendations,
                "place_recommendations": place_recommendations,
                "win_candidates": win_candidates,
                "place_candidates": place_candidates,
                "top1_win": top1_win_rec,
                "top1_place": top1_place_rec,
                "odds_source": odds_source,
                "odds_time": odds_time,
                "confidence": confidence,
                "effective_win_threshold": effective_win_threshold,
                "effective_place_threshold": effective_place_threshold,
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
