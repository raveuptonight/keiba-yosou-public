"""
Enhanced Feature Extraction Module

Additional features:
1. Pedigree (sire/broodmare sire statistics)
2. Detailed last race info (finish, popularity, last 3F, corner positions)
3. Venue-specific statistics
4. Enhanced pace prediction
5. Trend features (finish trends, jockey form)
6. Season/timing features
"""

import logging
from datetime import date
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EnhancedFeatureExtractor:
    """Enhanced feature extractor class."""

    # Venue code to name mapping
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

    # Small/tight courses (inner course focus)
    SMALL_TRACK_VENUES = {
        "01",
        "02",
        "03",
        "06",
        "10",
    }  # Sapporo, Hakodate, Fukushima, Nakayama, Kokura

    # Right-handed / Left-handed courses
    RIGHT_TURN_VENUES = {"01", "02", "03", "06", "09", "10"}
    LEFT_TURN_VENUES = {"04", "05", "07", "08"}

    def __init__(self, db_connection):
        self.conn = db_connection
        self._cache = {}
        self._sire_stats_cache = {}

    # ========================================
    # 1. Pedigree features
    # ========================================

    def get_pedigree_info(self, kettonum: str) -> dict[str, Any]:
        """Get pedigree info (sire ID, broodmare sire ID)."""
        if not kettonum:
            return {"sire_id": "", "broodmare_sire_id": ""}

        cache_key = f"pedigree_{kettonum}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                ketto1_hanshoku_toroku_bango as sire_id,
                ketto3_hanshoku_toroku_bango as broodmare_sire_id,
                ketto1_bamei as sire_name,
                ketto3_bamei as broodmare_sire_name
            FROM kyosoba_master2
            WHERE ketto_toroku_bango = %s
            ORDER BY data_sakusei_nengappi DESC
            LIMIT 1
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            row = cur.fetchone()
            cur.close()

            if row:
                result = {
                    "sire_id": row[0] or "",
                    "broodmare_sire_id": row[1] or "",
                    "sire_name": row[2] or "",
                    "broodmare_sire_name": row[3] or "",
                }
            else:
                result = {
                    "sire_id": "",
                    "broodmare_sire_id": "",
                    "sire_name": "",
                    "broodmare_sire_name": "",
                }

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get pedigree info: {e}")
            self.conn.rollback()
            return {
                "sire_id": "",
                "broodmare_sire_id": "",
                "sire_name": "",
                "broodmare_sire_name": "",
            }

    def get_sire_stats(
        self,
        sire_id: str,
        distance: int = None,
        baba_code: str = None,
        venue_code: str = None,
        is_turf: bool = True,
    ) -> dict[str, float]:
        """
        Get sire offspring statistics.

        Args:
            sire_id: Sire breeding registration number
            distance: Distance (m) - filters ±200m range when specified
            baba_code: Track condition code (1=good, 2=slightly heavy, 3=heavy, 4=bad)
            venue_code: Venue code
            is_turf: Whether it's a turf course

        Returns:
            Dictionary with win_rate, place_rate, and runs
        """
        if not sire_id:
            return {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

        # Generate cache key
        cache_key = f"sire_{sire_id}_{distance}_{baba_code}_{venue_code}_{is_turf}"
        if cache_key in self._sire_stats_cache:
            return self._sire_stats_cache[cache_key]

        # Build conditions
        conditions = ["k.ketto1_hanshoku_toroku_bango = %s"]
        params = [sire_id]

        # Turf/Dirt condition
        track_prefix = "1" if is_turf else "2"
        conditions.append(f"r.track_code LIKE '{track_prefix}%'")

        # Distance condition (±200m)
        if distance:
            conditions.append("r.kyori::int BETWEEN %s AND %s")
            params.extend([distance - 200, distance + 200])

        # Track condition
        if baba_code:
            if is_turf:
                conditions.append("r.shiba_babajotai_code = %s")
            else:
                conditions.append("r.dirt_babajotai_code = %s")
            params.append(baba_code)

        # Venue condition
        if venue_code:
            conditions.append("r.keibajo_code = %s")
            params.append(venue_code)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN u.kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN u.kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho u
            JOIN kyosoba_master2 k ON u.ketto_toroku_bango = k.ketto_toroku_bango
            JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
            WHERE {where_clause}
              AND u.data_kubun = '7'
              AND u.kakutei_chakujun ~ '^[0-9]+$'
              AND u.kaisai_nen >= %s
        """
        params.append(str(date.today().year - 3))  # Past 3 years

        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                runs, wins, places = row
                result = {
                    "win_rate": wins / runs if runs > 0 else 0.08,
                    "place_rate": places / runs if runs > 0 else 0.25,
                    "runs": runs,
                }
            else:
                result = {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

            self._sire_stats_cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get sire stats: {e}")
            self.conn.rollback()
            return {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

    def extract_pedigree_features(self, kettonum: str, race_info: dict) -> dict[str, Any]:
        """Extract pedigree-related features."""
        features = {}

        # Get pedigree info
        pedigree = self.get_pedigree_info(kettonum)
        sire_id = pedigree.get("sire_id", "")
        broodmare_sire_id = pedigree.get("broodmare_sire_id", "")

        # Hash IDs for categorical features
        features["sire_id_hash"] = hash(sire_id) % 10000 if sire_id else 0
        features["broodmare_sire_id_hash"] = (
            hash(broodmare_sire_id) % 10000 if broodmare_sire_id else 0
        )

        # Race conditions
        distance = self._safe_int(race_info.get("kyori"), 1600)
        track_code = race_info.get("track_code", "")
        is_turf = track_code.startswith("1") if track_code else True
        baba_code = (
            race_info.get("shiba_babajotai_code", "1")
            if is_turf
            else race_info.get("dirt_babajotai_code", "1")
        )
        venue_code = race_info.get("keibajo_code", "")

        # Sire x distance stats
        sire_dist_stats = self.get_sire_stats(sire_id, distance=distance, is_turf=is_turf)
        features["sire_distance_win_rate"] = sire_dist_stats["win_rate"]
        features["sire_distance_place_rate"] = sire_dist_stats["place_rate"]
        features["sire_distance_runs"] = min(sire_dist_stats["runs"], 500)  # Cap

        # Sire x track condition stats
        sire_baba_stats = self.get_sire_stats(sire_id, baba_code=baba_code, is_turf=is_turf)
        features["sire_baba_win_rate"] = sire_baba_stats["win_rate"]
        features["sire_baba_place_rate"] = sire_baba_stats["place_rate"]

        # Sire x venue stats
        sire_venue_stats = self.get_sire_stats(sire_id, venue_code=venue_code, is_turf=is_turf)
        features["sire_venue_win_rate"] = sire_venue_stats["win_rate"]
        features["sire_venue_place_rate"] = sire_venue_stats["place_rate"]

        # Broodmare sire overall stats (simplified)
        bms_stats = self.get_sire_stats(broodmare_sire_id, is_turf=is_turf)
        features["broodmare_sire_win_rate"] = bms_stats["win_rate"]
        features["broodmare_sire_place_rate"] = bms_stats["place_rate"]

        return features

    # ========================================
    # 2. Detailed last race info
    # ========================================

    def get_past_races_detailed(
        self, kettonum: str, current_race_code: str, limit: int = 5
    ) -> list[dict]:
        """Get detailed past race info (including distance and class)."""
        if not kettonum:
            return []

        cache_key = f"past_detailed_{kettonum}_{current_race_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                u.race_code,
                u.kaisai_nen,
                u.kaisai_gappi,
                u.keibajo_code,
                u.kakutei_chakujun,
                u.tansho_ninkijun,
                u.soha_time,
                u.kohan_3f,
                u.corner1_juni,
                u.corner2_juni,
                u.corner3_juni,
                u.corner4_juni,
                u.futan_juryo,
                u.bataiju,
                u.kishu_code,
                r.kyori,
                r.track_code,
                r.grade_code,
                r.shiba_babajotai_code,
                r.dirt_babajotai_code
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code AND u.data_kubun = r.data_kubun
            WHERE u.ketto_toroku_bango = %s
              AND u.data_kubun = '7'
              AND u.race_code < %s
              AND u.kakutei_chakujun ~ '^[0-9]+$'
            ORDER BY u.race_code DESC
            LIMIT %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum, current_race_code, limit))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            cur.close()
            result = [dict(zip(columns, row)) for row in rows]
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get detailed past races: {e}")
            self.conn.rollback()
            return []

    def calc_agari_3f_rank(self, race_code: str, kohan_3f: str) -> int:
        """Calculate last 3F rank."""
        if not race_code or not kohan_3f:
            return 9

        cache_key = f"agari_rank_{race_code}_{kohan_3f}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT kohan_3f
            FROM umagoto_race_joho
            WHERE race_code = %s
              AND data_kubun = '7'
              AND kohan_3f ~ '^[0-9]+$'
            ORDER BY kohan_3f::int ASC
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (race_code,))
            rows = cur.fetchall()
            cur.close()

            rank = 1
            for row in rows:
                if row[0] == kohan_3f:
                    self._cache[cache_key] = rank
                    return rank
                rank += 1

            self._cache[cache_key] = 9
            return 9
        except Exception as e:
            logger.debug(f"Failed to calc agari rank: {e}")
            self.conn.rollback()
            return 9

    def extract_zenso_features(
        self, kettonum: str, current_race_code: str, race_info: dict, current_ninki: int = None
    ) -> dict[str, Any]:
        """Extract last race info features."""
        features = {}
        past_races = self.get_past_races_detailed(kettonum, current_race_code, limit=5)

        # Default values when no past races
        if not past_races:
            features["zenso1_chakujun"] = 10
            features["zenso1_ninki"] = 10
            features["zenso1_ninki_diff"] = 0
            features["zenso1_class_diff"] = 0
            features["zenso1_agari_rank"] = 9
            features["zenso1_corner_avg"] = 8.0
            features["zenso1_distance"] = 1600
            features["zenso1_distance_diff"] = 0
            features["zenso2_chakujun"] = 10
            features["zenso3_chakujun"] = 10
            features["zenso_chakujun_trend"] = 0  # 0=no data
            features["zenso_agari_trend"] = 0
            return features

        # Last race (1 race ago)
        z1 = past_races[0]
        features["zenso1_chakujun"] = self._safe_int(z1.get("kakutei_chakujun"), 10)
        features["zenso1_ninki"] = self._safe_int(z1.get("tansho_ninkijun"), 10)

        # Popularity difference (positive if popularity improved)
        if current_ninki:
            features["zenso1_ninki_diff"] = features["zenso1_ninki"] - current_ninki
        else:
            features["zenso1_ninki_diff"] = 0

        # Class difference
        current_class = self._grade_to_rank(race_info.get("grade_code", ""))
        past_class = self._grade_to_rank(z1.get("grade_code", ""))
        features["zenso1_class_diff"] = (
            current_class - past_class
        )  # Positive = stepping up in class

        # Last 3F rank
        features["zenso1_agari_rank"] = self.calc_agari_3f_rank(
            z1.get("race_code", ""), z1.get("kohan_3f", "")
        )

        # Corner position average
        corners = []
        for i in [1, 2, 3, 4]:
            c = self._safe_int(z1.get(f"corner{i}_juni"), 0)
            if c > 0:
                corners.append(c)
        features["zenso1_corner_avg"] = np.mean(corners) if corners else 8.0

        # Distance
        features["zenso1_distance"] = self._safe_int(z1.get("kyori"), 1600)
        current_distance = self._safe_int(race_info.get("kyori"), 1600)
        features["zenso1_distance_diff"] = current_distance - features["zenso1_distance"]

        # 2nd and 3rd last race finish positions
        features["zenso2_chakujun"] = (
            self._safe_int(past_races[1].get("kakutei_chakujun"), 10) if len(past_races) > 1 else 10
        )
        features["zenso3_chakujun"] = (
            self._safe_int(past_races[2].get("kakutei_chakujun"), 10) if len(past_races) > 2 else 10
        )

        # Finish position trend (last 3 races)
        # 1=improving (better finishes), 0=stable, -1=declining
        if len(past_races) >= 3:
            c1 = features["zenso1_chakujun"]
            features["zenso2_chakujun"]
            c3 = features["zenso3_chakujun"]
            # Compare 1st and 3rd last race
            if c1 < c3 - 2:
                features["zenso_chakujun_trend"] = 1  # Improving
            elif c1 > c3 + 2:
                features["zenso_chakujun_trend"] = -1  # Declining
            else:
                features["zenso_chakujun_trend"] = 0  # Stable
        else:
            features["zenso_chakujun_trend"] = 0

        # Last 3F trend
        agaris = []
        for _, race in enumerate(past_races[:3]):
            l3f = self._safe_int(race.get("kohan_3f"), 0)
            if l3f > 0:
                agaris.append(l3f / 10.0)

        if len(agaris) >= 3:
            # Shorter time = improvement
            if agaris[0] < agaris[2] - 0.3:
                features["zenso_agari_trend"] = 1
            elif agaris[0] > agaris[2] + 0.3:
                features["zenso_agari_trend"] = -1
            else:
                features["zenso_agari_trend"] = 0
        else:
            features["zenso_agari_trend"] = 0

        return features

    # ========================================
    # 3. Venue-specific statistics
    # ========================================

    def get_venue_stats(
        self, kettonum: str, venue_code: str, is_turf: bool = True
    ) -> dict[str, float]:
        """Get venue-specific statistics (from shussobetsu_keibajo table)."""
        if not kettonum or not venue_code:
            return {"win_rate": 0.0, "place_rate": 0.0, "runs": 0}

        cache_key = f"venue_stats_{kettonum}_{venue_code}_{is_turf}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        venue_name = self.VENUE_CODES.get(venue_code, "")
        if not venue_name:
            return {"win_rate": 0.0, "place_rate": 0.0, "runs": 0}

        surface = "shiba" if is_turf else "dirt"
        col_prefix = f"{venue_name}_{surface}"

        sql = f"""
            SELECT
                COALESCE(NULLIF({col_prefix}_1chaku, '')::int, 0) as wins,
                COALESCE(NULLIF({col_prefix}_2chaku, '')::int, 0) as second,
                COALESCE(NULLIF({col_prefix}_3chaku, '')::int, 0) as third,
                COALESCE(NULLIF({col_prefix}_4chaku, '')::int, 0) as fourth,
                COALESCE(NULLIF({col_prefix}_5chaku, '')::int, 0) as fifth,
                COALESCE(NULLIF({col_prefix}_chakugai, '')::int, 0) as other
            FROM shussobetsu_keibajo
            WHERE ketto_toroku_bango = %s
            ORDER BY data_sakusei_nengappi DESC
            LIMIT 1
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kettonum,))
            row = cur.fetchone()
            cur.close()

            if row:
                wins = row[0]
                places = row[0] + row[1] + row[2]
                total = sum(row)
                result = {
                    "win_rate": wins / total if total > 0 else 0.0,
                    "place_rate": places / total if total > 0 else 0.0,
                    "runs": total,
                }
            else:
                result = {"win_rate": 0.0, "place_rate": 0.0, "runs": 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get venue stats: {e}")
            self.conn.rollback()
            return {"win_rate": 0.0, "place_rate": 0.0, "runs": 0}

    def extract_venue_features(
        self, kettonum: str, race_info: dict, past_races: list[dict] = None
    ) -> dict[str, Any]:
        """Extract venue-related features."""
        features = {}

        venue_code = race_info.get("keibajo_code", "")
        track_code = race_info.get("track_code", "")
        is_turf = track_code.startswith("1") if track_code else True

        # Stats at this venue
        venue_stats = self.get_venue_stats(kettonum, venue_code, is_turf)
        features["venue_win_rate"] = venue_stats["win_rate"]
        features["venue_place_rate"] = venue_stats["place_rate"]
        features["venue_runs"] = min(venue_stats["runs"], 50)

        # Small track aptitude (performance at tight courses)
        small_track_stats = {"wins": 0, "places": 0, "runs": 0}
        large_track_stats = {"wins": 0, "places": 0, "runs": 0}

        if past_races:
            for race in past_races:
                race_venue = race.get("keibajo_code", "")
                chakujun = self._safe_int(race.get("kakutei_chakujun"), 99)
                if chakujun > 18:
                    continue

                if race_venue in self.SMALL_TRACK_VENUES:
                    small_track_stats["runs"] += 1
                    if chakujun == 1:
                        small_track_stats["wins"] += 1
                    if chakujun <= 3:
                        small_track_stats["places"] += 1
                else:
                    large_track_stats["runs"] += 1
                    if chakujun == 1:
                        large_track_stats["wins"] += 1
                    if chakujun <= 3:
                        large_track_stats["places"] += 1

        # Small/large track aptitude scores
        if small_track_stats["runs"] > 0:
            features["small_track_place_rate"] = (
                small_track_stats["places"] / small_track_stats["runs"]
            )
        else:
            features["small_track_place_rate"] = 0.25

        if large_track_stats["runs"] > 0:
            features["large_track_place_rate"] = (
                large_track_stats["places"] / large_track_stats["runs"]
            )
        else:
            features["large_track_place_rate"] = 0.25

        # Set aptitude score based on whether current race is at small track
        is_small_track = venue_code in self.SMALL_TRACK_VENUES
        if is_small_track:
            features["track_type_fit"] = features["small_track_place_rate"]
        else:
            features["track_type_fit"] = features["large_track_place_rate"]

        return features

    # ========================================
    # 4. Enhanced pace prediction
    # ========================================

    def extract_pace_features_enhanced(
        self, entry: dict, all_entries: list[dict], running_styles: dict[str, int]
    ) -> dict[str, Any]:
        """Extract enhanced pace features."""
        features = {}

        umaban = self._safe_int(entry.get("umaban"), 0)
        my_style = running_styles.get(entry.get("ketto_toroku_bango", ""), 2)

        # Count front-runners inside my post position
        inner_senkou = 0
        inner_nige = 0
        for e in all_entries:
            e_umaban = self._safe_int(e.get("umaban"), 0)
            e_kettonum = e.get("ketto_toroku_bango", "")
            e_style = running_styles.get(e_kettonum, 2)

            if e_umaban < umaban:
                if e_style == 1:  # Front-runner
                    inner_nige += 1
                elif e_style == 2:  # Stalker
                    inner_senkou += 1

        features["inner_nige_count"] = inner_nige
        features["inner_senkou_count"] = inner_senkou

        # Post position x running style advantage
        # Inside post + front-running = advantage, outside post + closer = less disadvantage
        waku_style_score = 0.0
        if my_style in (1, 2):  # Front-runner/Stalker
            if umaban <= 4:  # Inside post
                waku_style_score = 0.1
            elif umaban >= 13:  # Outside post
                waku_style_score = -0.1
        else:  # Closer/Deep closer
            if umaban <= 4:
                waku_style_score = -0.05
            elif umaban >= 13:
                waku_style_score = 0.05

        features["waku_style_advantage"] = waku_style_score

        return features

    # ========================================
    # 5. Trend features (jockey form, etc.)
    # ========================================

    def get_jockey_recent_form(self, kishu_code: str, days: int = 14) -> dict[str, float]:
        """Get jockey's recent form/performance."""
        if not kishu_code:
            return {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

        cache_key = f"jockey_recent_{kishu_code}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql = """
            SELECT
                COUNT(*) as runs,
                SUM(CASE WHEN kakutei_chakujun = '01' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN kakutei_chakujun IN ('01','02','03') THEN 1 ELSE 0 END) as places
            FROM umagoto_race_joho
            WHERE kishu_code = %s
              AND data_kubun = '7'
              AND kakutei_chakujun ~ '^[0-9]+$'
              AND TO_DATE(kaisai_nen || kaisai_gappi, 'YYYYMMDD') >= CURRENT_DATE - %s
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (kishu_code, days))
            row = cur.fetchone()
            cur.close()

            if row and row[0] > 0:
                runs, wins, places = row
                result = {"win_rate": wins / runs, "place_rate": places / runs, "runs": runs}
            else:
                result = {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to get jockey recent form: {e}")
            self.conn.rollback()
            return {"win_rate": 0.08, "place_rate": 0.25, "runs": 0}

    def extract_trend_features(self, kishu_code: str, past_races: list[dict]) -> dict[str, Any]:
        """Extract trend features."""
        features = {}

        # Jockey's last 2 weeks performance
        jockey_form = self.get_jockey_recent_form(kishu_code, days=14)
        features["jockey_recent_win_rate"] = jockey_form["win_rate"]
        features["jockey_recent_place_rate"] = jockey_form["place_rate"]
        features["jockey_recent_runs"] = min(jockey_form["runs"], 30)

        return features

    # ========================================
    # 6. Season/timing features
    # ========================================

    def extract_seasonal_features(self, race_info: dict, horse_age: int) -> dict[str, Any]:
        """Extract season/timing features."""
        features = {}

        # Month (1-12)
        gappi = race_info.get("kaisai_gappi", "0101")
        month = self._safe_int(gappi[:2], 6)
        features["race_month"] = month

        # Season encoding (sin/cos for cyclical representation)
        features["month_sin"] = np.sin(2 * np.pi * month / 12)
        features["month_cos"] = np.cos(2 * np.pi * month / 12)

        # Meet week (1=opening week, 2=middle, 3=final week)
        nichime = self._safe_int(race_info.get("kaisai_nichiji", "01"), 1)
        if nichime <= 2:
            features["kaisai_week"] = 1  # Opening week
        elif nichime >= 7:
            features["kaisai_week"] = 3  # Final week
        else:
            features["kaisai_week"] = 2  # Middle

        # Age x month (growth period detection)
        # 3-year-olds in spring-summer are in growth period
        if horse_age == 3 and 3 <= month <= 8:
            features["growth_period"] = 1
        elif horse_age == 4 and 1 <= month <= 6:
            features["growth_period"] = 1
        else:
            features["growth_period"] = 0

        # Winter flag
        features["is_winter"] = 1 if month in (12, 1, 2) else 0

        return features

    # ========================================
    # Integration method
    # ========================================

    def extract_all_enhanced_features(
        self,
        entry: dict,
        race_info: dict,
        all_entries: list[dict],
        running_styles: dict[str, int],
        current_ninki: int = None,
    ) -> dict[str, Any]:
        """Extract all enhanced features."""
        features = {}
        kettonum = entry.get("ketto_toroku_bango", "")
        kishu_code = entry.get("kishu_code", "")
        horse_age = self._safe_int(entry.get("barei"), 4)
        current_race_code = race_info.get("race_code", "")

        # 1. Pedigree features
        pedigree_features = self.extract_pedigree_features(kettonum, race_info)
        features.update(pedigree_features)

        # 2. Last race info features
        zenso_features = self.extract_zenso_features(
            kettonum, current_race_code, race_info, current_ninki
        )
        features.update(zenso_features)

        # 3. Venue-specific stats
        past_races = self.get_past_races_detailed(kettonum, current_race_code, limit=10)
        venue_features = self.extract_venue_features(kettonum, race_info, past_races)
        features.update(venue_features)

        # 4. Enhanced pace prediction
        pace_features = self.extract_pace_features_enhanced(entry, all_entries, running_styles)
        features.update(pace_features)

        # 5. Trend features
        trend_features = self.extract_trend_features(kishu_code, past_races)
        features.update(trend_features)

        # 6. Season/timing features
        seasonal_features = self.extract_seasonal_features(race_info, horse_age)
        features.update(seasonal_features)

        return features

    # ========================================
    # Helper methods
    # ========================================

    def _safe_int(self, val, default: int = 0) -> int:
        """Safely convert value to int."""
        try:
            if val is None or val == "":
                return default
            return int(val)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, val, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            if val is None or val == "":
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    def _grade_to_rank(self, grade_code: str) -> int:
        """Convert grade code to rank (numeric)."""
        mapping = {"A": 8, "B": 7, "C": 6, "D": 5, "E": 4, "F": 3, "G": 2, "H": 1}
        return mapping.get(grade_code, 3)

    def clear_cache(self):
        """Clear internal caches."""
        self._cache = {}
        self._sire_stats_cache = {}
