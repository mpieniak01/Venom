"""Receiver-side SSE timing must not turn event/word counts into model tokens."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scripts.dev import _202c_common as common


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Response:
    status = 200
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}

    def __init__(self, frames, clock):
        self.frames = iter(frames)
        self.clock = clock

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def readline(self, size):
        delay, raw = next(self.frames, (0, b""))
        self.clock.now += delay
        return raw


def frame(name, data, delay=0):
    return [
        (0, ("event: " + name + "\n").encode()),
        (0, ("data: " + json.dumps(data) + "\n").encode()),
        (delay, b"\n"),
    ]


def run(monkeypatch, frames, timeout=1):
    clock = Clock()
    monkeypatch.setattr(common.time, "perf_counter", clock)
    response = Response(frames, clock)
    monkeypatch.setattr(common.request, "urlopen", lambda *a, **k: response)
    return common.stream_simple_chat(
        "http://fixture.invalid",
        prompt="test",
        model="test-model",
        max_tokens=32,
        temperature=0,
        timeout_sec=timeout,
    )


def test_first_text_is_timed_before_done_ignoring_metadata_and_whitespace(monkeypatch):
    frames = (
        frame("meta", {}, 0.01)
        + frame("content", {"text": " "}, 0.01)
        + frame("content", {"text": "hello "}, 0.02)
        + frame("content", {"text": "world"}, 0.08)
        + frame("done", {}, 0.01)
    )
    result = run(monkeypatch, frames)
    assert result.ok and result.text == "hello world"
    assert result.first_token_latency_ms == pytest.approx(40)
    assert result.latency_ms == pytest.approx(130)
    assert result.event_count == 5
    assert result.first_token_latency_ms != result.latency_ms / result.event_count


@pytest.mark.parametrize(
    "frames,reason",
    [
        (frame("content", {"text": "partial"}), "empty_or_incomplete"),
        (frame("error", {"error": "model failed"}), "server_error_event"),
        (frame("content", {"text": None}) + frame("done", {}), "invalid_content_event"),
        (frame("content", {"text": " "}) + frame("done", {}), "empty_or_incomplete"),
        (
            [(0, b"event: content\n"), (0, b"data: not-json\n"), (0, b"\n")],
            "JSONDecodeError",
        ),
        ([(0, b"data: " + b"x" * 65537 + b"\n")], "stream_too_large"),
        ([(0, b"data: " + bytes([255]) + b"\n")], "UnicodeDecodeError"),
    ],
)
def test_invalid_or_failed_stream_is_not_a_successful_sample(
    monkeypatch, frames, reason
):
    result = run(monkeypatch, frames)
    assert not result.ok and reason in result.error


def test_wall_clock_deadline_is_not_reset_by_new_events(monkeypatch):
    result = run(
        monkeypatch,
        frame("content", {"text": "one"}, 0.08)
        + frame("content", {"text": "two"}, 0.08)
        + frame("done", {}),
        timeout=0.1,
    )
    assert not result.ok and "deadline_exceeded" in result.error


def test_non_sse_body_is_not_a_timing_measurement(monkeypatch):
    monkeypatch.setattr(Response, "headers", {"Content-Type": "application/json"})
    result = run(monkeypatch, [])
    assert not result.ok and "response_is_not_sse" in result.error


def test_benchmark_reports_observed_latency_and_no_word_based_token_rate(monkeypatch):
    monkeypatch.setitem(sys.modules, "_202c_common", common)
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts/dev/202c_latency_memory_benchmark.py"
    )
    spec = importlib.util.spec_from_file_location("perf202c_metrics_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "activate_runtime", lambda *a: (True, "ok", {}))
    monkeypatch.setattr(module, "system_memory_used_mb", lambda: 10)
    monkeypatch.setattr(module, "gpu_memory_used_mb", lambda: 20)
    monkeypatch.setattr(
        module,
        "stream_simple_chat",
        lambda *a, **k: common.StreamResult(
            True, "one two three", 100, 99, first_token_latency_ms=20
        ),
    )
    result = module._run_benchmark_for_runtime(
        base_url="http://fixture.invalid",
        runtime_id="test",
        model_name="test-model",
        prompts=[{"id": "p1", "prompt": "test"}],
        repetitions=2,
        warmup=0,
        max_tokens=32,
        temperature=0,
    )
    assert result["summary"]["first_token_latency_ms"]["p95_ms"] == 20
    assert result["samples"][0]["first_token_latency_ms"] == 20
    assert result["summary"]["tokens_per_sec"]["status"] == "UNAVAILABLE"
    assert result["summary"]["tokens_per_sec"]["p50"] is None


def test_late_terminal_event_cannot_bypass_wall_clock_deadline(monkeypatch):
    result = run(
        monkeypatch,
        frame("content", {"text": "one"}, 0.01) + frame("done", {}, 0.2),
        timeout=0.1,
    )
    assert not result.ok and "deadline_exceeded" in result.error
