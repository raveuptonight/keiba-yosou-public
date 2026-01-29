"""
騎手・調教師情報エンドポイント
"""

import logging

from fastapi import APIRouter, Path, Query, status

from src.api.exceptions import DatabaseErrorException
from src.api.schemas.jockey import (
    DistanceCategoryStats,
    JockeyBasicInfo,
    JockeySearchResult,
    JockeyStats,
    OverallStats,
    SurfaceStats,
    TopJockey,
    TrainerBasicInfo,
    TrainerSearchResult,
    TrainerStats,
    VenueStats,
)
from src.db.async_connection import get_connection
from src.db.queries.jockey_queries import (
    get_jockey_stats,
    get_trainer_stats,
    search_jockeys_by_name,
    search_trainers_by_name,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_affiliation_name(tozai_code: str) -> str:
    """所属コードから名称を取得"""
    affiliation_map = {"1": "美浦", "2": "栗東"}
    return affiliation_map.get(tozai_code, "不明")


def _get_venue_name(venue_code: str) -> str:
    """競馬場コードから名称を取得"""
    venue_map = {
        "01": "札幌",
        "02": "函館",
        "03": "福島",
        "04": "新潟",
        "05": "東京",
        "06": "中山",
        "07": "中京",
        "08": "京都",
        "09": "阪神",
        "10": "小倉",
    }
    return venue_map.get(venue_code, "不明")


def _get_distance_category_name(category: str) -> str:
    """距離カテゴリから名称を取得"""
    category_map = {
        "sprint": "短距離（〜1400m）",
        "mile": "マイル（1401-1800m）",
        "middle": "中距離（1801-2200m）",
        "long": "長距離（2201m〜）",
    }
    return category_map.get(category, "不明")


@router.get(
    "/jockeys/search",
    response_model=list[JockeySearchResult],
    status_code=status.HTTP_200_OK,
    summary="騎手名検索",
    description="騎手名で検索します（部分一致）。",
)
async def search_jockeys(
    name: str = Query(..., min_length=1, description="検索する騎手名（部分一致）"),
    limit: int = Query(
        10, ge=1, le=50, description="取得件数上限（デフォルト: 10）"
    ),
) -> list[JockeySearchResult]:
    """
    騎手名で検索

    Args:
        name: 検索する騎手名
        limit: 取得件数上限

    Returns:
        List[JockeySearchResult]: 検索結果リスト
    """
    logger.info(f"GET /jockeys/search: name={name}, limit={limit}")

    try:
        async with get_connection() as conn:
            results = await search_jockeys_by_name(conn, name, limit)

            jockeys = [
                JockeySearchResult(
                    kishu_code=row["kishu_code"],
                    name=row["name"].strip() if row["name"] else "",
                    name_short=row["name_short"].strip()
                    if row["name_short"]
                    else "",
                    affiliation=_get_affiliation_name(
                        row.get("tozai_shozoku_code", "1")
                    ),
                )
                for row in results
            ]

            logger.info(f"Found {len(jockeys)} jockeys matching '{name}'")
            return jockeys

    except Exception as e:
        logger.error(f"Failed to search jockeys: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/jockeys/{kishu_code}",
    response_model=JockeyStats,
    status_code=status.HTTP_200_OK,
    summary="騎手詳細統計取得",
    description="騎手の詳細統計情報を取得します。",
)
async def get_jockey(
    kishu_code: str = Path(
        ..., min_length=5, max_length=5, description="騎手コード（5桁）"
    )
) -> JockeyStats:
    """
    騎手の詳細統計を取得

    Args:
        kishu_code: 騎手コード

    Returns:
        JockeyStats: 騎手詳細統計

    Raises:
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /jockeys/{kishu_code}")

    try:
        async with get_connection() as conn:
            data = await get_jockey_stats(conn, kishu_code)

            if not data:
                raise DatabaseErrorException(f"Jockey not found: {kishu_code}")

            basic_info = data["basic_info"]
            overall = data["overall_stats"]
            distance_data = data["distance_stats"]
            venue_data = data["venue_stats"]

            # 勝率計算
            total_races = overall["total_races"] or 0
            wins = overall["wins"] or 0
            top2 = overall["top2"] or 0
            top3 = overall["top3"] or 0

            win_rate = wins / total_races if total_races > 0 else 0.0
            top2_rate = top2 / total_races if total_races > 0 else 0.0
            top3_rate = top3 / total_races if total_races > 0 else 0.0

            # 芝/ダート勝率
            turf_races = overall["turf_races"] or 0
            turf_wins = overall["turf_wins"] or 0
            dirt_races = overall["dirt_races"] or 0
            dirt_wins = overall["dirt_wins"] or 0

            turf_win_rate = turf_wins / turf_races if turf_races > 0 else 0.0
            dirt_win_rate = dirt_wins / dirt_races if dirt_races > 0 else 0.0

            # レスポンス作成
            response = JockeyStats(
                basic_info=JockeyBasicInfo(
                    kishu_code=basic_info["kishu_code"],
                    name=basic_info["name"],
                    name_short=basic_info["name_short"],
                    affiliation=_get_affiliation_name(
                        basic_info.get("tozai_shozoku_code", "1")
                    ),
                    birth_date=basic_info.get("birth_date"),
                    license_date=basic_info.get("license_date"),
                ),
                overall_stats=OverallStats(
                    total_races=total_races,
                    wins=wins,
                    top2=top2,
                    top3=top3,
                    win_rate=win_rate,
                    top2_rate=top2_rate,
                    top3_rate=top3_rate,
                ),
                surface_stats=SurfaceStats(
                    turf_races=turf_races,
                    turf_wins=turf_wins,
                    turf_win_rate=turf_win_rate,
                    dirt_races=dirt_races,
                    dirt_wins=dirt_wins,
                    dirt_win_rate=dirt_win_rate,
                ),
                distance_stats=[
                    DistanceCategoryStats(
                        category=_get_distance_category_name(d["distance_category"]),
                        races=d["races"],
                        wins=d["wins"],
                        win_rate=d["wins"] / d["races"] if d["races"] > 0 else 0.0,
                    )
                    for d in distance_data
                ],
                venue_stats=[
                    VenueStats(
                        venue=_get_venue_name(v["venue_code"]),
                        venue_code=v["venue_code"],
                        races=v["races"],
                        wins=v["wins"],
                        win_rate=v["wins"] / v["races"] if v["races"] > 0 else 0.0,
                    )
                    for v in venue_data[:5]
                ],
            )

            logger.info(f"Jockey stats retrieved: {basic_info['name']}")
            return response

    except Exception as e:
        logger.error(f"Failed to get jockey stats: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/trainers/search",
    response_model=list[TrainerSearchResult],
    status_code=status.HTTP_200_OK,
    summary="調教師名検索",
    description="調教師名で検索します（部分一致）。",
)
async def search_trainers(
    name: str = Query(..., min_length=1, description="検索する調教師名（部分一致）"),
    limit: int = Query(
        10, ge=1, le=50, description="取得件数上限（デフォルト: 10）"
    ),
) -> list[TrainerSearchResult]:
    """
    調教師名で検索

    Args:
        name: 検索する調教師名
        limit: 取得件数上限

    Returns:
        List[TrainerSearchResult]: 検索結果リスト
    """
    logger.info(f"GET /trainers/search: name={name}, limit={limit}")

    try:
        async with get_connection() as conn:
            results = await search_trainers_by_name(conn, name, limit)

            trainers = [
                TrainerSearchResult(
                    chokyoshi_code=row["chokyoshi_code"],
                    name=row["name"].strip() if row["name"] else "",
                    name_short=row["name_short"].strip()
                    if row["name_short"]
                    else "",
                    affiliation=_get_affiliation_name(
                        row.get("tozai_shozoku_code", "1")
                    ),
                )
                for row in results
            ]

            logger.info(f"Found {len(trainers)} trainers matching '{name}'")
            return trainers

    except Exception as e:
        logger.error(f"Failed to search trainers: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/trainers/{chokyoshi_code}",
    response_model=TrainerStats,
    status_code=status.HTTP_200_OK,
    summary="調教師詳細統計取得",
    description="調教師の詳細統計情報を取得します。",
)
async def get_trainer(
    chokyoshi_code: str = Path(
        ..., min_length=5, max_length=5, description="調教師コード（5桁）"
    )
) -> TrainerStats:
    """
    調教師の詳細統計を取得

    Args:
        chokyoshi_code: 調教師コード

    Returns:
        TrainerStats: 調教師詳細統計

    Raises:
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /trainers/{chokyoshi_code}")

    try:
        async with get_connection() as conn:
            data = await get_trainer_stats(conn, chokyoshi_code)

            if not data:
                raise DatabaseErrorException(
                    f"Trainer not found: {chokyoshi_code}"
                )

            basic_info = data["basic_info"]
            overall = data["overall_stats"]
            distance_data = data["distance_stats"]
            venue_data = data["venue_stats"]
            top_jockeys_data = data["top_jockeys"]

            # 勝率計算
            total_races = overall["total_races"] or 0
            wins = overall["wins"] or 0
            top2 = overall["top2"] or 0
            top3 = overall["top3"] or 0

            win_rate = wins / total_races if total_races > 0 else 0.0
            top2_rate = top2 / total_races if total_races > 0 else 0.0
            top3_rate = top3 / total_races if total_races > 0 else 0.0

            # 芝/ダート勝率
            turf_races = overall["turf_races"] or 0
            turf_wins = overall["turf_wins"] or 0
            dirt_races = overall["dirt_races"] or 0
            dirt_wins = overall["dirt_wins"] or 0

            turf_win_rate = turf_wins / turf_races if turf_races > 0 else 0.0
            dirt_win_rate = dirt_wins / dirt_races if dirt_races > 0 else 0.0

            # レスポンス作成
            response = TrainerStats(
                basic_info=TrainerBasicInfo(
                    chokyoshi_code=basic_info["chokyoshi_code"],
                    name=basic_info["name"],
                    name_short=basic_info["name_short"],
                    affiliation=_get_affiliation_name(
                        basic_info.get("tozai_shozoku_code", "1")
                    ),
                    birth_date=basic_info.get("birth_date"),
                    license_date=basic_info.get("license_date"),
                ),
                overall_stats=OverallStats(
                    total_races=total_races,
                    wins=wins,
                    top2=top2,
                    top3=top3,
                    win_rate=win_rate,
                    top2_rate=top2_rate,
                    top3_rate=top3_rate,
                ),
                surface_stats=SurfaceStats(
                    turf_races=turf_races,
                    turf_wins=turf_wins,
                    turf_win_rate=turf_win_rate,
                    dirt_races=dirt_races,
                    dirt_wins=dirt_wins,
                    dirt_win_rate=dirt_win_rate,
                ),
                distance_stats=[
                    DistanceCategoryStats(
                        category=_get_distance_category_name(d["distance_category"]),
                        races=d["races"],
                        wins=d["wins"],
                        win_rate=d["wins"] / d["races"] if d["races"] > 0 else 0.0,
                    )
                    for d in distance_data
                ],
                venue_stats=[
                    VenueStats(
                        venue=_get_venue_name(v["venue_code"]),
                        venue_code=v["venue_code"],
                        races=v["races"],
                        wins=v["wins"],
                        win_rate=v["wins"] / v["races"] if v["races"] > 0 else 0.0,
                    )
                    for v in venue_data[:5]
                ],
                top_jockeys=[
                    TopJockey(
                        kishu_code=j["kishu_code"],
                        jockey_name=j["jockey_name"],
                        rides=j["rides"],
                        wins=j["wins"],
                        win_rate=j["wins"] / j["rides"] if j["rides"] > 0 else 0.0,
                    )
                    for j in top_jockeys_data
                ],
            )

            logger.info(f"Trainer stats retrieved: {basic_info['name']}")
            return response

    except Exception as e:
        logger.error(f"Failed to get trainer stats: {e}")
        raise DatabaseErrorException(str(e))
