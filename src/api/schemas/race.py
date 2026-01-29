"""
レース関連のPydanticスキーマ
"""

from pydantic import BaseModel, Field

from src.api.schemas.common import PrizeMoneyResponse


class RaceBase(BaseModel):
    """レース基本情報"""

    race_id: str = Field(..., min_length=16, max_length=16, description="レースID（16桁）")
    race_name: str = Field(..., description="レース名")
    race_number: str = Field(..., description="レース番号（例: '11R'）")
    race_time: str | None = Field(None, description="発走時刻（例: '15:25'）")
    venue: str = Field(..., description="競馬場名（例: '中山'）")
    venue_code: str = Field(..., description="競馬場コード（例: '05'）")
    grade: str | None = Field(None, description="グレード（例: 'G1', 'G2', 'G3', '○'）")
    distance: int = Field(..., gt=0, description="距離（メートル）")
    track_code: str = Field(..., description="馬場種別コード（10=芝, 20=ダート）")
    race_date: str | None = Field(None, description="開催日（YYYY-MM-DD）")


class RaceEntry(BaseModel):
    """レース出走馬情報"""

    horse_number: int = Field(..., ge=1, le=18, description="馬番（1-18）")
    kettonum: str = Field(..., min_length=10, max_length=10, description="血統登録番号（10桁）")
    horse_name: str = Field(..., description="馬名")
    sex: str | None = Field(None, description="性別（牡/牝/騙）")
    age: int | None = Field(None, description="馬齢")
    sire: str | None = Field(None, description="父馬名")
    jockey_code: str = Field(..., description="騎手コード")
    jockey_name: str = Field(..., description="騎手名")
    trainer_code: str = Field(..., description="調教師コード")
    trainer_name: str = Field(..., description="調教師名")
    weight: float = Field(..., description="装着重量（kg）")
    horse_weight: int | None = Field(None, description="馬体重（kg）")
    odds: float | None = Field(None, ge=0.1, description="単勝オッズ")
    last_race: str | None = Field(None, description="前走情報（例: '中山2着'）")
    finish_position: int | None = Field(None, description="着順（レース終了後のみ）")
    finish_time: str | None = Field(None, description="走破タイム（レース終了後のみ）")


class RaceResult(BaseModel):
    """レース結果情報"""

    horse_number: int = Field(..., description="馬番")
    horse_name: str = Field(..., description="馬名")
    jockey_name: str = Field(..., description="騎手名")
    finish_position: int = Field(..., description="着順")
    finish_time: str = Field(..., description="走破タイム")
    odds: float | None = Field(None, description="単勝オッズ")
    kohan_3f: str | None = Field(None, description="上がり3F")


class PayoffInfo(BaseModel):
    """払戻金情報"""

    kumi: str = Field(..., description="組番（例: '5', '5-9', '5→9→4'）")
    payoff: int = Field(..., description="払戻金（円）")
    ninki: int | None = Field(None, description="人気順")


class RacePayoffs(BaseModel):
    """レース払戻金"""

    win: PayoffInfo | None = Field(None, description="単勝")
    place: list[PayoffInfo] | None = Field(None, description="複勝")
    bracket_quinella: PayoffInfo | None = Field(None, description="枠連")
    quinella: PayoffInfo | None = Field(None, description="馬連")
    exacta: PayoffInfo | None = Field(None, description="馬単")
    wide: list[PayoffInfo] | None = Field(None, description="ワイド")
    trio: PayoffInfo | None = Field(None, description="3連複")
    trifecta: PayoffInfo | None = Field(None, description="3連単")


class RaceDetail(RaceBase):
    """レース詳細情報"""

    track_condition: str | None = Field(None, description="馬場状態（良/稍/重/不）")
    weather: str | None = Field(None, description="天気（晴/曇/小雨/雨）")
    prize_money: PrizeMoneyResponse = Field(..., description="賞金情報")
    entries: list[RaceEntry] = Field(..., description="出走馬一覧")
    results: list[RaceResult] | None = Field(None, description="レース結果（レース終了後のみ）")
    payoffs: RacePayoffs | None = Field(None, description="払戻金（レース終了後のみ）")
    lap_times: list[str] | None = Field(
        None, description="ラップタイム（200m毎、レース終了後のみ）"
    )
    head_to_head: list["HeadToHeadRace"] | None = Field(None, description="出走馬の過去対戦成績")


class HorseInMatchup(BaseModel):
    """対戦表内の馬情報"""

    kettonum: str = Field(..., description="血統登録番号")
    name: str = Field(..., description="馬名")
    horse_number: int = Field(..., description="馬番")
    finish_position: int = Field(..., description="着順")


class HeadToHeadRace(BaseModel):
    """馬同士の過去対戦レース"""

    race_id: str = Field(..., description="レースID")
    race_name: str = Field(..., description="レース名")
    race_date: str = Field(..., description="レース日（YYYY-MM-DD）")
    venue_code: str = Field(..., description="競馬場コード")
    distance: int = Field(..., description="距離（メートル）")
    horses: list[HorseInMatchup] = Field(..., description="対戦した馬のリスト")


class RaceListResponse(BaseModel):
    """レース一覧レスポンス"""

    date: str | None = Field(None, description="レース日（YYYY-MM-DD）、複数日にまたがる場合はNone")
    races: list[RaceBase] = Field(..., description="レース一覧")
    count: int = Field(..., ge=0, description="レース総数")
