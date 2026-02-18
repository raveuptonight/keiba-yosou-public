"""
Surface-specific model training CLI.

Train and evaluate turf-only or dirt-only models, then compare
against the existing mixed (all-surface) model.

Usage:
    python -m src.models.train_surface --surface turf
    python -m src.models.train_surface --surface turf --deploy
    python -m src.models.train_surface --surface dirt --years 4
"""

import argparse
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("models")


def main():
    parser = argparse.ArgumentParser(description="Train surface-specific model")
    parser.add_argument(
        "--surface",
        required=True,
        choices=["turf", "dirt"],
        help="Surface type to train",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of years of training data (default: 3)",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy as ensemble_model_{surface}_latest.pkl if training succeeds",
    )
    parser.add_argument(
        "--test-year",
        type=int,
        default=2022,
        help="Year for backtest comparison (default: 2022)",
    )
    args = parser.parse_args()

    surface = args.surface
    years = args.years
    test_year = args.test_year

    exclude_years = {test_year}

    logger.info(f"=== Surface-specific model training: {surface} ===")
    logger.info(f"Training years: {years}, Test year: {test_year} (excluded from training)")

    # --- Step 1: Train surface-specific model ---
    from src.scheduler.retrain.trainer import train_new_model

    train_result = train_new_model(
        MODEL_DIR, years=years, surface=surface, exclude_years=exclude_years
    )

    if train_result.get("status") != "success":
        logger.error(f"Training failed: {train_result.get('message', 'unknown error')}")
        return

    new_model_path = train_result["model_path"]
    logger.info(f"Surface model saved: {new_model_path}")

    # --- Step 2: Compare with mixed model on surface-filtered test data ---
    mixed_model_path = MODEL_DIR / "ensemble_model_latest.pkl"

    if mixed_model_path.exists():
        logger.info("Comparing surface model vs mixed model (on surface-filtered test data)...")
        from src.scheduler.retrain.evaluator import compare_models

        comparison = compare_models(
            mixed_model_path,
            new_model_path,
            test_year=test_year,
            surface=surface,
        )

        if comparison.get("status") == "success":
            logger.info("=" * 60)
            logger.info(f"Comparison results ({surface} test data only)")
            logger.info("=" * 60)
            logger.info(f"  Mixed model score:   {comparison['old_score']:.4f}")
            logger.info(f"  Surface model score: {comparison['new_score']:.4f}")
            logger.info(f"  Improvement:         {comparison['improvement']:+.4f}")

            new_eval = comparison.get("new_eval", {})
            old_eval = comparison.get("old_eval", {})
            for metric in ["win_auc", "quinella_auc", "place_auc", "top3_coverage"]:
                old_val = old_eval.get(metric, 0) if old_eval else 0
                new_val = new_eval.get(metric, 0)
                diff = new_val - old_val
                if "coverage" in metric:
                    logger.info(
                        f"  {metric}: {old_val*100:.1f}% -> {new_val*100:.1f}% ({diff*100:+.1f}%)"
                    )
                else:
                    logger.info(f"  {metric}: {old_val:.4f} -> {new_val:.4f} ({diff:+.4f})")
            logger.info("=" * 60)
        else:
            logger.warning(f"Comparison failed: {comparison.get('message', 'unknown')}")
            comparison = {}
    else:
        logger.warning(f"Mixed model not found at {mixed_model_path}, skipping comparison")
        comparison = {}

    # --- Step 3: Save result JSON ---
    timestamp = datetime.now().strftime("%Y%m%d")
    result_path = MODEL_DIR / f"surface_train_result_{surface}_{timestamp}.json"

    result_data = {
        "surface": surface,
        "years": years,
        "test_year": test_year,
        "trained_at": datetime.now().isoformat(),
        "train_result": train_result,
        "comparison": comparison,
    }
    result_path.write_text(json.dumps(result_data, indent=2, default=str))
    logger.info(f"Result saved: {result_path}")

    # --- Step 4: Deploy (optional) ---
    if args.deploy:
        deploy_path = MODEL_DIR / f"ensemble_model_{surface}_latest.pkl"
        shutil.copy2(new_model_path, deploy_path)
        logger.info(f"Deployed: {deploy_path}")
    else:
        logger.info("Use --deploy to deploy the surface model")


if __name__ == "__main__":
    main()
