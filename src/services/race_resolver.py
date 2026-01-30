"""
レース指定文字列をレースIDに解決するモジュール

「京都2r」のような指定を実際のレースIDに変換
日付指定（2025-12-28）やレース名検索（有馬記念）にも対応
"""

import logging
import re
from datetime import date
from typing import Any

import requests

from src.config import API_BASE_URL_DEFAULT

# ロガー設定
logger = logging.getLogger(__name__)

# 競馬場名マッピング（略称含む）
VENUE_ALIASES = {
    # 中央競馬場
    "札幌": ["札幌", "さっぽろ"],
    "函館": ["函館", "はこだて"],
    "福島": ["福島", "ふくしま"],
    "新潟": ["新潟", "にいがた"],
    "東京": ["東京", "とうきょう"],
    "中山": ["中山", "なかやま"],
    "中京": ["中京", "ちゅうきょう"],
    "京都": ["京都", "きょうと"],
    "阪神": ["阪神", "はんしん"],
    "小倉": ["小倉", "こくら"],
}

# 逆引きマップ（略称 → 正式名称）
VENUE_NAME_MAP = {}
for official, aliases in VENUE_ALIASES.items():
    for alias in aliases:
        VENUE_NAME_MAP[alias] = official


class MultipleRacesFoundException(Exception):
    """複数のレースが見つかった場合の例外"""

    def __init__(self, message: str, races: list[dict[str, Any]]):
        super().__init__(message)
        self.races = races


class RaceResolver:
    """
    レース指定文字列をレースIDに解決するクラス
    """

    def __init__(self, api_base_url: str = API_BASE_URL_DEFAULT):
        """
        Args:
            api_base_url: API base URL
        """
        self.api_base_url = api_base_url
        logger.debug(f"RaceResolver初期化: api_base_url={api_base_url}")

    def parse_race_spec(self, race_spec: str) -> tuple[str, int] | None:
        """
        レース指定文字列をパース

        Args:
            race_spec: レース指定文字列（例: 京都2r, 中山11R）

        Returns:
            (競馬場名, レース番号) のタプル。パース失敗時はNone
        """
        # 正規表現でパース: 競馬場名 + 数字 + r/R
        pattern = r"^(.+?)(\d{1,2})[rR]$"
        match = re.match(pattern, race_spec.strip())

        if not match:
            logger.warning(f"レース指定文字列のパースに失敗: {race_spec}")
            return None

        venue_input = match.group(1).strip()
        race_number = int(match.group(2))

        # 競馬場名を正式名称に変換
        venue = VENUE_NAME_MAP.get(venue_input)

        if not venue:
            logger.warning(f"未知の競馬場名: {venue_input}")
            return None

        if race_number < 1 or race_number > 12:
            logger.warning(f"無効なレース番号: {race_number}")
            return None

        logger.debug(f"パース成功: venue={venue}, race_number={race_number}")
        return venue, race_number

    def resolve_to_race_id(self, race_spec: str, target_date: date | None = None) -> str | None:
        """
        レース指定文字列をレースIDに解決

        指定日（または今日）のレースのみを検索します。

        Args:
            race_spec: レース指定文字列（例: 京都2r）
            target_date: 対象日（省略時は本日JST）

        Returns:
            レースID。解決失敗時はNone
        """
        # レース指定文字列をパース
        parsed = self.parse_race_spec(race_spec)
        if not parsed:
            return None

        venue, race_number = parsed

        # 基準日が指定されていなければ本日
        if target_date is None:
            target_date = date.today()

        logger.info(
            f"レース解決開始: venue={venue}, race_number={race_number}, 対象日={target_date}"
        )

        # 指定日のレースのみを検索
        race_id = self._find_race_from_api(venue, race_number, target_date)
        if race_id:
            logger.info(
                f"レース解決成功: race_spec={race_spec} -> race_id={race_id} (日付: {target_date})"
            )
            return race_id

        logger.warning(
            f"レース解決失敗: race_spec={race_spec} ({target_date}に該当レースが見つかりませんでした)"
        )
        return None

    def _find_race_from_api(self, venue: str, race_number: int, target_date: date) -> str | None:
        """
        APIからレース一覧を取得して該当レースを検索

        Args:
            venue: 競馬場名
            race_number: レース番号
            target_date: 対象日

        Returns:
            レースID。見つからない場合はNone
        """
        try:
            # APIエンドポイント: /api/races/date/{target_date}
            response = requests.get(
                f"{self.api_base_url}/api/races/date/{target_date.isoformat()}", timeout=10
            )

            if response.status_code != 200:
                logger.error(f"レース一覧取得失敗: status={response.status_code}")
                return None

            data = response.json()
            races = data.get("races", [])

            logger.debug(f"API取得: {len(races)}件のレース（{target_date}）")

            for race in races:
                race_venue = race.get("venue", "")
                race_num_str = race.get("race_number", "")

                # race_numberは "11R" 形式なので数字部分を抽出
                try:
                    race_num = int(re.sub(r"[^0-9]", "", race_num_str))
                except (ValueError, TypeError):
                    continue

                logger.debug(f"チェック: {race_venue} {race_num}R vs {venue} {race_number}R")

                if race_venue == venue and race_num == race_number:
                    race_id = race.get("race_id")
                    logger.info(f"レース発見: {venue} {race_number}R -> {race_id}")
                    return race_id

            logger.debug(f"該当レース未発見: {venue} {race_number}R on {target_date}")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"レース一覧取得エラー: {e}")
            return None


def parse_date_input(date_input: str) -> date | None:
    """
    日付文字列をパース

    対応形式:
    - YYYY-MM-DD (例: 2025-12-28)
    - YYYY/MM/DD (例: 2025/12/28)
    - MM/DD (例: 12/28) - 今年または来年
    - MMDD (例: 1228) - 今年または来年

    Args:
        date_input: 日付文字列

    Returns:
        dateオブジェクト、パース失敗時はNone
    """
    date_input = date_input.strip()
    today = date.today()

    # YYYY-MM-DD or YYYY/MM/DD
    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", date_input)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    # MM/DD
    match = re.match(r"^(\d{1,2})/(\d{1,2})$", date_input)
    if match:
        try:
            month, day = int(match.group(1)), int(match.group(2))
            # 今年で試す
            target = date(today.year, month, day)
            # 過去の日付なら来年
            if target < today:
                target = date(today.year + 1, month, day)
            return target
        except ValueError:
            return None

    # MMDD
    match = re.match(r"^(\d{2})(\d{2})$", date_input)
    if match:
        try:
            month, day = int(match.group(1)), int(match.group(2))
            # 今年で試す
            target = date(today.year, month, day)
            # 過去の日付なら来年
            if target < today:
                target = date(today.year + 1, month, day)
            return target
        except ValueError:
            return None

    return None


def extract_year_from_input(race_input: str) -> tuple[int | None, str]:
    """
    入力から年度を抽出

    例:
    - "2022 日本ダービー" -> (2022, "日本ダービー")
    - "2024有馬記念" -> (2024, "有馬記念")
    - "有馬記念" -> (None, "有馬記念")

    Args:
        race_input: ユーザー入力

    Returns:
        (年度, レース名)のタプル。年度指定がない場合はNone
    """
    race_input = race_input.strip()

    # "YYYY レース名" or "YYYYレース名" のパターン
    match = re.match(r"^(\d{4})\s*(.+)$", race_input)
    if match:
        year_str = match.group(1)
        race_name = match.group(2).strip()
        try:
            year = int(year_str)
            # 妥当な年度範囲チェック（1980-2030）
            if 1980 <= year <= 2030:
                return (year, race_name)
        except ValueError:
            pass

    return (None, race_input)


def search_races_by_name(
    race_name: str, api_base_url: str = API_BASE_URL_DEFAULT, specific_year: int | None = None
) -> list[dict[str, Any]]:
    """
    レース名で検索（データベースから直接・高速）

    Args:
        race_name: レース名（部分一致）
        api_base_url: API base URL
        specific_year: 特定年度（指定時はその年のみ検索）

    Returns:
        マッチしたレースのリスト
    """
    try:
        # 検索範囲を決定
        if specific_year:
            # 特定年度指定時: その年の1/1〜12/31
            days_before = (date.today() - date(specific_year, 1, 1)).days
            days_after = (date(specific_year, 12, 31) - date.today()).days
        else:
            # 通常: 過去365日（今日を含まない）
            days_before = 365
            days_after = 0

        # 新しいAPI エンドポイントを使用（1回のリクエストで全検索）
        params: dict[str, Any] = {
            "query": race_name,
            "days_before": max(0, days_before),
            "days_after": max(0, days_after),
            "limit": 50,
        }
        response = requests.get(
            f"{api_base_url}/api/races/search/name",
            params=params,
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            races = data.get("races", [])

            # race_date フィールドを追加（互換性のため）
            for race in races:
                # race_idから日付を抽出（YYYYMMDDで始まる16桁）
                race_id = race.get("race_id", "")
                if len(race_id) >= 8:
                    year = race_id[:4]
                    month = race_id[4:6]
                    day = race_id[6:8]
                    race["race_date"] = f"{year}-{month}-{day}"

            logger.info(f"Found {len(races)} races matching '{race_name}' (API search)")
            return races

        logger.warning(f"API search failed with status {response.status_code}")
        return []

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to search races by name: {e}")
        return []


def _get_races_from_api(api_base_url: str, target_date: date) -> list[dict[str, Any]]:
    """
    APIから指定日のレース一覧を取得

    Args:
        api_base_url: API base URL
        target_date: 対象日

    Returns:
        レース一覧
    """
    try:
        response = requests.get(
            f"{api_base_url}/api/races/date/{target_date.isoformat()}", timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("races", [])
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"レース一覧取得エラー: {e}")
        return []


def resolve_race_input(race_input: str, api_base_url: str = API_BASE_URL_DEFAULT) -> str:
    """
    レース指定文字列をレースIDに解決（ユーティリティ関数）

    対応形式:
    1. レースID (16桁): 2025122806050811
    2. 競馬場+レース番号: 京都2r, 中山11R
    3. 日付: 2025-12-28, 12/28, 1228
    4. レース名: 有馬記念, 京都金杯

    Args:
        race_input: レース指定文字列
        api_base_url: API base URL

    Returns:
        レースID（解決済み、または元の入力がすでにレースID）

    Raises:
        ValueError: レース指定が無効な場合
        MultipleRacesFoundException: 複数のレースが見つかった場合
    """
    race_input = race_input.strip()

    # 1. すでにレースID形式（16桁の数字）の場合はそのまま返す
    if re.match(r"^\d{16}$", race_input):
        logger.debug(f"レースID形式と判定: {race_input}")
        return race_input

    # 2. 日付形式かチェック
    target_date = parse_date_input(race_input)
    if target_date:
        logger.info(f"日付指定と判定: {race_input} -> {target_date}")
        races = _get_races_from_api(api_base_url, target_date)

        if not races:
            raise ValueError(f"{target_date}のレースが見つかりません")

        # 複数レースがある場合は選択させる
        if len(races) > 1:
            raise MultipleRacesFoundException(
                f"{target_date}に{len(races)}件のレースがあります。選択してください。", races
            )

        # 1件だけならそれを返す
        return races[0]["race_id"]

    # 3. 競馬場名+レース番号形式かチェック
    if re.match(r"^.+\d{1,2}[rR]$", race_input):
        resolver = RaceResolver(api_base_url)
        race_id = resolver.resolve_to_race_id(race_input)

        if race_id:
            return race_id
        else:
            raise ValueError(
                f"'{race_input}'のレースが今日見つかりません。\n"
                f"開催予定、もしくは過去のレースの場合は日付をYYYY-MM-DD形式で指定してください。\n"
                f"例: 2024-12-28 または 2024/12/28"
            )

    # 4. レース名検索（年度指定対応）
    specific_year, race_name = extract_year_from_input(race_input)
    logger.info(
        f"レース名検索: {race_name}" + (f" (年度: {specific_year})" if specific_year else "")
    )
    races = search_races_by_name(race_name, api_base_url, specific_year)

    if not races:
        year_msg = f"{specific_year}年の" if specific_year else ""
        raise ValueError(
            f"{year_msg}レース '{race_name}' が見つかりません。\n"
            f"例: 京都2r, 2025-12-28, 有馬記念, 2022 日本ダービー, または16桁のレースID"
        )

    # 複数レースがある場合は最新のレースを返す
    if len(races) > 1:
        # race_dateでソート（降順）して最新のレースを取得
        sorted_races = sorted(races, key=lambda r: r.get("race_date", ""), reverse=True)
        latest_race = sorted_races[0]
        logger.info(
            f"複数レース検出（{len(races)}件）、最新のレースを選択: {latest_race.get('race_date')}"
        )
        return latest_race["race_id"]

    # 1件だけならそれを返す
    return races[0]["race_id"]
