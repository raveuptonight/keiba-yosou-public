"""
騎手情報エンドポイント
"""

import logging
from typing import List
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from src.api.exceptions import DatabaseErrorException
from src.db.async_connection import get_connection
from src.db.table_names import TABLE_KISYU, TABLE_UMA_RACE

logger = logging.getLogger(__name__)

router = APIRouter()


class JockeySearchResult(BaseModel):
    """騎手検索結果"""
    code: str = Field(..., description="騎手コード")
    name: str = Field(..., description="騎手名")
    win_rate: float = Field(0.0, ge=0.0, le=1.0, description="勝率")
    place_rate: float = Field(0.0, ge=0.0, le=1.0, description="複勝率")
    total_rides: int = Field(0, ge=0, description="騎乗数")
    wins: int = Field(0, ge=0, description="勝利数")


@router.get(
    "/jockeys/search",
    response_model=List[JockeySearchResult],
    status_code=status.HTTP_200_OK,
    summary="騎手名検索",
    description="騎手名で騎手を検索します（部分一致）。"
)
async def search_jockeys(
    name: str = Query(
        ...,
        min_length=1,
        description="検索する騎手名（部分一致）"
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="取得件数上限（デフォルト: 10）"
    )
) -> List[JockeySearchResult]:
    """
    騎手名で騎手を検索

    Args:
        name: 検索する騎手名
        limit: 取得件数上限

    Returns:
        List[JockeySearchResult]: 検索結果リスト
    """
    logger.info(f"GET /jockeys/search: name={name}, limit={limit}")

    # 実際のカラム名を使用
    sql = f"""
        SELECT
            k.kishu_code,
            k.kishumei,
            COALESCE(stats.total_rides, 0) as total_rides,
            COALESCE(stats.wins, 0) as wins,
            COALESCE(stats.places, 0) as places
        FROM {TABLE_KISYU} k
        LEFT JOIN (
            SELECT
                kishu_code,
                COUNT(*) as total_rides,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01', '02', '03') THEN 1 ELSE 0 END) as places
            FROM {TABLE_UMA_RACE}
            WHERE data_kubun = '7'
            GROUP BY kishu_code
        ) stats ON k.kishu_code = stats.kishu_code
        WHERE k.kishumei LIKE $1 OR k.kishumei_ryakusho LIKE $1
        ORDER BY COALESCE(stats.wins, 0) DESC
        LIMIT $2
    """

    try:
        async with get_connection() as conn:
            search_pattern = f"%{name}%"
            rows = await conn.fetch(sql, search_pattern, limit)

            jockeys = []
            for row in rows:
                total = row["total_rides"] or 0
                wins = row["wins"] or 0
                places = row["places"] or 0

                jockeys.append(JockeySearchResult(
                    code=row["kishu_code"].strip() if row["kishu_code"] else "",
                    name=row["kishumei"].strip() if row["kishumei"] else "",
                    win_rate=wins / total if total > 0 else 0.0,
                    place_rate=places / total if total > 0 else 0.0,
                    total_rides=total,
                    wins=wins,
                ))

            logger.info(f"Found {len(jockeys)} jockeys matching '{name}'")
            return jockeys

    except Exception as e:
        logger.error(f"Failed to search jockeys: {e}")
        raise DatabaseErrorException(str(e))
