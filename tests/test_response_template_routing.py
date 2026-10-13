"""Regression coverage for shared response planning without model activation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from semantic_kernel import Kernel

from venom_core.agents.executive import ExecutiveAgent
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import orchestrator_dispatch as dispatch
from venom_core.core.orchestrator.orchestrator_core import Orchestrator
from venom_core.services import conversation_providers as conversation
from venom_core.services.execution_template_planner import resolve_response_template


@pytest.fixture
def registry():
    previous = conversation.set_conversation_registry(None)
    value = conversation.ConversationProviderRegistry(None)
    conversation.set_conversation_registry(value)
    yield value
    conversation.set_conversation_registry(previous)


class StatusProvider:
    def __init__(self):
        self.handle = AsyncMock(return_value="fresh device status")

    def accepts(self, text, context):
        return text == "/device status"


@pytest.mark.asyncio
async def test_template_skips_classifier_context_and_executes_bound_handler(registry):
    provider = StatusProvider()
    await registry.register("device", provider)
    task_id = uuid4()
    turn = conversation.create_conversation_context("chat", task_id=str(task_id))
    request = TaskRequest(content="/device status")
    task = SimpleNamespace(context_history={})
    state = Mock()
    state.get_task.return_value = task
    state.update_context.side_effect = lambda _, values: task.context_history.update(
        values
    )
    orch = SimpleNamespace(
        state_manager=state,
        request_tracer=Mock(),
        intent_manager=SimpleNamespace(
            classify_intent=AsyncMock(side_effect=AssertionError("LLM classification")),
            requires_tool=Mock(),
        ),
        context_builder=SimpleNamespace(
            build_context=AsyncMock(side_effect=AssertionError("unused model context"))
        ),
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: Mock()),
    )
    await registry.prepare(request.content, turn)
    with conversation.conversation_turn(turn):
        intent, context, required, debug = await dispatch._prepare_intent_and_context(
            orch, task_id, request, request.content, False
        )
        provider.handle.assert_not_awaited()
        assert intent == "MODULE_CONVERSATION" and required
        assert debug == {"source": "template", "provider_id": "device"}
        assert (
            task.context_history["response_template"]["handler"]
            == "conversation_provider"
        )
        assert (
            await dispatch._execute_with_stream_callback(
                orch, task_id, intent, context, request
            )
            == "fresh device status"
        )
    orch.intent_manager.classify_intent.assert_not_awaited()
    orch.context_builder.build_context.assert_not_awaited()
    provider.handle.assert_awaited_once()
    await registry.finish(turn)
    await registry.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, {}, "x" * 32769])
async def test_claimed_handler_has_no_generic_fallback(registry, result):
    provider = StatusProvider()
    provider.handle.return_value = result
    await registry.register("device", provider)
    turn = conversation.create_conversation_context("chat")
    await registry.prepare("/device status", turn)
    with pytest.raises(conversation.ConversationProviderError, match="invalid_output"):
        await registry.handle_selected("device", "/device status", turn)
    await registry.finish(turn)
    await registry.close()


@pytest.mark.asyncio
async def test_replaced_provider_cannot_execute_prepared_template(registry):
    await registry.register("device", StatusProvider())
    turn = conversation.create_conversation_context("chat")
    await registry.prepare("/device status", turn)
    replacement = StatusProvider()
    await registry.register("device", replacement)
    with pytest.raises(
        conversation.ConversationProviderError, match="provider_disabled"
    ):
        await registry.handle_selected("device", "/device status", turn)
    replacement.handle.assert_not_awaited()
    await registry.finish(turn)
    await registry.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forced",
    [
        {"forced_tool": "git"},
        {"forced_provider": "openai"},
        {"forced_intent": "VERSION_CONTROL"},
    ],
)
async def test_forced_routes_preserve_existing_selection(registry, forced):
    provider = StatusProvider()
    await registry.register("device", provider)
    turn = conversation.create_conversation_context("chat")
    await registry.prepare("/device status", turn)
    classifier = AsyncMock(return_value="GENERAL_CHAT")
    orch = SimpleNamespace(
        intent_manager=SimpleNamespace(
            classify_intent=classifier, last_intent_debug={}
        ),
        request_tracer=None,
    )
    request = TaskRequest(content="/device status", **forced)
    with conversation.conversation_turn(turn):
        intent, _ = await dispatch._classify_intent_and_log(
            orch, uuid4(), request, request.content
        )
    assert intent != "MODULE_CONVERSATION"
    provider.handle.assert_not_awaited()
    await registry.finish(turn)
    await registry.close()


@pytest.mark.asyncio
async def test_provider_without_explicit_matcher_is_not_an_early_template(registry):
    provider = SimpleNamespace(handle=AsyncMock(return_value=None))
    await registry.register("legacy", provider)
    turn = conversation.create_conversation_context("chat")
    await registry.prepare("ordinary chat", turn)
    assert registry.match("ordinary chat", turn) is None
    assert await registry.handle("ordinary chat", turn) is None
    await registry.finish(turn)
    await registry.close()


@pytest.mark.parametrize(
    "content,expected",
    [
        ("status projektu", False),
        ("przeanalizuj status projektu", True),
        ("explain project status", True),
        ("analysiere Projektstatus", True),
    ],
)
@pytest.mark.asyncio
async def test_project_report_analysis_is_explicit(content, expected):
    request = TaskRequest(content=content)
    assert (resolve_response_template(request, "STATUS_REPORT") is None) == expected
    agent = ExecutiveAgent(
        Kernel(),
        SimpleNamespace(
            generate_roadmap_report=lambda: "current roadmap",
            get_vision=lambda: None,
            get_next_milestone=lambda: None,
        ),
    )
    agent.process = AsyncMock(return_value="analysis")
    result = await agent.generate_status_report(include_analysis=expected)
    assert "current roadmap" in result
    assert agent.process.await_count == int(expected)


@pytest.mark.parametrize(
    "method,updated",
    [
        ("_refresh_kernel", True),
        ("_refresh_kernel_if_needed", True),
        ("_refresh_kernel_if_needed", False),
    ],
)
def test_classifier_follows_executor_refresh(monkeypatch, method, updated):
    from venom_core.core.orchestrator import orchestrator_core

    old, new = Kernel(), Kernel()
    dispatcher = SimpleNamespace(kernel=new)
    orch = SimpleNamespace(
        intent_manager=SimpleNamespace(kernel=old),
        task_dispatcher=SimpleNamespace(kernel=old),
        kernel_manager=Mock(),
        flow_coordinator=Mock(),
    )
    function = (
        "refresh_kernel" if method == "_refresh_kernel" else "refresh_kernel_if_needed"
    )
    monkeypatch.setattr(
        orchestrator_core, function, lambda *args: dispatcher if updated else None
    )
    getattr(Orchestrator, method)(orch)
    assert orch.intent_manager.kernel is (new if updated else old)
    assert orch.intent_manager.kernel is orch.task_dispatcher.kernel


@pytest.mark.asyncio
async def test_selected_template_executes_only_after_global_policy(
    registry, monkeypatch
):
    provider = StatusProvider()
    await registry.register("device", provider)
    task = SimpleNamespace(context_history={})
    state = Mock()
    state.get_task.return_value = task
    state.update_context.side_effect = lambda _, values: task.context_history.update(
        values
    )
    orch = SimpleNamespace(
        state_manager=state,
        request_tracer=None,
        NON_LEARNING_INTENTS=set(),
        intent_manager=SimpleNamespace(
            classify_intent=AsyncMock(), requires_tool=Mock()
        ),
        context_builder=SimpleNamespace(
            preprocess_request=AsyncMock(), build_context=AsyncMock()
        ),
        result_processor=SimpleNamespace(process_error=AsyncMock()),
        _persist_session_context=Mock(),
        _is_perf_test_prompt=lambda _: False,
        validator=Mock(),
        _broadcast_event=AsyncMock(),
        _append_session_history=Mock(),
    )
    monkeypatch.setattr(
        dispatch, "_initialize_task_execution", AsyncMock(return_value=task)
    )
    policy = AsyncMock(return_value=True)
    monkeypatch.setattr(dispatch, "_handle_policy_block_global_pre_execution", policy)
    await dispatch.run_task(orch, uuid4(), TaskRequest(content="/device status"))
    policy.assert_awaited_once()
    provider.handle.assert_not_awaited()
    orch.intent_manager.classify_intent.assert_not_awaited()
    orch.result_processor.process_error.assert_not_awaited()
    assert not registry._prepared
    await registry.close()
