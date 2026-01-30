"""
PostgreSQL Async Connection Management Module (asyncpg)

Async connection pool management for FastAPI.
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

# Global connection pool
_pool: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    """Initialize the database connection pool."""
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
            command_timeout=120,  # 120 second timeout
        )
        logger.info(f"Database pool initialized: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


async def close_db_pool() -> None:
    """Close the database connection pool."""
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
    Get the connection pool.

    Returns:
        asyncpg.Pool: Connection pool

    Raises:
        RuntimeError: If pool is not initialized
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
    return _pool


@asynccontextmanager
async def get_connection():
    """
    Context manager for acquiring a database connection.

    Usage:
        async with get_connection() as conn:
            result = await conn.fetch("SELECT * FROM race LIMIT 10")

    Yields:
        asyncpg.Connection: Database connection
    """
    pool = get_pool()
    async with pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def get_transaction():
    """
    Context manager for acquiring a database connection with transaction.

    Usage:
        async with get_transaction() as conn:
            await conn.execute("INSERT INTO ...")
            await conn.execute("UPDATE ...")
            # Auto-commit on success, auto-rollback on exception

    Yields:
        asyncpg.Connection: Connection with transaction
    """
    async with get_connection() as conn:
        async with conn.transaction():
            yield conn


async def test_connection() -> bool:
    """
    Test database connection.

    Returns:
        bool: True if connection successful, False otherwise
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
    Get list of all tables in the database.

    Returns:
        list[dict]: List of table information
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
    Execute a generic SELECT query.

    Args:
        sql: SQL query
        *args: Query parameters

    Returns:
        list[dict]: Query results
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
    Execute a SELECT query that returns a single row.

    Args:
        sql: SQL query
        *args: Query parameters

    Returns:
        Optional[dict]: Query result (None if not found)
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
    Execute a SELECT query that returns a single value.

    Args:
        sql: SQL query
        *args: Query parameters

    Returns:
        Any: Single value from query result
    """
    try:
        async with get_connection() as conn:
            return await conn.fetchval(sql, *args)
    except Exception as e:
        logger.error(f"Query execution failed: {e}\nSQL: {sql}")
        raise
