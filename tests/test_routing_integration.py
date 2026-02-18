from __future__ import annotations

from types import SimpleNamespace

from venom_core.contracts.routing import ReasonCode, RuntimeTarget
from venom_core.core.routing_integration import build_routing_decision


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
