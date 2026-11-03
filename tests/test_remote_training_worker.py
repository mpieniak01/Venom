"""Remote coordinator contracts use fake stages, never GPU or paid endpoints."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services.granite_operator.contract import TrainingProfile, write_json
from venom_core.services.remote_training import host, worker


def identity():
    return {
        "model": "ibm-granite/granite-4.2-3b",
        "revision": "4e9c275e232f10211ec88644d106a1f6a1b60e06",
        **{
            key: "a" * 64
            for key in (
                "tokenizer_sha256",
                "template_sha256",
                "profile_sha256",
                "data_sha256",
                "code_sha256",
                "dependencies_sha256",
                "encoding_sha256",
            )
        },
        "dataset": "domain",
        "limits": {"max_updates": 24, "max_seconds": 100},
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "host"
    run = root / "runs/job01"
    run.mkdir(parents=True)
    source = run / "input"
    source.mkdir()
    manifest = {"run_id": "job01", "identity": identity()}
    write_json(source / ".bundle-manifest.json", manifest)
    host_data = {
        "schema_version": 1,
        "host_id": "testhost",
        "worker_python": sys.executable,
        "snapshot": str(tmp_path / "snapshot"),
        "admission_db": str(root / "admission.db"),
        "code_root": str(tmp_path),
    }
    write_json(root / "host.json", host_data)
    monkeypatch.setattr(worker, "require_offline", lambda: None)
    from venom_core.services.remote_training import remote_env

    monkeypatch.setattr(remote_env, "runtime_receipt", lambda root: {"ok": True})
    monkeypatch.setattr(worker, "require_interpreter", lambda host: None)
    monkeypatch.setattr(
        worker, "preflight", lambda *args: (TrainingProfile(), {"datasets": {}})
    )
    monkeypatch.setattr(worker, "binding", lambda *args: "stable-host-binding")
    from venom_core.services.remote_training import bundles

    monkeypatch.setattr(bundles, "verify_directory", lambda *args: None)

    class Lease:
        def operation(self, **kwargs):
            from contextlib import nullcontext

            return nullcontext()

        def release(self):
            pass

    import venom_core.services.runtime_admission as admission

    monkeypatch.setattr(
        admission,
        "RuntimeAdmission",
        lambda *args, **kwargs: SimpleNamespace(acquire=lambda **kwargs: Lease()),
    )
    calls = []

    def stage(host, request, result, **kwargs):
        calls.append(request)
        output = Path(request["output"])
        (output / "checkpoint").mkdir(parents=True)
        start = 16 if request["stage"] == "smoke-resume" else 0
        if request.get("checkpoint"):
            start = json.loads(
                (Path(request["checkpoint"]) / "receipt.json").read_text()
            )["step"]
        count = start + request["updates"]
        for name, value in [
            ("identity.json", {"native": "actual-fake-native"}),
            ("checkpoint/receipt.json", {"step": count, "fingerprint": "native"}),
            (
                "checkpoint/adapter_config.json",
                {"base_model_name_or_path": "ibm-granite/granite-4.2-3b"},
            ),
        ]:
            write_json(output / name, value)
        (output / "checkpoint/adapter_model.safetensors").write_bytes(b"fake-adapter")
        checks = {
            name: True
            for name in (
                "mask",
                "updated_adapter",
                "frozen_base",
                "reload",
                "resume",
                "long_context",
                "tool_loop",
                "adapter_effect",
            )
        }
        metrics = {"checks": checks, "fingerprint": "native", "step": count}
        write_json(output / "metrics.json", metrics)
        return metrics

    monkeypatch.setattr(worker, "run_stage", stage)

    def request(stage="smoke", checkpoint=None):
        attempts = run / "attempts"
        attempts.mkdir(exist_ok=True)
        attempt = attempts / f"{len(list(attempts.iterdir())) + 1:04d}"
        attempt.mkdir()
        return {
            "host_root": str(root),
            "run_root": str(run),
            "attempt_root": str(attempt),
            "manifest": manifest,
            "run_id": "job01",
            "stage": stage,
            "checkpoint": checkpoint,
            "timeout_seconds": 100,
        }

    return root, run, request, calls


def test_smoke_then_train_preserves_native_contract(setup):
    root, run, request, calls = setup
    smoke = request()
    worker.execute(smoke)
    assert [row["updates"] for row in calls] == [16, 4]
    assert (
        json.loads((run / "qualification-proof.json").read_text())["binding"]
        == "stable-host-binding"
    )
    train = request("train")
    worker.execute(train)
    result = Path(train["attempt_root"]) / "result"
    assert (result / "adapter_model.safetensors").read_bytes() == b"fake-adapter"
    assert json.loads((result / "status.json").read_text())["state"] == "succeeded"
    assert calls[-1]["qualification"].endswith("qualification.json")
    assert (
        json.loads((result / "environment.json").read_text())["native"]
        == "actual-fake-native"
    )
    assert (
        json.loads((result / "metrics.json").read_text())["cost"]["status"]
        == "not_measured"
    )


def test_no_native_smoke_no_full_training(setup):
    root, run, request, calls = setup
    req = request("train")
    with pytest.raises(FileNotFoundError):
        worker.execute(req)
    assert calls == []
    assert (
        json.loads((Path(req["attempt_root"]) / "result/status.json").read_text())[
            "state"
        ]
        == "failed"
    )


def test_qualification_does_not_transfer_to_changed_host(setup, monkeypatch):
    root, run, request, calls = setup
    worker.execute(request())
    monkeypatch.setattr(worker, "binding", lambda *args: "another-host")
    with pytest.raises(ValueError, match="new_host_qualification"):
        worker.execute(request("train"))
    assert len(calls) == 2


def test_resume_uses_remaining_updates_and_never_resets_weights(setup):
    root, run, request, calls = setup
    worker.execute(request())
    checkpoint = "attempts/0001/result/stages/smoke-resume/checkpoint"
    worker.execute(request("train", checkpoint))
    assert calls[-1]["stage"] == "train-resume"
    assert calls[-1]["updates"] == 4
    assert calls[-1]["checkpoint"].endswith(checkpoint)


def test_changed_qualification_artifact_blocks_training(setup):
    root, run, request, calls = setup
    worker.execute(request())
    file = run / "attempts/0001/result/stages/smoke-first/metrics.json"
    file.write_text("{}")
    with pytest.raises(ValueError, match="qualification_changed"):
        worker.execute(request("train"))


def test_tokenizer_missing_and_explicit_host_init(tmp_path):
    with pytest.raises(ValueError, match="tokenizer_missing"):
        host.tokenizer_identity(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "tokenizer_config.json").write_text('{"chat_template":"native"}')
    tokenizer, template = host.tokenizer_identity(snapshot)
    assert len(tokenizer) == 64
    assert len(template) == 64
    code = tmp_path / "code"
    (code / "venom_core").mkdir(parents=True)
    result = host.initialize(
        tmp_path / "host",
        worker_python=Path(sys.executable),
        snapshot=snapshot,
        admission_db=tmp_path / "ledger.db",
        code_root=code,
    )
    assert result["gpu_qualified"] is False
    with pytest.raises(ValueError, match="already_initialized"):
        host.initialize(
            tmp_path / "host",
            worker_python=Path(sys.executable),
            snapshot=snapshot,
            admission_db=tmp_path / "ledger.db",
            code_root=code,
        )


def test_cli_help_and_network_boundary(monkeypatch, capsys):
    from venom_core.services.remote_training import cli

    with pytest.raises(SystemExit) as code:
        cli.main(["--help"])
    assert code.value.code == 0
    assert cli.main(["status", "--run-id", "a"]) == 1
    assert "remote_training_operation_failed" in capsys.readouterr().out


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize(
    "model,expected_worker",
    [
        ("ibm-granite/granite-4.2-3b", "granite_operator.worker"),
        ("google/gemma-4-12B-it", "gemma4_operator.training_worker"),
        ("google/gemma-4-E4B-it", "gemma4_operator.training_worker"),
    ],
)
def test_stage_subprocess_is_fixed_and_retains_host_lock(
    tmp_path, monkeypatch, exit_code, model, expected_worker
):
    import os

    from venom_core.services.remote_training import worker

    result = tmp_path / "result"
    (result / "logs").mkdir(parents=True)
    stage = result / "stage"
    stage.mkdir()
    write_json(stage / "metrics.json", {"loss": 0.4})
    descriptor = os.open(tmp_path / "lock", os.O_CREAT | os.O_RDWR, 0o600)
    monkeypatch.setenv("REMOTE_TRAINING_GPU_LOCK_FD", str(descriptor))
    captured = {}
    child = SimpleNamespace(wait=lambda **kwargs: exit_code, poll=lambda: exit_code)

    def popen(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return child

    monkeypatch.setattr(worker.subprocess, "Popen", popen)
    try:
        host_config = {
            "worker_python": sys.executable,
            "admission_db": str(tmp_path / "ledger"),
            "code_root": str(tmp_path),
        }
        request = {
            "stage": "smoke-first",
            "output": str(stage),
            "profile": {"model": model},
        }
        if exit_code:
            with pytest.raises(RuntimeError, match="stage_failed"):
                worker.run_stage(
                    host_config, request, result, run_id="a", timeout=3, children=[]
                )
        else:
            assert worker.run_stage(
                host_config, request, result, run_id="a", timeout=3, children=[]
            ) == {"loss": 0.4}
        assert captured["pass_fds"] == (descriptor,)
        assert captured["argv"][0:3] == ["setpriv", "--pdeathsig", "TERM"]
        assert "venom_core.services." + expected_worker in captured["argv"]
        assert captured["env"]["HF_HUB_OFFLINE"] == "1"
    finally:
        os.close(descriptor)


def test_native_preflight_and_explicit_pack_share_encoding(tmp_path, monkeypatch):
    from venom_core.services.granite_operator import engine
    from venom_core.services.remote_training import job, worker_support

    snapshot = tmp_path / TrainingProfile().revision
    snapshot.mkdir()
    (snapshot / "tokenizer_config.json").write_text('{"chat_template":"native"}')

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            assert kwargs["local_files_only"] is True
            return cls()

    monkeypatch.setitem(
        sys.modules, "transformers", SimpleNamespace(AutoTokenizer=Tokenizer)
    )
    monkeypatch.setattr(
        engine,
        "encoded_rows",
        lambda rows, *args: [
            {"input_ids": [1, 2], "labels": [-100, 2]} for row in rows
        ],
    )
    document = {
        "datasets": {name: {"sha256": "a" * 64, "rows": 1} for name in job.DATA_FILES}
    }
    source = tmp_path / "data"
    source.mkdir()
    for name in job.DATA_FILES:
        target = source / name
        target.parent.mkdir(exist_ok=True)
        target.write_text('{"text":"fixture"}\n')
    manifest = tmp_path / "manifest.json"
    write_json(manifest, document)
    profile = tmp_path / "profile.json"
    write_json(profile, TrainingProfile().identity())
    monkeypatch.setattr(job, "load_dataset", lambda *args: ([{"id": 1}], [{"id": 2}]))
    monkeypatch.setattr(
        worker_support, "load_dataset", lambda *args: ([{"id": 1}], [{"id": 2}])
    )
    bundle = tmp_path / "input.zip"
    built = job.prepare(source, manifest, profile, snapshot, bundle, run_id="preflight")
    from venom_core.services.remote_training.bundles import extract_bundle

    extracted = tmp_path / "extracted"
    extract_bundle(bundle, extracted)
    code_root = Path(job.__file__).resolve().parents[3]
    config = {"snapshot": str(snapshot), "code_root": str(code_root)}
    actual, _ = worker_support.preflight(config, extracted, built["identity"])
    assert actual == TrainingProfile()
    assert set(built["files"]) == {
        "profile.json",
        "data-manifest.json",
        *job.DATA_FILES,
    }
    assert not any("test" in name for name in built["files"])
    changed = dict(built["identity"], encoding_sha256="b" * 64)
    with pytest.raises(ValueError, match="native_encoding_mismatch"):
        worker_support.preflight(config, extracted, changed)
    changed = dict(built["identity"], profile_sha256="b" * 64)
    with pytest.raises(ValueError, match="identity_mismatch"):
        worker_support.preflight(config, extracted, changed)
    for kwargs in ({"updates": 0}, {"max_seconds": 0}, {"dataset": "test"}):
        with pytest.raises(ValueError):
            job.prepare(
                source,
                manifest,
                profile,
                snapshot,
                tmp_path / "bad.zip",
                run_id="bad",
                **kwargs,
            )


def test_smoke_resume_continues_sixteen_step_checkpoint(setup):
    root, run, request, calls = setup
    worker.execute(request())
    calls.clear()
    checkpoint = "attempts/0001/result/stages/smoke-first/checkpoint"
    worker.execute(request("smoke", checkpoint))
    assert len(calls) == 1
    assert calls[0]["stage"] == "smoke-resume"
    assert calls[0]["updates"] == 4
    with pytest.raises(ValueError, match="smoke_resume_requires"):
        worker.execute(
            request("smoke", "attempts/0001/result/stages/smoke-resume/checkpoint")
        )


def test_runtime_guard_rejects_cloud_python_and_wrong_interpreter(monkeypatch):
    monkeypatch.setattr(
        worker,
        "sys",
        SimpleNamespace(version_info=(3, 12, 9), executable="/model/python"),
    )
    with pytest.raises(ValueError, match="qualified_py314"):
        worker.require_interpreter({"worker_python": "/model/python"})
    monkeypatch.setattr(
        worker,
        "sys",
        SimpleNamespace(version_info=(3, 14, 8), executable="/model/python"),
    )
    worker.require_interpreter({"worker_python": "/model/python"})
    with pytest.raises(ValueError, match="qualified_py314"):
        worker.require_interpreter({"worker_python": "/wrong/python"})


def test_stage_logs_reach_live_supervisor_stream(tmp_path, monkeypatch, capsys):
    import os

    from venom_core.services.remote_training import worker

    result = tmp_path / "result"
    (result / "logs").mkdir(parents=True)
    stage = result / "stage"
    stage.mkdir()
    write_json(stage / "metrics.json", {"loss": 0.2})
    real_popen = worker.subprocess.Popen

    def harmless_process(argv, **kwargs):
        return real_popen(
            [
                sys.executable,
                "-c",
                "import time;print('model-progress-1',flush=True);time.sleep(0.3);print('model-progress-2',flush=True)",
            ],
            **kwargs,
        )

    monkeypatch.setattr(worker.subprocess, "Popen", harmless_process)
    descriptor = os.open(tmp_path / "lock", os.O_CREAT | os.O_RDWR, 0o600)
    monkeypatch.setenv("REMOTE_TRAINING_GPU_LOCK_FD", str(descriptor))
    try:
        worker.run_stage(
            {
                "admission_db": str(tmp_path / "ledger"),
                "code_root": str(tmp_path),
                "worker_python": sys.executable,
            },
            {
                "stage": "smoke-first",
                "output": str(stage),
                "profile": TrainingProfile().identity(),
            },
            result,
            run_id="fixture",
            timeout=3,
            children=[],
        )
    finally:
        os.close(descriptor)
    live = capsys.readouterr().out
    assert "model-progress-1" in live
    assert "model-progress-2" in live
    raw_stage_log = (result / "logs/training.log").read_text()
    assert raw_stage_log in live
    assert json.loads(live.splitlines()[0])["phase"] == "loading"
    assert json.loads(live.splitlines()[-1])["phase"] == "stage_complete"


def test_stage_timeout_reaps_child_and_retains_last_output(
    tmp_path, monkeypatch, capsys
):
    from venom_core.services.remote_training import worker

    path = tmp_path / "training.log"
    path.write_bytes(b"timeout-diagnostic")
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            worker._wait_stage(child, 0.1, path, 0)
        assert child.poll() is not None
        assert capsys.readouterr().out == "timeout-diagnostic"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


@pytest.mark.parametrize("failure_at", [None, 125])
def test_three_independent_milestones_preserve_earlier_checkpoints(
    setup, monkeypatch, failure_at
):
    root, run, request, calls = setup
    original = request()
    original["manifest"]["identity"]["limits"]["max_updates"] = 160
    write_json(run / "input/.bundle-manifest.json", original["manifest"])
    worker.execute(original)
    last = None
    artifacts = {}
    real = worker.run_stage

    def stage(host, body, result, **kwargs):
        if failure_at and body["updates"] == 45:
            raise RuntimeError("fixture_interrupted")
        return real(host, body, result, **kwargs)

    monkeypatch.setattr(worker, "run_stage", stage)
    for step in [80, 125, 160]:
        req = request("train", last)
        req["until_update"] = step
        if step == failure_at:
            with pytest.raises(RuntimeError, match="fixture_interrupted"):
                worker.execute(req)
            break
        worker.execute(req)
        result = Path(req["attempt_root"]) / "result"
        metadata = json.loads((result / "metrics.json").read_text())
        assert metadata["candidate_step"] == step
        assert metadata["planned_max_updates"] == 160
        assert (
            json.loads((result / "checkpoint/receipt.json").read_text())["step"] == step
        )
        last = (result / "checkpoint").relative_to(run).as_posix()
        artifacts[step] = (
            result / "checkpoint/receipt.json",
            (result / "checkpoint/receipt.json").read_bytes(),
        )
    assert all(path.read_bytes() == content for path, content in artifacts.values())
    if failure_at is None:
        assert [c["updates"] for c in calls if c["stage"].startswith("train")] == [
            12,
            68,
            45,
            35,
        ]
    else:
        assert set(artifacts) == {80}


def test_full_160_update_request_keeps_native_stages_within_128(setup):
    root, run, request, calls = setup
    req = request()
    req["manifest"]["identity"]["limits"]["max_updates"] = 160
    write_json(run / "input/.bundle-manifest.json", req["manifest"])
    worker.execute(req)
    worker.execute(request("train"))
    stages = [c for c in calls if c["stage"].startswith("train")]
    assert [c["updates"] for c in stages] == [12, 128, 20]
    assert len({c["output"] for c in stages}) == 3


@pytest.mark.parametrize("until", [0, 161, True])
def test_invalid_milestone_does_not_run_training_stage(setup, until):
    root, run, request, calls = setup
    worker.execute(request())
    req = request("train")
    req["until_update"] = until
    with pytest.raises(ValueError):
        worker.execute(req)
    assert len(calls) == 2
