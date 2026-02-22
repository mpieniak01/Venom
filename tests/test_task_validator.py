from types import SimpleNamespace
from uuid import uuid4

import pytest

from venom_core.api.schemas.tasks import TaskRequest
from venom_core.core.orchestrator.task_pipeline.task_validator import TaskValidator


def _runtime_info(**overrides):
    base = {
        "provider": "onnx",
        "model_name": "gemma-3-4b-it-onnx",
        "endpoint": None,
        "service_type": "onnx",
        "config_hash": "abc",
        "runtime_id": "onnx@local",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _orch_stub():
    calls = {"set_runtime_error": []}

    def _build_error_envelope(**kwargs):
        return kwargs

    def _set_runtime_error(task_id, envelope):
        calls["set_runtime_error"].append((task_id, envelope))

    orch = SimpleNamespace(
        request_tracer=None,
        task_dispatcher=SimpleNamespace(kernel=object()),
        _build_error_envelope=_build_error_envelope,
        _set_runtime_error=_set_runtime_error,
    )
    return orch, calls


def test_validate_routing_blocks_onnx_in_task_mode(monkeypatch):
    orch, calls = _orch_stub()
    validator = TaskValidator(orch=orch)
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.task_validator.get_active_llm_runtime",
        lambda: _runtime_info(provider="onnx"),
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.task_validator.normalize_forced_provider",
        lambda value: value,
    )
    with pytest.raises(RuntimeError, match="runtime_not_supported"):
        validator.validate_routing(
            task_id=uuid4(),
            request=TaskRequest(content="test"),
            forced_provider="",
        )
    assert len(calls["set_runtime_error"]) == 1
    envelope = calls["set_runtime_error"][0][1]
    assert envelope["error_code"] == "runtime_not_supported"
