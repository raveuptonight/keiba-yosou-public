"""
レース指定文字列をレースIDに解決するモジュール

「京都2r」のような指定を実際のレースIDに変換
"""

import re
import logging
from datetime import date, timedelta
from typing import Optional, Tuple
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

    def parse_race_spec(self, race_spec: str) -> Optional[Tuple[str, int]]:
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

    def resolve_to_race_id(
        self,
        race_spec: str,
        target_date: Optional[date] = None
    ) -> Optional[str]:
        """
        レース指定文字列をレースIDに解決

        Args:
            race_spec: レース指定文字列（例: 京都2r）
            target_date: 対象日（省略時は本日）

        Returns:
            レースID。解決失敗時はNone
        """
        # レース指定文字列をパース
        parsed = self.parse_race_spec(race_spec)
        if not parsed:
            return None

        venue, race_number = parsed

        # 対象日が指定されていなければ本日
        if target_date is None:
            target_date = date.today()

        logger.info(f"レース解決開始: venue={venue}, race_number={race_number}, date={target_date}")

        # APIからレース一覧を取得（本日〜翌日）
        race_id = self._find_race_from_api(venue, race_number, target_date)

        if race_id:
            logger.info(f"レース解決成功: race_spec={race_spec} -> race_id={race_id}")
            return race_id

        # 本日見つからなければ翌日を検索
        next_date = target_date + timedelta(days=1)
        logger.debug(f"本日見つからず、翌日を検索: {next_date}")
        race_id = self._find_race_from_api(venue, race_number, next_date)

        if race_id:
            logger.info(f"レース解決成功（翌日）: race_spec={race_spec} -> race_id={race_id}")
            return race_id

        logger.warning(f"レース解決失敗: race_spec={race_spec}")
        return None

    def _find_race_from_api(
        self,
        venue: str,
        race_number: int,
        target_date: date
    ) -> Optional[str]:
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
            # TODO: APIエンドポイントが実装されたら修正
            # response = requests.get(
            #     f"{self.api_base_url}/api/races",
            #     params={"date": target_date.isoformat()},
            #     timeout=10
            # )
            #
            # if response.status_code != 200:
            #     logger.error(f"レース一覧取得失敗: status={response.status_code}")
            #     return None
            #
            # races = response.json().get("races", [])
            #
            # for race in races:
            #     if (race.get("venue") == venue and
            #         race.get("race_number") == race_number):
            #         return race.get("race_id")

            # 暫定: モックレスポンス
            logger.warning("APIエンドポイント未実装のため、レース解決をスキップ")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"レース一覧取得エラー: {e}")
            return None


def resolve_race_input(
    race_input: str,
    api_base_url: str = API_BASE_URL_DEFAULT
) -> str:
    """
    レース指定文字列をレースIDに解決（ユーティリティ関数）

    Args:
        race_input: レース指定文字列（レースID or 京都2r形式）
        api_base_url: API base URL

    Returns:
        レースID（解決済み、または元の入力がすでにレースID）

    Raises:
        ValueError: レース指定が無効な場合
    """
    # すでにレースID形式（12桁の数字）の場合はそのまま返す
    if re.match(r"^\d{12}$", race_input):
        logger.debug(f"レースID形式と判定: {race_input}")
        return race_input

    # 競馬場名+レース番号形式の場合は解決
    resolver = RaceResolver(api_base_url)
    race_id = resolver.resolve_to_race_id(race_input)

    if race_id is None:
        raise ValueError(
            f"レース '{race_input}' が見つかりません。\n"
            f"例: 京都2r, 中山11R, または12桁のレースID"
        )

    return race_id
