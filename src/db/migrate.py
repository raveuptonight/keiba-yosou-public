"""
Database Migration Runner

Executes SQL migration files in order to set up required tables.
"""

import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Migration directory
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db_connection():
    """Get database connection from environment variables."""
    db_mode = os.getenv("DB_MODE", "local")

    if db_mode == "mock":
        logger.info("Mock mode: skipping migrations")
        return None

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_NAME", "keiba_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD")

    if not password:
        logger.error("DB_PASSWORD environment variable is not set")
        sys.exit(1)

    logger.info(f"Connecting to database: {host}:{port}/{database}")

    return psycopg2.connect(host=host, port=port, database=database, user=user, password=password)


def get_migration_files():
    """Get sorted list of migration files."""
    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return []

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return sql_files


def run_migration(conn, migration_file: Path):
    """Execute a single migration file."""
    logger.info(f"Running migration: {migration_file.name}")

    with open(migration_file, encoding="utf-8") as f:
        sql = f.read()

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
        logger.info(f"Migration completed: {migration_file.name}")
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Migration failed: {migration_file.name} - {e}")
        raise
    finally:
        cursor.close()


def run_migrations():
    """Run all pending migrations."""
    logger.info("=" * 50)
    logger.info("Starting database migrations")
    logger.info("=" * 50)

    conn = get_db_connection()

    if conn is None:
        logger.info("Skipping migrations (mock mode)")
        return

    try:
        migration_files = get_migration_files()

        if not migration_files:
            logger.info("No migration files found")
            return

        logger.info(f"Found {len(migration_files)} migration file(s)")

        for migration_file in migration_files:
            run_migration(conn, migration_file)

        logger.info("=" * 50)
        logger.info("All migrations completed successfully")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Migration process failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


def check_tables():
    """Check if required tables exist."""
    logger.info("Checking database tables...")

    conn = get_db_connection()

    if conn is None:
        logger.info("Skipping table check (mock mode)")
        return

    required_tables = [
        "predictions",
        "analysis_results",
        "accuracy_tracking",
        "daily_bias",
        "model_calibration",
        "shap_analysis",
    ]

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """
        )
        existing_tables = [row[0] for row in cursor.fetchall()]

        logger.info("Existing tables:")
        for table in existing_tables:
            logger.info(f"  - {table}")

        logger.info("\nRequired tables status:")
        all_exist = True
        for table in required_tables:
            if table in existing_tables:
                logger.info(f"  [OK] {table}")
            else:
                logger.warning(f"  [MISSING] {table}")
                all_exist = False

        if all_exist:
            logger.info("\nAll required tables exist")
        else:
            logger.warning("\nSome tables are missing. Run: make migrate")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument("--check", action="store_true", help="Check if required tables exist")
    args = parser.parse_args()

    if args.check:
        check_tables()
    else:
        run_migrations()
