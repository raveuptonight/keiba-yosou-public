"""
Ensemble Calibrator

Combines Isotonic Regression and Platt Scaling (LogisticRegression)
for more robust probability calibration.
"""

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class EnsembleCalibrator:
    """Ensemble of Isotonic Regression and Platt Scaling calibrators.

    Args:
        isotonic: Trained IsotonicRegression instance.
        platt: Trained LogisticRegression instance (Platt scaling).
        iso_weight: Weight for Isotonic predictions (default 0.6).
    """

    def __init__(
        self,
        isotonic: IsotonicRegression,
        platt: LogisticRegression,
        iso_weight: float = 0.6,
    ):
        self.isotonic = isotonic
        self.platt = platt
        self.iso_weight = iso_weight
        self.platt_weight = 1.0 - iso_weight

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return calibrated probabilities.

        Args:
            X: Raw ensemble probabilities (1-D array).

        Returns:
            Calibrated probabilities (1-D array), clipped to [0, 1].
        """
        iso_pred = self.isotonic.predict(X)
        platt_pred = self.platt.predict_proba(X.reshape(-1, 1))[:, 1]
        blended = iso_pred * self.iso_weight + platt_pred * self.platt_weight
        return np.clip(blended, 0.0, 1.0)

    def __repr__(self) -> str:
        return (
            f"EnsembleCalibrator(iso_weight={self.iso_weight}, "
            f"platt_weight={self.platt_weight})"
        )
