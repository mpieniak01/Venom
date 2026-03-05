from __future__ import annotations

import types

import pytest

from venom_core.services import onnx_runtime_cleanup


def test_safe_call_returns_false_when_target_is_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.SimpleNamespace(release_onnx_task_runtime="not-callable")
    monkeypatch.setattr(
        "venom_core.services.onnx_runtime_cleanup.importlib.import_module",
        lambda _name: module,
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            wait=True,
        )
        is False
    )


def test_safe_call_returns_false_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_name: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "venom_core.services.onnx_runtime_cleanup.importlib.import_module",
        _raise,
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            wait=False,
        )
        is False
    )


def test_release_onnx_runtime_best_effort_returns_true_when_one_hook_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def _fake_safe_call(module_name: str, function_name: str, **kwargs: object) -> bool:
        calls.append((module_name, function_name, kwargs))
        return function_name == "release_onnx_simple_client"

    monkeypatch.setattr(onnx_runtime_cleanup, "_safe_call", _fake_safe_call)

    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=True) is True
    assert calls == [
        (
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            {"wait": True},
        ),
        (
            "venom_core.api.routes.llm_simple",
            "release_onnx_simple_client",
            {},
        ),
    ]


def test_release_onnx_runtime_best_effort_returns_false_when_hooks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        onnx_runtime_cleanup,
        "_safe_call",
        lambda *_args, **_kwargs: False,
    )
    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=False) is False
