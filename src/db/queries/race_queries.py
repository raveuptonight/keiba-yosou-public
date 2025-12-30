"""
レース情報取得クエリモジュール

レースの基本情報、出走馬一覧、今日のレース一覧などを取得するクエリ群
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from asyncpg import Connection

from src.db.table_names import (
    TABLE_RACE,
    TABLE_UMA_RACE,
    TABLE_UMA,
    TABLE_KISYU,
    TABLE_CHOKYOSI,
    TABLE_ODDS_TANSHO,
    COL_RACE_ID,
    COL_KETTONUM,
    COL_UMABAN,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
    COL_JYOCD,
    COL_DATA_KUBUN,
    COL_RACE_NAME,
    COL_GRADE_CD,
    COL_TRACK_CD,
    COL_KYORI,
    COL_RACE_NUM,
    COL_TENKO_CD,
    COL_SHIBA_BABA_CD,
    COL_DIRT_BABA_CD,
    COL_HASSO_JIKOKU,
    COL_BAMEI,
    COL_KISYUCODE,
    COL_CHOKYOSICODE,
    COL_KISYU_NAME,
    COL_CHOKYOSI_NAME,
    DATA_KUBUN_KAKUTEI,
)
from src.config import ML_TRAINING_YEARS_BACK

logger = logging.getLogger(__name__)


async def get_race_info(conn: Connection, race_id: str) -> Optional[Dict[str, Any]]:
    """
    レース基本情報を取得

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        レース情報のdict、見つからない場合はNone
    """
    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            honshokin1,
            honshokin2,
            honshokin3,
            honshokin4,
            honshokin5,
            {COL_SHIBA_BABA_CD},
            {COL_DIRT_BABA_CD},
            {COL_TENKO_CD},
            {COL_RACE_NUM},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {COL_HASSO_JIKOKU}
        FROM {TABLE_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
    """

    try:
        row = await conn.fetchrow(sql, race_id, DATA_KUBUN_KAKUTEI)
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get race info: race_id={race_id}, error={e}")
        raise


async def get_race_entries(conn: Connection, race_id: str) -> List[Dict[str, Any]]:
    """
    レースの出走馬一覧を取得

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        出走馬情報のリスト（馬番順）
    """
    sql = f"""
        SELECT
            se.{COL_UMABAN},
            se.{COL_KETTONUM},
            um.{COL_BAMEI},
            se.{COL_KISYUCODE},
            ks.{COL_KISYU_NAME},
            se.{COL_CHOKYOSICODE},
            ch.{COL_CHOKYOSI_NAME},
            se.futan,
            se.bataiju,
            o1.tansyo_odds,
            se.wakuban,
            se.sei_code,
            se.barei,
            se.tozai_code,
            se.chokyosi_code
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_UMA} um ON se.{COL_KETTONUM} = um.{COL_KETTONUM}
        LEFT JOIN {TABLE_KISYU} ks ON se.{COL_KISYUCODE} = ks.{COL_KISYUCODE}
        LEFT JOIN {TABLE_CHOKYOSI} ch ON se.{COL_CHOKYOSICODE} = ch.{COL_CHOKYOSICODE}
        LEFT JOIN {TABLE_ODDS_TANSHO} o1
            ON se.{COL_RACE_ID} = o1.{COL_RACE_ID}
            AND se.{COL_UMABAN} = o1.{COL_UMABAN}
            AND o1.{COL_DATA_KUBUN} = '3'
        WHERE se.{COL_RACE_ID} = $1
          AND se.{COL_DATA_KUBUN} = $2
        ORDER BY se.{COL_UMABAN}
    """

    try:
        rows = await conn.fetch(sql, race_id, DATA_KUBUN_KAKUTEI)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get race entries: race_id={race_id}, error={e}")
        raise


async def get_races_by_date(
    conn: Connection,
    target_date: date,
    venue_code: Optional[str] = None,
    grade_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    指定日のレース一覧を取得

    Args:
        conn: データベース接続
        target_date: 対象日（date型）
        venue_code: 競馬場コード（オプション）
        grade_filter: グレードフィルタ（オプション）

    Returns:
        レース情報のリスト（レース番号順）
    """
    year = str(target_date.year)
    monthday = target_date.strftime("%m%d")

    # 基本SQL
    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            {COL_RACE_NUM},
            {COL_HASSO_JIKOKU},
            {COL_SHIBA_BABA_CD},
            {COL_DIRT_BABA_CD},
            {COL_TENKO_CD},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} = $2
          AND {COL_DATA_KUBUN} = $3
    """

    params = [year, monthday, DATA_KUBUN_KAKUTEI]
    param_idx = 4

    # 競馬場フィルタ
    if venue_code:
        sql += f" AND {COL_JYOCD} = ${param_idx}"
        params.append(venue_code)
        param_idx += 1

    # グレードフィルタ
    if grade_filter:
        sql += f" AND {COL_GRADE_CD} = ${param_idx}"
        params.append(grade_filter)
        param_idx += 1

    sql += f" ORDER BY {COL_RACE_NUM}"

    try:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get races by date: date={target_date}, error={e}")
        raise


async def get_races_today(
    conn: Connection,
    venue_code: Optional[str] = None,
    grade_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    今日のレース一覧を取得

    Args:
        conn: データベース接続
        venue_code: 競馬場コード（オプション）
        grade_filter: グレードフィルタ（オプション）

    Returns:
        レース情報のリスト（レース番号順）
    """
    today = date.today()
    return await get_races_by_date(conn, today, venue_code, grade_filter)


async def get_race_entry_count(conn: Connection, race_id: str) -> int:
    """
    レースの出走頭数を取得

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        出走頭数
    """
    sql = f"""
        SELECT COUNT(*) as entry_count
        FROM {TABLE_UMA_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} = $2
    """

    try:
        row = await conn.fetchrow(sql, race_id, DATA_KUBUN_KAKUTEI)
        return row['entry_count'] if row else 0
    except Exception as e:
        logger.error(f"Failed to get race entry count: race_id={race_id}, error={e}")
        raise


async def get_upcoming_races(
    conn: Connection,
    days_ahead: int = 7,
    grade_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    今後N日間のレース一覧を取得

    Args:
        conn: データベース接続
        days_ahead: 何日先まで取得するか（デフォルト: 7日）
        grade_filter: グレードフィルタ（オプション）

    Returns:
        レース情報のリスト（開催日・レース番号順）
    """
    today = date.today()
    year = str(today.year)
    start_monthday = today.strftime("%m%d")

    # 終了日を計算
    from datetime import timedelta
    end_date = today + timedelta(days=days_ahead)
    end_monthday = end_date.strftime("%m%d")

    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_GRADE_CD},
            {COL_JYOCD},
            {COL_TRACK_CD},
            {COL_KYORI},
            {COL_RACE_NUM},
            {COL_HASSO_JIKOKU},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} >= $2
          AND {COL_KAISAI_MONTHDAY} <= $3
          AND {COL_DATA_KUBUN} = $4
    """

    params = [year, start_monthday, end_monthday, DATA_KUBUN_KAKUTEI]

    # グレードフィルタ
    if grade_filter:
        sql += f" AND {COL_GRADE_CD} = $5"
        params.append(grade_filter)

    sql += f" ORDER BY {COL_KAISAI_MONTHDAY}, {COL_RACE_NUM}"

    try:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get upcoming races: days_ahead={days_ahead}, error={e}")
        raise


async def get_race_detail(conn: Connection, race_id: str) -> Optional[Dict[str, Any]]:
    """
    レース詳細情報を取得（レース情報+出走馬一覧）

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        レース詳細情報のdict（race + entries）、見つからない場合はNone
    """
    # レース基本情報
    race_info = await get_race_info(conn, race_id)
    if not race_info:
        return None

    # 出走馬一覧
    entries = await get_race_entries(conn, race_id)

    return {
        "race": race_info,
        "entries": entries,
        "entry_count": len(entries)
    }


async def check_race_exists(conn: Connection, race_id: str) -> bool:
    """
    レースが存在するかチェック

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        存在する場合True、しない場合False
    """
    sql = f"""
        SELECT EXISTS(
            SELECT 1 FROM {TABLE_RACE}
            WHERE {COL_RACE_ID} = $1
              AND {COL_DATA_KUBUN} = $2
        ) AS exists
    """

    try:
        row = await conn.fetchrow(sql, race_id, DATA_KUBUN_KAKUTEI)
        return row['exists'] if row else False
    except Exception as e:
        logger.error(f"Failed to check race exists: race_id={race_id}, error={e}")
        raise
