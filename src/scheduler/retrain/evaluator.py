"""
Model Evaluation Functions

Functions for comparing and evaluating ensemble models.
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2.extras

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor

logger = logging.getLogger(__name__)


def compare_models(current_model_path: Path, new_model_path: str, test_year: int = 2022) -> dict:
    """
    Compare old and new models using comprehensive evaluation.

    Evaluation metrics:
    - AUC (win/quinella/place)
    - Top-3 coverage
    - Return rate simulation (win/place)
    - RMSE

    Uses composite score for final judgment (AUC focused, returns considered).

    Note: test_year should be a year not included in training data.
          Default 2022 (training uses 2023 onwards).

    Args:
        current_model_path: Path to current model
        new_model_path: Path to new model
        test_year: Year to use for testing

    Returns:
        Comparison result dictionary
    """

    logger.info(f"Model comparison (test year: {test_year})")
    logger.info("* Backtesting with data outside training set")

    # Load models
    try:
        old_model_data = joblib.load(current_model_path)
        new_model_data = joblib.load(new_model_path)
    except Exception as e:
        logger.error(f"Model load error: {e}")
        return {"status": "error", "message": str(e)}

    old_features = old_model_data["feature_names"]
    new_features = new_model_data["feature_names"]

    # Get classification models
    old_model_data.get("models", {})
    new_model_data.get("models", {})

    # Get test data (including payout data)
    db = get_db()
    conn = db.get_connection()

    try:
        extractor = FastFeatureExtractor(conn)
        test_data = extractor.extract_year_data(test_year)

        if test_data is None or len(test_data) == 0:
            return {"status": "error", "message": "no_test_data"}

        if isinstance(test_data, list):
            df = pd.DataFrame(test_data)
        else:
            df = test_data

        logger.info(f"Test samples: {len(df)}")

        # Get payout data
        payouts = get_payouts_for_year(conn, test_year)

        # Evaluate both models
        # Check for missing features (old model may not work with new feature set)
        missing_old_features = set(old_features) - set(df.columns)
        if missing_old_features:
            logger.warning(f"Missing features for old model: {missing_old_features}")
            logger.info("Feature set changed, evaluating new model only")
            old_eval = None
        else:
            old_eval = evaluate_model(df, old_model_data, old_features, payouts, "Old model")
        new_eval = evaluate_model(df, new_model_data, new_features, payouts, "New model")

        # Calculate composite scores
        new_score = calculate_composite_score(new_eval)

        logger.info("=" * 50)
        logger.info("Comparison results")
        logger.info("=" * 50)

        if old_eval is not None:
            old_score = calculate_composite_score(old_eval)
            improvement = new_score - old_score
            logger.info(f"Old model composite score: {old_score:.4f}")
            logger.info(f"New model composite score: {new_score:.4f}")
            logger.info(
                f"Improvement: {improvement:+.4f} ({'New model wins' if improvement > 0 else 'Keep old model'})"
            )
        else:
            # Force new model adoption when features changed
            old_score = 0.0
            improvement = 1.0
            logger.info("Old model: Evaluation skipped (feature change)")
            logger.info(f"New model composite score: {new_score:.4f}")
            logger.info("Adopting new model due to feature set change")

        return {
            "status": "success",
            "old_eval": old_eval,
            "new_eval": new_eval,
            "old_score": float(old_score),
            "new_score": float(new_score),
            "improvement": float(improvement),
            "test_samples": len(df),
            # Backward compatibility
            "old_rmse": old_eval.get("rmse", 0) if old_eval else 0,
            "new_rmse": new_eval.get("rmse", 0),
        }

    finally:
        conn.close()


def evaluate_model(
    df: pd.DataFrame, model_data: dict, features: list, payouts: dict, model_name: str
) -> dict:
    """
    Run comprehensive model evaluation.

    Args:
        df: Test dataframe
        model_data: Model data dictionary
        features: Feature column names
        payouts: Payout data dictionary
        model_name: Name for logging

    Returns:
        Evaluation result dictionary
    """
    from sklearn.metrics import roc_auc_score

    models = model_data.get("models", {})
    weights = model_data.get("ensemble_weights")  # CatBoost-compatible weights
    X = df[features].fillna(0)

    # Regression prediction (ranking)
    xgb_reg = models.get("xgb_regressor") or model_data.get("xgb_model")
    lgb_reg = models.get("lgb_regressor") or model_data.get("lgb_model")
    cb_reg = models.get("cb_regressor") or model_data.get("cb_model")

    if cb_reg is not None and weights is not None:
        # 3-model ensemble
        reg_pred = (
            xgb_reg.predict(X) * weights["xgb"]
            + lgb_reg.predict(X) * weights["lgb"]
            + cb_reg.predict(X) * weights["cb"]
        )
    else:
        # 2-model average (backward compatibility)
        reg_pred = (xgb_reg.predict(X) + lgb_reg.predict(X)) / 2

    rmse = float(np.sqrt(np.mean((reg_pred - df["target"]) ** 2)))

    # Classification predictions
    eval_result = {"rmse": rmse}

    # CatBoost classifiers
    cb_win = models.get("cb_win")
    cb_quinella = models.get("cb_quinella")
    cb_place = models.get("cb_place")

    # Win AUC
    if "xgb_win" in models and "lgb_win" in models:
        win_prob = get_ensemble_proba(
            models["xgb_win"],
            models["lgb_win"],
            X,
            models.get("win_calibrator"),
            cb_clf=cb_win,
            weights=weights,
        )
        win_actual = (df["target"] == 1).astype(int)
        try:
            eval_result["win_auc"] = float(roc_auc_score(win_actual, win_prob))
        except Exception:
            eval_result["win_auc"] = 0.5

    # Quinella AUC
    if "xgb_quinella" in models and "lgb_quinella" in models:
        quinella_prob = get_ensemble_proba(
            models["xgb_quinella"],
            models["lgb_quinella"],
            X,
            models.get("quinella_calibrator"),
            cb_clf=cb_quinella,
            weights=weights,
        )
        quinella_actual = (df["target"] <= 2).astype(int)
        try:
            eval_result["quinella_auc"] = float(roc_auc_score(quinella_actual, quinella_prob))
        except Exception:
            eval_result["quinella_auc"] = 0.5

    # Place AUC
    if "xgb_place" in models and "lgb_place" in models:
        place_prob = get_ensemble_proba(
            models["xgb_place"],
            models["lgb_place"],
            X,
            models.get("place_calibrator"),
            cb_clf=cb_place,
            weights=weights,
        )
        place_actual = (df["target"] <= 3).astype(int)
        try:
            eval_result["place_auc"] = float(roc_auc_score(place_actual, place_prob))
        except Exception:
            eval_result["place_auc"] = 0.5

    # Top-3 coverage (calculated per race)
    df_eval = df.copy()
    df_eval["pred_rank"] = reg_pred

    if "race_code" in df_eval.columns:
        top3_hits = 0
        total_races = 0

        for _race_code, race_df in df_eval.groupby("race_code"):
            race_df_sorted = race_df.sort_values("pred_rank")
            top3_pred = race_df_sorted.head(3)["target"].values
            if any(t == 1 for t in top3_pred):
                top3_hits += 1
            total_races += 1

        eval_result["top3_coverage"] = float(top3_hits / total_races) if total_races > 0 else 0

    # Return simulation
    returns = simulate_returns(df_eval, reg_pred, payouts)
    eval_result.update(returns)

    # Log output
    logger.info(f"[{model_name}]")
    logger.info(f"  RMSE: {rmse:.4f}")
    logger.info(f"  Win AUC: {eval_result.get('win_auc', 0):.4f}")
    logger.info(f"  Quinella AUC: {eval_result.get('quinella_auc', 0):.4f}")
    logger.info(f"  Place AUC: {eval_result.get('place_auc', 0):.4f}")
    logger.info(f"  Top-3 coverage: {eval_result.get('top3_coverage', 0)*100:.1f}%")
    logger.info(f"  Win return: {eval_result.get('tansho_return', 0)*100:.1f}%")
    logger.info(f"  Place return: {eval_result.get('fukusho_return', 0)*100:.1f}%")

    return eval_result


def get_ensemble_proba(
    xgb_clf, lgb_clf, X, calibrator=None, cb_clf=None, weights=None
) -> np.ndarray:
    """
    Get ensemble probability (with calibration, CatBoost support).

    Args:
        xgb_clf: XGBoost classifier
        lgb_clf: LightGBM classifier
        X: Feature matrix
        calibrator: Optional calibrator
        cb_clf: Optional CatBoost classifier
        weights: Optional ensemble weights

    Returns:
        Ensemble probability array
    """
    xgb_prob = xgb_clf.predict_proba(X)[:, 1]
    lgb_prob = lgb_clf.predict_proba(X)[:, 1]

    if cb_clf is not None and weights is not None:
        # 3-model ensemble
        cb_prob = cb_clf.predict_proba(X)[:, 1]
        raw_prob = xgb_prob * weights["xgb"] + lgb_prob * weights["lgb"] + cb_prob * weights["cb"]
    elif weights is not None:
        # 2-model weighted ensemble
        raw_prob = xgb_prob * weights.get("xgb", 0.5) + lgb_prob * weights.get("lgb", 0.5)
    else:
        # 2-model simple average (backward compatibility)
        raw_prob = (xgb_prob + lgb_prob) / 2

    if calibrator is not None:
        try:
            return calibrator.predict(raw_prob)
        except Exception:
            pass
    return raw_prob


def get_payouts_for_year(conn, year: int) -> dict:
    """
    Get payout data for a year.

    Args:
        conn: Database connection
        year: Target year

    Returns:
        Dictionary mapping race_code to payout data
    """
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            """
            SELECT race_code,
                   tansho1_umaban, tansho1_haraimodoshikin,
                   fukusho1_umaban, fukusho1_haraimodoshikin,
                   fukusho2_umaban, fukusho2_haraimodoshikin,
                   fukusho3_umaban, fukusho3_haraimodoshikin
            FROM haraimodoshi
            WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
        """,
            (year,),
        )

        payouts = {}
        for row in cur.fetchall():
            race_code = row["race_code"]

            # Safely get win payout
            tansho_umaban = row["tansho1_umaban"]
            tansho_payout = row["tansho1_haraimodoshikin"]
            tansho_umaban_str = str(tansho_umaban).strip() if tansho_umaban else None
            try:
                tansho_payout_int = (
                    int(str(tansho_payout).strip())
                    if tansho_payout and str(tansho_payout).strip()
                    else 0
                )
            except ValueError:
                tansho_payout_int = 0

            payouts[race_code] = {
                "tansho": {"umaban": tansho_umaban_str, "payout": tansho_payout_int},
                "fukusho": [],
            }

            # Safely get place payouts
            for i in range(1, 4):
                umaban = row.get(f"fukusho{i}_umaban")
                payout = row.get(f"fukusho{i}_haraimodoshikin")
                if umaban and str(umaban).strip():
                    try:
                        payout_int = (
                            int(str(payout).strip()) if payout and str(payout).strip() else 0
                        )
                    except ValueError:
                        payout_int = 0
                    if payout_int > 0:
                        payouts[race_code]["fukusho"].append(
                            {"umaban": str(umaban).strip(), "payout": payout_int}
                        )
        cur.close()
        logger.info(f"Payout data retrieved: {len(payouts)} races")
        return payouts
    except Exception as e:
        logger.warning(f"Payout data retrieval error: {e}")
        return {}


def simulate_returns(df: pd.DataFrame, predictions: np.ndarray, payouts: dict) -> dict:
    """
    Simulate returns (bet 100 yen on top prediction per race).

    Args:
        df: Dataframe with race data
        predictions: Prediction scores
        payouts: Payout data dictionary

    Returns:
        Return statistics dictionary
    """
    df_sim = df.copy()
    df_sim["pred_rank"] = predictions

    tansho_bet = 0
    tansho_win = 0
    fukusho_bet = 0
    fukusho_win = 0

    # Check horse number column (umaban or horse_number)
    umaban_col = "umaban" if "umaban" in df_sim.columns else "horse_number"
    if "race_code" not in df_sim.columns or umaban_col not in df_sim.columns:
        logger.warning(
            f"Missing columns for return calculation: race_code={('race_code' in df_sim.columns)}, {umaban_col}={(umaban_col in df_sim.columns)}"
        )
        return {"tansho_return": 0, "fukusho_return": 0}

    for race_code, race_df in df_sim.groupby("race_code"):
        race_df_sorted = race_df.sort_values("pred_rank")
        if len(race_df_sorted) == 0:
            continue

        top1 = race_df_sorted.iloc[0]
        pred_umaban = str(int(top1[umaban_col]))

        payout_data = payouts.get(race_code, {})

        # Win bet
        tansho_bet += 100
        tansho_info = payout_data.get("tansho", {})
        if tansho_info.get("umaban") == pred_umaban:
            tansho_win += tansho_info.get("payout", 0)

        # Place bet
        fukusho_bet += 100
        for fuku in payout_data.get("fukusho", []):
            if fuku.get("umaban") == pred_umaban:
                fukusho_win += fuku.get("payout", 0)
                break

    return {
        "tansho_return": float(tansho_win / tansho_bet) if tansho_bet > 0 else 0,
        "fukusho_return": float(fukusho_win / fukusho_bet) if fukusho_bet > 0 else 0,
        "tansho_bet": tansho_bet,
        "tansho_win": tansho_win,
        "fukusho_bet": fukusho_bet,
        "fukusho_win": fukusho_win,
    }


def calculate_composite_score(eval_result: dict) -> float:
    """
    Calculate composite score.

    Weights:
    - Win AUC: 25% (core classification accuracy)
    - Quinella AUC: 15%
    - Place AUC: 15%
    - Top-3 coverage: 20% (practical utility)
    - Win return: 15% (profitability)
    - Place return: 10%

    Args:
        eval_result: Evaluation result dictionary

    Returns:
        Composite score
    """
    weights = {
        "win_auc": 0.25,
        "quinella_auc": 0.15,
        "place_auc": 0.15,
        "top3_coverage": 0.20,
        "tansho_return": 0.15,
        "fukusho_return": 0.10,
    }

    score = 0
    for metric, weight in weights.items():
        value = eval_result.get(metric, 0)
        # AUC is in 0.5-1.0 range, so subtract 0.5 and double to get 0-1 scale
        if "auc" in metric:
            value = (value - 0.5) * 2
        # Return rate: 1.0 = 100%, use as-is
        score += value * weight

    return score
