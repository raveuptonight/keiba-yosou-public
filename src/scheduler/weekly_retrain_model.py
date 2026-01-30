"""
Weekly Model Retrain Module

Executes weekly at Tuesday 23:00 to:
1. Retrain ensemble model (XGBoost + LightGBM + CatBoost) with latest data
2. Classification models (win/place) + calibration
3. Backtest comparison of old vs new model
4. Deploy new model if improved
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from src.scheduler.retrain.evaluator import compare_models
from src.scheduler.retrain.manager import deploy_new_model, git_commit_and_push_model
from src.scheduler.retrain.notifier import send_retrain_notification
from src.scheduler.retrain.trainer import train_new_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class WeeklyRetrain:
    """Weekly retraining class for ensemble model."""

    def __init__(self, model_dir: str | None = None, backup_dir: str | None = None):
        """
        Initialize retrainer.

        Args:
            model_dir: Directory for models (defaults to /app/models or local models/)
            backup_dir: Directory for backups (defaults to model_dir/backup)
        """
        # Default paths: support both local and Docker environments
        if model_dir is None:
            if Path("/app/models").exists():
                model_dir = "/app/models"
            else:
                model_dir = str(Path(__file__).parent.parent.parent / "models")
        if backup_dir is None:
            backup_dir = str(Path(model_dir) / "backup")
        self.model_dir = Path(model_dir)
        self.backup_dir = Path(backup_dir)
        self.current_model_path = self.model_dir / "ensemble_model_latest.pkl"

    def run_weekly_job(
        self,
        force_deploy: bool = False,
        notify: bool = True,
        years: int = 3,
        git_push: bool = True,
    ) -> dict:
        """
        Run weekly retraining job.

        Args:
            force_deploy: Deploy even without improvement
            notify: Send Discord notification
            years: Number of years for training data
            git_push: Commit and push model to git repository

        Returns:
            Job result dictionary
        """
        logger.info("=" * 50)
        logger.info(f"Weekly model retrain started: {datetime.now()}")
        logger.info("=" * 50)

        result = {"date": date.today().isoformat(), "deployed": False}

        # 1. Train new model
        training_result = train_new_model(self.model_dir, years=years)
        result["training"] = training_result

        if training_result["status"] != "success":
            logger.error(f"Training failed: {training_result}")
            return result

        new_model_path = training_result["model_path"]

        # 2. Compare with current model (if exists)
        if self.current_model_path.exists():
            comparison = compare_models(self.current_model_path, new_model_path)
            result["comparison"] = comparison

            if comparison["status"] == "success":
                # Deploy if improved (or force deploy)
                if comparison["improvement"] > 0 or force_deploy:
                    deploy_new_model(new_model_path, self.current_model_path, self.backup_dir)
                    result["deployed"] = True
                    logger.info("New model deployed")
                else:
                    logger.info("No improvement, keeping current model")
                    # Remove temporary file
                    Path(new_model_path).unlink()
            elif force_deploy:
                # Force deploy even if comparison failed
                deploy_new_model(new_model_path, self.current_model_path, self.backup_dir)
                result["deployed"] = True
                logger.info("Force deployed (comparison failed)")
        else:
            # No current model, deploy directly
            import shutil

            shutil.move(new_model_path, self.current_model_path)
            result["deployed"] = True
            result["comparison"] = {"note": "initial_deployment"}
            logger.info("Initial deployment complete")

        # 2.5. Git commit and push (if deployed)
        if result["deployed"] and git_push:
            git_result = git_commit_and_push_model(
                self.current_model_path,
                metrics=training_result,
                push=True,
            )
            result["git_pushed"] = git_result
            if git_result:
                logger.info("Model committed and pushed to git repository")
            else:
                logger.warning("Git push failed (model still deployed locally)")

        # 3. Send notification
        if notify:
            send_retrain_notification(result)

        # Save result
        result_path = self.model_dir / f"retrain_result_{date.today().strftime('%Y%m%d')}.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Weekly model retrain (ensemble_model)")
    parser.add_argument(
        "--force", "-f", action="store_true", help="Deploy even without improvement"
    )
    parser.add_argument("--no-notify", action="store_true", help="Skip Discord notification")
    parser.add_argument(
        "--years", "-y", type=int, default=3, help="Years of training data (default: 3)"
    )
    parser.add_argument("--no-git", action="store_true", help="Skip git commit/push")

    args = parser.parse_args()

    retrain = WeeklyRetrain()
    result = retrain.run_weekly_job(
        force_deploy=args.force,
        notify=not args.no_notify,
        years=args.years,
        git_push=not args.no_git,
    )

    print("\n=== Retrain Result ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
