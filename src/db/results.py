"""
Prediction Results Database Management Module

Provides operations for the predictions schema in PostgreSQL.
"""

from datetime import date
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from src.db.connection import get_db


class PredictionResultsDB:
    """Prediction results database management class."""

    def __init__(self):
        """Initialize."""
        self.db = get_db()

    def save_prediction(
        self,
        race_id: str,
        race_name: str,
        race_date: date,
        venue: str,
        analysis_result: dict[str, Any],
        prediction_result: dict[str, Any],
        total_investment: int,
        expected_return: int,
        expected_roi: float,
        llm_model: str,
    ) -> int:
        """
        Save a prediction.

        Args:
            race_id: Race ID
            race_name: Race name
            race_date: Race date
            venue: Racecourse
            analysis_result: Analysis result (dict)
            prediction_result: Prediction result (dict)
            total_investment: Total investment amount
            expected_return: Expected return amount
            expected_roi: Expected ROI
            llm_model: LLM model used

        Returns:
            int: ID of the inserted record
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO predictions.predictions (
                        race_id, race_name, race_date, venue,
                        analysis_result, prediction_result,
                        total_investment, expected_return, expected_roi,
                        llm_model
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s
                    )
                    ON CONFLICT (race_id) DO UPDATE SET
                        analysis_result = EXCLUDED.analysis_result,
                        prediction_result = EXCLUDED.prediction_result,
                        total_investment = EXCLUDED.total_investment,
                        expected_return = EXCLUDED.expected_return,
                        expected_roi = EXCLUDED.expected_roi,
                        llm_model = EXCLUDED.llm_model
                    RETURNING id
                    """,
                    (
                        race_id,
                        race_name,
                        race_date,
                        venue,
                        Json(analysis_result),
                        Json(prediction_result),
                        total_investment,
                        expected_return,
                        expected_roi,
                        llm_model,
                    ),
                )
                result = cur.fetchone()
                prediction_id = int(result[0]) if result else 0
                conn.commit()
                return prediction_id
        finally:
            conn.close()

    def save_result(
        self,
        prediction_id: int,
        actual_result: dict[str, Any],
        total_return: int,
        profit: int,
        actual_roi: float,
        prediction_accuracy: float,
        reflection_result: dict[str, Any],
    ) -> int:
        """
        Save race result.

        Args:
            prediction_id: Prediction ID
            actual_result: Actual race result (dict)
            total_return: Actual return amount
            profit: Profit/loss
            actual_roi: Actual ROI
            prediction_accuracy: Prediction accuracy
            reflection_result: Reflection result (dict)

        Returns:
            int: ID of the inserted record
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO predictions.results (
                        prediction_id, actual_result,
                        total_return, profit, actual_roi,
                        prediction_accuracy, reflection_result
                    ) VALUES (
                        %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        prediction_id,
                        Json(actual_result),
                        total_return,
                        profit,
                        actual_roi,
                        prediction_accuracy,
                        Json(reflection_result),
                    ),
                )
                result = cur.fetchone()
                result_id = int(result[0]) if result else 0
                conn.commit()
                return result_id
        finally:
            conn.close()

    def get_prediction_by_race_id(self, race_id: str) -> dict[str, Any] | None:
        """
        Get prediction by race ID.

        Args:
            race_id: Race ID

        Returns:
            Dict or None: Prediction record
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM predictions.predictions
                    WHERE race_id = %s
                    """,
                    (race_id,),
                )
                result = cur.fetchone()
                return dict(result) if result else None
        finally:
            conn.close()

    def get_recent_predictions(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get recent predictions list.

        Args:
            limit: Number of records to retrieve

        Returns:
            List[Dict]: List of predictions
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM predictions.recent_predictions_with_results
                    LIMIT %s
                    """,
                    (limit,),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        finally:
            conn.close()

    def get_stats(self, period: str = "all") -> dict[str, Any] | None:
        """
        Get statistics.

        Args:
            period: Aggregation period (daily/weekly/monthly/all)

        Returns:
            Dict or None: Statistics
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM predictions.stats
                    WHERE period = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (period,),
                )
                result = cur.fetchone()
                return dict(result) if result else None
        finally:
            conn.close()

    def update_stats(
        self,
        period: str,
        start_date: date | None,
        end_date: date | None,
    ) -> None:
        """
        Update statistics.

        Args:
            period: Aggregation period
            start_date: Start date
            end_date: End date
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                # Calculate statistics
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_races,
                        COALESCE(SUM(p.total_investment), 0) as total_investment,
                        COALESCE(SUM(r.total_return), 0) as total_return,
                        COALESCE(SUM(r.profit), 0) as total_profit,
                        CASE
                            WHEN SUM(p.total_investment) > 0
                            THEN (SUM(r.total_return)::NUMERIC / SUM(p.total_investment) * 100)
                            ELSE 0
                        END as roi,
                        COUNT(CASE WHEN r.profit > 0 THEN 1 END) as hit_count,
                        CASE
                            WHEN COUNT(*) > 0
                            THEN (COUNT(CASE WHEN r.profit > 0 THEN 1 END)::NUMERIC / COUNT(*))
                            ELSE 0
                        END as hit_rate,
                        MAX(r.actual_roi) as best_roi,
                        MIN(r.actual_roi) as worst_roi
                    FROM predictions.predictions p
                    LEFT JOIN predictions.results r ON p.id = r.prediction_id
                    WHERE (%s IS NULL OR p.race_date >= %s)
                      AND (%s IS NULL OR p.race_date <= %s)
                    """,
                    (start_date, start_date, end_date, end_date),
                )
                stats = cur.fetchone()

                # Save statistics
                cur.execute(
                    """
                    INSERT INTO predictions.stats (
                        period, start_date, end_date,
                        total_races, total_investment, total_return, total_profit, roi,
                        hit_count, hit_rate,
                        best_roi, worst_roi
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (period, start_date, end_date) DO UPDATE SET
                        total_races = EXCLUDED.total_races,
                        total_investment = EXCLUDED.total_investment,
                        total_return = EXCLUDED.total_return,
                        total_profit = EXCLUDED.total_profit,
                        roi = EXCLUDED.roi,
                        hit_count = EXCLUDED.hit_count,
                        hit_rate = EXCLUDED.hit_rate,
                        best_roi = EXCLUDED.best_roi,
                        worst_roi = EXCLUDED.worst_roi,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (period, start_date, end_date) + stats,
                )
                conn.commit()
        finally:
            conn.close()


# Global instance
_results_db: PredictionResultsDB | None = None


def get_results_db() -> PredictionResultsDB:
    """
    Get global instance of PredictionResultsDB.

    Returns:
        PredictionResultsDB: Prediction results database management object
    """
    global _results_db
    if _results_db is None:
        _results_db = PredictionResultsDB()
    return _results_db


if __name__ == "__main__":
    # Simple operation check
    print("=== Prediction Results DB Operation Check ===")
    db = get_results_db()

    # Get recent predictions
    recent = db.get_recent_predictions(limit=5)
    print(f"Recent prediction count: {len(recent)}")

    # Get statistics
    stats = db.get_stats("all")
    if stats:
        print(f"Total races: {stats.get('total_races', 0)}")
        print(f"ROI: {stats.get('roi', 0):.2f}%")
    else:
        print("No statistics")
