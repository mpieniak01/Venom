from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from venom_core.services import knowledge_lessons_service as ksvc
from venom_core.services import llm_simple_stream_service as ssvc
from venom_core.services import llm_simple_transport as transport
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


async def _noop_sleep() -> None:
    return None


async def _emit_error() -> str:
    return "event: error\\ndata: {}\\n\\n"
