"""
PostgreSQL非同期接続管理モジュール (asyncpg)

FastAPI用の非同期接続プール管理
"""

import logging
from contextlib import asynccontextmanager

import asyncpg

from src.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_POOL_MAX_SIZE,
    DB_POOL_MIN_SIZE,
    DB_PORT,
    DB_USER,
)

logger = logging.getLogger(__name__)

# グローバル接続プール
_pool: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    """データベース接続プールを初期化"""
    global _pool

    if _pool is not None:
        logger.warning("Database pool already initialized")
        return

    try:
        _pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            command_timeout=120,  # 120秒でタイムアウト
        )
        logger.info(
            f"Database pool initialized: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


async def close_db_pool() -> None:
    """データベース接続プールをクローズ"""
    global _pool

    if _pool is None:
        logger.warning("Database pool not initialized")
        return

    try:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")
    except Exception as e:
        logger.error(f"Failed to close database pool: {e}")
        raise


def get_pool() -> asyncpg.Pool:
    """
    接続プールを取得

    Returns:
        asyncpg.Pool: 接続プール

    Raises:
        RuntimeError: プールが初期化されていない場合
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call init_db_pool() first."
        )
    return _pool


@asynccontextmanager
async def get_connection():
    """
    データベース接続を取得するコンテキストマネージャ

    使用例:
        async with get_connection() as conn:
            result = await conn.fetch("SELECT * FROM race LIMIT 10")

    Yields:
        asyncpg.Connection: データベース接続
    """
    pool = get_pool()
    async with pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def get_transaction():
    """
    トランザクション付きデータベース接続を取得

    使用例:
        async with get_transaction() as conn:
            await conn.execute("INSERT INTO ...")
            await conn.execute("UPDATE ...")
            # 正常終了時は自動コミット、例外時は自動ロールバック

    Yields:
        asyncpg.Connection: トランザクション付き接続
    """
    async with get_connection() as conn:
        async with conn.transaction():
            yield conn


async def test_connection() -> bool:
    """
    データベース接続をテスト

    Returns:
        bool: 接続成功時True、失敗時False
    """
    try:
        async with get_connection() as conn:
            version = await conn.fetchval("SELECT version();")
            logger.info(f"Database connection test successful: {version}")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


async def get_table_list() -> list[dict]:
    """
    データベース内の全テーブル一覧を取得

    Returns:
        list[dict]: テーブル情報のリスト
    """
    sql = """
        SELECT
            schemaname AS schema,
            tablename AS "table",
            pg_size_pretty(pg_total_relation_size(
                schemaname || '.' || tablename
            )) AS size
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """

    try:
        async with get_connection() as conn:
            rows = await conn.fetch(sql)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get table list: {e}")
        raise


async def execute_query(sql: str, *args) -> list[dict]:
    """
    汎用SELECT クエリ実行

    Args:
        sql: SQLクエリ
        *args: クエリパラメータ

    Returns:
        list[dict]: クエリ結果
    """
    try:
        async with get_connection() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Query execution failed: {e}\nSQL: {sql}")
        raise


async def execute_one(sql: str, *args) -> dict | None:
    """
    単一行を返すSELECTクエリ実行

    Args:
        sql: SQLクエリ
        *args: クエリパラメータ

    Returns:
        Optional[dict]: クエリ結果（見つからない場合はNone）
    """
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Query execution failed: {e}\nSQL: {sql}")
        raise


async def execute_value(sql: str, *args):
    """
    単一値を返すSELECTクエリ実行

    Args:
        sql: SQLクエリ
        *args: クエリパラメータ

    Returns:
        Any: クエリ結果の単一値
    """
    try:
        async with get_connection() as conn:
            return await conn.fetchval(sql, *args)
    except Exception as e:
        logger.error(f"Query execution failed: {e}\nSQL: {sql}")
        raise
