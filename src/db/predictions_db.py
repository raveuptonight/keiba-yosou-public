"""
予想結果・学習履歴データベース

予想結果の保存、学習履歴の管理、学習ポイントの取得
"""

import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.db.connection import get_db


class PredictionsDB:
    """予想結果・学習履歴データベース"""

    def __init__(self):
        self.db = get_db()

    def save_prediction(
        self,
        race_id: str,
        race_date: str,
        ml_scores: Dict,
        analysis: Dict,
        prediction: Dict,
        model_version: str = "v1.0"
    ) -> int:
        """
        予想結果を保存

        Args:
            race_id: レースID
            race_date: レース日付（YYYY-MM-DD）
            ml_scores: ML予測結果
            analysis: Phase 1分析結果
            prediction: Phase 2最終予想
            model_version: モデルバージョン

        Returns:
            int: 保存された予想ID
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor()

            query = """
                INSERT INTO predictions (
                    race_id, race_date, ml_scores, analysis, prediction, model_version
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING prediction_id;
            """

            cursor.execute(
                query,
                (
                    race_id,
                    race_date,
                    Json(ml_scores),
                    Json(analysis),
                    Json(prediction),
                    model_version
                )
            )

            prediction_id = cursor.fetchone()[0]
            conn.commit()

            print(f"✅ 予想結果保存: prediction_id={prediction_id}")
            return prediction_id

        except Exception as e:
            conn.rollback()
            raise Exception(f"予想結果保存エラー: {e}")

        finally:
            cursor.close()
            conn.close()

    def save_learning_history(
        self,
        prediction_id: int,
        race_id: str,
        actual_result: Dict,
        ml_analysis: Dict,
        llm_analysis: Dict,
        learning_points: List[str],
        ml_retrain_result: Optional[Dict] = None,
        accuracy_metrics: Optional[Dict] = None
    ) -> int:
        """
        学習履歴を保存

        Args:
            prediction_id: 予想ID
            race_id: レースID
            actual_result: 実際の結果
            ml_analysis: ML外れ値分析
            llm_analysis: LLM失敗分析
            learning_points: 学習ポイントリスト
            ml_retrain_result: 再学習結果（オプション）
            accuracy_metrics: 精度指標（オプション）

        Returns:
            int: 学習履歴ID
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor()

            query = """
                INSERT INTO learning_history (
                    prediction_id, race_id, actual_result,
                    ml_outlier_analysis, llm_failure_analysis,
                    learning_points, ml_retrain_result, accuracy_metrics
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING learning_id;
            """

            cursor.execute(
                query,
                (
                    prediction_id,
                    race_id,
                    Json(actual_result),
                    Json(ml_analysis),
                    Json(llm_analysis),
                    learning_points,
                    Json(ml_retrain_result) if ml_retrain_result else None,
                    Json(accuracy_metrics) if accuracy_metrics else None
                )
            )

            learning_id = cursor.fetchone()[0]
            conn.commit()

            print(f"✅ 学習履歴保存: learning_id={learning_id}")
            return learning_id

        except Exception as e:
            conn.rollback()
            raise Exception(f"学習履歴保存エラー: {e}")

        finally:
            cursor.close()
            conn.close()

    def get_recent_learning_points(
        self,
        limit: int = 10,
        days_back: int = 30
    ) -> List[Dict]:
        """
        最近の学習ポイントを取得

        Args:
            limit: 取得件数
            days_back: 何日前までのデータを取得するか

        Returns:
            list: 学習ポイントリスト（新しい順）
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cutoff_date = datetime.now() - timedelta(days=days_back)

            query = """
                SELECT
                    learning_id,
                    race_id,
                    analyzed_at,
                    learning_points,
                    ml_outlier_analysis->>'outlier_rate' as outlier_rate,
                    ml_outlier_analysis->>'avg_error' as avg_error
                FROM learning_history
                WHERE analyzed_at >= %s
                  AND learning_points IS NOT NULL
                  AND array_length(learning_points, 1) > 0
                ORDER BY analyzed_at DESC
                LIMIT %s;
            """

            cursor.execute(query, (cutoff_date, limit))
            results = cursor.fetchall()

            # dict形式に変換
            learning_data = []
            for row in results:
                learning_data.append({
                    'learning_id': row['learning_id'],
                    'race_id': row['race_id'],
                    'analyzed_at': row['analyzed_at'].isoformat(),
                    'learning_points': row['learning_points'],
                    'outlier_rate': float(row['outlier_rate']) if row['outlier_rate'] else 0,
                    'avg_error': float(row['avg_error']) if row['avg_error'] else 0
                })

            return learning_data

        except Exception as e:
            raise Exception(f"学習ポイント取得エラー: {e}")

        finally:
            cursor.close()
            conn.close()

    def get_prediction_by_id(self, prediction_id: int) -> Optional[Dict]:
        """
        予想IDから予想データを取得

        Args:
            prediction_id: 予想ID

        Returns:
            dict: 予想データ（見つからない場合はNone）
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT
                    prediction_id, race_id, race_date,
                    ml_scores, analysis, prediction,
                    model_version, predicted_at
                FROM predictions
                WHERE prediction_id = %s;
            """

            cursor.execute(query, (prediction_id,))
            result = cursor.fetchone()

            if result:
                return dict(result)
            return None

        except Exception as e:
            raise Exception(f"予想取得エラー: {e}")

        finally:
            cursor.close()
            conn.close()

    def get_accuracy_stats(self, days_back: int = 30) -> Dict:
        """
        直近の予想精度統計を取得

        Args:
            days_back: 何日前までのデータを集計するか

        Returns:
            dict: 精度統計
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cutoff_date = datetime.now() - timedelta(days=days_back)

            query = """
                SELECT
                    COUNT(*) as total_predictions,
                    AVG((ml_outlier_analysis->>'outlier_rate')::float) as avg_outlier_rate,
                    AVG((ml_outlier_analysis->>'avg_error')::float) as avg_error,
                    COUNT(CASE WHEN ml_retrain_result IS NOT NULL THEN 1 END) as retrain_count
                FROM learning_history
                WHERE analyzed_at >= %s;
            """

            cursor.execute(query, (cutoff_date,))
            result = cursor.fetchone()

            if result:
                return {
                    'total_predictions': result['total_predictions'],
                    'avg_outlier_rate': float(result['avg_outlier_rate']) if result['avg_outlier_rate'] else 0,
                    'avg_error': float(result['avg_error']) if result['avg_error'] else 0,
                    'retrain_count': result['retrain_count'],
                    'period_days': days_back
                }

            return {
                'total_predictions': 0,
                'avg_outlier_rate': 0,
                'avg_error': 0,
                'retrain_count': 0,
                'period_days': days_back
            }

        except Exception as e:
            raise Exception(f"精度統計取得エラー: {e}")

        finally:
            cursor.close()
            conn.close()

    def init_tables(self):
        """
        テーブル初期化（マイグレーション実行）
        """
        conn = self.db.get_connection()
        if not conn:
            raise ConnectionError("データベース接続失敗")

        try:
            cursor = conn.cursor()

            # マイグレーションファイルを読み込んで実行
            migration_file = "src/db/migrations/001_create_predictions_tables.sql"

            with open(migration_file, 'r', encoding='utf-8') as f:
                sql = f.read()

            cursor.execute(sql)
            conn.commit()

            print("✅ テーブル初期化完了")

        except Exception as e:
            conn.rollback()
            raise Exception(f"テーブル初期化エラー: {e}")

        finally:
            cursor.close()
            conn.close()


# 使用例
if __name__ == "__main__":
    db = PredictionsDB()

    # テーブル初期化
    try:
        db.init_tables()
        print("テーブル初期化成功")
    except Exception as e:
        print(f"エラー: {e}")

    # 学習ポイント取得テスト
    try:
        learning_points = db.get_recent_learning_points(limit=5)
        print(f"\n最近の学習ポイント: {len(learning_points)}件")
        for lp in learning_points:
            print(f"  {lp['race_id']}: {lp['learning_points']}")
    except Exception as e:
        print(f"学習ポイント取得エラー: {e}")
