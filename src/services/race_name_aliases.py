"""
Race Name Aliases Mapping

Provides mapping from common nicknames to official names
so users can search using colloquial terms.
"""

# Race name aliases (nickname -> official name patterns)
RACE_NAME_ALIASES: dict[str, list[str]] = {
    # G1 races
    "日本ダービー": ["東京優駿"],
    "ダービー": ["東京優駿", "ダービー"],
    "皐月賞": ["皐月賞"],
    "桜花賞": ["桜花賞"],
    "オークス": ["優駿牝馬"],
    "優駿牝馬": ["優駿牝馬"],
    "菊花賞": ["菊花賞"],
    "天皇賞春": ["天皇賞（春）", "天皇賞(春)"],
    "天皇賞秋": ["天皇賞（秋）", "天皇賞(秋)"],
    "宝塚記念": ["宝塚記念"],
    "有馬記念": ["有馬記念"],
    "ジャパンカップ": ["ジャパンカップ", "ジャパンＣ"],
    "安田記念": ["安田記念"],
    "マイルチャンピオンシップ": ["マイルチャンピオンシップ", "マイルＣＳ"],
    "マイルCS": ["マイルチャンピオンシップ", "マイルＣＳ"],
    "スプリンターズステークス": ["スプリンターズステークス", "スプリンターズＳ"],
    "スプリンターズS": ["スプリンターズステークス", "スプリンターズＳ"],
    "エリザベス女王杯": ["エリザベス女王杯"],
    "秋華賞": ["秋華賞"],
    "フェブラリーステークス": ["フェブラリーステークス", "フェブラリーＳ"],
    "フェブラリーS": ["フェブラリーステークス", "フェブラリーＳ"],
    "高松宮記念": ["高松宮記念"],
    "大阪杯": ["大阪杯"],
    "ヴィクトリアマイル": ["ヴィクトリアマイル"],
    # 2-year-old G1
    "朝日杯": ["朝日杯フューチュリティステークス", "朝日杯ＦＳ"],
    "朝日杯FS": ["朝日杯フューチュリティステークス", "朝日杯ＦＳ"],
    "阪神ジュベナイルフィリーズ": ["阪神ジュベナイルフィリーズ", "阪神ＪＦ"],
    "阪神JF": ["阪神ジュベナイルフィリーズ", "阪神ＪＦ"],
    "ホープフルステークス": ["ホープフルステークス", "ホープフルＳ"],
    "ホープフルS": ["ホープフルステークス", "ホープフルＳ"],
    # Fillies G1
    "桜花": ["桜花賞"],
    "秋華": ["秋華賞"],
    # Other major races (including G2/G3)
    "NHKマイル": ["ＮＨＫマイルカップ", "ＮＨKマイルＣ"],
    "NHKマイルC": ["ＮＨＫマイルカップ", "ＮＨKマイルＣ"],
    "チャンピオンズカップ": ["チャンピオンズカップ", "チャンピオンズＣ"],
    "チャンピオンズC": ["チャンピオンズカップ", "チャンピオンズＣ"],
    # G2 races
    "オールカマー": ["オールカマー", "産経賞オールカマー"],
    "京都記念": ["京都記念"],
    "阪神大賞典": ["阪神大賞典"],
    "日経賞": ["日経賞"],
    "金鯱賞": ["金鯱賞"],
    "京成杯AH": ["京成杯オータムハンデキャップ", "京成杯ＡＨ"],
    "神戸新聞杯": ["神戸新聞杯"],
    "毎日王冠": ["毎日王冠"],
    "京都大賞典": ["京都大賞典"],
    "ステイヤーズS": ["ステイヤーズステークス", "ステイヤーズＳ"],
    "中山金杯": ["中山金杯"],
    "京都金杯": ["京都金杯"],
    "日経新春杯": ["日経新春杯"],
    "きさらぎ賞": ["きさらぎ賞"],
    "小倉大賞典": ["小倉大賞典"],
    "中山記念": ["中山記念"],
    "弥生賞": ["弥生賞"],
    "阪神牝馬S": ["阪神牝馬ステークス", "阪神牝馬Ｓ"],
    "産経大阪杯": ["大阪杯", "産経大阪杯"],
}


def expand_race_name_query(query: str) -> list[str]:
    """
    Expand race name query using aliases.

    Args:
        query: Race name entered by user

    Returns:
        List of race names to search (original query + aliases)
    """
    query_lower = query.lower().strip()

    # Check alias mapping
    search_terms = [query]  # Include original query

    for alias, official_names in RACE_NAME_ALIASES.items():
        if alias.lower() == query_lower or alias.lower() in query_lower:
            search_terms.extend(official_names)
            break

    # Remove duplicates
    return list(set(search_terms))


def get_primary_search_term(query: str) -> str:
    """
    Get the primary search term.

    Args:
        query: Race name entered by user

    Returns:
        Primary search term (first official name if alias exists, otherwise original query)
    """
    query_lower = query.lower().strip()

    for alias, official_names in RACE_NAME_ALIASES.items():
        if alias.lower() == query_lower:
            return official_names[0]

    return query
