"""
馬情報取得クエリモジュール

馬の基本情報、過去成績、血統情報、調教情報などを取得するクエリ群
"""

import logging
from datetime import date, timedelta
from typing import Any

from asyncpg import Connection

from src.config import ML_TRAINING_YEARS_BACK
from src.db.table_names import (
    COL_BAMEI,
    COL_BATAIJU,
    COL_BIRTH_DATE,
    COL_CHOKYOSI_NAME,
    COL_CHOKYOSICODE,
    COL_DATA_KUBUN,
    COL_DIRT_BABA_CD,
    COL_HANSYOKU_NUM,
    COL_JYOCD,
    COL_KAISAI_MONTHDAY,
    COL_KAISAI_YEAR,
    COL_KAKUTEI_CHAKUJUN,
    COL_KEIROCODE,
    COL_KETTONUM,
    COL_KINRYO,
    COL_KISYU_NAME,
    COL_KISYUCODE,
    COL_KYORI,
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_SEX,
    COL_SHIBA_BABA_CD,
    COL_TIME,
    COL_TOZAI_CODE,
    DATA_KUBUN_KAKUTEI,
    TABLE_CHOKYOSI,
    TABLE_HANRO_CHOKYO,
    TABLE_HANSYOKU,
    TABLE_KISYU,
    TABLE_RACE,
    TABLE_SANKU,
    TABLE_SHUTUBA_KYORI,
    TABLE_UMA,
    TABLE_UMA_RACE,
    TABLE_WOOD_CHOKYO,
)

logger = logging.getLogger(__name__)


async def get_horse_info(conn: Connection, kettonum: str) -> dict[str, Any] | None:
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
            u.{COL_KETTONUM},
            u.{COL_BAMEI},
            u.{COL_BIRTH_DATE},
            u.{COL_SEX},
            u.{COL_KEIROCODE},
            u.ketto1_hanshoku_toroku_bango,
            u.ketto2_hanshoku_toroku_bango,
            u.seisansha_code,
            u.banushi_code,
            u.{COL_CHOKYOSICODE},
            ch.{COL_CHOKYOSI_NAME},
            ch.{COL_TOZAI_CODE} as tozai_code,
            u.heichi_honshokin_ruikei,
            u.shogai_honshokin_ruikei,
            u.heichi_fukashokin_ruikei,
            u.shogai_fukashokin_ruikei,
            u.heichi_shutokushokin_ruikei,
            u.shogai_shutokushokin_ruikei,
            u.sogo_1chaku,
            u.sogo_2chaku,
            u.sogo_3chaku,
            u.sogo_4chaku,
            u.sogo_5chaku,
            u.sogo_chakugai,
            -- 賞金合計を計算（カラムがcharacter型の場合に対応）
            COALESCE(NULLIF(u.heichi_honshokin_ruikei, '')::bigint, 0) +
            COALESCE(NULLIF(u.shogai_honshokin_ruikei, '')::bigint, 0) +
            COALESCE(NULLIF(u.heichi_fukashokin_ruikei, '')::bigint, 0) +
            COALESCE(NULLIF(u.shogai_fukashokin_ruikei, '')::bigint, 0) +
            COALESCE(NULLIF(u.heichi_shutokushokin_ruikei, '')::bigint, 0) +
            COALESCE(NULLIF(u.shogai_shutokushokin_ruikei, '')::bigint, 0) as total_prize_money
        FROM {TABLE_UMA} u
        LEFT JOIN {TABLE_CHOKYOSI} ch ON u.{COL_CHOKYOSICODE} = ch.{COL_CHOKYOSICODE}
        WHERE u.{COL_KETTONUM} = $1
    """

    try:
        row = await conn.fetchrow(sql, kettonum)
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get horse info: kettonum={kettonum}, error={e}")
        raise


async def get_horses_recent_races(
    conn: Connection,
    kettonums: list[str],
    limit: int = 10
) -> dict[str, list[dict[str, Any]]]:
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
                COALESCE(ra.{COL_SHIBA_BABA_CD}, ra.{COL_DIRT_BABA_CD}) as baba_jotai,
                ra.{COL_RACE_NAME},
                ra.grade_code,
                se.{COL_KAKUTEI_CHAKUJUN},
                se.{COL_TIME},
                se.{COL_KISYUCODE},
                se.{COL_KINRYO} as futan,
                se.{COL_BATAIJU},
                se.tansho_odds,
                se.kakutoku_honshokin,
                se.umaban,
                se.zogen_sa,
                se.corner1_juni,
                se.corner2_juni,
                se.corner3_juni,
                se.corner4_juni,
                se.time_sa,
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
        SELECT
            rr.*,
            winner.{COL_BAMEI} as winner_name,
            ks.{COL_KISYU_NAME}
        FROM ranked_races rr
        LEFT JOIN {TABLE_UMA_RACE} winner
            ON rr.{COL_RACE_ID} = winner.{COL_RACE_ID}
            AND winner.{COL_KAKUTEI_CHAKUJUN} = '1'
            AND winner.{COL_DATA_KUBUN} = $2
        LEFT JOIN {TABLE_KISYU} ks
            ON rr.{COL_KISYUCODE} = ks.{COL_KISYUCODE}
        WHERE rr.rn <= $4
        ORDER BY rr.{COL_KETTONUM}, rr.rn
    """

    try:
        rows = await conn.fetch(sql, kettonums, DATA_KUBUN_KAKUTEI, cutoff_year, limit)

        # kettonum ごとにグループ化
        result: dict[str, list[dict[str, Any]]] = {}
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
) -> list[dict[str, Any]]:
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
    kettonums: list[str]
) -> dict[str, dict[str, Any]]:
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
            sk.ketto1_hanshoku_toroku_bango AS chichi,
            sk.ketto2_hanshoku_toroku_bango AS haha,
            sk.ketto3_hanshoku_toroku_bango AS chichi_chichi,
            sk.ketto4_hanshoku_toroku_bango AS chichi_haha,
            sk.ketto5_hanshoku_toroku_bango AS haha_chichi,
            sk.ketto6_hanshoku_toroku_bango AS haha_haha,
            hn_f.bamei AS chichi_name,
            hn_m.bamei AS haha_name,
            hn_ff.bamei AS chichi_chichi_name,
            hn_fm.bamei AS chichi_haha_name,
            hn_mf.bamei AS haha_chichi_name,
            hn_mm.bamei AS haha_haha_name
        FROM {TABLE_SANKU} sk
        LEFT JOIN {TABLE_HANSYOKU} hn_f
            ON sk.ketto1_hanshoku_toroku_bango = hn_f.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_m
            ON sk.ketto2_hanshoku_toroku_bango = hn_m.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_ff
            ON sk.ketto3_hanshoku_toroku_bango = hn_ff.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_fm
            ON sk.ketto4_hanshoku_toroku_bango = hn_fm.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_mf
            ON sk.ketto5_hanshoku_toroku_bango = hn_mf.{COL_HANSYOKU_NUM}
        LEFT JOIN {TABLE_HANSYOKU} hn_mm
            ON sk.ketto6_hanshoku_toroku_bango = hn_mm.{COL_HANSYOKU_NUM}
        WHERE sk.{COL_KETTONUM} = ANY($1)
    """

    try:
        rows = await conn.fetch(sql, kettonums)

        # kettonum ごとに辞書化
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            result[kettonum] = dict(row)

        return result
    except Exception as e:
        logger.error(f"Failed to get horses pedigree: kettonums={kettonums[:3]}..., error={e}")
        raise


async def get_horses_training(
    conn: Connection,
    kettonums: list[str],
    days_back: int = 30
) -> dict[str, list[dict[str, Any]]]:
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
                ketto_toroku_bango,
                chokyo_nengappi,
                'hanro' AS training_type,
                tracen_kubun,
                time_gokei_4furlong,
                time_gokei_3furlong,
                lap_time_4furlong,
                lap_time_3furlong
            FROM {TABLE_HANRO_CHOKYO}
            WHERE ketto_toroku_bango = ANY($1)
              AND chokyo_nengappi >= $2
              AND time_gokei_4furlong IS NOT NULL
              AND time_gokei_4furlong <> '0'

            UNION ALL

            -- ウッド調教
            SELECT
                ketto_toroku_bango,
                chokyo_nengappi,
                'wood' AS training_type,
                tracen_kubun,
                time_gokei_6furlong AS time_gokei_4furlong,
                time_gokei_5furlong AS time_gokei_3furlong,
                laptime_6furlong AS lap_time_4furlong,
                laptime_5furlong AS lap_time_3furlong
            FROM {TABLE_WOOD_CHOKYO}
            WHERE ketto_toroku_bango = ANY($1)
              AND chokyo_nengappi >= $2
              AND time_gokei_6furlong IS NOT NULL
              AND time_gokei_6furlong <> '0'
        ),
        ranked_training AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY ketto_toroku_bango
                    ORDER BY chokyo_nengappi DESC
                ) AS rn
            FROM combined_training
        )
        SELECT *
        FROM ranked_training
        WHERE rn <= 5
        ORDER BY ketto_toroku_bango, rn
    """

    try:
        rows = await conn.fetch(sql, kettonums, cutoff_date)

        # kettonum ごとにグループ化
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            kettonum = row['ketto_toroku_bango']
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
    kettonums: list[str]
) -> dict[str, dict[str, Any]]:
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
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            kettonum = row[COL_KETTONUM]
            result[kettonum] = dict(row)

        return result
    except Exception as e:
        # 統計テーブルが存在しない場合は空の辞書を返す
        logger.warning(f"Statistics not available: race_id={race_id}, error={e}")
        return {}


async def get_horse_detail(
    conn: Connection,
    kettonum: str,
    history_limit: int = 10
) -> dict[str, Any] | None:
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


async def search_horses_by_name(
    conn: Connection,
    name: str,
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    馬名で馬を検索

    Args:
        conn: データベース接続
        name: 馬名（部分一致）
        limit: 取得件数上限

    Returns:
        馬情報のリスト
    """
    # kyosoba_master2の実カラム名を直接使用
    sql = f"""
        SELECT
            u.ketto_toroku_bango,
            u.bamei,
            u.seibetsu_code,
            u.seinengappi,
            (
                SELECT COUNT(*)
                FROM {TABLE_UMA_RACE} ur
                WHERE ur.ketto_toroku_bango = u.ketto_toroku_bango
                  AND ur.data_kubun = '7'
            ) as race_count,
            (
                SELECT COUNT(*)
                FROM {TABLE_UMA_RACE} ur
                WHERE ur.ketto_toroku_bango = u.ketto_toroku_bango
                  AND ur.data_kubun = '7'
                  AND ur.kakutei_chakujun = '01'
            ) as win_count
        FROM {TABLE_UMA} u
        WHERE u.bamei LIKE $1
        ORDER BY u.seinengappi DESC NULLS LAST
        LIMIT $2
    """

    try:
        # 部分一致検索のパターン
        search_pattern = f"%{name}%"
        rows = await conn.fetch(sql, search_pattern, limit)

        result = []
        for row in rows:
            result.append({
                "kettonum": row["ketto_toroku_bango"].strip() if row["ketto_toroku_bango"] else "",
                "name": row["bamei"].strip() if row["bamei"] else "",
                "sex": row["seibetsu_code"].strip() if row["seibetsu_code"] else "",
                "birth_date": row["seinengappi"],
                "runs": row["race_count"] or 0,
                "wins": row["win_count"] or 0,
            })

        return result
    except Exception as e:
        logger.error(f"Failed to search horses by name: name={name}, error={e}")
        raise


async def get_training_before_race(
    conn: Connection,
    kettonum: str,
    race_date: str,
    days_before: int = 14
) -> dict[str, Any] | None:
    """
    レース前の直近調教データを取得

    Args:
        conn: データベース接続
        kettonum: 血統登録番号
        race_date: レース日（YYYYMMDD形式）
        days_before: 何日前まで遡るか（デフォルト: 14日）

    Returns:
        調教データ（坂路またはウッドチップ）
    """
    try:
        # race_dateをdate型に変換
        race_year = int(race_date[:4])
        race_month = int(race_date[4:6])
        race_day = int(race_date[6:8])
        race_dt = date(race_year, race_month, race_day)

        # 検索開始日
        start_date = race_dt - timedelta(days=days_before)
        start_date_str = start_date.strftime("%Y%m%d")

        # 坂路調教データを検索
        hanro_sql = f"""
            SELECT
                chokyo_nengappi as training_date,
                time_gokei_4furlong as time_4f,
                time_gokei_3furlong as time_3f,
                '坂路' as training_type
            FROM {TABLE_HANRO_CHOKYO}
            WHERE {COL_KETTONUM} = $1
              AND chokyo_nengappi >= $2
              AND chokyo_nengappi < $3
              AND {COL_DATA_KUBUN} = $4
            ORDER BY chokyo_nengappi DESC
            LIMIT 1
        """

        hanro_row = await conn.fetchrow(
            hanro_sql,
            kettonum,
            start_date_str,
            race_date,
            DATA_KUBUN_KAKUTEI
        )

        # ウッドチップ調教データを検索
        wood_sql = f"""
            SELECT
                chokyo_nengappi as training_date,
                time_gokei_4furlong as time_4f,
                time_gokei_3furlong as time_3f,
                'ウッド' as training_type
            FROM {TABLE_WOOD_CHOKYO}
            WHERE {COL_KETTONUM} = $1
              AND chokyo_nengappi >= $2
              AND chokyo_nengappi < $3
              AND {COL_DATA_KUBUN} = $4
            ORDER BY chokyo_nengappi DESC
            LIMIT 1
        """

        wood_row = await conn.fetchrow(
            wood_sql,
            kettonum,
            start_date_str,
            race_date,
            DATA_KUBUN_KAKUTEI
        )

        # より新しい方を返す
        if hanro_row and wood_row:
            if hanro_row["training_date"] >= wood_row["training_date"]:
                return dict(hanro_row)
            else:
                return dict(wood_row)
        elif hanro_row:
            return dict(hanro_row)
        elif wood_row:
            return dict(wood_row)
        else:
            return None

    except Exception as e:
        logger.error(f"Failed to get training data: kettonum={kettonum}, race_date={race_date}, error={e}")
        return None
