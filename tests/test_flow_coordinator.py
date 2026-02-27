"""Unit tests for flow coordinator orchestration branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from venom_core.core.orchestrator import flow_coordinator as fc_mod
from venom_core.core.orchestrator.flow_coordinator import FlowCoordinator


class _Middleware:
    def __init__(self) -> None:
        self.broadcast_event = AsyncMock()


class _StateManager:
    def __init__(self) -> None:
        self.add_log = MagicMock()


def _task_dispatcher(**overrides):
    base = {
        "kernel": object(),
        "coder_agent": object(),
        "critic_agent": object(),
        "architect_agent": object(),
        "dispatch": AsyncMock(return_value="dispatch-result"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_should_use_council_lazy_initializes_flow(monkeypatch):
    state = _StateManager()
    task_dispatcher = _task_dispatcher()

    council_flow = MagicMock()
    council_flow.should_use_council.return_value = True
    council_ctor = MagicMock(return_value=council_flow)
    monkeypatch.setattr(fc_mod, "CouncilFlow", council_ctor)

    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    assert coordinator.should_use_council("complex task", "PLAN") is True
    council_ctor.assert_called_once()
    council_flow.should_use_council.assert_called_once_with("complex task", "PLAN")


@pytest.mark.asyncio
async def test_run_council_success_with_lazy_config(monkeypatch):
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)
    middleware = _Middleware()

    monkeypatch.setattr(
        fc_mod, "GuardianAgent", lambda kernel: f"guardian:{bool(kernel)}"
    )
    monkeypatch.setattr(fc_mod, "create_local_llm_config", lambda: {"cfg": "ok"})

    class _FakeCouncilConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_council(self):
            group_chat = SimpleNamespace(
                agents=[SimpleNamespace(name="Coder"), SimpleNamespace(name="Critic")]
            )
            return ("user_proxy", group_chat, "manager")

    class _FakeCouncilSession:
        def __init__(self, user_proxy, group_chat, manager):
            self.user_proxy = user_proxy
            self.group_chat = group_chat
            self.manager = manager

        async def run(self, context):
            assert context == "problem-context"
            return "council-result"

        def get_message_count(self):
            return 3

        def get_speakers(self):
            return ["Coder", "Critic"]

    monkeypatch.setattr(fc_mod, "CouncilConfig", _FakeCouncilConfig)
    monkeypatch.setattr(fc_mod, "CouncilSession", _FakeCouncilSession)

    result = await coordinator.run_council(uuid4(), "problem-context", middleware)

    assert result == "council-result"
    assert coordinator._council_config is not None
    assert middleware.broadcast_event.await_count == 3
    state.add_log.assert_called()


@pytest.mark.asyncio
async def test_run_council_returns_fallback_on_error():
    state = _StateManager()
    task_dispatcher = _task_dispatcher(coder_agent=None)
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)
    middleware = _Middleware()

    result = await coordinator.run_council(uuid4(), "ctx", middleware)

    assert "Council mode nie powiódł się" in result
    middleware.broadcast_event.assert_awaited()
    assert state.add_log.call_count >= 2


@pytest.mark.asyncio
async def test_run_council_returns_fallback_when_architect_missing():
    state = _StateManager()
    task_dispatcher = _task_dispatcher(architect_agent=None)
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)
    middleware = _Middleware()

    result = await coordinator.run_council(uuid4(), "ctx", middleware)

    assert "Council mode nie powiódł się" in result
    middleware.broadcast_event.assert_awaited()


def test_normalize_council_tuple_variants():
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    assert coordinator._normalize_council_tuple(("u",)) == ("u", None, None)

    obj = SimpleNamespace(user_proxy="u", group_chat="g", manager="m")
    assert coordinator._normalize_council_tuple(obj) == ("u", "g", "m")


@pytest.mark.asyncio
async def test_code_generation_with_review_fallback_to_dispatch():
    state = _StateManager()
    task_dispatcher = _task_dispatcher(coder_agent=None, critic_agent=None)
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    result = await coordinator.code_generation_with_review(uuid4(), "implement api")

    assert result == "dispatch-result"
    task_dispatcher.dispatch.assert_awaited_once_with(
        "CODE_GENERATION", "implement api"
    )


@pytest.mark.asyncio
async def test_code_generation_with_review_uses_lazy_loop(monkeypatch):
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    fake_loop = SimpleNamespace(execute=AsyncMock(return_value="loop-result"))
    monkeypatch.setattr(fc_mod, "CodeReviewLoop", lambda **_: fake_loop)

    result = await coordinator.code_generation_with_review(uuid4(), "implement parser")

    assert result == "loop-result"
    fake_loop.execute.assert_awaited_once()
    assert coordinator._code_review_loop is fake_loop


@pytest.mark.asyncio
async def test_code_generation_with_review_passes_skill_manager(monkeypatch):
    state = _StateManager()
    sentinel_skill_manager = object()
    task_dispatcher = _task_dispatcher(skill_manager=sentinel_skill_manager)
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    fake_loop = SimpleNamespace(execute=AsyncMock(return_value="loop-result"))
    captured_kwargs = {}

    def _code_review_ctor(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_loop

    monkeypatch.setattr(fc_mod, "CodeReviewLoop", _code_review_ctor)

    result = await coordinator.code_generation_with_review(uuid4(), "implement parser")

    assert result == "loop-result"
    assert captured_kwargs["skill_manager"] is sentinel_skill_manager


@pytest.mark.asyncio
async def test_flow_methods_lazy_initialize_and_execute(monkeypatch):
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(
        state,
        task_dispatcher,
        event_broadcaster=object(),
        orchestrator_submit_task=AsyncMock(),
    )

    healing = SimpleNamespace(execute=AsyncMock(return_value={"h": True}))
    forge = SimpleNamespace(execute=AsyncMock(return_value={"f": True}))
    issue = SimpleNamespace(execute=AsyncMock(return_value={"i": True}))
    campaign = SimpleNamespace(execute=AsyncMock(return_value={"c": True}))

    monkeypatch.setattr(fc_mod, "HealingFlow", lambda **_: healing)
    monkeypatch.setattr(fc_mod, "ForgeFlow", lambda **_: forge)
    monkeypatch.setattr(fc_mod, "IssueHandlerFlow", lambda **_: issue)
    monkeypatch.setattr(fc_mod, "CampaignFlow", lambda **_: campaign)

    assert (await coordinator.execute_healing_cycle(uuid4())) == {"h": True}
    assert (await coordinator.execute_forge_workflow(uuid4(), "spec", "tool")) == {
        "f": True
    }
    assert (await coordinator.handle_remote_issue(7)) == {"i": True}
    assert (
        await coordinator.execute_campaign_mode(goal_store={"x": 1}, max_iterations=2)
    )["c"]


@pytest.mark.asyncio
async def test_execute_campaign_mode_requires_submit():
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)

    with pytest.raises(RuntimeError, match="orchestrator_submit_task"):
        await coordinator.execute_campaign_mode(goal_store={}, max_iterations=1)


def test_reset_flows_sets_all_to_none():
    state = _StateManager()
    task_dispatcher = _task_dispatcher()
    coordinator = FlowCoordinator(state, task_dispatcher, event_broadcaster=None)
    coordinator._code_review_loop = object()
    coordinator._council_flow = object()
    coordinator._forge_flow = object()
    coordinator._campaign_flow = object()
    coordinator._healing_flow = object()
    coordinator._issue_handler_flow = object()

    coordinator.reset_flows()

    assert coordinator._code_review_loop is None
    assert coordinator._council_flow is None
    assert coordinator._forge_flow is None
    assert coordinator._campaign_flow is None
    assert coordinator._healing_flow is None
    assert coordinator._issue_handler_flow is None
