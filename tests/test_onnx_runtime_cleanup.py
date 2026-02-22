from __future__ import annotations

from venom_core.api.routes import llm_simple, tasks


class _DummyOnnxClient:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[bool, bool]] = []

    def shutdown(self, wait: bool, cancel_futures: bool = False) -> None:
        self.calls.append((wait, cancel_futures))


def test_release_onnx_simple_client_closes_and_resets(monkeypatch):
    client = _DummyOnnxClient()
    monkeypatch.setattr(llm_simple, "_ONNX_SIMPLE_CLIENT", client)
    llm_simple.release_onnx_simple_client()
    assert llm_simple._ONNX_SIMPLE_CLIENT is None
    assert client.closed == 1


def test_release_onnx_task_runtime_resets_worker_and_executor(monkeypatch):
    client = _DummyOnnxClient()
    executor = _DummyExecutor()
    monkeypatch.setattr(tasks, "_ONNX_WORKER_CLIENT", client)
    monkeypatch.setattr(tasks, "_ONNX_EXECUTOR", executor)
    tasks.release_onnx_task_runtime(wait=True)
    assert tasks._ONNX_WORKER_CLIENT is None
    assert tasks._ONNX_EXECUTOR is None
    assert client.closed == 1
    assert executor.calls == [(True, True)]
