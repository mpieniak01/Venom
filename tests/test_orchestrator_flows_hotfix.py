"""Unit tests for orchestrator flow helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from venom_core.core.orchestrator import orchestrator_flows as flows


@pytest.mark.asyncio
async def test_code_generation_with_review_fallback_dispatch():
    orch = SimpleNamespace(
        task_dispatcher=SimpleNamespace(
            coder_agent=None,
            critic_agent=None,
            dispatch=AsyncMock(return_value="fallback"),
        ),
        _code_review_loop=None,
        state_manager=object(),
    )
    result = await flows.code_generation_with_review(orch, uuid4(), "implement x")
    assert result == "fallback"


@pytest.mark.asyncio
async def test_code_generation_with_review_uses_loop():
    loop = SimpleNamespace(execute=AsyncMock(return_value="reviewed"))
    orch = SimpleNamespace(
        task_dispatcher=SimpleNamespace(
            coder_agent=object(),
            critic_agent=object(),
        ),
        _code_review_loop=loop,
        state_manager=object(),
    )
    result = await flows.code_generation_with_review(orch, uuid4(), "implement y")
    assert result == "reviewed"
    loop.execute.assert_awaited_once()


def test_should_use_council_initializes_flow_and_uses_context_fallback():
    router = SimpleNamespace(
        set_council_flow=MagicMock(),
        should_use_council=MagicMock(return_value=True),
    )
    orch = SimpleNamespace(
        _council_flow=None,
        state_manager=object(),
        task_dispatcher=object(),
        event_broadcaster=object(),
        flow_router=router,
    )
    with patch(
        "venom_core.core.orchestrator.orchestrator_flows.CouncilFlow"
    ) as flow_cls:
        flow_cls.return_value = object()
        assert (
            flows.should_use_council(orch, content=None, context="ctx", intent="I")
            is True
        )
    router.set_council_flow.assert_called_once()
    router.should_use_council.assert_called_once_with("ctx", "I")


@pytest.mark.asyncio
async def test_run_council_success_with_existing_config():
    session = SimpleNamespace(
        run=AsyncMock(return_value="done"),
        get_message_count=lambda: 2,
        get_speakers=lambda: ["coder", "critic"],
    )
    group_chat = SimpleNamespace(
        agents=[SimpleNamespace(name="coder"), SimpleNamespace(name="critic")]
    )
    config = SimpleNamespace(
        create_council=lambda: ("user_proxy", group_chat, "manager")
    )
    state_manager = SimpleNamespace(add_log=MagicMock())
    orch = SimpleNamespace(
        _council_config=config,
        _normalize_council_tuple=lambda t: t,
        _broadcast_event=AsyncMock(),
        state_manager=state_manager,
    )

    with patch("venom_core.core.council.CouncilSession", return_value=session):
        result = await flows.run_council(orch, uuid4(), "context")

    assert result == "done"
    assert state_manager.add_log.call_count >= 2


@pytest.mark.asyncio
async def test_run_council_error_path_returns_fallback_message():
    config = SimpleNamespace(create_council=lambda: ("u", None, None))
    orch = SimpleNamespace(
        _council_config=config,
        _normalize_council_tuple=lambda _t: (_t[0], _t[1], _t[2]),
        _broadcast_event=AsyncMock(),
        state_manager=SimpleNamespace(add_log=MagicMock()),
    )
    with patch(
        "venom_core.core.council.CouncilSession",
        side_effect=RuntimeError("session-failed"),
    ):
        result = await flows.run_council(orch, uuid4(), "context")
    assert "Council mode nie powiódł się" in result


@pytest.mark.asyncio
async def test_flow_execute_helpers_initialize_once():
    orch = SimpleNamespace(
        _healing_flow=None,
        _forge_flow=None,
        _issue_handler_flow=None,
        _campaign_flow=None,
        state_manager=object(),
        task_dispatcher=object(),
        event_broadcaster=object(),
        submit_task=AsyncMock(),
    )
    with (
        patch(
            "venom_core.core.orchestrator.orchestrator_flows.HealingFlow"
        ) as healing_cls,
        patch("venom_core.core.orchestrator.orchestrator_flows.ForgeFlow") as forge_cls,
        patch(
            "venom_core.core.orchestrator.orchestrator_flows.IssueHandlerFlow"
        ) as issue_cls,
        patch(
            "venom_core.core.orchestrator.orchestrator_flows.CampaignFlow"
        ) as campaign_cls,
    ):
        healing_cls.return_value.execute = AsyncMock(return_value={"h": True})
        forge_cls.return_value.execute = AsyncMock(return_value={"f": True})
        issue_cls.return_value.execute = AsyncMock(return_value={"i": True})
        campaign_cls.return_value.execute = AsyncMock(return_value={"c": True})

        assert (await flows.execute_healing_cycle(orch, uuid4()))["h"] is True
        assert (await flows.execute_forge_workflow(orch, uuid4(), "spec", "tool"))[
            "f"
        ] is True
        assert (await flows.handle_remote_issue(orch, 7))["i"] is True
        assert (
            await flows.execute_campaign_mode(orch, goal_store={}, max_iterations=1)
        )["c"] is True


@pytest.mark.asyncio
async def test_generate_help_response_success_and_exception():
    kernel = SimpleNamespace(plugins={"render": object(), "_internal": object()})
    dispatcher = SimpleNamespace(
        agent_map={"CODE_GENERATION": object(), "RESEARCH": object()},
        kernel=kernel,
    )
    orch = SimpleNamespace(
        task_dispatcher=dispatcher,
        event_broadcaster=object(),
        _broadcast_event=AsyncMock(),
    )

    text = await flows.generate_help_response(orch, uuid4())
    assert "Venom - System Pomocy" in text
    assert "**render**" in text

    broken = SimpleNamespace(task_dispatcher=SimpleNamespace(), event_broadcaster=None)
    error_text = await flows.generate_help_response(broken, uuid4())
    assert "Wystąpił błąd podczas generowania pomocy" in error_text


def test_is_public_plugin_filters_private_and_internal():
    assert flows.is_public_plugin("render")
    assert not flows.is_public_plugin("_hidden")
    assert not flows.is_public_plugin("InternalTool")
