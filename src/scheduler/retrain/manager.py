"""
Model Management Functions

Functions for backing up, deploying, and version controlling models.
"""

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_current_model(current_model_path: Path, backup_dir: Path) -> str | None:
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


def deploy_new_model(new_model_path: str, current_model_path: Path, backup_dir: Path) -> None:
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


def git_commit_and_push_model(
    model_path: Path,
    metrics: dict | None = None,
    push: bool = True,
) -> bool:
    """
    Commit and push model file to git repository.

    Args:
        model_path: Path to the model file to commit
        metrics: Optional training metrics to include in commit message
        push: Whether to push to remote (default: True)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Find repository root
        repo_root = _find_git_root(model_path)
        if not repo_root:
            logger.error("Git repository not found")
            return False

        # Get relative path from repo root
        rel_path = model_path.resolve().relative_to(repo_root)

        # Build commit message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"model: 週次再学習モデル更新 ({timestamp})"

        if metrics:
            details = []
            if "win_auc" in metrics:
                details.append(f"Win AUC: {metrics['win_auc']:.4f}")
            if "place_auc" in metrics:
                details.append(f"Place AUC: {metrics['place_auc']:.4f}")
            if "top3_coverage" in metrics:
                details.append(f"Top3: {metrics['top3_coverage']*100:.1f}%")
            if "samples" in metrics:
                details.append(f"Samples: {metrics['samples']:,}")
            if details:
                commit_msg += "\n\n" + "\n".join(details)

        # Git add
        result = subprocess.run(
            ["git", "add", str(rel_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"git add failed: {result.stderr}")
            return False

        # Git commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Check if it's "nothing to commit"
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                logger.info("No changes to commit")
                return True
            logger.error(f"git commit failed: {result.stderr}")
            return False

        logger.info(f"Committed: {rel_path}")

        # Git push
        if push:
            result = subprocess.run(
                ["git", "push"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.error(f"git push failed: {result.stderr}")
                return False
            logger.info("Pushed to remote repository")

        return True

    except Exception as e:
        logger.error(f"Git operation failed: {e}")
        return False


def _find_git_root(path: Path) -> Path | None:
    """
    Find the root of the git repository.

    Args:
        path: Starting path to search from

    Returns:
        Path to repository root or None if not found
    """
    current = path.resolve()
    if current.is_file():
        current = current.parent

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    return None
