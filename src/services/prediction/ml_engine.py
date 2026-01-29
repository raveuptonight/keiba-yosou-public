"""
ML Engine Module

Core machine learning prediction functions for horse racing.
Handles feature extraction for future races and ensemble model predictions.
"""

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ML model path (ensemble_model only)
ML_MODEL_PATH = Path("/app/models/ensemble_model_latest.pkl")
if not ML_MODEL_PATH.exists():
    # Local development path
    ML_MODEL_PATH = Path(__file__).parent.parent.parent.parent / "models" / "ensemble_model_latest.pkl"


def extract_future_race_features(conn, race_id: str, extractor, year: int):
    """
    Extract features for a future race.

    For races without finalized data, extract features from registered horse information.

    Args:
        conn: DB connection
        race_id: Race ID
        extractor: FastFeatureExtractor instance
        year: Target year

    Returns:
        pd.DataFrame: Feature DataFrame
    """
    import pandas as pd

    cur = conn.cursor()

    # 1. Get race information (registered data)
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

    # 2. Get horse entry data
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

    # Filter out horse_number 0 (scratched or registration-only entries)
    valid_entries = []
    for e in entries:
        umaban = e.get('umaban', '00')
        try:
            if int(umaban) >= 1:
                valid_entries.append(e)
        except (ValueError, TypeError):
            pass
    entries = valid_entries

    logger.info(f"Future race entries: {len(entries)} horses")

    # 3. Get past performance stats
    kettonums = [e['ketto_toroku_bango'] for e in entries if e.get('ketto_toroku_bango')]
    past_stats = extractor._get_past_stats_batch(kettonums)

    # 4. Cache jockey/trainer stats
    extractor._cache_jockey_trainer_stats(year)

    # 5. Get additional data
    jh_pairs = [(e.get('kishu_code', ''), e.get('ketto_toroku_bango', ''))
                for e in entries if e.get('kishu_code') and e.get('ketto_toroku_bango')]
    jockey_horse_stats = extractor._get_jockey_horse_combo_batch(jh_pairs)
    surface_stats = extractor._get_surface_stats_batch(kettonums)
    turn_stats = extractor._get_turn_rates_batch(kettonums)
    for kettonum, stats in turn_stats.items():
        if kettonum in past_stats:
            past_stats[kettonum]['right_turn_rate'] = stats['right_turn_rate']
            past_stats[kettonum]['left_turn_rate'] = stats['left_turn_rate']
            past_stats[kettonum]['right_turn_runs'] = stats.get('right_turn_runs', 0)
            past_stats[kettonum]['left_turn_runs'] = stats.get('left_turn_runs', 0)
    training_stats = extractor._get_training_stats_batch(kettonums)
    # Venue stats (for prediction, use all data - don't pass entries)
    venue_stats = extractor._get_venue_stats_batch(kettonums)

    # 5.5 Get pedigree/sire/jockey maiden stats
    pedigree_info = extractor._get_pedigree_batch(kettonums)
    race_codes = [e['race_code'] for e in entries]
    zenso_info = extractor._get_zenso_batch(kettonums, race_codes, entries)
    jockey_codes = list(set(e.get('kishu_code', '') for e in entries if e.get('kishu_code')))
    jockey_recent = extractor._get_jockey_recent_batch(jockey_codes, year)

    # Sire stats
    sire_ids = [p.get('sire_id', '') for p in pedigree_info.values() if p.get('sire_id')]
    sire_stats_turf = extractor._get_sire_stats_batch(sire_ids, year, is_turf=True)
    sire_stats_dirt = extractor._get_sire_stats_batch(sire_ids, year, is_turf=False)

    # Maiden race specific stats
    sire_maiden_stats = extractor._get_sire_maiden_stats_batch(sire_ids, year)
    jockey_maiden_stats = extractor._get_jockey_maiden_stats_batch(jockey_codes, year)
    logger.info(f"Maiden stats: sire={len(sire_maiden_stats)}, jockey={len(jockey_maiden_stats)}")

    # 6. Build features (with dummy finishing position)
    features_list = []
    for entry in entries:
        entry['kakutei_chakujun'] = '01'  # Dummy for prediction

        features = extractor._build_features(
            entry, races, past_stats,
            jockey_horse_stats=jockey_horse_stats,
            distance_stats=surface_stats,
            training_stats=training_stats,
            venue_stats=venue_stats,
            pedigree_info=pedigree_info,
            zenso_info=zenso_info,
            jockey_recent=jockey_recent,
            sire_stats_turf=sire_stats_turf,
            sire_stats_dirt=sire_stats_dirt,
            sire_maiden_stats=sire_maiden_stats,
            jockey_maiden_stats=jockey_maiden_stats,
            year=year
        )
        if features:
            features['bamei'] = entry.get('bamei', '')
            features_list.append(features)

    cur.close()

    if not features_list:
        return pd.DataFrame()

    return pd.DataFrame(features_list)


def compute_ml_predictions(
    race_id: str,
    horses: list[dict],
    bias_date: str | None = None,
    is_final: bool = False
) -> dict[str, Any]:
    """
    Compute ML predictions for a race.

    Args:
        race_id: Race ID (16 digits)
        horses: List of horse entries
        bias_date: Bias application date (YYYY-MM-DD format, auto-detect if omitted)
        is_final: Whether this is the final prediction (True applies track condition)

    Returns:
        Dict[horse_number, {"rank_score": float, "win_probability": float}]
    """
    logger.info(f"Computing ML predictions: race_id={race_id}, horses={len(horses)}")

    try:
        import joblib
        import pandas as pd

        from src.db.connection import get_db
        from src.models.feature_extractor import FastFeatureExtractor
        from src.services.prediction.bias_adjustment import (
            apply_bias_to_scores,
            load_bias_for_date,
        )
        from src.services.prediction.track_adjustment import (
            apply_track_condition_adjustment,
            get_current_track_condition,
            get_horse_baba_performance,
        )

        # Load model
        if not ML_MODEL_PATH.exists():
            logger.warning(f"ML model not found: {ML_MODEL_PATH}")
            return {}

        model_data = joblib.load(ML_MODEL_PATH)

        # Get ensemble_model keys (multiple formats supported)
        # Format 1: v2_enhanced_ensemble (new: classification model + calibration)
        # Format 2: xgb_model, lgb_model (weekly retrain format)
        # Format 3: models.xgboost, models.lightgbm (legacy)
        models_dict = model_data.get('models', {})
        version = model_data.get('version', '')

        # Get regression models
        if 'xgb_regressor' in models_dict:
            xgb_model = models_dict['xgb_regressor']
            lgb_model = models_dict.get('lgb_regressor')
        elif 'xgb_model' in model_data:
            xgb_model = model_data['xgb_model']
            lgb_model = model_data.get('lgb_model')
        elif 'xgboost' in models_dict:
            xgb_model = models_dict.get('xgboost')
            lgb_model = models_dict.get('lightgbm')
        else:
            logger.error("Invalid model format: ensemble_model required")
            return {}

        # Get classification models and calibrators (new format only)
        xgb_win = models_dict.get('xgb_win')
        lgb_win = models_dict.get('lgb_win')
        xgb_quinella = models_dict.get('xgb_quinella')
        lgb_quinella = models_dict.get('lgb_quinella')
        xgb_place = models_dict.get('xgb_place')
        lgb_place = models_dict.get('lgb_place')
        win_calibrator = models_dict.get('win_calibrator')
        quinella_calibrator = models_dict.get('quinella_calibrator')
        place_calibrator = models_dict.get('place_calibrator')

        # Get CatBoost models (v5+)
        cb_model = models_dict.get('cb_regressor')
        cb_win = models_dict.get('cb_win')
        cb_quinella = models_dict.get('cb_quinella')
        cb_place = models_dict.get('cb_place')
        has_catboost = cb_model is not None

        # Ensemble weights (default: XGB+LGB equal)
        ensemble_weights = model_data.get('ensemble_weights', {
            'xgb': 0.5, 'lgb': 0.5, 'cb': 0.0
        })

        has_classifiers = xgb_win is not None and lgb_win is not None
        has_quinella = xgb_quinella is not None and lgb_quinella is not None

        feature_names = model_data.get('feature_names', [])
        logger.info(f"Ensemble model loaded: {ML_MODEL_PATH}, features={len(feature_names)}, "
                   f"CatBoost={'yes' if has_catboost else 'no'}")

        # Get DB connection
        db = get_db()
        conn = db.get_connection()

        if not conn:
            logger.warning("DB connection failed for ML prediction")
            return {}

        try:
            # Feature extraction (using same FastFeatureExtractor as training)
            extractor = FastFeatureExtractor(conn)
            year = int(race_id[:4])
            logger.info(f"Extracting features for race {race_id}...")

            # First try to get confirmed data (past races)
            df = extractor.extract_year_data(year, max_races=10000)
            race_df = df[df['race_code'] == race_id].copy() if len(df) > 0 else pd.DataFrame()

            # If no confirmed data, extract features directly for future race
            if len(race_df) == 0:
                logger.info(f"No confirmed data, extracting features for future race: {race_id}")
                race_df = extract_future_race_features(conn, race_id, extractor, year)

            if len(race_df) == 0:
                logger.warning(f"No data for race: {race_id}")
                return {}

            logger.info(f"Found {len(race_df)} horses for race {race_id}")

            # Extract only features expected by model
            available_features = [f for f in feature_names if f in race_df.columns]
            missing_features = [f for f in feature_names if f not in race_df.columns]
            if missing_features:
                logger.warning(f"Missing features: {missing_features[:5]}...")
                for f in missing_features:
                    race_df[f] = 0

            X = race_df[feature_names].fillna(0)
            features_list = race_df.to_dict('records')

            # ML prediction (ensemble_model: XGBoost + LightGBM + CatBoost)
            if not xgb_model or not lgb_model:
                logger.error("Ensemble model requires both XGBoost and LightGBM")
                return {}

            # Regression prediction (rank scores)
            xgb_pred = xgb_model.predict(X)
            lgb_pred = lgb_model.predict(X)

            # 3-model ensemble if CatBoost available
            if has_catboost:
                cb_pred = cb_model.predict(X)
                w = ensemble_weights
                rank_scores = (xgb_pred * w['xgb'] + lgb_pred * w['lgb'] + cb_pred * w['cb'])
            else:
                # Backward compatibility: XGB+LGB only
                w = ensemble_weights
                xgb_w = w.get('xgb', 0.5)
                lgb_w = w.get('lgb', 0.5)
                total = xgb_w + lgb_w
                rank_scores = (xgb_pred * xgb_w + lgb_pred * lgb_w) / total

            # If classification models exist, predict probabilities directly
            if has_classifiers:
                logger.info("Using classification models for probability prediction")
                n_horses = len(X)

                # Win probability
                xgb_win_prob = xgb_win.predict_proba(X)[:, 1]
                lgb_win_prob = lgb_win.predict_proba(X)[:, 1]

                if has_catboost and cb_win is not None:
                    cb_win_prob = cb_win.predict_proba(X)[:, 1]
                    w = ensemble_weights
                    win_probs = (xgb_win_prob * w['xgb'] + lgb_win_prob * w['lgb'] + cb_win_prob * w['cb'])
                else:
                    w = ensemble_weights
                    xgb_w = w.get('xgb', 0.5)
                    lgb_w = w.get('lgb', 0.5)
                    total = xgb_w + lgb_w
                    win_probs = (xgb_win_prob * xgb_w + lgb_win_prob * lgb_w) / total

                # Quinella probability (use if available, otherwise estimate)
                if has_quinella:
                    xgb_quinella_prob = xgb_quinella.predict_proba(X)[:, 1]
                    lgb_quinella_prob = lgb_quinella.predict_proba(X)[:, 1]

                    if has_catboost and cb_quinella is not None:
                        cb_quinella_prob = cb_quinella.predict_proba(X)[:, 1]
                        w = ensemble_weights
                        quinella_probs = (xgb_quinella_prob * w['xgb'] + lgb_quinella_prob * w['lgb'] + cb_quinella_prob * w['cb'])
                    else:
                        w = ensemble_weights
                        xgb_w = w.get('xgb', 0.5)
                        lgb_w = w.get('lgb', 0.5)
                        total = xgb_w + lgb_w
                        quinella_probs = (xgb_quinella_prob * xgb_w + lgb_quinella_prob * lgb_w) / total
                else:
                    # Legacy compatibility: estimate from win and place rates
                    quinella_probs = None

                # Place probability
                xgb_place_prob = xgb_place.predict_proba(X)[:, 1]
                lgb_place_prob = lgb_place.predict_proba(X)[:, 1]

                if has_catboost and cb_place is not None:
                    cb_place_prob = cb_place.predict_proba(X)[:, 1]
                    w = ensemble_weights
                    place_probs = (xgb_place_prob * w['xgb'] + lgb_place_prob * w['lgb'] + cb_place_prob * w['cb'])
                else:
                    w = ensemble_weights
                    xgb_w = w.get('xgb', 0.5)
                    lgb_w = w.get('lgb', 0.5)
                    total = xgb_w + lgb_w
                    place_probs = (xgb_place_prob * xgb_w + lgb_place_prob * lgb_w) / total

                # Apply calibration (built-in model calibrators)
                if win_calibrator is not None:
                    win_probs = win_calibrator.predict(win_probs)
                    logger.info("Applied win_calibrator")
                if quinella_calibrator is not None and quinella_probs is not None:
                    quinella_probs = quinella_calibrator.predict(quinella_probs)
                    logger.info("Applied quinella_calibrator")
                if place_calibrator is not None:
                    place_probs = place_calibrator.predict(place_probs)
                    logger.info("Applied place_calibrator")

                # Normalize probabilities (each independently)
                # Win probability: sum to 1.0 (only one winner)
                win_sum = win_probs.sum()
                if win_sum > 0:
                    win_probs = win_probs / win_sum

                # Quinella probability: sum to 2.0 (2 horses in top 2)
                if quinella_probs is not None:
                    expected_quinella_sum = min(2.0, n_horses)
                    quinella_sum = quinella_probs.sum()
                    if quinella_sum > 0:
                        quinella_probs = quinella_probs * expected_quinella_sum / quinella_sum

                # Place probability: sum to 3.0 (3 horses in top 3)
                expected_place_sum = min(3.0, n_horses)
                place_sum = place_probs.sum()
                if place_sum > 0:
                    place_probs = place_probs * expected_place_sum / place_sum
            else:
                # Legacy format: convert scores to probabilities (softmax-style)
                logger.info("Using regression scores for probability (legacy mode)")
                scores_exp = np.exp(-rank_scores)
                win_probs = scores_exp / scores_exp.sum()
                quinella_probs = None
                place_probs = None

            # Convert results to dictionary format
            ml_scores = {}
            for i, features in enumerate(features_list):
                horse_num = features.get('umaban', i + 1)
                score_data = {
                    "rank_score": float(rank_scores[i]),
                    "win_probability": float(min(1.0, win_probs[i]))  # Clip
                }
                if quinella_probs is not None:
                    # Clip individual probability to not exceed 1.0
                    score_data["quinella_probability"] = float(min(1.0, quinella_probs[i]))
                if place_probs is not None:
                    # Clip individual probability to not exceed 1.0
                    score_data["place_probability"] = float(min(1.0, place_probs[i]))
                ml_scores[str(horse_num)] = score_data

            logger.info(f"ML predictions computed: {len(ml_scores)} horses")

            # Debug: Check ML scores
            sample_scores = list(ml_scores.items())[:3]
            for umaban, data in sample_scores:
                logger.info(f"DEBUG ml_score[{umaban}]: win={data.get('win_probability', 0)*100:.4f}%")

            # Apply bias
            # Priority:
            # 1. Use bias_date parameter if provided
            # 2. Use KEIBA_BIAS_DATE environment variable if set
            # 3. Auto-detect: for Sunday races, use previous Saturday's bias
            from datetime import date, timedelta

            # Determine bias date from parameter or environment
            bias_date_str = bias_date or os.environ.get('KEIBA_BIAS_DATE')

            if bias_date_str:
                # Use specified bias
                bias_data = load_bias_for_date(bias_date_str)
                if bias_data:
                    logger.info(f"Applying bias: {bias_date_str}")
                    ml_scores = apply_bias_to_scores(
                        ml_scores, race_id, horses, bias_data
                    )
                else:
                    logger.warning(f"Bias file not found: {bias_date_str}")
            else:
                # Auto-detect mode (Sunday race uses previous Saturday)
                race_year = int(race_id[:4])
                race_month = int(race_id[6:8])
                race_day = int(race_id[8:10])
                try:
                    race_date = date(race_year, race_month, race_day)
                    if race_date.weekday() == 6:  # Sunday
                        saturday_date = race_date - timedelta(days=1)
                        bias_data = load_bias_for_date(saturday_date.isoformat())
                        if bias_data:
                            logger.info(f"Auto-detected bias applied: {saturday_date}")
                            ml_scores = apply_bias_to_scores(
                                ml_scores, race_id, horses, bias_data
                            )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Bias application skipped: {e}")

            # Apply track condition adjustment for final predictions
            if is_final:
                logger.info("Final prediction: applying track condition adjustment")
                track_condition = get_current_track_condition(conn, race_id)
                if track_condition and track_condition.get('condition', 0) > 0:
                    # Get horse registration numbers
                    kettonums = [h.get('ketto_toroku_bango', '') for h in horses if h.get('ketto_toroku_bango')]
                    if kettonums:
                        baba_performance = get_horse_baba_performance(
                            conn,
                            kettonums,
                            track_condition['track_type'],
                            track_condition['condition']
                        )
                        if baba_performance:
                            ml_scores = apply_track_condition_adjustment(
                                ml_scores, horses, track_condition, baba_performance
                            )
                else:
                    logger.info("No track condition data, skipping adjustment")

            return ml_scores

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"ML prediction failed: {e}")
        return {}
