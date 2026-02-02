from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=None)
def resolve_config_path(
    filename: str,
    *,
    prefer_dir: str = "config",
    legacy_dir: str = "data/config",
) -> Path:
    """
    Resolve config file path with backward-compatible fallback.

    Resolution order:
    1) <prefer_dir>/<filename>
    2) <legacy_dir>/<filename> (warn once)
    3) <prefer_dir>/<filename> (default even if missing)
    """
    preferred_path = Path(prefer_dir) / filename
    legacy_path = Path(legacy_dir) / filename

    if preferred_path.exists():
        return preferred_path

    if legacy_path.exists():
        logger.warning(
            "Using legacy config path '%s'. Consider moving to '%s'.",
            legacy_path.as_posix(),
            preferred_path.as_posix(),
        )
        return legacy_path

    return preferred_path
