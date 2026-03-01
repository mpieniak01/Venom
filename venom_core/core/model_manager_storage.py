"""Storage/path helpers for ModelManager."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, Protocol


class LoggerLike(Protocol):
    def error(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


def is_valid_model_name(model_name: str) -> bool:
    """Validate model name before subprocess usage."""
    return bool(model_name and re.match(r"^[\w\-.:]+$", model_name))


def resolve_models_mount() -> Path:
    """Resolve preferred mount for disk usage metrics."""
    disk_mount = Path("/usr/lib/wsl/drivers")
    if disk_mount.exists():
        return disk_mount
    return Path("/")


def delete_local_model_file(
    *,
    model_info: Dict[str, Any],
    models_dir: Path,
    logger: LoggerLike,
) -> bool:
    """Delete local model path with traversal safeguards."""
    model_path = Path(str(model_info["path"])).resolve()

    if not model_path.is_relative_to(models_dir):
        logger.error("Nieprawidłowa ścieżka modelu: %s", model_path)
        return False

    if not model_path.exists():
        logger.error("Ścieżka modelu nie istnieje: %s", model_path)
        return False

    if model_path.is_dir():
        shutil.rmtree(model_path)
    else:
        model_path.unlink()
    return True
