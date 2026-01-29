"""
Database Connection Module

Manages connections to PostgreSQL (local, Neon, or mock).
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

# Load .env file
load_dotenv()

# Logger setup
logger = logging.getLogger(__name__)


class MockConnection:
    """
    Mock connection class (dummy for when DB is not connected).
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
    Mock cursor class.
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
    Class for managing PostgreSQL connections.

    Manages connections to local PostgreSQL, Neon, or mock.
    """

    def __init__(self):
        """
        Get connection info from environment variables.

        Raises:
            ValueError: If invalid DB_MODE is set
            MissingEnvironmentVariableError: If required environment variables are not set
        """
        self.db_mode = os.getenv("DB_MODE", "local")
        self._connection_pool: Optional[pool.SimpleConnectionPool] = None

        logger.info(f"DatabaseConnection instance created: mode={self.db_mode}")

        if self.db_mode == "mock":
            # Mock mode (when DB is not connected)
            logger.info("DB connection settings (mock): No actual DB connection")
            return

        if self.db_mode == "local":
            # For Docker: Prefer DB_*, fallback to LOCAL_DB_*
            self.host = os.getenv("DB_HOST") or os.getenv("LOCAL_DB_HOST", "localhost")
            self.port = os.getenv("DB_PORT") or os.getenv("LOCAL_DB_PORT", "5432")
            self.database = os.getenv("DB_NAME") or os.getenv("LOCAL_DB_NAME", "keiba_db")
            self.user = os.getenv("DB_USER") or os.getenv("LOCAL_DB_USER", "postgres")
            self.password = os.getenv("DB_PASSWORD") or os.getenv("LOCAL_DB_PASSWORD")

            # Password is required for local mode
            if not self.password:
                logger.error("DB_PASSWORD is not set")
                raise MissingEnvironmentVariableError("DB_PASSWORD")

            logger.info(f"DB connection settings (local): host={self.host}, port={self.port}, database={self.database}")

        elif self.db_mode == "neon":
            # Future Neon support
            self.connection_url = os.getenv("NEON_DATABASE_URL")

            if not self.connection_url:
                logger.error("NEON_DATABASE_URL is not set")
                raise MissingEnvironmentVariableError("NEON_DATABASE_URL")

            logger.info("DB connection settings (Neon): URL configured")

        else:
            logger.error(f"Invalid DB_MODE: {self.db_mode}")
            raise ValueError(f"Invalid DB_MODE: {self.db_mode}. Use 'local', 'neon', or 'mock'.")

    def get_connection(self) -> Psycopg2Connection:
        """
        Get database connection.

        Returns:
            Database connection object (MockConnection when in mock mode)

        Raises:
            DatabaseConnectionError: If database connection fails
        """
        if self.db_mode == "mock":
            logger.debug("Returning mock connection")
            return MockConnection()

        try:
            if self.db_mode == "local":
                logger.debug(f"Starting DB connection (local): {self.host}:{self.port}/{self.database}")
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                )
                logger.debug("DB connection successful (local)")
                return conn

            elif self.db_mode == "neon":
                logger.debug("Starting DB connection (Neon)")
                conn = psycopg2.connect(self.connection_url)
                logger.debug("DB connection successful (Neon)")
                return conn

        except psycopg2.OperationalError as e:
            logger.error(f"DB connection failed (auth/network error): {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}") from e
        except psycopg2.Error as e:
            logger.error(f"DB connection failed (PostgreSQL error): {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}") from e
        except Exception as e:
            logger.error(f"DB connection failed (unexpected error): {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}") from e

    def get_connection_pool(
        self,
        minconn: int = DB_CONNECTION_POOL_MIN,
        maxconn: int = DB_CONNECTION_POOL_MAX
    ) -> pool.SimpleConnectionPool:
        """
        Get connection pool (for cases requiring multiple connections).

        Args:
            minconn: Minimum connections (default: config value)
            maxconn: Maximum connections (default: config value)

        Returns:
            Connection pool

        Raises:
            DatabaseConnectionError: If connection pool creation fails
        """
        if self.db_mode == "mock":
            logger.warning("Connection pool is not available in mock mode")
            return None

        if self._connection_pool is None:
            try:
                if self.db_mode == "local":
                    logger.info(f"Creating connection pool (local): min={minconn}, max={maxconn}")
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
                    logger.info(f"Creating connection pool (Neon): min={minconn}, max={maxconn}")
                    self._connection_pool = pool.SimpleConnectionPool(
                        minconn, maxconn, self.connection_url
                    )

                logger.info("Connection pool created successfully")

            except psycopg2.OperationalError as e:
                logger.error(f"Connection pool creation failed (auth/network error): {e}")
                raise DatabaseConnectionError(f"Connection pool creation failed: {e}") from e
            except psycopg2.Error as e:
                logger.error(f"Connection pool creation failed (PostgreSQL error): {e}")
                raise DatabaseConnectionError(f"Connection pool creation failed: {e}") from e
            except Exception as e:
                logger.error(f"Connection pool creation failed (unexpected error): {e}")
                raise DatabaseConnectionError(f"Connection pool creation failed: {e}") from e

        return self._connection_pool

    def close_pool(self) -> None:
        """
        Close connection pool.

        Closes all connections in the pool.
        """
        if self._connection_pool is not None:
            try:
                logger.info("Starting connection pool close")
                self._connection_pool.closeall()
                self._connection_pool = None
                logger.info("Connection pool closed successfully")
            except Exception as e:
                logger.error(f"Connection pool close failed: {e}")


# Global instance (used like a singleton)
_db_instance: Optional[DatabaseConnection] = None


def get_db() -> DatabaseConnection:
    """
    Get global instance of DatabaseConnection.

    Uses singleton pattern to get connection management object.

    Returns:
        Database connection management object

    Raises:
        ValueError: If invalid DB_MODE is set
        MissingEnvironmentVariableError: If required environment variables are not set
    """
    global _db_instance
    if _db_instance is None:
        logger.info("Creating DatabaseConnection instance")
        _db_instance = DatabaseConnection()
    return _db_instance


def test_connection() -> bool:
    """
    Test database connection.

    Returns:
        True if connection successful, False otherwise
    """
    conn = None
    cursor = None

    try:
        logger.info("Starting DB connection test")
        db = get_db()

        if db.db_mode == "mock":
            logger.info("Mock mode: skipping connection test")
            print("Info: Mock mode - no actual DB connection")
            return True

        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()

        if version:
            logger.info(f"DB connection test successful: {version[0]}")
            print(f"DB connection successful: {version[0]}")
            return True
        else:
            logger.error("DB connection test failed: could not get version")
            print("Connection failed: could not get version info")
            return False

    except DatabaseConnectionError as e:
        logger.error(f"DB connection test failed (connection error): {e}")
        print(f"Connection failed: {e}")
        return False
    except MissingEnvironmentVariableError as e:
        logger.error(f"DB connection test failed (env var error): {e}")
        print(f"Connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"DB connection test failed (unexpected error): {e}")
        print(f"Connection failed: {e}")
        return False
    finally:
        # Resource cleanup
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.debug("DB connection test finished (resource cleanup complete)")


if __name__ == "__main__":
    # Run connection test when this file is executed directly
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    test_connection()
