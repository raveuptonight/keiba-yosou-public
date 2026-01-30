"""
Race information endpoints.
"""

import logging
from datetime import date

from fastapi import APIRouter, Path, Query, status

from src.api.exceptions import DatabaseErrorException, RaceNotFoundException
from src.api.schemas.common import PrizeMoneyResponse
from src.api.schemas.race import (
    HeadToHeadRace,
    HorseInMatchup,
    PayoffInfo,
    RaceBase,
    RaceDetail,
    RaceEntry,
    RaceListResponse,
    RacePayoffs,
    RaceResult,
)
from src.db.async_connection import get_connection
from src.db.queries.payoff_queries import get_race_lap_times, get_race_payoffs, get_race_results
from src.db.queries.race_queries import (
    get_horse_head_to_head,
    get_race_detail,
    get_race_entry_count,
    get_races_by_date,
    get_races_today,
    get_upcoming_races,
    search_races_by_name_db,
)
from src.db.table_names import (
    COL_BAMEI,
    COL_BAREI,
    COL_BATAIJU,
    COL_CHOKYOSI_NAME,
    COL_CHOKYOSICODE,
    COL_DIRT_BABA_CD,
    COL_GRADE_CD,
    COL_HASSO_JIKOKU,
    COL_JYOCD,
    COL_KAISAI_MONTHDAY,
    COL_KAISAI_YEAR,
    COL_KETTONUM,
    COL_KINRYO,
    COL_KISYU_NAME,
    COL_KISYUCODE,
    COL_KYORI,
    COL_KYOSO_SHUBETSU_CD,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_RACE_NUM,
    COL_SEX,
    COL_SHIBA_BABA_CD,
    COL_TENKO_CD,
    COL_TRACK_CD,
    COL_UMABAN,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_race_name_with_fallback(
    race_name: str,
    grade_code: str | None = None,
    kyoso_joken_code: str | None = None,
    kyoso_shubetsu_code: str | None = None,
) -> str:
    """Return a fallback value if race name is empty."""
    if race_name and race_name.strip():
        return race_name.strip()

    # Generate name from condition code if race name is empty
    from src.db.code_mappings import generate_race_condition_name

    condition_name = generate_race_condition_name(kyoso_joken_code, kyoso_shubetsu_code, grade_code)

    if condition_name:
        return condition_name

    # Fallback if still unable to generate
    if grade_code in ["A", "B", "C", "D"]:
        return "重賞レース"
    return "条件戦"


def _get_venue_name(venue_code: str) -> str:
    """Get venue name from venue code."""
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


def _get_grade_display(grade_code: str | None) -> str | None:
    """Get display name from grade code."""
    if not grade_code:
        return None
    grade_map = {
        "A": "G1",
        "B": "G2",
        "C": "G3",
        "D": "重賞",
        "E": "OP",
        "F": "J・G1",
        "G": "J・G2",
        "H": "J・G3",
        "L": "L",
    }
    return grade_map.get(grade_code.strip())


def _format_track_code(track_code: str) -> str:
    """Format track code to display name."""
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
    description="本日開催のレース一覧を取得します。グレードや競馬場でフィルタ可能。",
)
async def get_today_races(
    grade: str | None = Query(None, description="グレードフィルタ（A=G1, B=G2, C=G3）"),
    venue: str | None = Query(None, description="競馬場コード（01=札幌, 02=函館, etc.）"),
) -> RaceListResponse:
    """
    Get today's race list.

    Args:
        grade: Grade filter (optional).
        venue: Venue code (optional).

    Returns:
        RaceListResponse: Race list.

    Raises:
        DatabaseErrorException: Database connection error.
    """
    logger.info(f"GET /races/today: grade={grade}, venue={venue}")

    try:
        async with get_connection() as conn:
            races_data = await get_races_today(conn, venue_code=venue, grade_filter=grade)

            # Convert to response format
            races = []
            for race in races_data:
                # Get entry count
                await get_race_entry_count(conn, race[COL_RACE_ID])

                races.append(
                    RaceBase(
                        race_id=race[COL_RACE_ID],
                        race_name=_get_race_name_with_fallback(
                            race[COL_RACE_NAME],
                            race.get(COL_GRADE_CD),
                            race.get("kyoso_joken_code"),
                            race.get(COL_KYOSO_SHUBETSU_CD),
                        ),
                        race_number=f"{race[COL_RACE_NUM]}R" if race.get(COL_RACE_NUM) else "不明",
                        race_time=race.get(COL_HASSO_JIKOKU, "不明"),
                        venue=_get_venue_name(race[COL_JYOCD]),
                        venue_code=race[COL_JYOCD],
                        grade=_get_grade_display(race.get(COL_GRADE_CD)),
                        distance=race[COL_KYORI],
                        track_code=race[COL_TRACK_CD],
                    )
                )

            today = date.today()
            response = RaceListResponse(
                date=today.strftime("%Y-%m-%d"), races=races, count=len(races)
            )

            logger.info(f"Found {len(races)} races for today")
            return response

    except Exception as e:
        logger.error(f"Failed to get today's races: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/races/upcoming",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="今後のレース一覧取得",
    description="今後開催予定のレース一覧を取得します。",
)
async def get_upcoming_races_list(
    days: int = Query(7, ge=1, le=30, description="何日先まで取得するか（1-30日）"),
    grade: str | None = Query(None, description="グレードフィルタ（A=G1, B=G2, C=G3）"),
) -> RaceListResponse:
    """
    Get upcoming race list.

    Args:
        days: Number of days ahead to fetch (default 7).
        grade: Grade filter (optional).

    Returns:
        RaceListResponse: Race list.
    """
    logger.info(f"GET /races/upcoming: days={days}, grade={grade}")

    try:
        async with get_connection() as conn:
            races_data = await get_upcoming_races(conn, days_ahead=days, grade_filter=grade)

            races = []
            for race in races_data:
                races.append(
                    RaceBase(
                        race_id=race[COL_RACE_ID],
                        race_name=_get_race_name_with_fallback(
                            race[COL_RACE_NAME],
                            race.get(COL_GRADE_CD),
                            race.get("kyoso_joken_code"),
                            race.get(COL_KYOSO_SHUBETSU_CD),
                        ),
                        race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                        race_time=race.get(COL_HASSO_JIKOKU, "不明"),
                        venue=_get_venue_name(race[COL_JYOCD]),
                        venue_code=race[COL_JYOCD],
                        grade=_get_grade_display(race.get(COL_GRADE_CD)),
                        distance=race[COL_KYORI],
                        track_code=race[COL_TRACK_CD],
                        race_date=f"{race[COL_KAISAI_YEAR]}-{race[COL_KAISAI_MONTHDAY][:2]}-{race[COL_KAISAI_MONTHDAY][2:]}",
                    )
                )

            response = RaceListResponse(
                date=date.today().strftime("%Y-%m-%d"), races=races, count=len(races)
            )

            logger.info(f"Found {len(races)} upcoming races")
            return response

    except Exception as e:
        logger.error(f"Failed to get upcoming races: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/races/date/{target_date}",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="指定日のレース一覧取得",
    description="指定した日付のレース一覧を取得します。",
)
async def get_races_for_date(
    target_date: str = Path(..., description="対象日（YYYY-MM-DD形式）"),
    venue: str | None = Query(None, description="競馬場コード（01=札幌, 02=函館, etc.）"),
    grade: str | None = Query(None, description="グレードフィルタ（A=G1, B=G2, C=G3）"),
) -> RaceListResponse:
    """
    Get race list for a specified date.

    Args:
        target_date: Target date (YYYY-MM-DD format).
        venue: Venue code (optional).
        grade: Grade filter (optional).

    Returns:
        RaceListResponse: Race list.
    """
    logger.info(f"GET /races/date/{target_date}: venue={venue}, grade={grade}")

    try:
        from datetime import datetime

        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError as e:
        raise DatabaseErrorException(f"Invalid date format: {target_date}. Use YYYY-MM-DD") from e

    try:
        async with get_connection() as conn:
            races_data = await get_races_by_date(
                conn, parsed_date, venue_code=venue, grade_filter=grade
            )

            races = []
            for race in races_data:
                races.append(
                    RaceBase(
                        race_id=race[COL_RACE_ID],
                        race_name=_get_race_name_with_fallback(
                            race[COL_RACE_NAME],
                            race.get(COL_GRADE_CD),
                            race.get("kyoso_joken_code"),
                            race.get(COL_KYOSO_SHUBETSU_CD),
                        ),
                        race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                        race_time=race.get(COL_HASSO_JIKOKU, "不明"),
                        venue=_get_venue_name(race[COL_JYOCD]),
                        venue_code=race[COL_JYOCD],
                        grade=_get_grade_display(race.get(COL_GRADE_CD)),
                        distance=race[COL_KYORI],
                        track_code=race[COL_TRACK_CD],
                        race_date=target_date,
                    )
                )

            response = RaceListResponse(date=target_date, races=races, count=len(races))

            logger.info(f"Found {len(races)} races for {target_date}")
            return response

    except Exception as e:
        logger.error(f"Failed to get races for date {target_date}: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/races/{race_id}",
    response_model=RaceDetail,
    status_code=status.HTTP_200_OK,
    summary="レース詳細取得",
    description="特定レースの詳細情報（出走馬一覧含む）を取得します。",
)
async def get_race(
    race_id: str = Path(..., min_length=16, max_length=16, description="レースID（16桁）")
) -> RaceDetail:
    """
    Get race detail information.

    Args:
        race_id: Race ID (16 digits).

    Returns:
        RaceDetail: Race detail information.

    Raises:
        RaceNotFoundException: Race not found.
        DatabaseErrorException: Database connection error.
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

            # Convert entry information
            entries = []
            for entry in entries_data:
                # Sex conversion
                sex_map = {"1": "牡", "2": "牝", "3": "騙"}
                sex = sex_map.get(entry.get(COL_SEX), None)

                # Build previous race information
                last_race_str = None
                if entry.get("last_venue_code") and entry.get("last_finish"):
                    last_venue = _get_venue_name(entry["last_venue_code"])
                    last_finish = entry["last_finish"]
                    last_race_str = f"{last_venue}{last_finish}着"

                entries.append(
                    RaceEntry(
                        horse_number=entry[COL_UMABAN],
                        kettonum=entry[COL_KETTONUM],
                        horse_name=entry[COL_BAMEI],
                        sex=sex,
                        age=entry.get(COL_BAREI),
                        sire=entry.get("sire_name"),
                        jockey_code=entry[COL_KISYUCODE],
                        jockey_name=entry.get(COL_KISYU_NAME, "不明"),
                        trainer_code=entry[COL_CHOKYOSICODE],
                        trainer_name=entry.get(COL_CHOKYOSI_NAME, "不明"),
                        weight=float(entry.get(COL_KINRYO, 0)) / 10.0,
                        horse_weight=entry.get(COL_BATAIJU),
                        odds=(
                            float(entry["tansho_odds"]) / 10.0 if entry.get("tansho_odds") else None
                        ),
                        last_race=last_race_str,
                    )
                )

            # Prize money information
            prize_money = PrizeMoneyResponse(
                first=race.get("honshokin1", 0),
                second=race.get("honshokin2", 0),
                third=race.get("honshokin3", 0),
                fourth=race.get("honshokin4", 0),
                fifth=race.get("honshokin5", 0),
            )

            # Track condition (turf or dirt)
            track_condition = race.get(COL_SHIBA_BABA_CD) or race.get(COL_DIRT_BABA_CD)

            # Get race date
            race_year = race.get(COL_KAISAI_YEAR)
            race_monthday = race.get(COL_KAISAI_MONTHDAY)
            race_date = None
            if race_year and race_monthday and len(race_monthday) == 4:
                try:
                    race_date = date(int(race_year), int(race_monthday[:2]), int(race_monthday[2:]))
                except (ValueError, IndexError):
                    pass

            # Check if past race (race date < today)
            results_data = None
            payoffs_data = None
            lap_times_data = None
            if race_date and race_date < date.today():
                # Get results and payoffs
                try:
                    results_raw = await get_race_results(conn, race_id)
                    if results_raw:
                        results_data = [
                            RaceResult(
                                horse_number=r["umaban"],
                                horse_name=r["bamei"],
                                jockey_name=r["kishumei"],
                                finish_position=r["chakujun"],
                                finish_time=r["time"],
                                odds=r.get("odds"),
                                kohan_3f=r.get("kohan_3f"),
                            )
                            for r in results_raw
                        ]

                    payoffs_raw = await get_race_payoffs(conn, race_id)
                    if payoffs_raw:
                        payoffs_data = RacePayoffs(
                            win=(
                                PayoffInfo(**payoffs_raw["win"]) if payoffs_raw.get("win") else None
                            ),
                            place=(
                                [PayoffInfo(**p) for p in payoffs_raw["place"]]
                                if payoffs_raw.get("place")
                                else None
                            ),
                            bracket_quinella=(
                                PayoffInfo(**payoffs_raw["bracket_quinella"])
                                if payoffs_raw.get("bracket_quinella")
                                else None
                            ),
                            quinella=(
                                PayoffInfo(**payoffs_raw["quinella"])
                                if payoffs_raw.get("quinella")
                                else None
                            ),
                            exacta=(
                                PayoffInfo(**payoffs_raw["exacta"])
                                if payoffs_raw.get("exacta")
                                else None
                            ),
                            wide=(
                                [PayoffInfo(**w) for w in payoffs_raw["wide"]]
                                if payoffs_raw.get("wide")
                                else None
                            ),
                            trio=(
                                PayoffInfo(**payoffs_raw["trio"])
                                if payoffs_raw.get("trio")
                                else None
                            ),
                            trifecta=(
                                PayoffInfo(**payoffs_raw["trifecta"])
                                if payoffs_raw.get("trifecta")
                                else None
                            ),
                        )

                    lap_times_data = await get_race_lap_times(conn, race_id)
                except Exception as e:
                    logger.warning(f"Failed to get race results/payoffs: {e}")
                    # Return race info even if results/payoffs fetch fails

            # Get head-to-head records for entered horses
            head_to_head_data = None
            try:
                kettonums = [entry[COL_KETTONUM] for entry in entries_data]
                if len(kettonums) >= 2:
                    matchups_raw = await get_horse_head_to_head(conn, kettonums, limit=10)
                    if matchups_raw:
                        head_to_head_data = [
                            HeadToHeadRace(
                                race_id=m["race_id"],
                                race_name=m["race_name"],
                                race_date=m["race_date"],
                                venue_code=m["venue_code"],
                                distance=m["distance"],
                                horses=[
                                    HorseInMatchup(
                                        kettonum=h["kettonum"],
                                        name=h["name"],
                                        horse_number=h["horse_number"],
                                        finish_position=h["finish_position"],
                                    )
                                    for h in m["horses"]
                                ],
                            )
                            for m in matchups_raw
                        ]
            except Exception as e:
                logger.warning(f"Failed to get head-to-head data: {e}")
                # Return race info even if head-to-head fetch fails

            response = RaceDetail(
                race_id=race[COL_RACE_ID],
                race_name=_get_race_name_with_fallback(
                    race[COL_RACE_NAME],
                    race.get(COL_GRADE_CD),
                    race.get("kyoso_joken_code"),
                    race.get(COL_KYOSO_SHUBETSU_CD),
                ),
                race_number=f"{race.get(COL_RACE_NUM, '?')}R",
                race_time=race.get(COL_HASSO_JIKOKU, "不明"),
                venue=_get_venue_name(race[COL_JYOCD]),
                venue_code=race[COL_JYOCD],
                grade=_get_grade_display(race.get(COL_GRADE_CD)),
                distance=race[COL_KYORI],
                track_code=race[COL_TRACK_CD],
                track_condition=track_condition,
                weather=race.get(COL_TENKO_CD),
                prize_money=prize_money,
                entries=entries,
                results=results_data,
                payoffs=payoffs_data,
                lap_times=lap_times_data if lap_times_data else None,
                head_to_head=head_to_head_data,
            )

            logger.info(f"Race detail retrieved: {race[COL_RACE_NAME]} ({len(entries)} horses)")
            return response

    except RaceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Failed to get race detail: {e}")
        raise DatabaseErrorException(str(e)) from e


@router.get(
    "/races/search/name",
    response_model=RaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="レース名検索",
    description="レース名で検索します（部分一致、過去30日〜未来30日）。",
)
async def search_races_by_name(
    query: str = Query(..., min_length=1, description="レース名検索クエリ（部分一致）"),
    days_before: int = Query(30, ge=0, le=365, description="過去何日前まで検索するか（0〜365日）"),
    days_after: int = Query(30, ge=0, le=365, description="未来何日先まで検索するか（0〜365日）"),
    limit: int = Query(20, ge=1, le=100, description="最大取得件数（1〜100）"),
) -> RaceListResponse:
    """
    Search races by name.

    Args:
        query: Race name search query (partial match).
        days_before: Number of days before to search.
        days_after: Number of days after to search.
        limit: Maximum number of results.

    Returns:
        RaceListResponse: List of matching races.

    Raises:
        DatabaseErrorException: Database connection error.
    """
    logger.info(
        f"GET /races/search/name: query={query}, days_before={days_before}, days_after={days_after}"
    )

    try:
        async with get_connection() as conn:
            races_data = await search_races_by_name_db(
                conn, query, days_before=days_before, days_after=days_after, limit=limit
            )

            races = []
            for race in races_data:
                races.append(
                    RaceBase(
                        race_id=race["race_id"],
                        race_name=_get_race_name_with_fallback(
                            race["race_name"],
                            race.get("grade_code"),
                            race.get("kyoso_joken_code"),
                            race.get("kyoso_shubetsu_code"),
                        ),
                        race_number=f"{race.get('race_number', '?')}R",
                        race_time=None,
                        venue=_get_venue_name(race["venue_code"]),
                        venue_code=race["venue_code"],
                        grade=_get_grade_display(race.get("grade_code")),
                        distance=race["distance"],
                        track_code=race["track_code"],
                    )
                )

            logger.info(f"Found {len(races)} races matching '{query}'")
            return RaceListResponse(
                date=None,
                races=races,
                count=len(races),  # None because results may span multiple dates
            )

    except Exception as e:
        logger.error(f"Failed to search races by name: {e}")
        raise DatabaseErrorException(str(e)) from e
