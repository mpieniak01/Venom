"""First-use ownership and release regressions without loading real ML models."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from venom_core.memory.embedding_service import EmbeddingService


def test_first_use_shares_one_model_between_concurrent_callers(monkeypatch):
    service = EmbeddingService(service_type="local")
    first_loading = threading.Event()
    second_waiting = threading.Event()
    release = threading.Event()
    lock = threading.RLock()
    acquisitions = 0

    class ObservedLock:
        def __enter__(self):
            nonlocal acquisitions
            acquisitions += 1
            if acquisitions == 2:
                second_waiting.set()
            lock.acquire()

        def __exit__(self, *_args):
            lock.release()

    service._model_load_lock = ObservedLock()
    created = []

    def load_model(_name):
        created.append(object())
        first_loading.set()
        assert release.wait(3)
        return created[-1]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=load_model),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service._ensure_model_loaded)
        second = None
        try:
            assert first_loading.wait(1)
            second = executor.submit(service._ensure_model_loaded)
            assert second_waiting.wait(1)
            assert len(created) == 1
        finally:
            release.set()
        first.result()
        assert second is not None
        second.result()
    assert len(created) == 1
    assert service._model is created[0]


def test_release_closes_client_and_cache_without_loading_another_model():
    service = EmbeddingService(service_type="openai")
    close = Mock()
    client = SimpleNamespace(close=close)
    service._client = client
    service._model = object()
    service._get_embedding_cached = Mock()
    assert service.release_model_resource() is True
    assert service._client is None
    assert service._model is None
    close.assert_called_once()
    service._get_embedding_cached.cache_clear.assert_called_once()
    assert service.release_model_resource() is True
    close.assert_called_once()


def test_failed_client_close_remains_owned_and_can_be_retried():
    service = EmbeddingService(service_type="openai")
    close = Mock(side_effect=[RuntimeError("busy"), None])
    client = SimpleNamespace(close=close)
    service._client = client
    assert service.release_model_resource() is False
    assert service._client is client
    assert service.release_model_resource() is True
    assert service._client is None
    assert close.call_count == 2


def test_failed_first_initialization_can_retry(monkeypatch):
    from venom_core.memory import embedding_service

    service = EmbeddingService(service_type="openai")
    monkeypatch.setattr(
        embedding_service.SETTINGS, "OPENAI_API_KEY", "unit-test-not-real"
    )
    client = SimpleNamespace(close=Mock())
    factory = Mock(side_effect=[RuntimeError("temporary"), client])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=factory))
    with pytest.raises(RuntimeError, match="temporary"):
        service._ensure_model_loaded()
    assert service._client is None
    service._ensure_model_loaded()
    assert service._client is client
    service._ensure_model_loaded()
    assert factory.call_count == 2
    assert service.release_model_resource() is True


def test_cleanup_loaded_module_calls_hook_without_import(monkeypatch):
    from venom_core.services import onnx_runtime_cleanup

    hook = Mock()
    monkeypatch.setitem(
        sys.modules,
        "venom_core.api.routes.tasks",
        SimpleNamespace(release_onnx_task_runtime=hook),
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks", "release_onnx_task_runtime", wait=True
        )
        is True
    )
    hook.assert_called_once_with(wait=True)
