"""Offline remote-evaluation orchestration, framing and paired-case identity."""

import copy
import json
import selectors
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.granite_operator import remote_comparison as module


@pytest.fixture
def rpc(tmp_path):
    script = "import sys,json;print(json.dumps({'ok':True,'result':{'ready':True}}),flush=True);[(print(json.dumps({'ok':True,'result':json.loads(line)}),flush=True)) for line in sys.stdin]"
    remote = module.RemoteInference.__new__(module.RemoteInference)
    remote.process = subprocess.Popen(
        [sys.executable, "-u", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
        start_new_session=True,
    )
    remote.error_log = (tmp_path / "stderr").open("ab")
    remote.healthy = True
    remote.buffer = b""
    remote.selector = selectors.DefaultSelector()
    remote.selector.register(remote.process.stdout, selectors.EVENT_READ)
    assert remote.receive(5) == {"ready": True}
    yield remote
    remote.close()


def test_rpc_preserves_messages_and_bounded_deadline(rpc):
    messages = [{"role": "user", "content": "untrusted text; never a shell command"}]
    result = rpc.generate(None, messages, [], "adapter", time.monotonic() + 20)
    assert result["op"] == "generate"
    assert result["arm"] == "adapter"
    assert result["messages"] == messages
    assert 0 < result["seconds"] <= 20
    expired = time.monotonic() - 1
    with pytest.raises(TimeoutError):
        rpc.generate(None, [], [], "base", expired)
    with pytest.raises(ValueError, match="too_large"):
        rpc.request("generate", text="x" * module.MAX_LINE)


def test_rpc_rejects_invalid_response_and_lost_peer(rpc):
    rpc.buffer = b'{"ok":false}\n'
    with pytest.raises(RuntimeError, match="operation_failed"):
        rpc.receive(1)
    rpc.process.kill()
    rpc.process.wait()
    with pytest.raises(RuntimeError, match="disconnected"):
        rpc.receive(1)


def args(tmp_path):
    return SimpleNamespace(
        cases=tmp_path / "cases.json",
        output=tmp_path / "out",
        resume=False,
        adapter_sha256="a" * 64,
        host="gpu-test",
        remote_result="/workspace/result",
        max_seconds=60,
    )


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    options = args(tmp_path)
    options.cases.write_text("{}")
    cases = [{"id": str(i), "system": "system", "tools": []} for i in range(4)]
    manifest = {
        "qualification": {"status": "PASS"},
        "sandbox_image": "sha256:" + "b" * 64,
    }
    monkeypatch.setattr(
        module, "load_frozen", lambda _: (manifest, copy.deepcopy(cases))
    )
    monkeypatch.setattr(module, "cleanup_owned", lambda _: True)
    monkeypatch.setattr(module, "summarize", lambda rows: {"trial_count": len(rows)})
    calls = []

    def trial(remote, case, dataset, output, image, run_id, arm, **kwargs):
        calls.append((case["id"], arm))
        assert kwargs["generator"] == remote.generate
        return {"case_id": case["id"], "arm": arm, "oracle": {"success": arm == "base"}}

    monkeypatch.setattr(module, "run_case", trial)
    instances = []

    class Remote:
        def __init__(self, *_):
            instances.append(self)
            self.ready = {"adapter_sha256": "a" * 64}
            self.closed = False

        def generate(self, *_):
            return {"text": "warmup"}

        def close(self):
            self.closed = True

    return options, calls, instances, Remote


def test_paired_evaluation_and_exact_resume(evaluation):
    options, calls, instances, factory = evaluation
    result = module.evaluate(options, factory)
    assert result["trial_count"] == 8
    assert instances[-1].closed
    assert all(
        calls[i][0] == calls[i + 1][0]
        and {calls[i][1], calls[i + 1][1]} == {"base", "adapter"}
        for i in range(0, 8, 2)
    )
    assert calls[0][1] != calls[2][1]
    progress = json.loads((options.output / "progress.json").read_text())
    assert progress["completed"] == 8
    assert progress["status"] == "COMPLETE"
    options.resume = True
    module.evaluate(options, factory)
    assert len(calls) == 8
    options.adapter_sha256 = "c" * 64
    with pytest.raises(ValueError, match="identity_changed"):
        module.evaluate(options, factory)


def test_duplicate_resume_records_rejected(evaluation):
    options, _, _, factory = evaluation
    module.evaluate(options, factory)
    path = options.output / "trials.jsonl"
    text = path.read_text()
    path.write_text(text + text.splitlines()[0] + "\n")
    options.resume = True
    with pytest.raises(ValueError, match="trials_invalid"):
        module.evaluate(options, factory)


def test_remote_cleanup_even_when_trial_fails(evaluation, monkeypatch):
    options, _, instances, factory = evaluation

    def failure(*a, **kw):
        raise RuntimeError("infrastructure_failure")

    monkeypatch.setattr(module, "run_case", failure)
    with pytest.raises(RuntimeError, match="infrastructure_failure"):
        module.evaluate(options, factory)
    assert instances[-1].closed


@pytest.mark.parametrize(
    "code,kind",
    [
        ("comparison_context_limit", ValueError),
        ("comparison_task_deadline", TimeoutError),
    ],
)
def test_expected_generation_limits_are_case_failures(rpc, code, kind):
    rpc.buffer = (json.dumps({"ok": False, "error": code}) + "\n").encode()
    with pytest.raises(kind, match=code):
        rpc.receive(1)


def test_rejected_restart_never_changes_completed_run(evaluation, monkeypatch):
    options, _, _, factory = evaluation
    module.evaluate(options, factory)
    before = {p.name: p.read_bytes() for p in options.output.iterdir() if p.is_file()}
    monkeypatch.setattr(
        module, "parser", lambda: SimpleNamespace(parse_args=lambda _: options)
    )
    assert module.main([]) == 1
    after = {p.name: p.read_bytes() for p in options.output.iterdir() if p.is_file()}
    assert after == before
    options.resume = True
    options.adapter_sha256 = "c" * 64
    assert module.main([]) == 1
    assert (options.output / "status.json").read_bytes() == before["status.json"]


def test_successful_resume_replaces_previous_failure_status(evaluation):
    options, _, _, factory = evaluation
    module.evaluate(options, factory)
    (options.output / "status.json").write_text('{"status":"FAIL"}')
    options.resume = True
    module.evaluate(options, factory)
    assert json.loads((options.output / "status.json").read_text()) == {
        "status": "COMPLETE"
    }


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CalledProcessError(1, "docker"),
        subprocess.TimeoutExpired("docker", 1),
    ],
)
def test_cleanup_subprocess_failures_are_recorded_and_reported(
    evaluation, monkeypatch, capsys, failure
):
    options, _, _, factory = evaluation
    evaluate = module.evaluate
    monkeypatch.setattr(module, "evaluate", lambda args: evaluate(args, factory))
    monkeypatch.setattr(
        module, "parser", lambda: SimpleNamespace(parse_args=lambda _: options)
    )

    def cleanup(_):
        raise failure

    monkeypatch.setattr(module, "cleanup_owned", cleanup)
    assert module.main([]) == 1
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result == {"ok": False, "error": type(failure).__name__}
    assert json.loads((options.output / "status.json").read_text())["status"] == "FAIL"


def test_missing_manifest_fields_are_json_errors_without_owning_output(
    evaluation, monkeypatch, capsys
):
    options, _, _, _ = evaluation
    monkeypatch.setattr(
        module, "load_frozen", lambda _: ({"qualification": {"status": "PASS"}}, [])
    )
    monkeypatch.setattr(
        module, "parser", lambda: SimpleNamespace(parse_args=lambda _: options)
    )
    assert module.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "KeyError"}
    assert not (options.output / "status.json").exists()
