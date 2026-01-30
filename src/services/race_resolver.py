"""
Race Specification String Resolver Module

Resolves specifications like "京都2r" to actual race IDs.
Also supports date specification (2025-12-28) and race name search (有馬記念).
"""

import logging
import re
from datetime import date
from typing import Any

import requests

from src.config import API_BASE_URL_DEFAULT

# Logger configuration
logger = logging.getLogger(__name__)

# Venue name mapping (including abbreviations)
VENUE_ALIASES = {
    # JRA racecourses
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

# Reverse lookup map (alias -> official name)
VENUE_NAME_MAP = {}
for official, aliases in VENUE_ALIASES.items():
    for alias in aliases:
        VENUE_NAME_MAP[alias] = official


class MultipleRacesFoundException(Exception):
    """Exception raised when multiple races are found."""

    def __init__(self, message: str, races: list[dict[str, Any]]):
        super().__init__(message)
        self.races = races


class RaceResolver:
    """
    Class for resolving race specification strings to race IDs.
    """

    def __init__(self, api_base_url: str = API_BASE_URL_DEFAULT):
        """
        Args:
            api_base_url: API base URL
        """
        self.api_base_url = api_base_url
        logger.debug(f"RaceResolver initialized: api_base_url={api_base_url}")

    def parse_race_spec(self, race_spec: str) -> tuple[str, int] | None:
        """
        Parse a race specification string.

        Args:
            race_spec: Race specification string (e.g., 京都2r, 中山11R)

        Returns:
            Tuple of (venue name, race number). None if parsing fails.
        """
        # Parse with regex: venue name + number + r/R
        pattern = r"^(.+?)(\d{1,2})[rR]$"
        match = re.match(pattern, race_spec.strip())

        if not match:
            logger.warning(f"Failed to parse race specification: {race_spec}")
            return None

        venue_input = match.group(1).strip()
        race_number = int(match.group(2))

        # Convert venue name to official name
        venue = VENUE_NAME_MAP.get(venue_input)

        if not venue:
            logger.warning(f"Unknown venue name: {venue_input}")
            return None

        if race_number < 1 or race_number > 12:
            logger.warning(f"Invalid race number: {race_number}")
            return None

        logger.debug(f"Parse successful: venue={venue}, race_number={race_number}")
        return venue, race_number

    def resolve_to_race_id(self, race_spec: str, target_date: date | None = None) -> str | None:
        """
        Resolve a race specification string to a race ID.

        Searches only races on the specified date (or today).

        Args:
            race_spec: Race specification string (e.g., 京都2r)
            target_date: Target date (defaults to today JST if omitted)

        Returns:
            Race ID. None if resolution fails.
        """
        # Parse race specification string
        parsed = self.parse_race_spec(race_spec)
        if not parsed:
            return None

        venue, race_number = parsed

        # Default to today if no date specified
        if target_date is None:
            target_date = date.today()

        logger.info(
            f"Starting race resolution: venue={venue}, race_number={race_number}, target_date={target_date}"
        )

        # Search only races on the specified date
        race_id = self._find_race_from_api(venue, race_number, target_date)
        if race_id:
            logger.info(
                f"Race resolution successful: race_spec={race_spec} -> race_id={race_id} (date: {target_date})"
            )
            return race_id

        logger.warning(
            f"Race resolution failed: race_spec={race_spec} (no matching race found on {target_date})"
        )
        return None

    def _find_race_from_api(self, venue: str, race_number: int, target_date: date) -> str | None:
        """
        Fetch race list from API and search for the matching race.

        Args:
            venue: Venue name
            race_number: Race number
            target_date: Target date

        Returns:
            Race ID. None if not found.
        """
        try:
            # API endpoint: /api/races/date/{target_date}
            response = requests.get(
                f"{self.api_base_url}/api/races/date/{target_date.isoformat()}", timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch race list: status={response.status_code}")
                return None

            data = response.json()
            races = data.get("races", [])

            logger.debug(f"API response: {len(races)} races ({target_date})")

            for race in races:
                race_venue = race.get("venue", "")
                race_num_str = race.get("race_number", "")

                # race_number is in "11R" format, extract numeric part
                try:
                    race_num = int(re.sub(r"[^0-9]", "", race_num_str))
                except (ValueError, TypeError):
                    continue

                logger.debug(f"Checking: {race_venue} {race_num}R vs {venue} {race_number}R")

                if race_venue == venue and race_num == race_number:
                    race_id = race.get("race_id")
                    logger.info(f"Race found: {venue} {race_number}R -> {race_id}")
                    return race_id

            logger.debug(f"No matching race found: {venue} {race_number}R on {target_date}")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching race list: {e}")
            return None


def parse_date_input(date_input: str) -> date | None:
    """
    Parse a date string.

    Supported formats:
    - YYYY-MM-DD (e.g., 2025-12-28)
    - YYYY/MM/DD (e.g., 2025/12/28)
    - MM/DD (e.g., 12/28) - this year or next year
    - MMDD (e.g., 1228) - this year or next year

    Args:
        date_input: Date string

    Returns:
        date object, None if parsing fails
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
            # Try this year first
            target = date(today.year, month, day)
            # If in the past, use next year
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
            # Try this year first
            target = date(today.year, month, day)
            # If in the past, use next year
            if target < today:
                target = date(today.year + 1, month, day)
            return target
        except ValueError:
            return None

    return None


def extract_year_from_input(race_input: str) -> tuple[int | None, str]:
    """
    Extract year from input.

    Examples:
    - "2022 日本ダービー" -> (2022, "日本ダービー")
    - "2024有馬記念" -> (2024, "有馬記念")
    - "有馬記念" -> (None, "有馬記念")

    Args:
        race_input: User input

    Returns:
        Tuple of (year, race name). Year is None if not specified.
    """
    race_input = race_input.strip()

    # Pattern: "YYYY race_name" or "YYYYrace_name"
    match = re.match(r"^(\d{4})\s*(.+)$", race_input)
    if match:
        year_str = match.group(1)
        race_name = match.group(2).strip()
        try:
            year = int(year_str)
            # Check reasonable year range (1980-2030)
            if 1980 <= year <= 2030:
                return (year, race_name)
        except ValueError:
            pass

    return (None, race_input)


def search_races_by_name(
    race_name: str, api_base_url: str = API_BASE_URL_DEFAULT, specific_year: int | None = None
) -> list[dict[str, Any]]:
    """
    Search races by name (directly from database - fast).

    Args:
        race_name: Race name (partial match)
        api_base_url: API base URL
        specific_year: Specific year (searches only that year if specified)

    Returns:
        List of matching races
    """
    try:
        # Determine search range
        if specific_year:
            # When specific year is specified: 1/1 to 12/31 of that year
            days_before = (date.today() - date(specific_year, 1, 1)).days
            days_after = (date(specific_year, 12, 31) - date.today()).days
        else:
            # Default: past 365 days (excluding today)
            days_before = 365
            days_after = 0

        # Use new API endpoint (single request for all search)
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

            # Add race_date field (for compatibility)
            for race in races:
                # Extract date from race_id (16-digit starting with YYYYMMDD)
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
    Fetch race list for a specific date from API.

    Args:
        api_base_url: API base URL
        target_date: Target date

    Returns:
        List of races
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
        logger.error(f"Error fetching race list: {e}")
        return []


def resolve_race_input(race_input: str, api_base_url: str = API_BASE_URL_DEFAULT) -> str:
    """
    Resolve race specification string to race ID (utility function).

    Supported formats:
    1. Race ID (16 digits): 2025122806050811
    2. Venue + race number: 京都2r, 中山11R
    3. Date: 2025-12-28, 12/28, 1228
    4. Race name: 有馬記念, 京都金杯

    Args:
        race_input: Race specification string
        api_base_url: API base URL

    Returns:
        Race ID (resolved, or original input if already a race ID)

    Raises:
        ValueError: If race specification is invalid
        MultipleRacesFoundException: If multiple races are found
    """
    race_input = race_input.strip()

    # 1. If already in race ID format (16-digit number), return as-is
    if re.match(r"^\d{16}$", race_input):
        logger.debug(f"Identified as race ID format: {race_input}")
        return race_input

    # 2. Check if date format
    target_date = parse_date_input(race_input)
    if target_date:
        logger.info(f"Identified as date specification: {race_input} -> {target_date}")
        races = _get_races_from_api(api_base_url, target_date)

        if not races:
            raise ValueError(f"{target_date}のレースが見つかりません")

        # If multiple races, prompt for selection
        if len(races) > 1:
            raise MultipleRacesFoundException(
                f"{target_date}に{len(races)}件のレースがあります。選択してください。", races
            )

        # Return if only one race
        return races[0]["race_id"]

    # 3. Check if venue name + race number format
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

    # 4. Race name search (with year specification support)
    specific_year, race_name = extract_year_from_input(race_input)
    logger.info(
        f"Race name search: {race_name}" + (f" (year: {specific_year})" if specific_year else "")
    )
    races = search_races_by_name(race_name, api_base_url, specific_year)

    if not races:
        year_msg = f"{specific_year}年の" if specific_year else ""
        raise ValueError(
            f"{year_msg}レース '{race_name}' が見つかりません。\n"
            f"例: 京都2r, 2025-12-28, 有馬記念, 2022 日本ダービー, または16桁のレースID"
        )

    # If multiple races, return the most recent one
    if len(races) > 1:
        # Sort by race_date (descending) and get the most recent
        sorted_races = sorted(races, key=lambda r: r.get("race_date", ""), reverse=True)
        latest_race = sorted_races[0]
        logger.info(
            f"Multiple races found ({len(races)}), selecting most recent: {latest_race.get('race_date')}"
        )
        return latest_race["race_id"]

    # Return if only one race
    return races[0]["race_id"]
