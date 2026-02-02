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
) -> Path:
    """
    Resolve config file path.

    Returns the path under ``prefer_dir`` without checking for existence.
    Callers must validate the file exists (e.g. ``path.exists()``) and
    handle missing files appropriately.
    """
    return Path(prefer_dir) / filename
