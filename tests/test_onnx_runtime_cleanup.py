from __future__ import annotations

import sys
import types

import pytest

from venom_core.services import onnx_runtime_cleanup


def test_cleanup_does_not_import_missing_entrypoints(monkeypatch):
    # Missing routes may have expensive import-time dependency initialization.
    for name in ("venom_core.api.routes.tasks", "venom_core.api.routes.llm_simple"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=True) is False
    assert "venom_core.api.routes.tasks" not in sys.modules
    assert "venom_core.api.routes.llm_simple" not in sys.modules


def test_safe_call_returns_false_when_target_is_not_callable(monkeypatch):
    module = types.SimpleNamespace(release_onnx_task_runtime="not-callable")
    monkeypatch.setitem(sys.modules, "venom_core.api.routes.tasks", module)
    assert not onnx_runtime_cleanup._safe_call(
        "venom_core.api.routes.tasks", "release_onnx_task_runtime", wait=True
    )


def test_safe_call_returns_false_when_loaded_hook_raises(monkeypatch):
    def fail(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "venom_core.api.routes.tasks",
        types.SimpleNamespace(release_onnx_task_runtime=fail),
    )
    assert not onnx_runtime_cleanup._safe_call(
        "venom_core.api.routes.tasks", "release_onnx_task_runtime", wait=False
    )


def test_release_onnx_runtime_best_effort_returns_true_when_one_hook_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_call(module_name: str, function_name: str, **kwargs: object) -> bool:
        calls.append((module_name, function_name, kwargs))
        return function_name == "release_onnx_simple_client"

    monkeypatch.setattr(onnx_runtime_cleanup, "_safe_call", fake_call)
    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=True) is True
    assert calls == [
        ("venom_core.api.routes.tasks", "release_onnx_task_runtime", {"wait": True}),
        ("venom_core.api.routes.llm_simple", "release_onnx_simple_client", {}),
    ]


def test_release_onnx_runtime_best_effort_returns_false_when_hooks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        onnx_runtime_cleanup, "_safe_call", lambda *_args, **_kwargs: False
    )
    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=False) is False
