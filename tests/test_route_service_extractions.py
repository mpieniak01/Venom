from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest

from venom_core.services import knowledge_lessons_service as ksvc
from venom_core.services import llm_simple_stream_service as ssvc
from venom_core.services import llm_simple_transport as transport
from venom_core.services import tasks_onnx_service as tsvc
from venom_core.services import tasks_service


class _Logger:
    def __init__(self) -> None:
        self.records: list[tuple[str, tuple[object, ...]]] = []

    def info(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))

    def warning(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))

    def exception(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))


class _LessonsStore:
    def __init__(self) -> None:
        self.lessons = [1, 2, 3]

    def delete_last_n(self, count: int) -> int:
        return count

    def delete_by_time_range(self, _start: datetime, _end: datetime) -> int:
        return 2

    def delete_by_tag(self, _tag: str) -> int:
        return 1

    def clear_all(self) -> bool:
        return True

    def prune_by_ttl(self, days: int) -> int:
        return max(days - 1, 0)

    def dedupe_lessons(self) -> int:
        return 4


class _FailingLessonsStore(_LessonsStore):
    def clear_all(self) -> bool:
        return False


@dataclass
class _Request:
    content: str
    session_id: str
    forced_intent: str | None = None
    store_knowledge: bool = True
    generation_params: dict[str, object] | None = None


@dataclass
class _Runtime:
    provider: str = "onnx"
    model_name: str = "m1"
    endpoint: str = "http://localhost"
    config_hash: str = "h"
    runtime_id: str = "rid"

    def to_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model_name,
            "endpoint": self.endpoint,
        }


class _Task:
    def __init__(self) -> None:
        self.id = "task-1"


class _StateManager:
    def __init__(self) -> None:
        self.context_updates: list[tuple[str, dict[str, object]]] = []
        self.logs: list[tuple[str, str]] = []
        self.statuses: list[tuple[str, object, str | None]] = []

    def create_task(self, _content: str) -> _Task:
        return _Task()

    def update_context(self, task_id: str, payload: dict[str, object]) -> None:
        self.context_updates.append((task_id, payload))

    def add_log(self, task_id: str, message: str) -> None:
        self.logs.append((task_id, message))

    async def update_status(
        self, task_id: str, status: object, result: str | None = None
    ) -> None:
        self.statuses.append((task_id, status, result))


class _Tracer:
    def __init__(self) -> None:
        self.steps: list[str] = []
        self.statuses: list[object] = []
        self.error_payloads: list[dict[str, object]] = []

    def create_trace(self, *_args, **_kwargs) -> None:
        self.steps.append("create")

    def set_llm_metadata(self, *_args, **_kwargs) -> None:
        self.steps.append("llm_meta")

    def update_status(self, _task_id: str, status: object) -> None:
        self.statuses.append(status)

    def add_step(self, *_args, **_kwargs) -> None:
        self.steps.append("step")

    def set_error_metadata(self, _task_id: str, payload: dict[str, object]) -> None:
        self.error_payloads.append(payload)


class _HttpStatusError(Exception):
    def __init__(self, status: int) -> None:
        self.response = SimpleNamespace(status_code=status)


class _OpenResponse:
    def __init__(self, packets: list[dict[str, object]]):
        self._packets = packets

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


async def _iter_packets(resp: _OpenResponse):
    for packet in resp._packets:
        yield packet


def test_knowledge_lessons_helpers_cover_success_and_failure_paths() -> None:
    logger = _Logger()
    store = _LessonsStore()

    assert (
        ksvc.prune_latest_lessons(lessons_store=store, count=3, logger=logger)[
            "deleted"
        ]
        == 3
    )

    start, end = ksvc.parse_iso_range(
        start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z"
    )
    assert start.tzinfo is not None and end.tzinfo is not None

    payload = ksvc.prune_lessons_by_range(
        lessons_store=store,
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        start_dt=start,
        end_dt=end,
        logger=logger,
    )
    assert payload["deleted"] == 2
    assert (
        ksvc.prune_lessons_by_tag(lessons_store=store, tag="x", logger=logger)[
            "deleted"
        ]
        == 1
    )
    assert ksvc.prune_lessons_by_ttl(lessons_store=store, days=3)["deleted"] == 2
    assert ksvc.dedupe_lessons(lessons_store=store)["removed"] == 4
    assert (
        ksvc.purge_all_lessons(lessons_store=store, logger=logger)["status"]
        == "success"
    )

    with pytest.raises(RuntimeError):
        ksvc.purge_all_lessons(lessons_store=_FailingLessonsStore(), logger=logger)


@pytest.mark.asyncio
async def test_tasks_onnx_helpers_cover_trace_and_run_branches() -> None:
    request = _Request(content="hello", session_id="sess", forced_intent="X")
    runtime = _Runtime()
    tracer = _Tracer()

    tsvc.trace_onnx_task_start(
        tracer=tracer, task_id="t1", request=request, runtime=runtime
    )
    tsvc.trace_onnx_task_success(tracer=tracer, task_id="t1", result="ok")
    tsvc.trace_onnx_task_failure(tracer=tracer, task_id="t1", exc=ValueError("boom"))
    assert tracer.steps
    assert tracer.statuses
    assert (
        tracer.error_payloads
        and tracer.error_payloads[0]["error_code"] == "onnx_task_error"
    )

    state = _StateManager()
    starts: list[str] = []
    scheduled: list[str] = []
    task = tsvc.create_and_submit_onnx_task(
        state_manager=state,
        request=request,
        runtime=runtime,
        trace_start_fn=lambda task_id: starts.append(task_id),
        schedule_runner_fn=lambda task_id: scheduled.append(task_id),
    )
    assert task.id == "task-1"
    assert starts == ["task-1"]
    assert scheduled == ["task-1"]

    successes: list[str] = []
    failures: list[str] = []

    async def _run_generation(_messages, _max_tokens, _temperature):
        return " result "

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-1",
        request=_Request(
            content="x",
            session_id="sess",
            generation_params={"max_tokens": 50, "temperature": 0.2},
        ),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda _task_id, result: successes.append(result),
        trace_failure_fn=lambda _task_id, exc: failures.append(str(exc)),
        logger=_Logger(),
    )
    assert successes == ["result"]
    assert not failures

    async def _run_fail(_messages, _max_tokens, _temperature):
        raise RuntimeError("gen_fail")

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-2",
        request=_Request(content="x", session_id="sess"),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_fail,
        trace_success_fn=lambda _task_id, result: successes.append(result),
        trace_failure_fn=lambda _task_id, exc: failures.append(str(exc)),
        logger=_Logger(),
    )
    assert "gen_fail" in failures[-1]


@pytest.mark.asyncio
async def test_tasks_onnx_fast_help_and_session_history_contract() -> None:
    state = _StateManager()
    runtime = _Runtime()
    history: list[tuple[str, str, str, str | None]] = []
    generation_calls: list[tuple[int | None, float | None]] = []

    async def _run_generation(_messages, max_tokens, temperature):
        generation_calls.append((max_tokens, temperature))
        return "model-output"

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-fast-help",
        request=_Request(
            content="pomoc", session_id="sess-fast", forced_intent="HELP_REQUEST"
        ),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda *_args: None,
        trace_failure_fn=lambda *_args: None,
        append_session_history_fn=lambda task_id,
        role,
        content,
        session_id: history.append((task_id, role, content, session_id)),
        logger=_Logger(),
    )

    assert generation_calls == []
    assert len(history) == 2
    assert history[0] == ("task-fast-help", "user", "pomoc", "sess-fast")
    assert history[1][0] == "task-fast-help"
    assert history[1][1] == "assistant"
    assert history[1][3] == "sess-fast"
    assert history[1][2].startswith("Jasne, pomogę.")

    history.clear()
    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-normal",
        request=_Request(
            content="zwykłe zapytanie",
            session_id="sess-normal",
            generation_params={"max_tokens": 32, "temperature": 0.4},
        ),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda *_args: None,
        trace_failure_fn=lambda *_args: None,
        append_session_history_fn=lambda task_id,
        role,
        content,
        session_id: history.append((task_id, role, content, session_id)),
        logger=_Logger(),
    )

    assert generation_calls == [(32, 0.4)]
    assert history == [
        ("task-normal", "user", "zwykłe zapytanie", "sess-normal"),
        ("task-normal", "assistant", "model-output", "sess-normal"),
    ]


@pytest.mark.asyncio
async def test_tasks_onnx_appends_learning_log_for_store_knowledge() -> None:
    state = _StateManager()
    runtime = _Runtime()
    learning_log_calls: list[tuple[str, str, str, str, bool, str]] = []

    async def _run_generation(_messages, _max_tokens, _temperature):
        return "onnx-result"

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-learning",
        request=_Request(
            content="krótkie pytanie",
            session_id="sess-learning",
            forced_intent="GENERAL_CHAT",
            store_knowledge=True,
        ),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda *_args: None,
        trace_failure_fn=lambda *_args: None,
        append_learning_log_fn=lambda task_id, intent, prompt, result, success, error: (
            learning_log_calls.append((task_id, intent, prompt, result, success, error))
        ),
        logger=_Logger(),
    )

    assert learning_log_calls == [
        (
            "task-learning",
            "GENERAL_CHAT",
            "krótkie pytanie",
            "onnx-result",
            True,
            "",
        )
    ]


@pytest.mark.asyncio
async def test_tasks_onnx_skips_learning_log_for_non_learning_intent() -> None:
    state = _StateManager()
    runtime = _Runtime()
    learning_log_calls: list[tuple[str, str, str, str, bool, str]] = []

    async def _run_generation(_messages, _max_tokens, _temperature):
        return "onnx-result"

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-no-learning",
        request=_Request(
            content="jaka godzina",
            session_id="sess-no-learning",
            forced_intent="TIME_REQUEST",
            store_knowledge=True,
        ),
        runtime=runtime,
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda *_args: None,
        trace_failure_fn=lambda *_args: None,
        append_learning_log_fn=lambda task_id, intent, prompt, result, success, error: (
            learning_log_calls.append((task_id, intent, prompt, result, success, error))
        ),
        logger=_Logger(),
    )

    assert learning_log_calls == []


def test_stream_state_helper_decisions_and_packet_update() -> None:
    state = ssvc.SimpleStreamState(chunks=[])
    ssvc.reset_stream_attempt_state(state)
    assert not state.retry_requested and not state.failed and not state.completed

    assert ssvc.apply_post_attempt_action("retry") == (True, False)
    assert ssvc.apply_post_attempt_action("done") == (False, True)
    assert ssvc.apply_post_attempt_action("stop") == (False, False)

    finalized: list[bool] = []
    state.completed = True
    assert (
        ssvc.resolve_post_attempt_action(
            state=state, finalize_success_fn=lambda: finalized.append(True)
        )
        == "done"
    )
    assert finalized == [True]

    state.retry_requested = True
    assert (
        ssvc.resolve_post_attempt_action(
            state=state, finalize_success_fn=lambda: finalized.append(False)
        )
        == "retry"
    )
    state.retry_requested = False
    state.completed = False
    state.failed = True
    assert (
        ssvc.resolve_post_attempt_action(
            state=state, finalize_success_fn=lambda: finalized.append(False)
        )
        == "stop"
    )

    state = ssvc.SimpleStreamState(chunks=[])
    first_chunks: list[str] = []
    events = ssvc.update_stream_state_from_packet(
        packet={"x": 1},
        runtime=SimpleNamespace(provider="ollama"),
        state=state,
        ollama_telemetry={},
        extract_ollama_telemetry_fn=lambda _p: {"eval_count": 5},
        extract_sse_tool_calls_fn=lambda _p: [{"id": "t1"}],
        extract_sse_contents_fn=lambda _p: ["A", "B"],
        on_first_chunk_fn=lambda c: first_chunks.append(c),
    )
    assert state.chunk_count == 2
    assert state.chunks == ["A", "B"]
    assert first_chunks == ["A"]
    assert any(e.startswith("event: tool_calls") for e in events)
    assert any(e.startswith("event: content") for e in events)


@pytest.mark.asyncio
async def test_stream_single_attempt_retry_and_failure() -> None:
    state = ssvc.SimpleStreamState(chunks=[])

    # Wrap coroutine factory into async context manager provider expected by helper.
    class _OpenOK:
        def __call__(self, **_kwargs):
            return _OpenResponse([{"ok": True}])

    emitted = [
        event
        async for event in ssvc.stream_single_attempt(
            transport=ssvc.StreamTransportConfig(
                open_stream_response_fn=_OpenOK(),
                iter_stream_packets_fn=_iter_packets,
                completions_url="u",
                payload={},
                provider_name="p",
            ),
            retry=ssvc.StreamRetryConfig(
                http_status_error_type=_HttpStatusError,
                max_attempts=2,
                is_retryable_status_fn=lambda code: code == 503,
                runtime_provider="ollama",
                retry_backoff=0.0,
                sleep_fn=lambda _s: _noop_sleep(),
            ),
            state=state,
            attempt=1,
            handle_packet_fn=lambda _p: ["event: content\\ndata: {}\\n\\n"],
            emit_http_error_fn=lambda _exc: _emit_error(),
        )
    ]
    assert emitted
    assert state.completed

    state2 = ssvc.SimpleStreamState(chunks=[])

    class _OpenErr:
        def __call__(self, **_kwargs):
            raise _HttpStatusError(503)

    emitted_retry = [
        event
        async for event in ssvc.stream_single_attempt(
            transport=ssvc.StreamTransportConfig(
                open_stream_response_fn=_OpenErr(),
                iter_stream_packets_fn=_iter_packets,
                completions_url="u",
                payload={},
                provider_name="p",
            ),
            retry=ssvc.StreamRetryConfig(
                http_status_error_type=_HttpStatusError,
                max_attempts=3,
                is_retryable_status_fn=lambda code: code == 503,
                runtime_provider="ollama",
                retry_backoff=0.0,
                sleep_fn=lambda _s: _noop_sleep(),
            ),
            state=state2,
            attempt=1,
            handle_packet_fn=lambda _p: ["x"],
            emit_http_error_fn=lambda _exc: _emit_error(),
        )
    ]
    assert emitted_retry == []
    assert state2.retry_requested

    state3 = ssvc.SimpleStreamState(chunks=[])

    emitted_fail = [
        event
        async for event in ssvc.stream_single_attempt(
            transport=ssvc.StreamTransportConfig(
                open_stream_response_fn=_OpenErr(),
                iter_stream_packets_fn=_iter_packets,
                completions_url="u",
                payload={},
                provider_name="p",
            ),
            retry=ssvc.StreamRetryConfig(
                http_status_error_type=_HttpStatusError,
                max_attempts=3,
                is_retryable_status_fn=lambda code: code == 503,
                runtime_provider="ollama",
                retry_backoff=0.0,
                sleep_fn=lambda _s: _noop_sleep(),
            ),
            state=state3,
            attempt=3,
            handle_packet_fn=lambda _p: ["x"],
            emit_http_error_fn=lambda _exc: _emit_error(),
        )
    ]
    assert state3.failed
    assert emitted_fail and emitted_fail[0].startswith("event: error")

    state4 = ssvc.SimpleStreamState(chunks=[])
    emitted_non_retryable = [
        event
        async for event in ssvc.stream_single_attempt(
            transport=ssvc.StreamTransportConfig(
                open_stream_response_fn=_OpenErr(),
                iter_stream_packets_fn=_iter_packets,
                completions_url="u",
                payload={},
                provider_name="p",
            ),
            retry=ssvc.StreamRetryConfig(
                http_status_error_type=_HttpStatusError,
                max_attempts=3,
                is_retryable_status_fn=lambda code: code == 500,
                runtime_provider="openai",
                retry_backoff=0.0,
                sleep_fn=lambda _s: _noop_sleep(),
            ),
            state=state4,
            attempt=1,
            handle_packet_fn=lambda _p: ["x"],
            emit_http_error_fn=lambda _exc: _emit_error(),
        )
    ]
    assert state4.failed
    assert emitted_non_retryable and emitted_non_retryable[0].startswith("event: error")


def test_tasks_service_metrics_and_status_values(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(tasks_service.metrics_module, "metrics_collector", sentinel)
    assert tasks_service.get_metrics_collector() is sentinel
    assert tasks_service.trace_status_values()
    monkeypatch.setattr(tasks_service.metrics_module, "metrics_collector", None)
    assert tasks_service.get_metrics_collector() is None


@pytest.mark.asyncio
async def test_tasks_onnx_empty_generation_and_non_numeric_params() -> None:
    state = _StateManager()
    failures: list[str] = []
    successes: list[str] = []

    async def _run_generation(_messages, max_tokens, temperature):
        assert max_tokens is None
        assert temperature is None
        return "   "

    await tsvc.run_onnx_task(
        state_manager=state,
        task_id="task-empty",
        request=_Request(
            content="x",
            session_id="sess",
            generation_params={"max_tokens": "bad", "temperature": "bad"},
        ),
        runtime=_Runtime(),
        build_messages_fn=lambda content, _intent: [
            {"role": "user", "content": content}
        ],
        run_generation_fn=_run_generation,
        trace_success_fn=lambda _task_id, result: successes.append(result),
        trace_failure_fn=lambda _task_id, exc: failures.append(str(exc)),
        logger=_Logger(),
    )

    assert not failures
    assert successes == ["Brak odpowiedzi z runtime ONNX."]


@pytest.mark.asyncio
async def test_llm_simple_transport_iter_and_error_reader_paths(monkeypatch) -> None:
    class _Resp:
        def __init__(self, lines):
            self._lines = lines
            self.encoding = "utf-8"

        async def aiter_lines(self):
            for line in self._lines:
                yield line

        async def aread(self):
            return b"error-body"

    packets = []
    async for packet in transport.iter_stream_packets(
        _Resp(
            [
                "",
                "event: keepalive",
                "data:   ",
                "data: not-json",
                "data: [1,2,3]",
                'data: {"ok": true}',
                "data: [DONE]",
                'data: {"late": true}',
            ]
        )
    ):
        packets.append(packet)
    assert packets == [{"ok": True}]
    assert await transport.read_http_error_response_text(None) == ""
    assert await transport.read_http_error_response_text(_Resp([])) == "error-body"

    class _ErrResp:
        async def aread(self):
            raise RuntimeError("read-fail")

    assert await transport.read_http_error_response_text(_ErrResp()) == ""


@pytest.mark.asyncio
async def test_llm_simple_transport_open_stream_response_adapter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _StreamResp:
        async def __aenter__(self):
            captured["entered_response"] = True
            return self

        async def __aexit__(self, *_exc):
            return False

    class _Client:
        async def __aenter__(self):
            captured["entered_client"] = True
            return self

        async def __aexit__(self, *_exc):
            return False

        def astream(self, method, url, json, disable_retry):
            captured["request"] = {
                "method": method,
                "url": url,
                "json": json,
                "disable_retry": disable_retry,
            }
            return _StreamResp()

    def _factory(*, provider, timeout):
        captured["factory"] = {"provider": provider, "timeout": timeout}
        return _Client()

    monkeypatch.setattr(transport, "TrafficControlledHttpClient", _factory)

    async with transport.open_stream_response(
        provider_name="ollama",
        completions_url="http://x",
        payload={"a": 1},
    ):
        pass

    assert captured["factory"] == {"provider": "ollama", "timeout": None}
    assert captured["request"] == {
        "method": "POST",
        "url": "http://x",
        "json": {"a": 1},
        "disable_retry": True,
    }


def test_llm_simple_transport_httpx_module_exposes_httpx() -> None:
    module = transport.httpx_module()
    assert module is transport.httpx
    assert hasattr(module, "HTTPStatusError")


def test_stream_state_helper_resolve_retry_when_not_completed() -> None:
    state = ssvc.SimpleStreamState(chunks=[])
    assert (
        ssvc.resolve_post_attempt_action(state=state, finalize_success_fn=lambda: None)
        == "retry"
    )


def test_update_stream_state_from_packet_non_ollama_and_no_events() -> None:
    state = ssvc.SimpleStreamState(chunks=[])
    events = ssvc.update_stream_state_from_packet(
        packet={},
        runtime=SimpleNamespace(provider="openai"),
        state=state,
        ollama_telemetry={"eval_count": 1},
        extract_ollama_telemetry_fn=lambda _p: {"eval_count": 9},
        extract_sse_tool_calls_fn=lambda _p: [],
        extract_sse_contents_fn=lambda _p: [],
        on_first_chunk_fn=lambda _c: None,
    )
    assert events == []
    assert state.chunk_count == 0
    assert state.chunks == []


def test_tasks_onnx_trace_helpers_accept_none_tracer() -> None:
    request = _Request(content="hello", session_id="sess")
    runtime = _Runtime()
    tsvc.trace_onnx_task_start(
        tracer=None,
        task_id="t1",
        request=request,
        runtime=runtime,
    )
    tsvc.trace_onnx_task_success(tracer=None, task_id="t1", result="ok")
    tsvc.trace_onnx_task_failure(tracer=None, task_id="t1", exc=RuntimeError("x"))


async def _noop_sleep() -> None:
    return None


async def _emit_error() -> str:
    return "event: error\\ndata: {}\\n\\n"
