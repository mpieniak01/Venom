"""Offline task batching, adapter ownership, queue budgets and durable host results."""

import argparse
import concurrent.futures
import contextlib
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.granite_operator import comparison
from scripts.granite_operator import comparison_host as host
from scripts.granite_operator import comparison_parallel as parallel
from scripts.granite_operator.comparison_support import generation_time


@pytest.mark.parametrize(
    "changes",
    [
        {"concurrency": 3},
        {"concurrency": True},
        {"batch_size": 0},
        {"batch_size": 2},
        {"batch_wait_ms": -1},
        {"batch_wait_ms": 101},
        {"task_seconds": 0},
        {"task_seconds": 601},
        {"max_seconds": 0},
        {"max_seconds": 14401},
        {"host": "hybrid"},
    ],
)
def test_execution_rejects_unsupported_or_unbounded_settings(changes):
    with pytest.raises(ValueError, match="execution_invalid"):
        parallel.Execution(**changes).validate()


def test_cli_settings_are_explicit_and_batch_size_defaults_to_task_limit():
    parser = argparse.ArgumentParser()
    parallel.execution_options(parser)
    args = parser.parse_args(["--concurrency", "4", "--execution-host", "remote"])
    value = parallel.execution_from_args(args)
    assert value.batch_size == 4 and value.host == "remote"
    args.batch_size = 2
    assert parallel.execution_from_args(args).batch_size == 2
    assert parallel.execution_from_args(parser.parse_args([])).concurrency == 1


def result(text="ok"):
    return {"text": text, "seconds": 0.01, "tokens": 1, "input_tokens": 2}


@pytest.mark.parametrize("width,size", [(1, 1), (2, 2), (4, 4), (4, 1)])
def test_tasks_overlap_but_all_model_calls_stay_on_one_owner(width, size):
    owner = threading.get_ident()
    calls = []

    def batcher(session, requests):
        assert threading.get_ident() == owner
        assert len(requests) <= size and len({r[2] for r in requests}) == 1
        calls.append(len(requests))
        return [result() for _ in requests]

    scheduler = parallel.TaskScheduler(
        None, parallel.Execution(width, size), batcher=batcher
    )
    completed = []

    def trial(job, runner):
        assert threading.get_ident() != owner
        assert runner.trial_session.torch.cuda.max_memory_allocated() is None
        runner.trial_session.torch.cuda.reset_peak_memory_stats()
        assert runner.trial_session.torch.cuda.max_memory_reserved() is None
        value = runner.generate(
            None, [{"role": "user", "content": job}], [], job, time.monotonic() + 5
        )
        assert value["queue_seconds"] >= 0
        return job

    scheduler.run(["base", "adapter", "base", "adapter"], trial, completed.append)
    assert sorted(completed) == ["adapter", "adapter", "base", "base"]
    assert scheduler.stats["batch_items"] == 4
    assert scheduler.stats["batches"] == len(calls)
    assert not scheduler.waiters
    with pytest.raises(RuntimeError, match="scheduler_closed"):
        scheduler.generate(None, [], [], "base", time.monotonic() + 5)


@pytest.mark.parametrize(
    "code", ["comparison_context_limit", "comparison_task_deadline"]
)
def test_expected_limits_fail_only_the_affected_case(code):
    def batcher(session, requests):
        if any(r[0][0]["content"] == "bad" for r in requests):
            raise ValueError(code) if code.endswith("limit") else TimeoutError(code)
        return [result() for _ in requests]

    scheduler = parallel.TaskScheduler(None, parallel.Execution(2, 2), batcher=batcher)
    observed = []

    def trial(job, runner):
        try:
            runner.generate(None, [{"content": job}], [], "base", time.monotonic() + 5)
            return "ok"
        except (ValueError, TimeoutError) as error:
            return str(error)

    scheduler.run(["bad", "good"], trial, observed.append)
    assert sorted(observed) == sorted([code, "ok"])


@pytest.mark.parametrize("failure", ["cuda", "length", "persist"])
def test_fatal_error_unblocks_waiting_tasks_and_propagates(failure):
    def batcher(session, requests):
        if failure == "cuda":
            raise RuntimeError("cuda_failed")
        if failure == "length":
            return []
        return [result() for _ in requests]

    scheduler = parallel.TaskScheduler(None, parallel.Execution(2, 2), batcher=batcher)

    def trial(job, runner):
        return runner.generate(None, [], [], "base", time.monotonic() + 5)

    def persist(row):
        raise OSError("disk_failed")

    with pytest.raises((RuntimeError, OSError)):
        scheduler.run([1, 2, 3], trial, persist)
    assert not scheduler.waiters


def test_session_deadline_cancels_queued_work(monkeypatch):
    scheduler = parallel.TaskScheduler(None, parallel.Execution(max_seconds=1))

    # The task remains alive while the coordinator's global wall budget expires.
    def trial(job, runner):
        while runner.error is None:
            time.sleep(0.005)
        raise RuntimeError("cancelled")

    with pytest.raises(TimeoutError, match="session_deadline"):
        scheduler.run([1], trial, lambda row: None)


class Array:
    def __init__(self, values):
        self.values = values
        self.shape = (len(values), max(map(len, values)))

    def __getitem__(self, key):
        return SimpleNamespace(tolist=lambda: self.values[key[0]][key[1]])


class Encoding(dict):
    def to(self, device):
        assert device == "cuda"
        return self


@pytest.fixture
def model():
    tokenizer = SimpleNamespace(padding_side="right", pad_token_id=0, eos_token_id=9)
    tokenizer.apply_chat_template = lambda messages, **kw: messages

    def pad(data, **kw):
        assert tokenizer.padding_side == "left"
        return Encoding(input_ids=Array(data["input_ids"]))

    tokenizer.pad = pad
    tokenizer.decode = lambda tokens, **kw: str(tokens)
    torch = SimpleNamespace(
        cuda=SimpleNamespace(synchronize=Mock()), inference_mode=contextlib.nullcontext
    )
    model = SimpleNamespace(disable_adapter=Mock(side_effect=contextlib.nullcontext))
    model.generate = lambda **kw: Array([[1, 2, 3, 7, 9, 0], [1, 2, 3, 8, 9, 0]])
    return SimpleNamespace(tokenizer=tokenizer, torch=torch, model=model)


@pytest.mark.parametrize("arm", ["base", "adapter"])
def test_batch_generation_pads_left_trims_eos_and_uses_one_adapter(model, arm):
    requests = [
        ([1, 2, 3], [], arm, time.monotonic() + 5),
        ([4], [], arm, time.monotonic() + 5),
    ]
    rows = parallel.generate_batch(model, requests)
    assert rows[0]["text"] == "[7, 9]" and rows[1]["input_tokens"] == 1
    assert rows[0]["batch_id"] == rows[1]["batch_id"] and rows[0]["batch_size"] == 2
    assert model.tokenizer.padding_side == "right"
    assert model.model.disable_adapter.call_count == (1 if arm == "base" else 0)


@pytest.mark.parametrize("kind", ["mixed", "context", "deadline", "padding"])
def test_batch_limits_and_padding_restore(model, kind):
    req = [([1, 2, 3], [], "base", time.monotonic() + 5)]
    if kind == "mixed":
        req.append(([1], [], "adapter", time.monotonic() + 5))
    if kind == "context":
        req[0] = ([1] * 2048, [], "base", time.monotonic() + 5)
    if kind == "deadline":
        req[0] = ([1], [], "base", time.monotonic() - 1)
    if kind == "padding":
        model.tokenizer.pad = Mock(side_effect=ValueError("pad_failed"))
    with pytest.raises((ValueError, TimeoutError)):
        parallel.generate_batch(model, req)
    assert model.tokenizer.padding_side == "right"


def test_shared_batch_times_are_counted_once_in_throughput():
    a = {"generation_seconds": 3, "generations": [{"batch_id": "same", "seconds": 3}]}
    assert generation_time([a, a]) == 3
    assert generation_time([{"generation_seconds": 2}, a, a]) == 5
    assert generation_time([{"generation_seconds": 4, "generations": [{}]}]) == 4


@pytest.fixture
def host_trial(tmp_path, monkeypatch):
    manifest = {
        "sandbox_image": "sha256:" + "a" * 64,
        "qualification": {"status": "PASS"},
    }
    cases = [{"id": "first", "system": "s", "tools": []}]
    request = {
        "execution": parallel.Execution(2, 2).validate(),
        "cases": str(tmp_path / "cases"),
        "output": str(tmp_path),
        "run_id": "a" * 32,
    }
    cuda = SimpleNamespace(
        reset_peak_memory_stats=Mock(),
        max_memory_allocated=lambda: 12,
        max_memory_reserved=lambda: 14,
    )
    session = SimpleNamespace(torch=SimpleNamespace(cuda=cuda))

    def run_case(_session, case, *args, **kw):
        assert kw["task_timeout_seconds"] == 60
        kw["generator"](None, [], [], "base", time.monotonic() + 5)
        return {"case_id": case["id"], "arm": args[-1], "oracle": {"success": True}}

    monkeypatch.setattr(comparison, "run_case", run_case)

    def factory(session, execution):
        return parallel.TaskScheduler(
            session, execution, batcher=lambda s, rs: [result() for _ in rs]
        )

    return tmp_path, manifest, cases, request, session, factory


def test_host_trials_persist_exactly_once_and_resume(host_trial):
    output, manifest, cases, request, session, factory = host_trial
    rows, metrics = host.evaluate_trials(
        session, cases, manifest, request, output, scheduler_factory=factory
    )
    assert len(rows) == 2 and {r["trial_sequence"] for r in rows} == {1, 2}
    assert metrics["peak_allocated_bytes"] == 12 and metrics["resumed_trials"] == 0
    original = (output / "trials.jsonl").read_text()
    rows, metrics = host.evaluate_trials(
        session, cases, manifest, request, output, rows=rows, scheduler_factory=factory
    )
    assert (
        metrics["resumed_trials"] == 2
        and (output / "trials.jsonl").read_text() == original
    )
    with pytest.raises(ValueError, match="resume_trials_invalid"):
        host.evaluate_trials(
            session,
            cases,
            manifest,
            request,
            output,
            rows=rows + rows,
            scheduler_factory=factory,
        )


def test_host_refuses_missing_trials_from_broken_scheduler(host_trial):
    output, manifest, cases, request, session, _ = host_trial

    class Broken:
        def __init__(self, *args):
            pass

        def run(self, *args):
            pass

    with pytest.raises(RuntimeError, match="incomplete"):
        host.evaluate_trials(
            session, cases, manifest, request, output, scheduler_factory=Broken
        )


@pytest.fixture
def source(tmp_path, monkeypatch):
    from venom_core.services.granite_operator.contract import (
        TrainingProfile,
        file_digest,
    )

    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "status.json").write_text(
        json.dumps({"state": "succeeded", "exit_code": 0})
    )
    config = {
        "snapshot": str(tmp_path / "snapshot"),
        "host_id": "host-fixture",
        "worker_python": "/qualified/python",
        "admission_db": str(tmp_path / "db"),
    }
    monkeypatch.setattr(host, "load_host", lambda _: config)
    monkeypatch.setattr(
        host, "validate_local", lambda *_: ({"model": "fixture"}, TrainingProfile())
    )
    request = {
        "adapter_root": str(adapter),
        "host_root": str(tmp_path / "host"),
        "expected_adapter_sha256": file_digest(adapter / "adapter_model.safetensors"),
    }
    return request, config


@pytest.mark.parametrize("kind", ["ok", "hash", "status"])
def test_imported_adapter_is_bound_to_successful_training_and_exact_weights(
    source, kind
):
    request, config = source
    from pathlib import Path

    if kind == "hash":
        request["expected_adapter_sha256"] = "0" * 64
    if kind == "status":
        (Path(request["adapter_root"]) / "status.json").write_text("{}")
    if kind == "ok":
        assert host.adapter_source(request)[0] == config
    else:
        with pytest.raises(ValueError, match="adapter_changed|training_not_succeeded"):
            host.adapter_source(request)


@pytest.fixture
def full_host(source, tmp_path, monkeypatch):
    from venom_core.services.granite_operator import engine

    request, config = source
    output = tmp_path / "output"
    output.mkdir()
    cases = tmp_path / "manifest.json"
    cases.write_text("{}")
    request.update(
        output=str(output),
        cases=str(cases),
        run_id="a" * 32,
        execution=parallel.Execution().validate(),
    )
    manifest = {
        "sandbox_image": "sha256:" + "a" * 64,
        "qualification": {"status": "PASS"},
    }
    case = [{"id": "one", "system": "s", "tools": []}]
    monkeypatch.setattr(host, "load_frozen", lambda _: (manifest, case))
    monkeypatch.setattr(host.importlib.metadata, "version", lambda _: "fixture-1")
    monkeypatch.setattr(host.subprocess, "run", Mock())
    monkeypatch.setattr(engine, "require_owner", Mock())
    fake = SimpleNamespace(
        model=SimpleNamespace(
            eval=Mock(), requires_grad_=Mock(), gradient_checkpointing_disable=Mock()
        ),
        torch=SimpleNamespace(set_num_threads=Mock()),
    )
    constructor = Mock(return_value=fake)
    monkeypatch.setattr(engine, "Session", constructor)
    warmup = Mock()
    monkeypatch.setattr(comparison, "generate", warmup)
    monkeypatch.setattr(
        host,
        "evaluate_trials",
        lambda *args, **kwargs: ([{"case_id": "one", "arm": "base"}], {"batches": 1}),
    )
    monkeypatch.setattr(
        host,
        "summarize",
        lambda rows: {"paired": {"proposed_promotion_gate_passed": True}},
    )
    return request, output, constructor, warmup, manifest, case


def test_one_host_worker_records_execution_identity_and_never_promotes(full_host):
    request, output, constructor, warmup, _, _ = full_host
    host.worker(request)
    assert constructor.call_count == 1 and warmup.call_count == 4
    identity = json.loads((output / "identity.json").read_text())
    assert identity["placement"] == "model_tools_and_oracle_on_one_host"
    assert (
        identity["execution"]["concurrency"] == 1
        and identity["versions"]["torch"] == "fixture-1"
    )
    summary = json.loads((output / "summary.json").read_text())
    assert (
        summary["status"] == "COMPLETE"
        and not summary["paired"]["proposed_promotion_gate_passed"]
    )
    # Identical settings permit resume, changing them never mixes old trial results.
    host.worker(request)
    request["execution"] = parallel.Execution(2, 2).validate()
    with pytest.raises(ValueError, match="identity_changed"):
        host.worker(request)


@pytest.mark.parametrize("kind", ["context", "qualification", "empty", "docker"])
def test_host_preflight_fails_before_loading_gpu(full_host, monkeypatch, kind):
    from venom_core.services.granite_operator.contract import TrainingProfile

    request, output, constructor, _, manifest, cases = full_host
    if kind == "context":
        monkeypatch.setattr(
            host,
            "validate_local",
            lambda *_: ({"model": "fixture"}, TrainingProfile(context=4096)),
        )
    if kind == "qualification":
        manifest["qualification"]["status"] = "FAIL"
    if kind == "empty":
        cases.clear()
    if kind == "docker":
        monkeypatch.setattr(
            host.subprocess,
            "run",
            Mock(side_effect=RuntimeError("sandbox_unavailable")),
        )
    with pytest.raises((ValueError, RuntimeError)):
        host.worker(request)
    constructor.assert_not_called()
    assert not (output / "summary.json").exists()


@pytest.mark.parametrize("outcome", ["success", "exit", "timeout", "start", "cleanup"])
def test_coordinator_keeps_reservation_until_worker_and_containers_are_quiet(
    source, tmp_path, monkeypatch, outcome
):
    import subprocess
    from pathlib import Path

    from scripts.granite_operator import remote_inference
    from venom_core.services import runtime_admission
    from venom_core.services.granite_operator import cli

    request, config = source
    options = SimpleNamespace(
        cases=tmp_path / "manifest",
        output=tmp_path / "results",
        resume=False,
        adapter_root=Path(request["adapter_root"]),
        host_root=tmp_path / "host",
        expected_adapter_sha256=request["expected_adapter_sha256"],
        worker_python=None,
        admission_db=None,
        concurrency=2,
        batch_size=None,
        batch_wait_ms=20,
        task_seconds=60,
        max_seconds=120,
        execution_host="local",
    )
    options.host_root.mkdir()
    monkeypatch.setattr(cli, "require_offline", Mock())
    monkeypatch.setattr(comparison, "load_frozen", lambda _: ({}, []))
    lease = SimpleNamespace(
        release=Mock(), operation=lambda **kwargs: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        runtime_admission,
        "RuntimeAdmission",
        lambda *a, **kw: SimpleNamespace(acquire=lambda **kw: lease),
    )
    child = SimpleNamespace(
        wait=Mock(return_value=0 if outcome != "exit" else 1), poll=lambda: 0
    )
    if outcome == "timeout":
        child.wait.side_effect = subprocess.TimeoutExpired("worker", 120)
    monkeypatch.setattr(
        comparison.subprocess,
        "Popen",
        Mock(
            return_value=child,
            side_effect=OSError("spawn") if outcome == "start" else None,
        ),
    )
    terminate = Mock()
    monkeypatch.setattr(remote_inference, "terminate", terminate)
    monkeypatch.setattr(comparison, "cleanup_owned", lambda _: outcome != "cleanup")
    if outcome in ("exit", "timeout", "start", "cleanup"):
        with pytest.raises((RuntimeError, subprocess.TimeoutExpired, OSError)):
            comparison.coordinate(options)
    else:
        comparison.coordinate(options)
    assert lease.release.call_count == (0 if outcome == "cleanup" else 1)
    assert terminate.call_count == (1 if outcome == "timeout" else 0)
    status = json.loads((options.output / "status.json").read_text())
    assert status["status"] == (
        "FAIL" if outcome in ("exit", "timeout", "start", "cleanup") else "PASS"
    )


def test_imported_cli_requires_one_source_and_passes_execution_options(
    monkeypatch, tmp_path
):
    import sys

    base = [
        "comparison",
        "--cases",
        str(tmp_path / "cases"),
        "--output",
        str(tmp_path / "out"),
        "--adapter-root",
        str(tmp_path / "adapter"),
        "--host-root",
        str(tmp_path / "host"),
        "--expected-adapter-sha256",
        "a" * 64,
        "--concurrency",
        "4",
        "--execution-host",
        "remote",
    ]
    received = []
    monkeypatch.setattr(comparison, "coordinate", received.append)
    monkeypatch.setattr(sys, "argv", base)
    comparison.main()
    assert received[0].concurrency == 4 and received[0].execution_host == "remote"
    monkeypatch.setattr(
        sys, "argv", base + ["--training-run", str(tmp_path / "legacy")]
    )
    with pytest.raises(SystemExit):
        comparison.main()


def test_imported_worker_dispatches_to_same_host_implementation(monkeypatch):
    from venom_core.services.granite_operator import engine

    monkeypatch.setattr(engine, "require_owner", lambda: None)
    called = []
    monkeypatch.setattr(host, "worker", called.append)
    request = {"adapter_root": "operator-provided"}
    comparison.worker(request)
    assert called[0]["execution"]["concurrency"] == 1


def test_short_budget_fails_only_that_request_and_preserves_queue_timing():
    runner = parallel.TaskScheduler(
        None, parallel.Execution(2, 2), batcher=lambda s, r: [result() for _ in r]
    )
    runner.deadline = time.monotonic() + 10
    short = concurrent.futures.Future()
    long = concurrent.futures.Future()
    now = time.monotonic()
    runner._dispatch(
        [([], [], "base", now - 1, short, now), ([], [], "base", now + 5, long, now)]
    )
    with pytest.raises(TimeoutError) as caught:
        short.result()
    assert caught.value.queue_seconds >= 0 and long.result()["text"] == "ok"


@pytest.mark.parametrize("configured", [8, [8, 9]])
def test_batch_uses_model_generation_stop_tokens(model, configured):
    model.model.generation_config = SimpleNamespace(eos_token_id=configured)
    rows = parallel.generate_batch(
        model, [([1, 2, 3], [], "adapter", time.monotonic() + 5)] * 2
    )
    assert rows[1]["text"] == "[8]"


@pytest.mark.parametrize(
    "args,width,enabled,cap",
    [
        (["--execution-host", "remote"], 4, True, 8),
        ([], 1, False, 2),
        (
            ["--execution-host", "remote", "--no-adaptive", "--concurrency", "2"],
            2,
            False,
            8,
        ),
        (["--execution-host", "remote", "--max-concurrency", "4"], 4, True, 4),
    ],
)
def test_remote_policy_starts_aggressively_without_probe(args, width, enabled, cap):
    parser = argparse.ArgumentParser()
    parallel.execution_options(parser)
    value = parallel.execution_from_args(parser.parse_args(args))
    assert (value.concurrency, value.adaptive, value.max_concurrency) == (
        width,
        enabled,
        cap,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"max_concurrency": 3},
        {"adaptive": 1},
        {"low_gpu_percent": 0},
        {"high_memory_percent": 101},
        {"window_trials": 7},
        {"concurrency": 4, "adaptive": True, "max_concurrency": 2},
    ],
)
def test_invalid_adaptation_cannot_bypass_bounds(change):
    with pytest.raises(ValueError):
        parallel.Execution(**change).validate()


@pytest.mark.parametrize(
    "mode",
    [
        "low",
        "high",
        "memory",
        "missing",
        "oom",
        "timeout",
        "fatal",
        "minimum",
        "incomplete",
        "deadline",
    ],
)
def test_adaptive_policy_uses_evidence_preserves_rows_and_never_oscillates(
    monkeypatch, mode
):
    import itertools

    from scripts.granite_operator import comparison_adaptive as adaptive

    clock = itertools.count(0, 2)
    monkeypatch.setattr(
        adaptive, "time", SimpleNamespace(monotonic=lambda: next(clock))
    )

    class OOM(RuntimeError):
        pass

    empty = Mock()
    session = SimpleNamespace(
        torch=SimpleNamespace(
            OutOfMemoryError=OOM, cuda=SimpleNamespace(empty_cache=empty)
        )
    )
    widths = []
    done = []
    events = []
    failed = False

    class Runner:
        def __init__(self, session, settings):
            self.execution = settings
            widths.append(settings.concurrency)
            self.batcher = lambda *args: []
            self.stats = {
                k: 0
                for k in [
                    "gpu_batch_seconds",
                    "batch_call_seconds",
                    "batches",
                    "batch_items",
                ]
            }

        def run(self, jobs, trial, persist):
            nonlocal failed
            if mode == "fatal":
                raise ValueError("bad_dataset")
            if mode == "incomplete":
                return
            for number, job in jobs:
                self.batcher(session, [])
                persist(
                    (
                        number,
                        {
                            "id": job,
                            "failure": "task_timeout" if mode == "timeout" else None,
                        },
                    )
                )
                if mode in ("oom", "minimum") and not failed:
                    failed = True
                    raise OOM()

    settings = parallel.Execution(
        concurrency=1 if mode == "minimum" else 4,
        batch_size=1,
        adaptive=True,
        host="remote",
        window_trials=8,
        max_seconds=1 if mode == "deadline" else 7200,
    )

    def sample():
        if mode == "missing":
            return None
        return {
            "gpu_percent": 90 if mode == "high" else 20,
            "memory_percent": 95 if mode == "memory" else 30,
        }

    runner = adaptive.AdaptiveScheduler(
        session, settings, factory=Runner, sample=sample, changed=events.append
    )
    if mode in ("fatal", "minimum", "incomplete", "deadline"):
        with pytest.raises((RuntimeError, ValueError, TimeoutError)):
            runner.run(list(range(32)), None, done.append)
    else:
        runner.run(list(range(32)), None, done.append)
        assert sorted(r["id"] for r in done) == list(range(32))
        if mode == "low":
            assert widths[0] == 4 and 8 in widths
        elif mode in ("high", "memory", "missing"):
            assert set(widths) == {4}
        else:
            assert widths[0] == 4 and 2 in widths and max(widths[1:]) <= 2
    assert events[0]["reason"] == "initial"
    assert empty.call_count == (1 if mode == "oom" else 0)


@pytest.mark.parametrize(
    "payload", ["20, 100, 1000", "101, 2, 3", "20, 4, 3", "20, 0, 0", "invalid"]
)
def test_gpu_headroom_sampling_is_bounded_and_invalid_samples_are_ignored(
    monkeypatch, payload
):
    from scripts.granite_operator import comparison_adaptive as adaptive

    monkeypatch.setattr(
        adaptive.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=payload)
    )
    result = adaptive.gpu_sample()
    assert (result is not None) == (payload == "20, 100, 1000")
    monkeypatch.setattr(
        adaptive.subprocess, "run", Mock(side_effect=OSError("unavailable"))
    )
    assert adaptive.gpu_sample() is None


def test_host_records_actual_width_and_adaptive_decisions(host_trial, monkeypatch):
    from scripts.granite_operator import comparison_adaptive as adaptive

    output, manifest, cases, request, session, factory = host_trial
    request["execution"] = parallel.Execution(2, 2, adaptive=True).validate()
    real = adaptive.AdaptiveScheduler
    monkeypatch.setattr(
        adaptive,
        "AdaptiveScheduler",
        lambda *a, **kw: real(*a, **kw, sample=lambda: None),
    )
    rows, metrics = host.evaluate_trials(
        session, cases, manifest, request, output, scheduler_factory=factory
    )
    assert len(rows) == 2 and all(r["execution_concurrency"] == 2 for r in rows)
    assert json.loads((output / "concurrency-decisions.jsonl").read_text())["to"] == 2
    assert metrics["decisions"][0]["reason"] == "initial"
