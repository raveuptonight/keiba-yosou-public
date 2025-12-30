"""
馬情報取得クエリモジュール

馬の基本情報、過去成績、血統情報、調教情報などを取得するクエリ群
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from asyncpg import Connection

from src.db.table_names import (
    TABLE_UMA,
    TABLE_UMA_RACE,
    TABLE_RACE,
    TABLE_SANKU,
    TABLE_HANSYOKU,
    TABLE_HANRO_CHOKYO,
    TABLE_WOOD_CHOKYO,
    TABLE_SHUTUBA_KYORI,
    TABLE_KISYU,
    TABLE_CHOKYOSI,
    COL_KETTONUM,
    COL_RACE_ID,
    COL_BAMEI,
    COL_SEX,
    COL_KEIROCODE,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
    COL_KAKUTEI_CHAKUJUN,
    COL_TIME,
    COL_BATAIJU,
    COL_KISYUCODE,
    COL_CHOKYOSICODE,
    COL_DATA_KUBUN,
    COL_SANDAI_KETTO,
    COL_HANSYOKU_NUM,
    COL_HANSYOKUBA_NAME,
    COL_CHOKYO_DATE,
    COL_TIME_4F,
    COL_TIME_3F,
    COL_JYOCD,
    COL_KYORI,
    COL_RACE_NAME,
    DATA_KUBUN_KAKUTEI,
)
from src.config import ML_TRAINING_YEARS_BACK

logger = logging.getLogger(__name__)


async def get_horse_info(conn: Connection, kettonum: str) -> Optional[Dict[str, Any]]:
    """
    馬の基本情報を取得

    Args:
        conn: データベース接続
        kettonum: 血統登録番号（10桁）

    Returns:
        馬情報のdict、見つからない場合はNone
    """
    sql = f"""
        SELECT
            {COL_KETTONUM},
            {COL_BAMEI},
            birth_date,
            {COL_SEX},
            {COL_KEIROCODE},
            chichi_kettonum,
            haha_kettonum,
            breeder_code,
            owner_code,
            {COL_CHOKYOSICODE},
            total_honcho_sochu_shoto_sho,
            total_honcho_sochu_kei_sochu,
            heichi_sochu_kei,
            heichi_shutoku,
            tokubetsu_sochu_kei
        FROM {TABLE_UMA}
        WHERE {COL_KETTONUM} = $1
    """

    try:
        row = await conn.fetchrow(sql, kettonum)
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get horse info: kettonum={kettonum}, error={e}")
        raise


async def get_horses_recent_races(
    conn: Connection,
    kettonums: List[str],
    limit: int = 10
) -> Dict[str, List[Dict[str, Any]]]:
    """
    複数の馬の過去成績を一括取得（直近N走）

    Args:
        conn: データベース接続
        kettonums: 血統登録番号のリスト
        limit: 各馬の取得走数（デフォルト: 10）

    Returns:
        Dict[kettonum, 過去成績リスト]
    """
    # 10年以内のデータに絞り込み
    cutoff_year = str(date.today().year - ML_TRAINING_YEARS_BACK)

    sql = f"""
        WITH ranked_races AS (
            SELECT
                se.{COL_KETTONUM},
                se.{COL_RACE_ID},
                ra.{COL_RACE_NAME},
                ra.{COL_KAISAI_YEAR},
                ra.{COL_KAISAI_MONTHDAY},
                ra.{COL_JYOCD},
                ra.{COL_KYORI},
                ra.baba_jotai,
                ra.{COL_RACE_NAME},
                ra.grade_cd,
                se.{COL_KAKUTEI_CHAKUJUN},
                se.{COL_TIME},
                se.{COL_KISYUCODE},
                se.futan,
                se.{COL_BATAIJU},
                se.tansyo_odds,
                se.syogkin,
                se.umaban,
                se.zogensa,
                se.corner1_jyuni,
                se.corner2_jyuni,
                se.corner3_jyuni,
                se.corner4_jyuni,
                se.time_dif,
                ROW_NUMBER() OVER (
                    PARTITION BY se.{COL_KETTONUM}
                    ORDER BY ra.{COL_KAISAI_YEAR} DESC, ra.{COL_KAISAI_MONTHDAY} DESC
                ) AS rn
            FROM {TABLE_UMA_RACE} se
            INNER JOIN {TABLE_RACE} ra ON se.{COL_RACE_ID} = ra.{COL_RACE_ID}
            WHERE se.{COL_KETTONUM} = ANY($1)
              AND se.{COL_DATA_KUBUN} = $2
              AND ra.{COL_KAISAI_YEAR} >= $3
        )
        SELECT *
        FROM ranked_races
        WHERE rn <= $4
        ORDER BY {COL_KETTONUM}, rn
    """

    try:
        rows = await conn.fetch(sql, kettonums, DATA_KUBUN_KAKUTEI, cutoff_year, limit)

        # kettonum ごとにグループ化
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            if kettonum not in result:
                result[kettonum] = []
            result[kettonum].append(dict(row))

        return result
    except Exception as e:
        logger.error(f"Failed to get horses recent races: kettonums={kettonums[:3]}..., error={e}")
        raise


async def get_horse_recent_races(
    conn: Connection,
    kettonum: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    単一馬の過去成績を取得（直近N走）

    Args:
        conn: データベース接続
        kettonum: 血統登録番号（10桁）
        limit: 取得走数（デフォルト: 10）

    Returns:
        過去成績のリスト
    """
    result = await get_horses_recent_races(conn, [kettonum], limit)
    return result.get(kettonum, [])


async def get_horses_pedigree(
    conn: Connection,
    kettonums: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    複数の馬の血統情報を一括取得

    Args:
        conn: データベース接続
        kettonums: 血統登録番号のリスト

    Returns:
        Dict[kettonum, 血統情報dict]
    """
    sql = f"""
        SELECT
            sk.{COL_KETTONUM},
            sk.{COL_SANDAI_KETTO}[1] AS chichi,
            sk.{COL_SANDAI_KETTO}[2] AS haha,
            sk.{COL_SANDAI_KETTO}[3] AS chichi_chichi,
            sk.{COL_SANDAI_KETTO}[4] AS chichi_haha,
            sk.{COL_SANDAI_KETTO}[5] AS haha_chichi,
            sk.{COL_SANDAI_KETTO}[6] AS haha_haha,
            hn_f.{COL_HANSYOKUBA_NAME} AS chichi_name,
            hn_m.{COL_HANSYOKUBA_NAME} AS haha_name,
            hn_ff.{COL_HANSYOKUBA_NAME} AS chichi_chichi_name,
            hn_fm.{COL_HANSYOKUBA_NAME} AS chichi_haha_name,
            hn_mf.{COL_HANSYOKUBA_NAME} AS haha_chichi_name,
            hn_mm.{COL_HANSYOKUBA_NAME} AS haha_haha_name
        FROM {TABLE_SANKU} sk
        LEFT JOIN {TABLE_HANSYOKU} hn_f
            ON sk.{COL_SANDAI_KETTO}[1] = hn_f.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_m
            ON sk.{COL_SANDAI_KETTO}[2] = hn_m.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_ff
            ON sk.{COL_SANDAI_KETTO}[3] = hn_ff.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_fm
            ON sk.{COL_SANDAI_KETTO}[4] = hn_fm.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_mf
            ON sk.{COL_SANDAI_KETTO}[5] = hn_mf.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_mm
            ON sk.{COL_SANDAI_KETTO}[6] = hn_mm.{COL_HANSYOKU_NUM}
        WHERE sk.{COL_KETTONUM} = ANY($1)
    """

    try:
        rows = await conn.fetch(sql, kettonums)

        # kettonum ごとに辞書化
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            result[kettonum] = dict(row)

        return result
    except Exception as e:
        logger.error(f"Failed to get horses pedigree: kettonums={kettonums[:3]}..., error={e}")
        raise


async def get_horses_training(
    conn: Connection,
    kettonums: List[str],
    days_back: int = 30
) -> Dict[str, List[Dict[str, Any]]]:
    """
    複数の馬の調教情報を一括取得（直近N日分）

    Args:
        conn: データベース接続
        kettonums: 血統登録番号のリスト
        days_back: 何日前まで取得するか（デフォルト: 30日）

    Returns:
        Dict[kettonum, 調教情報リスト]
    """
    cutoff_date = (date.today() - timedelta(days=days_back)).strftime("%Y%m%d")

    # 坂路調教（HC）とウッド調教（WC）を統合
    sql = f"""
        WITH combined_training AS (
            -- 坂路調教
            SELECT
                {COL_KETTONUM},
                {COL_CHOKYO_DATE},
                'hanro' AS training_type,
                han_name,
                baba_jotai,
                {COL_TIME_4F},
                {COL_TIME_3F},
                han_type,
                tresen_kubun
            FROM {TABLE_HANRO_CHOKYO}
            WHERE {COL_KETTONUM} = ANY($1)
              AND {COL_CHOKYO_DATE} >= $2
              AND {COL_TIME_4F} > 0

            UNION ALL

            -- ウッド調教
            SELECT
                {COL_KETTONUM},
                {COL_CHOKYO_DATE},
                'wood' AS training_type,
                han_name,
                baba_jotai,
                time_6f AS {COL_TIME_4F},
                time_5f AS {COL_TIME_3F},
                han_type,
                tresen_kubun
            FROM {TABLE_WOOD_CHOKYO}
            WHERE {COL_KETTONUM} = ANY($1)
              AND {COL_CHOKYO_DATE} >= $2
              AND time_6f > 0
        ),
        ranked_training AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY {COL_KETTONUM}
                    ORDER BY {COL_CHOKYO_DATE} DESC
                ) AS rn
            FROM combined_training
        )
        SELECT *
        FROM ranked_training
        WHERE rn <= 5
        ORDER BY {COL_KETTONUM}, rn
    """

    try:
        rows = await conn.fetch(sql, kettonums, cutoff_date)

        # kettonum ごとにグループ化
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            if kettonum not in result:
                result[kettonum] = []
            result[kettonum].append(dict(row))

        return result
    except Exception as e:
        logger.error(f"Failed to get horses training: kettonums={kettonums[:3]}..., error={e}")
        raise


async def get_horses_statistics(
    conn: Connection,
    race_id: str,
    kettonums: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    複数の馬の着度数統計を一括取得

    Args:
        conn: データベース接続
        race_id: レースID（16桁）
        kettonums: 血統登録番号のリスト

    Returns:
        Dict[kettonum, 着度数統計dict]
    """
    sql = f"""
        SELECT
            ck.{COL_KETTONUM},
            ck.kyori_chakudo,
            ck.baba_chakudo,
            ck.jyocd_chakudo,
            ck.kisyu_chakudo,
            ck.{COL_KAISAI_YEAR},
            ck.{COL_KAISAI_MONTHDAY}
        FROM {TABLE_SHUTUBA_KYORI} ck
        WHERE ck.{COL_RACE_ID} = $1
          AND ck.{COL_KETTONUM} = ANY($2)
    """

    try:
        rows = await conn.fetch(sql, race_id, kettonums)

        # kettonum ごとに辞書化
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            result[kettonum] = dict(row)

        return result
    except Exception as e:
        logger.error(f"Failed to get horses statistics: race_id={race_id}, error={e}")
        raise


async def get_horse_detail(
    conn: Connection,
    kettonum: str,
    history_limit: int = 10
) -> Optional[Dict[str, Any]]:
    """
    馬の詳細情報を取得（基本情報+過去成績+血統）

    Args:
        conn: データベース接続
        kettonum: 血統登録番号（10桁）
        history_limit: 過去成績の取得件数（デフォルト: 10）

    Returns:
        馬の詳細情報のdict、見つからない場合はNone
    """
    # 基本情報
    horse_info = await get_horse_info(conn, kettonum)
    if not horse_info:
        return None

    # 過去成績
    recent_races = await get_horse_recent_races(conn, kettonum, history_limit)

    # 血統情報
    pedigree_dict = await get_horses_pedigree(conn, [kettonum])
    pedigree = pedigree_dict.get(kettonum)

    # 調教情報
    training_dict = await get_horses_training(conn, [kettonum])
    training = training_dict.get(kettonum, [])

    return {
        "horse_info": horse_info,
        "recent_races": recent_races,
        "pedigree": pedigree,
        "training": training,
        "total_races": len(recent_races)
    }


async def check_horse_exists(conn: Connection, kettonum: str) -> bool:
    """
    馬が存在するかチェック

    Args:
        conn: データベース接続
        kettonum: 血統登録番号（10桁）

    Returns:
        存在する場合True、しない場合False
    """
    sql = f"""
        SELECT EXISTS(
            SELECT 1 FROM {TABLE_UMA}
            WHERE {COL_KETTONUM} = $1
        ) AS exists
    """

    try:
        row = await conn.fetchrow(sql, kettonum)
        return row['exists'] if row else False
    except Exception as e:
        logger.error(f"Failed to check horse exists: kettonum={kettonum}, error={e}")
        raise
