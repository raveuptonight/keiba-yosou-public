"""
予想関連のPydanticスキーマ

確率ベース・ランキング形式・順位分布・信頼度スコアを出力
"""

from datetime import datetime

from pydantic import BaseModel, Field


class PositionDistribution(BaseModel):
    """順位分布予測"""

    first: float = Field(
        ..., ge=0.0, le=1.0, description="1着確率"
    )
    second: float = Field(
        ..., ge=0.0, le=1.0, description="2着確率"
    )
    third: float = Field(
        ..., ge=0.0, le=1.0, description="3着確率"
    )
    out_of_place: float = Field(
        ..., ge=0.0, le=1.0, description="4着以下確率"
    )


class HorseRankingEntry(BaseModel):
    """全馬ランキングエントリ（確率ベース）"""

    rank: int = Field(
        ..., ge=1, description="予測順位（1が最上位）"
    )
    horse_number: int = Field(
        ..., ge=1, le=18, description="馬番（1-18）"
    )
    horse_name: str = Field(..., description="馬名")
    horse_sex: str | None = Field(None, description="性別（牡/牝/セ）")
    horse_age: int | None = Field(None, description="馬齢")
    jockey_name: str | None = Field(None, description="騎手名")
    win_probability: float = Field(
        ..., ge=0.0, le=1.0, description="単勝率（1着確率）"
    )
    quinella_probability: float = Field(
        ..., ge=0.0, le=1.0, description="連対率（2着以内確率）"
    )
    place_probability: float = Field(
        ..., ge=0.0, le=1.0, description="複勝率（3着以内確率）"
    )
    position_distribution: PositionDistribution = Field(
        ..., description="順位分布予測"
    )
    rank_score: float = Field(
        ..., description="MLモデル予測スコア（小さいほど上位）"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="この馬の予測信頼度"
    )


class QuinellaRankingEntry(BaseModel):
    """連対率順ランキングエントリ"""
    rank: int
    horse_number: int
    quinella_prob: float


class PlaceRankingEntry(BaseModel):
    """複勝率順ランキングエントリ"""
    rank: int
    horse_number: int
    place_prob: float


class DarkHorseEntry(BaseModel):
    """穴馬候補エントリ"""
    horse_number: int
    win_prob: float
    place_prob: float


class PredictionResult(BaseModel):
    """予想結果本体（確率ベース・ランキング形式）"""

    ranked_horses: list[HorseRankingEntry] = Field(
        ..., description="全馬ランキング（勝率順・単勝向け）"
    )
    quinella_ranking: list[QuinellaRankingEntry] | None = Field(
        None, description="連対率順Top5（馬連・ワイド向け）"
    )
    place_ranking: list[PlaceRankingEntry] | None = Field(
        None, description="複勝率順Top5（複勝向け）"
    )
    dark_horses: list[DarkHorseEntry] | None = Field(
        None, description="穴馬候補（複勝率高い＆勝率低い）"
    )
    prediction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="予測全体の信頼度スコア"
    )
    model_info: str = Field(
        ..., description="使用モデル情報"
    )


class PredictionRequest(BaseModel):
    """予想生成リクエスト"""

    race_id: str = Field(
        ..., min_length=16, max_length=16, description="レースID（16桁）"
    )
    is_final: bool = Field(
        False, description="最終予想フラグ（馬体重後）"
    )
    bias_date: str | None = Field(
        None, description="バイアス適用日（YYYY-MM-DD形式）"
    )


class PredictionResponse(BaseModel):
    """予想生成レスポンス"""

    prediction_id: str = Field(
        ..., description="予想ID"
    )
    race_id: str = Field(
        ..., description="レースID"
    )
    race_name: str = Field(
        ..., description="レース名"
    )
    race_date: str = Field(
        ..., description="レース日（YYYY-MM-DD）"
    )
    venue: str = Field(
        ..., description="競馬場名"
    )
    race_number: str = Field(
        ..., description="レース番号"
    )
    race_time: str = Field(
        ..., description="発走時刻"
    )
    prediction_result: PredictionResult = Field(
        ..., description="予想結果本体（確率ベース・ランキング形式）"
    )
    predicted_at: datetime = Field(
        ..., description="予想実行日時"
    )
    is_final: bool = Field(
        ..., description="最終予想フラグ"
    )


class PredictionHistoryItem(BaseModel):
    """予想履歴アイテム"""

    prediction_id: str = Field(
        ..., description="予想ID"
    )
    predicted_at: datetime = Field(
        ..., description="予想実行日時"
    )
    is_final: bool = Field(
        ..., description="最終予想フラグ"
    )
    prediction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="予測信頼度"
    )


class PredictionHistoryResponse(BaseModel):
    """予想履歴レスポンス"""

    race_id: str = Field(
        ..., description="レースID"
    )
    predictions: list[PredictionHistoryItem] = Field(
        ..., description="予想履歴一覧"
    )
