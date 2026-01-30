"""
Payoff Information Query Module.

Query functions for retrieving race result payoffs (dividends).
"""

import logging
from typing import Any

from asyncpg import Connection

from src.db.table_names import (
    COL_DATA_KUBUN,
    COL_RACE_ID,
    DATA_KUBUN_KAKUTEI,
    TABLE_HARAIMODOSI,
)

logger = logging.getLogger(__name__)


async def get_race_payoffs(conn: Connection, race_id: str) -> dict[str, Any]:
    """
    Get all payoffs (dividends) for a race by ticket type.

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        {
            "win": {"kumi": "5", "payoff": 330, "ninki": 1},
            "place": [
                {"kumi": "5", "payoff": 140, "ninki": 1},
                {"kumi": "9", "payoff": 120, "ninki": 2},
                {"kumi": "4", "payoff": 130, "ninki": 3}
            ],
            "bracket_quinella": {"kumi": "3-5", "payoff": 890, "ninki": 1},
            "quinella": {"kumi": "5-9", "payoff": 450, "ninki": 1},
            "exacta": {"kumi": "5-9", "payoff": 780, "ninki": 1},
            "wide": [
                {"kumi": "5-9", "payoff": 220, "ninki": 1},
                {"kumi": "4-5", "payoff": 240, "ninki": 2},
                {"kumi": "4-9", "payoff": 200, "ninki": 3}
            ],
            "trio": {"kumi": "4-5-9", "payoff": 680, "ninki": 1},
            "trifecta": {"kumi": "5-9-4", "payoff": 2340, "ninki": 1}
        }
    """
    sql = f"""
        SELECT
            tansho1_umaban, tansho1_haraimodoshikin, tansho1_ninkijun,
            fukusho1_umaban, fukusho1_haraimodoshikin, fukusho1_ninkijun,
            fukusho2_umaban, fukusho2_haraimodoshikin, fukusho2_ninkijun,
            fukusho3_umaban, fukusho3_haraimodoshikin, fukusho3_ninkijun,
            wakuren1_kumiban1, wakuren1_kumiban2, wakuren1_haraimodoshikin, wakuren1_ninkijun,
            umaren1_kumiban1, umaren1_kumiban2, umaren1_haraimodoshikin, umaren1_ninkijun,
            umatan1_kumiban1, umatan1_kumiban2, umatan1_haraimodoshikin, umatan1_ninkijun,
            wide1_kumiban1, wide1_kumiban2, wide1_haraimodoshikin, wide1_ninkijun,
            wide2_kumiban1, wide2_kumiban2, wide2_haraimodoshikin, wide2_ninkijun,
            wide3_kumiban1, wide3_kumiban2, wide3_haraimodoshikin, wide3_ninkijun,
            sanrenpuku1_kumiban1, sanrenpuku1_kumiban2, sanrenpuku1_kumiban3,
            sanrenpuku1_haraimodoshikin, sanrenpuku1_ninkijun,
            sanrentan1_kumiban1, sanrentan1_kumiban2, sanrentan1_kumiban3,
            sanrentan1_haraimodoshikin, sanrentan1_ninkijun
        FROM {TABLE_HARAIMODOSI}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
    """

    try:
        # First try finalized data (data_kubun=7), then preliminary data (data_kubun=2)
        row = await conn.fetchrow(sql, race_id, DATA_KUBUN_KAKUTEI)

        if not row:
            # If finalized data is not available, get preliminary data
            row = await conn.fetchrow(sql, race_id, "2")

        if not row:
            return {}

        result: dict[str, Any] = {}

        # Win
        if row["tansho1_umaban"]:
            result["win"] = {
                "kumi": row["tansho1_umaban"].strip(),
                "payoff": (
                    int(row["tansho1_haraimodoshikin"]) if row["tansho1_haraimodoshikin"] else 0
                ),
                "ninki": int(row["tansho1_ninkijun"]) if row["tansho1_ninkijun"] else 0,
            }

        # Place
        place_list = []
        for i in range(1, 4):
            umaban_col = f"fukusho{i}_umaban"
            kin_col = f"fukusho{i}_haraimodoshikin"
            ninki_col = f"fukusho{i}_ninkijun"
            if row[umaban_col]:
                place_list.append(
                    {
                        "kumi": row[umaban_col].strip(),
                        "payoff": int(row[kin_col]) if row[kin_col] else 0,
                        "ninki": int(row[ninki_col]) if row[ninki_col] else 0,
                    }
                )
        if place_list:
            result["place"] = place_list

        # Bracket quinella
        if row["wakuren1_kumiban1"] and row["wakuren1_kumiban2"]:
            kumi = f"{row['wakuren1_kumiban1'].strip()}-{row['wakuren1_kumiban2'].strip()}"
            result["bracket_quinella"] = {
                "kumi": kumi,
                "payoff": (
                    int(row["wakuren1_haraimodoshikin"]) if row["wakuren1_haraimodoshikin"] else 0
                ),
                "ninki": int(row["wakuren1_ninkijun"]) if row["wakuren1_ninkijun"] else 0,
            }

        # Quinella
        if row["umaren1_kumiban1"] and row["umaren1_kumiban2"]:
            kumi = f"{row['umaren1_kumiban1'].strip()}-{row['umaren1_kumiban2'].strip()}"
            result["quinella"] = {
                "kumi": kumi,
                "payoff": (
                    int(row["umaren1_haraimodoshikin"]) if row["umaren1_haraimodoshikin"] else 0
                ),
                "ninki": int(row["umaren1_ninkijun"]) if row["umaren1_ninkijun"] else 0,
            }

        # Exacta
        if row["umatan1_kumiban1"] and row["umatan1_kumiban2"]:
            kumi = f"{row['umatan1_kumiban1'].strip()}→{row['umatan1_kumiban2'].strip()}"
            result["exacta"] = {
                "kumi": kumi,
                "payoff": (
                    int(row["umatan1_haraimodoshikin"]) if row["umatan1_haraimodoshikin"] else 0
                ),
                "ninki": int(row["umatan1_ninkijun"]) if row["umatan1_ninkijun"] else 0,
            }

        # Wide
        wide_list = []
        for i in range(1, 4):
            kumi1_col = f"wide{i}_kumiban1"
            kumi2_col = f"wide{i}_kumiban2"
            kin_col = f"wide{i}_haraimodoshikin"
            ninki_col = f"wide{i}_ninkijun"
            if row[kumi1_col] and row[kumi2_col]:
                kumi = f"{row[kumi1_col].strip()}-{row[kumi2_col].strip()}"
                wide_list.append(
                    {
                        "kumi": kumi,
                        "payoff": int(row[kin_col]) if row[kin_col] else 0,
                        "ninki": int(row[ninki_col]) if row[ninki_col] else 0,
                    }
                )
        if wide_list:
            result["wide"] = wide_list

        # Trio
        if (
            row["sanrenpuku1_kumiban1"]
            and row["sanrenpuku1_kumiban2"]
            and row["sanrenpuku1_kumiban3"]
        ):
            kumi = f"{row['sanrenpuku1_kumiban1'].strip()}-{row['sanrenpuku1_kumiban2'].strip()}-{row['sanrenpuku1_kumiban3'].strip()}"
            result["trio"] = {
                "kumi": kumi,
                "payoff": (
                    int(row["sanrenpuku1_haraimodoshikin"])
                    if row["sanrenpuku1_haraimodoshikin"]
                    else 0
                ),
                "ninki": int(row["sanrenpuku1_ninkijun"]) if row["sanrenpuku1_ninkijun"] else 0,
            }

        # Trifecta
        if row["sanrentan1_kumiban1"] and row["sanrentan1_kumiban2"] and row["sanrentan1_kumiban3"]:
            kumi = f"{row['sanrentan1_kumiban1'].strip()}→{row['sanrentan1_kumiban2'].strip()}→{row['sanrentan1_kumiban3'].strip()}"
            result["trifecta"] = {
                "kumi": kumi,
                "payoff": (
                    int(row["sanrentan1_haraimodoshikin"])
                    if row["sanrentan1_haraimodoshikin"]
                    else 0
                ),
                "ninki": int(row["sanrentan1_ninkijun"]) if row["sanrentan1_ninkijun"] else 0,
            }

        return result

    except Exception as e:
        logger.error(f"Failed to get race payoffs: race_id={race_id}, error={e}")
        raise


async def get_race_results(conn: Connection, race_id: str) -> list[dict[str, Any]]:
    """
    Get race results (entry list with finishing positions).

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        [
            {
                "chakujun": 1,
                "umaban": 5,
                "bamei": "レガレイラ",
                "kishumei": "Ｃ．ルメール",
                "time": "2301",
                "odds": 3.3
            },
            ...
        ]
    """
    from src.db.table_names import (
        COL_BAMEI,
        COL_KAKUTEI_CHAKUJUN,
        COL_KETTONUM,
        COL_TIME,
        COL_UMABAN,
        TABLE_UMA,
        TABLE_UMA_RACE,
    )

    sql = f"""
        SELECT
            se.{COL_UMABAN},
            se.{COL_KAKUTEI_CHAKUJUN},
            um.{COL_BAMEI},
            se.kishumei_ryakusho,
            se.{COL_TIME},
            se.tansho_odds,
            se.kohan_3f
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_UMA} um ON se.{COL_KETTONUM} = um.{COL_KETTONUM}
        WHERE se.{COL_RACE_ID} = $1
          AND se.{COL_DATA_KUBUN} = $2
          AND se.{COL_KAKUTEI_CHAKUJUN} != '' AND se.{COL_KAKUTEI_CHAKUJUN} != '00'
        ORDER BY CAST(se.{COL_KAKUTEI_CHAKUJUN} AS INTEGER)
    """

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_KAKUTEI)

        results = []
        for row in rows:
            # Convert finishing position to int (stored as string)
            try:
                chakujun = int(row[COL_KAKUTEI_CHAKUJUN]) if row[COL_KAKUTEI_CHAKUJUN] else 0
            except (ValueError, TypeError):
                chakujun = 0

            results.append(
                {
                    "chakujun": chakujun,
                    "umaban": int(row[COL_UMABAN]) if row[COL_UMABAN] else 0,
                    "bamei": row[COL_BAMEI].strip() if row[COL_BAMEI] else "",
                    "kishumei": (
                        row["kishumei_ryakusho"].strip() if row["kishumei_ryakusho"] else ""
                    ),
                    "time": row[COL_TIME].strip() if row[COL_TIME] else "",
                    "odds": float(row["tansho_odds"]) / 10.0 if row["tansho_odds"] else None,
                    "kohan_3f": row["kohan_3f"].strip() if row.get("kohan_3f") else None,
                }
            )

        return results

    except Exception as e:
        logger.error(f"Failed to get race results: race_id={race_id}, error={e}")
        raise


async def get_race_lap_times(conn: Connection, race_id: str) -> list[str]:
    """
    Get race lap times (per 200m).

    Args:
        conn: Database connection.
        race_id: Race ID (16 digits).

    Returns:
        List of lap times (e.g., ["123", "115", "118", ...]).
    """
    from src.db.table_names import TABLE_RACE

    sql = f"""
        SELECT
            lap_time1, lap_time2, lap_time3, lap_time4, lap_time5,
            lap_time6, lap_time7, lap_time8, lap_time9, lap_time10,
            lap_time11, lap_time12, lap_time13, lap_time14, lap_time15,
            lap_time16, lap_time17, lap_time18, lap_time19, lap_time20,
            lap_time21, lap_time22, lap_time23, lap_time24, lap_time25
        FROM {TABLE_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
    """

    try:
        row = await conn.fetchrow(sql, race_id, DATA_KUBUN_KAKUTEI)

        if not row:
            return []

        # Collect lap times (non-empty values only)
        lap_times = []
        for i in range(1, 26):
            lap_col = f"lap_time{i}"
            if row.get(lap_col) and row[lap_col].strip() not in ("", "0", "00", "000"):
                lap_times.append(row[lap_col].strip())
            else:
                break  # Stop at the first empty lap

        return lap_times

    except Exception as e:
        logger.error(f"Failed to get race lap times: race_id={race_id}, error={e}")
        return []  # Return empty list on error
