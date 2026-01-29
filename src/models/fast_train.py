"""
Fast Training Script

High-speed batch training pipeline for horse racing ML models.
Orchestrates feature extraction and model training with GPU support.

Usage:
    python -m src.models.fast_train --start-year 2015 --end-year 2025

Architecture:
    This is the entry point that coordinates:
    - feature_extractor/: Batch feature extraction
    - trainer.py: Model training and saving
"""

import argparse
import logging

import pandas as pd

from src.db.connection import get_db
from src.models.feature_extractor import FastFeatureExtractor
from src.models.trainer import save_model, train_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Main entry point for fast training pipeline."""
    parser = argparse.ArgumentParser(description="Fast Training Script")
    parser.add_argument("--start-year", type=int, default=2015, help="Start year")
    parser.add_argument("--end-year", type=int, default=2025, help="End year")
    parser.add_argument("--max-races", type=int, default=5000, help="Max races per year")
    parser.add_argument("--output", default="/app/models", help="Output directory")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU")

    args = parser.parse_args()

    print("=" * 60)
    print("Fast Training Script")
    print("=" * 60)
    print(f"Period: {args.start_year} - {args.end_year}")
    print(f"Max races per year: {args.max_races}")
    print(f"GPU: {'Disabled' if args.no_gpu else 'Enabled'}")
    print("=" * 60)

    # Database connection
    db = get_db()
    conn = db.get_connection()

    try:
        extractor = FastFeatureExtractor(conn)

        # Collect data year by year
        all_data = []
        for year in range(args.start_year, args.end_year + 1):
            df = extractor.extract_year_data(year, args.max_races)
            if len(df) > 0:
                all_data.append(df)

        if not all_data:
            logger.error("No data available")
            return

        # Concatenate all years
        full_df = pd.concat(all_data, ignore_index=True)
        logger.info(f"Total data: {len(full_df)} samples")

        # Train model
        models, results = train_model(full_df, use_gpu=not args.no_gpu)

        # Save model
        model_path = save_model(models, results, args.output)

        # Display results
        print("\n" + "=" * 60)
        print("Training Complete")
        print("=" * 60)
        print(f"Samples: {len(full_df)}")
        print(f"Features: {len(results['feature_names'])}")
        print(f"Validation RMSE: {results['rmse']:.4f}")
        print(f"Win classifier accuracy: {results['win_accuracy']:.4f}")
        print(f"Place classifier accuracy: {results['place_accuracy']:.4f}")
        print(f"Model path: {model_path}")

        print("\nFeature Importance TOP15:")
        for i, (name, imp) in enumerate(list(results["importance"].items())[:15], 1):
            print(f"  {i:2d}. {name}: {imp:.4f}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
