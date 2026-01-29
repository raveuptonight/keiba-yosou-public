"""
予想データ集約クエリモジュール

予想生成に必要な全データを27テーブルから効率的に集約するクエリ群
API_DESIGN.mdの「データ集約クエリ」セクションに基づいて実装
"""

import logging
from typing import Any

from asyncpg import Connection

from src.db.queries.horse_queries import (
    get_horses_pedigree,
    get_horses_recent_races,
    get_horses_statistics,
    get_horses_training,
)
from src.db.queries.odds_queries import (
    get_race_odds,
)
from src.db.queries.race_queries import (
    get_race_entries,
    get_race_info,
)
from src.db.table_names import COL_KETTONUM, COL_RACE_NAME

logger = logging.getLogger(__name__)


async def get_race_prediction_data(conn: Connection, race_id: str) -> dict[str, Any]:
    """
    予想生成に必要な全データを集約

    27テーブルからレース予想に必要な全情報を一括取得します。
    API_DESIGN.mdの「データ集約クエリ」セクションに記載された処理フローに従います。

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        {
            "race": {...},           # レース基本情報（RA）
            "horses": [...],         # 出走馬情報（SE, UM）
            "histories": {...},      # 各馬の過去10走（SE + RA）
            "pedigrees": {...},      # 血統情報（SK, HN）
            "training": {...},       # 調教情報（HC, WC）
            "statistics": {...},     # 着度数統計（CK）
            "odds": {...}            # オッズ情報（O1-O6）
        }

    Raises:
        ValueError: レースが見つからない場合
    """
    logger.info(f"Starting data aggregation for race_id={race_id}")

    # 1. レース基本情報取得（RA）
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        raise ValueError(f"Race not found: race_id={race_id}")

    logger.debug(f"Race info retrieved: {race_info[COL_RACE_NAME]}")

    # 2. 出走馬一覧取得（SE, UM, KS, CH, O1）
    horses = await get_race_entries(conn, race_id)
    if not horses:
        logger.warning(f"No horses found for race_id={race_id}")
        return {
            "race": race_info,
            "horses": [],
            "histories": {},
            "pedigrees": {},
            "training": {},
            "statistics": {},
            "odds": {},
        }

    logger.debug(f"Found {len(horses)} horses")

    # 3. 血統登録番号リストを抽出
    kettonums = [horse[COL_KETTONUM] for horse in horses]

    logger.debug(f"Extracted {len(kettonums)} kettonums")

    # 4. 並列データ取得（各馬の詳細データ）
    # 4.1 過去成績（SE + RA: 過去10走）
    logger.debug("Fetching horse histories...")
    histories = await get_horses_recent_races(conn, kettonums, limit=10)

    # 4.2 血統情報（SK, HN）
    logger.debug("Fetching pedigrees...")
    pedigrees = await get_horses_pedigree(conn, kettonums)

    # 4.3 調教情報（HC, WC: 最新1ヶ月）
    logger.debug("Fetching training data...")
    training = await get_horses_training(conn, kettonums, days_back=30)

    # 4.4 着度数統計（CK）
    logger.debug("Fetching statistics...")
    statistics = await get_horses_statistics(conn, race_id, kettonums)

    # 5. オッズ情報取得（O1-O6）
    logger.debug("Fetching odds data...")
    odds = await get_race_odds(conn, race_id)

    logger.info(f"Data aggregation completed for race_id={race_id}")

    return {
        "race": race_info,
        "horses": horses,
        "histories": histories,
        "pedigrees": pedigrees,
        "training": training,
        "statistics": statistics,
        "odds": odds,
    }


async def get_multiple_races_prediction_data(
    conn: Connection, race_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """
    複数レースの予想データを一括取得

    Args:
        conn: データベース接続
        race_ids: レースIDのリスト

    Returns:
        Dict[race_id, 予想データ]
    """
    result = {}

    for race_id in race_ids:
        try:
            data = await get_race_prediction_data(conn, race_id)
            result[race_id] = data
        except ValueError as e:
            logger.warning(f"Skipping race_id={race_id}: {e}")
            continue
        except Exception as e:
            logger.error(f"Failed to get prediction data for race_id={race_id}: {e}")
            raise

    return result


async def get_race_prediction_data_slim(conn: Connection, race_id: str) -> dict[str, Any]:
    """
    予想データの軽量版を取得（過去成績を5走に制限）

    朝予想など、データ量を抑えたい場合に使用します。

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        予想データ（histories は各馬5走まで）
    """
    logger.info(f"Starting slim data aggregation for race_id={race_id}")

    # レース基本情報
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        raise ValueError(f"Race not found: race_id={race_id}")

    # 出走馬一覧
    horses = await get_race_entries(conn, race_id)
    if not horses:
        return {
            "race": race_info,
            "horses": [],
            "histories": {},
            "pedigrees": {},
            "training": {},
            "statistics": {},
            "odds": {},
        }

    from src.db.table_names import COL_KETTONUM

    kettonums = [horse[COL_KETTONUM] for horse in horses]

    # 過去成績は5走まで
    histories = await get_horses_recent_races(conn, kettonums, limit=5)

    # 血統情報
    pedigrees = await get_horses_pedigree(conn, kettonums)

    # 調教情報（最新3本まで）
    training = await get_horses_training(conn, kettonums, days_back=14)

    # 着度数統計
    statistics = await get_horses_statistics(conn, race_id, kettonums)

    # オッズ情報（単勝・複勝のみ）
    odds = await get_race_odds(conn, race_id, ticket_types=["win", "place"])

    logger.info(f"Slim data aggregation completed for race_id={race_id}")

    return {
        "race": race_info,
        "horses": horses,
        "histories": histories,
        "pedigrees": pedigrees,
        "training": training,
        "statistics": statistics,
        "odds": odds,
    }


async def validate_prediction_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    予想データの整合性をチェック

    Args:
        data: get_race_prediction_data() の返り値

    Returns:
        {
            "is_valid": bool,
            "warnings": List[str],
            "missing_data": Dict[str, List[str]]
        }
    """
    warnings = []
    missing_data = {"histories": [], "pedigrees": [], "training": [], "statistics": []}

    from src.db.table_names import COL_BAMEI, COL_KETTONUM

    # 出走馬がいるかチェック
    if not data.get("horses"):
        warnings.append("No horses found")
        return {"is_valid": False, "warnings": warnings, "missing_data": missing_data}

    # 各馬のデータ完全性チェック
    for horse in data["horses"]:
        kettonum = horse[COL_KETTONUM]
        horse_name = horse[COL_BAMEI]

        # 過去成績がない馬
        if kettonum not in data["histories"] or not data["histories"][kettonum]:
            missing_data["histories"].append(horse_name)
            warnings.append(f"No race history for {horse_name}")

        # 血統情報がない馬
        if kettonum not in data["pedigrees"]:
            missing_data["pedigrees"].append(horse_name)
            warnings.append(f"No pedigree data for {horse_name}")

        # 調教情報がない馬
        if kettonum not in data["training"] or not data["training"][kettonum]:
            missing_data["training"].append(horse_name)
            warnings.append(f"No training data for {horse_name}")

        # 着度数統計がない馬
        if kettonum not in data["statistics"]:
            missing_data["statistics"].append(horse_name)
            warnings.append(f"No statistics data for {horse_name}")

    # オッズ情報がない場合
    if not data.get("odds") or not data["odds"].get("win"):
        warnings.append("No odds data available")

    # 警告があってもデータ取得自体は成功とみなす
    is_valid = len(data["horses"]) > 0

    return {"is_valid": is_valid, "warnings": warnings, "missing_data": missing_data}


async def get_prediction_data_summary(data: dict[str, Any]) -> dict[str, Any]:
    """
    予想データのサマリー情報を生成

    Args:
        data: get_race_prediction_data() の返り値

    Returns:
        {
            "race_name": str,
            "venue": str,
            "distance": int,
            "entry_count": int,
            "data_completeness": {
                "histories": float,  # 0.0 - 1.0
                "pedigrees": float,
                "training": float,
                "statistics": float,
                "odds": bool
            }
        }
    """
    from src.db.table_names import (
        COL_JYOCD,
        COL_KETTONUM,
        COL_KYORI,
        COL_RACE_NAME,
    )

    race_info = data.get("race", {})
    horses = data.get("horses", [])
    entry_count = len(horses)

    if entry_count == 0:
        return {
            "race_name": race_info.get(COL_RACE_NAME, "Unknown"),
            "venue": race_info.get(COL_JYOCD, "Unknown"),
            "distance": race_info.get(COL_KYORI, 0),
            "entry_count": 0,
            "data_completeness": {
                "histories": 0.0,
                "pedigrees": 0.0,
                "training": 0.0,
                "statistics": 0.0,
                "odds": False,
            },
        }

    # データ完全性の計算
    kettonums = [h[COL_KETTONUM] for h in horses]

    histories_count = sum(
        1 for k in kettonums if k in data.get("histories", {}) and data["histories"][k]
    )
    pedigrees_count = sum(1 for k in kettonums if k in data.get("pedigrees", {}))
    training_count = sum(
        1 for k in kettonums if k in data.get("training", {}) and data["training"][k]
    )
    statistics_count = sum(1 for k in kettonums if k in data.get("statistics", {}))

    return {
        "race_name": race_info.get(COL_RACE_NAME, "Unknown"),
        "venue": race_info.get(COL_JYOCD, "Unknown"),
        "distance": race_info.get(COL_KYORI, 0),
        "entry_count": entry_count,
        "data_completeness": {
            "histories": histories_count / entry_count,
            "pedigrees": pedigrees_count / entry_count,
            "training": training_count / entry_count,
            "statistics": statistics_count / entry_count,
            "odds": bool(data.get("odds", {}).get("win")),
        },
    }
