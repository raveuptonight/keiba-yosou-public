"""
Prediction Data Aggregation Query Module.

Query functions for efficiently aggregating all data needed for prediction
generation from 27 tables. Implementation based on the "Data Aggregation Query"
section in API_DESIGN.md.
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
    Aggregate all data needed for prediction generation.

    Retrieves all information needed for race prediction from 27 tables.
    Follows the processing flow described in the "Data Aggregation Query"
    section of API_DESIGN.md.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        {
            "race": {...},           # Race basic info (RA)
            "horses": [...],         # Entry info (SE, UM)
            "histories": {...},      # Past 10 races per horse (SE + RA)
            "pedigrees": {...},      # Pedigree info (SK, HN)
            "training": {...},       # Training info (HC, WC)
            "statistics": {...},     # Finish position stats (CK)
            "odds": {...}            # Odds info (O1-O6)
        }

    Raises:
        ValueError: If race is not found.
    """
    logger.info(f"Starting data aggregation for race_id={race_id}")

    # 1. Get race basic info (RA)
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        raise ValueError(f"Race not found: race_id={race_id}")

    logger.debug(f"Race info retrieved: {race_info[COL_RACE_NAME]}")

    # 2. Get entry list (SE, UM, KS, CH, O1)
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

    # 3. Extract pedigree registration number list
    kettonums = [horse[COL_KETTONUM] for horse in horses]

    logger.debug(f"Extracted {len(kettonums)} kettonums")

    # 4. Parallel data retrieval (detailed data for each horse)
    # 4.1 Past race history (SE + RA: last 10 races)
    logger.debug("Fetching horse histories...")
    histories = await get_horses_recent_races(conn, kettonums, limit=10)

    # 4.2 Pedigree info (SK, HN)
    logger.debug("Fetching pedigrees...")
    pedigrees = await get_horses_pedigree(conn, kettonums)

    # 4.3 Training info (HC, WC: last month)
    logger.debug("Fetching training data...")
    training = await get_horses_training(conn, kettonums, days_back=30)

    # 4.4 Finish position stats (CK)
    logger.debug("Fetching statistics...")
    statistics = await get_horses_statistics(conn, race_id, kettonums)

    # 5. Get odds info (O1-O6)
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
    Batch retrieve prediction data for multiple races.

    Args:
        conn: Database connection.
        race_ids: List of race IDs.

    Returns:
        Dict[race_id, prediction_data]
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
    Get lightweight version of prediction data (limited to 5 past races).

    Used when data volume needs to be reduced, such as for morning predictions.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        Prediction data (histories limited to 5 races per horse).
    """
    logger.info(f"Starting slim data aggregation for race_id={race_id}")

    # Race basic info
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        raise ValueError(f"Race not found: race_id={race_id}")

    # Entry list
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

    # Race history limited to 5 races
    histories = await get_horses_recent_races(conn, kettonums, limit=5)

    # Pedigree info
    pedigrees = await get_horses_pedigree(conn, kettonums)

    # Training info (up to 3 latest sessions)
    training = await get_horses_training(conn, kettonums, days_back=14)

    # Finish position stats
    statistics = await get_horses_statistics(conn, race_id, kettonums)

    # Odds info (win and place only)
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
    Check prediction data integrity.

    Args:
        data: Return value from get_race_prediction_data().

    Returns:
        {
            "is_valid": bool,
            "warnings": List[str],
            "missing_data": Dict[str, List[str]]
        }
    """
    warnings: list[str] = []
    missing_data: dict[str, list[str]] = {
        "histories": [],
        "pedigrees": [],
        "training": [],
        "statistics": [],
    }

    from src.db.table_names import COL_BAMEI, COL_KETTONUM

    # Check if there are any entries
    if not data.get("horses"):
        warnings.append("No horses found")
        return {"is_valid": False, "warnings": warnings, "missing_data": missing_data}

    # Check data completeness for each horse
    for horse in data["horses"]:
        kettonum = horse[COL_KETTONUM]
        horse_name = horse[COL_BAMEI]

        # Horse with no race history
        if kettonum not in data["histories"] or not data["histories"][kettonum]:
            missing_data["histories"].append(horse_name)
            warnings.append(f"No race history for {horse_name}")

        # Horse with no pedigree info
        if kettonum not in data["pedigrees"]:
            missing_data["pedigrees"].append(horse_name)
            warnings.append(f"No pedigree data for {horse_name}")

        # Horse with no training info
        if kettonum not in data["training"] or not data["training"][kettonum]:
            missing_data["training"].append(horse_name)
            warnings.append(f"No training data for {horse_name}")

        # Horse with no finish position stats
        if kettonum not in data["statistics"]:
            missing_data["statistics"].append(horse_name)
            warnings.append(f"No statistics data for {horse_name}")

    # No odds info available
    if not data.get("odds") or not data["odds"].get("win"):
        warnings.append("No odds data available")

    # Data retrieval is considered successful even with warnings
    is_valid = len(data["horses"]) > 0

    return {"is_valid": is_valid, "warnings": warnings, "missing_data": missing_data}


async def get_prediction_data_summary(data: dict[str, Any]) -> dict[str, Any]:
    """
    Generate summary information for prediction data.

    Args:
        data: Return value from get_race_prediction_data().

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

    # Calculate data completeness
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
