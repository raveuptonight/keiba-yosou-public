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
import numpy as np

import os

# MLモデルパス（ensemble_modelのみ使用）
ML_MODEL_PATH = Path("/app/models/ensemble_model_latest.pkl")
if not ML_MODEL_PATH.exists():
    # ローカル開発時のパス
    ML_MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "ensemble_model_latest.pkl"

# キャリブレーションファイルパス
CALIBRATION_PATH = Path("/app/models/calibration.pkl")
if not CALIBRATION_PATH.exists():
    CALIBRATION_PATH = Path(__file__).parent.parent.parent / "models" / "calibration.pkl"

# キャリブレーターをグローバルにキャッシュ
_calibrators = None


def _load_calibrators():
    """キャリブレーターを読み込み（遅延読み込み）"""
    global _calibrators
    if _calibrators is not None:
        return _calibrators

    if not CALIBRATION_PATH.exists():
        logger.warning(f"キャリブレーションファイルが見つかりません: {CALIBRATION_PATH}")
        return None

    try:
        import joblib
        calibration_data = joblib.load(CALIBRATION_PATH)
        _calibrators = calibration_data.get('calibrators', {})
        logger.info(f"キャリブレーター読み込み完了: {list(_calibrators.keys())}")
        return _calibrators
    except Exception as e:
        logger.error(f"キャリブレーター読み込み失敗: {e}")
        return None
from src.api.schemas.prediction import (
    PredictionResponse,
    PredictionResult,
    HorseRankingEntry,
    PositionDistribution,
    PredictionHistoryItem,
)
from src.exceptions import (
    PredictionError,
    DatabaseQueryError,
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


def _extract_future_race_features(conn, race_id: str, extractor, year: int):
    """
    未来レースの特徴量を抽出

    確定データがない未来のレースに対して、登録済みの出走馬情報から特徴量を抽出する

    Args:
        conn: DB接続
        race_id: レースID
        extractor: FastFeatureExtractor
        year: 対象年

    Returns:
        pd.DataFrame: 特徴量DataFrame
    """
    import pandas as pd

    cur = conn.cursor()

    # 1. レース情報を取得（登録済みデータ）
    cur.execute('''
        SELECT race_code, kaisai_nen, kaisai_gappi, keibajo_code,
               kyori, track_code, grade_code,
               shiba_babajotai_code, dirt_babajotai_code
        FROM race_shosai
        WHERE race_code = %s
          AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        LIMIT 1
    ''', (race_id,))

    race_row = cur.fetchone()
    if not race_row:
        cur.close()
        return pd.DataFrame()

    race_cols = [d[0] for d in cur.description]
    races = [dict(zip(race_cols, race_row))]

    # 2. 出走馬データを取得
    cur.execute('''
        SELECT
            race_code, umaban, wakuban, ketto_toroku_bango,
            seibetsu_code, barei, futan_juryo,
            blinker_shiyo_kubun, kishu_code, chokyoshi_code,
            bataiju, zogen_sa, bamei
        FROM umagoto_race_joho
        WHERE race_code = %s
          AND data_kubun IN ('1', '2', '3', '4', '5', '6')
        ORDER BY umaban::int
    ''', (race_id,))

    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    entries = [dict(zip(cols, row)) for row in rows]

    if not entries:
        cur.close()
        return pd.DataFrame()

    logger.info(f"Future race entries: {len(entries)} horses")

    # 3. 過去成績を取得
    kettonums = [e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')]
    past_stats = extractor._get_past_stats_batch(kettonums)

    # 4. 騎手・調教師キャッシュ
    extractor._cache_jockey_trainer_stats(year)

    # 5. 追加データ
    jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
    jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
    surface_stats = extractor._get_surface_stats_batch(kettonums)
    turn_stats = extractor._get_turn_rates_batch(kettonums)
    for kettonum, stats in turn_stats.items():
        if kettonum in past_stats:
            past_stats[kettonum]['right_turn_rate'] = stats['right_turn_rate']
            past_stats[kettonum]['left_turn_rate'] = stats['left_turn_rate']
    training_stats = extractor._get_training_stats_batch(kettonums)

    # 6. 特徴量生成（ダミーの着順を設定）
    features_list = []
    for entry in entries:
        entry['kakutei_chakujun'] = '01'  # 予測用ダミー

        features = extractor._build_features(
            entry, races, past_stats,
            jockey_horse_stats=jockey_horse_stats,
            distance_stats=surface_stats,
            training_stats=training_stats
        )
        if features:
            features['bamei'] = entry.get('bamei', '')
            features_list.append(features)

    cur.close()

    if not features_list:
        return pd.DataFrame()

    return pd.DataFrame(features_list)


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
        from src.models.fast_train import FastFeatureExtractor
        from src.db.connection import get_db
        import pandas as pd
        import numpy as np
        import joblib

        # モデル読み込み
        if not ML_MODEL_PATH.exists():
            logger.warning(f"ML model not found: {ML_MODEL_PATH}")
            return {}

        model_data = joblib.load(ML_MODEL_PATH)

        # ensemble_modelのキーを取得（2つの形式に対応）
        # 形式1: xgb_model, lgb_model（weekly_retrain_model.py形式）
        # 形式2: models.xgboost, models.lightgbm（旧形式）
        if 'xgb_model' in model_data:
            xgb_model = model_data['xgb_model']
            lgb_model = model_data['lgb_model']
        elif 'models' in model_data:
            xgb_model = model_data['models'].get('xgboost')
            lgb_model = model_data['models'].get('lightgbm')
        else:
            logger.error(f"Invalid model format: ensemble_model required")
            return {}

        feature_names = model_data.get('feature_names', [])
        logger.info(f"Ensemble model loaded: {ML_MODEL_PATH}, features={len(feature_names)}")

        # DB接続を取得
        db = get_db()
        conn = db.get_connection()

        if not conn:
            logger.warning("DB connection failed for ML prediction")
            return {}

        try:
            # 特徴量抽出（ML学習時と同じFastFeatureExtractorを使用）
            extractor = FastFeatureExtractor(conn)
            year = int(race_id[:4])
            logger.info(f"Extracting features for race {race_id}...")

            # まず確定済みデータから試行（過去レース）
            df = extractor.extract_year_data(year, max_races=10000)
            race_df = df[df['race_code'] == race_id].copy() if len(df) > 0 else pd.DataFrame()

            # 確定データがない場合、未来レースとして直接特徴量抽出
            if len(race_df) == 0:
                logger.info(f"No confirmed data, extracting features for future race: {race_id}")
                race_df = _extract_future_race_features(conn, race_id, extractor, year)

            if len(race_df) == 0:
                logger.warning(f"No data for race: {race_id}")
                return {}

            logger.info(f"Found {len(race_df)} horses for race {race_id}")

            # モデルが期待する特徴量のみを抽出
            available_features = [f for f in feature_names if f in race_df.columns]
            missing_features = [f for f in feature_names if f not in race_df.columns]
            if missing_features:
                logger.warning(f"Missing features: {missing_features[:5]}...")
                for f in missing_features:
                    race_df[f] = 0

            X = race_df[feature_names].fillna(0)
            features_list = race_df.to_dict('records')

            # ML予測（ensemble_model: XGBoost + LightGBM）
            if not xgb_model or not lgb_model:
                logger.error("Ensemble model requires both XGBoost and LightGBM")
                return {}

            xgb_pred = xgb_model.predict(X)
            lgb_pred = lgb_model.predict(X)
            rank_scores = (xgb_pred + lgb_pred) / 2

            # スコアを確率に変換（softmax風）
            scores_exp = np.exp(-rank_scores)
            win_probs = scores_exp / scores_exp.sum()

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


def _generate_mock_prediction(race_id: str, is_final: bool) -> PredictionResponse:
    """モック予想を生成（確率ベース・ランキング形式）"""
    logger.info(f"[MOCK] Generating mock prediction for race_id={race_id}")

    # モックのランキングデータ
    mock_horses = [
        {"rank": 1, "horse_number": 1, "horse_name": "モックホース1", "win_prob": 0.25},
        {"rank": 2, "horse_number": 5, "horse_name": "モックホース5", "win_prob": 0.18},
        {"rank": 3, "horse_number": 3, "horse_name": "モックホース3", "win_prob": 0.12},
        {"rank": 4, "horse_number": 7, "horse_name": "モックホース7", "win_prob": 0.10},
        {"rank": 5, "horse_number": 2, "horse_name": "モックホース2", "win_prob": 0.08},
    ]

    ranked_horses = [
        HorseRankingEntry(
            rank=h["rank"],
            horse_number=h["horse_number"],
            horse_name=h["horse_name"],
            win_probability=h["win_prob"],
            quinella_probability=min(h["win_prob"] * 1.8, 0.5),
            place_probability=min(h["win_prob"] * 2.5, 0.6),
            position_distribution=PositionDistribution(
                first=h["win_prob"],
                second=h["win_prob"] * 0.8,
                third=h["win_prob"] * 0.6,
                out_of_place=max(0, 1.0 - h["win_prob"] * 2.4),
            ),
            rank_score=float(h["rank"]),
            confidence=0.7 - h["rank"] * 0.05,
        )
        for h in mock_horses
    ]

    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        prediction_confidence=0.72,
        model_info="mock_model",
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
        predicted_at=datetime.now(),
        is_final=is_final,
    )


def _generate_ml_only_prediction(
    race_data: Dict[str, Any],
    ml_scores: Dict[str, Any]
) -> Dict[str, Any]:
    """
    MLスコアから確率ベース・ランキング形式の予想結果を生成

    Args:
        race_data: レースデータ
        ml_scores: ML予測スコア

    Returns:
        Dict: 確率ベース・ランキング形式の予想データ
    """
    horses = race_data.get("horses", [])
    n_horses = len(horses)

    # MLスコアでソート（スコアが低いほど上位）
    scored_horses = []
    for horse in horses:
        umaban_raw = horse.get("umaban", "")
        # 馬番を正規化（'01' -> '1'、1 -> '1' 等）
        try:
            umaban = str(int(umaban_raw))
        except (ValueError, TypeError):
            umaban = str(umaban_raw)
        score_data = ml_scores.get(umaban, {})
        scored_horses.append({
            "horse_number": int(umaban) if umaban.isdigit() else 0,
            "horse_name": horse.get("bamei", "不明"),
            "rank_score": score_data.get("rank_score", 999),
            "win_probability": score_data.get("win_probability", 0.0),
        })

    # スコア順にソート
    scored_horses.sort(key=lambda x: x["rank_score"])

    # 順位分布を計算（簡易モデル: 勝率ベースで推定）
    def calc_position_distribution(win_prob: float, rank: int, n: int) -> Dict[str, float]:
        """順位分布を推定（勝率と予測順位から算出）"""
        # 1着確率 = 勝率
        first = win_prob
        # 2着確率 = 予測順位に応じて減衰
        second = min(win_prob * 1.5, 0.3) if rank <= 5 else win_prob * 0.5
        # 3着確率
        third = min(win_prob * 1.8, 0.35) if rank <= 7 else win_prob * 0.3
        # 4着以下
        out = max(0.0, 1.0 - first - second - third)
        return {
            "first": round(first, 4),
            "second": round(second, 4),
            "third": round(third, 4),
            "out_of_place": round(out, 4),
        }

    # キャリブレーターを読み込み
    calibrators = _load_calibrators()

    # ランキングエントリを生成
    ranked_horses = []
    for i, h in enumerate(scored_horses):
        rank = i + 1
        win_prob = h["win_probability"]
        pos_dist = calc_position_distribution(win_prob, rank, n_horses)

        # 連対率（2着以内確率）- 上限1.0
        quinella_prob = min(1.0, pos_dist["first"] + pos_dist["second"])
        # 複勝率（3着以内確率）- 上限1.0
        place_prob = min(1.0, pos_dist["first"] + pos_dist["second"] + pos_dist["third"])

        # キャリブレーション適用（Isotonic Regressionで補正）
        if calibrators:
            if 'win' in calibrators:
                win_prob = float(calibrators['win'].predict(np.array([[win_prob]]).ravel())[0])
            if 'quinella' in calibrators:
                quinella_prob = float(calibrators['quinella'].predict(np.array([[quinella_prob]]).ravel())[0])
            if 'place' in calibrators:
                place_prob = float(calibrators['place'].predict(np.array([[place_prob]]).ravel())[0])

            # 確率の上下限を保証（0.0〜1.0）
            win_prob = max(0.0, min(1.0, win_prob))
            quinella_prob = max(0.0, min(1.0, quinella_prob))
            place_prob = max(0.0, min(1.0, place_prob))

        # 個別の信頼度（データの完全性とスコアの分離度から算出）
        # スコアが他の馬と十分に離れているかで信頼度を評価
        if i < len(scored_horses) - 1:
            score_gap = scored_horses[i + 1]["rank_score"] - h["rank_score"]
            confidence = min(0.95, 0.5 + score_gap * 0.3)
        else:
            confidence = 0.5

        ranked_horses.append({
            "rank": rank,
            "horse_number": h["horse_number"],
            "horse_name": h["horse_name"],
            "win_probability": round(win_prob, 4),
            "quinella_probability": round(quinella_prob, 4),
            "place_probability": round(place_prob, 4),
            "position_distribution": pos_dist,
            "rank_score": round(h["rank_score"], 4),
            "confidence": round(confidence, 4),
        })

    # 予測全体の信頼度（トップ馬の勝率と2位との差から算出）
    if len(scored_horses) >= 2:
        top_prob = scored_horses[0]["win_probability"]
        second_prob = scored_horses[1]["win_probability"]
        gap_ratio = (top_prob - second_prob) / max(top_prob, 0.01)
        prediction_confidence = min(0.95, 0.4 + gap_ratio * 0.5 + top_prob)
    else:
        prediction_confidence = 0.5

    return {
        "ranked_horses": ranked_horses,
        "prediction_confidence": round(prediction_confidence, 4),
        "model_info": "ensemble_model",
    }


async def generate_prediction(
    race_id: str,
    is_final: bool = False
) -> PredictionResponse:
    """
    予想生成のメイン関数（MLモデルのみ使用、LLM不使用）
    確率ベース・ランキング形式・順位分布・信頼度スコアを出力

    Args:
        race_id: レースID（16桁）
        is_final: 最終予想フラグ（馬体重後）

    Returns:
        PredictionResponse: 予想結果（確率ベース・ランキング形式）

    Raises:
        PredictionError: 予想生成に失敗した場合
    """
    logger.info(f"Starting ML prediction: race_id={race_id}, is_final={is_final}")

    # モックモードの場合
    if _is_mock_mode():
        return _generate_mock_prediction(race_id, is_final)

    try:
        # 遅延インポート（モック時は不要）
        from src.db.async_connection import get_connection
        from src.db.queries import (
            get_race_prediction_data,
            check_race_exists,
        )

        # 1. データ取得
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

        # 2. ML予測を計算
        ml_scores = {}
        try:
            ml_scores = _compute_ml_predictions(race_id, race_data.get("horses", []))
            if ml_scores:
                logger.info(f"ML predictions computed: {len(ml_scores)} horses")
            else:
                raise PredictionError("ML予測が利用できません")
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            raise PredictionError(f"ML予測に失敗しました: {e}") from e

        # 3. MLスコアから確率ベース・ランキング形式の予想結果を生成
        logger.debug("Generating probability-based ranking prediction")
        ml_result = _generate_ml_only_prediction(
            race_data=race_data,
            ml_scores=ml_scores
        )

        # 4. 予想結果をPydanticモデルに変換
        logger.debug("Converting ML result to PredictionResponse")
        prediction_response = _convert_to_prediction_response(
            race_data=race_data,
            ml_result=ml_result,
            is_final=is_final
        )

        # 5. DBに保存
        prediction_id = await save_prediction(prediction_response)
        prediction_response.prediction_id = prediction_id

        logger.info(f"ML prediction completed: prediction_id={prediction_id}")
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
            # predictions テーブルに保存（確率ベース形式）
            sql = """
                INSERT INTO predictions (
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING prediction_id;
            """

            # prediction_id を生成（UUIDベース）
            prediction_id = str(uuid.uuid4())

            # prediction_result をdict形式で取得（asyncpgがJSONBに自動変換）
            import json
            prediction_result_dict = prediction_data.prediction_result.model_dump()

            # race_date を date型に変換
            from datetime import date as date_type
            if isinstance(prediction_data.race_date, str):
                race_date = date_type.fromisoformat(prediction_data.race_date)
            else:
                race_date = prediction_data.race_date

            result = await conn.fetchrow(
                sql,
                prediction_id,
                prediction_data.race_id,
                race_date,
                prediction_data.is_final,
                json.dumps(prediction_result_dict),  # asyncpg JSONB用にJSON文字列
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
                race_name_raw = race_info.get(COL_RACE_NAME)
                # レース名が空の場合は条件コードからフォールバック生成
                if race_name_raw and race_name_raw.strip():
                    race_name = race_name_raw.strip()
                else:
                    # 競走条件からレース名を推測
                    kyoso_joken = race_info.get("kyoso_joken_code", "")
                    kyoso_shubetsu = race_info.get("kyoso_shubetsu_code", "")
                    # 簡易マッピング
                    joken_map = {
                        "005": "新馬", "010": "未勝利", "016": "1勝クラス",
                        "017": "2勝クラス", "018": "3勝クラス", "701": "OP"
                    }
                    shubetsu_map = {
                        "11": "3歳", "12": "3歳以上", "13": "4歳以上"
                    }
                    shubetsu_name = shubetsu_map.get(kyoso_shubetsu, "")
                    joken_name = joken_map.get(kyoso_joken, "条件戦")
                    race_name = f"{shubetsu_name}{joken_name}".strip() or "条件戦"

                venue_code = race_info.get(COL_JYOCD, "00")
                venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
                race_number = str(race_info.get("race_bango", "?"))
                race_time = race_info.get("hasso_jikoku", "00:00")

            # PredictionResponse に変換
            prediction_result_data = row["prediction_result"]
            # 文字列として保存されている場合はパース
            if isinstance(prediction_result_data, str):
                import json
                try:
                    prediction_result_data = json.loads(prediction_result_data)
                except json.JSONDecodeError:
                    prediction_result_data = {"ranked_horses": [], "prediction_confidence": 0.5, "model_info": "unknown"}
            # ランキングエントリを構築
            ranked_horses = [
                HorseRankingEntry(
                    rank=h["rank"],
                    horse_number=h["horse_number"],
                    horse_name=h["horse_name"],
                    win_probability=h["win_probability"],
                    quinella_probability=h.get("quinella_probability", h["win_probability"] + h.get("position_distribution", {}).get("second", 0)),
                    place_probability=h["place_probability"],
                    position_distribution=PositionDistribution(**h["position_distribution"]),
                    rank_score=h["rank_score"],
                    confidence=h["confidence"],
                )
                for h in prediction_result_data.get("ranked_horses", [])
            ]
            prediction_result = PredictionResult(
                ranked_horses=ranked_horses,
                prediction_confidence=prediction_result_data.get("prediction_confidence", 0.5),
                model_info=prediction_result_data.get("model_info", "unknown"),
            )

            # race_dateを文字列に変換
            race_date_raw = row["race_date"]
            if hasattr(race_date_raw, 'isoformat'):
                race_date_str = race_date_raw.isoformat()
            else:
                race_date_str = str(race_date_raw)

            prediction_response = PredictionResponse(
                prediction_id=row["prediction_id"],
                race_id=row["race_id"],
                race_name=race_name,
                race_date=race_date_str,
                venue=venue,
                race_number=race_number,
                race_time=race_time,
                prediction_result=prediction_result,
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
                        prediction_result
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
                        prediction_result
                    FROM predictions
                    WHERE race_id = $1 AND is_final = $2
                    ORDER BY predicted_at DESC;
                """
                rows = await conn.fetch(sql, race_id, is_final)

            predictions = []
            for row in rows:
                pred_result = row["prediction_result"]
                # 文字列として保存されている場合はパース
                if isinstance(pred_result, str):
                    import json
                    try:
                        pred_result = json.loads(pred_result)
                    except json.JSONDecodeError:
                        pred_result = {}
                confidence = pred_result.get("prediction_confidence", 0.5) if pred_result else 0.5
                predictions.append(
                    PredictionHistoryItem(
                        prediction_id=row["prediction_id"],
                        predicted_at=row["predicted_at"],
                        is_final=row["is_final"],
                        prediction_confidence=confidence,
                    )
                )

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
    ml_result: Dict[str, Any],
    is_final: bool
) -> PredictionResponse:
    """
    ML結果を確率ベース・ランキング形式のPredictionResponseに変換

    Args:
        race_data: レースデータ
        ml_result: ML予想結果（確率ベース・ランキング形式）
        is_final: 最終予想フラグ

    Returns:
        PredictionResponse: 変換後の予想結果
    """
    race_info = race_data.get("race", {})

    # レース情報を抽出
    race_id = race_info.get(COL_RACE_ID, "")
    race_name_raw = race_info.get(COL_RACE_NAME)
    # レース名が空の場合は条件コードからフォールバック生成
    if race_name_raw and race_name_raw.strip():
        race_name = race_name_raw.strip()
    else:
        # 競走条件からレース名を推測
        kyoso_joken = race_info.get("kyoso_joken_code", "")
        kyoso_shubetsu = race_info.get("kyoso_shubetsu_code", "")
        # 簡易マッピング
        joken_map = {
            "005": "新馬", "010": "未勝利", "016": "1勝クラス",
            "017": "2勝クラス", "018": "3勝クラス", "701": "OP"
        }
        shubetsu_map = {
            "11": "3歳", "12": "3歳以上", "13": "4歳以上"
        }
        shubetsu_name = shubetsu_map.get(kyoso_shubetsu, "")
        joken_name = joken_map.get(kyoso_joken, "条件戦")
        race_name = f"{shubetsu_name}{joken_name}".strip() or "条件戦"

    venue_code = race_info.get(COL_JYOCD, "00")
    venue = VENUE_CODE_MAP.get(venue_code, f"競馬場{venue_code}")
    race_number = str(race_info.get("race_bango", "?"))
    race_time = race_info.get("hasso_jikoku", "00:00")

    # 開催日を計算
    kaisai_year = race_info.get(COL_KAISAI_YEAR, "")
    kaisai_monthday = race_info.get(COL_KAISAI_MONTHDAY, "")
    if kaisai_year and kaisai_monthday:
        race_date = f"{kaisai_year}-{kaisai_monthday[:2]}-{kaisai_monthday[2:]}"
    else:
        race_date = datetime.now().strftime("%Y-%m-%d")

    # ランキングエントリを構築
    ranked_horses_data = ml_result.get("ranked_horses", [])
    ranked_horses = [
        HorseRankingEntry(
            rank=h["rank"],
            horse_number=h["horse_number"],
            horse_name=h["horse_name"],
            win_probability=h["win_probability"],
            quinella_probability=h["quinella_probability"],
            place_probability=h["place_probability"],
            position_distribution=PositionDistribution(**h["position_distribution"]),
            rank_score=h["rank_score"],
            confidence=h["confidence"],
        )
        for h in ranked_horses_data
    ]

    # PredictionResult を構築（確率ベース・ランキング形式）
    prediction_result = PredictionResult(
        ranked_horses=ranked_horses,
        prediction_confidence=ml_result.get("prediction_confidence", 0.5),
        model_info=ml_result.get("model_info", "ensemble_model"),
    )

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
                is_final=False
            )

            print("\n予想結果（確率ベース・ランキング形式）:")
            print(f"予想ID: {prediction.prediction_id}")
            print(f"レース: {prediction.race_name}")
            print(f"予測信頼度: {prediction.prediction_result.prediction_confidence:.2%}")
            print(f"\n全馬ランキング:")
            for h in prediction.prediction_result.ranked_horses:
                print(f"  {h.rank}位: {h.horse_number}番 {h.horse_name} "
                      f"(勝率: {h.win_probability:.1%}, 複勝率: {h.place_probability:.1%})")

        except Exception as e:
            print(f"エラー: {e}")

    asyncio.run(test_prediction())
