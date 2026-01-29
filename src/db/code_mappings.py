"""
JRA-VAN コードマッピング定義 (DEPRECATED)

このファイルは後方互換性のために残されています。
新しいコードでは src.db.code_master を使用してください。

コードマスタテーブルから動的に値を取得するようになりました。
"""

# 新しいcode_masterモジュールから関数をインポート
from src.db.code_master import (
    generate_race_condition_name,
    get_babajotai_name,
    get_grade_name,
    get_keibajo_name,
    get_kyoso_joken_name,
    get_kyoso_shubetsu_name,
    get_moshoku_name,
    get_seibetsu_name,
    get_tenko_name,
    get_track_name,
)

# 後方互換性のため、__all__でエクスポート
__all__ = [
    "get_keibajo_name",
    "get_grade_name",
    "get_kyoso_shubetsu_name",
    "get_kyoso_joken_name",
    "get_track_name",
    "get_babajotai_name",
    "get_tenko_name",
    "get_seibetsu_name",
    "get_moshoku_name",
    "generate_race_condition_name",
]
