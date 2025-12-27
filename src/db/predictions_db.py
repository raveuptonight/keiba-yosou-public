"""
予想結果・学習履歴データベース

予想結果の保存、学習履歴の管理、学習ポイントの取得を行うDBクライアント
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.db.connection import get_db
from src.config import (
    DB_DEFAULT_LEARNING_POINTS_LIMIT,
    DB_DEFAULT_DAYS_BACK,
    DB_DEFAULT_STATS_DAYS_BACK,
    MIGRATION_DIR,
)
from src.exceptions import (
    DatabaseError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseMigrationError,
)

# ロガー設定
logger = logging.getLogger(__name__)


class PredictionsDB:
    """
    予想結果・学習履歴データベースクライアント

    predictions テーブルと learning_history テーブルへのアクセスを提供します。

    Attributes:
        db: データベース接続マネージャー
    """

    def __init__(self):
        """
        初期化

        Raises:
            DatabaseConnectionError: データベース接続マネージャーの取得に失敗した場合
        """
        try:
            self.db = get_db()
            logger.info("PredictionsDB初期化完了")
        except Exception as e:
            logger.error(f"PredictionsDB初期化失敗: {e}")
            raise DatabaseConnectionError(f"PredictionsDB初期化失敗: {e}") from e

    def save_prediction(
        self,
        race_id: str,
        race_date: str,
        ml_scores: Dict[str, Any],
        analysis: Dict[str, Any],
        prediction: Dict[str, Any],
        model_version: str = "v1.0"
    ) -> int:
        """
        予想結果を保存

        Args:
            race_id: レースID
            race_date: レース日付（YYYY-MM-DD形式）
            ml_scores: ML予測結果
            analysis: Phase 1分析結果
            prediction: Phase 2最終予想
            model_version: モデルバージョン

        Returns:
            保存された予想ID

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseQueryError: クエリ実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
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

            result = cursor.fetchone()
            if not result:
                raise DatabaseQueryError("予想結果保存後、IDが取得できませんでした")

            prediction_id = result[0]
            conn.commit()

            logger.info(f"予想結果保存成功: prediction_id={prediction_id}")
            print(f"✅ 予想結果保存: prediction_id={prediction_id}")
            return prediction_id

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"予想結果保存失敗（DB エラー）: {e}")
            raise DatabaseQueryError(f"予想結果保存失敗: {e}") from e
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"予想結果保存失敗: {e}")
            raise DatabaseQueryError(f"予想結果保存失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_learning_history(
        self,
        prediction_id: Optional[int],
        race_id: str,
        actual_result: Dict[str, Any],
        ml_analysis: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        learning_points: List[str],
        ml_retrain_result: Optional[Dict[str, Any]] = None,
        accuracy_metrics: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        学習履歴を保存

        Args:
            prediction_id: 予想ID（省略可能）
            race_id: レースID
            actual_result: 実際の結果
            ml_analysis: ML外れ値分析結果
            llm_analysis: LLM失敗分析結果
            learning_points: 学習ポイントリスト
            ml_retrain_result: 再学習結果（オプション）
            accuracy_metrics: 精度指標（オプション）

        Returns:
            学習履歴ID

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseQueryError: クエリ実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
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

            result = cursor.fetchone()
            if not result:
                raise DatabaseQueryError("学習履歴保存後、IDが取得できませんでした")

            learning_id = result[0]
            conn.commit()

            logger.info(f"学習履歴保存成功: learning_id={learning_id}")
            print(f"✅ 学習履歴保存: learning_id={learning_id}")
            return learning_id

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"学習履歴保存失敗（DBエラー）: {e}")
            raise DatabaseQueryError(f"学習履歴保存失敗: {e}") from e
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"学習履歴保存失敗: {e}")
            raise DatabaseQueryError(f"学習履歴保存失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_recent_learning_points(
        self,
        limit: int = DB_DEFAULT_LEARNING_POINTS_LIMIT,
        days_back: int = DB_DEFAULT_DAYS_BACK
    ) -> List[Dict[str, Any]]:
        """
        最近の学習ポイントを取得

        Args:
            limit: 取得件数（デフォルト: 設定ファイルから）
            days_back: 何日前までのデータを取得するか（デフォルト: 設定ファイルから）

        Returns:
            学習ポイントリスト（新しい順）

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseQueryError: クエリ実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
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
            learning_data: List[Dict[str, Any]] = []
            for row in results:
                learning_data.append({
                    'learning_id': row['learning_id'],
                    'race_id': row['race_id'],
                    'analyzed_at': row['analyzed_at'].isoformat(),
                    'learning_points': row['learning_points'],
                    'outlier_rate': float(row['outlier_rate']) if row['outlier_rate'] else 0,
                    'avg_error': float(row['avg_error']) if row['avg_error'] else 0
                })

            logger.debug(f"学習ポイント取得成功: {len(learning_data)}件")
            return learning_data

        except psycopg2.Error as e:
            logger.error(f"学習ポイント取得失敗（DBエラー）: {e}")
            raise DatabaseQueryError(f"学習ポイント取得失敗: {e}") from e
        except Exception as e:
            logger.error(f"学習ポイント取得失敗: {e}")
            raise DatabaseQueryError(f"学習ポイント取得失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_prediction_by_id(self, prediction_id: int) -> Optional[Dict[str, Any]]:
        """
        予想IDから予想データを取得

        Args:
            prediction_id: 予想ID

        Returns:
            予想データ（見つからない場合はNone）

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseQueryError: クエリ実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
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
                logger.debug(f"予想取得成功: prediction_id={prediction_id}")
                return dict(result)

            logger.debug(f"予想が見つかりません: prediction_id={prediction_id}")
            return None

        except psycopg2.Error as e:
            logger.error(f"予想取得失敗（DBエラー）: {e}")
            raise DatabaseQueryError(f"予想取得失敗: {e}") from e
        except Exception as e:
            logger.error(f"予想取得失敗: {e}")
            raise DatabaseQueryError(f"予想取得失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_accuracy_stats(
        self,
        days_back: int = DB_DEFAULT_STATS_DAYS_BACK
    ) -> Dict[str, Any]:
        """
        直近の予想精度統計を取得

        Args:
            days_back: 何日前までのデータを集計するか（デフォルト: 設定ファイルから）

        Returns:
            精度統計（以下のキーを含む）:
                - total_predictions: 総予想数
                - avg_outlier_rate: 平均外れ値率
                - avg_error: 平均誤差
                - retrain_count: 再学習実行回数
                - period_days: 集計期間（日数）

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseQueryError: クエリ実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
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

            if result and result['total_predictions'] > 0:
                stats = {
                    'total_predictions': result['total_predictions'],
                    'avg_outlier_rate': float(result['avg_outlier_rate']) if result['avg_outlier_rate'] else 0,
                    'avg_error': float(result['avg_error']) if result['avg_error'] else 0,
                    'retrain_count': result['retrain_count'],
                    'period_days': days_back
                }
                logger.debug(f"精度統計取得成功: {stats['total_predictions']}件")
                return stats

            logger.debug("精度統計データなし、デフォルト値を返却")
            return {
                'total_predictions': 0,
                'avg_outlier_rate': 0,
                'avg_error': 0,
                'retrain_count': 0,
                'period_days': days_back
            }

        except psycopg2.Error as e:
            logger.error(f"精度統計取得失敗（DBエラー）: {e}")
            raise DatabaseQueryError(f"精度統計取得失敗: {e}") from e
        except Exception as e:
            logger.error(f"精度統計取得失敗: {e}")
            raise DatabaseQueryError(f"精度統計取得失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def init_tables(self) -> None:
        """
        テーブル初期化（マイグレーション実行）

        predictions および learning_history テーブルを作成します。

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
            DatabaseMigrationError: マイグレーション実行に失敗した場合
        """
        conn = self.db.get_connection()
        if not conn:
            raise DatabaseConnectionError("データベース接続失敗")

        cursor = None
        try:
            cursor = conn.cursor()

            # マイグレーションファイルを読み込んで実行
            migration_file = Path(MIGRATION_DIR) / "001_create_predictions_tables.sql"

            if not migration_file.exists():
                raise DatabaseMigrationError(
                    f"マイグレーションファイルが見つかりません: {migration_file}"
                )

            with open(migration_file, 'r', encoding='utf-8') as f:
                sql = f.read()

            cursor.execute(sql)
            conn.commit()

            logger.info("テーブル初期化完了")
            print("✅ テーブル初期化完了")

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"テーブル初期化失敗（DBエラー）: {e}")
            raise DatabaseMigrationError(f"テーブル初期化失敗: {e}") from e
        except DatabaseMigrationError:
            # 既知のエラーは再スロー
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"テーブル初期化失敗: {e}")
            raise DatabaseMigrationError(f"テーブル初期化失敗: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


# 使用例
if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    db = PredictionsDB()

    # テーブル初期化
    try:
        db.init_tables()
        print("テーブル初期化成功")
    except DatabaseMigrationError as e:
        print(f"エラー: {e}")

    # 学習ポイント取得テスト
    try:
        learning_points = db.get_recent_learning_points(limit=5)
        print(f"\n最近の学習ポイント: {len(learning_points)}件")
        for lp in learning_points:
            print(f"  {lp['race_id']}: {lp['learning_points']}")
    except DatabaseQueryError as e:
        print(f"学習ポイント取得エラー: {e}")
