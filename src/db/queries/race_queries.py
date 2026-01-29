"""
レース情報取得クエリモジュール

レースの基本情報、出走馬一覧、今日のレース一覧などを取得するクエリ群
"""

import logging
from datetime import date
from typing import Any

from asyncpg import Connection

from src.db.table_names import (
    COL_BAMEI,
    COL_BAREI,
    COL_BATAIJU,
    COL_CHOKYOSI_NAME,
    COL_CHOKYOSICODE,
    COL_DATA_KUBUN,
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
    COL_KYOSO_JOKEN_2SAI,
    COL_KYOSO_JOKEN_3SAI,
    COL_KYOSO_JOKEN_4SAI,
    COL_KYOSO_JOKEN_5SAI_IJO,
    COL_KYOSO_SHUBETSU_CD,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_RACE_NUM,
    COL_SEX,
    COL_SHIBA_BABA_CD,
    COL_TENKO_CD,
    COL_TOZAI_CODE,
    COL_TRACK_CD,
    COL_UMABAN,
    COL_WAKUBAN,
    DATA_KUBUN_KAKUTEI,
    TABLE_CHOKYOSI,
    TABLE_HANSYOKU,
    TABLE_KISYU,
    TABLE_RACE,
    TABLE_SANKU,
    TABLE_UMA,
    TABLE_UMA_RACE,
)

logger = logging.getLogger(__name__)


# 年齢別競走条件コードから統合した値を取得するSQL式
def get_kyoso_joken_code_expr() -> str:
    """
    年齢別の競走条件コードカラムから、最初の非'000'値を取得するSQL式

    Returns:
        COALESCE式の文字列（AS kyoso_joken_code付き）
    """
    return f"""COALESCE(
        NULLIF({COL_KYOSO_JOKEN_2SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_3SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_4SAI}, '000'),
        NULLIF({COL_KYOSO_JOKEN_5SAI_IJO}, '000'),
        '000'
    ) as kyoso_joken_code"""


async def get_race_info(conn: Connection, race_id: str) -> dict[str, Any] | None:
    """
    レース基本情報を取得

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        レース情報のdict、見つからない場合はNone
    """
    # 登録済みのレースをすべて取得（未来のレースも含む）
    # data_kubun: 1=登録, 2=速報, 3=枠順確定, 4=出馬表, 5=開催中, 6=確定前, 7=確定
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
            {COL_HASSO_JIKOKU},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get race info: race_id={race_id}, error={e}")
        raise


async def get_race_entries(conn: Connection, race_id: str) -> list[dict[str, Any]]:
    """
    レースの出走馬一覧を取得（血統・前走情報含む）

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        出走馬情報のリスト（馬番順）
    """
    # 出走馬情報は登録済みのレースをすべて取得（未来のレースも含む）
    # 前走情報は確定データのみ取得
    sql = f"""
        WITH last_race AS (
            -- 各馬の前走情報を取得（確定データのみ）
            SELECT DISTINCT ON (se2.{COL_KETTONUM})
                se2.{COL_KETTONUM},
                se2.{COL_JYOCD} AS last_venue_code,
                se2.kakutei_chakujun AS last_finish
            FROM {TABLE_UMA_RACE} se2
            WHERE se2.{COL_RACE_ID} < $1
              AND se2.{COL_DATA_KUBUN} = '7'
              AND se2.kakutei_chakujun IS NOT NULL
              AND se2.kakutei_chakujun::integer > 0
            ORDER BY se2.{COL_KETTONUM}, se2.{COL_RACE_ID} DESC
        )
        SELECT
            se.{COL_UMABAN},
            se.{COL_KETTONUM},
            um.{COL_BAMEI},
            se.{COL_KISYUCODE},
            ks.{COL_KISYU_NAME},
            se.{COL_CHOKYOSICODE},
            ch.{COL_CHOKYOSI_NAME},
            se.{COL_KINRYO},
            se.{COL_BATAIJU},
            se.tansho_odds,
            se.{COL_WAKUBAN},
            se.{COL_SEX},
            se.{COL_BAREI},
            se.{COL_TOZAI_CODE},
            hn_f.bamei AS sire_name,
            lr.last_venue_code,
            lr.last_finish
        FROM {TABLE_UMA_RACE} se
        INNER JOIN {TABLE_UMA} um ON se.{COL_KETTONUM} = um.{COL_KETTONUM}
        LEFT JOIN {TABLE_KISYU} ks ON se.{COL_KISYUCODE} = ks.{COL_KISYUCODE}
        LEFT JOIN {TABLE_CHOKYOSI} ch ON se.{COL_CHOKYOSICODE} = ch.{COL_CHOKYOSICODE}
        LEFT JOIN {TABLE_SANKU} sk ON se.{COL_KETTONUM} = sk.{COL_KETTONUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_f ON sk.ketto1_hanshoku_toroku_bango = hn_f.hanshoku_toroku_bango
        LEFT JOIN last_race lr ON se.{COL_KETTONUM} = lr.{COL_KETTONUM}
        WHERE se.{COL_RACE_ID} = $1
          AND se.{COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
        ORDER BY se.{COL_UMABAN}
    """

    try:
        rows = await conn.fetch(sql, race_id)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get race entries: race_id={race_id}, error={e}")
        raise


async def get_races_by_date(
    conn: Connection,
    target_date: date,
    venue_code: str | None = None,
    grade_filter: str | None = None,
) -> list[dict[str, Any]]:
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
    today = date.today()

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
            {COL_KAISAI_MONTHDAY},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} = $2
    """

    params = [year, monthday]
    param_idx = 3

    # 過去のレースは確定データのみ、未来のレースは登録済みデータを取得
    if target_date < today:
        sql += f" AND {COL_DATA_KUBUN} = ${param_idx}"
        params.append(DATA_KUBUN_KAKUTEI)
        param_idx += 1
    else:
        # 未来のレース: 登録('1'), 速報('2'), 枠順確定('3'), 出馬表('4'), 開催中('5'), 確定前('6')
        sql += f" AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')"

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
    conn: Connection, venue_code: str | None = None, grade_filter: str | None = None
) -> list[dict[str, Any]]:
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
    # 登録済みのレースをすべて取得（未来のレースも含む）
    sql = f"""
        SELECT COUNT(*) as entry_count
        FROM {TABLE_UMA_RACE}
        WHERE {COL_RACE_ID} = $1
          AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return row["entry_count"] if row else 0
    except Exception as e:
        logger.error(f"Failed to get race entry count: race_id={race_id}, error={e}")
        raise


async def get_upcoming_races(
    conn: Connection, days_ahead: int = 7, grade_filter: str | None = None
) -> list[dict[str, Any]]:
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

    # 未来のレースは data_kubun が '1'(登録) や '2'(速報) の場合があるため
    # 確定('7')に限定せず、登録済みのレースを全て取得
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
            {COL_KAISAI_MONTHDAY},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_KAISAI_YEAR} = $1
          AND {COL_KAISAI_MONTHDAY} >= $2
          AND {COL_KAISAI_MONTHDAY} <= $3
    """

    params = [year, start_monthday, end_monthday]

    # グレードフィルタ
    if grade_filter:
        sql += f" AND {COL_GRADE_CD} = $4"
        params.append(grade_filter)

    sql += f" ORDER BY {COL_KAISAI_MONTHDAY}, {COL_RACE_NUM}"

    try:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get upcoming races: days_ahead={days_ahead}, error={e}")
        raise


async def get_race_detail(conn: Connection, race_id: str) -> dict[str, Any] | None:
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

    return {"race": race_info, "entries": entries, "entry_count": len(entries)}


async def check_race_exists(conn: Connection, race_id: str) -> bool:
    """
    レースが存在するかチェック

    Args:
        conn: データベース接続
        race_id: レースID（16桁）

    Returns:
        存在する場合True、しない場合False
    """
    # 登録済みのレースをすべてチェック（未来のレースも含む）
    # data_kubun: 1=登録, 2=速報, 3=枠順確定, 4=出馬表, 5=開催中, 6=確定前, 7=確定
    sql = f"""
        SELECT EXISTS(
            SELECT 1 FROM {TABLE_RACE}
            WHERE {COL_RACE_ID} = $1
              AND {COL_DATA_KUBUN} IN ('1', '2', '3', '4', '5', '6', '7')
        ) AS exists
    """

    try:
        row = await conn.fetchrow(sql, race_id)
        return row["exists"] if row else False
    except Exception as e:
        logger.error(f"Failed to check race exists: race_id={race_id}, error={e}")
        raise


async def get_horse_head_to_head(
    conn: Connection, kettonums: list[str], limit: int = 20
) -> list[dict[str, Any]]:
    """
    複数の馬の過去の対戦成績を取得

    Args:
        conn: データベース接続
        kettonums: 血統登録番号のリスト
        limit: 取得する過去レース数の上限

    Returns:
        過去の対戦レースのリスト（各レースで対象馬の着順を含む）
    """
    if len(kettonums) < 2:
        return []

    # 対象馬が2頭以上出走したレースを検索
    sql = f"""
        WITH target_horses AS (
            SELECT {COL_RACE_ID}, {COL_KETTONUM}, {COL_UMABAN}, kakutei_chakujun, {COL_BAMEI}
            FROM {TABLE_UMA_RACE}
            WHERE {COL_KETTONUM} = ANY($1)
              AND {COL_DATA_KUBUN} = $2
              AND kakutei_chakujun IS NOT NULL
              AND kakutei_chakujun::integer > 0
        ),
        race_counts AS (
            SELECT {COL_RACE_ID}, COUNT(DISTINCT {COL_KETTONUM}) as horse_count
            FROM target_horses
            GROUP BY {COL_RACE_ID}
            HAVING COUNT(DISTINCT {COL_KETTONUM}) >= 2
        ),
        matched_races AS (
            SELECT DISTINCT th.{COL_RACE_ID}
            FROM target_horses th
            INNER JOIN race_counts rc ON th.{COL_RACE_ID} = rc.{COL_RACE_ID}
        )
        SELECT
            r.{COL_RACE_ID},
            r.{COL_RACE_NAME},
            r.{COL_KAISAI_YEAR},
            r.{COL_KAISAI_MONTHDAY},
            r.{COL_JYOCD},
            r.{COL_KYORI},
            th.{COL_KETTONUM},
            th.{COL_BAMEI},
            th.{COL_UMABAN},
            th.kakutei_chakujun
        FROM matched_races mr
        INNER JOIN {TABLE_RACE} r ON mr.{COL_RACE_ID} = r.{COL_RACE_ID}
        INNER JOIN target_horses th ON mr.{COL_RACE_ID} = th.{COL_RACE_ID}
        WHERE r.{COL_DATA_KUBUN} = $2
        ORDER BY r.{COL_KAISAI_YEAR} DESC, r.{COL_KAISAI_MONTHDAY} DESC, r.{COL_RACE_ID} DESC
        LIMIT $3
    """

    try:
        rows = await conn.fetch(sql, kettonums, DATA_KUBUN_KAKUTEI, limit * len(kettonums))

        # レースごとにグループ化
        races_dict: dict[str, dict[str, Any]] = {}
        for row in rows:
            race_id = row[COL_RACE_ID]

            if race_id not in races_dict:
                races_dict[race_id] = {
                    "race_id": race_id,
                    "race_name": row[COL_RACE_NAME],
                    "race_date": f"{row[COL_KAISAI_YEAR]}-{row[COL_KAISAI_MONTHDAY][:2]}-{row[COL_KAISAI_MONTHDAY][2:]}",
                    "venue_code": row[COL_JYOCD],
                    "distance": row[COL_KYORI],
                    "horses": [],
                }

            races_dict[race_id]["horses"].append(
                {
                    "kettonum": row[COL_KETTONUM],
                    "name": row[COL_BAMEI],
                    "horse_number": row[COL_UMABAN],
                    "finish_position": row["kakutei_chakujun"],
                }
            )

        # リストに変換してソート（レース日付の新しい順）
        result = list(races_dict.values())
        result.sort(key=lambda x: x["race_date"], reverse=True)

        logger.info(f"Found {len(result)} head-to-head races for {len(kettonums)} horses")
        return result[:limit]

    except Exception as e:
        logger.error(f"Failed to get head-to-head data: {e}")
        raise


async def search_races_by_name_db(
    conn: Connection,
    race_name_query: str,
    days_before: int = 30,
    days_after: int = 30,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    レース名で検索（データベースから直接、エイリアス対応）

    Args:
        conn: データベース接続
        race_name_query: レース名検索クエリ（部分一致）
        days_before: 過去何日前まで検索するか
        days_after: 未来何日先まで検索するか
        limit: 最大取得件数

    Returns:
        マッチしたレースのリスト
    """
    from src.services.race_name_aliases import expand_race_name_query

    today = date.today()
    start_date = today - __import__("datetime").timedelta(days=days_before)
    end_date = today + __import__("datetime").timedelta(days=days_after)

    start_year = str(start_date.year)
    start_monthday = start_date.strftime("%m%d")
    end_year = str(end_date.year)
    end_monthday = end_date.strftime("%m%d")

    sql = f"""
        SELECT
            {COL_RACE_ID},
            {COL_RACE_NAME},
            {COL_KAISAI_YEAR},
            {COL_KAISAI_MONTHDAY},
            {COL_JYOCD},
            {COL_RACE_NUM},
            {COL_GRADE_CD},
            {COL_KYORI},
            {COL_TRACK_CD},
            {get_kyoso_joken_code_expr()},
            {COL_KYOSO_SHUBETSU_CD}
        FROM {TABLE_RACE}
        WHERE {COL_RACE_NAME} LIKE $1
          AND (
              ({COL_KAISAI_YEAR} > $2 OR ({COL_KAISAI_YEAR} = $2 AND {COL_KAISAI_MONTHDAY} >= $3))
              AND
              ({COL_KAISAI_YEAR} < $4 OR ({COL_KAISAI_YEAR} = $4 AND {COL_KAISAI_MONTHDAY} <= $5))
          )
          AND {COL_DATA_KUBUN} = $6
        ORDER BY {COL_KAISAI_YEAR} DESC, {COL_KAISAI_MONTHDAY} DESC, {COL_RACE_NUM} DESC
        LIMIT $7
    """

    try:
        # エイリアス展開（例: "日本ダービー" → ["日本ダービー", "東京優駿"]）
        search_terms = expand_race_name_query(race_name_query)
        logger.info(f"Expanded search terms: {search_terms}")

        all_results = []
        seen_race_ids = set()

        # 各検索語で検索（重複排除）
        for term in search_terms:
            search_pattern = f"%{term}%"
            logger.debug(f"Searching races with pattern: {search_pattern}")

            rows = await conn.fetch(
                sql,
                search_pattern,
                start_year,
                start_monthday,
                end_year,
                end_monthday,
                DATA_KUBUN_KAKUTEI,
                limit,
            )

            for row in rows:
                race_id = row[COL_RACE_ID]
                if race_id in seen_race_ids:
                    continue
                seen_race_ids.add(race_id)
                all_results.append(row)

        # 日付順にソート（新しい順）
        all_results.sort(key=lambda r: (r[COL_KAISAI_YEAR], r[COL_KAISAI_MONTHDAY]), reverse=True)

        # limit適用
        all_results = all_results[:limit]

        results = []
        for row in all_results:
            year = row[COL_KAISAI_YEAR]
            monthday = row[COL_KAISAI_MONTHDAY]
            race_date = f"{year}-{monthday[:2]}-{monthday[2:]}"

            results.append(
                {
                    "race_id": row[COL_RACE_ID],
                    "race_name": row[COL_RACE_NAME],
                    "race_date": race_date,
                    "venue_code": row[COL_JYOCD],
                    "race_number": row[COL_RACE_NUM],
                    "grade_code": row[COL_GRADE_CD],
                    "distance": row[COL_KYORI],
                    "track_code": row[COL_TRACK_CD],
                    "kyoso_joken_code": row.get("kyoso_joken_code"),
                    "kyoso_shubetsu_code": row.get(COL_KYOSO_SHUBETSU_CD),
                }
            )

        logger.info(f"Found {len(results)} races matching '{race_name_query}'")
        return results

    except Exception as e:
        logger.error(f"Failed to search races by name: {e}")
        raise
