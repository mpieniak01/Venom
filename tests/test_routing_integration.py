from __future__ import annotations

from types import SimpleNamespace

import pytest

from venom_core.contracts.routing import ReasonCode, RuntimeTarget
from venom_core.core.routing_integration import (
    _build_fallback_chain,
    build_routing_decision,
)


def test_build_routing_decision_local_path(monkeypatch):
    class DummyRouter:
        def __init__(self, *args, **kwargs):
            pass

        def route_task(self, task_type, prompt):
            return {
                "target": "local",
                "model_name": "gemma3:4b",
                "provider": "local",
                "reason": "Tryb LOCAL - zadanie STANDARD",
                "is_paid": False,
            }

        def calculate_complexity(self, prompt, task_type):
            return 2

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=True,
                provider=preferred_provider,
                reason_code="PRIMARY_PROVIDER_SELECTED",
                fallback_applied=False,
                user_message="ok",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )

    decision = build_routing_decision(
        request=SimpleNamespace(
            content="hello",
            forced_intent=None,
            forced_tool=None,
            forced_provider=None,
        ),
        runtime_info=SimpleNamespace(provider="ollama", model_name="gemma3:4b"),
        state_manager=None,
    )

    assert decision.provider == "ollama"
    assert decision.target_runtime == RuntimeTarget.LOCAL_OLLAMA
    assert decision.reason_code == ReasonCode.DEFAULT_ECO_MODE
    assert decision.fallback_applied is False


def test_build_routing_decision_governance_fallback(monkeypatch):
    class DummyRouter:
        def __init__(self, *args, **kwargs):
            pass

        def route_task(self, task_type, prompt):
            return {
                "target": "cloud",
                "model_name": "gpt-4o-mini",
                "provider": "openai",
                "reason": "Tryb HYBRID: złożone zadanie CODING_COMPLEX -> CLOUD",
                "is_paid": True,
            }

        def calculate_complexity(self, prompt, task_type):
            return 8

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=True,
                provider="vllm",
                reason_code="FALLBACK_AUTH_ERROR",
                fallback_applied=True,
                user_message="fallback",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )

    decision = build_routing_decision(
        request=SimpleNamespace(
            content="implement complex flow",
            forced_intent="COMPLEX_PLANNING",
            forced_tool=None,
            forced_provider=None,
        ),
        runtime_info=SimpleNamespace(provider="ollama", model_name="gemma3:4b"),
        state_manager=None,
    )

    assert decision.provider == "vllm"
    assert decision.target_runtime == RuntimeTarget.LOCAL_VLLM
    assert decision.fallback_applied is True
    assert decision.reason_code == ReasonCode.FALLBACK_AUTH_ERROR
    assert decision.fallback_chain == ["openai", "vllm"]


def test_build_fallback_chain_variants():
    assert _build_fallback_chain(
        preferred_provider="openai",
        selected_provider="vllm",
        fallback_applied=True,
    ) == ["openai", "vllm"]
    assert _build_fallback_chain(
        preferred_provider="ollama",
        selected_provider="ollama",
        fallback_applied=False,
    ) == ["ollama"]
    assert (
        _build_fallback_chain(
            preferred_provider="",
            selected_provider="vllm",
            fallback_applied=True,
        )
        == []
    )


def test_build_routing_decision_sets_policy_gate_passed_from_governance(monkeypatch):
    class DummyRouter:
        def __init__(self, *args, **kwargs):
            pass

        def route_task(self, task_type, prompt):
            return {
                "target": "cloud",
                "model_name": "gpt-4o-mini",
                "provider": "openai",
                "reason": "restricted by governance",
                "is_paid": True,
            }

        def calculate_complexity(self, prompt, task_type):
            return 7

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=False,
                provider=preferred_provider,
                reason_code="PRIMARY_PROVIDER_SELECTED",
                fallback_applied=False,
                user_message="blocked",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )

    decision = build_routing_decision(
        request=SimpleNamespace(
            content="blocked request",
            forced_intent=None,
            forced_tool=None,
            forced_provider="openai",
        ),
        runtime_info=SimpleNamespace(provider="ollama", model_name="gemma3:4b"),
        state_manager=None,
    )

    assert decision.policy_gate_passed is False


def test_build_routing_decision_prefers_feedback_loop_alias_for_code_generation(
    monkeypatch,
):
    class DummyRouter:
        def __init__(self, *args, **kwargs):
            pass

        def route_task(self, task_type, prompt):
            return {
                "target": "local",
                "model_name": "phi3:mini",
                "provider": "local",
                "reason": "Tryb LOCAL - zadanie CODING_SIMPLE",
                "is_paid": False,
            }

        def calculate_complexity(self, prompt, task_type):
            return 2

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=True,
                provider="ollama",
                reason_code="PRIMARY_PROVIDER_SELECTED",
                fallback_applied=False,
                user_message="ok",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )

    decision = build_routing_decision(
        request=SimpleNamespace(
            content="write code",
            forced_intent="CODE_GENERATION",
            forced_tool=None,
            forced_provider=None,
        ),
        runtime_info=SimpleNamespace(provider="ollama", model_name="phi3:mini"),
        state_manager=None,
    )

    assert decision.provider == "ollama"
    assert decision.model == "code_generation"


def test_build_routing_decision_reuses_router_for_same_state_manager(monkeypatch):
    init_calls = {"count": 0}

    class DummyRouter:
        def __init__(self, *args, **kwargs):
            init_calls["count"] += 1

        def route_task(self, task_type, prompt):
            return {
                "target": "local",
                "model_name": "gemma3:4b",
                "provider": "local",
                "reason": "Tryb LOCAL - zadanie STANDARD",
                "is_paid": False,
            }

        def calculate_complexity(self, prompt, task_type):
            return 1

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=True,
                provider=preferred_provider,
                reason_code="PRIMARY_PROVIDER_SELECTED",
                fallback_applied=False,
                user_message="ok",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )

    class DummyStateManager:
        pass

    state_manager = DummyStateManager()
    request = SimpleNamespace(
        content="hello",
        forced_intent=None,
        forced_tool=None,
        forced_provider=None,
    )
    runtime_info = SimpleNamespace(provider="ollama", model_name="gemma3:4b")

    first = build_routing_decision(
        request=request,
        runtime_info=runtime_info,
        state_manager=state_manager,
    )
    second = build_routing_decision(
        request=request,
        runtime_info=runtime_info,
        state_manager=state_manager,
    )

    assert first.provider == "ollama"
    assert second.provider == "ollama"
    assert init_calls["count"] == 1


def test_build_routing_decision_disables_router_cache_via_env(monkeypatch):
    init_calls = {"count": 0}

    class DummyRouter:
        def __init__(self, *args, **kwargs):
            init_calls["count"] += 1

        def route_task(self, task_type, prompt):
            return {
                "target": "local",
                "model_name": "gemma3:4b",
                "provider": "local",
                "reason": "Tryb LOCAL - zadanie STANDARD",
                "is_paid": False,
            }

        def calculate_complexity(self, prompt, task_type):
            return 1

    class DummyGovernance:
        def select_provider_with_fallback(self, preferred_provider, reason=None):
            return SimpleNamespace(
                allowed=True,
                provider=preferred_provider,
                reason_code="PRIMARY_PROVIDER_SELECTED",
                fallback_applied=False,
                user_message="ok",
            )

    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter", DummyRouter
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: DummyGovernance(),
    )
    monkeypatch.setenv("VENOM_ROUTER_CACHE_ENABLED", "0")

    class DummyStateManager:
        pass

    state_manager = DummyStateManager()
    request = SimpleNamespace(
        content="hello",
        forced_intent=None,
        forced_tool=None,
        forced_provider=None,
    )
    runtime_info = SimpleNamespace(provider="ollama", model_name="gemma3:4b")

    build_routing_decision(
        request=request,
        runtime_info=runtime_info,
        state_manager=state_manager,
    )
    build_routing_decision(
        request=request,
        runtime_info=runtime_info,
        state_manager=state_manager,
    )

    assert init_calls["count"] == 2


@pytest.mark.parametrize("provider", ["onnx", "multi_runtime"])
@pytest.mark.parametrize("routed_provider", ["local", "selected_worker"])
def test_actual_governance_keeps_selected_local_worker(
    monkeypatch, provider, routed_provider
):
    """Regression for the real onnx->ollama auth-error metadata mismatch."""
    from venom_core.core.provider_governance import ProviderGovernance

    class Router:
        def __init__(self, **kwargs):
            pass

        def route_task(self, task_type, prompt):
            return {
                "target": "local",
                "provider": provider
                if routed_provider == "selected_worker"
                else "local",
                "model_name": "served-model",
                "reason": "local runtime",
            }

        def calculate_complexity(self, prompt, task_type):
            return 1

    governance = ProviderGovernance()
    monkeypatch.setattr("venom_core.core.routing_integration.HybridModelRouter", Router)
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: governance,
    )
    decision = build_routing_decision(
        request=SimpleNamespace(
            content="hello",
            forced_intent="GENERAL_CHAT",
            forced_tool=None,
            forced_provider=None,
        ),
        runtime_info=SimpleNamespace(provider=provider, model_name="served-model"),
    )
    assert decision.policy_gate_passed
    assert decision.provider == provider
    assert decision.target_runtime.value == provider
    assert decision.target_runtime.is_local()
    assert not decision.target_runtime.is_cloud()
    assert decision.fallback_chain == [provider]
    assert not decision.fallback_applied
    assert decision.reason_code != ReasonCode.FALLBACK_AUTH_ERROR
    assert decision.to_dict()["target_runtime"] == provider
    assert governance.fallback_history == []
