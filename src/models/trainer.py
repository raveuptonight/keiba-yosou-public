"""
Model Training Module

Contains training and saving functions for the XGBoost ensemble model:
- Regression model (finishing position prediction)
- Win classifier (1st place binary)
- Place classifier (top-3 binary)
- Isotonic calibration for probability calibration
"""

import logging
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

logger = logging.getLogger(__name__)


def train_model(df: pd.DataFrame, use_gpu: bool = True) -> tuple[dict, dict]:
    """Train ensemble model (regression + classification + calibration).

    Uses a 3-way time-ordered split:
    - train (70%): Model training
    - calib (15%): Calibrator training (prevents data leak)
    - test  (15%): Final evaluation

    Args:
        df: Feature DataFrame with 'target' column (finishing position)
        use_gpu: Whether to use GPU for training

    Returns:
        Tuple of (models_dict, results_dict):
        - models_dict: Contains regressor, win_classifier, place_classifier, calibrators
        - results_dict: Contains metrics, feature names, importance
    """
    logger.info(f"Starting model training: {len(df)} samples")

    # Separate features and target
    target_col = "target"
    exclude_cols = {target_col, "race_code"}  # race_code is object type, exclude
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols].fillna(0)
    y = df[target_col]

    # Classification targets
    y_win = (y == 1).astype(int)  # Win (1st place)
    y_place = (y <= 3).astype(int)  # Place (top 3)

    # ===== 3-way split (time-ordered) =====
    n = len(X)
    train_end = int(n * 0.70)
    calib_end = int(n * 0.85)

    X_train = X.iloc[:train_end]
    X_calib = X.iloc[train_end:calib_end]  # For calibrator
    X_test = X.iloc[calib_end:]  # Final evaluation
    X_val = X_calib  # Use calib data for early stopping

    y_train = y.iloc[:train_end]
    y_calib = y.iloc[train_end:calib_end]
    y.iloc[calib_end:]
    y_val = y_calib

    y_win_train = y_win.iloc[:train_end]
    y_win_calib = y_win.iloc[train_end:calib_end]
    y_win_test = y_win.iloc[calib_end:]
    y_win_val = y_win_calib

    y_place_train = y_place.iloc[:train_end]
    y_place_calib = y_place.iloc[train_end:calib_end]
    y_place_test = y_place.iloc[calib_end:]
    y_place_val = y_place_calib

    logger.info(f"Train: {len(X_train)}, Calib: {len(X_calib)}, Test: {len(X_test)}")

    # Common parameters
    base_params = {
        "n_estimators": 800,
        "max_depth": 7,
        "learning_rate": 0.03,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "n_jobs": -1,
    }

    # GPU settings
    if use_gpu:
        base_params["tree_method"] = "hist"
        base_params["device"] = "cuda"
        logger.info("GPU training mode")
    else:
        logger.info("CPU training mode")

    models = {}

    # ===== 1. Regression Model (Finishing Position) =====
    logger.info("Training regression model...")
    reg_model = xgb.XGBRegressor(
        objective="reg:squarederror", early_stopping_rounds=50, **base_params
    )
    reg_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=100)
    models["regressor"] = reg_model

    # Regression validation
    pred_reg = reg_model.predict(X_val)
    rmse = np.sqrt(np.mean((pred_reg - y_val) ** 2))
    logger.info(f"Regression validation RMSE: {rmse:.4f}")

    # ===== 2. Win Classifier =====
    logger.info("Training win classifier...")
    win_params = base_params.copy()
    win_params["scale_pos_weight"] = len(y_win_train[y_win_train == 0]) / max(
        len(y_win_train[y_win_train == 1]), 1
    )
    win_model = xgb.XGBClassifier(
        objective="binary:logistic", early_stopping_rounds=50, **win_params
    )
    win_model.fit(X_train, y_win_train, eval_set=[(X_val, y_win_val)], verbose=100)
    models["win_classifier"] = win_model

    # Win classifier validation
    pred_win_prob = win_model.predict_proba(X_val)[:, 1]
    win_accuracy = ((pred_win_prob > 0.5) == y_win_val).mean()
    logger.info(f"Win classifier accuracy: {win_accuracy:.4f}")

    # ===== 3. Place Classifier =====
    logger.info("Training place classifier...")
    place_params = base_params.copy()
    place_params["scale_pos_weight"] = len(y_place_train[y_place_train == 0]) / max(
        len(y_place_train[y_place_train == 1]), 1
    )
    place_model = xgb.XGBClassifier(
        objective="binary:logistic", early_stopping_rounds=50, **place_params
    )
    place_model.fit(X_train, y_place_train, eval_set=[(X_val, y_place_val)], verbose=100)
    models["place_classifier"] = place_model

    # Place classifier validation
    pred_place_prob = place_model.predict_proba(X_val)[:, 1]
    place_accuracy = ((pred_place_prob > 0.5) == y_place_val).mean()
    logger.info(f"Place classifier accuracy: {place_accuracy:.4f}")

    # ===== 4. Calibration (Train on calib data) =====
    logger.info("Training calibrators...")

    # Predictions on calib data (for calibrator training)
    pred_win_prob_calib = win_model.predict_proba(X_calib)[:, 1]
    pred_place_prob_calib = place_model.predict_proba(X_calib)[:, 1]

    # Win probability calibration
    win_calibrator = IsotonicRegression(out_of_bounds="clip")
    win_calibrator.fit(pred_win_prob_calib, y_win_calib)
    models["win_calibrator"] = win_calibrator

    # Place probability calibration
    place_calibrator = IsotonicRegression(out_of_bounds="clip")
    place_calibrator.fit(pred_place_prob_calib, y_place_calib)
    models["place_calibrator"] = place_calibrator

    # ===== 5. Final Evaluation (Test data) =====
    logger.info("Final evaluation (test data)...")

    # Test predictions
    pred_win_prob_test = win_model.predict_proba(X_test)[:, 1]
    pred_place_prob_test = place_model.predict_proba(X_test)[:, 1]

    # Apply calibration
    calibrated_win_test = win_calibrator.predict(pred_win_prob_test)
    calibrated_place_test = place_calibrator.predict(pred_place_prob_test)

    # Metrics (before calibration)
    win_auc_raw = roc_auc_score(y_win_test, pred_win_prob_test)
    win_brier_raw = brier_score_loss(y_win_test, pred_win_prob_test)
    place_auc_raw = roc_auc_score(y_place_test, pred_place_prob_test)
    place_brier_raw = brier_score_loss(y_place_test, pred_place_prob_test)

    # Metrics (after calibration)
    win_auc = roc_auc_score(y_win_test, calibrated_win_test)
    win_brier = brier_score_loss(y_win_test, calibrated_win_test)
    place_auc = roc_auc_score(y_place_test, calibrated_place_test)
    place_brier = brier_score_loss(y_place_test, calibrated_place_test)

    logger.info(f"Win AUC: {win_auc:.4f} (raw: {win_auc_raw:.4f})")
    logger.info(
        f"Win Brier: {win_brier:.4f} (raw: {win_brier_raw:.4f}, improvement: {(win_brier_raw - win_brier) / win_brier_raw * 100:.1f}%)"
    )
    logger.info(f"Place AUC: {place_auc:.4f} (raw: {place_auc_raw:.4f})")
    logger.info(
        f"Place Brier: {place_brier:.4f} (raw: {place_brier_raw:.4f}, improvement: {(place_brier_raw - place_brier) / place_brier_raw * 100:.1f}%)"
    )
    logger.info(
        f"Calibrated - Win prob mean: {calibrated_win_test.mean():.4f}, Place prob mean: {calibrated_place_test.mean():.4f}"
    )

    # Feature importance (from regression model)
    importance = dict(
        sorted(zip(feature_cols, reg_model.feature_importances_), key=lambda x: x[1], reverse=True)
    )

    return models, {
        "feature_names": feature_cols,
        "rmse": rmse,
        "win_accuracy": win_accuracy,
        "place_accuracy": place_accuracy,
        "win_auc": win_auc,
        "win_brier": win_brier,
        "place_auc": place_auc,
        "place_brier": place_brier,
        "importance": importance,
        "train_size": len(X_train),
        "calib_size": len(X_calib),
        "test_size": len(X_test),
    }


def save_model(models: dict, results: dict, output_dir: str) -> str:
    """Save trained models to disk.

    Creates a timestamped model file and updates a 'latest' symlink.

    Args:
        models: Dictionary of trained models
        results: Dictionary of training results and metrics
        output_dir: Directory to save models

    Returns:
        Path to the saved model file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = Path(output_dir) / f"xgboost_model_{timestamp}.pkl"
    latest_path = Path(output_dir) / "xgboost_model_latest.pkl"

    model_data = {
        # Backward compatibility: keep 'model' key for regression model
        "model": models["regressor"],
        # New model structure
        "models": models,
        "feature_names": results["feature_names"],
        "feature_importance": results["importance"],
        "trained_at": timestamp,
        "rmse": results["rmse"],
        "win_accuracy": results.get("win_accuracy"),
        "place_accuracy": results.get("place_accuracy"),
        "version": "v2_enhanced",
    }

    joblib.dump(model_data, model_path)
    logger.info(f"Model saved: {model_path}")

    # Update symlink
    if latest_path.exists() or latest_path.is_symlink():
        latest_path.unlink()
    latest_path.symlink_to(model_path.name)

    return str(model_path)
