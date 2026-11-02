"""CPU-only contracts for the fixed SSH stdio inference worker."""

import contextlib
import io
import json
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.granite_operator import remote_inference as rpc


def session():
    cuda = SimpleNamespace(
        max_memory_allocated=lambda: 11,
        max_memory_reserved=lambda: 22,
        get_device_name=lambda _: "fixtureGPU",
        reset_peak_memory_stats=Mock(),
    )
    return SimpleNamespace(
        torch=SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="13.0"))
    )


def request(**changes):
    return {
        "op": "generate",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [],
        "arm": "base",
        "seconds": 5,
        **changes,
    }


def records(sink):
    return [json.loads(line) for line in sink.getvalue().splitlines()]


def test_persistent_protocol_both_arms_and_no_stdout_noise(capsys):
    fake = session()
    calls = []

    def generate(current, messages, tools, arm, deadline):
        calls.append((current, messages, tools, arm, deadline))
        print("library diagnostic")
        return {"text": "response", "seconds": 0.01, "tokens": 1, "input_tokens": 2}

    requests = [
        {"op": "ready"},
        request(),
        request(arm="adapter"),
        {"op": "reset_stats"},
        {"op": "stats"},
        {"op": "close"},
    ]
    sink = io.StringIO()
    rpc.serve(
        fake,
        {"model": "fixture"},
        "a" * 64,
        io.StringIO("".join(json.dumps(row) + "\n" for row in requests)),
        sink,
        generator=generate,
    )
    output = records(sink)
    assert all(row["ok"] for row in output)
    assert output[0]["result"]["adapter_sha256"] == "a" * 64
    assert [item[3] for item in calls] == ["base", "adapter"]
    assert output[-2]["result"] == {
        "peak_allocated_bytes": 11,
        "peak_reserved_bytes": 22,
    }
    assert output[-1]["result"]["status"] == "closed"
    fake.torch.cuda.reset_peak_memory_stats.assert_called_once()
    assert "library diagnostic" not in sink.getvalue()
    assert "library diagnostic" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        [],
        {"op": []},
        {"op": "shell", "command": "id"},
        request(arm="other"),
        request(arm=[]),
        request(seconds=float("nan")),
        request(seconds=61),
        request(seconds=True),
        request(messages=[]),
        request(messages=[{"role": "bad"}]),
        request(tools=["bad"]),
        request(command="id"),
    ],
)
def test_untrusted_requests_cannot_select_code_or_model(bad):
    with pytest.raises(ValueError, match="remote_inference_"):
        rpc.validate_request(bad)


@pytest.mark.parametrize("raw", ["not-json\n", '"string"\n', '{"op":"unknown"}\n'])
def test_invalid_record_yields_stable_error(raw):
    sink = io.StringIO()
    rpc.serve(session(), {}, "a" * 64, io.StringIO(raw), sink)
    assert records(sink)[1]["ok"] is False
    assert records(sink)[1]["error"].startswith("remote_inference_")


def test_oversized_or_unterminated_record_closes_session():
    for raw in ["x" * (rpc.MAX_LINE + 1), '{"op":"ready"}']:
        sink = io.StringIO()
        rpc.serve(session(), {}, "a" * 64, io.StringIO(raw), sink)
        assert records(sink)[1]["error"] == "remote_inference_request_too_large"


def test_context_limit_is_case_error_but_cuda_failure_is_fatal():
    def source():
        return io.StringIO(json.dumps(request()) + "\n")

    sink = io.StringIO()

    def context_limit(*args):
        raise ValueError("comparison_context_limit")

    rpc.serve(session(), {}, "a" * 64, source(), sink, generator=context_limit)
    assert records(sink)[1]["error"] == "comparison_context_limit"

    def cuda_failure(*args):
        raise RuntimeError("sensitive internal details")

    sink = io.StringIO()
    with pytest.raises(RuntimeError, match="remote_inference_generation_failed"):
        rpc.serve(session(), {}, "a" * 64, source(), sink, generator=cuda_failure)
    assert "sensitive" not in sink.getvalue()


def test_trusted_result_requires_terminal_matching_attempt(tmp_path, monkeypatch):
    root = tmp_path / "host"
    result = root / "runs/job1/attempts/0002/result"
    result.mkdir(parents=True)
    (result / "status.json").write_text(
        json.dumps({"state": "succeeded", "exit_code": 0})
    )
    weights = result / "adapter_model.safetensors"
    weights.write_bytes(b"fixture")
    state = {"status": "succeeded", "stage": "train", "exit_code": 0, "attempt": 2}
    monkeypatch.setattr(
        rpc,
        "JobStore",
        lambda _: SimpleNamespace(
            status=lambda _: state, attempt_status=lambda *_: state
        ),
    )
    monkeypatch.setattr(rpc, "load_host", lambda _: {"host": "fixture"})
    monkeypatch.setattr(
        rpc, "validate_local", lambda *args: ({"model": "fixture"}, "profile")
    )
    value = rpc.trusted_result(root, result, rpc.file_digest(weights))
    assert value[1] == {"model": "fixture"}
    state["attempt"] = 3
    with pytest.raises(ValueError, match="training_not_succeeded"):
        rpc.trusted_result(root, result, rpc.file_digest(weights))
    state["attempt"] = 2
    with pytest.raises(ValueError, match="adapter_mismatch"):
        rpc.trusted_result(root, result, "a" * 64)
    (result / "status.json").write_text('{"state":"failed","exit_code":1}')
    with pytest.raises(ValueError, match="worker_not_succeeded"):
        rpc.trusted_result(root, result, rpc.file_digest(weights))
    with pytest.raises(ValueError, match="result_path_invalid"):
        rpc.trusted_result(root, root / "runs/job1/input", "a" * 64)


def test_group_termination_waits_before_release(monkeypatch):
    calls = []
    child = SimpleNamespace(
        pid=123,
        poll=lambda: None,
        wait=Mock(side_effect=[subprocess.TimeoutExpired("fixture", 10), 0]),
    )
    monkeypatch.setattr(rpc.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    rpc.terminate(child)
    assert calls == [(123, signal.SIGTERM), (123, signal.SIGKILL)]
    assert child.wait.call_count == 2
    rpc.terminate(SimpleNamespace(poll=lambda: 0))


def test_signal_handlers_unwind_and_restore():
    previous = signal.getsignal(signal.SIGTERM)
    with rpc.termination_signals():
        with pytest.raises(InterruptedError, match="remote_inference_interrupted"):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    assert signal.getsignal(signal.SIGTERM) is previous


def test_cli_failure_never_exposes_exception_details(monkeypatch, capsys):
    monkeypatch.setattr(
        rpc, "coordinate", Mock(side_effect=RuntimeError("private detail"))
    )
    assert (
        rpc.main(
            [
                "--host-root",
                "/tmp/host",
                "--result",
                "/tmp/result",
                "--expected-adapter-sha256",
                "a" * 64,
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "error": "remote_inference_session_failed",
    }


def test_generation_deadline_is_a_recoverable_case_result():
    def expired(*args):
        raise TimeoutError("comparison_task_deadline")

    sink = io.StringIO()
    rpc.serve(
        session(),
        {},
        "a" * 64,
        io.StringIO(json.dumps(request()) + "\n"),
        sink,
        generator=expired,
    )
    assert records(sink)[1] == {"ok": False, "error": "comparison_task_deadline"}


def test_coordinator_leases_fixed_child_and_releases_only_after_exit(
    tmp_path, monkeypatch
):
    from venom_core.services import runtime_admission
    from venom_core.services.granite_operator import cli
    from venom_core.services.remote_training import remote_env, worker

    events = []
    host = {
        "code_root": str(tmp_path),
        "admission_db": str(tmp_path / "admission.db"),
        "worker_python": "/operator/venv/bin/python",
    }
    monkeypatch.setattr(
        rpc, "trusted_result", lambda *a: (host, {"model": "fixture"}, None)
    )
    monkeypatch.setattr(cli, "require_offline", lambda: None)
    monkeypatch.setattr(worker, "require_interpreter", lambda _: None)
    monkeypatch.setattr(remote_env, "runtime_receipt", lambda _: {"ok": True})

    class Lease:
        @contextlib.contextmanager
        def operation(self, **values):
            events.append("operation")
            yield
            assert values["confirm_quiescent"]()
            events.append("quiescent")

        def release(self):
            events.append("release")

    def acquire(**kwargs):
        assert kwargs["owner"] == kwargs["engine"] == "granite-training"
        events.append("acquire")
        return Lease()

    monkeypatch.setattr(
        runtime_admission,
        "RuntimeAdmission",
        lambda *a, **k: SimpleNamespace(acquire=acquire),
    )
    captured = {}

    def wait(**kwargs):
        events.append("wait")
        return 0

    def popen(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(wait=wait, poll=lambda: 0)

    monkeypatch.setattr(rpc.subprocess, "Popen", popen)
    args = SimpleNamespace(
        host_root=tmp_path,
        result=tmp_path / "result",
        expected_adapter_sha256="a" * 64,
        max_seconds=120,
    )
    rpc.coordinate(args)
    assert events == ["acquire", "operation", "wait", "quiescent", "release"]
    assert captured["argv"][:7] == [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        "/operator/venv/bin/python",
        "-m",
        "scripts.granite_operator.remote_inference",
    ]
    assert captured["env"]["VENOM_GRANITE_ADMISSION_DB"] == host["admission_db"]
    assert captured["env"]["HF_HUB_OFFLINE"] == "1"
    assert captured["pass_fds"]
    assert captured["start_new_session"] is True


def test_worker_loads_only_operator_selected_safetensors_and_freezes_model(
    tmp_path, monkeypatch, capsys
):
    from venom_core.services.granite_operator import engine

    fake = session()
    fake.model = Mock()
    fake.torch.set_num_threads = Mock()
    monkeypatch.setattr(engine, "require_owner", lambda: None)
    created = []
    monkeypatch.setattr(engine, "Session", lambda *args: created.append(args) or fake)
    result = tmp_path / "result"
    result.mkdir()
    weights = result / "adapter_model.safetensors"
    weights.write_bytes(b"fixture")
    expected = rpc.file_digest(weights)
    monkeypatch.setattr(
        rpc,
        "trusted_result",
        lambda *args: ({"snapshot": "/models/base"}, {"model": "fixture"}, "profile"),
    )
    monkeypatch.setattr(rpc.sys, "stdin", io.StringIO('{"op":"close"}\n'))
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "host_root": str(tmp_path),
                "result": str(result),
                "expected_hash": expected,
            }
        )
    )
    rpc.worker(request_path)
    assert created == [("profile", Path("/models/base"), result)]
    fake.model.eval.assert_called_once()
    fake.model.requires_grad_.assert_called_once_with(False)
    fake.model.gradient_checkpointing_disable.assert_called_once()
    assert all(json.loads(line)["ok"] for line in capsys.readouterr().out.splitlines())
