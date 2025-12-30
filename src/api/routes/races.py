"""
レース情報エンドポイント
"""

import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Query, Path, status

from src.api.schemas.race import RaceListResponse, RaceDetail, RaceBase, RaceEntry
from src.api.schemas.common import PrizeMoneyResponse
from src.api.exceptions import RaceNotFoundException, DatabaseErrorException
from src.db.async_connection import get_connection
from src.db.queries.race_queries import (
    get_races_today,
    get_races_by_date,
    get_upcoming_races,
    get_race_detail,
    get_race_entry_count,
)
from src.db.table_names import (
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_GRADE_CD,
    COL_JYOCD,
    COL_TRACK_CD,
    COL_KYORI,
    COL_RACE_NUM,
    COL_HASSO_JIKOKU,
    COL_TENKO_CD,
    COL_SHIBA_BABA_CD,
    COL_DIRT_BABA_CD,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
    COL_KETTONUM,
    COL_BAMEI,
    COL_KISYUCODE,
    COL_KISYU_NAME,
    COL_CHOKYOSICODE,
    COL_CHOKYOSI_NAME,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_venue_name(venue_code: str) -> str:
    """競馬場コードから名称を取得"""
    venue_map = {
        "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
        "05": "東京", "06": "中山", "07": "中京", "08": "京都",
        "09": "阪神", "10": "小倉"
    }
    return venue_map.get(venue_code, "不明")


def _format_track_code(track_code: str) -> str:
    """馬場コードをフォーマット"""
    if track_code.startswith("1"):
        return "芝"
    elif track_code.startswith("2"):
        return "ダート"
    return "不明"


@router.get(
    "/races/today",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="今日のレース一覧取得",
    description="本日開催のレース一覧を取得します。グレードや競馬場でフィルタ可能。"
)
async def get_today_races(
    grade: Optional[str] = Query(
        None,
        description="グレードフィルタ（A=G1, B=G2, C=G3）"
    ),
    venue: Optional[str] = Query(
        None,
        description="競馬場コード（01=札幌, 02=函館, etc.）"
    )
) -> RaceListResponse:
    """
    今日のレース一覧を取得

    Args:
        grade: グレードフィルタ（オプション）
        venue: 競馬場コード（オプション）

    Returns:
        RaceListResponse: レース一覧

    Raises:
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /races/today: grade={grade}, venue={venue}")

    try:
        async with get_connection() as conn:
            races_data = await get_races_today(conn, venue_code=venue, grade_filter=grade)

            # レスポンス用に変換
            races = []
            for race in races_data:
                # 出走頭数を取得
                entry_count = await get_race_entry_count(conn, race[COL_RACE_ID])

                races.append(RaceBase(
                    race_id=race[COL_RACE_ID],
                    race_name=race[COL_RACE_NAME],
                    race_number=f"{race[COL_RACE_NUM]}R" if race.get(COL_RACE_NUM) else "不明",
                    race_time=race.get(COL_HASSO_JIKOKU, '不明'),
                    venue=_get_venue_name(race[COL_JYOCD]),
                    venue_code=race[COL_JYOCD],
                    grade=race.get(COL_GRADE_CD),
                    distance=race[COL_KYORI],
                    track_code=race[COL_TRACK_CD],
                ))

            today = date.today()
            response = RaceListResponse(
                date=today.strftime("%Y-%m-%d"),
                races=races,
                total=len(races)
            )

            logger.info(f"Found {len(races)} races for today")
            return response

    except Exception as e:
        logger.error(f"Failed to get today's races: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/races/upcoming",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="今後のレース一覧取得",
    description="今後開催予定のレース一覧を取得します。"
)
async def get_upcoming_races_list(
    days: int = Query(
        7,
        ge=1,
        le=30,
        description="何日先まで取得するか（1-30日）"
    ),
    grade: Optional[str] = Query(
        None,
        description="グレードフィルタ（A=G1, B=G2, C=G3）"
    )
) -> RaceListResponse:
    """
    今後のレース一覧を取得

    Args:
        days: 何日先まで取得するか（デフォルト7日）
        grade: グレードフィルタ（オプション）

    Returns:
        RaceListResponse: レース一覧
    """
    logger.info(f"GET /races/upcoming: days={days}, grade={grade}")

    try:
        async with get_connection() as conn:
            races_data = await get_upcoming_races(conn, days_ahead=days, grade_filter=grade)

            races = []
            for race in races_data:
                races.append(RaceBase(
                    race_id=race[COL_RACE_ID],
                    race_name=race[COL_RACE_NAME],
                    race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                    race_time=race.get(COL_HASSO_JIKOKU, '不明'),
                    venue=_get_venue_name(race[COL_JYOCD]),
                    venue_code=race[COL_JYOCD],
                    grade=race.get(COL_GRADE_CD),
                    distance=race[COL_KYORI],
                    track_code=race[COL_TRACK_CD],
                    race_date=f"{race[COL_KAISAI_YEAR]}-{race[COL_KAISAI_MONTHDAY][:2]}-{race[COL_KAISAI_MONTHDAY][2:]}"
                ))

            response = RaceListResponse(
                date=date.today().strftime("%Y-%m-%d"),
                races=races,
                total=len(races)
            )

            logger.info(f"Found {len(races)} upcoming races")
            return response

    except Exception as e:
        logger.error(f"Failed to get upcoming races: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/races/date/{target_date}",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="指定日のレース一覧取得",
    description="指定した日付のレース一覧を取得します。"
)
async def get_races_for_date(
    target_date: str = Path(
        ...,
        description="対象日（YYYY-MM-DD形式）"
    ),
    venue: Optional[str] = Query(
        None,
        description="競馬場コード（01=札幌, 02=函館, etc.）"
    ),
    grade: Optional[str] = Query(
        None,
        description="グレードフィルタ（A=G1, B=G2, C=G3）"
    )
) -> RaceListResponse:
    """
    指定日のレース一覧を取得

    Args:
        target_date: 対象日（YYYY-MM-DD形式）
        venue: 競馬場コード（オプション）
        grade: グレードフィルタ（オプション）

    Returns:
        RaceListResponse: レース一覧
    """
    logger.info(f"GET /races/date/{target_date}: venue={venue}, grade={grade}")

    try:
        from datetime import datetime
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise DatabaseErrorException(f"Invalid date format: {target_date}. Use YYYY-MM-DD")

    try:
        async with get_connection() as conn:
            races_data = await get_races_by_date(
                conn, parsed_date, venue_code=venue, grade_filter=grade
            )

            races = []
            for race in races_data:
                races.append(RaceBase(
                    race_id=race[COL_RACE_ID],
                    race_name=race[COL_RACE_NAME],
                    race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                    race_time=race.get(COL_HASSO_JIKOKU, '不明'),
                    venue=_get_venue_name(race[COL_JYOCD]),
                    venue_code=race[COL_JYOCD],
                    grade=race.get(COL_GRADE_CD),
                    distance=race[COL_KYORI],
                    track_code=race[COL_TRACK_CD],
                    race_date=target_date
                ))

            response = RaceListResponse(
                date=target_date,
                races=races,
                total=len(races)
            )

            logger.info(f"Found {len(races)} races for {target_date}")
            return response

    except Exception as e:
        logger.error(f"Failed to get races for date {target_date}: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/races/{race_id}",
    response_model=RaceDetail,
    status_code=status.HTTP_200_OK,
    summary="レース詳細取得",
    description="特定レースの詳細情報（出走馬一覧含む）を取得します。"
)
async def get_race(
    race_id: str = Path(
        ...,
        min_length=16,
        max_length=16,
        description="レースID（16桁）"
    )
) -> RaceDetail:
    """
    レース詳細情報を取得

    Args:
        race_id: レースID（16桁）

    Returns:
        RaceDetail: レース詳細情報

    Raises:
        RaceNotFoundException: レースが見つからない
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /races/{race_id}")

    try:
        async with get_connection() as conn:
            detail = await get_race_detail(conn, race_id)

            if not detail:
                logger.warning(f"Race not found: {race_id}")
                raise RaceNotFoundException(race_id)

            race = detail["race"]
            entries_data = detail["entries"]

            # 出走馬情報を変換
            entries = []
            for entry in entries_data:
                entries.append(RaceEntry(
                    horse_number=entry["umaban"],
                    kettonum=entry[COL_KETTONUM],
                    horse_name=entry[COL_BAMEI],
                    jockey_code=entry[COL_KISYUCODE],
                    jockey_name=entry.get(COL_KISYU_NAME, "不明"),
                    trainer_code=entry[COL_CHOKYOSICODE],
                    trainer_name=entry.get(COL_CHOKYOSI_NAME, "不明"),
                    weight=float(entry.get("futan", 0)),
                    horse_weight=entry.get("bataiju"),
                    odds=float(entry["tansyo_odds"]) / 10.0 if entry.get("tansyo_odds") else None
                ))

            # 賞金情報
            prize_money = PrizeMoneyResponse(
                first=race.get("honshokin1", 0),
                second=race.get("honshokin2", 0),
                third=race.get("honshokin3", 0),
                fourth=race.get("honshokin4", 0),
                fifth=race.get("honshokin5", 0)
            )

            # 馬場状態（芝またはダート）
            track_condition = race.get(COL_SHIBA_BABA_CD) or race.get(COL_DIRT_BABA_CD)

            response = RaceDetail(
                race_id=race[COL_RACE_ID],
                race_name=race[COL_RACE_NAME],
                race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                race_time=race.get(COL_HASSO_JIKOKU, '不明'),
                venue=_get_venue_name(race[COL_JYOCD]),
                venue_code=race[COL_JYOCD],
                grade=race.get(COL_GRADE_CD),
                distance=race[COL_KYORI],
                track_code=race[COL_TRACK_CD],
                track_condition=track_condition,
                weather=race.get(COL_TENKO_CD),
                prize_money=prize_money,
                entries=entries
            )

            logger.info(f"Race detail retrieved: {race[COL_RACE_NAME]} ({len(entries)} horses)")
            return response

    except RaceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Failed to get race detail: {e}")
        raise DatabaseErrorException(str(e))
