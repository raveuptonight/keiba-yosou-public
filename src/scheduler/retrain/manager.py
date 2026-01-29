"""
Model Management Functions

Functions for backing up and deploying models.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_current_model(
    current_model_path: Path,
    backup_dir: Path
) -> str | None:
    """
    Backup current model.

    Args:
        current_model_path: Path to current model file
        backup_dir: Directory for backups

    Returns:
        Backup file path or None if no model exists
    """
    if not current_model_path.exists():
        logger.warning("Current model not found")
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"ensemble_model_{timestamp}.pkl"

    shutil.copy(current_model_path, backup_path)
    logger.info(f"Model backed up: {backup_path}")

    return str(backup_path)


def deploy_new_model(
    new_model_path: str,
    current_model_path: Path,
    backup_dir: Path
) -> None:
    """
    Deploy new model to production.

    Backs up the current model first, then replaces it with the new model.

    Args:
        new_model_path: Path to new model file
        current_model_path: Path for production model
        backup_dir: Directory for backups
    """
    # Backup current model
    backup_current_model(current_model_path, backup_dir)

    # Deploy new model
    shutil.move(new_model_path, current_model_path)
    logger.info(f"New model deployed: {current_model_path}")
