"""
FastFeatureExtractor - High-speed batch feature extraction for horse racing data.

This is the main orchestrator class that coordinates all feature extraction
operations using batch database queries for efficient processing.
"""

import logging
from typing import Any

import pandas as pd

from . import db_queries, pedigree, performance, venue
from .utils import (
    calc_days_since_last,
    calc_speed_index,
    calc_style_pace_compatibility,
    determine_class,
    determine_style,
    encode_sex,
    get_distance_category,
    get_interval_category,
    safe_float,
    safe_int,
    stable_hash,
)

logger = logging.getLogger(__name__)


class FastFeatureExtractor:
    """High-speed batch feature extraction for horse racing predictions.

    Uses batch database queries to efficiently extract features for large
    amounts of historical race data. Implements data leak prevention by
    excluding the current race from historical statistics.

    Attributes:
        VENUE_CODES: Mapping of venue codes to names
        SMALL_TRACK_VENUES: Set of venue codes with tighter turns
    """

    # Venue code -> name mapping
    VENUE_CODES = {
        "01": "sapporo",
        "02": "hakodate",
        "03": "fukushima",
        "04": "niigata",
        "05": "tokyo",
        "06": "nakayama",
        "07": "chukyo",
        "08": "kyoto",
        "09": "hanshin",
        "10": "kokura",
    }
    # Small track venues (tighter turns)
    SMALL_TRACK_VENUES = {"01", "02", "03", "06", "10"}

    def __init__(self, conn):
        """Initialize extractor with database connection.

        Args:
            conn: PostgreSQL database connection
        """
        self.conn = conn
        self._jockey_cache = {}
        self._trainer_cache = {}
        self._pedigree_cache = {}
        self._sire_stats_cache = {}

    def extract_year_data(self, year: int, max_races: int = 5000) -> pd.DataFrame:
        """Extract one year of training data in batch mode.

        Orchestrates the entire feature extraction pipeline:
        1. Fetch race list
        2. Fetch all horse entries
        3. Gather all historical statistics (with leak prevention)
        4. Build feature vectors

        Args:
            year: Target year
            max_races: Maximum number of races to process

        Returns:
            DataFrame with features and target (finishing position)
        """
        logger.info(f"Fetching data for year {year}...")

        # 1. Get race list
        races = db_queries.get_races(self.conn, year, max_races)
        logger.info(f"  Target races: {len(races)}")

        if not races:
            return pd.DataFrame()

        race_codes = [r["race_code"] for r in races]

        # 2. Batch fetch all horse entries
        entries = db_queries.get_all_entries(self.conn, race_codes)
        logger.info(f"  Entries: {len(entries)}")

        # 3. Batch fetch past performance (last 10 races) - exclude current race to prevent data leak
        kettonums = list({e["ketto_toroku_bango"] for e in entries if e.get("ketto_toroku_bango")})
        past_stats = db_queries.get_past_stats_batch(self.conn, kettonums, entries=entries)
        logger.info(f"  Past stats: {len(past_stats)} horses")

        # 4. Cache jockey/trainer stats
        self._jockey_cache, self._trainer_cache = db_queries.cache_jockey_trainer_stats(
            self.conn, year
        )

        # 5. Batch fetch additional data
        # Jockey-horse combinations
        jh_pairs = [
            (e.get("kishu_code", ""), e.get("ketto_toroku_bango", ""))
            for e in entries
            if e.get("kishu_code") and e.get("ketto_toroku_bango")
        ]
        jockey_horse_stats = db_queries.get_jockey_horse_combo_batch(self.conn, jh_pairs)
        logger.info(f"  Jockey-horse combos: {len(jockey_horse_stats)}")

        # Turf/dirt stats - exclude current race to prevent data leak
        surface_stats = performance.get_surface_stats_batch(self.conn, kettonums, entries=entries)
        logger.info(f"  Turf/dirt stats: {len(surface_stats)}")

        # Left/right turn stats
        turn_stats = performance.get_turn_rates_batch(self.conn, kettonums)
        # Merge turn stats into past_stats
        for kettonum, stats in turn_stats.items():
            if kettonum in past_stats:
                past_stats[kettonum]["right_turn_rate"] = stats["right_turn_rate"]
                past_stats[kettonum]["left_turn_rate"] = stats["left_turn_rate"]
                past_stats[kettonum]["right_turn_runs"] = stats.get("right_turn_runs", 0)
                past_stats[kettonum]["left_turn_runs"] = stats.get("left_turn_runs", 0)

        # Training data
        training_stats = db_queries.get_training_stats_batch(self.conn, kettonums)
        logger.info(f"  Training data: {len(training_stats)}")

        # Track condition stats - exclude current race to prevent data leak
        baba_stats = performance.get_baba_stats_batch(self.conn, kettonums, races, entries=entries)
        logger.info(f"  Track condition stats: {len(baba_stats)}")

        # Interval stats - exclude current race to prevent data leak
        interval_stats = performance.get_interval_stats_batch(self.conn, kettonums, entries=entries)
        logger.info(f"  Interval stats: {len(interval_stats)}")

        # ===== Extended features (v2) =====
        # Pedigree info
        pedigree_info = pedigree.get_pedigree_batch(self.conn, kettonums)
        logger.info(f"  Pedigree info: {len(pedigree_info)}")

        # Venue-specific stats - exclude current race to prevent data leak
        venue_stats = venue.get_venue_stats_batch(self.conn, kettonums, entries=entries)
        logger.info(f"  Venue stats: {len(venue_stats)}")

        # Previous race details - exclude current race to prevent data leak
        zenso_info = venue.get_zenso_batch(self.conn, kettonums, race_codes, entries=entries)
        logger.info(f"  Zenso details: {len(zenso_info)}")

        # Jockey recent performance
        jockey_codes = list({e.get("kishu_code", "") for e in entries if e.get("kishu_code")})
        jockey_recent = venue.get_jockey_recent_batch(self.conn, jockey_codes, year)
        logger.info(f"  Jockey recent: {len(jockey_recent)}")

        # Sire stats (turf/dirt)
        sire_ids = [p.get("sire_id", "") for p in pedigree_info.values() if p.get("sire_id")]
        sire_stats_turf = pedigree.get_sire_stats_batch(self.conn, sire_ids, year, is_turf=True)
        sire_stats_dirt = pedigree.get_sire_stats_batch(self.conn, sire_ids, year, is_turf=False)
        logger.info(f"  Sire stats (turf): {len(sire_stats_turf)}, (dirt): {len(sire_stats_dirt)}")

        # Sire maiden race stats
        sire_maiden_stats = pedigree.get_sire_maiden_stats_batch(self.conn, sire_ids, year)
        logger.info(f"  Sire maiden stats: {len(sire_maiden_stats)}")

        # Jockey maiden race stats
        jockey_maiden_stats = venue.get_jockey_maiden_stats_batch(self.conn, jockey_codes, year)
        logger.info(f"  Jockey maiden stats: {len(jockey_maiden_stats)}")

        # 6. Group entries by race and calculate pace predictions
        entries_by_race = {}
        for entry in entries:
            rc = entry["race_code"]
            if rc not in entries_by_race:
                entries_by_race[rc] = []
            entries_by_race[rc].append(entry)

        pace_predictions = {}
        for rc, race_entries in entries_by_race.items():
            pace_predictions[rc] = self._calc_pace_prediction(race_entries, past_stats)

        # 7. Build feature vectors
        features_list = []
        for entry in entries:
            features = self._build_features(
                entry,
                races,
                past_stats,
                jockey_horse_stats=jockey_horse_stats,
                distance_stats=surface_stats,
                baba_stats=baba_stats,
                training_stats=training_stats,
                interval_stats=interval_stats,
                pace_predictions=pace_predictions,
                entries_by_race=entries_by_race,
                # Extended feature data
                pedigree_info=pedigree_info,
                venue_stats=venue_stats,
                zenso_info=zenso_info,
                jockey_recent=jockey_recent,
                sire_stats_turf=sire_stats_turf,
                sire_stats_dirt=sire_stats_dirt,
                sire_maiden_stats=sire_maiden_stats,
                jockey_maiden_stats=jockey_maiden_stats,
                year=year,
            )
            if features:
                features_list.append(features)

        df = pd.DataFrame(features_list)
        logger.info(f"  Feature generation complete: {len(df)} samples")

        return df

    def _cache_jockey_trainer_stats(self, year: int):
        """Cache jockey and trainer statistics (wrapper for backward compatibility)."""
        self._jockey_cache, self._trainer_cache = db_queries.cache_jockey_trainer_stats(
            self.conn, year
        )
        logger.info(
            f"  Jockey cache: {len(self._jockey_cache)}, Trainer cache: {len(self._trainer_cache)}"
        )

    # ===== Wrapper methods for backward compatibility =====
    # These delegate to the modular query functions

    def _get_races(self, year: int, max_races: int) -> list[dict]:
        """Get race list."""
        return db_queries.get_races(self.conn, year, max_races)

    def _get_all_entries(self, race_codes: list[str]) -> list[dict]:
        """Batch fetch horse entry data."""
        return db_queries.get_all_entries(self.conn, race_codes)

    def _get_past_stats_batch(
        self, kettonums: list[str], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch past performance stats."""
        return db_queries.get_past_stats_batch(self.conn, kettonums, entries)

    def _get_jockey_horse_combo_batch(self, pairs: list) -> dict[str, dict]:
        """Batch fetch jockey-horse combination stats."""
        return db_queries.get_jockey_horse_combo_batch(self.conn, pairs)

    def _get_training_stats_batch(self, kettonums: list[str]) -> dict[str, dict]:
        """Batch fetch training data."""
        return db_queries.get_training_stats_batch(self.conn, kettonums)

    def _get_surface_stats_batch(
        self, kettonums: list[str], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch turf/dirt stats."""
        return performance.get_surface_stats_batch(self.conn, kettonums, entries)

    def _get_turn_rates_batch(self, kettonums: list[str]) -> dict[str, dict]:
        """Batch fetch turn direction stats."""
        return performance.get_turn_rates_batch(self.conn, kettonums)

    def _get_baba_stats_batch(
        self, kettonums: list[str], races: list[dict], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch track condition stats."""
        return performance.get_baba_stats_batch(self.conn, kettonums, races, entries)

    def _get_interval_stats_batch(
        self, kettonums: list[str], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch interval stats."""
        return performance.get_interval_stats_batch(self.conn, kettonums, entries)

    def _get_pedigree_batch(self, kettonums: list[str]) -> dict[str, dict]:
        """Batch fetch pedigree info."""
        return pedigree.get_pedigree_batch(self.conn, kettonums)

    def _get_sire_stats_batch(
        self, sire_ids: list[str], year: int, is_turf: bool = True
    ) -> dict[str, dict]:
        """Batch fetch sire stats."""
        return pedigree.get_sire_stats_batch(self.conn, sire_ids, year, is_turf)

    def _get_sire_maiden_stats_batch(self, sire_ids: list[str], year: int) -> dict[str, dict]:
        """Batch fetch sire maiden stats."""
        return pedigree.get_sire_maiden_stats_batch(self.conn, sire_ids, year)

    def _get_venue_stats_batch(
        self, kettonums: list[str], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch venue stats."""
        return venue.get_venue_stats_batch(self.conn, kettonums, entries)

    def _get_zenso_batch(
        self, kettonums: list[str], race_codes: list[str], entries: list[dict] = None
    ) -> dict[str, dict]:
        """Batch fetch zenso info."""
        return venue.get_zenso_batch(self.conn, kettonums, race_codes, entries)

    def _get_jockey_recent_batch(self, jockey_codes: list[str], year: int) -> dict[str, dict]:
        """Batch fetch jockey recent stats."""
        return venue.get_jockey_recent_batch(self.conn, jockey_codes, year)

    def _get_jockey_maiden_stats_batch(self, jockey_codes: list[str], year: int) -> dict[str, dict]:
        """Batch fetch jockey maiden stats."""
        return venue.get_jockey_maiden_stats_batch(self.conn, jockey_codes, year)

    # ===== Utility method wrappers =====

    def _safe_int(self, val, default: int = 0) -> int:
        """Safely convert to int."""
        return safe_int(val, default)

    def _safe_float(self, val, default: float = 0.0) -> float:
        """Safely convert to float."""
        return safe_float(val, default)

    def _encode_sex(self, sex_code: str) -> int:
        """Encode sex code."""
        return encode_sex(sex_code)

    def _calc_speed_index(self, avg_time) -> float:
        """Calculate speed index."""
        return calc_speed_index(avg_time)

    def _determine_style(self, avg_corner3: float) -> int:
        """Determine running style."""
        return determine_style(avg_corner3)

    def _determine_class(self, grade_code: str) -> int:
        """Determine class rank."""
        return determine_class(grade_code)

    def _get_distance_category(self, distance: int) -> str:
        """Get distance category."""
        return get_distance_category(distance)

    def _get_interval_category(self, days: int) -> str:
        """Get interval category."""
        return get_interval_category(days)

    def _calc_days_since_last(
        self, last_race_date: str, current_year: str, current_gappi: str
    ) -> int:
        """Calculate days since last race."""
        return calc_days_since_last(last_race_date, current_year, current_gappi)

    def _calc_style_pace_compatibility(self, running_style: int, pace_type: int) -> float:
        """Calculate style-pace compatibility."""
        return calc_style_pace_compatibility(running_style, pace_type)

    def _grade_to_rank(self, grade_code: str) -> int:
        """Convert grade to rank."""
        return determine_class(grade_code)

    def _stable_hash(self, s: str, mod: int = 10000) -> int:
        """Generate stable hash."""
        return stable_hash(s, mod)

    def _calc_pace_prediction(
        self, entries: list[dict], past_stats: dict[str, dict]
    ) -> dict[str, Any]:
        """Calculate pace prediction for a race.

        Estimates the race pace based on running styles of participating horses.

        Args:
            entries: List of horse entries in the race
            past_stats: Dictionary of past performance stats

        Returns:
            Dictionary with pace prediction info:
            - pace_maker_count: Number of front runners (nige)
            - senkou_count: Number of stalkers
            - sashi_count: Number of closers
            - pace_type: 1=Slow, 2=Middle, 3=High
        """
        pace_makers = 0
        senkou_count = 0
        sashi_count = 0

        for entry in entries:
            kettonum = entry.get("ketto_toroku_bango", "")
            past = past_stats.get(kettonum, {})
            style = determine_style(past.get("avg_corner3", 8))
            if style == 1:  # Nige
                pace_makers += 1
            elif style == 2:  # Senkou
                senkou_count += 1
            elif style == 3:  # Sashi
                sashi_count += 1

        # Pace prediction: 2+ nige = High pace, 0 nige = Slow pace
        if pace_makers >= 2:
            pace_type = 3  # High pace
        elif pace_makers == 0:
            pace_type = 1  # Slow pace
        else:
            pace_type = 2  # Middle pace

        return {
            "pace_maker_count": pace_makers,
            "senkou_count": senkou_count,
            "sashi_count": sashi_count,
            "pace_type": pace_type,
        }

    def _build_features(
        self,
        entry: dict,
        races: list[dict],
        past_stats: dict[str, dict],
        jockey_horse_stats: dict[str, dict] = None,
        distance_stats: dict[str, dict] = None,
        baba_stats: dict[str, dict] = None,
        training_stats: dict[str, dict] = None,
        interval_stats: dict[str, dict] = None,
        pace_predictions: dict[str, dict] = None,
        entries_by_race: dict[str, list[dict]] = None,
        # Extended feature data
        pedigree_info: dict[str, dict] = None,
        venue_stats: dict[str, dict] = None,
        zenso_info: dict[str, dict] = None,
        jockey_recent: dict[str, dict] = None,
        sire_stats_turf: dict[str, dict] = None,
        sire_stats_dirt: dict[str, dict] = None,
        sire_maiden_stats: dict[str, dict] = None,
        jockey_maiden_stats: dict[str, dict] = None,
        year: int = None,
    ) -> dict | None:
        """Build feature vector for a single entry.

        This is the core feature engineering method that constructs all features
        for a horse-race combination.

        Args:
            entry: Horse entry data
            races: List of all races
            past_stats: Past performance statistics
            jockey_horse_stats: Jockey-horse combo stats
            distance_stats: Turf/dirt stats
            baba_stats: Track condition stats
            training_stats: Training data
            interval_stats: Rest interval stats
            pace_predictions: Race pace predictions
            entries_by_race: Entries grouped by race
            pedigree_info: Pedigree data
            venue_stats: Venue-specific stats
            zenso_info: Previous race details
            jockey_recent: Jockey recent form
            sire_stats_turf: Sire turf stats
            sire_stats_dirt: Sire dirt stats
            sire_maiden_stats: Sire maiden race stats
            jockey_maiden_stats: Jockey maiden race stats
            year: Target year

        Returns:
            Feature dictionary or None if invalid entry
        """
        # Import the feature builder module
        from .feature_builder import build_features

        return build_features(
            entry=entry,
            races=races,
            past_stats=past_stats,
            jockey_cache=self._jockey_cache,
            trainer_cache=self._trainer_cache,
            jockey_horse_stats=jockey_horse_stats,
            distance_stats=distance_stats,
            baba_stats=baba_stats,
            training_stats=training_stats,
            interval_stats=interval_stats,
            pace_predictions=pace_predictions,
            entries_by_race=entries_by_race,
            pedigree_info=pedigree_info,
            venue_stats=venue_stats,
            zenso_info=zenso_info,
            jockey_recent=jockey_recent,
            sire_stats_turf=sire_stats_turf,
            sire_stats_dirt=sire_stats_dirt,
            sire_maiden_stats=sire_maiden_stats,
            jockey_maiden_stats=jockey_maiden_stats,
            year=year,
            small_track_venues=self.SMALL_TRACK_VENUES,
        )
