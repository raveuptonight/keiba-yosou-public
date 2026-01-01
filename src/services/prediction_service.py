"""
予想サービス

レース予想の生成、保存、取得を管理するサービスレイヤー
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncpg

import os
from src.services.rate_limiter import claude_rate_limiter

# MLモデルパス
ML_MODEL_PATH = Path("/app/models/xgboost_model_latest.pkl")
if not ML_MODEL_PATH.exists():
    # ローカル開発時のパス
    ML_MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "xgboost_model_latest.pkl"
from src.api.schemas.prediction import (
    PredictionResponse,
    PredictionResult,
    WinPrediction,
    BettingStrategy,
    HorseRanking,
    RecommendedTicket,
    PredictionHistoryItem,
    ExcludedHorse,
)
from src.exceptions import (
    PredictionError,
    DatabaseQueryError,
    LLMAPIError,
    LLMResponseError,
    LLMTimeoutError,
    MissingDataError,
)
from src.db.table_names import (
    COL_RACE_ID,
    COL_RACE_NAME,
    COL_JYOCD,
    COL_KAISAI_YEAR,
    COL_KAISAI_MONTHDAY,
)

logger = logging.getLogger(__name__)

# 競馬場コードマッピング
VENUE_CODE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉"
}


def _is_mock_mode() -> bool:
    """モックモードかどうかを判定"""
    return os.getenv("DB_MODE", "local") == "mock"


def _compute_ml_predictions(race_id: str, horses: List[Dict]) -> Dict[str, Any]:
    """
    機械学習による予測を計算

    Args:
        race_id: レースID（16桁）
        horses: 出走馬リスト

    Returns:
        Dict[馬番, {"rank_score": float, "win_probability": float}]
    """
    logger.info(f"Computing ML predictions: race_id={race_id}, horses={len(horses)}")

    try:
        from src.features.real_feature_extractor import RealFeatureExtractor
        from src.models.xgboost_model import HorseRacingXGBoost
        from src.db.connection import get_db
        import pandas as pd

        # モデル読み込み
        model = HorseRacingXGBoost()
        if ML_MODEL_PATH.exists():
            try:
                model.load(str(ML_MODEL_PATH))
                logger.info(f"ML model loaded: {ML_MODEL_PATH}")
            except Exception as e:
                logger.warning(f"Failed to load ML model, using mock: {e}")
        else:
            logger.warning(f"ML model not found: {ML_MODEL_PATH}")

        # DB接続を取得
        db = get_db()
        conn = db.get_connection()

        if not conn:
            logger.warning("DB connection failed for ML prediction")
            return {}

        try:
            # 特徴量抽出
            extractor = RealFeatureExtractor(conn)

            # data_kubun: 出馬表段階では "4" or "5"、確定後は "7"
            features_list = extractor.extract_features_for_race(race_id, data_kubun="5")
            if not features_list:
                features_list = extractor.extract_features_for_race(race_id, data_kubun="7")

            if not features_list:
                logger.warning(f"No features extracted for race: {race_id}")
                return {}

            # DataFrame に変換
            features_list.sort(key=lambda x: x.get('umaban', 0))
            df = pd.DataFrame(features_list)

            # ML予測
            rank_scores = model.predict(df)
            win_probs = model.predict_win_probability(df)

            # 結果を辞書形式に変換
            ml_scores = {}
            for i, features in enumerate(features_list):
                horse_num = features.get('umaban', i + 1)
                ml_scores[str(horse_num)] = {
                    "rank_score": float(rank_scores[i]),
                    "win_probability": float(win_probs[i])
                }

            logger.info(f"ML predictions computed: {len(ml_scores)} horses")
            return ml_scores

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"ML prediction failed: {e}")
        return {}


def _generate_mock_prediction(race_id: str, total_investment: int, is_final: bool) -> PredictionResponse:
    """モック予想を生成"""
    logger.info(f"[MOCK] Generating mock prediction for race_id={race_id}")

    # モックの予想結果
    win_prediction = WinPrediction(
        first=HorseRanking(horse_number=1, horse_name="モックホース1", expected_odds=3.5, confidence=0.8),
        second=HorseRanking(horse_number=5, horse_name="モックホース5", expected_odds=8.2, confidence=0.6),
        third=HorseRanking(horse_number=3, horse_name="モックホース3", expected_odds=12.0, confidence=0.5),
    )

    betting_strategy = BettingStrategy(
        recommended_tickets=[
            RecommendedTicket(ticket_type="3連複", numbers=[1, 3, 5], amount=1000, expected_payout=5000),
            RecommendedTicket(ticket_type="馬連", numbers=[1, 5], amount=2000, expected_payout=4000),
        ]
    )

    prediction_result = PredictionResult(
        win_prediction=win_prediction,
        betting_strategy=betting_strategy
    )

    return PredictionResponse(
        prediction_id=str(uuid.uuid4()),
        race_id=race_id,
        race_name="モックレース",
        race_date=datetime.now().strftime("%Y-%m-%d"),
        venue="東京",
        race_number="11",
        race_time="15:40",
        prediction_result=prediction_result,
        total_investment=total_investment,
        expected_return=9000,
        expected_roi=0.9,
        predicted_at=datetime.now(),
        is_final=is_final,
    )


async def generate_prediction(
    race_id: str,
    is_final: bool = False,
    total_investment: int = 10000
) -> PredictionResponse:
    """
    予想生成のメイン関数

    Args:
        race_id: レースID（16桁）
        is_final: 最終予想フラグ（馬体重後）
        total_investment: 総投資額（円）

    Returns:
        PredictionResponse: 予想結果

    Raises:
        PredictionError: 予想生成に失敗した場合
    """
    logger.info(
        f"Starting prediction generation: race_id={race_id}, "
        f"is_final={is_final}, investment={total_investment}"
    )

    # モックモードの場合
    if _is_mock_mode():
        return _generate_mock_prediction(race_id, total_investment, is_final)

    # 1. レート制限チェック
    if not claude_rate_limiter.is_allowed():
        retry_after = claude_rate_limiter.get_retry_after()
        logger.warning(f"Rate limit exceeded. Retry after {retry_after} seconds")
        raise PredictionError(
            f"レート制限に達しました。{retry_after}秒後に再試行してください。"
        )

    try:
        # 遅延インポート（モック時は不要）
        from src.db.async_connection import get_connection
        from src.db.queries import (
            get_race_prediction_data,
            check_race_exists,
        )
        from src.services.claude_client import generate_race_prediction

        # 2. データ取得
        async with get_connection() as conn:
            # レースの存在チェック
            exists = await check_race_exists(conn, race_id)
            if not exists:
                raise MissingDataError(f"レースが見つかりません: race_id={race_id}")

            # 予想データを取得
            logger.debug(f"Fetching race prediction data: race_id={race_id}")
            race_data = await get_race_prediction_data(conn, race_id)

            if not race_data or not race_data.get("horses"):
                raise MissingDataError(
                    f"レースデータが不足しています: race_id={race_id}"
                )

        # 2.5. ML予測を計算（非同期処理の外で実行）
        ml_scores = {}
        try:
            ml_scores = _compute_ml_predictions(race_id, race_data.get("horses", []))
            if ml_scores:
                logger.info(f"ML predictions available: {len(ml_scores)} horses")
            else:
                logger.warning("ML predictions not available, proceeding without")
        except Exception as e:
            logger.warning(f"ML prediction failed, proceeding without: {e}")

        # 3. LLM予想実行（Claude使用、ML予測を含む）
        logger.debug("Calling Claude API for prediction")
        try:
            llm_result = await generate_race_prediction(
                race_data=race_data,
                ml_scores=ml_scores if ml_scores else None,
            )
        except (LLMAPIError, LLMResponseError, LLMTimeoutError) as e:
            logger.error(f"LLM prediction failed: {e}")
            raise PredictionError(f"予想生成に失敗しました: {e}") from e

        # 4. 予想結果をPydanticモデルに変換
        logger.debug("Converting LLM result to PredictionResponse")
        prediction_response = _convert_to_prediction_response(
            race_data=race_data,
            llm_result=llm_result,
            total_investment=total_investment,
            is_final=is_final
        )

        # 5. DBに保存
        prediction_id = await save_prediction(prediction_response)
        prediction_response.prediction_id = prediction_id

        logger.info(
            f"Prediction generation completed: prediction_id={prediction_id}"
        )
        return prediction_response

    except MissingDataError:
        raise
    except PredictionError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during prediction generation: {e}")
        raise PredictionError(f"予想生成中にエラーが発生しました: {e}") from e


async def save_prediction(prediction_data: PredictionResponse) -> str:
    """
    予想結果をDBに保存

    Args:
        prediction_data: 予想結果

    Returns:
        str: 予想ID

    Raises:
        DatabaseQueryError: DB保存に失敗した場合
    """
    logger.debug(f"Saving prediction: race_id={prediction_data.race_id}")

    # モックモードの場合はUUIDを生成して返すだけ
    if _is_mock_mode():
        prediction_id = str(uuid.uuid4())
        logger.info(f"[MOCK] Prediction saved: prediction_id={prediction_id}")
        return prediction_id

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            # predictions テーブルに保存
            sql = """
                INSERT INTO predictions (
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    total_investment,
                    expected_return,
                    expected_roi,
                    prediction_result,
                    predicted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING prediction_id;
            """

            # prediction_id を生成（UUIDベース）
            prediction_id = str(uuid.uuid4())

            # prediction_result を辞書に変換
            prediction_result_dict = prediction_data.prediction_result.model_dump()

            result = await conn.fetchrow(
                sql,
                prediction_id,
                prediction_data.race_id,
                prediction_data.race_date,
                prediction_data.is_final,
                prediction_data.total_investment,
                prediction_data.expected_return,
                prediction_data.expected_roi,
                prediction_result_dict,  # JSONB として保存
                prediction_data.predicted_at,
            )

            if not result:
                raise DatabaseQueryError("予想結果の保存に失敗しました")

            saved_id = result["prediction_id"]
            logger.info(f"Prediction saved: prediction_id={saved_id}")
            return saved_id

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while saving prediction: {e}")
        raise DatabaseQueryError(f"予想結果の保存に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while saving prediction: {e}")
        raise DatabaseQueryError(f"予想結果の保存中にエラーが発生しました: {e}") from e


async def get_prediction_by_id(prediction_id: str) -> Optional[PredictionResponse]:
    """
    保存済み予想を取得

    Args:
        prediction_id: 予想ID

    Returns:
        PredictionResponse: 予想結果（見つからない場合はNone）

    Raises:
        DatabaseQueryError: DB取得に失敗した場合
    """
    logger.debug(f"Fetching prediction: prediction_id={prediction_id}")

    # モックモードの場合
    if _is_mock_mode():
        logger.info(f"[MOCK] Prediction not found (mock mode): prediction_id={prediction_id}")
        return None

    try:
        from src.db.async_connection import get_connection
        from src.db.queries import get_race_info

        async with get_connection() as conn:
            sql = """
                SELECT
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    total_investment,
                    expected_return,
                    expected_roi,
                    prediction_result,
                    predicted_at
                FROM predictions
                WHERE prediction_id = $1;
            """

            row = await conn.fetchrow(sql, prediction_id)

            if not row:
                logger.debug(f"Prediction not found: prediction_id={prediction_id}")
                return None

            # レース情報を取得（race_name等）
            race_info = await get_race_info(conn, row["race_id"])

            if not race_info:
                logger.warning(
                    f"Race info not found for prediction: race_id={row['race_id']}"
                )
                # デフォルト値を使用
                race_name = "不明"
                venue = "不明"
                race_number = "?"
                race_time = "00:00"
            else:
                race_name = race_info.get(COL_RACE_NAME, "不明")
                venue_code = race_info.get(COL_JYOCD, "00")
                venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
                race_number = str(race_info.get("race_num", "?"))
                race_time = race_info.get("hasso_jikoku", "00:00")

            # PredictionResponse に変換
            prediction_result = PredictionResult(**row["prediction_result"])

            prediction_response = PredictionResponse(
                prediction_id=row["prediction_id"],
                race_id=row["race_id"],
                race_name=race_name,
                race_date=row["race_date"],
                venue=venue,
                race_number=race_number,
                race_time=race_time,
                prediction_result=prediction_result,
                total_investment=row["total_investment"],
                expected_return=row["expected_return"],
                expected_roi=row["expected_roi"],
                predicted_at=row["predicted_at"],
                is_final=row["is_final"],
            )

            logger.info(f"Prediction fetched: prediction_id={prediction_id}")
            return prediction_response

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching prediction: {e}")
        raise DatabaseQueryError(f"予想結果の取得に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching prediction: {e}")
        raise DatabaseQueryError(f"予想結果の取得中にエラーが発生しました: {e}") from e


async def get_predictions_by_race(
    race_id: str,
    is_final: Optional[bool] = None
) -> List[PredictionHistoryItem]:
    """
    レースの予想履歴を取得

    Args:
        race_id: レースID
        is_final: 最終予想フラグでフィルタ（None の場合は全件）

    Returns:
        List[PredictionHistoryItem]: 予想履歴リスト

    Raises:
        DatabaseQueryError: DB取得に失敗した場合
    """
    logger.debug(f"Fetching predictions by race: race_id={race_id}, is_final={is_final}")

    # モックモードの場合
    if _is_mock_mode():
        logger.info(f"[MOCK] No predictions (mock mode): race_id={race_id}")
        return []

    try:
        from src.db.async_connection import get_connection

        async with get_connection() as conn:
            if is_final is None:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        expected_roi
                    FROM predictions
                    WHERE race_id = $1
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id)
            else:
                sql = """
                    SELECT
                        prediction_id,
                        predicted_at,
                        is_final,
                        expected_roi
                    FROM predictions
                    WHERE race_id = $1 AND is_final = $2
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id, is_final)

            predictions = [
                PredictionHistoryItem(
                    prediction_id=row["prediction_id"],
                    predicted_at=row["predicted_at"],
                    is_final=row["is_final"],
                    expected_roi=row["expected_roi"],
                )
                for row in rows
            ]

            logger.info(
                f"Predictions fetched: race_id={race_id}, count={len(predictions)}"
            )
            return predictions

    except asyncpg.PostgresError as e:
        logger.error(f"Database error while fetching predictions: {e}")
        raise DatabaseQueryError(f"予想履歴の取得に失敗しました: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while fetching predictions: {e}")
        raise DatabaseQueryError(f"予想履歴の取得中にエラーが発生しました: {e}") from e


def _convert_to_prediction_response(
    race_data: Dict[str, Any],
    llm_result: Dict[str, Any],
    total_investment: int,
    is_final: bool
) -> PredictionResponse:
    """
    LLM結果をPredictionResponseに変換

    Args:
        race_data: レースデータ
        llm_result: LLM予想結果
        total_investment: 総投資額
        is_final: 最終予想フラグ

    Returns:
        PredictionResponse: 変換後の予想結果
    """
    race_info = race_data.get("race", {})

    # レース情報を抽出
    race_id = race_info.get(COL_RACE_ID, "")
    race_name = race_info.get(COL_RACE_NAME, "不明")
    venue_code = race_info.get(COL_JYOCD, "00")
    venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
    race_number = str(race_info.get("race_num", "?"))
    race_time = race_info.get("hasso_jikoku", "00:00")

    # 開催日を計算
    kaisai_year = race_info.get(COL_KAISAI_YEAR, "")
    kaisai_monthday = race_info.get(COL_KAISAI_MONTHDAY, "")
    if kaisai_year and kaisai_monthday:
        race_date = f"{kaisai_year}-{kaisai_monthday[:2]}-{kaisai_monthday[2:]}"
    else:
        race_date = datetime.now().strftime("%Y-%m-%d")

    # WinPrediction を構築
    win_pred_data = llm_result.get("win_prediction", {})

    def _build_horse_ranking(data: Dict[str, Any]) -> HorseRanking:
        return HorseRanking(
            horse_number=data.get("horse_number", 0),
            horse_name=data.get("horse_name", "不明"),
            expected_odds=data.get("expected_odds"),
            confidence=data.get("confidence")
        )

    win_prediction = WinPrediction(
        first=_build_horse_ranking(win_pred_data.get("first", {})),
        second=_build_horse_ranking(win_pred_data.get("second", {})),
        third=_build_horse_ranking(win_pred_data.get("third", {})),
        fourth=_build_horse_ranking(win_pred_data.get("fourth", {})) if "fourth" in win_pred_data else None,
        fifth=_build_horse_ranking(win_pred_data.get("fifth", {})) if "fifth" in win_pred_data else None,
        excluded=[
            ExcludedHorse(**exc)
            for exc in win_pred_data.get("excluded", [])
        ] if "excluded" in win_pred_data else None
    )

    # BettingStrategy を構築
    betting_data = llm_result.get("betting_strategy", {})
    recommended_tickets = [
        RecommendedTicket(**ticket)
        for ticket in betting_data.get("recommended_tickets", [])
    ]

    betting_strategy = BettingStrategy(
        recommended_tickets=recommended_tickets
    )

    # PredictionResult を構築
    prediction_result = PredictionResult(
        win_prediction=win_prediction,
        betting_strategy=betting_strategy
    )

    # 期待回収額・ROIを計算
    expected_return = sum(
        ticket.expected_payout or 0
        for ticket in recommended_tickets
    )
    expected_roi = expected_return / total_investment if total_investment > 0 else 0.0

    # PredictionResponse を構築
    prediction_response = PredictionResponse(
        prediction_id="",  # save_prediction で設定される
        race_id=race_id,
        race_name=race_name,
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        race_time=race_time,
        prediction_result=prediction_result,
        total_investment=total_investment,
        expected_return=expected_return,
        expected_roi=expected_roi,
        predicted_at=datetime.now(),
        is_final=is_final,
    )

    return prediction_response


if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    import asyncio

    async def test_prediction():
        """予想生成のテスト"""
        # テスト用レースID（存在するレースIDに置き換える）
        test_race_id = "2024031005011112"

        try:
            prediction = await generate_prediction(
                race_id=test_race_id,
                is_final=False,
                total_investment=10000
            )

            print("\n予想結果:")
            print(f"予想ID: {prediction.prediction_id}")
            print(f"レース: {prediction.race_name}")
            print(f"本命: {prediction.prediction_result.win_prediction.first.horse_name}")
            print(f"期待ROI: {prediction.expected_roi:.2f}")

        except Exception as e:
            print(f"エラー: {e}")

    asyncio.run(test_prediction())
