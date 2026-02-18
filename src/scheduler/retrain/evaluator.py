"""
Model Evaluation Functions

Functions for comparing and evaluating ensemble models.
"""

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import psycopg2.extras

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor
from src.services.prediction.ensemble import ensemble_proba

logger = logging.getLogger(__name__)


def compare_models(
    current_model_path: Path,
    new_model_path: str,
    test_year: int = 2022,
    surface: str | None = None,
) -> dict:
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
        surface: Surface filter ("turf", "dirt", or None for all)

    Returns:
        Comparison result dictionary
    """
    surface_label = f" [{surface}]" if surface else ""
    logger.info(f"Model comparison (test year: {test_year}){surface_label}")
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
        test_data = extractor.extract_year_data(test_year, surface=surface)

        if test_data is None or len(test_data) == 0:
            return {"status": "error", "message": "no_test_data"}

        if isinstance(test_data, list):
            df = pd.DataFrame(test_data)
        else:
            df = test_data

        logger.info(f"Test samples: {len(df)}")

        # Get payout data and odds for EV-based simulation
        payouts = get_payouts_for_year(conn, test_year)
        tansho_odds = get_tansho_odds_for_year(conn, test_year)

        # Evaluate both models
        # Check for missing features (old model may not work with new feature set)
        missing_old_features = set(old_features) - set(df.columns)
        if missing_old_features:
            logger.warning(f"Missing features for old model: {missing_old_features}")
            logger.info("Feature set changed, evaluating new model only")
            old_eval = None
        else:
            old_eval = evaluate_model(
                df, old_model_data, old_features, payouts, "Old model", tansho_odds
            )
        new_eval = evaluate_model(
            df, new_model_data, new_features, payouts, "New model", tansho_odds
        )

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
    df: pd.DataFrame,
    model_data: dict,
    features: list,
    payouts: dict,
    model_name: str,
    tansho_odds: dict | None = None,
) -> dict:
    """
    Run comprehensive model evaluation.

    Args:
        df: Test dataframe
        model_data: Model data dictionary
        features: Feature column names
        payouts: Payout data dictionary
        model_name: Name for logging
        tansho_odds: Optional tansho odds data for EV-based simulation

    Returns:
        Evaluation result dictionary
    """
    from sklearn.metrics import roc_auc_score

    models = model_data.get("models", {})
    weights = model_data.get("ensemble_weights") or {"xgb": 0.5, "lgb": 0.5}
    is_ranker = model_data.get("model_type") == "ranker"
    sort_ascending = not is_ranker  # Ranker: higher = better, Regressor: lower = better
    X = df[features].fillna(0)

    # Regression/Ranking prediction
    xgb_reg = models.get("xgb_regressor") or model_data.get("xgb_model")
    lgb_reg = models.get("lgb_regressor") or model_data.get("lgb_model")
    cb_reg = models.get("cb_regressor") or model_data.get("cb_model")

    if xgb_reg is None or lgb_reg is None:
        raise ValueError("XGBoost and LightGBM regressors are required")

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

    # RMSE (only meaningful for regressor; ranker scores are not on the same scale)
    if is_ranker:
        rmse = 0.0
    else:
        rmse = float(np.sqrt(np.mean((reg_pred - df["target"]) ** 2)))

    # Classification predictions
    eval_result = {"rmse": rmse}
    win_prob = None

    # CatBoost classifiers
    cb_win = models.get("cb_win")
    cb_quinella = models.get("cb_quinella")
    cb_place = models.get("cb_place")

    # Win AUC
    if "xgb_win" in models and "lgb_win" in models:
        win_prob = ensemble_proba(
            models["xgb_win"],
            models["lgb_win"],
            X,
            weights,
            cb_clf=cb_win,
            calibrator=models.get("win_calibrator"),
        )
        win_actual = (df["target"] == 1).astype(int)
        try:
            eval_result["win_auc"] = float(roc_auc_score(win_actual, win_prob))
        except Exception:
            eval_result["win_auc"] = 0.5

    # Quinella AUC
    if "xgb_quinella" in models and "lgb_quinella" in models:
        quinella_prob = ensemble_proba(
            models["xgb_quinella"],
            models["lgb_quinella"],
            X,
            weights,
            cb_clf=cb_quinella,
            calibrator=models.get("quinella_calibrator"),
        )
        quinella_actual = (df["target"] <= 2).astype(int)
        try:
            eval_result["quinella_auc"] = float(roc_auc_score(quinella_actual, quinella_prob))
        except Exception:
            eval_result["quinella_auc"] = 0.5

    # Place AUC
    if "xgb_place" in models and "lgb_place" in models:
        place_prob = ensemble_proba(
            models["xgb_place"],
            models["lgb_place"],
            X,
            weights,
            cb_clf=cb_place,
            calibrator=models.get("place_calibrator"),
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
            race_df_sorted = race_df.sort_values("pred_rank", ascending=sort_ascending)
            top3_pred = race_df_sorted.head(3)["target"].values
            if any(t == 1 for t in top3_pred):
                top3_hits += 1
            total_races += 1

        eval_result["top3_coverage"] = float(top3_hits / total_races) if total_races > 0 else 0

    # Return simulation (top-1 per race)
    returns = simulate_returns(df_eval, reg_pred, payouts, ascending=sort_ascending)
    eval_result.update(returns)

    # EV-based return simulation (matching production betting logic)
    if tansho_odds and win_prob is not None:
        ev_returns = simulate_ev_returns(df_eval, win_prob, tansho_odds, payouts)
        eval_result.update(ev_returns)

    # Log output
    logger.info(f"[{model_name}]")
    logger.info(f"  RMSE: {rmse:.4f}")
    logger.info(f"  Win AUC: {eval_result.get('win_auc', 0):.4f}")
    logger.info(f"  Quinella AUC: {eval_result.get('quinella_auc', 0):.4f}")
    logger.info(f"  Place AUC: {eval_result.get('place_auc', 0):.4f}")
    logger.info(f"  Top-3 coverage: {eval_result.get('top3_coverage', 0)*100:.1f}%")
    logger.info(f"  Win return (top1): {eval_result.get('tansho_return', 0)*100:.1f}%")
    logger.info(f"  Place return (top1): {eval_result.get('fukusho_return', 0)*100:.1f}%")
    if "ev_tansho_return" in eval_result:
        logger.info(
            f"  EV-based return: {eval_result['ev_tansho_return']*100:.1f}% "
            f"({eval_result['ev_bet_count']} bets in {eval_result['ev_race_count']} races)"
        )

    return eval_result


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

        payouts: dict[str, Any] = {}
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


def simulate_returns(
    df: pd.DataFrame, predictions: np.ndarray, payouts: dict, ascending: bool = True
) -> dict:
    """
    Simulate returns (bet 100 yen on top prediction per race).

    Args:
        df: Dataframe with race data
        predictions: Prediction scores
        payouts: Payout data dictionary
        ascending: Sort direction (True for regressor, False for ranker)

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
        race_df_sorted = race_df.sort_values("pred_rank", ascending=ascending)
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


def get_tansho_odds_for_year(conn, year: int) -> dict:
    """Get tansho (win) odds for all horses in a year.

    Args:
        conn: Database connection
        year: Target year

    Returns:
        Dict mapping race_code -> {umaban: odds_float}
    """
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            """
            SELECT race_code, umaban, odds
            FROM odds1_tansho
            WHERE EXTRACT(YEAR FROM TO_DATE(SUBSTRING(race_code, 1, 8), 'YYYYMMDD')) = %s
        """,
            (year,),
        )

        odds_dict: dict[str, dict[str, float]] = {}
        for row in cur.fetchall():
            race_code = row["race_code"]
            umaban = str(row["umaban"]).strip()
            try:
                odds = float(row["odds"]) / 10  # Stored as 10x value
            except (ValueError, TypeError):
                continue
            if odds > 0:
                if race_code not in odds_dict:
                    odds_dict[race_code] = {}
                odds_dict[race_code][umaban] = odds

        cur.close()
        logger.info(f"Tansho odds retrieved: {len(odds_dict)} races")
        return odds_dict
    except Exception as e:
        logger.warning(f"Tansho odds retrieval error: {e}")
        return {}


def simulate_ev_returns(
    df: pd.DataFrame,
    win_probs: np.ndarray,
    tansho_odds: dict,
    payouts: dict,
    ev_threshold: float = 1.5,
) -> dict:
    """Simulate EV-based betting returns (matching production logic).

    Bets 100 yen on each horse where win_prob * odds >= ev_threshold.
    Multiple bets per race are possible; some races may have zero bets.

    Args:
        df: Dataframe with race_code and umaban/horse_number columns
        win_probs: Win probability array (aligned with df rows)
        tansho_odds: Dict mapping race_code -> {umaban: odds}
        payouts: Payout data dictionary
        ev_threshold: EV threshold for betting

    Returns:
        EV-based return statistics
    """
    df_sim = df.copy()
    df_sim["win_prob"] = win_probs

    umaban_col = "umaban" if "umaban" in df_sim.columns else "horse_number"
    if "race_code" not in df_sim.columns or umaban_col not in df_sim.columns:
        return {"ev_tansho_return": 0, "ev_bet_count": 0, "ev_race_count": 0}

    total_bet = 0
    total_win = 0
    bet_count = 0
    races_with_bets = 0

    for race_code, race_df in df_sim.groupby("race_code"):
        race_odds = tansho_odds.get(race_code, {})
        if not race_odds:
            continue

        payout_data = payouts.get(race_code, {})
        tansho_info = payout_data.get("tansho", {})
        winning_umaban = tansho_info.get("umaban")
        winning_payout = tansho_info.get("payout", 0)

        race_bet = False
        for _, row in race_df.iterrows():
            umaban = str(int(row[umaban_col]))
            win_prob = row["win_prob"]
            odds = race_odds.get(umaban, 0)

            if odds <= 0 or win_prob <= 0:
                continue

            ev = win_prob * odds
            if ev >= ev_threshold:
                total_bet += 100
                bet_count += 1
                race_bet = True
                if umaban == winning_umaban:
                    total_win += winning_payout

        if race_bet:
            races_with_bets += 1

    return {
        "ev_tansho_return": float(total_win / total_bet) if total_bet > 0 else 0,
        "ev_bet_count": bet_count,
        "ev_race_count": races_with_bets,
        "ev_total_bet": total_bet,
        "ev_total_win": total_win,
    }


def calculate_composite_score(eval_result: dict) -> float:
    """
    Calculate composite score.

    Weights:
    - Win AUC: 25% (core classification accuracy)
    - Quinella AUC: 15%
    - Place AUC: 15%
    - Top-3 coverage: 20% (practical utility)
    - Win return (top1): 10% (baseline profitability)
    - Place return (top1): 5%
    - EV-based return: 10% (production-matching profitability)

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
        "tansho_return": 0.10,
        "fukusho_return": 0.05,
        "ev_tansho_return": 0.10,
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
