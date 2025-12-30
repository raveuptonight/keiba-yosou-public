"""
JRA-VAN コードマッピング定義

データベースのコードテーブルから取得した値を
日本語名称にマッピングする
"""

from typing import Final, Dict, Optional

# ===== 競走条件コード (kyoso_joken_code) =====
KYOSO_JOKEN_CODE: Final[Dict[str, str]] = {
    "000": "",
    "001": "100万以下",
    "002": "200万以下",
    "003": "300万以下",
    "004": "400万以下",
    "005": "1勝クラス",
    "006": "600万以下",
    "007": "700万以下",
    "008": "800万以下",
    "009": "900万以下",
    "010": "2勝クラス",
    "011": "1100万以下",
    "012": "1200万以下",
    "013": "1300万以下",
    "014": "1400万以下",
    "015": "1500万以下",
    "016": "3勝クラス",
    "017": "1700万以下",
    "018": "1800万以下",
    "019": "1900万以下",
    "020": "2000万以下",
    "021": "2100万以下",
    "022": "2200万以下",
    "023": "2300万以下",
    "024": "2400万以下",
    "025": "2500万以下",
    "026": "2600万以下",
    "027": "2700万以下",
    "028": "2800万以下",
    "029": "2900万以下",
    "030": "3000万以下",
    "701": "未勝利",
    "702": "未出走",
    "703": "500万以下",
    "999": "オープン",
}

# ===== 競走種別コード (kyoso_shubetsu_code) =====
KYOSO_SHUBETSU_CODE: Final[Dict[str, str]] = {
    "11": "2歳",
    "12": "3歳",
    "13": "3歳以上",
    "14": "4歳以上",
    "15": "2歳牝馬",
    "16": "3歳牝馬",
    "17": "3歳以上牝馬",
    "18": "4歳以上牝馬",
    "21": "2歳新馬",
    "22": "3歳新馬",
    "23": "3歳以上新馬",
    "24": "4歳以上新馬",
}

# ===== グレードコード (grade_code) =====
GRADE_CODE: Final[Dict[str, str]] = {
    "A": "G1",
    "B": "G2",
    "C": "G3",
    "D": "Listed",
    "E": "オープン",
    "F": "1600万",
    "G": "1000万",
    "H": "500万",
    "I": "500万以下",
    "J": "新馬",
}

# ===== トラックコード (track_code) =====
TRACK_CODE: Final[Dict[str, str]] = {
    "10": "芝",
    "11": "芝・右",
    "12": "芝・左",
    "13": "芝・直線",
    "14": "芝・右外",
    "15": "芝・左外",
    "16": "芝・右内",
    "17": "芝・左内",
    "18": "芝・右外2周",
    "19": "芝・左外2周",
    "20": "ダート",
    "21": "ダート・右",
    "22": "ダート・左",
    "23": "ダート・直線",
    "24": "ダート・右外",
    "25": "ダート・左外",
    "26": "ダート・右内",
    "27": "ダート・左内",
    "29": "障害",
}

# ===== 競馬場コード (keibajo_code) =====
KEIBAJO_CODE: Final[Dict[str, str]] = {
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

# ===== 馬場状態コード (babajotai_code) =====
BABAJOTAI_CODE: Final[Dict[str, str]] = {
    "1": "良",
    "2": "稍重",
    "3": "重",
    "4": "不良",
}

# ===== 天候コード (tenko_code) =====
TENKO_CODE: Final[Dict[str, str]] = {
    "1": "晴",
    "2": "曇",
    "3": "雨",
    "4": "小雨",
    "5": "小雪",
    "6": "雪",
}

# ===== 性別コード (seibetsu_code) =====
SEIBETSU_CODE: Final[Dict[str, str]] = {
    "1": "牡",
    "2": "牝",
    "3": "セ",
}

# ===== 毛色コード (moshoku_code) =====
MOSHOKU_CODE: Final[Dict[str, str]] = {
    "1": "栗毛",
    "2": "栃栗毛",
    "3": "鹿毛",
    "4": "黒鹿毛",
    "5": "青鹿毛",
    "6": "青毛",
    "7": "芦毛",
    "8": "栗粕毛",
    "9": "鹿粕毛",
    "10": "青粕毛",
    "11": "白毛",
}


# ===== ヘルパー関数 =====

def get_kyoso_joken_name(code: str) -> str:
    """競走条件コードから名称を取得"""
    return KYOSO_JOKEN_CODE.get(code, "")


def get_kyoso_shubetsu_name(code: str) -> str:
    """競走種別コードから名称を取得"""
    return KYOSO_SHUBETSU_CODE.get(code, "")


def get_grade_name(code: str) -> str:
    """グレードコードから名称を取得"""
    return GRADE_CODE.get(code, "")


def get_track_name(code: str) -> str:
    """トラックコードから名称を取得"""
    return TRACK_CODE.get(code, "")


def get_keibajo_name(code: str) -> str:
    """競馬場コードから名称を取得"""
    return KEIBAJO_CODE.get(code, "")


def get_babajotai_name(code: str) -> str:
    """馬場状態コードから名称を取得"""
    return BABAJOTAI_CODE.get(code, "")


def get_tenko_name(code: str) -> str:
    """天候コードから名称を取得"""
    return TENKO_CODE.get(code, "")


def get_seibetsu_name(code: str) -> str:
    """性別コードから名称を取得"""
    return SEIBETSU_CODE.get(code, "")


def get_moshoku_name(code: str) -> str:
    """毛色コードから名称を取得"""
    return MOSHOKU_CODE.get(code, "")


def generate_race_condition_name(
    kyoso_joken_code: Optional[str],
    kyoso_shubetsu_code: Optional[str],
    grade_code: Optional[str]
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
    parts = []

    # 競走種別（年齢・性別）
    if kyoso_shubetsu_code:
        shubetsu = get_kyoso_shubetsu_name(kyoso_shubetsu_code)
        if shubetsu:
            parts.append(shubetsu)

    # 競走条件（クラス）
    if kyoso_joken_code:
        joken = get_kyoso_joken_name(kyoso_joken_code)
        if joken:
            parts.append(joken)

    # グレード（重賞の場合は上書き）
    if grade_code and grade_code in ['A', 'B', 'C', 'D']:
        # 重賞レースの場合は元のレース名を使うべき
        return ""

    if not parts:
        return "条件戦"

    return "".join(parts)
