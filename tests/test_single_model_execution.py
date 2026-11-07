"""One chosen MAF service executes tasks through existing permission guards."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator.task_pipeline.execution_strategy import (
    ExecutionStrategy,
)
from venom_core.execution.agent_contracts import tool_function
from venom_core.execution.maf_runtime import AgentRuntime, MafChatService


def completion(text, calls=None):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "fixture",
        "object": "chat.completion",
        "created": 1,
        "model": "selected-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if calls else "stop",
            }
        ],
    }


def service(handler, service_id="selected", model_id="selected-model", capable=False):
    client = AsyncOpenAI(
        api_key="fixture",
        base_url="http://fixture.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    model = MafChatService(service_id, model_id, async_client=client)
    model.supports_function_calling = capable
    return model


def orchestrator(kernel):
    states = {}

    def update(task_id, values):
        states.setdefault(task_id, {}).update(values)

    return SimpleNamespace(
        task_dispatcher=SimpleNamespace(kernel=kernel),
        state_manager=SimpleNamespace(update_context=update),
        request_tracer=SimpleNamespace(add_step=Mock(), set_llm_metadata=Mock()),
        _trace_llm_start=Mock(),
        _should_use_council=Mock(side_effect=AssertionError("role routing reached")),
        states=states,
    )


class Tools:
    def __init__(self):
        self.effects = []

    @tool_function(name="echo", description="Return fixture text")
    def echo(self, text: str) -> str:
        self.effects.append(text)
        return "result:" + text


def test_task_mode_defaults_and_rejects_silent_service_selection():
    assert TaskRequest(content="hello").agent_mode == "auto"
    for kwargs in (
        {"agent_mode": "unknown"},
        {"model_service_id": "selected"},
        {"agent_mode": "single_model", "model_service_id": "http://endpoint.invalid"},
    ):
        with pytest.raises(ValidationError):
            TaskRequest(content="hello", **kwargs)


@pytest.mark.asyncio
async def test_selected_service_bypasses_role_routing_and_captures_actual_tools():
    requests = []
    tools = Tools()

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            call = {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "Safe-echo",
                    "arguments": '{"text":"once"}',
                },
            }
            return httpx.Response(200, json=completion(None, [call]))
        return httpx.Response(200, json=completion("verified response"))

    chosen = service(respond, capable=True)
    unused = service(
        lambda _: pytest.fail("other model selected"),
        service_id="other",
        model_id="other-model",
    )
    kernel = AgentRuntime(permission_checker=lambda _: True)
    kernel.add_service(unused)
    kernel.add_service(chosen)
    kernel.add_plugin(tools, "Safe")
    orch = orchestrator(kernel)
    task_id = uuid4()
    request = TaskRequest(
        content="do task", agent_mode="single_model", model_service_id="selected"
    )
    try:
        result = await ExecutionStrategy(orch).execute(
            task_id, "CODE_GENERATION", "do task", request
        )
        assert result == "verified response"
        assert tools.effects == ["once"]
        assert all(row["model"] == "selected-model" for row in requests)
        assert len(requests) == 2
        orch.request_tracer.set_llm_metadata.assert_called_once_with(
            task_id,
            model="selected-model",
            provider=None,
        )
        capture = orch.states[task_id]["gemma4_operator"]
        assert capture["capture_complete"] is True
        assert capture["experience_export"] == "requires_review"
        assert "training_allowed" not in capture
        assert capture["runtime_identity"]["model"] == "selected-model"
        assert [row["role"] for row in capture["messages"]] == [
            "system",
            "user",
            "assistant",
            "tool",
            "assistant",
        ]
        assert capture["messages"][2]["tool_calls"][0]["function"]["arguments"] == {
            "text": "once"
        }
        assert capture["messages"][3]["content"] == "result:once"
        assert capture["tools"][0]["function"]["name"] == "Safe-echo"
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
async def test_unknown_tool_capability_uses_direct_response_without_tools():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion("plain response"))

    model = service(respond)
    kernel = AgentRuntime(permission_checker=lambda _: True)
    kernel.add_service(model)
    kernel.add_plugin(Tools(), "Safe")
    orch = orchestrator(kernel)
    task_id = uuid4()
    try:
        result = await ExecutionStrategy(orch).execute(
            task_id,
            "COMPLEX_PLANNING",
            "hello",
            TaskRequest(content="hello", agent_mode="single_model"),
        )
        assert result == "plain response"
        assert "tools" not in requests[0]
        assert orch.states[task_id]["single_model_execution"]["tools_enabled"] is False
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
async def test_failure_after_tool_retains_observation_without_retrying_effect():
    requests = []
    tools = Tools()

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=completion(
                    None,
                    [
                        {
                            "id": "completed",
                            "type": "function",
                            "function": {
                                "name": "Safe-echo",
                                "arguments": '{"text":"once"}',
                            },
                        }
                    ],
                ),
            )
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    kernel = AgentRuntime(permission_checker=lambda _: True)
    kernel.add_service(service(respond, capable=True))
    kernel.add_plugin(tools, "Safe")
    orch = orchestrator(kernel)
    task_id = uuid4()
    request = TaskRequest(content="do task", agent_mode="single_model")
    strategy = ExecutionStrategy(orch)
    try:
        with pytest.raises(Exception, match="unavailable"):
            await strategy.execute(task_id, "GENERAL_CHAT", "do task", request)
        assert tools.effects == ["once"]
        capture = orch.states[task_id]["gemma4_operator"]
        assert capture["execution_status"] == "failed"
        assert capture["capture_complete"] is False
        assert capture["messages"][-1]["role"] == "tool"
        assert capture["messages"][-1]["content"] == "result:once"
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs", [{"forced_tool": "git"}, {"forced_provider": "openai"}]
)
async def test_conflicting_forced_routes_fail_before_invocation(kwargs):
    orch = orchestrator(
        SimpleNamespace(get_service=Mock(side_effect=AssertionError("called")))
    )
    request = TaskRequest(content="do task", agent_mode="single_model", **kwargs)
    task_id = uuid4()
    strategy = ExecutionStrategy(orch)
    with pytest.raises(ValueError, match="single_model_.*conflict"):
        await strategy.execute(task_id, "GENERAL_CHAT", "do task", request)
    orch.task_dispatcher.kernel.get_service.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_service_is_not_silently_replaced():
    kernel = AgentRuntime()
    orch = orchestrator(kernel)
    request = TaskRequest(
        content="do task", agent_mode="single_model", model_service_id="absent"
    )
    task_id = uuid4()
    strategy = ExecutionStrategy(orch)
    with pytest.raises(KeyError, match="absent"):
        await strategy.execute(task_id, "GENERAL_CHAT", "do task", request)


@pytest.mark.asyncio
async def test_auto_mode_preserves_existing_council_route():
    orch = SimpleNamespace(
        _should_use_council=Mock(return_value=True),
        run_council=AsyncMock(return_value="council"),
        _trace_llm_start=Mock(),
        state_manager=SimpleNamespace(add_log=Mock()),
        request_tracer=None,
    )
    assert (
        await ExecutionStrategy(orch).execute(
            uuid4(), "COMPLEX_PLANNING", "context", TaskRequest(content="plan")
        )
        == "council"
    )


@pytest.mark.asyncio
async def test_single_model_tools_keep_existing_permission_guard():
    tools = Tools()
    permission_checks = []
    requests = []

    def check(name):
        permission_checks.append(name)
        return False

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=completion(
                    None,
                    [
                        {
                            "id": "denied",
                            "type": "function",
                            "function": {
                                "name": "Safe-echo",
                                "arguments": '{"text":"forbidden"}',
                            },
                        }
                    ],
                ),
            )
        return httpx.Response(200, json=completion("operation denied"))

    kernel = AgentRuntime(permission_checker=check)
    kernel.add_service(service(respond, capable=True))
    kernel.add_plugin(tools, "Safe")
    orch = orchestrator(kernel)
    try:
        await ExecutionStrategy(orch).execute(
            uuid4(),
            "CODE_GENERATION",
            "do task",
            TaskRequest(content="do task", agent_mode="single_model"),
        )
        assert tools.effects == []
        assert permission_checks == ["Tools"]
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
async def test_cancellation_preserves_completed_effect_as_incomplete_evidence():
    import asyncio

    reached_continuation = asyncio.Event()
    requests = []
    tools = Tools()

    async def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=completion(
                    None,
                    [
                        {
                            "id": "once",
                            "type": "function",
                            "function": {
                                "name": "Safe-echo",
                                "arguments": '{"text":"once"}',
                            },
                        }
                    ],
                ),
            )
        reached_continuation.set()
        await asyncio.Event().wait()

    kernel = AgentRuntime(permission_checker=lambda _: True)
    kernel.add_service(service(respond, capable=True))
    kernel.add_plugin(tools, "Safe")
    orch = orchestrator(kernel)
    task_id = uuid4()
    task = asyncio.create_task(
        ExecutionStrategy(orch).execute(
            task_id,
            "CODE_GENERATION",
            "do task",
            TaskRequest(content="do task", agent_mode="single_model"),
        )
    )
    try:
        await asyncio.wait_for(reached_continuation.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert tools.effects == ["once"]
        capture = orch.states[task_id]["gemma4_operator"]
        assert capture["execution_status"] == "failed"
        assert capture["capture_complete"] is False
        assert capture["messages"][-1]["content"] == "result:once"
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await kernel.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "allowlist,qualified",
    [
        ([], False),
        (["selected|selected-model"], True),
        (["selected|other-model"], False),
    ],
)
async def test_kernel_builder_qualification_is_exact_model_service_pair(
    allowlist, qualified
):
    from venom_core.execution.kernel_builder import KernelBuilder

    builder = KernelBuilder.__new__(KernelBuilder)
    builder.settings = SimpleNamespace(
        LLM_LOCAL_API_KEY="fixture",
        SINGLE_MODEL_TOOL_CALLING_ALLOWLIST=allowlist,
    )
    kernel = AgentRuntime()
    builder._register_local_http_service(
        kernel,
        "selected",
        "selected-model",
        "http://fixture.invalid/v1",
    )
    try:
        assert kernel.get_service("selected").supports_function_calling is qualified
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
async def test_single_model_skips_classifier_before_execution_strategy():
    from venom_core.core.orchestrator.orchestrator_dispatch import (
        _classify_intent_and_log,
    )

    classifier = AsyncMock(
        side_effect=AssertionError("different model classifier invoked")
    )
    orch = SimpleNamespace(
        intent_manager=SimpleNamespace(classify_intent=classifier), request_tracer=None
    )
    request = TaskRequest(content="diagnose", agent_mode="single_model")
    intent, details = await _classify_intent_and_log(
        orch, uuid4(), request, request.content
    )
    assert intent == "GENERAL_CHAT"
    assert details["source"] == "single_model"
    classifier.assert_not_called()


def test_incomplete_pending_tool_capture_retains_observed_call():
    from agent_framework import Content

    from venom_core.core.orchestrator.task_pipeline.single_model import _record_trace
    from venom_core.execution.agent_contracts import (
        ConversationHistory,
        ConversationMessage,
    )

    history = ConversationHistory()
    history.add_user_message("perform")
    call = Content.from_function_call(
        call_id="pending", name="Safe-echo", arguments={"text": "x"}
    )
    history.add_message(
        ConversationMessage(
            "assistant", native_message=SimpleNamespace(contents=[call])
        )
    )
    orch = orchestrator(None)
    task_id = uuid4()
    _record_trace(
        orch,
        task_id,
        SimpleNamespace(ai_model_id="fixture", service_id="chosen"),
        history,
        [],
        False,
    )
    capture = orch.states[task_id]["gemma4_operator"]
    assert capture["capture_complete"] is False
    assert capture["messages"][-1]["tool_calls"][0]["id"] == "pending"


def test_mixed_unsupported_payload_cannot_claim_complete_capture():
    from agent_framework import Content

    from venom_core.core.orchestrator.task_pipeline.single_model import _record_trace
    from venom_core.execution.agent_contracts import (
        ConversationHistory,
        ConversationMessage,
    )

    history = ConversationHistory()
    history.add_user_message("perform")
    call = Content.from_function_call(
        call_id="pending", name="Safe-echo", arguments={"text": "x"}
    )
    history.add_message(
        ConversationMessage(
            "assistant",
            native_message=SimpleNamespace(
                contents=[call, SimpleNamespace(type="image")],
            ),
        )
    )
    orch = orchestrator(None)
    task_id = uuid4()
    _record_trace(
        orch,
        task_id,
        SimpleNamespace(ai_model_id="fixture", service_id="chosen"),
        history,
        [],
        True,
    )
    capture = orch.states[task_id]["gemma4_operator"]
    assert capture["capture_complete"] is False
    assert capture["messages"] == [{"role": "user", "content": "perform"}]


def test_reused_call_id_after_completed_result_is_incomplete():
    from agent_framework import Content

    from venom_core.core.orchestrator.task_pipeline.single_model import (
        _canonical_messages,
    )
    from venom_core.execution.agent_contracts import (
        ConversationHistory,
        ConversationMessage,
    )

    call = Content.from_function_call(
        call_id="duplicate", name="Safe-echo", arguments={"text": "x"}
    )
    result = Content.from_function_result(call_id="duplicate", result="actual")
    history = ConversationHistory()
    for role, content in (("assistant", call), ("tool", result), ("assistant", call)):
        history.add_message(
            ConversationMessage(
                role, native_message=SimpleNamespace(contents=[content])
            )
        )
    captured, complete = _canonical_messages(history)
    assert complete is False
    assert [row["role"] for row in captured] == ["assistant", "tool"]


def test_policy_context_uses_actual_selected_service_provider():
    from venom_core.core.orchestrator.orchestrator_dispatch import (
        _resolve_planned_provider,
    )

    selected = SimpleNamespace(operator_provider="openai", runtime_provider=None)
    kernel = SimpleNamespace(get_service=Mock(return_value=selected))
    orch = orchestrator(kernel)
    request = TaskRequest(
        content="task", agent_mode="single_model", model_service_id="cloud_high"
    )
    assert _resolve_planned_provider(orch, uuid4(), request) == "openai"
    kernel.get_service.assert_called_once_with("cloud_high")


def test_unknown_selected_provider_is_rejected_before_global_checkpoint():
    from venom_core.core.orchestrator.orchestrator_dispatch import (
        _resolve_planned_provider,
    )

    kernel = SimpleNamespace(get_service=Mock(return_value=SimpleNamespace()))
    orch = orchestrator(kernel)
    request = TaskRequest(
        content="task", agent_mode="single_model", model_service_id="unknown"
    )
    task_id = uuid4()
    with pytest.raises(ValueError, match="provider_identity_missing"):
        _resolve_planned_provider(orch, task_id, request)


def test_single_model_rejects_image_prepass_but_auto_preserves_images():
    assert TaskRequest(content="look", images=["image-reference"]).images == [
        "image-reference"
    ]
    with pytest.raises(ValidationError, match="native_adapter"):
        TaskRequest(
            content="look", agent_mode="single_model", images=["image-reference"]
        )
    with pytest.raises(ValidationError, match="preferred_language_unsupported"):
        TaskRequest(
            content="look",
            agent_mode="single_model",
            preferred_language="injected instructions",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "single_model"])
async def test_actual_context_builder_uses_stored_history_without_single_model_prepasses(
    monkeypatch, mode
):
    from venom_core.core.orchestrator.session_handler import SessionHandler
    from venom_core.core.orchestrator.task_pipeline import context_builder

    task = SimpleNamespace(
        context_history={
            "session_history": [{"role": "user", "content": "stored history"}],
            "session_summary": "stored summary",
        }
    )
    state = SimpleNamespace(
        get_task=Mock(return_value=task), update_context=Mock(), add_log=Mock()
    )
    handler = SessionHandler(state, Mock(), testing_mode=False)
    handler._ensure_session_summary = Mock()
    handler._ensure_summary_if_needed = Mock(
        side_effect=lambda request, task_id, session_id, summary, history: summary
    )
    handler._attach_memory_block = Mock()
    orch = SimpleNamespace(
        state_manager=state,
        _build_session_context_block=handler.build_session_context_block,
        _get_runtime_context_char_limit=Mock(return_value=4096),
    )
    monkeypatch.setattr(
        context_builder,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(provider="local"),
    )
    request = TaskRequest(content="new question", agent_mode=mode)
    context = await context_builder.ContextBuilder(orch).build_context(
        uuid4(), request, fast_path=False
    )
    assert "stored history" in context
    assert "new question" in context
    if mode == "single_model":
        handler._ensure_session_summary.assert_not_called()
        handler._ensure_summary_if_needed.assert_not_called()
        handler._attach_memory_block.assert_not_called()
    else:
        handler._ensure_session_summary.assert_called_once()
        handler._ensure_summary_if_needed.assert_called_once()
        handler._attach_memory_block.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected", [("auto", "translated"), ("single_model", "original")]
)
async def test_result_processor_has_no_second_translator_in_single_model(
    monkeypatch, mode, expected
):
    from venom_core.core.orchestrator.task_pipeline import result_processor

    monkeypatch.setattr(result_processor.metrics_module, "metrics_collector", None)
    translator = AsyncMock(return_value="translated")
    state = SimpleNamespace(
        update_status=AsyncMock(), add_log=Mock(), update_context=Mock()
    )
    orch = SimpleNamespace(
        _apply_preferred_language=translator,
        task_dispatcher=SimpleNamespace(agent_map={}),
        state_manager=state,
        _append_session_history=Mock(),
        request_tracer=None,
        _should_store_lesson=Mock(return_value=False),
        lessons_manager=SimpleNamespace(should_log_learning=Mock(return_value=False)),
        _broadcast_event=AsyncMock(),
    )
    request = TaskRequest(content="question", agent_mode=mode, preferred_language="pl")
    await result_processor.ResultProcessor(orch).process_success(
        uuid4(),
        "original",
        "GENERAL_CHAT",
        "context",
        request,
        False,
    )
    assert state.update_status.call_args.kwargs["result"] == expected
    if mode == "single_model":
        translator.assert_not_called()
    else:
        translator.assert_called_once()


@pytest.mark.asyncio
async def test_single_model_result_retains_real_session_without_model_backed_postpasses(
    tmp_path, monkeypatch
):
    from venom_core.core.orchestrator.session_handler import SessionHandler
    from venom_core.core.orchestrator.task_pipeline import result_processor
    from venom_core.services.session_store import SessionStore

    monkeypatch.setattr(result_processor.metrics_module, "metrics_collector", None)
    task = SimpleNamespace(context_history={})
    state = SimpleNamespace(
        get_task=Mock(return_value=task),
        update_status=AsyncMock(),
        update_context=Mock(),
        add_log=Mock(),
    )
    store = SessionStore(store_path=str(tmp_path / "single-model-session.json"))
    handler = SessionHandler(state, Mock(), session_store=store, testing_mode=False)
    handler._memory_upsert = Mock(side_effect=AssertionError("embedding model invoked"))
    handler._ensure_session_summary = Mock(
        side_effect=AssertionError("summary model invoked")
    )
    translator = AsyncMock(side_effect=AssertionError("translator model invoked"))
    lessons = SimpleNamespace(
        save_task_lesson=AsyncMock(side_effect=AssertionError("lesson model invoked")),
        should_log_learning=Mock(
            side_effect=AssertionError("legacy learning eligibility invoked")
        ),
        append_learning_log=Mock(
            side_effect=AssertionError("legacy llm-only success log invoked")
        ),
    )
    tracer = SimpleNamespace(update_status=Mock(), add_step=Mock())
    orch = SimpleNamespace(
        _apply_preferred_language=translator,
        task_dispatcher=SimpleNamespace(agent_map=Mock()),
        state_manager=state,
        session_handler=handler,
        _append_session_history=handler.append_session_history,
        request_tracer=tracer,
        _should_store_lesson=Mock(
            side_effect=AssertionError("legacy lesson eligibility invoked")
        ),
        lessons_manager=lessons,
        _broadcast_event=AsyncMock(),
    )
    request = TaskRequest(
        content="question",
        agent_mode="single_model",
        session_id="session",
        store_knowledge=True,
        preferred_language="pl",
    )
    task_id = uuid4()
    await result_processor.ResultProcessor(orch).process_success(
        task_id,
        "model result",
        "GENERAL_CHAT",
        "context",
        request,
        False,
    )
    state.update_status.assert_awaited_once()
    assert task.context_history["session_history"][-1]["content"] == "model result"
    assert store.get_history("session")[-1]["content"] == "model result"
    assert store.get_summary("session") is None
    handler._ensure_session_summary.assert_not_called()
    handler._memory_upsert.assert_not_called()
    translator.assert_not_called()
    orch._should_store_lesson.assert_not_called()
    lessons.save_task_lesson.assert_not_called()
    lessons.should_log_learning.assert_not_called()
    lessons.append_learning_log.assert_not_called()
    orch.task_dispatcher.agent_map.get.assert_not_called()
    selected = [
        call
        for call in tracer.add_step.call_args_list
        if call.args[1] == "SelectedModel"
    ]
    assert len(selected) == 1


@pytest.mark.asyncio
async def test_auto_result_keeps_existing_memory_lessons_and_learning_policy(
    monkeypatch,
):
    from venom_core.core.orchestrator.task_pipeline import result_processor

    monkeypatch.setattr(result_processor.metrics_module, "metrics_collector", None)
    handler = SimpleNamespace(_memory_upsert=Mock())
    lessons = SimpleNamespace(
        save_task_lesson=AsyncMock(),
        should_log_learning=Mock(return_value=True),
        append_learning_log=Mock(),
    )
    orch = SimpleNamespace(
        _apply_preferred_language=AsyncMock(return_value="translated"),
        task_dispatcher=SimpleNamespace(agent_map={"GENERAL_CHAT": Mock()}),
        state_manager=SimpleNamespace(
            update_status=AsyncMock(), update_context=Mock(), add_log=Mock()
        ),
        session_handler=handler,
        _append_session_history=Mock(),
        request_tracer=None,
        _should_store_lesson=Mock(return_value=True),
        lessons_manager=lessons,
        _broadcast_event=AsyncMock(),
    )
    request = TaskRequest(
        content="question", session_id="session", store_knowledge=True
    )
    await result_processor.ResultProcessor(orch).process_success(
        uuid4(),
        "original",
        "GENERAL_CHAT",
        "context",
        request,
        False,
    )
    orch._apply_preferred_language.assert_awaited_once()
    handler._memory_upsert.assert_called_once()
    lessons.save_task_lesson.assert_awaited_once()
    lessons.should_log_learning.assert_called_once()
    lessons.append_learning_log.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,intent",
    [
        ("auto", "GENERAL_CHAT"),
        ("single_model", "GENERAL_CHAT"),
        ("single_model", "MODULE_CONVERSATION"),
    ],
)
async def test_callback_dispatch_respects_single_model_before_conversation_provider(
    monkeypatch, mode, intent
):
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    provider = AsyncMock(return_value="intercepted")
    strategy = AsyncMock(return_value="selected model")
    monkeypatch.setattr(dispatch, "handle_conversation_turn", provider)
    monkeypatch.setattr(
        dispatch, "get_active_llm_runtime", lambda: SimpleNamespace(provider="local")
    )
    monkeypatch.setattr(dispatch, "current_conversation_context", lambda: None)
    monkeypatch.setattr(
        dispatch, "ExecutionStrategy", lambda orch: SimpleNamespace(execute=strategy)
    )
    callback = Mock()
    orch = SimpleNamespace(
        streaming_handler=SimpleNamespace(
            create_stream_callback=Mock(return_value=callback)
        ),
        request_tracer=None,
    )
    request = TaskRequest(content="question", agent_mode=mode)
    result = await dispatch._execute_with_stream_callback(
        orch, uuid4(), intent, "context", request
    )
    if mode == "single_model":
        assert result == "selected model"
        provider.assert_not_called()
        strategy.assert_awaited_once()
    else:
        assert result == "intercepted"
        provider.assert_awaited_once()
        strategy.assert_not_called()
        callback.assert_called_once_with("intercepted")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params,wire_key,limit",
    [
        (None, "max_tokens", 1024),
        ({"max_tokens": 37}, "max_tokens", 37),
        ({"max_new_tokens": 43}, "max_tokens", 43),
        ({"num_predict": 47}, "max_tokens", 47),
        ({"max_completion_tokens": 53}, "max_completion_tokens", 53),
    ],
)
async def test_single_model_token_limit_alias_reaches_actual_transport(
    params, wire_key, limit
):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion("response"))

    kernel = AgentRuntime()
    kernel.add_service(service(respond))
    orch = orchestrator(kernel)
    request = TaskRequest(
        content="question", agent_mode="single_model", generation_params=params
    )
    try:
        await ExecutionStrategy(orch).execute(
            uuid4(), "GENERAL_CHAT", "question", request
        )
        assert requests[0][wire_key] == limit
        other = (
            "max_tokens"
            if wire_key == "max_completion_tokens"
            else "max_completion_tokens"
        )
        assert other not in requests[0]
    finally:
        await kernel.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,intent",
    [
        ("single_model", "MODULE_CONVERSATION"),
        ("single_model", "HELP"),
        ("auto", "MODULE_CONVERSATION"),
    ],
)
async def test_forced_intent_keeps_selected_model_context(monkeypatch, mode, intent):
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    builder = AsyncMock(return_value="stored history and summary\\nquestion")
    orch = SimpleNamespace(
        context_builder=SimpleNamespace(build_context=builder),
        state_manager=SimpleNamespace(add_log=Mock()),
    )
    monkeypatch.setattr(dispatch, "resolve_response_template", lambda *_: object())
    request = TaskRequest(content="question", agent_mode=mode, forced_intent=intent)
    task_id = uuid4()
    result = await dispatch._build_context_for_intent(
        orch, task_id, request, request.content, intent, False
    )
    if mode == "single_model":
        assert "stored history and summary" in result
        builder.assert_awaited_once_with(task_id, request, False)
    else:
        assert result == "question"
        builder.assert_not_called()


@pytest.mark.parametrize(
    "request_fields",
    [
        {"model_tools": ["FileSkill-read_file"]},
        {"agent_mode": "single_model", "model_tools": ["FileSkill-write_file"]},
    ],
)
def test_task_rejects_model_tools_outside_read_only_single_model(request_fields):
    """Reject out-of-scope tools and tools on non-single-model requests."""
    with pytest.raises(ValidationError):
        TaskRequest(content="read", **request_fields)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id,capable,requested,expected",
    [
        ("gemma4:e4b", True, ["FileSkill-read_file"], ["FileSkill-read_file"]),
        ("gemma4:e4b", True, None, []),
        ("gemma4:e4b", False, ["FileSkill-read_file"], None),
        ("selected-model", True, ["FileSkill-read_file"], None),
        ("selected-model", True, [], None),
    ],
)
async def test_e4b_sends_only_task_tools_and_records_same_catalog(
    tmp_path, model_id, capable, requested, expected
):
    """Keep the offered and recorded tool catalogs scoped to the request."""
    from venom_core.execution.skills.file_skill import FileSkill

    requests = []

    def respond(request):
        """Produce the completion returned by the fake model."""
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion("response"))

    kernel = AgentRuntime()
    kernel.add_service(service(respond, model_id=model_id, capable=capable))
    kernel.add_plugin(FileSkill(str(tmp_path)), "FileSkill")
    kernel.add_plugin(Tools(), "Safe")
    orch = orchestrator(kernel)
    task_id = uuid4()
    request = TaskRequest(
        content="read", agent_mode="single_model", model_tools=requested
    )

    async def execute():
        """Record the resolved tool options in the fake native runtime."""
        return await ExecutionStrategy(orch).execute(
            task_id, "GENERAL_CHAT", "read", request
        )

    try:
        if expected is None:
            with pytest.raises(ValueError, match="model_tools_require_qualified"):
                await execute()
            assert requests == []
        else:
            assert await execute() == "response"
            assert len(requests) == 1
            wire = requests[0].get("tools") or []
            trace = orch.states[task_id]["gemma4_operator"]["tools"]
            assert [tool["function"]["name"] for tool in wire] == expected
            assert [tool["function"]["name"] for tool in trace] == expected
    finally:
        await kernel.aclose()


@pytest.mark.parametrize(
    "language,link_label,scope",
    [
        ("en", "[symlink]", "nested contents were not inspected"),
        ("pl", "[dowiązanie]", "bez zaglądania do podkatalogów"),
        ("de", "[symbolischer Link]", "Unterordner wurden nicht durchsucht"),
    ],
)
def test_fileskill_listing_reports_tool_type_and_scope(language, link_label, scope):
    """Render observed listing output with the original tool scope."""
    from agent_framework import Content

    from venom_core.core.orchestrator.task_pipeline.single_model import (
        _fileskill_listing_answer,
    )
    from venom_core.execution.agent_contracts import (
        ConversationHistory,
        ConversationMessage,
    )

    history = ConversationHistory()
    call = Content.from_function_call(
        call_id="listing",
        name="FileSkill-list_files",
        arguments={"directory": "sample"},
    )
    result = Content.from_function_result(
        call_id="listing",
        result="Zawartość katalogu 'sample':\n  [dowiązanie] sample/incoming\n  [katalog] sample/archive",
    )
    for role, content in (("assistant", call), ("tool", result)):
        history.add_message(
            ConversationMessage(
                role, native_message=SimpleNamespace(contents=[content])
            )
        )
    answer = _fileskill_listing_answer(history, language)
    assert answer is not None
    assert scope in answer
    assert f"{link_label} sample/incoming" in answer


@pytest.mark.parametrize(
    ("content", "preferred", "expected"),
    [
        ("List files in 'Żółty Brzeg'", None, "en"),
        ("Bitte zeige die Dateien", None, "de"),
        ("Wypisz pliki w katalogu", None, "pl"),
        ("List files", "de", "de"),
    ],
)
def test_file_answer_language_uses_request_when_preference_is_absent(
    content, preferred, expected
):
    """Detect short listing commands and honor an explicit language choice."""
    from venom_core.core.orchestrator.task_pipeline.single_model import (
        _file_answer_language,
    )

    assert (
        _file_answer_language(
            TaskRequest(content=content, preferred_language=preferred)
        )
        == expected
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model, tool, argument, value, allowed, model_answer, expected",
    [
        ("gemma4:e4b", "read_file", "file_path", "note.txt", True, "", "verified note"),
        (
            "gemma4:e4b",
            "read_file",
            "file_path",
            "large.txt",
            True,
            "",
            "x" * 4000 + "…",
        ),
        ("gemma4:e4b", "read_file", "file_path", "empty.txt", True, "", "(∅)"),
        ("gemma4:e4b", "file_exists", "file_path", "absent", True, "", "False"),
        (
            "gemma4:e4b",
            "read_file",
            "file_path",
            "../forbidden.txt",
            True,
            "",
            "Odmowa dostępu",
        ),
        (
            "gemma4:e4b",
            "read_file",
            "file_path",
            "note.txt",
            False,
            "",
            "Access denied.",
        ),
        ("gemma4:e4b", "read_file", "file_path", "note.txt", True, "real reply", None),
        (
            "functiongemma",
            "read_file",
            "file_path",
            "note.txt",
            True,
            "",
            "verified note",
        ),
    ],
)
async def test_single_model_surfaces_recorded_evidence_after_blank_reply(
    tmp_path, model, tool, argument, value, allowed, model_answer, expected
):
    from venom_core.execution.skills.file_skill import FileSkill

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("verified note")
    (workspace / "large.txt").write_text("x" * 5000)
    (workspace / "empty.txt").touch()
    (tmp_path / "forbidden.txt").write_text("outside workspace marker")
    requests = []
    name = f"FileSkill-{tool}"

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) > 1:
            return httpx.Response(200, json=completion(model_answer))
        call = {
            "id": "observed",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps({argument: value})},
        }
        return httpx.Response(200, json=completion(None, [call]))

    kernel = AgentRuntime(permission_checker=lambda _: allowed)
    kernel.add_service(service(respond, model_id=model, capable=True))
    kernel.add_plugin(FileSkill(str(workspace)), "FileSkill")
    orch = orchestrator(kernel)
    task_id = uuid4()
    request = TaskRequest(
        content="Check the requested path",
        agent_mode="single_model",
        model_tools=[name] if model == "gemma4:e4b" else None,
    )

    try:
        answer = await ExecutionStrategy(orch).execute(
            task_id, "GENERAL_CHAT", request.content, request
        )
    finally:
        await kernel.aclose()

    assert len(requests) == 2
    trace = orch.states[task_id]["gemma4_operator"]["messages"]
    assert trace[-1]["role"] == "assistant"
    assert trace[-1]["content"] == model_answer
    if expected is None:
        assert answer == model_answer
    else:
        assert "The model did not finish" in answer
        assert f"{name}:\n\n    " in answer
        assert expected in answer
        assert "outside workspace marker" not in answer


@pytest.mark.asyncio
async def test_single_model_does_not_create_fallback_without_tool_evidence(tmp_path):
    from venom_core.execution.skills.file_skill import FileSkill

    kernel = AgentRuntime()
    kernel.add_service(
        service(
            lambda _: httpx.Response(200, json=completion("")),
            model_id="gemma4:e4b",
            capable=True,
        )
    )
    kernel.add_plugin(FileSkill(str(tmp_path)), "FileSkill")
    request = TaskRequest(
        content="Read a file",
        agent_mode="single_model",
        model_tools=["FileSkill-read_file"],
    )
    try:
        assert (
            await ExecutionStrategy(orchestrator(kernel)).execute(
                uuid4(), "GENERAL_CHAT", request.content, request
            )
            == ""
        )
    finally:
        await kernel.aclose()
