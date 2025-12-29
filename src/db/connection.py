"""
データベース接続モジュール

PostgreSQL（ローカル or Neon or モック）への接続を管理する。
"""

import os
import logging
from typing import Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import connection as Psycopg2Connection
from dotenv import load_dotenv

from src.config import (
    DB_CONNECTION_POOL_MIN,
    DB_CONNECTION_POOL_MAX,
)
from src.exceptions import (
    DatabaseConnectionError,
    MissingEnvironmentVariableError,
)

# .envファイルを読み込み
load_dotenv()

# ロガー設定
logger = logging.getLogger(__name__)


class MockConnection:
    """
    モック接続クラス（DB未接続時のダミー）
    """
    def cursor(self):
        return MockCursor()

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


class MockCursor:
    """
    モックカーソルクラス
    """
    def execute(self, query, params=None):
        logger.debug(f"[MOCK] Execute: {query[:100]}...")

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def fetchmany(self, size=None):
        return []

    def close(self):
        pass


class DatabaseConnection:
    """
    PostgreSQL接続を管理するクラス

    ローカルPostgreSQL、Neon、またはモックへの接続を管理します。
    """

    def __init__(self):
        """
        接続情報を環境変数から取得

        Raises:
            ValueError: 不正なDB_MODEが設定されている場合
            MissingEnvironmentVariableError: 必須の環境変数が設定されていない場合
        """
        self.db_mode = os.getenv("DB_MODE", "local")
        self._connection_pool: Optional[pool.SimpleConnectionPool] = None

        logger.info(f"DatabaseConnection インスタンス作成: mode={self.db_mode}")

        if self.db_mode == "mock":
            # モックモード（DB未接続時）
            logger.info("DB接続設定（モック）: 実際のDB接続は行いません")
            return

        if self.db_mode == "local":
            # Docker環境用: DB_* を優先、なければ LOCAL_DB_* にフォールバック
            self.host = os.getenv("DB_HOST") or os.getenv("LOCAL_DB_HOST", "localhost")
            self.port = os.getenv("DB_PORT") or os.getenv("LOCAL_DB_PORT", "5432")
            self.database = os.getenv("DB_NAME") or os.getenv("LOCAL_DB_NAME", "keiba_db")
            self.user = os.getenv("DB_USER") or os.getenv("LOCAL_DB_USER", "postgres")
            self.password = os.getenv("DB_PASSWORD") or os.getenv("LOCAL_DB_PASSWORD")

            # ローカルモードではパスワードが必須
            if not self.password:
                logger.error("DB_PASSWORD が設定されていません")
                raise MissingEnvironmentVariableError("DB_PASSWORD")

            logger.info(f"DB接続設定（ローカル）: host={self.host}, port={self.port}, database={self.database}")

        elif self.db_mode == "neon":
            # 将来のNeon対応
            self.connection_url = os.getenv("NEON_DATABASE_URL")

            if not self.connection_url:
                logger.error("NEON_DATABASE_URL が設定されていません")
                raise MissingEnvironmentVariableError("NEON_DATABASE_URL")

            logger.info("DB接続設定（Neon）: URL設定済み")

        else:
            logger.error(f"不正なDB_MODE: {self.db_mode}")
            raise ValueError(f"Invalid DB_MODE: {self.db_mode}. Use 'local', 'neon', or 'mock'.")

    def get_connection(self) -> Psycopg2Connection:
        """
        データベース接続を取得

        Returns:
            データベース接続オブジェクト（モック時はMockConnection）

        Raises:
            DatabaseConnectionError: データベース接続に失敗した場合
        """
        if self.db_mode == "mock":
            logger.debug("モック接続を返却")
            return MockConnection()

        try:
            if self.db_mode == "local":
                logger.debug(f"DB接続開始（ローカル）: {self.host}:{self.port}/{self.database}")
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                )
                logger.debug("DB接続成功（ローカル）")
                return conn

            elif self.db_mode == "neon":
                logger.debug("DB接続開始（Neon）")
                conn = psycopg2.connect(self.connection_url)
                logger.debug("DB接続成功（Neon）")
                return conn

        except psycopg2.OperationalError as e:
            logger.error(f"DB接続失敗（認証/ネットワークエラー）: {e}")
            raise DatabaseConnectionError(f"データベース接続失敗: {e}") from e
        except psycopg2.Error as e:
            logger.error(f"DB接続失敗（PostgreSQLエラー）: {e}")
            raise DatabaseConnectionError(f"データベース接続失敗: {e}") from e
        except Exception as e:
            logger.error(f"DB接続失敗（予期しないエラー）: {e}")
            raise DatabaseConnectionError(f"データベース接続失敗: {e}") from e

    def get_connection_pool(
        self,
        minconn: int = DB_CONNECTION_POOL_MIN,
        maxconn: int = DB_CONNECTION_POOL_MAX
    ) -> pool.SimpleConnectionPool:
        """
        コネクションプールを取得（複数接続が必要な場合）

        Args:
            minconn: 最小接続数（デフォルト: 設定値）
            maxconn: 最大接続数（デフォルト: 設定値）

        Returns:
            コネクションプール

        Raises:
            DatabaseConnectionError: コネクションプール作成に失敗した場合
        """
        if self.db_mode == "mock":
            logger.warning("モックモードではコネクションプールは使用できません")
            return None

        if self._connection_pool is None:
            try:
                if self.db_mode == "local":
                    logger.info(f"コネクションプール作成開始（ローカル）: min={minconn}, max={maxconn}")
                    self._connection_pool = pool.SimpleConnectionPool(
                        minconn,
                        maxconn,
                        host=self.host,
                        port=self.port,
                        database=self.database,
                        user=self.user,
                        password=self.password,
                    )
                elif self.db_mode == "neon":
                    logger.info(f"コネクションプール作成開始（Neon）: min={minconn}, max={maxconn}")
                    self._connection_pool = pool.SimpleConnectionPool(
                        minconn, maxconn, self.connection_url
                    )

                logger.info("コネクションプール作成成功")

            except psycopg2.OperationalError as e:
                logger.error(f"コネクションプール作成失敗（認証/ネットワークエラー）: {e}")
                raise DatabaseConnectionError(f"コネクションプール作成失敗: {e}") from e
            except psycopg2.Error as e:
                logger.error(f"コネクションプール作成失敗（PostgreSQLエラー）: {e}")
                raise DatabaseConnectionError(f"コネクションプール作成失敗: {e}") from e
            except Exception as e:
                logger.error(f"コネクションプール作成失敗（予期しないエラー）: {e}")
                raise DatabaseConnectionError(f"コネクションプール作成失敗: {e}") from e

        return self._connection_pool

    def close_pool(self) -> None:
        """
        コネクションプールを閉じる

        すべてのプール内の接続を閉じます。
        """
        if self._connection_pool is not None:
            try:
                logger.info("コネクションプールクローズ開始")
                self._connection_pool.closeall()
                self._connection_pool = None
                logger.info("コネクションプールクローズ完了")
            except Exception as e:
                logger.error(f"コネクションプールクローズ失敗: {e}")


# グローバルインスタンス（シングルトン的に使用）
_db_instance: Optional[DatabaseConnection] = None


def get_db() -> DatabaseConnection:
    """
    DatabaseConnectionのグローバルインスタンスを取得

    シングルトンパターンで接続管理オブジェクトを取得します。

    Returns:
        データベース接続管理オブジェクト

    Raises:
        ValueError: 不正なDB_MODEが設定されている場合
        MissingEnvironmentVariableError: 必須の環境変数が設定されていない場合
    """
    global _db_instance
    if _db_instance is None:
        logger.info("DatabaseConnection インスタンス作成")
        _db_instance = DatabaseConnection()
    return _db_instance


def test_connection() -> bool:
    """
    データベース接続をテスト

    Returns:
        接続成功ならTrue、失敗ならFalse
    """
    conn = None
    cursor = None

    try:
        logger.info("DB接続テスト開始")
        db = get_db()

        if db.db_mode == "mock":
            logger.info("モックモード: 接続テストをスキップ")
            print("ℹ️ モックモード: 実際のDB接続は行いません")
            return True

        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()

        if version:
            logger.info(f"DB接続テスト成功: {version[0]}")
            print(f"DB接続成功: {version[0]}")
            return True
        else:
            logger.error("DB接続テスト失敗: バージョン取得できず")
            print("接続失敗: バージョン情報を取得できませんでした")
            return False

    except DatabaseConnectionError as e:
        logger.error(f"DB接続テスト失敗（接続エラー）: {e}")
        print(f"接続失敗: {e}")
        return False
    except MissingEnvironmentVariableError as e:
        logger.error(f"DB接続テスト失敗（環境変数エラー）: {e}")
        print(f"接続失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"DB接続テスト失敗（予期しないエラー）: {e}")
        print(f"接続失敗: {e}")
        return False
    finally:
        # リソースクリーンアップ
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.debug("DB接続テスト終了（リソースクリーンアップ完了）")


if __name__ == "__main__":
    # このファイルを直接実行した場合、接続テストを実行
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    test_connection()
