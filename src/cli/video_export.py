"""
Video JSON Export CLI

Export structured JSON for the video generation pipeline.

Usage:
    python -m src.cli.video_export --date tomorrow --filter graded
    python -m src.cli.video_export --date 2026-02-15 --filter all
    python -m src.cli.video_export --date 2026-02-15 --venue 東京 --race 11
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta

from src.export.video_json_exporter import VideoJsonExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resolve_date(date_str: str) -> date:
    """Resolve date string to date object.

    Supports:
        - 'tomorrow': next day
        - 'today': today
        - 'YYYY-MM-DD': specific date
    """
    if date_str == "tomorrow":
        return date.today() + timedelta(days=1)
    if date_str == "today":
        return date.today()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="動画用JSONエクスポート")
    parser.add_argument(
        "--date", "-d", required=True, help="対象日 (YYYY-MM-DD, 'tomorrow', 'today')"
    )
    parser.add_argument("--venue", help="会場指定（省略で全会場）")
    parser.add_argument("--race", type=int, help="レース番号指定")
    parser.add_argument(
        "--filter",
        default="all",
        choices=["graded", "main", "all"],
        help="フィルタ: graded=重賞のみ, main=メインのみ, all=全レース",
    )
    parser.add_argument("--output-dir", "-o", default="output/video_json")
    parser.add_argument(
        "--model",
        default=None,
        help="モデルパス (default: models/ensemble_model_latest.pkl)",
    )

    args = parser.parse_args()

    target_date = resolve_date(args.date)
    logger.info(f"Target date: {target_date}")
    logger.info(f"Filter: {args.filter}, Venue: {args.venue or 'all'}, Race: {args.race or 'all'}")

    exporter = VideoJsonExporter(model_path=args.model)
    output_files = exporter.export_day(
        target_date,
        output_dir=args.output_dir,
        race_filter=args.filter,
        venue=args.venue,
        race_number=args.race,
    )

    if output_files:
        print(f"\n{'='*50}")
        print(f"Exported {len(output_files)} file(s):")
        for f in output_files:
            print(f"  {f}")
        print(f"{'='*50}")
    else:
        print("No files exported (no races matched or no data available)")


if __name__ == "__main__":
    main()
