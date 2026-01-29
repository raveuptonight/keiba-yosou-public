"""
オッズ情報エンドポイント
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Path, Query, status

from src.api.exceptions import DatabaseErrorException, RaceNotFoundException
from src.api.schemas.odds import CombinationOdds, OddsResponse, SingleOdds
from src.db.async_connection import get_connection
from src.db.queries.odds_queries import (
    get_odds_exacta,
    get_odds_quinella,
    get_odds_trifecta,
    get_odds_trio,
    get_odds_wide,
    get_odds_win_place,
)
from src.db.queries.race_queries import check_race_exists

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/odds/{race_id}",
    response_model=OddsResponse,
    status_code=status.HTTP_200_OK,
    summary="オッズ情報取得",
    description="レースのオッズ情報を取得します。券種を指定可能。"
)
async def get_odds(
    race_id: str = Path(
        ...,
        min_length=16,
        max_length=16,
        description="レースID（16桁）"
    ),
    ticket_type: str = Query(
        "win",
        description="券種（win/place/quinella/exacta/wide/trio/trifecta）"
    )
) -> OddsResponse:
    """
    オッズ情報を取得

    Args:
        race_id: レースID（16桁）
        ticket_type: 券種

    Returns:
        OddsResponse: オッズ情報

    Raises:
        RaceNotFoundException: レースが見つからない
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /odds/{race_id}?ticket_type={ticket_type}")

    try:
        async with get_connection() as conn:
            # レース存在チェック
            exists = await check_race_exists(conn, race_id)
            if not exists:
                logger.warning(f"Race not found: {race_id}")
                raise RaceNotFoundException(race_id)

            odds_data = []

            # 券種に応じてオッズを取得
            if ticket_type == "win":
                # 単勝オッズ
                win_place = await get_odds_win_place(conn, race_id)
                odds_data = [
                    SingleOdds(horse_number=o["umaban"], odds=o["odds"])
                    for o in win_place["win"]
                ]

            elif ticket_type == "place":
                # 複勝オッズ
                win_place = await get_odds_win_place(conn, race_id)
                # 複勝は範囲があるため、中央値を返す
                odds_data = [
                    SingleOdds(
                        horse_number=o["umaban"],
                        odds=(o["odds_min"] + o["odds_max"]) / 2
                    )
                    for o in win_place["place"]
                ]

            elif ticket_type == "quinella":
                # 馬連オッズ
                quinella = await get_odds_quinella(conn, race_id, limit=100)
                odds_data = [
                    CombinationOdds(
                        numbers=[o["umaban1"], o["umaban2"]],
                        odds=o["odds"]
                    )
                    for o in quinella
                ]

            elif ticket_type == "exacta":
                # 馬単オッズ
                exacta = await get_odds_exacta(conn, race_id, limit=100)
                odds_data = [
                    CombinationOdds(
                        numbers=[o["umaban1"], o["umaban2"]],
                        odds=o["odds"]
                    )
                    for o in exacta
                ]

            elif ticket_type == "wide":
                # ワイドオッズ
                wide = await get_odds_wide(conn, race_id, limit=100)
                # ワイドも範囲があるため、中央値を返す
                odds_data = [
                    CombinationOdds(
                        numbers=[o["umaban1"], o["umaban2"]],
                        odds=(o["odds_min"] + o["odds_max"]) / 2
                    )
                    for o in wide
                ]

            elif ticket_type == "trio":
                # 3連複オッズ
                trio = await get_odds_trio(conn, race_id, limit=100)
                odds_data = [
                    CombinationOdds(
                        numbers=[o["umaban1"], o["umaban2"], o["umaban3"]],
                        odds=o["odds"]
                    )
                    for o in trio
                ]

            elif ticket_type == "trifecta":
                # 3連単オッズ
                trifecta = await get_odds_trifecta(conn, race_id, limit=100)
                odds_data = [
                    CombinationOdds(
                        numbers=[o["umaban1"], o["umaban2"], o["umaban3"]],
                        odds=o["odds"]
                    )
                    for o in trifecta
                ]

            else:
                logger.warning(f"Invalid ticket type: {ticket_type}")
                from src.api.exceptions import InvalidRequestException
                raise InvalidRequestException(
                    f"不正な券種です: {ticket_type}。"
                    f"有効な券種: win/place/quinella/exacta/wide/trio/trifecta"
                )

            response = OddsResponse(
                race_id=race_id,
                ticket_type=ticket_type,
                updated_at=datetime.now(),
                odds=odds_data
            )

            logger.info(f"Odds retrieved: {len(odds_data)} items for {ticket_type}")
            return response

    except RaceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Failed to get odds: {e}")
        raise DatabaseErrorException(str(e)) from e
