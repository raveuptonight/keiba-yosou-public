"""
Horse information Pydantic schemas.
"""

from datetime import date

from pydantic import BaseModel, Field


class Trainer(BaseModel):
    """Trainer information."""

    code: str = Field(..., description="調教師コード")
    name: str = Field(..., description="調教師名")
    affiliation: str = Field(..., description="厩舎所属（美浦/栗東）")


class Pedigree(BaseModel):
    """Pedigree information."""

    sire: str = Field(..., description="父馬")
    dam: str = Field(..., description="母馬")
    sire_sire: str = Field(..., description="父父馬")
    sire_dam: str = Field(..., description="父母馬")
    dam_sire: str = Field(..., description="母父馬（重要）")
    dam_dam: str = Field(..., description="母母馬")


class TrainingData(BaseModel):
    """Training data."""

    training_type: str = Field(..., description="調教種別（坂路/ウッド）")
    training_date: str = Field(..., description="調教日（YYYYMMDD）")
    time_4f: str | None = Field(None, description="4ハロンタイム")
    time_3f: str | None = Field(None, description="3ハロンタイム")


class RecentRace(BaseModel):
    """Recent race results."""

    race_id: str = Field(..., min_length=16, max_length=16, description="レースID")
    race_name: str = Field(..., description="レース名")
    race_date: date = Field(..., description="レース日")
    venue: str = Field(..., description="競馬場名")
    distance: int = Field(..., gt=0, description="距離（メートル）")
    track_condition: str = Field(..., description="馬場状態（良/稍/重/不）")
    finish_position: int = Field(..., ge=1, description="着順")
    time: str = Field(..., description="タイム（MM:SS.S形式）")
    time_diff: str | None = Field(None, description="勝ち馬とのタイム差（秒）")
    winner_name: str | None = Field(None, description="勝ち馬名（1着馬）")
    jockey: str = Field(..., description="騎手名")
    weight: float = Field(..., description="装着重量（kg）")
    horse_weight: int | None = Field(None, description="馬体重（kg）")
    odds: float | None = Field(None, ge=0.1, description="単勝オッズ")
    prize_money: int = Field(..., ge=0, description="獲得賞金（円）")
    training: TrainingData | None = Field(None, description="レース前直近調教データ")


class HorseSearchResult(BaseModel):
    """Horse search result."""

    kettonum: str = Field(..., min_length=10, max_length=10, description="血統登録番号")
    name: str = Field(..., description="馬名")
    sex: str | None = Field(None, description="性別コード")
    birth_date: date | None = Field(None, description="生年月日")
    runs: int = Field(0, ge=0, description="出走数")
    wins: int = Field(0, ge=0, description="勝利数")
    prize: int = Field(0, ge=0, description="獲得賞金（円）")


class TrainingRecord(BaseModel):
    """Training record (raw DB data format)."""

    training_type: str = Field(..., description="調教種別（hanro/wood）")
    chokyo_nengappi: str = Field(..., description="調教日（YYYYMMDD）")
    time_gokei_4furlong: str | None = Field(None, description="4ハロンタイム")
    time_gokei_3furlong: str | None = Field(None, description="3ハロンタイム")


class HorseDetail(BaseModel):
    """Detailed horse information."""

    kettonum: str = Field(..., min_length=10, max_length=10, description="血統登録番号")
    horse_name: str = Field(..., description="馬名")
    birth_date: date = Field(..., description="生年月日")
    sex: str = Field(..., description="性別（牡/牝/騙）")
    coat_color: str = Field(..., description="毛色（鹿毛/栗毛等）")
    sire: str = Field(..., description="父馬名")
    dam: str = Field(..., description="母馬名")
    breeder: str = Field(..., description="生産者名")
    owner: str = Field(..., description="馬主名")
    trainer: Trainer = Field(..., description="調教師情報")
    total_races: int = Field(..., ge=0, description="総出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")
    prize_money: int = Field(..., ge=0, description="通算獲得賞金（円）")
    running_style: str | None = Field(None, description="脚質（先行/差し/追い込み）")
    pedigree: Pedigree = Field(..., description="血統情報")
    recent_races: list[RecentRace] = Field(..., description="最近のレース成績")
    training: list[TrainingRecord] = Field(default_factory=list, description="直近の調教データ")
