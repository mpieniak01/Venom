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
    """
    return Path(prefer_dir) / filename
