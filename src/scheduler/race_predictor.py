"""
Race Prediction Scheduler

Automatically executes the day before race day:
1. Verify race entry data
2. Make predictions using ML model
3. Save results and send notifications
"""

import argparse
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor
from src.models.surface_utils import get_model_path_for_surface, get_surface_type
from src.services.prediction.ensemble import ensemble_predict, ensemble_proba

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RacePredictor:
    """Race prediction class (ensemble_model compatible - classification models + calibration + CatBoost)."""

    def __init__(
        self,
        model_path: str = "/app/models/ensemble_model_latest.pkl",
        use_adjustments: bool = True,
    ):
        self.model_path = model_path
        self.model_dir = Path(model_path).parent
        # Regression models
        self.xgb_model = None
        self.lgb_model = None
        self.cb_model = None  # CatBoost added
        # Classification models (new format)
        self.xgb_win = None
        self.lgb_win = None
        self.cb_win = None  # CatBoost added
        self.xgb_place = None
        self.lgb_place = None
        self.cb_place = None  # CatBoost added
        # Calibrators (new format)
        self.win_calibrator = None
        self.place_calibrator = None
        # Features
        self.feature_names: list[str] | None = None
        self.has_classifiers = False
        self.has_catboost = False  # CatBoost availability flag
        # Ensemble weights
        self.ensemble_weights: dict[str, float] | None = None
        # Feature adjustment coefficients
        self.feature_adjustments: dict[str, float] = {}
        # Surface-specific models (loaded lazily on first use)
        self._surface_models: dict[str, dict] = {}
        self._load_model()
        self._load_surface_models()
        if use_adjustments:
            self._load_feature_adjustments()

    def _load_model(self):
        """Load ensemble_model (supports both old and new formats)."""
        try:
            model_data = joblib.load(self.model_path)
            version = model_data.get("version", "")
            models_dict = model_data.get("models", {})

            # Get regression models (supports multiple formats)
            if "xgb_regressor" in models_dict:
                # New format: v2_enhanced_ensemble
                self.xgb_model = models_dict["xgb_regressor"]
                self.lgb_model = models_dict.get("lgb_regressor")
            elif "xgb_model" in model_data:
                # Old format: weekly_retrain_model.py
                self.xgb_model = model_data["xgb_model"]
                self.lgb_model = model_data.get("lgb_model")
            elif "xgboost" in models_dict:
                # Old format: models.xgboost
                self.xgb_model = models_dict.get("xgboost")
                self.lgb_model = models_dict.get("lightgbm")
            else:
                raise ValueError("Invalid model format: ensemble_model required")

            # Get classification models and calibrators (new format only)
            self.xgb_win = models_dict.get("xgb_win")
            self.lgb_win = models_dict.get("lgb_win")
            self.xgb_place = models_dict.get("xgb_place")
            self.lgb_place = models_dict.get("lgb_place")
            self.win_calibrator = models_dict.get("win_calibrator")
            self.place_calibrator = models_dict.get("place_calibrator")

            # Get CatBoost models (v5 and later)
            self.cb_model = models_dict.get("cb_regressor")
            self.cb_win = models_dict.get("cb_win")
            self.cb_place = models_dict.get("cb_place")
            self.has_catboost = self.cb_model is not None

            # Ensemble weights (default: XGB+LGB equal)
            self.ensemble_weights = model_data.get(
                "ensemble_weights", {"xgb": 0.5, "lgb": 0.5, "cb": 0.0}
            )

            self.has_classifiers = self.xgb_win is not None and self.lgb_win is not None

            self.feature_names = model_data.get("feature_names", [])
            logger.info(
                f"ensemble_model loaded: {len(self.feature_names)} features, "
                f"classifiers={'yes' if self.has_classifiers else 'no'}, "
                f"CatBoost={'yes' if self.has_catboost else 'no'}, "
                f"version={version}"
            )
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            raise

    def _load_surface_models(self):
        """Load surface-specific models (turf/dirt) if available."""
        for surface in ("turf", "dirt"):
            path = self.model_dir / f"ensemble_model_{surface}_latest.pkl"
            if path.exists():
                try:
                    self._surface_models[surface] = joblib.load(path)
                    logger.info(f"Surface model loaded: {surface} ({path})")
                except Exception as e:
                    logger.warning(f"Surface model load failed ({surface}): {e}")

    def _get_model_for_surface(self, track_code: str | None) -> dict | None:
        """Return surface-specific model data, or None to use default mixed model."""
        surface = get_surface_type(track_code)
        if surface in self._surface_models:
            logger.info(f"Using {surface} model for track_code={track_code}")
            return self._surface_models[surface]
        return None

    def _load_feature_adjustments(self):
        """Load feature adjustment coefficients from DB."""
        try:
            from src.scheduler.shap_analyzer import ShapAnalyzer

            self.feature_adjustments = ShapAnalyzer.load_adjustments_from_db()
            if self.feature_adjustments:
                adjusted_count = sum(1 for v in self.feature_adjustments.values() if v != 1.0)
                logger.info(f"Feature adjustments applied: {adjusted_count} adjustments")
        except Exception as e:
            logger.warning(f"Feature adjustment loading failed (using defaults): {e}")
            self.feature_adjustments = {}

    def _apply_feature_adjustments(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply adjustment coefficients to features."""
        if not self.feature_adjustments:
            return X

        X_adjusted = X.copy()
        for fname, adjustment in self.feature_adjustments.items():
            if fname in X_adjusted.columns and adjustment != 1.0:
                X_adjusted[fname] = X_adjusted[fname] * adjustment

        return X_adjusted

    def get_upcoming_races(self, target_date: date | None = None) -> list[dict]:
        """Get race entries for the specified date."""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # Get races for target date
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # Check if race entry data exists
            # data_kubun: 1=registration, 2=breaking news, 3=gate order confirmed,
            # 4=race entries, 5=during meeting, 6=pre-confirmation
            cur.execute(
                """
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.kyori, r.track_code, r.grade_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY r.race_code
            """,
                (kaisai_nen, kaisai_gappi),
            )

            races = []
            keibajo_names = {
                "01": "札幌",
                "02": "函館",
                "03": "福島",
                "04": "新潟",
                "05": "東京",
                "06": "中山",
                "07": "中京",
                "08": "京都",
                "09": "阪神",
                "10": "小倉",
            }

            for row in cur.fetchall():
                races.append(
                    {
                        "race_code": row[0],
                        "keibajo_code": row[1],
                        "keibajo_name": keibajo_names.get(row[1], row[1]),
                        "race_bango": row[2],
                        "kyori": row[3],
                        "track_code": row[4],
                        "grade_code": row[5],
                    }
                )

            cur.close()
            return races

        finally:
            conn.close()

    def get_race_entries(self, race_code: str) -> list[dict]:
        """Get race entry information for a race."""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    umaban, wakuban, ketto_toroku_bango, bamei,
                    kishu_code, futan_juryo, barei, seibetsu_code
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY umaban::int
            """,
                (race_code,),
            )

            entries = []
            for row in cur.fetchall():
                entries.append(
                    {
                        "umaban": row[0],
                        "wakuban": row[1],
                        "ketto_toroku_bango": row[2],
                        "bamei": row[3],
                        "kishu_code": row[4],
                        "futan_juryo": row[5],
                        "barei": row[6],
                        "seibetsu_code": row[7],
                    }
                )

            cur.close()
            return entries

        finally:
            conn.close()

    def predict_race(self, race_code: str, compute_shap: bool = False) -> list[dict]:
        """Execute race prediction.

        Args:
            race_code: Race code (16 digits).
            compute_shap: If True, compute SHAP values for each horse (for video export).
        """
        db = get_db()
        conn = db.get_connection()

        try:
            # Use FastFeatureExtractor
            extractor = FastFeatureExtractor(conn)

            # Get race information
            cur = conn.cursor()
            cur.execute(
                """
                SELECT kaisai_nen, keibajo_code, race_bango
                FROM race_shosai
                WHERE race_code = %s
                LIMIT 1
            """,
                (race_code,),
            )
            race_info = cur.fetchone()
            if not race_info:
                return []

            year = int(race_info[0])

            # Feature extraction (single race)
            cur.execute(
                """
                SELECT race_code FROM race_shosai
                WHERE race_code = %s
            """,
                (race_code,),
            )

            # Get race entry data
            cur.execute(
                """
                SELECT
                    race_code, umaban, wakuban, ketto_toroku_bango,
                    seibetsu_code, barei, futan_juryo,
                    blinker_shiyo_kubun, kishu_code, chokyoshi_code,
                    bataiju, zogen_sa, bamei
                FROM umagoto_race_joho
                WHERE race_code = %s
                  AND data_kubun IN ('1', '2', '3', '4', '5', '6')
                ORDER BY umaban::int
            """,
                (race_code,),
            )

            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            entries = [dict(zip(cols, row)) for row in rows]

            if not entries:
                logger.warning(f"No race entry data: {race_code}")
                return []

            # Get race information
            cur.execute(
                """
                SELECT race_code, kaisai_nen, kaisai_gappi, keibajo_code,
                       kyori, track_code, grade_code,
                       shiba_babajotai_code, dirt_babajotai_code
                FROM race_shosai
                WHERE race_code = %s
            """,
                (race_code,),
            )
            race_row = cur.fetchone()
            race_cols = [d[0] for d in cur.description]
            races = [dict(zip(race_cols, race_row))] if race_row else []

            # Get past performance stats
            kettonums = [e["ketto_toroku_bango"] for e in entries if e.get("ketto_toroku_bango")]
            past_stats = extractor._get_past_stats_batch(kettonums)

            # Jockey and trainer cache
            extractor._cache_jockey_trainer_stats(year)

            # Additional data
            jh_pairs = [
                (e.get("kishu_code", ""), e.get("ketto_toroku_bango", ""))
                for e in entries
                if e.get("kishu_code") and e.get("ketto_toroku_bango")
            ]
            jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
            surface_stats = extractor._get_surface_stats_batch(kettonums)
            turn_stats = extractor._get_turn_rates_batch(kettonums)
            for kettonum, stats in turn_stats.items():
                if kettonum in past_stats:
                    past_stats[kettonum]["right_turn_rate"] = stats["right_turn_rate"]
                    past_stats[kettonum]["left_turn_rate"] = stats["left_turn_rate"]
            training_stats = extractor._get_training_stats_batch(kettonums)

            # Generate features
            features_list = []
            for entry in entries:
                # Set dummy value if kakutei_chakujun is missing
                entry["kakutei_chakujun"] = "01"  # Dummy for prediction

                features = extractor._build_features(
                    entry,
                    races,
                    past_stats,
                    jockey_horse_stats=jockey_horse_stats,
                    distance_stats=surface_stats,
                    training_stats=training_stats,
                )
                if features:
                    features["bamei"] = entry.get("bamei", "")
                    features["_wakuban"] = entry.get("wakuban", "0")
                    features["_ketto_toroku_bango"] = entry.get("ketto_toroku_bango", "")
                    features["_kishu_code"] = entry.get("kishu_code", "")
                    features_list.append(features)

            if not features_list:
                return []

            # Prediction (ensemble: weighted average of XGBoost + LightGBM + CatBoost)
            df = pd.DataFrame(features_list)

            # Select model based on surface type
            track_code = race_row[5] if race_row else None
            surface_model_data = self._get_model_for_surface(track_code)

            if surface_model_data is not None:
                # Use surface-specific model
                m = surface_model_data.get("models", {})
                m_feature_names = surface_model_data.get("feature_names", self.feature_names)
                m_weights = surface_model_data.get(
                    "ensemble_weights", {"xgb": 0.5, "lgb": 0.5, "cb": 0.0}
                )
                m_xgb = m.get("xgb_regressor") or surface_model_data.get("xgb_model")
                m_lgb = m.get("lgb_regressor") or surface_model_data.get("lgb_model")
                m_cb = m.get("cb_regressor") or surface_model_data.get("cb_model")
                m_xgb_win = m.get("xgb_win")
                m_lgb_win = m.get("lgb_win")
                m_cb_win = m.get("cb_win")
                m_xgb_place = m.get("xgb_place")
                m_lgb_place = m.get("lgb_place")
                m_cb_place = m.get("cb_place")
                m_win_calibrator = m.get("win_calibrator")
                m_place_calibrator = m.get("place_calibrator")
                m_has_classifiers = m_xgb_win is not None and m_lgb_win is not None
                m_has_catboost = m_cb is not None
            else:
                # Use default mixed model
                m_feature_names = self.feature_names
                m_weights = self.ensemble_weights
                m_xgb = self.xgb_model
                m_lgb = self.lgb_model
                m_cb = self.cb_model
                m_xgb_win = self.xgb_win
                m_lgb_win = self.lgb_win
                m_cb_win = self.cb_win
                m_xgb_place = self.xgb_place
                m_lgb_place = self.lgb_place
                m_cb_place = self.cb_place
                m_win_calibrator = self.win_calibrator
                m_place_calibrator = self.place_calibrator
                m_has_classifiers = self.has_classifiers
                m_has_catboost = self.has_catboost

            X = df[m_feature_names].fillna(0)

            # Apply feature adjustment coefficients
            X = self._apply_feature_adjustments(X)

            # Model availability assertions for type checking
            assert m_xgb is not None, "XGBoost model not loaded"
            assert m_lgb is not None, "LightGBM model not loaded"
            assert m_weights is not None, "Ensemble weights not loaded"

            # Regression prediction (finishing position score)
            rank_scores = ensemble_predict(
                m_xgb, m_lgb, X, m_weights,
                cb_model=m_cb if m_has_catboost else None,
            )

            # Probability prediction using classification models
            if m_has_classifiers:
                win_probs = ensemble_proba(
                    m_xgb_win, m_lgb_win, X, m_weights,
                    cb_clf=m_cb_win if m_has_catboost else None,
                    calibrator=m_win_calibrator,
                )
                place_probs = ensemble_proba(
                    m_xgb_place, m_lgb_place, X, m_weights,
                    cb_clf=m_cb_place if m_has_catboost else None,
                    calibrator=m_place_calibrator,
                )
            else:
                # Old format: estimate probability from score
                scores_exp = np.exp(-rank_scores)
                win_probs = scores_exp / scores_exp.sum()
                place_probs = None

            # SHAP value computation (for video export, TOP horses)
            shap_data: dict[str, list[dict]] = {}
            if compute_shap:
                try:
                    import shap

                    from src.services.prediction.feature_names import FEATURE_DISPLAY_NAMES

                    explainer = shap.TreeExplainer(m_xgb)
                    shap_values = explainer.shap_values(X)

                    for i in range(len(features_list)):
                        umaban = str(features_list[i]["umaban"])
                        horse_shap = shap_values[i]
                        top_indices = np.argsort(np.abs(horse_shap))[::-1][:10]
                        shap_data[umaban] = [
                            {
                                "feature": m_feature_names[idx],
                                "shap_value": round(float(abs(horse_shap[idx])), 4),
                                "feature_value": round(float(X.iloc[i, idx]), 4),
                                "direction": "positive" if horse_shap[idx] > 0 else "negative",
                                "display_name": FEATURE_DISPLAY_NAMES.get(
                                    m_feature_names[idx], m_feature_names[idx]
                                ),
                            }
                            for idx in top_indices
                        ]
                except Exception as e:
                    logger.warning(f"SHAP computation failed (skipped): {e}")

            # Format results
            results = []
            for i, score in enumerate(rank_scores):
                result = {
                    "umaban": features_list[i]["umaban"],
                    "wakuban": features_list[i].get("_wakuban", "0"),
                    "bamei": features_list[i].get("bamei", ""),
                    "ketto_toroku_bango": features_list[i].get("_ketto_toroku_bango", ""),
                    "kishu_code": features_list[i].get("_kishu_code", ""),
                    "pred_score": float(score),
                    "win_prob": float(win_probs[i]),
                    "pred_rank": 0,  # Set later
                    "shap_top_features": shap_data.get(str(features_list[i]["umaban"]), []),
                }
                if place_probs is not None:
                    result["place_prob"] = float(place_probs[i])
                results.append(result)

            # Set prediction rank (lower score = higher rank)
            results.sort(key=lambda x: x["pred_score"])
            for i, r in enumerate(results):
                r["pred_rank"] = i + 1

            # Assign marks
            if compute_shap:
                from src.services.prediction.feature_names import assign_marks

                assign_marks(results)

            # Sort back by horse number
            results.sort(key=lambda x: int(x["umaban"]))

            cur.close()
            return results

        finally:
            conn.close()

    def run_predictions(self, target_date: date | None = None) -> dict[str, Any]:
        """Execute predictions for all races on the specified date."""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        logger.info(f"Executing predictions: {target_date}")

        # Check race entries
        races = self.get_upcoming_races(target_date)

        if not races:
            logger.info(f"No race entry data for {target_date}")
            return {"date": str(target_date), "status": "no_data", "races": []}

        logger.info(f"Verified race entries for {len(races)} races")

        results: dict[str, Any] = {
            "date": str(target_date),
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "races": [],
        }

        for race in races:
            race_code = race["race_code"]
            logger.info(f"Predicting: {race['keibajo_name']} {race['race_bango']}R")

            try:
                predictions = self.predict_race(race_code)

                if predictions:
                    # Extract TOP3
                    top3 = sorted(predictions, key=lambda x: x["pred_rank"])[:3]

                    race_result = {
                        "race_code": race_code,
                        "keibajo": race["keibajo_name"],
                        "race_number": race["race_bango"],
                        "kyori": race["kyori"],
                        "predictions": predictions,
                        "top3": [
                            {
                                "rank": p["pred_rank"],
                                "umaban": p["umaban"],
                                "bamei": p["bamei"],
                                "win_prob": p.get("win_prob", 0),
                                "place_prob": p.get("place_prob"),
                            }
                            for p in top3
                        ],
                    }
                    results["races"].append(race_result)
                    top3_str = [
                        f"{p['umaban']}番{p['bamei']}({p.get('win_prob', 0)*100:.1f}%)"
                        for p in top3
                    ]
                    logger.info(f"  TOP3: {top3_str}")

            except Exception as e:
                logger.error(f"Prediction failed {race_code}: {e}")

        return results


def print_predictions(results: dict):
    """Display prediction results."""
    print("\n" + "=" * 60)
    print(f"【{results['date']} レース予想】")
    print("=" * 60)

    if results["status"] == "no_data":
        print("出馬表データがありません")
        return

    for race in results["races"]:
        print(f"\n■ {race['keibajo']} {race['race_number']}R ({race['kyori']}m)")
        print("-" * 40)
        print("予想順位:")
        for p in race["top3"]:
            win_pct = p.get("win_prob", 0) * 100
            place_prob = p.get("place_prob")
            if place_prob is not None:
                place_pct = place_prob * 100
                print(
                    f"  {p['rank']}位: {p['umaban']}番 {p['bamei']} (勝率{win_pct:.1f}%, 複勝{place_pct:.1f}%)"
                )
            else:
                print(f"  {p['rank']}位: {p['umaban']}番 {p['bamei']} (勝率{win_pct:.1f}%)")

    print("\n" + "=" * 60)
    print(f"生成日時: {results['generated_at']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Race prediction scheduler")
    parser.add_argument("--date", "-d", help="Target date (YYYY-MM-DD)")
    parser.add_argument("--tomorrow", "-t", action="store_true", help="Predict tomorrow's races")
    parser.add_argument("--model", "-m", default="/app/models/ensemble_model_latest.pkl")

    args = parser.parse_args()

    # Determine target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.tomorrow:
        target_date = date.today() + timedelta(days=1)
    else:
        target_date = date.today() + timedelta(days=1)

    print(f"Target date: {target_date}")

    # Execute predictions
    predictor = RacePredictor(args.model)
    results = predictor.run_predictions(target_date)

    # Display results
    print_predictions(results)


if __name__ == "__main__":
    main()
