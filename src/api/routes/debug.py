"""
Debug endpoints (remove in production).
"""

import logging
from typing import Any

from fastapi import APIRouter

from src.db.async_connection import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/debug/schema/{table_name}")
async def get_table_schema(table_name: str):
    """Get table schema (for debugging)."""
    async with get_connection() as conn:
        # Get table schema
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position;
        """,
            table_name,
        )

        if not rows:
            return {"error": f"Table '{table_name}' not found"}

        columns = []
        for row in rows:
            columns.append(
                {
                    "column_name": row["column_name"],
                    "data_type": row["data_type"],
                    "max_length": row["character_maximum_length"],
                }
            )

        # Get sample data
        sample_data: dict[str, Any] | str | None = None
        try:
            sample = await conn.fetchrow(f"SELECT * FROM {table_name} LIMIT 1")
            sample_data = dict(sample) if sample else None
        except Exception as e:
            sample_data = f"Error: {e}"

        return {"table_name": table_name, "columns": columns, "sample_data": sample_data}
