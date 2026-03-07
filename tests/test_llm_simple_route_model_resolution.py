from __future__ import annotations

from venom_core.api.routes import llm_simple


def test_resolve_model_name_prefers_runtime_adapter_when_active_adapter_exists() -> (
    None
):
    resolved = llm_simple._resolve_model_name_for_simple_request(
        request_model="gemma3:4b",
        runtime_model="venom-adapter-self_learning_abc",
        active_adapter_id="self_learning_abc",
    )
    assert resolved == "venom-adapter-self_learning_abc"


def test_resolve_model_name_keeps_requested_model_without_active_adapter() -> None:
    resolved = llm_simple._resolve_model_name_for_simple_request(
        request_model="gemma3:4b",
        runtime_model="venom-adapter-self_learning_abc",
        active_adapter_id=None,
    )
    assert resolved == "gemma3:4b"


def test_resolve_model_name_falls_back_to_runtime_when_request_missing() -> None:
    resolved = llm_simple._resolve_model_name_for_simple_request(
        request_model="",
        runtime_model="gemma3:4b",
        active_adapter_id=None,
    )
    assert resolved == "gemma3:4b"
