import asyncio
import json
from contextlib import asynccontextmanager, nullcontext
from dataclasses import FrozenInstanceError
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from venom_core.services import conversation_providers as conversation
from venom_core.services import module_registry


@pytest.fixture(autouse=True)
def isolated_registry():
    previous = conversation.set_conversation_registry(None)
    yield
    conversation.set_conversation_registry(previous)


class Provider:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def handle(self, text, context):
        assert conversation.current_conversation_context() is context
        self.calls.append((text, context))
        return "handled" if text.startswith("/extension") else None

    async def close(self):
        self.closed = True


def context(actor="chat", **kwargs):
    return conversation.create_conversation_context(
        actor, task_id="task", conversation_id="conversation", **kwargs
    )


@pytest.mark.asyncio
async def test_one_entrypoint_for_both_actors_and_context_reset():
    registry = conversation.ConversationProviderRegistry(SimpleNamespace())
    provider = Provider()
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    for actor in ("chat", "voice"):
        turn = context(actor)
        assert (
            await conversation.handle_conversation_turn("/extension", turn) == "handled"
        )
        assert provider.calls[-1][1].actor == actor
        assert conversation.current_conversation_context() is None
    assert await registry.handle("ordinary chat", context()) is None
    await registry.close()
    assert provider.closed


def test_context_is_frozen_and_identifiers_are_only_correlation():
    turn = context(language="de")
    assert turn.actor == "chat" and turn.language == "de"
    assert turn.target_device_id is None and turn.deadline > turn.created_at
    with pytest.raises(FrozenInstanceError):
        turn.actor = "voice"
    with conversation.conversation_turn(turn):
        assert conversation.current_conversation_context() is turn
    assert conversation.current_conversation_context() is None


def test_direct_authenticated_host_context_defaults_deadline_and_retains_target():
    turn = conversation.ConversationContext(
        task_id="authenticated-task",
        conversation_id="correlation-only",
        actor="voice",
        created_at=100.0,
        target_device_id="fixture-device",
    )
    assert turn.deadline == 130.0 and turn.target_device_id == "fixture-device"


@pytest.mark.parametrize(
    "change",
    [
        {"actor": "model"},
        {"language": "xx"},
        {"created_at": float("nan")},
        {"deadline": float("inf")},
        {"deadline": 0},
        {"task_id": ""},
    ],
)
def test_invalid_host_context_is_rejected(change):
    values = dict(task_id="t", conversation_id="c", actor="chat")
    values.update(change)
    with pytest.raises(ValueError):
        conversation.ConversationContext(**values)


@pytest.mark.asyncio
async def test_concurrent_turns_and_nested_contexts_are_isolated():
    registry = conversation.ConversationProviderRegistry(None)
    seen = []

    class Concurrent:
        async def handle(self, text, turn):
            await asyncio.sleep(0)
            seen.append(
                (turn.task_id, conversation.current_conversation_context().task_id)
            )
            return text

    await registry.register("example", Concurrent())
    outer = context()
    with conversation.conversation_turn(outer):
        turns = [
            conversation.create_conversation_context("chat", task_id=f"t{i}")
            for i in range(4)
        ]
        assert await asyncio.gather(
            *(registry.handle(str(i), turn) for i, turn in enumerate(turns))
        ) == ["0", "1", "2", "3"]
        assert conversation.current_conversation_context() is outer
    assert all(left == right for left, right in seen)
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_provider_errors_and_timeout_are_explicit_and_reset_context():
    registry = conversation.ConversationProviderRegistry(None)

    class Failed:
        async def handle(self, text, turn):
            if text == "timeout":
                await asyncio.sleep(1)
            raise RuntimeError("private failure")

    await registry.register("example", Failed())
    for text, timeout, code in [
        ("error", 30, "conversation_provider_failed"),
        ("timeout", 0.01, "conversation_deadline"),
    ]:
        with pytest.raises(conversation.ConversationProviderError, match=code):
            await registry.handle(text, context(timeout_s=timeout))
        assert conversation.current_conversation_context() is None
    await registry.close()
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_registry_closed"
    ):
        await registry.handle("any", context())


@pytest.mark.asyncio
async def test_disabled_provider_is_removed_closed_and_inflight_cancelled():
    started = asyncio.Event()

    class Waiting(Provider):
        async def handle(self, text, turn):
            started.set()
            await asyncio.Event().wait()

    provider = Waiting()
    enabled = True

    def factory(app):
        return provider

    registry = conversation.ConversationProviderRegistry(
        None, lambda: {"example": factory} if enabled else {}
    )
    active = asyncio.create_task(registry.handle("/extension", context()))
    await started.wait()
    enabled = False
    await registry.refresh()
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_disabled"
    ):
        await active
    assert provider.closed and not registry.providers
    assert await registry.handle("ordinary", context()) is None


@pytest.mark.asyncio
async def test_invalid_provider_and_output_fail_without_fallback():
    registry = conversation.ConversationProviderRegistry(None)
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_invalid"
    ):
        await registry.register("example", SimpleNamespace(handle=lambda *_: None))

    class Invalid:
        async def handle(self, text, turn):
            return "x" * 32769

    await registry.register("example", Invalid())
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_invalid_output"
    ):
        await registry.handle("x", context())
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_typed_tool_catalog_is_optional_disabled_and_detached_from_kernel():
    registry = conversation.ConversationProviderRegistry(None)

    class Tools(Provider):
        enabled = True
        metadata = [
            {
                "name": "example.status",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

        def list_tools(self):
            return self.metadata if self.enabled else []

    provider = Tools()
    await registry.register("example", provider)
    listed = await registry.list_tools()
    assert listed["example"][0]["name"] == "example.status"
    listed["example"][0]["name"] = "modified by client"
    assert provider.metadata[0]["name"] == "example.status"
    provider.enabled = False
    assert await registry.list_tools() == {"example": []}
    await registry.unregister("example")
    assert await registry.list_tools() == {}
    await registry.close()
    assert await registry.list_tools() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tools",
    [
        None,
        {},
        ["bad"],
        [{}] * 65,
        [{"value": float("nan")}],
        [{"value": object()}],
        [{"name": "x" * (256 * 1024)}],
    ],
)
async def test_tool_catalog_rejects_unbounded_or_non_json_metadata(tools):
    registry = conversation.ConversationProviderRegistry(None)

    class InvalidTools(Provider):
        async def list_tools(self):
            return tools

    await registry.register("example", InvalidTools())
    with pytest.raises(
        conversation.ConversationProviderError,
        match="conversation_invalid_tool_catalog",
    ):
        await registry.list_tools()


@pytest.mark.asyncio
async def test_factory_replacement_and_optional_close():
    providers = []

    async def first(app):
        instance = Provider()
        providers.append(instance)
        return instance

    active_factory = first
    registry = conversation.ConversationProviderRegistry(
        None, lambda: {"example": active_factory}
    )
    await registry.refresh()
    assert await registry.handle("/extension", context()) == "handled"

    def second(app):
        return SimpleNamespace(handle=AsyncMock(return_value=None))

    active_factory = second
    await registry.refresh()
    assert providers[0].closed
    assert await registry.list_tools() == {}
    await registry.close()
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_registry_closed"
    ):
        await registry.register("example", Provider())


@pytest.mark.asyncio
async def test_shutdown_closes_every_provider_even_when_one_close_fails():
    registry = conversation.ConversationProviderRegistry(None)
    good = Provider()

    class Bad(Provider):
        def close(self):
            raise RuntimeError("private close detail")

    await registry.register("first", Bad())
    await registry.register("second", good)
    with pytest.raises(
        conversation.ConversationProviderError,
        match="conversation_provider_close_failed",
    ) as raised:
        await registry.close()
    assert raised.value.module_id == "first"
    assert good.closed and not registry.providers
    assert await registry.list_tools() == {}


@pytest.mark.asyncio
async def test_shutdown_during_factory_closes_unpublished_provider():
    started, release = asyncio.Event(), asyncio.Event()
    provider = Provider()

    async def factory(app):
        started.set()
        await release.wait()
        return provider

    registry = conversation.ConversationProviderRegistry(
        None, lambda: {"example": factory}
    )
    refreshing = asyncio.create_task(registry.refresh())
    await started.wait()
    shutting_down = asyncio.create_task(registry.close())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(refreshing, shutting_down)
    assert registry.closed and provider.closed and not registry.providers
    await registry.refresh()


@pytest.mark.asyncio
async def test_invalid_and_expired_contexts_never_invoke_provider():
    registry = conversation.ConversationProviderRegistry(None)
    provider = Provider()
    await registry.register("example", provider)
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_context_required"
    ):
        await registry.handle("/extension", None)
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_deadline"
    ):
        await registry.handle("/extension", context(timeout_s=0))
    assert not provider.calls
    await registry.unregister("missing")
    await registry.close()


@pytest.mark.asyncio
async def test_disabled_provider_cannot_return_after_suppressing_cancellation():
    started = asyncio.Event()

    class Suppressing(Provider):
        async def handle(self, text, turn):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "stale response"

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Suppressing())
    running = asyncio.create_task(registry.handle("/extension", context()))
    await started.wait()
    await registry.unregister("example")
    with pytest.raises(
        conversation.ConversationProviderError,
        match="conversation_provider_disabled",
    ):
        await running
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_chat_provider_preserves_trace_streaming_and_bypasses_dispatcher(
    monkeypatch,
):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    registry = conversation.ConversationProviderRegistry(None)
    provider = Provider()
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    monkeypatch.setattr(
        dispatch,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(provider="multi_runtime"),
    )
    strategy = Mock()
    monkeypatch.setattr(dispatch, "ExecutionStrategy", strategy)
    callback = Mock()
    orch = SimpleNamespace(
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: callback),
        request_tracer=Mock(),
    )
    task_id = uuid4()
    request = TaskRequest(
        content="/extension", session_id="actual-conversation", preferred_language="en"
    )
    assert (
        await dispatch._execute_with_stream_callback(
            orch, task_id, "GENERAL_CHAT", "enriched unsafe old context", request
        )
        == "handled"
    )
    strategy.assert_not_called()
    callback.assert_called_once_with("handled")
    turn = provider.calls[0][1]
    assert (
        turn.task_id == str(task_id) and turn.conversation_id == "actual-conversation"
    )
    assert turn.actor == "chat" and turn.language == "en"
    assert provider.calls[0][0] == "/extension"
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_ordinary_chat_and_native_voice_keep_existing_behavior(monkeypatch):
    from venom_core.api.audio_stream import _invoke_operator_agent
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Provider())
    conversation.set_conversation_registry(registry)
    monkeypatch.setattr(
        dispatch, "get_active_llm_runtime", lambda: SimpleNamespace(provider="ollama")
    )
    execution = AsyncMock(return_value="normal chat")
    monkeypatch.setattr(
        dispatch, "ExecutionStrategy", lambda _: SimpleNamespace(execute=execution)
    )
    orch = SimpleNamespace(
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: Mock())
    )
    request = TaskRequest(content="ordinary", session_id="normal")
    assert (
        await dispatch._execute_with_stream_callback(
            orch, uuid4(), "GENERAL_CHAT", "context", request
        )
        == "normal chat"
    )
    execution.assert_awaited_once()
    operator = SimpleNamespace(process=AsyncMock(return_value="normal voice"))
    assert (
        await _invoke_operator_agent(
            operator, "ordinary", mode="standard", conversation_id="voice-connection"
        )
        == "normal voice"
    )
    operator.process.assert_awaited_once()
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_native_voice_extension_precedes_legacy_gpio_and_ignores_actor_claims():
    from venom_core.api.audio_stream import _invoke_operator_agent

    registry = conversation.ConversationProviderRegistry(None)
    provider = Provider()
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    operator = SimpleNamespace(
        process=AsyncMock(side_effect=AssertionError("legacy GPIO invoked"))
    )
    assert (
        await _invoke_operator_agent(
            operator,
            "/extension",
            mode="standard",
            conversation_id="voice-session",
            voice_context={"actor": "chat", "operator_consent": True},
        )
        == "handled"
    )
    operator.process.assert_not_awaited()
    turn = provider.calls[0][1]
    assert turn.actor == "voice" and turn.conversation_id == "voice-session"
    assert turn.target_device_id is None
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_chat_turn_context_starts_before_classification_and_resets(monkeypatch):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    seen = []

    async def execute(orch, task_id, request, fast_path=False):
        turn = conversation.current_conversation_context()
        seen.append(turn)
        await asyncio.sleep(0)
        assert conversation.current_conversation_context() is turn

    monkeypatch.setattr(dispatch, "_run_task", execute)
    task_id = uuid4()
    await dispatch.run_task(None, task_id, TaskRequest(content="x", session_id="chat"))
    assert seen[0].task_id == str(task_id) and seen[0].actor == "chat"
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_manual_intervention_during_planning_invalidates_prepared_scope(
    monkeypatch,
):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    class Scoped(Provider):
        epoch = 1
        scope = {}

        async def prepare(self, text, turn):
            assert conversation.current_conversation_context() is turn
            self.scope[turn.task_id] = self.epoch

        async def handle(self, text, turn):
            assert self.scope[turn.task_id] == 1
            if self.scope[turn.task_id] != self.epoch:
                raise RuntimeError("manual_intervention")
            raise AssertionError("stale command executed")

        async def finish(self, turn):
            assert conversation.current_conversation_context() is turn
            self.scope.pop(turn.task_id, None)

    provider = Scoped()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)

    async def planning(*args, **kwargs):
        turn = conversation.current_conversation_context()
        assert provider.scope[turn.task_id] == 1
        provider.epoch += 1
        await conversation.handle_conversation_turn("/extension move", turn)

    monkeypatch.setattr(dispatch, "_run_task", planning)
    errors = AsyncMock()
    orch = SimpleNamespace(result_processor=SimpleNamespace(process_error=errors))
    await dispatch.run_task(orch, uuid4(), TaskRequest(content="/extension move"))
    errors.assert_awaited_once()
    assert errors.call_args.args[1].code == "conversation_provider_failed"
    assert not provider.scope and not registry._prepared
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_prepared_scope_is_finished_when_planning_returns_or_cancels(
    monkeypatch, cancel
):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    provider = Provider()
    provider.prepare = AsyncMock()
    provider.finish = AsyncMock()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)

    async def planning(*args, **kwargs):
        if cancel:
            raise asyncio.CancelledError()

    monkeypatch.setattr(dispatch, "_run_task", planning)
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await dispatch.run_task(None, uuid4(), TaskRequest(content="/extension"))
    else:
        await dispatch.run_task(None, uuid4(), TaskRequest(content="/extension"))
    provider.prepare.assert_awaited_once()
    provider.finish.assert_awaited_once()
    assert (
        not registry._prepared and conversation.current_conversation_context() is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tracing", [True, False])
@pytest.mark.parametrize("forced_tool", [None, "git"])
async def test_urgent_stop_completes_task_without_classifier_or_inference(
    monkeypatch, tracing, forced_tool
):
    from venom_core.core.models import TaskRequest, TaskStatus
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    class Urgent(Provider):
        async def urgent(self, text, turn):
            assert conversation.current_conversation_context() is turn
            return "stopped" if text == "/extension stop" else None

        async def handle(self, text, turn):
            raise AssertionError("ordinary provider before policy")

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Urgent())
    conversation.set_conversation_registry(registry)
    classify = AsyncMock(side_effect=AssertionError("blocked LLM classifier called"))
    monkeypatch.setattr(dispatch, "_prepare_intent_and_context", classify)
    collector = Mock() if tracing else None
    monkeypatch.setattr(dispatch.metrics_module, "metrics_collector", collector)
    callback = Mock()
    state = SimpleNamespace(
        get_task=Mock(return_value=object()),
        update_status=AsyncMock(),
        add_log=Mock(),
        update_context=Mock(),
    )
    orch = SimpleNamespace(
        state_manager=state,
        request_tracer=Mock() if tracing else None,
        _trace_step_async=AsyncMock(),
        _broadcast_event=AsyncMock(),
        _persist_session_context=Mock(),
        _append_session_history=Mock(),
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: callback),
        context_builder=SimpleNamespace(preprocess_request=AsyncMock()),
        result_processor=SimpleNamespace(
            process_success=AsyncMock(), process_error=AsyncMock()
        ),
    )
    task_id = uuid4()
    await dispatch.run_task(
        orch,
        task_id,
        TaskRequest(
            content="/extension stop", session_id="chat", forced_tool=forced_tool
        ),
    )
    classify.assert_not_awaited()
    orch.context_builder.preprocess_request.assert_not_awaited()
    orch.result_processor.process_success.assert_not_awaited()
    orch.result_processor.process_error.assert_not_awaited()
    state.update_status.assert_awaited_with(
        task_id, TaskStatus.COMPLETED, result="stopped"
    )
    assert [
        item.kwargs["role"] for item in orch._append_session_history.call_args_list
    ] == [
        "user",
        "assistant",
    ]
    callback.assert_called_once_with("stopped")
    assert orch._broadcast_event.call_args.kwargs["event_type"] == "TASK_COMPLETED"
    if collector is not None:
        collector.increment_task_completed.assert_called_once_with()
    assert (
        not registry._prepared and conversation.current_conversation_context() is None
    )


@pytest.mark.asyncio
async def test_native_voice_urgent_bypasses_model_switch_guard():
    from venom_core.api.audio_stream import _invoke_operator_agent

    class Urgent(Provider):
        async def urgent(self, text, turn):
            assert turn.actor == "voice"
            return "stopped" if text == "/extension stop" else None

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Urgent())
    conversation.set_conversation_registry(registry)
    entered = []

    @asynccontextmanager
    async def unavailable_model():
        entered.append(True)
        raise RuntimeError("runtime_switch_in_progress")
        yield

    operator = SimpleNamespace(process=AsyncMock())
    assert (
        await _invoke_operator_agent(
            operator,
            "/extension stop",
            mode="standard",
            legacy_guard=unavailable_model(),
        )
        == "stopped"
    )
    assert not entered
    operator.process.assert_not_awaited()
    with pytest.raises(RuntimeError, match="runtime_switch_in_progress"):
        await _invoke_operator_agent(
            operator,
            "ordinary",
            mode="standard",
            legacy_guard=unavailable_model(),
        )
    assert entered == [True]
    assert (
        not registry._prepared and conversation.current_conversation_context() is None
    )


@pytest.mark.asyncio
async def test_finish_cleans_expired_context_and_optional_hooks_are_idempotent():
    provider = Provider()
    provider.prepare = AsyncMock()
    provider.finish = AsyncMock()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    turn = context(timeout_s=0.02)
    await registry.prepare("/extension", turn)
    await registry.prepare("/extension", turn)
    provider.prepare.assert_awaited_once()
    await asyncio.sleep(0.03)
    await registry.finish(turn)
    await registry.finish(turn)
    provider.finish.assert_awaited_once_with(turn)
    assert not registry._prepared


@pytest.mark.asyncio
async def test_finish_cleans_all_scopes_even_when_one_hook_fails():
    registry = conversation.ConversationProviderRegistry(None)
    first, second = Provider(), Provider()
    first.finish = AsyncMock(side_effect=RuntimeError("private finish failure"))
    second.finish = AsyncMock()
    await registry.register("first", first)
    await registry.register("second", second)
    turn = context()
    await registry.prepare("/extension", turn)
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_failed"
    ):
        await registry.finish(turn)
    second.finish.assert_awaited_once_with(turn)
    assert (
        not registry._prepared and conversation.current_conversation_context() is None
    )


@pytest.mark.asyncio
async def test_invalid_prepare_hook_fails_closed_and_disabled_scope_is_removed():
    provider = Provider()
    provider.prepare = Mock()
    provider.finish = AsyncMock()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    turn = context()
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_invalid"
    ):
        await registry.prepare("/extension", turn)
    provider.prepare.assert_not_called()
    await registry.unregister("example")
    assert not registry._prepared[turn]
    await registry.finish(turn)
    provider.finish.assert_not_awaited()
    await registry.close()
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_registry_closed"
    ):
        await registry.prepare("any", turn)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["pcm", "encoded", "native"])
async def test_manual_during_delayed_asr_invalidates_the_original_voice_scope(
    monkeypatch, tmp_path, pipeline
):
    import threading

    import numpy as np

    from venom_core.api.audio_stream import AudioStreamHandler

    started, release = asyncio.Event(), asyncio.Event()
    thread_release = threading.Event()
    loop = asyncio.get_running_loop()

    class Snapshot(Provider):
        epoch = 1

        def __init__(self):
            super().__init__()
            self.prepared, self.finished, self.handled, self.scopes = [], [], [], {}

        async def prepare(self, text, turn):
            assert text == "" and turn.actor == "voice"
            assert conversation.current_conversation_context() is turn
            self.prepared.append(turn)
            self.scopes[turn.task_id] = self.epoch

        async def handle(self, text, turn):
            assert text == "/extension move"
            assert turn is self.prepared[0]
            assert conversation.current_conversation_context() is turn
            self.handled.append(turn)
            if self.scopes[turn.task_id] != self.epoch:
                raise RuntimeError("manual_during_asr")
            raise AssertionError("old utterance executed after manual intervention")

        async def finish(self, turn):
            assert turn is self.prepared[0]
            self.finished.append(turn)
            self.scopes.pop(turn.task_id, None)

    provider = Snapshot()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)

    async def delayed_asr(*args, **kwargs):
        assert conversation.current_conversation_context() is provider.prepared[0]
        started.set()
        await release.wait()
        return "/extension move"

    def delayed_file_asr(*args, **kwargs):
        assert conversation.current_conversation_context() is provider.prepared[0]
        loop.call_soon_threadsafe(started.set)
        assert thread_release.wait(timeout=5)
        return "/extension move"

    async def delayed_native_asr(*args, **kwargs):
        transcript = await delayed_asr()
        return {"transcription": transcript, "response_text": "model reply"}

    audio = np.array([1, 2], dtype=np.int16)
    handler = AudioStreamHandler()
    handler.audio_engine = SimpleNamespace(
        listen=AsyncMock(side_effect=delayed_asr),
        transcribe_file=delayed_file_asr,
        speak=AsyncMock(return_value=audio),
    )
    metadata = []
    monkeypatch.setattr(handler, "_persist_voice_session", lambda **_: tmp_path)
    monkeypatch.setattr(handler, "_persist_encoded_voice_session", lambda *_: tmp_path)
    monkeypatch.setattr(handler, "_load_wav_int16", lambda _: (audio, 16000))
    monkeypatch.setattr(handler, "_write_wav", lambda *_: None)
    monkeypatch.setattr(handler, "_normalize_recorded_audio", lambda value: (value, {}))
    monkeypatch.setattr(
        handler,
        "_voice_route_runtime_config",
        lambda: {
            "voice_route_profile": "auto",
            "audio_decoder_profile": "faster_whisper",
            "audio_decoder_chain": ["faster_whisper"],
        },
    )
    monkeypatch.setattr(
        handler,
        "_resolve_audio_decoder_plan",
        lambda: {
            "selected": "faster_whisper",
            "effective": "faster_whisper",
            "fallback_reason": None,
            "should_try_native": False,
        },
    )
    monkeypatch.setattr(
        handler, "_handle_decoder_plan_pre_stt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler, "_multi_runtime_runtime_snapshot_live", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handler, "_invoke_multi_runtime", AsyncMock(side_effect=delayed_native_asr)
    )
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: metadata.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _: {})
    monkeypatch.setattr(handler, "_connection_voice_mode", lambda _: "standard")
    monkeypatch.setattr(handler, "_send_json", AsyncMock())
    monkeypatch.setattr(handler, "_send_audio", AsyncMock())
    operator = SimpleNamespace(process=AsyncMock())
    if pipeline == "pcm":
        operation = handler._process_audio_buffer(1, [audio], operator)
    elif pipeline == "encoded":
        operation = handler._process_encoded_audio_buffer(1, [b"fixture"], operator)
    else:
        operation = handler._process_native_multi_runtime_pipeline(
            1, tmp_path, tmp_path / "audio.wav", {}, 0.0, operator
        )
    pending = asyncio.create_task(operation)
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert len(provider.prepared) == 1
        provider.epoch += 1
        release.set()
        thread_release.set()
        if pipeline == "native":
            with pytest.raises(conversation.ConversationProviderError):
                await pending
        else:
            await pending
            assert handler._send_json.call_args.args[1]["type"] == "error"
    finally:
        release.set()
        thread_release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    assert provider.handled == provider.prepared == provider.finished
    assert not provider.scopes and not registry._prepared
    handler.audio_engine.speak.assert_not_awaited()
    operator.process.assert_not_awaited()
    assert conversation.current_conversation_context() is None
    if pipeline != "native":
        assert metadata[0]["conversation_id"] == provider.prepared[0].conversation_id


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["silence", "error", "cancel"])
async def test_voice_input_scope_is_released_when_asr_does_not_produce_a_command(
    monkeypatch, tmp_path, outcome
):
    import numpy as np

    from venom_core.api.audio_stream import AudioStreamHandler

    provider = Provider()
    provider.prepare, provider.finish = AsyncMock(), AsyncMock()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)

    async def asr(*args, **kwargs):
        provider.prepare.assert_awaited_once()
        if outcome == "error":
            raise RuntimeError("asr failed")
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return ""

    handler = AudioStreamHandler()
    handler.audio_engine = SimpleNamespace(listen=AsyncMock(side_effect=asr))
    monkeypatch.setattr(handler, "_persist_voice_session", lambda **_: tmp_path)
    monkeypatch.setattr(
        handler, "_handle_decoder_plan_pre_stt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(handler, "_update_voice_session_metadata", Mock())
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _: {})
    monkeypatch.setattr(handler, "_send_json", AsyncMock())
    operation = handler._process_audio_buffer(
        1, [np.array([1, 2], dtype=np.int16)], None
    )
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await operation
    else:
        await operation
    provider.finish.assert_awaited_once()
    handler.audio_engine.listen.assert_awaited_once()
    assert provider.prepare.call_args.args[0] == ""
    assert provider.prepare.call_args.args[1] is provider.finish.call_args.args[0]
    assert not provider.calls and not registry._prepared
    assert conversation.current_conversation_context() is None


@pytest.mark.asyncio
async def test_unmatched_expired_chat_falls_through_without_renewing_deadline(
    monkeypatch,
):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    class Matching(Provider):
        def accepts(self, text, turn):
            assert conversation.current_conversation_context() is turn
            return text.startswith("/extension")

    provider = Matching()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    stale = context(timeout_s=0)
    original_deadline = stale.deadline
    assert await registry.handle("ordinary long chat", stale) is None
    assert await registry.urgent("ordinary long chat", stale) is None
    execution = AsyncMock(return_value="normal reply")
    monkeypatch.setattr(
        dispatch, "get_active_llm_runtime", lambda: SimpleNamespace(provider="ollama")
    )
    monkeypatch.setattr(
        dispatch, "ExecutionStrategy", lambda _: SimpleNamespace(execute=execution)
    )
    orch = SimpleNamespace(
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: Mock())
    )
    with conversation.conversation_turn(stale):
        assert (
            await dispatch._execute_with_stream_callback(
                orch,
                uuid4(),
                "GENERAL_CHAT",
                "context",
                TaskRequest(content="ordinary"),
            )
            == "normal reply"
        )
    execution.assert_awaited_once()
    assert not provider.calls and stale.deadline == original_deadline
    assert conversation.current_conversation_context() is None
    for route in (registry.handle, registry.urgent):
        provider.urgent = AsyncMock(return_value="stopped")
        with pytest.raises(
            conversation.ConversationProviderError, match="conversation_deadline"
        ):
            await route("/extension move", stale)
    assert not provider.calls and stale.deadline == original_deadline
    provider.urgent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["not_callable", "async", "not_bool", "throws"])
async def test_optional_accepts_requires_a_synchronous_boolean_predicate(kind):
    provider = Provider()
    if kind == "not_callable":
        provider.accepts = True
    elif kind == "async":
        provider.accepts = AsyncMock(return_value=True)
    elif kind == "not_bool":
        provider.accepts = Mock(return_value="yes")
    else:
        provider.accepts = Mock(side_effect=RuntimeError("private prefilter detail"))
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    with pytest.raises(conversation.ConversationProviderError):
        await registry.handle("/extension", context())
    assert not provider.calls and conversation.current_conversation_context() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("forced_tool", [None, "git"])
async def test_explicit_forced_tool_preserves_dispatcher_and_other_tool_intents(
    monkeypatch, forced_tool
):
    from venom_core.core.models import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch

    provider = Provider()
    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    monkeypatch.setattr(
        dispatch, "get_active_llm_runtime", lambda: SimpleNamespace(provider="ollama")
    )
    execution = AsyncMock(return_value="forced tool reply")
    monkeypatch.setattr(
        dispatch, "ExecutionStrategy", lambda _: SimpleNamespace(execute=execution)
    )
    orch = SimpleNamespace(
        streaming_handler=SimpleNamespace(create_stream_callback=lambda _: Mock()),
        request_tracer=None,
    )
    result = await dispatch._execute_with_stream_callback(
        orch,
        uuid4(),
        "SYSTEM_DIAGNOSTICS",
        "context",
        TaskRequest(content="/extension", forced_tool=forced_tool),
    )
    if forced_tool is None:
        assert result == "handled" and len(provider.calls) == 1
        execution.assert_not_awaited()
    else:
        assert result == "forced tool reply" and not provider.calls
        execution.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["pcm", "encoded", "native"])
@pytest.mark.parametrize("actor", [None, "chat"])
async def test_private_audio_pipeline_explicitly_rejects_missing_or_nonvoice_context(
    monkeypatch, tmp_path, pipeline, actor
):
    from venom_core.api.audio_stream import AudioStreamHandler

    handler = AudioStreamHandler()
    if pipeline == "pcm":
        operation = handler._process_audio_buffer_in_turn(1, [], None)
    elif pipeline == "encoded":
        operation = handler._process_encoded_audio_buffer_in_turn(1, [], None)
    else:
        handler.audio_engine = SimpleNamespace(speak=AsyncMock())
        monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
        monkeypatch.setattr(
            handler, "_multi_runtime_runtime_snapshot_live", AsyncMock(return_value={})
        )
        monkeypatch.setattr(
            handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(
            handler,
            "_invoke_multi_runtime",
            AsyncMock(
                return_value={"transcription": "/extension", "response_text": "x"}
            ),
        )
        monkeypatch.setattr(handler, "_send_json", AsyncMock())
        operation = handler._process_native_multi_runtime_in_turn(
            1, tmp_path, tmp_path / "fixture.wav", {}, 0.0, None
        )
    scope = conversation.conversation_turn(context(actor)) if actor else nullcontext()
    with scope:
        with pytest.raises(RuntimeError, match="voice_context_required"):
            await operation


@pytest.mark.asyncio
async def test_real_caller_cancellation_propagates_and_resets_context():
    started = asyncio.Event()

    class Waiting(Provider):
        async def handle(self, text, turn):
            started.set()
            await asyncio.Event().wait()

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Waiting())
    pending = asyncio.create_task(registry.handle("/extension", context()))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not registry._active and conversation.current_conversation_context() is None
    await registry.close()


@pytest.mark.asyncio
async def test_provider_self_cancellation_is_a_typed_error_not_caller_cancellation():
    class Cancelled(Provider):
        async def handle(self, text, turn):
            raise asyncio.CancelledError()

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Cancelled())
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_cancelled"
    ):
        await registry.handle("/extension", context())
    assert not registry._active and conversation.current_conversation_context() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["chat", "voice"])
async def test_disabling_child_provider_finishes_host_task_or_voice_error(
    monkeypatch, tmp_path, entry
):
    import numpy as np

    from venom_core.api.audio_stream import AudioStreamHandler
    from venom_core.core.models import TaskRequest, TaskStatus
    from venom_core.core.orchestrator import orchestrator_dispatch as dispatch
    from venom_core.core.orchestrator.task_pipeline.result_processor import (
        ResultProcessor,
    )

    started = asyncio.Event()

    class Waiting(Provider):
        async def handle(self, text, turn):
            started.set()
            await asyncio.Event().wait()

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("example", Waiting())
    conversation.set_conversation_registry(registry)
    if entry == "chat":
        state = SimpleNamespace(
            get_task=Mock(return_value=SimpleNamespace(context_history={})),
            update_status=AsyncMock(),
            add_log=Mock(),
        )
        orch = SimpleNamespace(
            state_manager=state,
            request_tracer=None,
            _broadcast_event=AsyncMock(),
            _persist_session_context=Mock(),
            _append_session_history=Mock(),
            context_builder=SimpleNamespace(preprocess_request=AsyncMock()),
            _is_perf_test_prompt=Mock(return_value=False),
            validator=SimpleNamespace(validate_forced_tool=Mock()),
            NON_LEARNING_INTENTS={"GENERAL_CHAT"},
            streaming_handler=SimpleNamespace(create_stream_callback=lambda _: Mock()),
            _build_error_envelope=Mock(return_value={"error_code": "agent_error"}),
            _set_runtime_error=Mock(),
        )
        orch.result_processor = ResultProcessor(orch)
        monkeypatch.setattr(
            dispatch,
            "_prepare_intent_and_context",
            AsyncMock(return_value=("GENERAL_CHAT", "context", False, {})),
        )
        monkeypatch.setattr(dispatch, "_emit_classification_trace", Mock())
        monkeypatch.setattr(dispatch, "_broadcast_intent", AsyncMock())
        monkeypatch.setattr(dispatch, "_resolve_planned_provider", lambda *_: None)
        monkeypatch.setattr(
            dispatch,
            "_handle_policy_block_global_pre_execution",
            AsyncMock(return_value=False),
        )
        pending = asyncio.create_task(
            dispatch.run_task(orch, uuid4(), TaskRequest(content="/extension"))
        )
    else:
        handler = AudioStreamHandler()
        handler.audio_engine = SimpleNamespace(
            listen=AsyncMock(return_value="/extension"), speak=AsyncMock()
        )
        monkeypatch.setattr(handler, "_persist_voice_session", lambda **_: tmp_path)
        monkeypatch.setattr(
            handler, "_handle_decoder_plan_pre_stt", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(handler, "_update_voice_session_metadata", Mock())
        monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _: {})
        monkeypatch.setattr(handler, "_send_json", AsyncMock())
        operator = SimpleNamespace(process=AsyncMock())
        pending = asyncio.create_task(
            handler._process_audio_buffer(
                1, [np.array([1, 2], dtype=np.int16)], operator
            )
        )
    await asyncio.wait_for(started.wait(), timeout=5)
    await registry.unregister("example")
    await pending
    if entry == "chat":
        assert state.update_status.call_args.args[1] == TaskStatus.FAILED
        assert (
            "conversation_provider_disabled"
            in state.update_status.call_args.kwargs["result"]
        )
    else:
        error = handler._send_json.call_args.args[1]
        assert error == {"type": "error", "message": "conversation_provider_disabled"}
        handler.audio_engine.speak.assert_not_awaited()
        operator.process.assert_not_awaited()
    assert (
        not registry._prepared and conversation.current_conversation_context() is None
    )


@pytest.mark.asyncio
async def test_real_kernel_refresh_keeps_the_same_provider(monkeypatch):
    from venom_core.core import dispatcher as dispatcher_module
    from venom_core.core.orchestrator import kernel_manager

    registry = conversation.ConversationProviderRegistry(None)
    provider = Provider()
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    runtime = SimpleNamespace(config_hash="new-runtime")
    monkeypatch.setattr(kernel_manager, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        kernel_manager,
        "KernelBuilder",
        lambda: SimpleNamespace(build_kernel=lambda: object()),
    )
    monkeypatch.setattr(
        dispatcher_module,
        "TaskDispatcher",
        lambda kernel, **kwargs: SimpleNamespace(kernel=kernel),
    )
    manager = kernel_manager.KernelManager(SimpleNamespace(goal_store=object()))
    manager.refresh_kernel(runtime)
    assert (
        await conversation.handle_conversation_turn("/extension", context())
        == "handled"
    )
    assert registry.providers["example"] is provider
    assert len(provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_transcription", [True, False])
async def test_multimodal_native_voice_uses_only_real_transcript_before_tts(
    monkeypatch, tmp_path, explicit_transcription
):
    import numpy as np

    from venom_core.api.audio_stream import AudioStreamHandler

    registry = conversation.ConversationProviderRegistry(None)
    provider = Provider()
    await registry.register("example", provider)
    conversation.set_conversation_registry(registry)
    handler = AudioStreamHandler()
    handler.audio_engine = SimpleNamespace(
        speak=AsyncMock(return_value=np.array([1, 2], dtype=np.int16))
    )
    metadata = []
    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler, "_multi_runtime_runtime_snapshot_live", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )
    result = {"text": "/extension", "response_text": "model reply"}
    if explicit_transcription:
        result["transcription"] = "/extension"
    monkeypatch.setattr(
        handler, "_invoke_multi_runtime", AsyncMock(return_value=result)
    )
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: metadata.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _agent: {})
    monkeypatch.setattr(handler, "_connection_voice_mode", lambda _cid: "standard")
    monkeypatch.setattr(handler, "_send_json", AsyncMock())
    monkeypatch.setattr(handler, "_send_audio", AsyncMock())
    assert (
        await handler._process_native_multi_runtime_pipeline(
            1, tmp_path / "voice-session", tmp_path / "audio.wav", {}, 0.0, None
        )
        is True
    )
    expected = "handled" if explicit_transcription else "model reply"
    handler.audio_engine.speak.assert_awaited_once_with(expected)
    assert metadata[0]["conversation_provider_handled"] is explicit_transcription
    assert len(provider.calls) == int(explicit_transcription)
    if explicit_transcription:
        assert provider.calls[0][1].actor == "voice"
        assert provider.calls[0][1].conversation_id == "voice-session"
    assert conversation.current_conversation_context() is None


def manifest(tmp_path, factory="example_module:create_provider"):
    path = tmp_path / "module.json"
    path.write_text(
        json.dumps(
            {
                "module_id": "example",
                "backend": {
                    "router_import": "example_module:router",
                    "conversation_provider_import": factory,
                    "feature_flag": "ENABLE_EXAMPLE",
                    "data_policy": {
                        "storage_mode": "core_prefixed",
                        "mutation_guard": "core_environment_policy",
                        "state_files": ["runtime-state.json"],
                    },
                },
            }
        )
    )
    return path


def test_manifest_validates_optional_factory_import(tmp_path):
    path = manifest(tmp_path, "bad-import")
    settings = SimpleNamespace(API_OPTIONAL_MODULES=f"manifest:{path}")
    assert any(
        "conversation_provider_import" in error
        for error in module_registry.validate_optional_modules_config(settings)
    )
    assert module_registry._parse_manifest_file(str(path)) is None


def test_optional_provider_lifecycle_reuses_app_domain_and_survives_kernel_refresh(
    tmp_path, monkeypatch
):
    provider = Provider()
    domain = object()
    created = []
    module = ModuleType("example_module")
    module.router = APIRouter()

    def factory(app):
        assert app.state.domain is domain
        created.append(app)
        return provider

    module.create_provider = factory
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    settings = SimpleNamespace(
        API_OPTIONAL_MODULES=f"manifest:{manifest(tmp_path)}", ENABLE_EXAMPLE=True
    )

    @asynccontextmanager
    async def core_lifespan(app):
        app.state.domain = domain
        yield
        assert provider.closed
        del app.state.domain

    app = FastAPI(lifespan=core_lifespan)
    assert module_registry.include_optional_api_routers(app, settings) == ["example"]
    with TestClient(app):
        registry = app.state.conversation_providers
        assert registry.providers["example"] is provider
        app.state.kernel = object()
        assert app.state.conversation_providers is registry
        assert len(created) == 1
    assert provider.closed
    assert not hasattr(app.state, "domain")
    assert conversation.get_conversation_registry() is None


def test_optional_provider_startup_failure_cleans_partial_registry(monkeypatch):
    provider = Provider()
    factories = {
        "first": lambda app: provider,
        "invalid": lambda app: object(),
    }
    monkeypatch.setattr(
        module_registry, "_conversation_provider_factories", lambda _: factories
    )
    app = FastAPI()
    module_registry._install_conversation_provider_lifespan(app, object())
    with pytest.raises(
        conversation.ConversationProviderError, match="conversation_provider_invalid"
    ):
        with TestClient(app):
            pass
    assert provider.closed and not app.state.conversation_providers.providers
    assert conversation.get_conversation_registry() is None


def test_provider_factories_skip_disabled_and_restore_import_paths(
    tmp_path, monkeypatch
):
    import sys

    path = manifest(tmp_path)
    settings = SimpleNamespace(
        API_OPTIONAL_MODULES=f"manifest:{path}", ENABLE_EXAMPLE=False
    )
    importer = Mock(side_effect=AssertionError("disabled factory imported"))
    monkeypatch.setattr(module_registry.importlib, "import_module", importer)
    assert module_registry._conversation_provider_factories(settings) == {}
    importer.assert_not_called()

    settings.ENABLE_EXAMPLE = True
    monkeypatch.setattr(
        module_registry.importlib,
        "import_module",
        Mock(return_value=SimpleNamespace(create_provider=None)),
    )
    before = list(sys.path)
    with pytest.raises(ValueError, match="invalid_conversation_provider_factory"):
        module_registry._conversation_provider_factories(settings)
    assert sys.path == before
