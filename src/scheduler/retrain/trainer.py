"""
Model Training Functions

Functions for training ensemble models (XGBoost + LightGBM + CatBoost).
"""

import logging
from datetime import date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2.extras
from sklearn.isotonic import IsotonicRegression

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor

logger = logging.getLogger(__name__)


def calc_bin_stats(
    predicted: np.ndarray,
    actual: np.ndarray,
    calibrated: np.ndarray,
    n_bins: int = 20
) -> dict:
    """
    Calculate calibration bin statistics.

    Args:
        predicted: Raw predicted probabilities
        actual: Actual outcomes (0 or 1)
        calibrated: Calibrated probabilities
        n_bins: Number of bins for calibration analysis

    Returns:
        Dictionary with calibration statistics
    """
    from sklearn.metrics import brier_score_loss

    bin_stats = []
    bin_edges = np.linspace(0, 1, n_bins + 1)

    for i in range(n_bins):
        bin_start = bin_edges[i]
        bin_end = bin_edges[i + 1]

        mask = (predicted >= bin_start) & (predicted < bin_end)
        count = mask.sum()

        if count > 0:
            bin_stats.append({
                'bin_start': float(bin_start),
                'bin_end': float(bin_end),
                'count': int(count),
                'avg_predicted': float(predicted[mask].mean()),
                'avg_actual': float(actual[mask].mean()),
                'calibrated': float(calibrated[mask].mean())
            })

    brier_before = brier_score_loss(actual, predicted)
    brier_after = brier_score_loss(actual, calibrated)
    improvement = (brier_before - brier_after) / brier_before * 100 if brier_before > 0 else 0

    return {
        'total_samples': int(len(predicted)),
        'avg_predicted': float(predicted.mean()),
        'avg_actual': float(actual.mean()),
        'brier_before': float(brier_before),
        'brier_after': float(brier_after),
        'improvement': float(improvement),
        'bin_stats': bin_stats
    }


def save_calibration_to_db(calibration_data: dict, model_version: str) -> bool:
    """
    Save calibration statistics to database.

    Args:
        calibration_data: Calibration statistics dictionary
        model_version: Model version string

    Returns:
        True if successful, False otherwise
    """
    try:
        db = get_db()
        conn = db.get_connection()
        cur = conn.cursor()

        # Deactivate existing active calibrations
        cur.execute("UPDATE model_calibration SET is_active = FALSE WHERE is_active = TRUE")

        # Save new calibration
        cur.execute('''
            INSERT INTO model_calibration (
                model_version, calibration_data, created_at, is_active
            ) VALUES (%s, %s, %s, TRUE)
        ''', (
            model_version,
            psycopg2.extras.Json(calibration_data),
            datetime.now()
        ))

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Calibration statistics saved to DB (version: {model_version})")
        return True
    except Exception as e:
        logger.error(f"Calibration save error: {e}")
        return False


def train_new_model(model_dir: Path, years: int = 3) -> dict:
    """
    Train new ensemble model (regression + classification + calibration).

    Args:
        model_dir: Directory to save the model
        years: Number of years of training data

    Returns:
        Training result dictionary
    """
    import catboost as cb
    import lightgbm as lgb
    import xgboost as xgb

    logger.info(f"Starting ensemble model training (past {years} years)")

    db = get_db()
    conn = db.get_connection()

    try:
        extractor = FastFeatureExtractor(conn)

        # Extract data
        current_year = date.today().year
        all_data = []

        for year in range(current_year - years, current_year + 1):
            logger.info(f"  Extracting {year} data...")
            year_data = extractor.extract_year_data(year)
            if year_data is not None and len(year_data) > 0:
                if isinstance(year_data, pd.DataFrame):
                    all_data.append(year_data)
                else:
                    all_data.append(pd.DataFrame(year_data))
                logger.info(f"    {len(year_data)} records")

        if not all_data:
            logger.error("No training data")
            return {'status': 'error', 'message': 'no_training_data'}

        # Combine DataFrames
        df = pd.concat(all_data, ignore_index=True)
        logger.info(f"Total samples: {len(df)}")

        # Features and targets (exclude string columns)
        exclude_cols = ['race_code', 'umaban', 'bamei', 'target', 'kakutei_chakujun', 'kettonum']
        # Extract numeric columns only
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [c for c in numeric_cols if c not in exclude_cols]

        X = df[feature_cols].fillna(0)
        y = df['target']

        # Classification targets
        y_win = (y == 1).astype(int)       # Win (1st place)
        y_quinella = (y <= 2).astype(int)  # Exacta (top 2)
        y_place = (y <= 3).astype(int)     # Place (top 3)

        # ===== 3-way split (time-series order) =====
        # train (70%): Model training
        # calib (15%): Calibrator training (prevent data leak)
        # test  (15%): Final evaluation
        n = len(df)
        train_end = int(n * 0.70)
        calib_end = int(n * 0.85)

        X_train = X[:train_end]
        X_calib = X[train_end:calib_end]
        X_test = X[calib_end:]
        X_val = X_calib  # Use calib data for early stopping

        y_train = y[:train_end]
        y_calib = y[train_end:calib_end]
        y_test = y[calib_end:]
        y_val = y_calib

        y_win_train = y_win[:train_end]
        y_win_calib = y_win[train_end:calib_end]
        y_win_test = y_win[calib_end:]
        y_win_val = y_win_calib

        y_quinella_train = y_quinella[:train_end]
        y_quinella_calib = y_quinella[train_end:calib_end]
        y_quinella_test = y_quinella[calib_end:]
        y_quinella_val = y_quinella_calib

        y_place_train = y_place[:train_end]
        y_place_calib = y_place[train_end:calib_end]
        y_place_test = y_place[calib_end:]
        y_place_val = y_place_calib

        logger.info(f"Train: {len(X_train)}, Calib: {len(X_calib)}, Test: {len(X_test)}")

        # Common parameters
        base_params = {
            'n_estimators': 500,
            'max_depth': 7,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'n_jobs': -1
        }

        # CatBoost parameters
        cb_params = {
            'iterations': 500,
            'depth': 7,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'random_seed': 42,
            'verbose': False,
            'thread_count': -1
        }

        # Ensemble weights (XGB:LGB:CB = 30:40:30)
        XGB_WEIGHT = 0.30
        LGB_WEIGHT = 0.40
        CB_WEIGHT = 0.30

        models = {}

        # ===== 1. Regression models =====
        logger.info("Training XGBoost regression model...")
        xgb_reg = xgb.XGBRegressor(**base_params)
        xgb_reg.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        models['xgb_regressor'] = xgb_reg

        logger.info("Training LightGBM regression model...")
        lgb_reg = lgb.LGBMRegressor(**base_params, verbose=-1)
        lgb_reg.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        models['lgb_regressor'] = lgb_reg

        logger.info("Training CatBoost regression model...")
        cb_reg = cb.CatBoostRegressor(**cb_params)
        cb_reg.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=50)
        models['cb_regressor'] = cb_reg

        # Ensemble evaluation
        xgb_pred = xgb_reg.predict(X_val)
        lgb_pred = lgb_reg.predict(X_val)
        cb_pred = cb_reg.predict(X_val)
        ensemble_pred = xgb_pred * XGB_WEIGHT + lgb_pred * LGB_WEIGHT + cb_pred * CB_WEIGHT
        rmse = np.sqrt(np.mean((ensemble_pred - y_val) ** 2))
        logger.info(f"Regression RMSE (3-model ensemble): {rmse:.4f}")

        # ===== 2. Win classification models =====
        win_weight = len(y_win_train[y_win_train == 0]) / max(len(y_win_train[y_win_train == 1]), 1)

        logger.info("Training XGBoost win classifier...")
        xgb_win = xgb.XGBClassifier(**base_params, scale_pos_weight=win_weight)
        xgb_win.fit(X_train, y_win_train, eval_set=[(X_val, y_win_val)], verbose=False)
        models['xgb_win'] = xgb_win

        logger.info("Training LightGBM win classifier...")
        lgb_win = lgb.LGBMClassifier(**base_params, scale_pos_weight=win_weight, verbose=-1)
        lgb_win.fit(X_train, y_win_train, eval_set=[(X_val, y_win_val)])
        models['lgb_win'] = lgb_win

        logger.info("Training CatBoost win classifier...")
        cb_win = cb.CatBoostClassifier(**cb_params, scale_pos_weight=win_weight)
        cb_win.fit(X_train, y_win_train, eval_set=(X_val, y_win_val), early_stopping_rounds=50)
        models['cb_win'] = cb_win

        # Win ensemble probability
        xgb_win_prob = xgb_win.predict_proba(X_val)[:, 1]
        lgb_win_prob = lgb_win.predict_proba(X_val)[:, 1]
        cb_win_prob = cb_win.predict_proba(X_val)[:, 1]
        ensemble_win_prob = xgb_win_prob * XGB_WEIGHT + lgb_win_prob * LGB_WEIGHT + cb_win_prob * CB_WEIGHT
        win_accuracy = ((ensemble_win_prob > 0.5) == y_win_val).mean()
        logger.info(f"Win classification accuracy (3-model ensemble): {win_accuracy:.4f}")

        # ===== 3. Quinella classification models =====
        quinella_weight = len(y_quinella_train[y_quinella_train == 0]) / max(len(y_quinella_train[y_quinella_train == 1]), 1)

        logger.info("Training XGBoost quinella classifier...")
        xgb_quinella = xgb.XGBClassifier(**base_params, scale_pos_weight=quinella_weight)
        xgb_quinella.fit(X_train, y_quinella_train, eval_set=[(X_val, y_quinella_val)], verbose=False)
        models['xgb_quinella'] = xgb_quinella

        logger.info("Training LightGBM quinella classifier...")
        lgb_quinella = lgb.LGBMClassifier(**base_params, scale_pos_weight=quinella_weight, verbose=-1)
        lgb_quinella.fit(X_train, y_quinella_train, eval_set=[(X_val, y_quinella_val)])
        models['lgb_quinella'] = lgb_quinella

        logger.info("Training CatBoost quinella classifier...")
        cb_quinella = cb.CatBoostClassifier(**cb_params, scale_pos_weight=quinella_weight)
        cb_quinella.fit(X_train, y_quinella_train, eval_set=(X_val, y_quinella_val), early_stopping_rounds=50)
        models['cb_quinella'] = cb_quinella

        # Quinella ensemble probability
        xgb_quinella_prob = xgb_quinella.predict_proba(X_val)[:, 1]
        lgb_quinella_prob = lgb_quinella.predict_proba(X_val)[:, 1]
        cb_quinella_prob = cb_quinella.predict_proba(X_val)[:, 1]
        ensemble_quinella_prob = xgb_quinella_prob * XGB_WEIGHT + lgb_quinella_prob * LGB_WEIGHT + cb_quinella_prob * CB_WEIGHT
        quinella_accuracy = ((ensemble_quinella_prob > 0.5) == y_quinella_val).mean()
        logger.info(f"Quinella classification accuracy (3-model ensemble): {quinella_accuracy:.4f}")

        # ===== 4. Place classification models =====
        place_weight = len(y_place_train[y_place_train == 0]) / max(len(y_place_train[y_place_train == 1]), 1)

        logger.info("Training XGBoost place classifier...")
        xgb_place = xgb.XGBClassifier(**base_params, scale_pos_weight=place_weight)
        xgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)], verbose=False)
        models['xgb_place'] = xgb_place

        logger.info("Training LightGBM place classifier...")
        lgb_place = lgb.LGBMClassifier(**base_params, scale_pos_weight=place_weight, verbose=-1)
        lgb_place.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)])
        models['lgb_place'] = lgb_place

        logger.info("Training CatBoost place classifier...")
        cb_place = cb.CatBoostClassifier(**cb_params, scale_pos_weight=place_weight)
        cb_place.fit(X_train, y_place_train, eval_set=(X_val, y_place_val), early_stopping_rounds=50)
        models['cb_place'] = cb_place

        # Place ensemble probability
        xgb_place_prob = xgb_place.predict_proba(X_val)[:, 1]
        lgb_place_prob = lgb_place.predict_proba(X_val)[:, 1]
        cb_place_prob = cb_place.predict_proba(X_val)[:, 1]
        ensemble_place_prob = xgb_place_prob * XGB_WEIGHT + lgb_place_prob * LGB_WEIGHT + cb_place_prob * CB_WEIGHT
        place_accuracy = ((ensemble_place_prob > 0.5) == y_place_val).mean()
        logger.info(f"Place classification accuracy (3-model ensemble): {place_accuracy:.4f}")

        # ===== 5. Calibration (using calib data) =====
        logger.info("Training calibrators (using calib data)...")

        # Predict on calib data (for calibrator training)
        xgb_win_prob_calib = xgb_win.predict_proba(X_calib)[:, 1]
        lgb_win_prob_calib = lgb_win.predict_proba(X_calib)[:, 1]
        cb_win_prob_calib = cb_win.predict_proba(X_calib)[:, 1]
        ensemble_win_prob_calib = xgb_win_prob_calib * XGB_WEIGHT + lgb_win_prob_calib * LGB_WEIGHT + cb_win_prob_calib * CB_WEIGHT

        xgb_quinella_prob_calib = xgb_quinella.predict_proba(X_calib)[:, 1]
        lgb_quinella_prob_calib = lgb_quinella.predict_proba(X_calib)[:, 1]
        cb_quinella_prob_calib = cb_quinella.predict_proba(X_calib)[:, 1]
        ensemble_quinella_prob_calib = xgb_quinella_prob_calib * XGB_WEIGHT + lgb_quinella_prob_calib * LGB_WEIGHT + cb_quinella_prob_calib * CB_WEIGHT

        xgb_place_prob_calib = xgb_place.predict_proba(X_calib)[:, 1]
        lgb_place_prob_calib = lgb_place.predict_proba(X_calib)[:, 1]
        cb_place_prob_calib = cb_place.predict_proba(X_calib)[:, 1]
        ensemble_place_prob_calib = xgb_place_prob_calib * XGB_WEIGHT + lgb_place_prob_calib * LGB_WEIGHT + cb_place_prob_calib * CB_WEIGHT

        # Train calibrators
        win_calibrator = IsotonicRegression(out_of_bounds='clip')
        win_calibrator.fit(ensemble_win_prob_calib, y_win_calib)
        models['win_calibrator'] = win_calibrator

        quinella_calibrator = IsotonicRegression(out_of_bounds='clip')
        quinella_calibrator.fit(ensemble_quinella_prob_calib, y_quinella_calib)
        models['quinella_calibrator'] = quinella_calibrator

        place_calibrator = IsotonicRegression(out_of_bounds='clip')
        place_calibrator.fit(ensemble_place_prob_calib, y_place_calib)
        models['place_calibrator'] = place_calibrator

        # ===== 6. Final evaluation (test data) =====
        logger.info("Running final evaluation (test data)...")
        from sklearn.metrics import brier_score_loss, roc_auc_score

        # Predict on test data (3-model ensemble)
        xgb_pred_test = xgb_reg.predict(X_test)
        lgb_pred_test = lgb_reg.predict(X_test)
        cb_pred_test = cb_reg.predict(X_test)
        ensemble_pred_test = xgb_pred_test * XGB_WEIGHT + lgb_pred_test * LGB_WEIGHT + cb_pred_test * CB_WEIGHT

        xgb_win_prob_test = xgb_win.predict_proba(X_test)[:, 1]
        lgb_win_prob_test = lgb_win.predict_proba(X_test)[:, 1]
        cb_win_prob_test = cb_win.predict_proba(X_test)[:, 1]
        ensemble_win_prob_test = xgb_win_prob_test * XGB_WEIGHT + lgb_win_prob_test * LGB_WEIGHT + cb_win_prob_test * CB_WEIGHT

        xgb_quinella_prob_test = xgb_quinella.predict_proba(X_test)[:, 1]
        lgb_quinella_prob_test = lgb_quinella.predict_proba(X_test)[:, 1]
        cb_quinella_prob_test = cb_quinella.predict_proba(X_test)[:, 1]
        ensemble_quinella_prob_test = xgb_quinella_prob_test * XGB_WEIGHT + lgb_quinella_prob_test * LGB_WEIGHT + cb_quinella_prob_test * CB_WEIGHT

        xgb_place_prob_test = xgb_place.predict_proba(X_test)[:, 1]
        lgb_place_prob_test = lgb_place.predict_proba(X_test)[:, 1]
        cb_place_prob_test = cb_place.predict_proba(X_test)[:, 1]
        ensemble_place_prob_test = xgb_place_prob_test * XGB_WEIGHT + lgb_place_prob_test * LGB_WEIGHT + cb_place_prob_test * CB_WEIGHT

        # Apply calibration
        calibrated_win_test = win_calibrator.predict(ensemble_win_prob_test)
        calibrated_quinella_test = quinella_calibrator.predict(ensemble_quinella_prob_test)
        calibrated_place_test = place_calibrator.predict(ensemble_place_prob_test)

        # AUC-ROC (before and after calibration)
        win_auc_raw = roc_auc_score(y_win_test, ensemble_win_prob_test)
        win_auc = roc_auc_score(y_win_test, calibrated_win_test)
        quinella_auc_raw = roc_auc_score(y_quinella_test, ensemble_quinella_prob_test)
        quinella_auc = roc_auc_score(y_quinella_test, calibrated_quinella_test)
        place_auc_raw = roc_auc_score(y_place_test, ensemble_place_prob_test)
        place_auc = roc_auc_score(y_place_test, calibrated_place_test)

        # Brier Score (before and after calibration)
        win_brier_raw = brier_score_loss(y_win_test, ensemble_win_prob_test)
        win_brier = brier_score_loss(y_win_test, calibrated_win_test)
        quinella_brier_raw = brier_score_loss(y_quinella_test, ensemble_quinella_prob_test)
        quinella_brier = brier_score_loss(y_quinella_test, calibrated_quinella_test)
        place_brier_raw = brier_score_loss(y_place_test, ensemble_place_prob_test)
        place_brier = brier_score_loss(y_place_test, calibrated_place_test)

        # Top-3 coverage (test data)
        top3_coverage = 0.0
        if 'race_code' in df.columns:
            test_df = df.iloc[calib_end:].copy()
            test_df['pred_score'] = ensemble_pred_test
            test_df['win_prob'] = calibrated_win_test

            top3_hits = 0
            total_races = 0
            for race_code, group in test_df.groupby('race_code'):
                if len(group) < 3:
                    continue
                winner = group[group['target'] == 1]
                if len(winner) == 0:
                    continue
                sorted_group = group.sort_values('pred_score')
                top3_horses = sorted_group.head(3).index.tolist()
                if winner.index[0] in top3_horses:
                    top3_hits += 1
                total_races += 1

            top3_coverage = top3_hits / total_races if total_races > 0 else 0
        else:
            logger.warning("race_code column not found, skipping Top-3 coverage")

        # Log evaluation results
        logger.info("=" * 50)
        logger.info("Model evaluation metrics (test data)")
        logger.info("=" * 50)
        logger.info(f"Win AUC:       {win_auc:.4f} (raw: {win_auc_raw:.4f})  {'Good' if win_auc >= 0.70 else 'Needs improvement'}")
        logger.info(f"Quinella AUC:  {quinella_auc:.4f} (raw: {quinella_auc_raw:.4f})  {'Good' if quinella_auc >= 0.68 else 'Needs improvement'}")
        logger.info(f"Place AUC:     {place_auc:.4f} (raw: {place_auc_raw:.4f})  {'Good' if place_auc >= 0.65 else 'Needs improvement'}")
        logger.info(f"Win Brier:     {win_brier:.4f} (raw: {win_brier_raw:.4f}, improvement: {(win_brier_raw - win_brier) / win_brier_raw * 100:.1f}%)")
        logger.info(f"Quinella Brier: {quinella_brier:.4f} (raw: {quinella_brier_raw:.4f}, improvement: {(quinella_brier_raw - quinella_brier) / quinella_brier_raw * 100:.1f}%)")
        logger.info(f"Place Brier:   {place_brier:.4f} (raw: {place_brier_raw:.4f}, improvement: {(place_brier_raw - place_brier) / place_brier_raw * 100:.1f}%)")
        logger.info(f"Top-3 coverage: {top3_coverage*100:.1f}%  {'Good' if top3_coverage >= 0.55 else 'Needs improvement'}")
        logger.info(f"Calibrated - Win avg: {calibrated_win_test.mean():.4f}, Quinella avg: {calibrated_quinella_test.mean():.4f}, Place avg: {calibrated_place_test.mean():.4f}")
        logger.info("=" * 50)

        # ===== 7. Save calibration statistics to DB =====
        logger.info("Calculating calibration statistics...")
        calibration_stats = {
            'created_at': datetime.now().isoformat(),
            'win_stats': calc_bin_stats(
                ensemble_win_prob_test, y_win_test.values, calibrated_win_test
            ),
            'quinella_stats': calc_bin_stats(
                ensemble_quinella_prob_test, y_quinella_test.values, calibrated_quinella_test
            ),
            'place_stats': calc_bin_stats(
                ensemble_place_prob_test, y_place_test.values, calibrated_place_test
            )
        }

        model_version = f"v4_quinella_ensemble_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        save_calibration_to_db(calibration_stats, model_version)

        # Save temporarily
        temp_model_path = model_dir / "ensemble_model_new.pkl"
        model_data = {
            # Backward compatibility (old format)
            'xgb_model': xgb_reg,
            'lgb_model': lgb_reg,
            'cb_model': cb_reg,  # CatBoost added
            # New model set
            'models': models,
            'feature_names': feature_cols,
            'trained_at': datetime.now().isoformat(),
            'training_samples': len(df),
            'train_size': len(X_train),
            'calib_size': len(X_calib),
            'test_size': len(X_test),
            'validation_rmse': float(rmse),
            'win_accuracy': float(win_accuracy),
            'quinella_accuracy': float(quinella_accuracy),
            'place_accuracy': float(place_accuracy),
            # Evaluation metrics (test data, after calibration)
            'win_auc': float(win_auc),
            'quinella_auc': float(quinella_auc),
            'place_auc': float(place_auc),
            'win_brier': float(win_brier),
            'quinella_brier': float(quinella_brier),
            'place_brier': float(place_brier),
            'top3_coverage': float(top3_coverage),
            'years': years,
            # Ensemble weights
            'ensemble_weights': {
                'xgb': XGB_WEIGHT,
                'lgb': LGB_WEIGHT,
                'cb': CB_WEIGHT
            },
            'version': 'v5_catboost_ensemble'  # CatBoost-enabled version
        }
        joblib.dump(model_data, temp_model_path)

        return {
            'status': 'success',
            'model_path': str(temp_model_path),
            'rmse': float(rmse),
            'win_accuracy': float(win_accuracy),
            'quinella_accuracy': float(quinella_accuracy),
            'place_accuracy': float(place_accuracy),
            'win_auc': float(win_auc),
            'quinella_auc': float(quinella_auc),
            'place_auc': float(place_auc),
            'win_brier': float(win_brier),
            'quinella_brier': float(quinella_brier),
            'top3_coverage': float(top3_coverage),
            'samples': len(df)
        }

    except Exception as e:
        logger.error(f"Training error: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

    finally:
        conn.close()
