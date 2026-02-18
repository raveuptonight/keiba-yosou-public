"""
Video JSON Exporter

Collects prediction data + DB master data and exports structured JSON
for the video generation pipeline.
"""

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.db.queries.video_export import (
    get_horse_course_stats,
    get_horse_past_races,
    get_jockey_course_stats,
    get_last_week_accuracy,
    get_pace_bias,
    get_waku_bias,
)
from src.scheduler.race_predictor import RacePredictor

logger = logging.getLogger(__name__)

VENUE_NAMES = {
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

GRADE_NAMES = {
    "A": "G1",
    "B": "G2",
    "C": "G3",
    "D": "Listed",
    "E": "OP",
}

TRACK_NAMES = {
    "10": "芝・左",
    "11": "芝・左・外",
    "12": "芝・左・内→外",
    "13": "芝・左・外→内",
    "14": "芝・左・内2周",
    "15": "芝・左・外2周",
    "17": "芝・右",
    "18": "芝・右・外",
    "19": "芝・右・内→外",
    "20": "芝・右・外→内",
    "21": "芝・右・内2周",
    "22": "芝・右・外2周",
    "23": "芝・直線",
    "24": "ダート・左",
    "25": "ダート・右",
    "26": "ダート・左・外",
    "27": "ダート・右・外",
    "29": "障害",
    "51": "ダート",
}


def _surface_from_track_code(track_code: str) -> str:
    """Extract surface type from track_code."""
    if not track_code:
        return "不明"
    first = track_code[0] if len(track_code) >= 1 else ""
    if first == "1" or first == "2":
        code_int = int(track_code) if track_code.isdigit() else 0
        if code_int >= 23 and code_int <= 27:
            return "ダート"
        if code_int >= 10 and code_int <= 22:
            return "芝"
        if code_int >= 51:
            return "ダート"
    return TRACK_NAMES.get(track_code, "不明")


class VideoJsonExporter:
    """Exports prediction data as structured JSON for video pipeline."""

    def __init__(
        self,
        model_path: str | None = None,
        channel_name: str = "AI競馬LAB",
    ):
        self.channel_name = channel_name
        effective_path = model_path or os.getenv(
            "MODEL_PATH", "models/ensemble_model_latest.pkl"
        )
        self.predictor = RacePredictor(model_path=effective_path)

    def export_day(
        self,
        target_date: date,
        output_dir: str = "output/video_json",
        race_filter: str = "all",
        venue: str | None = None,
        race_number: int | None = None,
    ) -> list[str]:
        """Export video JSON for all matching races on target_date.

        Args:
            target_date: Date to export predictions for.
            output_dir: Output directory for JSON files.
            race_filter: "all", "graded", or "main".
            venue: Venue name filter (e.g. "東京").
            race_number: Specific race number filter.

        Returns:
            List of output file paths.
        """
        races = self.predictor.get_upcoming_races(target_date)

        if not races:
            logger.info(f"No races found for {target_date}")
            return []

        # Apply filters
        filtered = self._filter_races(races, race_filter, venue, race_number)
        if not filtered:
            logger.info(f"No races matched filters: filter={race_filter}, venue={venue}")
            return []

        logger.info(f"Exporting {len(filtered)} races for {target_date}")

        output_files = []
        for race in filtered:
            try:
                output_path = self._export_single_race(race, target_date, output_dir)
                if output_path:
                    output_files.append(output_path)
            except Exception as e:
                logger.error(f"Export failed for {race['race_code']}: {e}")

        logger.info(f"Exported {len(output_files)} JSON files to {output_dir}")
        return output_files

    def _filter_races(
        self,
        races: list[dict],
        race_filter: str,
        venue: str | None,
        race_number: int | None,
    ) -> list[dict]:
        """Filter races based on criteria."""
        filtered = races

        if venue:
            filtered = [r for r in filtered if r.get("keibajo_name") == venue]

        if race_number is not None:
            filtered = [r for r in filtered if str(r.get("race_bango")) == str(race_number)]

        if race_filter == "graded":
            filtered = [r for r in filtered if r.get("grade_code", "") in ("A", "B", "C")]
        elif race_filter == "main":
            # Main race = R11 of each venue
            filtered = [r for r in filtered if str(r.get("race_bango")) == "11"]

        return filtered

    def _export_single_race(
        self, race: dict, target_date: date, output_dir: str
    ) -> str | None:
        """Export a single race to JSON."""
        race_code = race["race_code"]
        logger.info(
            f"Predicting: {race.get('keibajo_name', '')} {race.get('race_bango', '')}R"
        )

        # Run prediction with SHAP
        predictions = self.predictor.predict_race(race_code, compute_shap=True)
        if not predictions:
            logger.warning(f"No prediction results for {race_code}")
            return None

        # Get race detail for race_name etc.
        race_detail = self._get_race_detail(race_code)

        # Build enriched data via async queries
        enriched = asyncio.run(
            self._enrich_predictions(predictions, race, race_detail, target_date)
        )

        # Build output JSON
        output = self._build_output(
            race, race_detail, predictions, enriched, target_date
        )

        # Write to file
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        venue_name = race.get("keibajo_name", "unknown")
        race_num = race.get("race_bango", "0")
        filename = f"{target_date}_{venue_name}_{race_num}R.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported: {filepath}")
        return filepath

    def _get_race_detail(self, race_code: str) -> dict:
        """Get race detail from DB (sync, using psycopg2)."""
        from src.db.connection import get_db

        db = get_db()
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT race_code, kyosomei_hondai, grade_code, keibajo_code,
                       track_code, kyori, race_bango,
                       kaisai_nen, kaisai_gappi, kaisai_kai
                FROM race_shosai
                WHERE race_code = %s
                  AND data_kubun IN ('1','2','3','4','5','6','7')
                LIMIT 1
                """,
                (race_code,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return {}
            cols = [
                "race_code",
                "race_name",
                "grade_code",
                "keibajo_code",
                "track_code",
                "kyori",
                "race_bango",
                "kaisai_nen",
                "kaisai_gappi",
                "kaisai_kai",
            ]
            return dict(zip(cols, row))
        finally:
            conn.close()

    async def _enrich_predictions(
        self,
        predictions: list[dict],
        race: dict,
        race_detail: dict,
        target_date: date,
    ) -> dict[str, Any]:
        """Enrich predictions with past races, course stats, and bias data."""
        from src.db.async_connection import close_db_pool, init_db_pool, get_connection

        await init_db_pool()
        try:
            async with get_connection() as conn:
                enriched: dict[str, Any] = {
                    "horses": {},
                    "bias_data": {},
                    "last_week_results": None,
                }

                # Enrich each horse (top 8 only for performance)
                sorted_preds = sorted(predictions, key=lambda p: p["pred_rank"])
                top_horses = sorted_preds[:8]

                keibajo_code = race_detail.get("keibajo_code", race.get("keibajo_code", ""))
                track_code = race_detail.get("track_code", race.get("track_code", ""))
                kyori = int(race_detail.get("kyori", race.get("kyori", 0)) or 0)

                for pred in top_horses:
                    umaban = str(pred["umaban"])
                    kettonum = pred.get("ketto_toroku_bango", "")
                    kishu_code = pred.get("kishu_code", "")

                    horse_data: dict[str, Any] = {}

                    if kettonum:
                        horse_data["past_races"] = await get_horse_past_races(
                            conn, kettonum, limit=5
                        )
                        horse_data["course_stats"] = await get_horse_course_stats(
                            conn, kettonum, keibajo_code, track_code, kyori
                        )

                    if kishu_code:
                        horse_data["jockey_course_stats"] = await get_jockey_course_stats(
                            conn, kishu_code, keibajo_code, track_code, kyori
                        )

                    enriched["horses"][umaban] = horse_data

                # Waku bias and pace bias
                kaisai_nen = race_detail.get("kaisai_nen", "")
                kaisai_kai = race_detail.get("kaisai_kai", "")

                if keibajo_code and track_code and kaisai_nen and kaisai_kai:
                    enriched["bias_data"]["waku_bias"] = await get_waku_bias(
                        conn, keibajo_code, track_code, kaisai_nen, kaisai_kai
                    )
                    enriched["bias_data"]["pace_bias"] = await get_pace_bias(
                        conn, keibajo_code, track_code, kaisai_nen, kaisai_kai
                    )

                # Last week accuracy
                enriched["last_week_results"] = await get_last_week_accuracy(
                    conn, str(target_date)
                )

                return enriched
        finally:
            await close_db_pool()

    def _build_output(
        self,
        race: dict,
        race_detail: dict,
        predictions: list[dict],
        enriched: dict[str, Any],
        target_date: date,
    ) -> dict[str, Any]:
        """Build the final output JSON structure."""
        keibajo_code = race_detail.get("keibajo_code", race.get("keibajo_code", ""))
        track_code = race_detail.get("track_code", race.get("track_code", ""))
        kyori = race_detail.get("kyori", race.get("kyori", 0))
        grade_code = race_detail.get("grade_code", race.get("grade_code", ""))

        sorted_preds = sorted(predictions, key=lambda p: p["pred_rank"])

        # Build prediction entries
        pred_entries = []
        for pred in sorted_preds:
            umaban = str(pred["umaban"])
            horse_enriched = enriched.get("horses", {}).get(umaban, {})

            entry: dict[str, Any] = {
                "rank": pred["pred_rank"],
                "mark": pred.get("mark", ""),
                "umaban": pred["umaban"],
                "wakuban": pred.get("wakuban", ""),
                "horse_name": pred.get("bamei", ""),
                "win_prob": round(pred.get("win_prob", 0), 4),
                "place_prob": round(pred.get("place_prob", 0), 4) if pred.get("place_prob") else None,
                "shap_top_features": pred.get("shap_top_features", []),
            }

            if horse_enriched.get("past_races"):
                entry["past_races"] = horse_enriched["past_races"]
            if horse_enriched.get("jockey_course_stats"):
                entry["jockey_course_stats"] = horse_enriched["jockey_course_stats"]
            if horse_enriched.get("course_stats"):
                entry["course_stats"] = horse_enriched["course_stats"]

            pred_entries.append(entry)

        return {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "model_version": "v5_ensemble_xgb_lgb_cb",
                "channel_name": self.channel_name,
            },
            "race_info": {
                "race_code": race.get("race_code", ""),
                "race_name": (race_detail.get("race_name") or "").strip(),
                "grade": GRADE_NAMES.get(grade_code, ""),
                "venue": VENUE_NAMES.get(keibajo_code, keibajo_code),
                "race_number": race.get("race_bango", ""),
                "date": str(target_date),
                "distance": kyori,
                "surface": _surface_from_track_code(track_code),
                "horse_count": len(predictions),
            },
            "predictions": pred_entries,
            "bias_data": enriched.get("bias_data", {}),
            "last_week_results": enriched.get("last_week_results"),
        }
