"""Receiver-side SSE timing must not turn event/word counts into model tokens."""

import importlib.util
import io
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

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

    def read1(self, size):
        return self.readline(size)


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


def test_native_usage_drives_rate_and_receiver_tpot_not_word_or_event_counts(
    monkeypatch,
):
    frames = (
        frame("meta", {}, 0.01)
        + frame("content", {"text": "kot "}, 0.02)
        + frame("content", {"text": "ma"}, 0.07)
        + frame(
            "done",
            {
                "usage_source": "upstream",
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 7,
                    "total_tokens": 10,
                },
            },
            0.01,
        )
    )
    result = run(monkeypatch, frames)
    assert result.ok and result.output_tokens == 7 and result.prompt_tokens == 3
    assert result.usage_source == "upstream" and result.total_tokens == 10
    assert result.tokens_per_second == pytest.approx(7 / 0.11)
    assert result.time_per_output_token_ms == pytest.approx((110 - 30) / 6)
    assert len(result.text.split()) == 2 and result.event_count == 4


def test_aggregated_single_text_event_has_no_observable_tpot(monkeypatch):
    result = run(
        monkeypatch,
        frame("content", {"text": "many words at once"}, 0.1)
        + frame(
            "done",
            {"usage_source": "upstream", "usage": {"completion_tokens": 7}},
            0.01,
        ),
    )
    assert result.ok and result.tokens_per_second == pytest.approx(7 / 0.11)
    assert result.time_per_output_token_ms is None


def test_heuristic_usage_without_upstream_provenance_is_not_token_evidence(monkeypatch):
    result = run(
        monkeypatch,
        frame("content", {"text": "one two"}, 0.1)
        + frame(
            "done",
            {"usage_source": "word_estimate", "usage": {"completion_tokens": 2}},
            0.01,
        ),
    )
    assert result.ok and result.output_tokens is None
    assert result.tokens_per_second is None and result.time_per_output_token_ms is None


@pytest.mark.parametrize(
    "usage",
    [
        {"completion_tokens": True},
        {"completion_tokens": -1},
        {"completion_tokens": "7"},
        {"completion_tokens": 2.5},
        {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 99},
        {"completion_tokens": 0},
    ],
)
def test_invalid_native_usage_is_not_a_qualified_measurement(monkeypatch, usage):
    result = run(
        monkeypatch,
        frame("content", {"text": "text"}, 0.1)
        + frame("done", {"usage_source": "upstream", "usage": usage}, 0.01),
    )
    assert not result.ok
    assert "native_" in result.error


class ResourceReadError(Exception):
    pass


@pytest.fixture
def resource_fixture(monkeypatch):
    clock = Clock()
    state = SimpleNamespace(
        clock=clock,
        processes={10: {"birth": 900.0, "cpu": 100.0, "rss": 10.0, "children": []}},
        node_used_mb=100.0,
        memory_reads=[],
        threads=[],
    )

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def record(self):
            if self.pid not in state.processes:
                raise ResourceReadError("gone")
            return state.processes[self.pid]

        def create_time(self):
            return self.record()["birth"]

        def children(self, recursive):
            assert recursive is True
            return [Process(pid) for pid in self.record()["children"]]

        def cpu_times(self):
            record = self.record()
            if record.get("cpu_error"):
                raise ResourceReadError("cpu denied")
            return SimpleNamespace(user=record["cpu"], system=0.0)

        def memory_info(self):
            record = self.record()
            state.memory_reads.append(self.pid)
            if record.get("rss_error"):
                raise ResourceReadError("rss denied")
            return SimpleNamespace(rss=record["rss"] * 1024**2)

        def terminate(self):
            pytest.fail("target process must never be terminated")

        kill = terminate

    def node_memory():
        if state.node_used_mb is None:
            raise ResourceReadError("node denied")
        return SimpleNamespace(
            total=1024 * 1024**2,
            available=(1024 - state.node_used_mb) * 1024**2,
        )

    class DormantThread:
        def __init__(self, target, **kwargs):
            self.target = target
            self.started = False
            self.joins = []
            state.threads.append(self)

        def start(self):
            self.started = True

        def join(self, timeout):
            self.joins.append(timeout)

        def is_alive(self):
            return False

    fake_psutil = SimpleNamespace(
        Process=Process, Error=ResourceReadError, virtual_memory=node_memory
    )
    monkeypatch.setattr(
        common, "importlib", SimpleNamespace(import_module=lambda name: fake_psutil)
    )
    monkeypatch.setattr(
        common,
        "time",
        SimpleNamespace(perf_counter=clock, time=lambda: 1000.0 + clock.now),
    )
    monkeypatch.setattr(
        common,
        "threading",
        SimpleNamespace(
            Event=threading.Event, Lock=threading.Lock, Thread=DormantThread
        ),
    )

    def no_real_monitor(*args, **kwargs):
        pytest.fail("unit tests must not launch hardware monitoring subprocesses")

    monkeypatch.setattr(common.subprocess, "Popen", no_real_monitor)

    def sampler(roots=None, *, enable_gpu=False, **kwargs):
        instance = common.ProcessResourceSampler(roots, **kwargs)
        if not enable_gpu:
            instance._start_gpu_monitor = lambda: None
        return instance

    state.sampler = sampler
    return state


def test_resource_samples_deduplicate_overlapping_roots_and_exclude_historic_cpu(
    resource_fixture,
):
    state = resource_fixture
    state.processes[10]["children"] = [11, 12]
    state.processes[11] = {"birth": 901.0, "cpu": 200.0, "rss": 20.0, "children": [12]}
    state.processes[12] = {"birth": 902.0, "cpu": 300.0, "rss": 30.0, "children": []}
    sampler = state.sampler([10, 11, 10]).start()
    sampler._gpu.add(50.0, 0.0)
    assert sorted(state.memory_reads) == [10, 11, 12]
    state.clock.now = 1.0
    for process in state.processes.values():
        process["cpu"] += 1.0
        process["rss"] += 10.0
    state.node_used_mb = 300.0
    sampler._sample()
    sampler._gpu.add(90.0, 1.0)
    state.clock.now = 2.0
    for process in state.processes.values():
        process["cpu"] += 1.0
        process["rss"] -= 5.0
    state.node_used_mb = 200.0
    sampler._gpu.add(60.0, 2.0)
    result = sampler.finish()
    assert result["status"] == "OK" and not result["errors"]
    assert result["cpu_seconds_observed"] == pytest.approx(6.0)
    assert result["cpu_mean_percent_one_core"] == pytest.approx(300.0)
    assert result["process_rss_mb_sampled_peak"] == 90.0
    assert result["process_rss_mb_mean"] == 75.0
    assert result["node_ram_used_mb_sampled_peak"] == 300.0
    assert result["node_ram_used_mb_mean"] == 200.0
    assert result["gpu_device_used_mb_sampled_peak"] == 90.0
    assert result["gpu_device_used_mb_mean"] == pytest.approx(200.0 / 3)
    assert result["process_sample_count"] == result["gpu_sample_count"] == 3
    assert result["observed_process_identity_count"] == 3
    assert len(result["root_identities"]) == 2
    assert result["sampling"]["process"]["actual_interval_mean_s"] == 1.0
    assert result["sampling"]["process"]["last_sample_elapsed_s"] == 2.0
    assert sampler.finish() == result  # Idempotent cleanup, no second sampling.


def test_resource_loop_samples_middle_of_window_and_counts_new_child_from_birth(
    resource_fixture,
):
    state = resource_fixture
    sampler = state.sampler([10], interval_sec=0.2).start()
    waits = []

    class SampleSteps:
        def wait(self, interval):
            waits.append(interval)
            state.clock.now += interval
            if len(waits) == 1:
                state.processes[10]["children"] = [11]
                state.processes[11] = {
                    "birth": 1000.1,
                    "cpu": 0.1,
                    "rss": 100.0,
                    "children": [],
                }
                return False
            if len(waits) == 2:
                state.processes[11]["cpu"] = 0.2
                state.processes[11]["rss"] = 0.0
                return False
            return True

        def set(self):
            pass

    sampler._stop = SampleSteps()
    sampler._sample_loop()
    result = sampler.finish()
    assert waits == [0.2, 0.2, 0.2]
    assert result["process_sample_count"] == 4
    assert result["process_rss_mb_sampled_peak"] == 110.0
    assert result["cpu_seconds_observed"] == pytest.approx(0.2)
    assert result["cpu_mean_percent_one_core"] == pytest.approx(100 / 3)


def test_resource_no_roots_means_nullable_metrics_without_threads_or_subprocesses(
    resource_fixture,
):
    state = resource_fixture
    sampler = state.sampler(enable_gpu=True).start()
    state.clock.now = 1.0
    result = sampler.finish()
    assert result["status"] == "UNAVAILABLE"
    assert result["root_identities"] == []
    assert result["process_sample_count"] == result["gpu_sample_count"] == 0
    assert state.threads == [] and state.memory_reads == []
    for key in (
        "cpu_mean_percent_one_core",
        "cpu_seconds_observed",
        "process_rss_mb_sampled_peak",
        "process_rss_mb_mean",
        "node_ram_used_mb_sampled_peak",
        "gpu_device_used_mb_sampled_peak",
        "gpu_device_used_mb_mean",
    ):
        assert result[key] is None


def test_resource_missing_root_at_start_does_not_start_monitor(resource_fixture):
    state = resource_fixture
    result = state.sampler([999], enable_gpu=True).start().finish()
    assert result["status"] == "UNAVAILABLE"
    assert result["root_identities"] == [
        {"pid": 999, "create_time": None, "status": "UNAVAILABLE"}
    ]
    assert state.threads == []
    assert result["cpu_seconds_observed"] is None
    assert result["node_ram_used_mb_sampled_peak"] is None


@pytest.mark.parametrize("replacement", [None, 1001.0])
def test_resource_root_loss_or_pid_reuse_marks_partial_without_following_pid(
    resource_fixture,
    replacement,
):
    state = resource_fixture
    sampler = state.sampler([10]).start()
    state.clock.now = 1.0
    if replacement is None:
        del state.processes[10]
    else:
        state.processes[10].update(birth=replacement, cpu=99999.0, rss=99999.0)
    sampler._sample()
    state.clock.now = 2.0
    result = sampler.finish()
    assert result["status"] == "PARTIAL"
    assert result["root_identities"][0]["create_time"] == 900.0
    assert result["root_identities"][0]["status"] in {"UNAVAILABLE", "CHANGED"}
    assert result["retired_process_count"] == 1
    assert state.memory_reads == [10]
    assert result["cpu_seconds_observed"] is None
    assert result["process_rss_mb_sampled_peak"] == 10.0


def test_resource_reused_descendant_is_excluded_even_with_live_root(resource_fixture):
    state = resource_fixture
    state.processes[10]["children"] = [11]
    state.processes[11] = {"birth": 901.0, "cpu": 200.0, "rss": 20.0, "children": []}
    sampler = state.sampler([10]).start()
    state.clock.now = 1.0
    state.processes[11].update(birth=1000.5, cpu=99999.0, rss=99999.0)
    result = sampler.finish()
    assert result["status"] == "PARTIAL"
    assert result["process_rss_mb_sampled_peak"] == 30.0
    assert result["cpu_seconds_observed"] == 0.0
    assert result["retired_process_count"] == 1
    assert state.memory_reads.count(11) == 1


def test_resource_unknown_reads_stay_none_but_valid_idle_zero_is_reported(
    resource_fixture,
):
    state = resource_fixture
    state.processes[10].update(cpu_error=True, rss_error=True)
    state.node_used_mb = None
    sampler = state.sampler([10]).start()
    state.clock.now = 1.0
    unknown = sampler.finish()
    assert unknown["status"] == "UNAVAILABLE"
    assert unknown["cpu_seconds_observed"] is None
    assert unknown["process_rss_mb_sampled_peak"] is None
    assert unknown["node_ram_used_mb_sampled_peak"] is None
    assert unknown["gpu_device_used_mb_sampled_peak"] is None
    state.processes[10].update(cpu_error=False, rss_error=False, rss=0.0)
    state.node_used_mb = 0.0
    sampler = state.sampler([10]).start()
    state.clock.now = 2.0
    idle = sampler.finish()
    assert idle["cpu_seconds_observed"] == 0.0
    assert idle["cpu_mean_percent_one_core"] == 0.0
    assert idle["process_rss_mb_sampled_peak"] == 0.0
    assert idle["node_ram_used_mb_sampled_peak"] == 0.0
    assert idle["gpu_device_used_mb_sampled_peak"] is None


def test_resource_unavailable_psutil_reports_requested_identity(
    resource_fixture, monkeypatch
):
    def missing_psutil(name):
        raise ImportError("fixture")

    monkeypatch.setattr(common.importlib, "import_module", missing_psutil)
    sampler = resource_fixture.sampler([10], enable_gpu=True).start()
    result = sampler.finish()
    assert result["status"] == "UNAVAILABLE"
    assert "psutil_unavailable" in result["errors"]
    assert result["root_identities"][0]["pid"] == 10
    assert resource_fixture.threads == []


def test_resource_gpu_reader_bounds_and_validates_samples_and_cleans_only_owned_handle(
    resource_fixture,
    monkeypatch,
):
    state = resource_fixture
    calls = []

    class Monitor:
        def __init__(self):
            self.stdout = io.StringIO("0\n12.5\nN/A\nNaN\n" + "9" * 200 + "\n17\n")
            self.terminate_count = 0
            self.kill_count = 0
            self.waits = []

        def poll(self):
            return None

        def terminate(self):
            self.terminate_count += 1

        def kill(self):
            self.kill_count += 1

        def wait(self, timeout):
            self.waits.append(timeout)
            if len(self.waits) == 1:
                raise common.subprocess.TimeoutExpired("fixture-monitor", timeout)
            return 0

    monitor = Monitor()

    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return monitor

    monkeypatch.setattr(common.subprocess, "Popen", popen)
    sampler = state.sampler(
        [10], enable_gpu=True, interval_sec=0.2, gpu_index=2
    ).start()
    sampler.start()  # One monitor per window, even if start is called twice.
    sampler._read_gpu()
    state.clock.now = 1.0
    result = sampler.finish()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [
        "nvidia-smi",
        "--query-gpu=memory.used",
        "--format=csv,noheader,nounits",
        "--id=2",
        "--loop-ms=200",
    ]
    assert kwargs["stderr"] == common.subprocess.DEVNULL
    assert result["gpu_sample_count"] == 3
    assert result["gpu_device_used_mb_sampled_peak"] == 17.0
    assert result["gpu_device_used_mb_mean"] == pytest.approx(29.5 / 3)
    assert result["gpu_scope"] == "whole_device_not_process_attributed"
    assert monitor.terminate_count == monitor.kill_count == 1
    assert monitor.waits == [1.0, 1.0]
    assert monitor.stdout.closed
    assert all(thread.joins == [1.0] for thread in state.threads)
    assert "gpu_monitor_invalid_or_oversized_line" in result["errors"]
    assert "gpu_monitor_invalid_numeric_reading" in result["errors"]
    sampler.finish()
    assert monitor.terminate_count == 1


def test_resource_gpu_launch_failure_keeps_device_metrics_unknown(
    resource_fixture, monkeypatch
):
    def absent_monitor(*args, **kwargs):
        raise FileNotFoundError("fixture")

    monkeypatch.setattr(common.subprocess, "Popen", absent_monitor)
    sampler = resource_fixture.sampler([10], enable_gpu=True).start()
    resource_fixture.clock.now = 1.0
    result = sampler.finish()
    assert result["status"] == "PARTIAL"
    assert result["gpu_status"] == "UNAVAILABLE"
    assert result["gpu_device_used_mb_sampled_peak"] is None
    assert result["gpu_sample_count"] == 0
    assert result["cpu_seconds_observed"] == 0.0


@pytest.mark.parametrize("interval", [0, -1, 0.01, 5.01, float("nan"), float("inf")])
def test_resource_invalid_sampling_interval_is_rejected(interval):
    with pytest.raises(ValueError, match="interval_sec"):
        common.ProcessResourceSampler([10], interval_sec=interval)


@pytest.mark.parametrize("roots", [[0], [-1], [True], ["10"], list(range(1, 4098))])
def test_resource_invalid_root_scope_is_rejected(roots):
    with pytest.raises(ValueError, match="root_pids"):
        common.ProcessResourceSampler(roots)


@pytest.mark.parametrize("gpu_index", [-1, True, "0"])
def test_resource_invalid_gpu_index_is_rejected(gpu_index):
    with pytest.raises(ValueError, match="gpu_index"):
        common.ProcessResourceSampler([10], gpu_index=gpu_index)


def test_resource_finish_before_start_is_explicitly_unavailable():
    result = common.ProcessResourceSampler([10]).finish()
    assert result["status"] == "UNAVAILABLE"
    assert "sampler_not_started" in result["errors"]
    assert result["cpu_seconds_observed"] is None


@pytest.fixture
def benchmark_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "_202c_common", common)
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts/dev/202c_latency_memory_benchmark.py"
    )
    spec = importlib.util.spec_from_file_location("perf202c_resources_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_benchmark(module, **kwargs):
    arguments = {
        "base_url": "http://fixture.invalid",
        "runtime_id": "fixture",
        "model_name": "fixture-model",
        "prompts": [{"id": "p1", "prompt": "fixture"}],
        "repetitions": 2,
        "warmup": 2,
        "max_tokens": 32,
        "temperature": 0,
    }
    arguments.update(kwargs)
    return module._run_benchmark_for_runtime(**arguments)


def test_benchmark_resource_window_wraps_only_measured_repetitions(
    benchmark_module,
    monkeypatch,
):
    module = benchmark_module
    events = []
    resource_summary = common.ProcessResourceSampler().finish()

    class Sampler:
        def __init__(self, **kwargs):
            events.append(("construct", kwargs))

        def start(self):
            events.append("start")
            return self

        def finish(self):
            events.append("finish")
            return resource_summary

    def activate(*args):
        events.append("activate")
        return True, "ok", {}

    def request(*args, **kwargs):
        events.append("request")
        return common.StreamResult(True, "fixture", 100, 1)

    monkeypatch.setattr(module, "ProcessResourceSampler", Sampler)
    monkeypatch.setattr(module, "activate_runtime", activate)
    monkeypatch.setattr(module, "stream_simple_chat", request)
    result = fixture_benchmark(
        module, process_root_pids=[10, 11], sample_interval_sec=0.2, gpu_index=2
    )
    assert events == [
        "activate",
        "request",
        "request",
        "request",
        ("construct", {"root_pids": [10, 11], "interval_sec": 0.2, "gpu_index": 2}),
        "start",
        "request",
        "request",
        "finish",
    ]
    assert result["resources"]["benchmark_stage"] == "measured_repetitions_only"
    assert result["resources"]["excluded_stages"] == [
        "activation",
        "first_post_activation_request",
        "warmup",
    ]
    assert result["summary"]["host_mem_used_mb_peak"] is None
    assert result["summary"]["gpu_mem_used_mb_peak"] is None
    assert not any("mem" in key for sample in result["samples"] for key in sample)


@pytest.mark.parametrize("fail_request", [4, 5])
def test_benchmark_request_exception_always_finishes_sampler(
    benchmark_module,
    monkeypatch,
    fail_request,
):
    module = benchmark_module
    events = []
    request_count = 0

    class Sampler:
        def __init__(self, **kwargs):
            pass

        def start(self):
            events.append("start")
            return self

        def finish(self):
            events.append("finish")
            return {}

    def request(*args, **kwargs):
        nonlocal request_count
        request_count += 1
        if request_count == fail_request:
            events.append("request_exception")
            raise RuntimeError("fixture request failed")
        events.append("request")
        return common.StreamResult(True, "fixture", 100, 1)

    monkeypatch.setattr(module, "ProcessResourceSampler", Sampler)
    monkeypatch.setattr(module, "activate_runtime", lambda *a: (True, "ok", {}))
    monkeypatch.setattr(module, "stream_simple_chat", request)
    with pytest.raises(RuntimeError, match="fixture request failed"):
        fixture_benchmark(module)
    assert events[-2:] == ["request_exception", "finish"]
    assert events.count("start") == events.count("finish") == 1
    assert events.index("start") == 3


def test_benchmark_unavailable_resources_remain_nullable_in_json_and_markdown(
    benchmark_module,
    resource_fixture,
    monkeypatch,
):
    module = benchmark_module
    monkeypatch.setattr(module, "activate_runtime", lambda *a: (True, "ok", {}))
    monkeypatch.setattr(
        module,
        "stream_simple_chat",
        lambda *a, **k: common.StreamResult(True, "fixture", 100, 1),
    )
    result = fixture_benchmark(module, process_root_pids=None)
    assert result["resources"]["status"] == "UNAVAILABLE"
    assert resource_fixture.threads == []
    assert result["summary"]["cpu_mean_percent_one_core"] is None
    assert result["summary"]["process_rss_mb_sampled_peak"] is None
    assert result["summary"]["node_ram_used_mb_sampled_peak"] is None
    assert result["summary"]["gpu_device_used_mb_sampled_peak"] is None
    restored = json.loads(json.dumps(result))
    assert restored["resources"]["cpu_seconds_observed"] is None
    markdown = module._build_markdown({"baseline": result, "candidate": result})
    for metric in (
        "cpu_mean_percent_one_core",
        "process_rss_mb_sampled_peak",
        "node_ram_used_mb_sampled_peak",
        "gpu_device_used_mb_sampled_peak",
    ):
        assert f"| {metric} | unavailable | unavailable |" in markdown


def test_resource_gpu_sample_returning_after_stop_is_discarded(resource_fixture):
    sampler = resource_fixture.sampler([10]).start()

    class DelayedOutput:
        def readline(self, size):
            sampler._stop.set()
            return "99999\n"

    sampler._gpu_monitor = SimpleNamespace(stdout=DelayedOutput())
    sampler._read_gpu()
    assert sampler._gpu.count == 0
    assert sampler._gpu.peak is None
    sampler._gpu_monitor = None
    sampler.finish()


def test_resource_no_cpu_delta_cannot_be_a_complete_resource_result(resource_fixture):
    state = resource_fixture
    sampler = state.sampler([10]).start()
    sampler._worker = None  # A single snapshot has no observed CPU-time delta.
    sampler._gpu.add(0.0, 0.0)
    result = sampler.finish()
    assert result["status"] == "PARTIAL"
    assert result["cpu_status"] == "UNAVAILABLE"
    assert result["cpu_seconds_observed"] is None
    assert result["process_rss_mb_sampled_peak"] == 10.0


@pytest.mark.parametrize(
    "candidate",
    [
        {},
        {"activation_ok": False, "summary": {}, "samples": []},
        {
            "activation_ok": True,
            "summary": {"success_count": 0, "p95_ms": None},
            "samples": [{"ok": False}],
        },
    ],
)
def test_benchmark_missing_or_failed_candidate_has_no_latency_kpi(
    benchmark_module,
    candidate,
):
    baseline = {
        "activation_ok": True,
        "summary": {"success_count": 1, "p95_ms": 100.0},
        "samples": [{"ok": True}],
    }
    kpi, derived = benchmark_module._comparison_metrics(baseline, candidate)
    assert kpi["p95_latency_within_25pct"] is None
    assert kpi["p95_latency_within_35pct"] is None
    assert derived["p95_ratio_candidate_vs_baseline"] is None
    markdown = benchmark_module._build_markdown(
        {"baseline": baseline, "candidate": candidate, "kpi": kpi}
    )
    assert "| p95_ms | 100.0 | unavailable |" in markdown
    assert "- p95_latency_within_25pct: unavailable" in markdown


def test_resource_sampling_scope_and_error_storage_are_bounded(resource_fixture):
    state = resource_fixture
    state.processes[10]["children"] = [11, 12]
    for pid in (11, 12):
        state.processes[pid] = {
            "birth": 900.0 + pid,
            "cpu": 100.0,
            "rss": 10.0,
            "children": [],
        }
    sampler = state.sampler([10])
    sampler._MAX_PROCESSES = 2
    sampler.start()
    state.clock.now = 1.0
    result = sampler.finish()
    assert "process_scope_limit_reached" in result["errors"]
    assert result["observed_process_identity_count"] == 2
    assert 12 not in state.memory_reads
    for index in range(100):
        sampler._error(f"fixture_error:{index}")
    assert len(sampler._errors) == sampler._MAX_ERRORS
    assert sampler._dropped_errors > 0


def test_resource_worker_shutdown_timeout_is_finite_and_partial(resource_fixture):
    state = resource_fixture
    sampler = state.sampler([10]).start()
    sampler._worker.is_alive = lambda: True
    state.clock.now = 1.0
    result = sampler.finish()
    assert sampler._worker.joins == [1.0]
    assert "process_sampler_shutdown_timeout" in result["errors"]
    assert result["status"] == "PARTIAL"
    assert result["cpu_seconds_observed"] is None


@pytest.mark.parametrize("seed", [None, 0, 42])
def test_benchmark_receiver_preserves_seed_in_http_body(monkeypatch, seed):
    clock = Clock()
    response = Response(frame("content", {"text": "reply"}) + frame("done", {}), clock)
    captured = []

    def open_response(req, **kwargs):
        captured.append(json.loads(req.data))
        return response

    monkeypatch.setattr(common.request, "urlopen", open_response)
    monkeypatch.setattr(common.time, "perf_counter", clock)
    result = common.stream_simple_chat(
        "http://fixture.invalid",
        prompt="test",
        model="fixture",
        max_tokens=32,
        temperature=0,
        seed=seed,
    )
    assert result.ok
    if seed is None:
        assert "seed" not in captured[0]
    else:
        assert captured[0]["seed"] == seed


@pytest.mark.parametrize("seed", [None, 0, 42])
def test_benchmark_forwards_same_seed_to_first_warmup_and_measured_requests(
    benchmark_module, monkeypatch, seed
):
    module = benchmark_module
    captured = []
    monkeypatch.setattr(module, "activate_runtime", lambda *a: (True, "ok", {}))

    def request(*args, **kwargs):
        captured.append(kwargs.get("seed"))
        return common.StreamResult(True, "fixture", 100, 1)

    monkeypatch.setattr(module, "stream_simple_chat", request)
    result = fixture_benchmark(module, seed=seed)
    assert captured == [seed] * 5
    assert result["requested_generation_settings"]["seed"] == seed


def test_benchmark_cli_rejects_seed_outside_provider_range(benchmark_module):
    assert benchmark_module._generation_seed("0") == 0
    assert benchmark_module._generation_seed(str(-(2**63))) == -(2**63)
    with pytest.raises(ValueError):
        benchmark_module._generation_seed("not-an-int")
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        benchmark_module._generation_seed(str(2**63))


def native_frame(packet, delay=0):
    text = packet if isinstance(packet, str) else json.dumps(packet, ensure_ascii=False)
    return [(0, ("data: " + text + "\n").encode()), (delay, b"\n")]


def native_packet(text="", *, finish=None, model="fixture-model", usage=None):
    packet = {
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]
    }
    if model is not None:
        packet["model"] = model
    if usage is not None:
        packet["usage"] = usage
    return packet


def run_native(monkeypatch, frames, timeout=1):
    clock = Clock()
    monkeypatch.setattr(common.time, "perf_counter", clock)
    response = Response(frames, clock)
    monkeypatch.setattr(common.request, "urlopen", lambda *a, **k: response)
    return common.native_chat(
        "http://fixture.invalid/v1",
        prompt="test",
        model="fixture-model",
        max_tokens=32,
        temperature=0,
        timeout_sec=timeout,
    )


def test_native_receiver_times_text_and_reads_usage_after_finish(monkeypatch):
    result = run_native(
        monkeypatch,
        native_frame(native_packet(), 0.01)
        + native_frame(native_packet("kot "), 0.02)
        + native_frame(native_packet("ma"), 0.07)
        + native_frame(native_packet(finish="stop"))
        + native_frame(
            {
                "choices": [],
                "model": "fixture-model",
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 7,
                    "total_tokens": 10,
                },
            },
            0.01,
        )
        + native_frame("[DONE]"),
    )
    assert result.ok and result.text == "kot ma"
    assert result.first_token_latency_ms == pytest.approx(30)
    assert result.latency_ms == pytest.approx(110)
    assert result.output_tokens == 7 and result.total_tokens == 10
    assert result.reported_model == "fixture-model"
    assert result.tokens_per_second == pytest.approx(7 / 0.11)
    assert result.time_per_output_token_ms == pytest.approx((110 - 30) / 6)


@pytest.mark.parametrize("terminal", ["stop", "length"])
def test_native_eof_after_successful_finish_is_complete(monkeypatch, terminal):
    result = run_native(
        monkeypatch, native_frame(native_packet("answer", finish=terminal), 0.1)
    )
    assert result.ok and result.tokens_per_second is None
    assert result.time_per_output_token_ms is None


@pytest.mark.parametrize(
    "frames,reason",
    [
        (native_frame(native_packet("partial")), "empty_or_incomplete"),
        (native_frame("[DONE]"), "empty_or_incomplete"),
        (
            native_frame(native_packet("partial", finish="abort"))
            + native_frame("[DONE]"),
            "native_unsuccessful_finish",
        ),
        (
            native_frame(native_packet("partial", finish="error"))
            + native_frame("[DONE]"),
            "native_unsuccessful_finish",
        ),
        (
            native_frame({"error": {"message": "failed"}}) + native_frame("[DONE]"),
            "native_error_packet",
        ),
        (
            native_frame(native_packet("wrong", finish="stop", model="other")),
            "native_reported_model_mismatch",
        ),
        (
            native_frame(
                native_packet(
                    "bad",
                    finish="stop",
                    usage={
                        "completion_tokens": True,
                    },
                )
            ),
            "invalid_native_usage_counter",
        ),
        (
            native_frame(
                native_packet(
                    "bad",
                    finish="stop",
                    usage={
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "total_tokens": 99,
                    },
                )
            ),
            "inconsistent_native_usage_total",
        ),
        ([(0, b"data: " + b"x" * 65537 + b"\n")], "stream_too_large"),
        (native_frame("not-json"), "JSONDecodeError"),
    ],
)
def test_native_rejects_partial_abort_error_and_invalid_evidence(
    monkeypatch, frames, reason
):
    result = run_native(monkeypatch, frames)
    assert not result.ok and reason in result.error


def test_native_missing_model_is_unconfirmed_and_usage_is_not_estimated(monkeypatch):
    result = run_native(
        monkeypatch,
        native_frame(native_packet("many words", finish="stop", model=None), 0.1),
    )
    assert result.ok and result.reported_model is None
    assert result.output_tokens is None and result.tokens_per_second is None


def test_native_late_done_cannot_bypass_absolute_deadline(monkeypatch):
    result = run_native(
        monkeypatch,
        native_frame(native_packet("answer"), 0.01) + native_frame("[DONE]", 0.2),
        timeout=0.1,
    )
    assert not result.ok and "deadline_exceeded" in result.error


def test_native_text_response_has_native_usage_but_no_stream_ttft(monkeypatch):
    clock, captured = Clock(), []

    class JsonResponse(Response):
        headers = {"Content-Type": "application/json"}

        def read1(self, size):
            if getattr(self, "_read", False):
                return b""
            self._read = True
            clock.now += 0.1
            return json.dumps(
                {
                    "model": "fixture-model",
                    "choices": [
                        {"message": {"content": "full reply"}, "finish_reason": "stop"}
                    ],
                    "usage": {"completion_tokens": 7},
                }
            ).encode()

    def opener(req, **kwargs):
        captured.append(json.loads(req.data))
        return JsonResponse([], clock)

    monkeypatch.setattr(common.request, "urlopen", opener)
    monkeypatch.setattr(common.time, "perf_counter", clock)
    result = common.native_chat(
        "http://fixture.invalid/v1",
        prompt="test",
        model="fixture-model",
        max_tokens=17,
        temperature=0,
        seed=42,
        stream=False,
    )
    assert result.ok and result.output_tokens == 7
    assert result.first_token_latency_ms is None
    assert result.time_per_output_token_ms is None
    assert result.tokens_per_second == pytest.approx(70)
    assert captured[0]["stream"] is False and captured[0]["seed"] == 42
    assert captured[0]["max_tokens"] == 17
    assert "stream_options" not in captured[0]


def test_simple_nonstream_payload_has_no_token_stream_ttft(monkeypatch):
    clock, captured = Clock(), []
    response = Response(
        frame("content", {"text": "full reply"}, 0.1)
        + frame(
            "done", {"usage_source": "upstream", "usage": {"completion_tokens": 7}}
        ),
        clock,
    )

    def opener(req, **kwargs):
        captured.append(json.loads(req.data))
        return response

    monkeypatch.setattr(common.request, "urlopen", opener)
    monkeypatch.setattr(common.time, "perf_counter", clock)
    result = common.stream_simple_chat(
        "http://fixture.invalid",
        prompt="test",
        model="fixture-model",
        max_tokens=17,
        temperature=0,
        stream=False,
    )
    assert result.ok and captured[0]["stream"] is False
    assert result.first_token_latency_ms is None
    assert result.time_per_output_token_ms is None


def test_jsonl_preserves_stream_and_per_case_output_budget(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"id": "text", "prompt": "test", "stream": False, "max_tokens": 17})
        + "\n"
    )
    case = common.load_prompts_jsonl(path)[0]
    assert case["stream"] is False and case["max_tokens"] == 17


@pytest.mark.parametrize(
    "metadata", [{"stream": "false"}, {"max_tokens": True}, {"max_tokens": 0}]
)
def test_jsonl_rejects_ambiguous_generation_metadata(tmp_path, metadata):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"prompt": "test", **metadata}) + "\n")
    with pytest.raises(ValueError, match="invalid"):
        common.load_prompts_jsonl(path)


def test_native_benchmark_uses_case_metadata_without_venom_activation(
    benchmark_module, monkeypatch
):
    module, captured = benchmark_module, []

    def forbidden(*args, **kwargs):
        pytest.fail("native measurement must not activate Venom")

    def receiver(url, **kwargs):
        captured.append((url, kwargs))
        return common.StreamResult(True, "fixture", 100, 1)

    monkeypatch.setattr(module, "activate_runtime", forbidden)
    monkeypatch.setattr(module, "native_chat", receiver)
    result = fixture_benchmark(
        module,
        transport="native",
        native_base_url="http://fixture.invalid/v1",
        prompts=[
            {"id": "text", "prompt": "fixture", "stream": False, "max_tokens": 17}
        ],
        seed=42,
    )
    assert len(captured) == 5 and result["measurement_complete"]
    assert all(url.endswith("/v1") for url, _ in captured)
    assert all(
        args["stream"] is False and args["max_tokens"] == 17 and args["seed"] == 42
        for _, args in captured
    )
    assert result["samples"][0]["model_identity"] == "unreported"
    assert result["samples"][0]["stream"] is False


@pytest.mark.parametrize("repetitions,warmup", [(0, 0), (-1, 0), (1, -1)])
def test_invalid_counts_are_rejected_before_activation(
    benchmark_module, monkeypatch, repetitions, warmup
):
    monkeypatch.setattr(
        benchmark_module,
        "activate_runtime",
        lambda *args: pytest.fail("invalid counts must not mutate runtime"),
    )
    with pytest.raises(ValueError, match="invalid_benchmark_counts"):
        fixture_benchmark(benchmark_module, repetitions=repetitions, warmup=warmup)


def complete_benchmark_result(repetitions=2, warmup=1):
    return {
        "activation_ok": True,
        "cold_start": {"ok": True},
        "warmup_samples": [{"ok": True}] * warmup,
        "samples": [{"ok": True}] * repetitions,
        "summary": {"success_count": repetitions, "p95_ms": 100},
        "errors": [],
    }


@pytest.mark.parametrize(
    "failure", [None, "activation", "cold", "warmup", "sample", "incomplete"]
)
def test_cli_native_pair_strict_completeness_without_venom(
    benchmark_module, monkeypatch, tmp_path, failure
):
    module = benchmark_module
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(json.dumps({"prompt": "fixture"}) + "\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--prompts",
            str(corpus),
            "--repetitions",
            "2",
            "--warmup",
            "1",
            "--baseline-transport",
            "native",
            "--candidate-transport",
            "native",
            "--baseline-model",
            "exact-base",
            "--candidate-model",
            "exact-candidate",
            "--baseline-native-base-url",
            "http://base.invalid/v1",
            "--candidate-native-base-url",
            "http://candidate.invalid/v1",
        ],
    )
    reports, calls = [], []

    def forbidden(*args, **kwargs):
        pytest.fail("native pair must not read env or require Venom/options")

    for name in (
        "resolve_base_url",
        "wait_backend_ready",
        "http_json",
        "activate_runtime",
        "pick_gemma3_model_with_reason",
    ):
        monkeypatch.setattr(module, name, forbidden)

    def measure(**kwargs):
        calls.append(kwargs)
        result = complete_benchmark_result()
        if kwargs["model_name"] == "exact-candidate":
            if failure == "activation":
                result["activation_ok"] = False
            elif failure == "cold":
                result["cold_start"]["ok"] = False
            elif failure == "warmup":
                result["warmup_samples"][0]["ok"] = False
            elif failure == "sample":
                result["samples"][0]["ok"] = False
            elif failure == "incomplete":
                result["samples"].pop()
        return result

    monkeypatch.setattr(module, "_run_benchmark_for_runtime", measure)
    monkeypatch.setattr(
        module, "dump_json", lambda path, report: reports.append(report)
    )
    monkeypatch.setattr(module, "dump_text", lambda *args: None)
    assert module.main() == (1 if failure else 0)
    assert [call["model_name"] for call in calls] == ["exact-base", "exact-candidate"]
    assert reports[-1]["measurement_complete"] is (failure is None)
    assert reports[-1]["qualification_status"] == "NOT_QUALIFIED"
    if failure:
        assert any(error.startswith("candidate:") for error in reports[-1]["errors"])


def test_native_fragmented_utf8_and_unterminated_error_are_not_silently_accepted(
    monkeypatch,
):
    wire = b"".join(
        raw
        for _, raw in (
            native_frame(native_packet("żółw", finish="stop")) + native_frame("[DONE]")
        )
    )
    split = wire.index("ż".encode()) + 1
    result = run_native(monkeypatch, [(0, wire[:split]), (0.1, wire[split:])])
    assert result.ok and result.text == "żółw"
    result = run_native(
        monkeypatch,
        native_frame(native_packet("text", finish="stop"))
        + [(0, b'data: {"error": "failed"}')],
    )
    assert not result.ok and "incomplete_native_event" in result.error


def test_native_read_socket_timeout_uses_remaining_wall_clock_budget(monkeypatch):
    clock, timeouts = Clock(), []
    response = Response(
        native_frame(native_packet("text"), 0.2)
        + native_frame(native_packet(finish="stop"), 0.3),
        clock,
    )
    response.fp = SimpleNamespace(
        raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=timeouts.append))
    )
    monkeypatch.setattr(common.time, "perf_counter", clock)
    monkeypatch.setattr(common.request, "urlopen", lambda *a, **k: response)
    result = common.native_chat(
        "http://fixture.invalid/v1",
        prompt="test",
        model="fixture-model",
        max_tokens=32,
        temperature=0,
        timeout_sec=1,
    )
    assert result.ok and timeouts[0] == 1
    assert timeouts[-1] == pytest.approx(0.5)
    assert timeouts == sorted(timeouts, reverse=True)


@pytest.mark.parametrize("stream", [True, False])
def test_native_missing_model_or_endpoint_never_uses_discovery(
    benchmark_module, monkeypatch, tmp_path, stream
):
    module = benchmark_module
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(json.dumps({"prompt": "fixture", "stream": stream}) + "\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--prompts",
            str(corpus),
            "--baseline-transport",
            "native",
            "--candidate-transport",
            "native",
        ],
    )
    for name in (
        "resolve_base_url",
        "wait_backend_ready",
        "http_json",
        "_run_benchmark_for_runtime",
    ):
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("no discovery"))
    reports = []
    monkeypatch.setattr(
        module, "dump_json", lambda path, report: reports.append(report)
    )
    assert module.main() == 1
    assert "baseline_native_model_and_base_url_required" in reports[-1]["errors"]


def test_mixed_pair_keeps_simple_readiness_without_forcing_model_heuristics(
    benchmark_module, monkeypatch, tmp_path
):
    module = benchmark_module
    corpus = tmp_path / "cases.jsonl"
    corpus.write_text(json.dumps({"prompt": "fixture"}) + "\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--prompts",
            str(corpus),
            "--repetitions",
            "2",
            "--warmup",
            "1",
            "--baseline-model",
            "explicit-simple",
            "--candidate-model",
            "explicit-native",
            "--candidate-transport",
            "native",
            "--candidate-native-base-url",
            "http://native.invalid/v1",
        ],
    )
    readiness, calls = [], []
    monkeypatch.setattr(
        module, "resolve_base_url", lambda **kwargs: "http://simple.invalid"
    )
    monkeypatch.setattr(
        module,
        "wait_backend_ready",
        lambda url, **kwargs: readiness.append(url) or True,
    )
    monkeypatch.setattr(
        module, "http_json", lambda *a, **k: pytest.fail("explicit models")
    )

    def measure(**kwargs):
        calls.append(kwargs)
        return complete_benchmark_result()

    monkeypatch.setattr(module, "_run_benchmark_for_runtime", measure)
    monkeypatch.setattr(module, "dump_json", lambda *args: None)
    monkeypatch.setattr(module, "dump_text", lambda *args: None)
    assert module.main() == 0
    assert readiness == ["http://simple.invalid"]
    assert [call["transport"] for call in calls] == ["simple", "native"]
