"""Version lifecycle helpers for ModelManager."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional, Protocol, cast


class LoggerLike(Protocol):
    def info(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


class VersionLike(Protocol):
    created_at: Optional[str]
    performance_metrics: Dict[str, Any]
    is_active: bool

    def to_dict(self) -> Dict[str, Any]: ...


class ModelManagerLike(Protocol):
    versions: dict[str, Any]
    active_version: Optional[str]


def register_version(
    *,
    manager: ModelManagerLike,
    version_id: str,
    base_model: str,
    adapter_path: Optional[str],
    performance_metrics: Optional[Dict[str, Any]],
    model_version_cls: Callable[..., VersionLike],
    logger: LoggerLike,
) -> VersionLike:
    version = model_version_cls(
        version_id=version_id,
        base_model=base_model,
        adapter_path=adapter_path,
        created_at=datetime.now().isoformat(),
        performance_metrics=performance_metrics,
        is_active=False,
    )
    manager.versions[version_id] = version
    logger.info(f"Zarejestrowano wersję modelu: {version_id}")
    return version


def activate_version(
    *,
    manager: ModelManagerLike,
    version_id: str,
    logger: LoggerLike,
) -> bool:
    if version_id not in manager.versions:
        logger.error("Wersja modelu nie istnieje")
        return False

    if manager.active_version:
        manager.versions[manager.active_version].is_active = False

    manager.versions[version_id].is_active = True
    manager.active_version = version_id
    logger.info("Aktywowano wersję modelu")
    return True


def get_active_version(*, manager: ModelManagerLike) -> Optional[VersionLike]:
    if not manager.active_version:
        return None
    version = manager.versions.get(manager.active_version)
    if version is None:
        return None
    return cast(VersionLike, version)


def get_version(
    *,
    manager: ModelManagerLike,
    version_id: str,
) -> Optional[VersionLike]:
    version = manager.versions.get(version_id)
    if version is None:
        return None
    return cast(VersionLike, version)


def get_all_versions(*, manager: ModelManagerLike) -> list[VersionLike]:
    return sorted(
        [cast(VersionLike, version) for version in manager.versions.values()],
        key=lambda version: version.created_at or "",
        reverse=True,
    )


def get_genealogy(*, manager: ModelManagerLike) -> Dict[str, Any]:
    versions_data = [version.to_dict() for version in get_all_versions(manager=manager)]
    return {
        "total_versions": len(manager.versions),
        "active_version": manager.active_version,
        "versions": versions_data,
    }


def compare_versions(
    *,
    manager: ModelManagerLike,
    version_id_1: str,
    version_id_2: str,
    compute_metric_diff_fn: Callable[[Any, Any], Optional[Dict[str, Any]]],
    logger: LoggerLike,
) -> Optional[Dict[str, Any]]:
    version_1 = get_version(manager=manager, version_id=version_id_1)
    version_2 = get_version(manager=manager, version_id=version_id_2)

    if not version_1 or not version_2:
        logger.error("Jedna lub obie wersje nie istnieją")
        return None

    comparison: Dict[str, Any] = {
        "version_1": version_1.to_dict(),
        "version_2": version_2.to_dict(),
        "metrics_diff": {},
    }

    metric_keys = set(version_1.performance_metrics.keys()) | set(
        version_2.performance_metrics.keys()
    )
    for key in metric_keys:
        metric_diff = compute_metric_diff_fn(
            version_1.performance_metrics.get(key),
            version_2.performance_metrics.get(key),
        )
        if metric_diff is not None:
            comparison["metrics_diff"][key] = metric_diff

    return comparison


def compute_metric_diff(val1: Any, val2: Any) -> Optional[Dict[str, Any]]:
    if val1 is None or val2 is None:
        return None

    try:
        diff = val2 - val1
        if val1 != 0:
            diff_pct = (diff / val1) * 100
        else:
            diff_pct = float("inf") if val2 != 0 else 0
        return {
            "v1": val1,
            "v2": val2,
            "diff": diff,
            "diff_pct": diff_pct,
        }
    except (TypeError, ValueError):
        return {
            "v1": val1,
            "v2": val2,
            "diff": "N/A",
        }
