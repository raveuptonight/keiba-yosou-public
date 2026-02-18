"""
Surface Type Utilities

Helper functions for determining track surface type (turf/dirt/obstacle)
and resolving model paths based on surface.
"""

from pathlib import Path


def get_surface_type(track_code: str | None) -> str:
    """Return surface type from track_code.

    Args:
        track_code: Track code from race_shosai table.

    Returns:
        'turf', 'dirt', or 'obstacle'.
    """
    try:
        tc = int(track_code) if track_code else 0
    except (ValueError, TypeError):
        return "obstacle"

    if 10 <= tc <= 22:
        return "turf"
    elif tc in (24, 25, 26, 27, 51):
        return "dirt"
    else:
        return "obstacle"


def get_model_path_for_surface(model_dir: Path, surface: str) -> Path:
    """Return model file path for given surface type.

    Falls back to mixed model if surface-specific model does not exist.

    Args:
        model_dir: Directory containing model files.
        surface: Surface type ('turf', 'dirt', or 'obstacle').

    Returns:
        Path to the appropriate model file.
    """
    mixed_path = model_dir / "ensemble_model_latest.pkl"

    if surface == "turf":
        p = model_dir / "ensemble_model_turf_latest.pkl"
        return p if p.exists() else mixed_path
    elif surface == "dirt":
        p = model_dir / "ensemble_model_dirt_latest.pkl"
        return p if p.exists() else mixed_path

    return mixed_path
