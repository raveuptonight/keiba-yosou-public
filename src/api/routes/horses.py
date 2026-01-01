"""
馬情報エンドポイント
"""

import logging
from datetime import date
from fastapi import APIRouter, Query, Path, status

from typing import Optional, List
from src.api.schemas.horse import HorseDetail, HorseSearchResult, Trainer, Pedigree, RecentRace, TrainingData, TrainingRecord
from src.api.exceptions import HorseNotFoundException, DatabaseErrorException
from src.db.async_connection import get_connection
from src.db.queries.horse_queries import get_horse_detail, search_horses_by_name, get_training_before_race, get_horses_training
from src.db.table_names import (
    COL_KETTONUM,
    COL_BAMEI,
    COL_SEX,
    COL_KEIROCODE,
    COL_BIRTH_DATE,
    COL_CHOKYOSICODE,
    COL_CHOKYOSI_NAME,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
    COL_JYOCD,
    COL_KYORI,
    COL_KAKUTEI_CHAKUJUN,
    COL_TIME,
    COL_KISYU_NAME,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/horses/search",
    response_model=List[HorseSearchResult],
    status_code=status.HTTP_200_OK,
    summary="馬名検索",
    description="馬名で馬を検索します（部分一致）。"
)
async def search_horses(
    name: str = Query(
        ...,
        min_length=1,
        description="検索する馬名（部分一致）"
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="取得件数上限（デフォルト: 10）"
    )
) -> List[HorseSearchResult]:
    """
    馬名で馬を検索

    Args:
        name: 検索する馬名
        limit: 取得件数上限

    Returns:
        List[HorseSearchResult]: 検索結果リスト
    """
    logger.info(f"GET /horses/search: name={name}, limit={limit}")

    try:
        async with get_connection() as conn:
            results = await search_horses_by_name(conn, name, limit)

            horses = []
            for row in results:
                sex_map = {"1": "牡", "2": "牝", "3": "セ"}

                # 生年月日を変換（'YYYYMMDD' -> date）
                birth_date_str = row.get("birth_date")
                birth_date_val = None
                if birth_date_str and len(str(birth_date_str)) >= 8:
                    try:
                        bd_str = str(birth_date_str)[:8]
                        birth_date_val = date(int(bd_str[:4]), int(bd_str[4:6]), int(bd_str[6:8]))
                    except (ValueError, IndexError):
                        birth_date_val = None

                horses.append(HorseSearchResult(
                    kettonum=row["kettonum"],
                    name=row["name"].strip() if row["name"] else "",
                    sex=sex_map.get(row.get("sex", ""), ""),
                    birth_date=birth_date_val,
                    runs=row.get("runs", 0),
                    wins=row.get("wins", 0),
                    prize=0  # TODO: 賞金情報取得
                ))

            logger.info(f"Found {len(horses)} horses matching '{name}'")
            return horses

    except Exception as e:
        logger.error(f"Failed to search horses: {e}")
        raise DatabaseErrorException(str(e))


def _get_venue_name(venue_code: str) -> str:
    """競馬場コードから名称を取得"""
    venue_map = {
        "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
        "05": "東京", "06": "中山", "07": "中京", "08": "京都",
        "09": "阪神", "10": "小倉"
    }
    return venue_map.get(venue_code, "不明")


def _get_sex_name(sex_code: str) -> str:
    """性別コードから名称を取得"""
    sex_map = {"1": "牡", "2": "牝", "3": "騙"}
    return sex_map.get(sex_code, "不明")


def _get_color_name(color_code: str) -> str:
    """毛色コードから名称を取得"""
    color_map = {
        "1": "鹿毛", "2": "栗毛", "3": "栃栗毛", "4": "黒鹿毛",
        "5": "青鹿毛", "6": "青毛", "7": "芦毛", "8": "白毛", "9": "栗毛"
    }
    return color_map.get(color_code, "不明")


def _get_affiliation(tozai_code: str) -> str:
    """所属コードから名称を取得"""
    affiliation_map = {"1": "美浦", "2": "栗東"}
    return affiliation_map.get(tozai_code, "不明")


@router.get(
    "/horses/{kettonum}",
    response_model=HorseDetail,
    status_code=status.HTTP_200_OK,
    summary="馬詳細情報取得",
    description="馬の詳細情報、過去成績、血統情報を取得します。"
)
async def get_horse(
    kettonum: str = Path(
        ...,
        min_length=10,
        max_length=10,
        description="血統登録番号（10桁）"
    ),
    history_limit: int = Query(
        10,
        ge=1,
        le=50,
        description="過去成績取得件数（デフォルト: 10）"
    )
) -> HorseDetail:
    """
    馬の詳細情報を取得

    Args:
        kettonum: 血統登録番号（10桁）
        history_limit: 過去成績取得件数

    Returns:
        HorseDetail: 馬の詳細情報

    Raises:
        HorseNotFoundException: 馬が見つからない
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /horses/{kettonum} (history_limit={history_limit})")

    try:
        async with get_connection() as conn:
            detail = await get_horse_detail(conn, kettonum, history_limit)

            if not detail:
                logger.warning(f"Horse not found: {kettonum}")
                raise HorseNotFoundException(kettonum)

            horse_info = detail["horse_info"]
            recent_races_data = detail.get("recent_races", [])
            pedigree_data = detail.get("pedigree", {})

            # 調教師情報
            trainer = Trainer(
                code=horse_info.get(COL_CHOKYOSICODE, "不明"),
                name=horse_info.get(COL_CHOKYOSI_NAME, "不明"),
                affiliation=_get_affiliation(horse_info.get("tozai_code", "1"))
            )

            # 血統情報
            pedigree = Pedigree(
                sire=pedigree_data.get("chichi_name", "不明"),
                dam=pedigree_data.get("haha_name", "不明"),
                sire_sire=pedigree_data.get("chichi_chichi_name", "不明"),
                sire_dam=pedigree_data.get("chichi_haha_name", "不明"),
                dam_sire=pedigree_data.get("haha_chichi_name", "不明"),
                dam_dam=pedigree_data.get("haha_haha_name", "不明")
            )

            # 過去成績
            recent_races = []
            for race in recent_races_data:
                # 日付フォーマット
                race_year = race[COL_KAISAI_YEAR]
                race_monthday = race[COL_KAISAI_MONTHDAY]
                race_date = date(int(race_year), int(race_monthday[:2]), int(race_monthday[2:]))

                # 調教データを取得（レース前14日以内）
                race_date_str = f"{race_year}{race_monthday}"
                training_data = await get_training_before_race(conn, kettonum, race_date_str, days_before=14)

                training_obj = None
                if training_data:
                    training_obj = TrainingData(
                        training_type=training_data.get("training_type", "不明"),
                        training_date=training_data.get("training_date", ""),
                        time_4f=training_data.get("time_4f"),
                        time_3f=training_data.get("time_3f")
                    )

                recent_races.append(RecentRace(
                    race_id=race[COL_RACE_ID],
                    race_name=race[COL_RACE_NAME],
                    race_date=race_date,
                    venue=_get_venue_name(race[COL_JYOCD]),
                    distance=race[COL_KYORI],
                    track_condition=race.get("baba_jotai", "不明"),
                    finish_position=race[COL_KAKUTEI_CHAKUJUN],
                    time=race.get(COL_TIME, "不明"),
                    time_diff=race.get("time_sa"),  # 勝ち馬とのタイム差
                    winner_name=race.get("winner_name"),  # 勝ち馬名
                    jockey=race.get(COL_KISYU_NAME, "不明"),
                    weight=float(race.get("futan", 0)) / 10.0,
                    horse_weight=race.get("bataiju"),
                    odds=float(race["tansho_odds"]) / 10.0 if race.get("tansho_odds") else None,
                    prize_money=race.get("syogkin", 0),
                    training=training_obj
                ))

            # 通算成績を計算（総合成績から）
            sogo_1 = int(horse_info.get("sogo_1chaku", "0") or "0")
            sogo_2 = int(horse_info.get("sogo_2chaku", "0") or "0")
            sogo_3 = int(horse_info.get("sogo_3chaku", "0") or "0")
            sogo_4 = int(horse_info.get("sogo_4chaku", "0") or "0")
            sogo_5 = int(horse_info.get("sogo_5chaku", "0") or "0")
            sogo_gai = int(horse_info.get("sogo_chakugai", "0") or "0")

            total_races = sogo_1 + sogo_2 + sogo_3 + sogo_4 + sogo_5 + sogo_gai
            wins = sogo_1
            win_rate = wins / total_races if total_races > 0 else 0.0

            # 通算獲得賞金（クエリで計算済み）
            total_prize_money = horse_info.get("total_prize_money", 0) or 0

            # 生年月日を変換
            birth_date_val = date(2000, 1, 1)  # デフォルト値
            birth_date_str = horse_info.get(COL_BIRTH_DATE)
            if birth_date_str:
                try:
                    bd_str = str(birth_date_str)[:8]
                    birth_date_val = date(int(bd_str[:4]), int(bd_str[4:6]), int(bd_str[6:8]))
                except (ValueError, IndexError):
                    pass

            # 調教データを変換
            training_data = detail.get("training", [])
            training_records = []
            for t in training_data[:5]:  # 直近5件
                training_records.append(TrainingRecord(
                    training_type=t.get("training_type", "unknown"),
                    chokyo_nengappi=t.get("chokyo_nengappi", ""),
                    time_gokei_4furlong=t.get("time_gokei_4furlong"),
                    time_gokei_3furlong=t.get("time_gokei_3furlong"),
                ))

            response = HorseDetail(
                kettonum=kettonum,
                horse_name=horse_info[COL_BAMEI],
                birth_date=birth_date_val,
                sex=_get_sex_name(horse_info.get(COL_SEX, "1")),
                coat_color=_get_color_name(horse_info.get(COL_KEIROCODE, "1")),
                sire=pedigree_data.get("chichi_name", "不明"),
                dam=pedigree_data.get("haha_name", "不明"),
                breeder=horse_info.get("breeder_code", "不明"),
                owner=horse_info.get("owner_code", "不明"),
                trainer=trainer,
                total_races=total_races,
                wins=wins,
                win_rate=win_rate,
                prize_money=total_prize_money,
                running_style=None,  # TODO: 脚質判定ロジックを追加
                pedigree=pedigree,
                recent_races=recent_races,
                training=training_records
            )

            logger.info(f"Horse detail retrieved: {horse_info[COL_BAMEI]} ({total_races} races)")
            return response

    except HorseNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Failed to get horse detail: {e}")
        raise DatabaseErrorException(str(e))


@router.get(
    "/horses/{kettonum}/training",
    response_model=List[TrainingData],
    status_code=status.HTTP_200_OK,
    summary="馬の調教データ取得",
    description="指定した馬の調教データ（坂路・ウッドチップ）を取得します。"
)
async def get_horse_training(
    kettonum: str = Path(
        ...,
        min_length=10,
        max_length=10,
        description="血統登録番号（10桁）"
    ),
    days_back: int = Query(
        30,
        ge=7,
        le=90,
        description="何日前まで取得するか（7〜90日）"
    )
) -> List[TrainingData]:
    """
    馬の調教データを取得

    Args:
        kettonum: 血統登録番号（10桁）
        days_back: 何日前まで取得するか

    Returns:
        List[TrainingData]: 調教データリスト

    Raises:
        DatabaseErrorException: DB接続エラー
    """
    logger.info(f"GET /horses/{kettonum}/training: days_back={days_back}")

    try:
        async with get_connection() as conn:
            training_dict = await get_horses_training(conn, [kettonum], days_back=days_back)
            training_list = training_dict.get(kettonum, [])

            results = []
            for t in training_list:
                results.append(TrainingData(
                    training_type="坂路" if t["training_type"] == "hanro" else "ウッド",
                    training_date=t["chokyo_nengappi"],
                    time_4f=t.get("time_gokei_4furlong"),
                    time_3f=t.get("time_gokei_3furlong")
                ))

            logger.info(f"Found {len(results)} training records for {kettonum}")
            return results

    except Exception as e:
        logger.error(f"Failed to get training data: {e}")
        raise DatabaseErrorException(str(e))
