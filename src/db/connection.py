"""
データベース接続モジュール

PostgreSQL（ローカル or Neon）への接続を管理する。
"""

import os
from typing import Optional

import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()


class DatabaseConnection:
    """PostgreSQL接続を管理するクラス"""

    def __init__(self):
        """接続情報を環境変数から取得"""
        self.db_mode = os.getenv("DB_MODE", "local")
        self._connection_pool: Optional[pool.SimpleConnectionPool] = None

        if self.db_mode == "local":
            self.host = os.getenv("LOCAL_DB_HOST", "localhost")
            self.port = os.getenv("LOCAL_DB_PORT", "5432")
            self.database = os.getenv("LOCAL_DB_NAME", "keiba_db")
            self.user = os.getenv("LOCAL_DB_USER", "postgres")
            self.password = os.getenv("LOCAL_DB_PASSWORD")
        elif self.db_mode == "neon":
            # 将来のNeon対応
            self.connection_url = os.getenv("NEON_DATABASE_URL")
        else:
            raise ValueError(f"Invalid DB_MODE: {self.db_mode}")

    def get_connection(self):
        """
        データベース接続を取得

        Returns:
            psycopg2.connection: データベース接続オブジェクト

        Raises:
            psycopg2.Error: 接続エラー
        """
        if self.db_mode == "local":
            return psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
        elif self.db_mode == "neon":
            return psycopg2.connect(self.connection_url)

    def get_connection_pool(self, minconn=1, maxconn=10):
        """
        コネクションプールを取得（複数接続が必要な場合）

        Args:
            minconn: 最小接続数
            maxconn: 最大接続数

        Returns:
            psycopg2.pool.SimpleConnectionPool: コネクションプール
        """
        if self._connection_pool is None:
            if self.db_mode == "local":
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
                self._connection_pool = pool.SimpleConnectionPool(
                    minconn, maxconn, self.connection_url
                )

        return self._connection_pool

    def close_pool(self):
        """コネクションプールを閉じる"""
        if self._connection_pool is not None:
            self._connection_pool.closeall()
            self._connection_pool = None


# グローバルインスタンス（シングルトン的に使用）
_db_instance: Optional[DatabaseConnection] = None


def get_db() -> DatabaseConnection:
    """
    DatabaseConnectionのグローバルインスタンスを取得

    Returns:
        DatabaseConnection: データベース接続管理オブジェクト
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseConnection()
    return _db_instance


def test_connection() -> bool:
    """
    データベース接続をテスト

    Returns:
        bool: 接続成功ならTrue、失敗ならFalse
    """
    try:
        db = get_db()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"接続成功: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"接続失敗: {e}")
        return False


if __name__ == "__main__":
    # このファイルを直接実行した場合、接続テストを実行
    test_connection()
