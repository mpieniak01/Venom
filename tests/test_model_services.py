from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from venom_core.bootstrap.model_services import initialize_model_services


def test_initialize_model_services_success(monkeypatch, tmp_path) -> None:
    class _FakeModelManager:
        def __init__(self, *, models_dir: str):
            self.models_dir = models_dir

    class _FakeModelRegistry:
        pass

    class _FakeBenchmarkService:
        def __init__(self, *, model_registry, service_monitor, llm_controller):
            self.model_registry = model_registry
            self.service_monitor = service_monitor
            self.llm_controller = llm_controller

    monkeypatch.setattr("venom_core.core.model_manager.ModelManager", _FakeModelManager)
    monkeypatch.setattr(
        "venom_core.core.model_registry.ModelRegistry", _FakeModelRegistry
    )
    monkeypatch.setattr(
        "venom_core.services.benchmark.BenchmarkService", _FakeBenchmarkService
    )

    logger = MagicMock()
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "models"))
    service_monitor = object()
    llm_controller = object()

    model_manager, model_registry, benchmark_service = initialize_model_services(
        settings=settings,
        service_monitor=service_monitor,
        llm_controller=llm_controller,
        logger=logger,
    )

    assert model_manager is not None
    assert model_registry is not None
    assert benchmark_service is not None
    assert benchmark_service.service_monitor is service_monitor
    logger.info.assert_called()


def test_initialize_model_services_handles_missing_service_monitor(
    monkeypatch, tmp_path
) -> None:
    class _FakeModelManager:
        def __init__(self, *, models_dir: str):
            self.models_dir = models_dir

    class _FakeModelRegistry:
        pass

    class _FakeBenchmarkService:
        def __init__(self, *, model_registry, service_monitor, llm_controller):
            self.model_registry = model_registry
            self.service_monitor = service_monitor
            self.llm_controller = llm_controller

    monkeypatch.setattr("venom_core.core.model_manager.ModelManager", _FakeModelManager)
    monkeypatch.setattr(
        "venom_core.core.model_registry.ModelRegistry", _FakeModelRegistry
    )
    monkeypatch.setattr(
        "venom_core.services.benchmark.BenchmarkService", _FakeBenchmarkService
    )

    logger = MagicMock()
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "models"))

    model_manager, model_registry, benchmark_service = initialize_model_services(
        settings=settings,
        service_monitor=None,
        llm_controller=None,
        logger=logger,
    )

    assert model_manager is not None
    assert model_registry is None
    assert benchmark_service is None
    logger.warning.assert_called()
