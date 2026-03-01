"""Adapter activation/deactivation helpers for ModelManager."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, TypeVar


class LoggerLike(Protocol):
    def info(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


class VersionLike(Protocol):
    version_id: str
    adapter_path: Optional[str]
    base_model: str
    created_at: Optional[str]
    performance_metrics: Dict[str, Any]
    is_active: bool


VersionT = TypeVar("VersionT", bound=VersionLike)


class ModelManagerLike(Protocol[VersionT]):
    models_dir: Path
    active_adapter_state_path: Path
    versions: dict[str, VersionT]
    active_version: Optional[str]

    def activate_version(self, version_id: str) -> bool: ...

    def register_version(
        self,
        version_id: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
    ) -> VersionT: ...

    def get_active_version(self) -> Optional[VersionT]: ...


def save_active_adapter_state(
    *,
    state_path: Path,
    adapter_id: str,
    adapter_path: str,
    base_model: str,
) -> None:
    """Persist currently active adapter for restore on restart."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "adapter_id": adapter_id,
        "adapter_path": adapter_path,
        "base_model": base_model,
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "academy",
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_active_adapter_state(
    *,
    state_path: Path,
    logger: LoggerLike,
) -> Optional[Dict[str, Any]]:
    """Load persisted active adapter state."""
    if not state_path.exists():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return None
            return data
    except Exception as exc:
        logger.warning("Nie udało się odczytać stanu aktywnego adaptera: %s", exc)
        return None


def clear_active_adapter_state(*, state_path: Path, logger: LoggerLike) -> None:
    """Clear persisted active adapter state."""
    try:
        state_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Nie udało się usunąć stanu aktywnego adaptera: %s", exc)


def restore_active_adapter(
    *, manager: ModelManagerLike[VersionT], logger: LoggerLike
) -> bool:
    """
    Try to restore active adapter from persisted state.

    Returns:
        True when adapter was restored and activated; otherwise False.
    """
    state = load_active_adapter_state(
        state_path=manager.active_adapter_state_path,
        logger=logger,
    )
    if not state:
        return False

    adapter_id = str(state.get("adapter_id") or "").strip()
    adapter_path = str(state.get("adapter_path") or "").strip()
    base_model = str(state.get("base_model") or "academy-base").strip()
    if not adapter_id or not adapter_path:
        clear_active_adapter_state(
            state_path=manager.active_adapter_state_path,
            logger=logger,
        )
        return False

    if not Path(adapter_path).exists():
        logger.warning("Persistowany adapter nie istnieje: %s", adapter_path)
        clear_active_adapter_state(
            state_path=manager.active_adapter_state_path,
            logger=logger,
        )
        return False

    restored = activate_adapter(
        manager=manager,
        adapter_id=adapter_id,
        adapter_path=adapter_path,
        base_model=base_model,
        logger=logger,
    )
    if not restored:
        clear_active_adapter_state(
            state_path=manager.active_adapter_state_path,
            logger=logger,
        )
    return restored


def activate_adapter(
    *,
    manager: ModelManagerLike[VersionT],
    adapter_id: str,
    adapter_path: str,
    base_model: Optional[str],
    logger: LoggerLike,
) -> bool:
    """
    Activate Academy LoRA adapter.

    Returns:
        True if activation succeeded; otherwise False.
    """
    logger.info("Aktywacja adaptera Academy")

    expected_adapter_path = (
        manager.models_dir.resolve() / adapter_id / "adapter"
    ).resolve()

    if adapter_path and Path(adapter_path).resolve() != expected_adapter_path:
        logger.error("Adapter path niezgodny z katalogiem Academy")
        return False

    if not expected_adapter_path.exists():
        logger.error("Adapter nie istnieje")
        return False

    if adapter_id in manager.versions:
        success = manager.activate_version(adapter_id)
        if success:
            version = manager.versions[adapter_id]
            save_active_adapter_state(
                state_path=manager.active_adapter_state_path,
                adapter_id=adapter_id,
                adapter_path=version.adapter_path or str(expected_adapter_path),
                base_model=version.base_model,
            )
        return success

    base = base_model or "academy-base"
    manager.register_version(
        version_id=adapter_id,
        base_model=base,
        adapter_path=str(expected_adapter_path),
        performance_metrics={
            "source": "academy",
            "created_at": datetime.now().isoformat(),
        },
    )

    success = manager.activate_version(adapter_id)

    if success:
        logger.info("✅ Adapter %s aktywowany pomyślnie", adapter_id)
        save_active_adapter_state(
            state_path=manager.active_adapter_state_path,
            adapter_id=adapter_id,
            adapter_path=str(expected_adapter_path),
            base_model=base,
        )
    else:
        logger.error("❌ Nie udało się aktywować adaptera")

    return success


def deactivate_adapter(
    *, manager: ModelManagerLike[VersionT], logger: LoggerLike
) -> bool:
    """
    Deactivate current adapter (rollback to base model).

    Returns:
        True if deactivation succeeded; otherwise False.
    """
    if not manager.active_version:
        logger.warning("Brak aktywnego adaptera do dezaktywacji")
        return False

    logger.info("Dezaktywacja adaptera: %s", manager.active_version)

    if manager.active_version in manager.versions:
        manager.versions[manager.active_version].is_active = False

    manager.active_version = None
    clear_active_adapter_state(
        state_path=manager.active_adapter_state_path, logger=logger
    )
    logger.info("✅ Adapter zdezaktywowany - powrót do modelu bazowego")

    return True


def get_active_adapter_info(
    *, manager: ModelManagerLike[VersionT]
) -> Optional[Dict[str, Any]]:
    """
    Return active adapter metadata.

    Returns:
        Adapter metadata dict or None when no active adapter exists.
    """
    if not manager.active_version:
        return None

    version = manager.get_active_version()
    if not version:
        return None

    return {
        "adapter_id": version.version_id,
        "adapter_path": version.adapter_path,
        "base_model": version.base_model,
        "created_at": version.created_at,
        "performance_metrics": version.performance_metrics,
        "is_active": version.is_active,
    }
