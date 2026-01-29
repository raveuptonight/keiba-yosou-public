"""
Real Feature Extractor Module

Extract features from JRA-VAN mykeibadb database for machine learning predictions.

Enhanced features (v2):
- Pedigree (sire/broodmare sire offspring statistics)
- Detailed last race info (finish, popularity, last 3F rank, corner positions)
- Venue-specific statistics
- Enhanced pace prediction
- Trend features (finish trends, jockey form)
- Season/timing features
"""

import logging
from typing import TYPE_CHECKING, Any

from src.features.enhanced_features import EnhancedFeatureExtractor

if TYPE_CHECKING:
    from src.features.daily_bias import DailyBiasResult
from src.features.extractors.calculators import (
    calc_avg_time_diff,
    calc_class_change,
    calc_corner_avg,
    calc_course_fit,
    calc_days_since_last,
    calc_distance_change,
    calc_distance_fit,
    calc_last3f_avg,
    calc_last3f_rank_avg,
    calc_pace_prediction,
    calc_place_rate,
    calc_speed_index_avg,
    calc_speed_index_max,
    calc_speed_index_recent,
    calc_style_pace_compatibility,
    calc_surface_rate,
    calc_turn_rate,
    calc_waku_bias,
    calc_win_rate,
    count_wins,
    determine_class_rank,
    determine_running_style,
    encode_sex,
    get_best_finish,
    get_default_enhanced_features,
    get_interval_category,
    is_jockey_changed,
    safe_float,
    safe_int,
)
from src.features.extractors.db_queries import (
    get_baba_stats,
    get_detailed_training,
    get_distance_stats,
    get_interval_stats,
    get_jockey_horse_combo,
    get_jockey_stats,
    get_past_races,
    get_race_entries,
    get_race_info,
    get_trainer_stats,
    get_training_data,
)

logger = logging.getLogger(__name__)


class RealFeatureExtractor:
    """Extract features from JRA-VAN database."""

    def __init__(self, db_connection):
        """
        Initialize extractor.

        Args:
            db_connection: psycopg2 connection object
        """
        self.conn = db_connection
        self._cache = {}
        self._enhanced_extractor = EnhancedFeatureExtractor(db_connection)

    def extract_features_for_race(
        self, race_code: str, data_kubun: str = "7"
    ) -> list[dict[str, Any]]:
        """
        Extract features for all horses in a race.

        Args:
            race_code: Race code (16 digits)
            data_kubun: Data classification (7=confirmed)

        Returns:
            List of feature dictionaries for each horse
        """
        # Get race entries
        entries = get_race_entries(self.conn, race_code, data_kubun, self._cache)
        if not entries:
            logger.warning(f"No entries found for race: {race_code}")
            return []

        # Get race info
        race_info = get_race_info(self.conn, race_code, data_kubun)

        # Pre-calculate running styles for pace prediction
        running_styles = {}
        for entry in entries:
            kettonum = entry.get("ketto_toroku_bango", "")
            past_races = get_past_races(self.conn, kettonum, race_code, self._cache)
            running_styles[kettonum] = determine_running_style(past_races)

        # Pre-calculate pace prediction
        pace_info = calc_pace_prediction(entries, race_info, get_past_races, self.conn, self._cache)

        features_list = []
        for entry in entries:
            features = self._extract_horse_features(
                entry, race_info, entries, pace_info, running_styles
            )
            features_list.append(features)

        return features_list

    def _extract_horse_features(
        self,
        entry: dict,
        race_info: dict,
        all_entries: list[dict],
        pace_info: dict = None,
        running_styles: dict[str, int] = None,
    ) -> dict[str, Any]:
        """Extract features for a single horse."""
        features = {}
        kettonum = entry.get("ketto_toroku_bango", "")

        if running_styles is None:
            running_styles = {}

        # ===== Basic info =====
        features["umaban"] = safe_int(entry.get("umaban"), 0)
        features["wakuban"] = safe_int(entry.get("wakuban"), 0)
        features["age"] = safe_int(entry.get("barei"), 4)
        features["sex"] = encode_sex(entry.get("seibetsu_code", ""))
        features["kinryo"] = safe_float(entry.get("futan_juryo"), 55.0) / 10.0

        # ===== Horse weight =====
        features["horse_weight"] = safe_int(entry.get("bataiju"), 480)
        features["weight_diff"] = safe_int(entry.get("zogen_sa"), 0)

        # ===== Blinker =====
        blinker = entry.get("blinker_shiyo_kubun", "0")
        features["blinker"] = 1 if blinker == "1" else 0

        # Note: Odds and popularity intentionally excluded (predict on ability, not market)

        # ===== Past race statistics =====
        past_races = get_past_races(
            self.conn, kettonum, race_info.get("race_code", ""), self._cache
        )

        # Speed index
        features["speed_index_avg"] = calc_speed_index_avg(past_races)
        features["speed_index_max"] = calc_speed_index_max(past_races)
        features["speed_index_recent"] = calc_speed_index_recent(past_races)

        # Last 3F
        features["last3f_time_avg"] = calc_last3f_avg(past_races)
        features["last3f_rank_avg"] = calc_last3f_rank_avg(past_races)

        # Running style
        features["running_style"] = determine_running_style(past_races)
        features["position_avg_3f"] = calc_corner_avg(past_races, "corner3_juni")
        features["position_avg_4f"] = calc_corner_avg(past_races, "corner4_juni")

        # Win/place rates
        features["win_rate"] = calc_win_rate(past_races)
        features["place_rate"] = calc_place_rate(past_races)
        features["win_count"] = count_wins(past_races)

        # Days since last race
        features["days_since_last_race"] = calc_days_since_last(past_races, race_info)

        # ===== Jockey stats =====
        jockey_code = entry.get("kishu_code", "")
        jockey_stats = get_jockey_stats(self.conn, jockey_code, self._cache)
        features["jockey_win_rate"] = jockey_stats.get("win_rate", 0.08)
        features["jockey_place_rate"] = jockey_stats.get("place_rate", 0.25)

        # ===== Trainer stats =====
        trainer_code = entry.get("chokyoshi_code", "")
        trainer_stats = get_trainer_stats(self.conn, trainer_code, self._cache)
        features["trainer_win_rate"] = trainer_stats.get("win_rate", 0.08)
        features["trainer_place_rate"] = trainer_stats.get("place_rate", 0.25)

        # ===== Jockey-horse combination stats =====
        jockey_horse_stats = get_jockey_horse_combo(self.conn, jockey_code, kettonum, self._cache)
        features["jockey_horse_runs"] = jockey_horse_stats.get("runs", 0)
        features["jockey_horse_wins"] = jockey_horse_stats.get("wins", 0)
        features["jockey_change"] = 1 if is_jockey_changed(past_races, jockey_code) else 0

        # ===== Training data =====
        training_data = get_training_data(
            self.conn, kettonum, race_info.get("race_code", ""), self._cache
        )
        features["training_score"] = training_data.get("score", 50.0)
        features["training_time_4f"] = training_data.get("time_4f", 52.0)
        features["training_count"] = training_data.get("count", 0)

        # ===== Distance change =====
        features["distance_change"] = calc_distance_change(past_races, race_info)

        # ===== Surface fitness =====
        track_code = race_info.get("track_code", "")
        features["is_turf"] = 1 if track_code.startswith("1") else 0
        features["turf_win_rate"] = calc_surface_rate(past_races, is_turf=True)
        features["dirt_win_rate"] = calc_surface_rate(past_races, is_turf=False)

        # ===== Class change =====
        features["class_change"] = calc_class_change(past_races, race_info)

        # ===== Time difference and best finish =====
        features["avg_time_diff"] = calc_avg_time_diff(past_races)
        features["best_finish"] = get_best_finish(past_races)

        # ===== Course and distance fit =====
        features["course_fit_score"] = calc_course_fit(
            past_races, race_info.get("keibajo_code", "")
        )
        features["distance_fit_score"] = calc_distance_fit(
            past_races, safe_int(race_info.get("kyori"), 1600)
        )

        # ===== Class =====
        features["class_rank"] = determine_class_rank(race_info)

        # ===== Field size =====
        features["field_size"] = len(all_entries)

        # ===== Post position bias =====
        features["waku_bias"] = calc_waku_bias(features["wakuban"], race_info)

        # ===== Distance category stats =====
        distance_stats = get_distance_stats(
            self.conn,
            kettonum,
            race_info.get("race_code", ""),
            safe_int(race_info.get("kyori"), 1600),
            race_info.get("track_code", ""),
            self._cache,
        )
        features["distance_cat_win_rate"] = distance_stats.get("win_rate", 0.0)
        features["distance_cat_place_rate"] = distance_stats.get("place_rate", 0.0)
        features["distance_cat_runs"] = distance_stats.get("runs", 0)

        # ===== Track condition stats =====
        track_code = race_info.get("track_code", "")
        is_turf = track_code.startswith("1") if track_code else True
        baba_code = (
            race_info.get("shiba_babajotai_code", "1")
            if is_turf
            else race_info.get("dirt_babajotai_code", "1")
        )

        baba_stats = get_baba_stats(
            self.conn, kettonum, race_info.get("race_code", ""), track_code, baba_code, self._cache
        )
        features["baba_win_rate"] = baba_stats.get("win_rate", 0.0)
        features["baba_place_rate"] = baba_stats.get("place_rate", 0.0)
        features["baba_runs"] = baba_stats.get("runs", 0)

        # Track condition encoding (1=good, 2=slightly heavy, 3=heavy, 4=bad)
        features["baba_condition"] = safe_int(baba_code, 1)

        # ===== Detailed training data =====
        detailed_training = get_detailed_training(
            self.conn, kettonum, race_info.get("race_code", ""), self._cache
        )
        features["training_time_3f"] = detailed_training.get("time_3f", 38.0)
        features["training_lap_1f"] = detailed_training.get("lap_1f", 12.5)
        features["training_days_before"] = detailed_training.get("days_before", 7)

        # ===== Turn direction stats =====
        features["right_turn_rate"] = calc_turn_rate(past_races, is_right=True)
        features["left_turn_rate"] = calc_turn_rate(past_races, is_right=False)

        # ===== Interval category stats =====
        days_since = features["days_since_last_race"]
        interval_cat = get_interval_category(days_since)
        interval_stats = get_interval_stats(self.conn, kettonum, interval_cat, self._cache)
        features["interval_win_rate"] = interval_stats.get("win_rate", features["win_rate"])
        features["interval_place_rate"] = interval_stats.get("place_rate", features["place_rate"])
        features["interval_runs"] = interval_stats.get("runs", 0)

        # Interval category encoding (1=consecutive, 2=1week, 3=2weeks, 4=3weeks, 5=4+weeks)
        interval_cat_map = {"rentou": 1, "week1": 2, "week2": 3, "week3": 4, "week4plus": 5}
        features["interval_category"] = interval_cat_map.get(interval_cat, 5)

        # ===== Pace prediction =====
        if pace_info:
            features["pace_maker_count"] = pace_info.get("pace_maker_count", 1)
            features["senkou_count"] = pace_info.get("senkou_count", 3)
            features["sashi_count"] = pace_info.get("sashi_count", 5)
            features["pace_type"] = pace_info.get("pace_type", 2)
        else:
            features["pace_maker_count"] = 1
            features["senkou_count"] = 3
            features["sashi_count"] = 5
            features["pace_type"] = 2

        # ===== Running style x pace compatibility =====
        running_style = features["running_style"]
        pace_type = features["pace_type"]
        features["style_pace_compatibility"] = calc_style_pace_compatibility(
            running_style, pace_type
        )

        # ===== Enhanced features (v2) =====
        try:
            # Current popularity (unknown at prediction time)
            current_ninki = safe_int(entry.get("tansho_ninkijun"), None)

            enhanced_features = self._enhanced_extractor.extract_all_enhanced_features(
                entry=entry,
                race_info=race_info,
                all_entries=all_entries,
                running_styles=running_styles,
                current_ninki=current_ninki,
            )
            features.update(enhanced_features)
        except Exception as e:
            logger.warning(f"Failed to extract enhanced features: {e}")
            # Continue with default values if enhanced features fail
            features.update(get_default_enhanced_features())

        return features

    def clear_cache(self):
        """Clear internal cache."""
        self._cache = {}
        if self._enhanced_extractor:
            self._enhanced_extractor.clear_cache()

    def inject_bias_features(
        self, features_list: list[dict[str, Any]], bias_result: "DailyBiasResult", venue_code: str
    ) -> list[dict[str, Any]]:
        """
        Inject bias features into feature dictionaries.

        Args:
            features_list: List of feature dictionaries
            bias_result: Daily bias analysis result
            venue_code: Venue code

        Returns:
            Feature list with bias features added
        """

        if bias_result is None:
            # Set default values if no bias data
            for features in features_list:
                features["bias_waku"] = 0.0
                features["bias_waku_adjusted"] = 0.0
                features["bias_pace"] = 0.0
                features["bias_pace_front"] = 0.0
                features["bias_jockey_today_win"] = 0.0
                features["bias_jockey_today_top3"] = 0.0
            return features_list

        # Get venue bias
        venue_bias = bias_result.venue_biases.get(venue_code)

        for features in features_list:
            wakuban = features.get("wakuban", 0)
            running_style = features.get("running_style", 2)

            # Post position bias
            if venue_bias:
                # Apply inner post advantage for inner posts
                if 1 <= wakuban <= 4:
                    features["bias_waku"] = venue_bias.waku_bias
                    features["bias_waku_adjusted"] = venue_bias.inner_waku_win_rate
                else:
                    # Apply outer post advantage for outer posts
                    features["bias_waku"] = -venue_bias.waku_bias
                    features["bias_waku_adjusted"] = venue_bias.outer_waku_win_rate

                # Running style bias
                features["bias_pace"] = venue_bias.pace_bias
                if running_style in (1, 2):  # Front-runner, stalker
                    features["bias_pace_front"] = venue_bias.zenso_win_rate
                else:  # Closer, deep closer
                    features["bias_pace_front"] = venue_bias.koshi_win_rate
            else:
                features["bias_waku"] = 0.0
                features["bias_waku_adjusted"] = 0.0
                features["bias_pace"] = 0.0
                features["bias_pace_front"] = 0.0

            # Jockey daily performance
            # Note: Jockey code needs to be obtained from entry, not available in features
            features["bias_jockey_today_win"] = 0.0
            features["bias_jockey_today_top3"] = 0.0

        return features_list

    def inject_jockey_bias(
        self, features: dict[str, Any], bias_result: "DailyBiasResult", kishu_code: str
    ) -> dict[str, Any]:
        """
        Inject jockey bias for individual horse.

        Args:
            features: Horse feature dictionary
            bias_result: Daily bias analysis result
            kishu_code: Jockey code

        Returns:
            Features with jockey bias added
        """
        if bias_result is None or not kishu_code:
            features["bias_jockey_today_win"] = 0.0
            features["bias_jockey_today_top3"] = 0.0
            return features

        jockey_perf = bias_result.jockey_performances.get(kishu_code)
        if jockey_perf:
            features["bias_jockey_today_win"] = jockey_perf.win_rate
            features["bias_jockey_today_top3"] = jockey_perf.top3_rate
        else:
            features["bias_jockey_today_win"] = 0.0
            features["bias_jockey_today_top3"] = 0.0

        return features
