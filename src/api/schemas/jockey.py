"""
騎手・調教師関連のPydanticスキーマ
"""


from pydantic import BaseModel, Field


class JockeyBasicInfo(BaseModel):
    """騎手基本情報"""

    kishu_code: str = Field(..., description="騎手コード")
    name: str = Field(..., description="騎手名")
    name_short: str = Field(..., description="騎手名（略称）")
    affiliation: str = Field(..., description="所属（美浦/栗東）")
    birth_date: str | None = Field(None, description="生年月日")
    license_date: str | None = Field(None, description="免許交付日")


class OverallStats(BaseModel):
    """通算成績"""

    total_races: int = Field(..., ge=0, description="総騎乗数/出走数")
    wins: int = Field(..., ge=0, description="1着数")
    top2: int = Field(..., ge=0, description="2着以内")
    top3: int = Field(..., ge=0, description="3着以内")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")
    top2_rate: float = Field(..., ge=0.0, le=1.0, description="連対率")
    top3_rate: float = Field(..., ge=0.0, le=1.0, description="複勝率")


class SurfaceStats(BaseModel):
    """馬場別成績"""

    turf_races: int = Field(..., ge=0, description="芝出走数")
    turf_wins: int = Field(..., ge=0, description="芝勝利数")
    turf_win_rate: float = Field(..., ge=0.0, le=1.0, description="芝勝率")
    dirt_races: int = Field(..., ge=0, description="ダート出走数")
    dirt_wins: int = Field(..., ge=0, description="ダート勝利数")
    dirt_win_rate: float = Field(..., ge=0.0, le=1.0, description="ダート勝率")


class DistanceCategoryStats(BaseModel):
    """距離別成績"""

    category: str = Field(..., description="距離カテゴリ")
    races: int = Field(..., ge=0, description="出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")


class VenueStats(BaseModel):
    """競馬場別成績"""

    venue: str = Field(..., description="競馬場名")
    venue_code: str = Field(..., description="競馬場コード")
    races: int = Field(..., ge=0, description="出走数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")


class TopJockey(BaseModel):
    """主戦騎手情報"""

    kishu_code: str = Field(..., description="騎手コード")
    jockey_name: str = Field(..., description="騎手名")
    rides: int = Field(..., ge=0, description="騎乗回数")
    wins: int = Field(..., ge=0, description="勝利数")
    win_rate: float = Field(..., ge=0.0, le=1.0, description="勝率")


class JockeyStats(BaseModel):
    """騎手詳細統計"""

    basic_info: JockeyBasicInfo = Field(..., description="基本情報")
    overall_stats: OverallStats = Field(..., description="通算成績")
    surface_stats: SurfaceStats = Field(..., description="馬場別成績")
    distance_stats: list[DistanceCategoryStats] = Field(
        ..., description="距離別成績"
    )
    venue_stats: list[VenueStats] = Field(
        ..., description="競馬場別成績（上位5件）"
    )


class TrainerBasicInfo(BaseModel):
    """調教師基本情報"""

    chokyoshi_code: str = Field(..., description="調教師コード")
    name: str = Field(..., description="調教師名")
    name_short: str = Field(..., description="調教師名（略称）")
    affiliation: str = Field(..., description="所属（美浦/栗東）")
    birth_date: str | None = Field(None, description="生年月日")
    license_date: str | None = Field(None, description="免許交付日")


class TrainerStats(BaseModel):
    """調教師詳細統計"""

    basic_info: TrainerBasicInfo = Field(..., description="基本情報")
    overall_stats: OverallStats = Field(..., description="通算成績")
    surface_stats: SurfaceStats = Field(..., description="馬場別成績")
    distance_stats: list[DistanceCategoryStats] = Field(
        ..., description="距離別成績"
    )
    venue_stats: list[VenueStats] = Field(
        ..., description="競馬場別成績（上位5件）"
    )
    top_jockeys: list[TopJockey] = Field(
        ..., description="主戦騎手（上位5名）"
    )


class JockeySearchResult(BaseModel):
    """騎手検索結果"""

    kishu_code: str = Field(..., description="騎手コード")
    name: str = Field(..., description="騎手名")
    name_short: str = Field(..., description="騎手名（略称）")
    affiliation: str = Field(..., description="所属（美浦/栗東）")


class TrainerSearchResult(BaseModel):
    """調教師検索結果"""

    chokyoshi_code: str = Field(..., description="調教師コード")
    name: str = Field(..., description="調教師名")
    name_short: str = Field(..., description="調教師名（略称）")
    affiliation: str = Field(..., description="所属（美浦/栗東）")
