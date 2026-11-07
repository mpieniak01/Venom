"""First-use ownership and release regressions without loading real ML models."""

import json
import os
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from venom_core.memory import embedding_process
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


def test_idle_release_refreshes_on_cache_hits_and_reloads(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("venom_core.memory.embedding_service.monotonic", lambda: now[0])
    first = Mock()
    second = Mock()
    for model in (first, second):
        model.encode.return_value.tolist.return_value = [1.0]
    factory = Mock(side_effect=[first, second])
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=factory),
    )

    service = EmbeddingService(service_type="local", idle_seconds=10)
    assert not service.release_if_idle()
    assert service.get_embedding("query") == [1.0]
    now[0] = 9
    assert service.get_embedding("query") == [1.0]
    first.encode.assert_called_once()
    now[0] = 18
    assert not service.release_if_idle()
    now[0] = 19
    assert service.release_if_idle()
    assert not service.release_if_idle()
    assert service.get_embedding("query") == [1.0]
    assert factory.call_count == 2
    second.encode.assert_called_once()


def test_idle_release_skips_active_batch_and_counts_from_completion(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("venom_core.memory.embedding_service.monotonic", lambda: now[0])
    encoding = threading.Event()
    finish = threading.Event()

    def encode(*_args, **_kwargs):
        encoding.set()
        assert finish.wait(3)
        return [SimpleNamespace(tolist=lambda: [1.0])]

    service = EmbeddingService(service_type="local", idle_seconds=10)
    model = Mock()
    model.encode.return_value.tolist.return_value = [1.0]
    service._model = model
    service.get_embedding("query")
    model.encode.side_effect = encode

    with ThreadPoolExecutor(max_workers=1) as executor:
        batch = executor.submit(service.get_embeddings_batch, ["note"])
        try:
            assert encoding.wait(1)
            now[0] = 12
            assert not service.release_if_idle()
        finally:
            finish.set()
        assert batch.result(timeout=1) == [[1.0]]
    assert not service.release_if_idle()
    now[0] = 22
    assert service.release_if_idle()


@pytest.mark.skipif(os.name != "posix", reason="Worker uses POSIX socket inheritance")
def test_process_embeddings_reap_idle_worker_and_restart(tmp_path, monkeypatch):
    fake = tmp_path / "sentence_transformers.py"
    fake.write_text(
        "class SentenceTransformer:\n"
        "    def __init__(self, name): pass\n"
        "    def encode(self, value, **options):\n"
        "        from types import SimpleNamespace\n"
        "        def vec(text): return SimpleNamespace(tolist=lambda: [len(text), 1.0])\n"
        "        return [vec(text) for text in value] if isinstance(value, list) else vec(value)\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    now = [0.0]
    monkeypatch.setattr(embedding_process, "monotonic", lambda: now[0])
    service = embedding_process.ProcessEmbeddingService(idle_seconds=10)
    assert not service.release_if_idle()
    with pytest.raises(ValueError):
        service.get_embedding(" ")
    with pytest.raises(ValueError):
        service.get_embeddings_batch([])
    assert service._worker is None
    try:
        assert service.get_embedding("note") == [4, 1.0]
        first = service._worker[0]
        assert service.get_embeddings_batch(["x", "yy"]) == [[1, 1.0], [2, 1.0]]
        assert service.embedding_dimension == 2
        now[0] = 9
        assert not service.release_if_idle()
        now[0] = 10
        assert service.release_if_idle()
        assert first.returncode == 0
        assert service._worker is None
        assert service.embedding_dimension == 2
        assert service._worker is None
        assert service.get_embedding("note") == [4, 1.0]
        second = service._worker[0]
        assert second.pid != first.pid
        second.kill()
        second.wait(timeout=3)
        assert service.get_embedding("again") == [5, 1.0]
        assert service._worker[0].pid != second.pid
    finally:
        assert service.release_model_resource()


def test_worker_dispatches_embedding_calls_and_errors(monkeypatch):
    model = Mock(embedding_dimension=2)
    model.get_embedding.side_effect = [[1.0, 2.0], RuntimeError("encode failed")]
    model.get_embeddings_batch.return_value = [[2.0, 1.0]]
    monkeypatch.setattr(embedding_process, "EmbeddingService", lambda **kwargs: model)
    parent, worker = socket.socketpair()
    with parent, parent.makefile("rb") as replies, ThreadPoolExecutor() as executor:
        parent.settimeout(2)
        serve = executor.submit(embedding_process._serve_embeddings, worker.detach())
        try:
            for request, expected in (
                (("dimension", None), [True, 2]),
                (("single", "query"), [True, [1.0, 2.0]]),
                (("batch", ["note"]), [True, [[2.0, 1.0]]]),
                (("single", "fails"), [False, None]),
                (("unknown", None), [False, None]),
            ):
                embedding_process._send(parent, request)
                assert json.loads(replies.readline()) == expected
        finally:
            parent.shutdown(socket.SHUT_WR)
        serve.result(timeout=2)


def test_process_embedding_timeout_retires_unresponsive_worker(monkeypatch):
    service = embedding_process.ProcessEmbeddingService(idle_seconds=10)
    process = Mock(pid=123)
    process.poll.return_value = None
    timeout = subprocess.TimeoutExpired(cmd="embedding-worker", timeout=2)
    process.wait.side_effect = [timeout, timeout, 0]
    channel = Mock()
    incoming = Mock()
    incoming.readline.side_effect = TimeoutError
    monkeypatch.setattr(service, "_start", lambda: (process, channel, incoming))
    with pytest.raises(RuntimeError, match="worker unavailable"):
        service.get_embedding("note")
    incoming.close.assert_called_once()
    channel.close.assert_called_once()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert service._worker is None


def test_process_embedding_expiry_skips_an_active_request(monkeypatch):
    service = embedding_process.ProcessEmbeddingService(idle_seconds=10)
    active = threading.Event()
    finish = threading.Event()

    def request(*_args):
        active.set()
        assert finish.wait(2)
        return [1.0]

    monkeypatch.setattr(service, "_request", request)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(service.get_embedding, "note")
        try:
            assert active.wait(1)
            assert not service.release_if_idle()
        finally:
            finish.set()
        assert pending.result(timeout=1) == [1.0]
