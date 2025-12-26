"""
予想結果データベース管理モジュール

PostgreSQLのpredictionsスキーマに対する操作を提供する。
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.db.connection import get_db


class PredictionResultsDB:
    """予想結果DB管理クラス"""

    def __init__(self):
        """初期化"""
        self.db = get_db()

    def save_prediction(
        self,
        race_id: str,
        race_name: str,
        race_date: date,
        venue: str,
        analysis_result: Dict[str, Any],
        prediction_result: Dict[str, Any],
        total_investment: int,
        expected_return: int,
        expected_roi: float,
        llm_model: str,
    ) -> int:
        """
        予想を保存

        Args:
            race_id: レースID
            race_name: レース名
            race_date: レース日
            venue: 競馬場
            analysis_result: 分析結果（dict）
            prediction_result: 予想結果（dict）
            total_investment: 総投資額
            expected_return: 期待回収額
            expected_roi: 期待ROI
            llm_model: 使用LLMモデル

        Returns:
            int: 挿入されたレコードのID
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
                prediction_id = cur.fetchone()[0]
                conn.commit()
                return prediction_id
        finally:
            conn.close()

    def save_result(
        self,
        prediction_id: int,
        actual_result: Dict[str, Any],
        total_return: int,
        profit: int,
        actual_roi: float,
        prediction_accuracy: float,
        reflection_result: Dict[str, Any],
    ) -> int:
        """
        レース結果を保存

        Args:
            prediction_id: 予想ID
            actual_result: 実際のレース結果（dict）
            total_return: 実際の回収額
            profit: 収支
            actual_roi: 実際のROI
            prediction_accuracy: 予想精度
            reflection_result: 反省結果（dict）

        Returns:
            int: 挿入されたレコードのID
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
                result_id = cur.fetchone()[0]
                conn.commit()
                return result_id
        finally:
            conn.close()

    def get_prediction_by_race_id(self, race_id: str) -> Optional[Dict[str, Any]]:
        """
        レースIDから予想を取得

        Args:
            race_id: レースID

        Returns:
            Dict or None: 予想レコード
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
                return cur.fetchone()
        finally:
            conn.close()

    def get_recent_predictions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        最近の予想一覧を取得

        Args:
            limit: 取得件数

        Returns:
            List[Dict]: 予想一覧
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
                return cur.fetchall()
        finally:
            conn.close()

    def get_stats(self, period: str = "all") -> Optional[Dict[str, Any]]:
        """
        統計情報を取得

        Args:
            period: 集計期間（daily/weekly/monthly/all）

        Returns:
            Dict or None: 統計情報
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
                return cur.fetchone()
        finally:
            conn.close()

    def update_stats(
        self,
        period: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> None:
        """
        統計情報を更新

        Args:
            period: 集計期間
            start_date: 開始日
            end_date: 終了日
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                # 統計を計算
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

                # 統計を保存
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


# グローバルインスタンス
_results_db: Optional[PredictionResultsDB] = None


def get_results_db() -> PredictionResultsDB:
    """
    PredictionResultsDBのグローバルインスタンスを取得

    Returns:
        PredictionResultsDB: 予想結果DB管理オブジェクト
    """
    global _results_db
    if _results_db is None:
        _results_db = PredictionResultsDB()
    return _results_db


if __name__ == "__main__":
    # 簡単な動作確認
    print("=== 予想結果DB動作確認 ===")
    db = get_results_db()

    # 最近の予想を取得
    recent = db.get_recent_predictions(limit=5)
    print(f"最近の予想件数: {len(recent)}")

    # 統計情報を取得
    stats = db.get_stats("all")
    if stats:
        print(f"総レース数: {stats.get('total_races', 0)}")
        print(f"回収率: {stats.get('roi', 0):.2f}%")
    else:
        print("統計情報なし")
