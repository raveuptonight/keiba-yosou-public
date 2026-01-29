"""
コードマスタテーブルからマッピングを取得

JRA-VANのコードマスタテーブルから各種コードの名称を取得し、
キャッシュして使用する。
"""

import logging

from asyncpg import Connection

logger = logging.getLogger(__name__)

# グローバルキャッシュ（起動時に一度だけロード）
_CODE_CACHE: dict[str, dict[str, str]] = {}


async def load_code_master(conn: Connection, table_name: str) -> dict[str, str]:
    """
    コードマスタテーブルから code -> meisho のマッピングを取得

    Args:
        conn: データベース接続
        table_name: コードマスタテーブル名

    Returns:
        コード -> 名称 のマッピング辞書
    """
    try:
        # テーブルごとに異なるカラム名を使用
        if table_name == "keibajo_code":
            # 競馬場コードは jomei カラムを使用
            query = f"SELECT code, jomei AS meisho FROM {table_name}"
        elif table_name == "tozai_shozoku_code":
            # 東西所属コードは meisho2 カラムを使用（美浦/栗東）
            query = f"SELECT code, meisho2 AS meisho FROM {table_name}"
        else:
            # その他のテーブルは meisho カラムを使用
            query = f"SELECT code, meisho FROM {table_name}"

        rows = await conn.fetch(query)

        mapping = {}
        for row in rows:
            code = row["code"].strip() if row["code"] else ""
            meisho = row["meisho"].strip() if row["meisho"] else ""
            if code:  # 空コードは除外
                mapping[code] = meisho

        logger.info(f"Loaded {len(mapping)} codes from {table_name}")
        return mapping

    except Exception as e:
        logger.error(f"Failed to load code master {table_name}: {e}")
        return {}


async def initialize_code_cache(conn: Connection) -> None:
    """
    全コードマスタをキャッシュにロード

    Args:
        conn: データベース接続
    """
    global _CODE_CACHE

    # ロード対象のコードマスタテーブル
    tables = [
        "keibajo_code",  # 競馬場コード
        "grade_code",  # グレードコード
        "kyoso_shubetsu_code",  # 競走種別コード
        "kyoso_joken_code",  # 競走条件コード
        "track_code",  # トラックコード
        "babajotai_code",  # 馬場状態コード
        "tenko_code",  # 天候コード
        "seibetsu_code",  # 性別コード
        "moshoku_code",  # 毛色コード
        "tozai_shozoku_code",  # 東西所属コード
    ]

    for table in tables:
        _CODE_CACHE[table] = await load_code_master(conn, table)

    logger.info(f"Code cache initialized with {len(_CODE_CACHE)} tables")


def get_code_name(table_name: str, code: str) -> str:
    """
    コードから名称を取得（キャッシュから）

    Args:
        table_name: コードマスタテーブル名
        code: コード値

    Returns:
        名称（見つからない場合は空文字列）
    """
    if not code:
        return ""

    code = code.strip()

    if table_name not in _CODE_CACHE:
        logger.warning(f"Code table {table_name} not in cache")
        return ""

    return _CODE_CACHE[table_name].get(code, "")


# ===== ヘルパー関数（後方互換性のため） =====


def get_keibajo_name(code: str) -> str:
    """競馬場コードから名称を取得"""
    return get_code_name("keibajo_code", code)


def get_grade_name(code: str) -> str:
    """グレードコードから名称を取得"""
    return get_code_name("grade_code", code)


def get_kyoso_shubetsu_name(code: str) -> str:
    """競走種別コードから名称を取得"""
    name = get_code_name("kyoso_shubetsu_code", code)
    # "サラブレッド系3歳" -> "3歳" のように簡略化
    if "サラブレッド系" in name:
        name = name.replace("サラブレッド系", "").strip()
    return name


def get_kyoso_joken_name(code: str) -> str:
    """競走条件コードから名称を取得"""
    return get_code_name("kyoso_joken_code", code)


def get_track_name(code: str) -> str:
    """トラックコードから名称を取得"""
    return get_code_name("track_code", code)


def get_babajotai_name(code: str) -> str:
    """馬場状態コードから名称を取得"""
    return get_code_name("babajotai_code", code)


def get_tenko_name(code: str) -> str:
    """天候コードから名称を取得"""
    return get_code_name("tenko_code", code)


def get_seibetsu_name(code: str) -> str:
    """性別コードから名称を取得"""
    return get_code_name("seibetsu_code", code)


def get_moshoku_name(code: str) -> str:
    """毛色コードから名称を取得"""
    return get_code_name("moshoku_code", code)


def generate_race_condition_name(
    kyoso_joken_code: str | None, kyoso_shubetsu_code: str | None, grade_code: str | None
) -> str:
    """
    レース条件から条件戦の名称を生成

    Args:
        kyoso_joken_code: 競走条件コード
        kyoso_shubetsu_code: 競走種別コード
        grade_code: グレードコード

    Returns:
        生成されたレース名（例: "3歳未勝利", "3歳以上1勝クラス"）
    """
    # 重賞レースの場合は元のレース名を使うべき
    if grade_code and grade_code in ["A", "B", "C", "D"]:
        return ""

    parts = []

    # 競走種別（年齢・性別）
    if kyoso_shubetsu_code:
        shubetsu = get_kyoso_shubetsu_name(kyoso_shubetsu_code)
        if shubetsu:
            parts.append(shubetsu)

    # 競走条件（クラス）
    if kyoso_joken_code and kyoso_joken_code != "000":
        joken = get_kyoso_joken_name(kyoso_joken_code)
        if joken:
            parts.append(joken)

    if not parts:
        return "条件戦"

    return "".join(parts)
