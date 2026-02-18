"""
Ensemble Prediction Utilities

Shared functions for ensemble model prediction (regression + classification).
Used by race_predictor, ml_engine, and evaluator.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def ensemble_predict(xgb_model, lgb_model, X, weights, cb_model=None) -> np.ndarray:
    """Ensemble regression prediction.

    Args:
        xgb_model: XGBoost regressor
        lgb_model: LightGBM regressor
        X: Feature matrix
        weights: Ensemble weights dict {"xgb": float, "lgb": float, "cb": float}
        cb_model: Optional CatBoost regressor

    Returns:
        Weighted average of regression predictions (rank_scores)
    """
    xgb_pred = xgb_model.predict(X)
    lgb_pred = lgb_model.predict(X)

    if cb_model is not None:
        cb_pred = cb_model.predict(X)
        return xgb_pred * weights["xgb"] + lgb_pred * weights["lgb"] + cb_pred * weights["cb"]

    # 2-model: normalize weights (e.g., xgb=0.4, lgb=0.3 -> divide by 0.7)
    xgb_w = weights.get("xgb", 0.5)
    lgb_w = weights.get("lgb", 0.5)
    total = xgb_w + lgb_w
    return (xgb_pred * xgb_w + lgb_pred * lgb_w) / total


def ensemble_proba(xgb_clf, lgb_clf, X, weights, cb_clf=None, calibrator=None) -> np.ndarray:
    """Ensemble classification probability with optional calibration.

    Args:
        xgb_clf: XGBoost classifier
        lgb_clf: LightGBM classifier
        X: Feature matrix
        weights: Ensemble weights dict {"xgb": float, "lgb": float, "cb": float}
        cb_clf: Optional CatBoost classifier
        calibrator: Optional calibrator (e.g., IsotonicRegression)

    Returns:
        Calibrated ensemble probability array
    """
    xgb_prob = xgb_clf.predict_proba(X)[:, 1]
    lgb_prob = lgb_clf.predict_proba(X)[:, 1]

    if cb_clf is not None:
        cb_prob = cb_clf.predict_proba(X)[:, 1]
        raw_prob = xgb_prob * weights["xgb"] + lgb_prob * weights["lgb"] + cb_prob * weights["cb"]
    else:
        # 2-model: normalize weights
        xgb_w = weights.get("xgb", 0.5)
        lgb_w = weights.get("lgb", 0.5)
        total = xgb_w + lgb_w
        raw_prob = (xgb_prob * xgb_w + lgb_prob * lgb_w) / total

    if calibrator is not None:
        try:
            calibrated = calibrator.predict(raw_prob)
            return np.clip(calibrated, 0, 1)
        except Exception as e:
            logger.warning(f"Calibrator failed, using raw probabilities: {e}")
    return raw_prob


def ensemble_proba_with_ci(
    xgb_clf, lgb_clf, X, weights, cb_clf=None, calibrator=None
) -> tuple[np.ndarray, np.ndarray]:
    """Ensemble classification probability with confidence interval.

    Uses weighted standard deviation across models as uncertainty measure.

    Args:
        xgb_clf: XGBoost classifier
        lgb_clf: LightGBM classifier
        X: Feature matrix
        weights: Ensemble weights dict {"xgb": float, "lgb": float, "cb": float}
        cb_clf: Optional CatBoost classifier
        calibrator: Optional calibrator

    Returns:
        Tuple of (mean_probability, std_probability)
    """
    xgb_prob = xgb_clf.predict_proba(X)[:, 1]
    lgb_prob = lgb_clf.predict_proba(X)[:, 1]

    if cb_clf is not None:
        cb_prob = cb_clf.predict_proba(X)[:, 1]
        probs = np.stack([xgb_prob, lgb_prob, cb_prob])
        w = np.array([weights["xgb"], weights["lgb"], weights["cb"]])
    else:
        probs = np.stack([xgb_prob, lgb_prob])
        xgb_w = weights.get("xgb", 0.5)
        lgb_w = weights.get("lgb", 0.5)
        w = np.array([xgb_w, lgb_w])
        w = w / w.sum()

    mean_prob = np.average(probs, axis=0, weights=w)
    diff = probs - mean_prob
    std_prob = np.sqrt(np.average(diff ** 2, axis=0, weights=w))

    if calibrator is not None:
        try:
            mean_prob = np.clip(calibrator.predict(mean_prob), 0, 1)
        except Exception as e:
            logger.warning(f"Calibrator failed in CI path, using raw probabilities: {e}")

    return mean_prob, std_prob
