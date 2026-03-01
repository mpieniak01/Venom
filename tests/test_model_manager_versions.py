"""Unit tests for extracted ModelManager version helpers."""

import pytest

from venom_core.core import model_manager_versions as mm_versions
from venom_core.core.model_manager import ModelManager, ModelVersion


class _DummyLogger:
    def info(self, msg, *args, **kwargs):  # pragma: no cover - trivial shim
        return None

    def error(self, msg, *args, **kwargs):  # pragma: no cover - trivial shim
        return None


def test_versions_register_and_activate_roundtrip(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))

    version = mm_versions.register_version(
        manager=manager,
        version_id="v-helpers-1",
        base_model="base",
        adapter_path=None,
        performance_metrics={"acc": 0.8},
        model_version_cls=ModelVersion,
        logger=logger,
    )
    assert version.version_id == "v-helpers-1"

    activated = mm_versions.activate_version(
        manager=manager,
        version_id="v-helpers-1",
        logger=logger,
    )
    assert activated is True
    assert manager.active_version == "v-helpers-1"


def test_versions_compare_and_genealogy(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    manager.register_version("v1", "base", performance_metrics={"acc": 0.8})
    manager.register_version("v2", "base", performance_metrics={"acc": 0.9})

    comparison = mm_versions.compare_versions(
        manager=manager,
        version_id_1="v1",
        version_id_2="v2",
        compute_metric_diff_fn=mm_versions.compute_metric_diff,
        logger=logger,
    )
    assert comparison is not None
    assert comparison["metrics_diff"]["acc"]["diff"] == pytest.approx(0.1)

    genealogy = mm_versions.get_genealogy(manager=manager)
    assert genealogy["total_versions"] == 2
    assert len(genealogy["versions"]) == 2


def test_versions_helpers_error_and_access_paths(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))

    assert not mm_versions.activate_version(
        manager=manager,
        version_id="missing",
        logger=logger,
    )
    assert mm_versions.get_active_version(manager=manager) is None
    assert mm_versions.get_version(manager=manager, version_id="missing") is None
    assert mm_versions.get_all_versions(manager=manager) == []

    manager.register_version("v1", "base", performance_metrics={"score": 1.0})
    manager.register_version("v2", "base", performance_metrics={"score": 2.0})
    assert mm_versions.get_version(manager=manager, version_id="v1") is not None
    assert mm_versions.get_active_version(manager=manager) is None

    missing_cmp = mm_versions.compare_versions(
        manager=manager,
        version_id_1="v1",
        version_id_2="missing",
        compute_metric_diff_fn=mm_versions.compute_metric_diff,
        logger=logger,
    )
    assert missing_cmp is None


def test_compute_metric_diff_edge_cases() -> None:
    assert mm_versions.compute_metric_diff(None, 1) is None
    assert mm_versions.compute_metric_diff(0, 3)["diff_pct"] == float("inf")
    non_numeric = mm_versions.compute_metric_diff("a", "b")
    assert non_numeric == {"v1": "a", "v2": "b", "diff": "N/A"}
