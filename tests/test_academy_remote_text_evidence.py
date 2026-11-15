"""Fault and provenance coverage for the remote text campaign evidence transfer."""

import hashlib
import io
import os
import sys
import tarfile
from contextlib import nullcontext
from pathlib import Path

import pytest

from scripts.academy.omni_pl_chat_data import write_jsonl
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.training_experiments import remote_text_qualification
from venom_core.services.training_experiments.adapters import resolve_adapter
from venom_core.services.training_experiments.checkpoint_evaluation import (
    GENERATION_OUTPUTS,
    seal_generation,
)
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    rows,
    stable_hash,
)
from venom_core.services.training_experiments.remote_text_evidence import (
    artifact_path,
    export_run,
    read_run,
    summarize,
    sync_run,
)
from venom_core.services.training_experiments.remote_text_qualification import (
    QualificationInputs,
    qualify,
    qualify_pending,
    read_qualification,
)

CAMPAIGN = "text-1"
RUN = "campaign-text-1-01"
LIMIT = 1_000_000
PLAN = "a" * 64
PROFILE = "b" * 64
DEV = "c" * 64
RECIPE = {"rank": 4, "alpha": 8, "dropout": 0.05, "target_modules": ["q_proj"]}


class Host:
    def __init__(self, directory, state):
        self.directory = directory
        self.state = state
        self.experiments = self
        self.calls = 0
        self.timeout = None
        self.mutate = None

    def status(self, campaign_id):
        assert campaign_id == CAMPAIGN
        return self.state

    def run_lock(self, run_id):
        assert run_id == RUN
        return nullcontext()

    def run_dir(self, run_id):
        assert run_id == RUN
        return self.directory

    def fetch(self, campaign_id, run_id, destination, max_bytes, *, timeout=None):
        self.calls += 1
        self.timeout = timeout
        result = io.BytesIO()
        export_run(self, campaign_id, run_id, result)
        payload = result.getvalue()
        assert len(payload) <= max_bytes
        destination.write_bytes(self.mutate(payload) if self.mutate else payload)
        return {"sha256": hashlib.sha256(payload).hexdigest()}


def _checkpoint(root, step):
    path = root / "training" / f"checkpoint-{step}"
    path.mkdir(parents=True)
    for name in CHECKPOINT_FILES:
        if name == "trainer_state.json":
            atomic_json(path / name, {"global_step": step})
        elif name == "adapter_config.json":
            atomic_json(
                path / name,
                {
                    "base_model_name_or_path": read_json(SNAPSHOT_PIN)["repo"],
                    "bias": "none",
                    "lora_alpha": RECIPE["alpha"],
                    "lora_dropout": RECIPE["dropout"],
                    "peft_type": "LORA",
                    "r": RECIPE["rank"],
                    "target_modules": r"model\.language_model\..*\.(q_proj)",
                    "task_type": "CAUSAL_LM",
                },
            )
        else:
            (path / name).write_text(f"{step}:{name}")
    hashes = {name: digest(path / name) for name in CHECKPOINT_FILES}
    atomic_json(path / "hashes.json", hashes)
    return hashes


def _publish_result(root, payload):
    atomic_json(root / "result.json", payload)
    checksum = digest(root / "result.json")
    atomic_json(root / "result-seal.json", {"result_sha256": checksum})
    return checksum


def _write_evaluation(run, manifest, result_root, eval_root, step, n_usable):
    eval_root.mkdir(parents=True)
    hashes = _checkpoint(run, step)
    for name in GENERATION_OUTPUTS:
        (eval_root / name).write_text("{}\n")
    atomic_json(eval_root / "judgments.json", [])
    atomic_json(
        eval_root / "manifest.json",
        {
            "outputs": {name: digest(eval_root / name) for name in GENERATION_OUTPUTS},
            "models": {
                "base": {"base": True},
                f"checkpoint-{step}": {
                    name: hashes[name]
                    for name in ("adapter_config.json", "adapter_model.safetensors")
                },
            },
            "data_sha256": manifest["profile"]["dev_sha256"],
            "snapshot_manifest_sha256": digest(SNAPSHOT_PIN),
            "model_repo": manifest["profile"]["model"],
            "revision": "f" * 40,
            "generation_mode": "text",
            "max_prompt_tokens": 512,
            "max_new_tokens": 128,
            "seed": 56,
            "engine": {"torch": "pinned"},
            "template": "vendor",
            "do_sample": False,
            "enable_thinking": False,
        },
    )
    seal_generation(eval_root)
    result = {
        "run_id": RUN,
        "profile_identity": PROFILE,
        "manifest_sha256": stable_hash(manifest),
        "dev_sha256": manifest["profile"]["dev_sha256"],
        "generation_sha256": digest(eval_root / "generation-seal.json"),
        "judgment_sha256": digest(eval_root / "judgments.json"),
        "checkpoint": {"step": step, "sha256": hashes["adapter_model.safetensors"]},
        "summaries": {
            "base": {"total": {"n": 2, "usable": 1, "critical": 0}},
            "candidate": {"total": {"n": 2, "usable": n_usable, "critical": 0}},
        },
    }
    checksum = _publish_result(result_root, result)
    return result, checksum


def setup_host(
    tmp_path, *, n_usable=2, checkpoint_eval=False, train_sha=DEV, dev_sha=DEV
):
    run = tmp_path / "host"
    run.mkdir()
    manifest = {
        "run_id": RUN,
        "campaign_id": CAMPAIGN,
        "profile_identity": PROFILE,
        "recipe": RECIPE,
        "profile": {
            "model": "LiquidAI/LFM3-Omni-2B",
            "train_sha256": train_sha,
            "dev_sha256": dev_sha,
            "calibration_sha256": "d" * 64,
        },
        "calibration": {"judge": "exact-v1", "dev_sha256": dev_sha},
    }
    atomic_json(
        run / "state.json",
        {"campaign_id": CAMPAIGN, "status": "succeeded", "attempt": 1},
    )
    atomic_json(run / "manifest.json", manifest)
    atomic_json(run / "recipe.json", manifest["recipe"])
    trial = {"run_id": RUN, "status": "succeeded", "attempt": 1}
    if checkpoint_eval:
        rows = []
        for step, usable in ((1, n_usable), (2, 1)):
            folder = run / "checkpoint-evaluations" / str(step)
            result, checksum = _write_evaluation(
                run, manifest, folder, folder, step, usable
            )
            rows.append(
                {"step": step, "status": "succeeded", "result_sha256": checksum}
            )
        trial["checkpoint_evaluations"] = rows
        checksum = _publish_result(run, {**result, "checkpoint_evaluations": rows})
    else:
        _, checksum = _write_evaluation(
            run, manifest, run, run / "evaluation-1", 1, n_usable
        )
    trial["result_sha256"] = checksum
    return Host(
        run,
        {
            "campaign_id": CAMPAIGN,
            "status": "succeeded",
            "plan": {
                "plan_sha256": PLAN,
                "profile_identity": PROFILE,
                "selection": {"min_usable_delta": 0.01, "max_critical_delta": 0.0},
            },
            "selected_run_id": RUN,
            "trials": [trial],
        },
    )


def test_publish_resume_and_best_observed_survive_host_loss(tmp_path):
    host = setup_host(tmp_path, checkpoint_eval=True)
    store = tmp_path / "store"
    saved = sync_run(host, host.state, RUN, store, LIMIT, timeout=15)
    assert saved["latest_resume"]["step"] == 2
    assert saved["latest_resume"]["sha256"] != saved["checkpoints"][0]["sha256"]
    assert host.timeout == 15
    assert artifact_path(store, RUN).is_file()
    # A controller restart can rebuild the receipt after the archive was committed.
    (store / RUN / "verified.json").unlink()
    reopened = sync_run(host, host.state, RUN, store, LIMIT)
    assert read_run(store, RUN) == reopened
    assert host.calls == 1
    report = summarize(host.state, {RUN: reopened})
    assert report["best_observed"]["step"] == 1
    assert report["best_qualified"] is None
    assert report["outcome"] == "PROVISIONAL"


def test_missing_or_flat_development_results(tmp_path):
    host = setup_host(tmp_path, n_usable=1)
    assert summarize(host.state, {})["outcome"] == "INCONCLUSIVE"
    saved = sync_run(host, host.state, RUN, tmp_path / "store", LIMIT)
    assert summarize(host.state, {RUN: saved})["outcome"] == "NO_IMPROVEMENT"
    host.state["trials"].append({"run_id": "second", "status": "failed"})
    assert summarize(host.state, {RUN: saved})["outcome"] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw[:2048],
        lambda raw: raw.replace(
            b"1:adapter_model.safetensors", b"1:ADAPTER_MODEL.safetensors", 1
        ),
    ],
)
def test_incomplete_or_corrupt_transfer_is_retried(tmp_path, mutate):
    host = setup_host(tmp_path)
    host.mutate = mutate
    store = tmp_path / "store"
    with pytest.raises(ValueError, match="remote_text_evidence_"):
        sync_run(host, host.state, RUN, store, LIMIT)
    assert not (store / RUN / "verified.json").exists()
    assert not (store / RUN / "evidence.tar").exists()
    host.mutate = None
    sync_run(host, host.state, RUN, store, LIMIT)
    assert host.calls == 2
    path = artifact_path(store, RUN)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive_changed"):
        artifact_path(store, RUN)


def test_archive_members_are_allowlisted_and_non_links(tmp_path):
    host = setup_host(tmp_path)

    def add_member(raw):
        with tarfile.open(fileobj=(stream := io.BytesIO(raw)), mode="a") as archive:
            malicious = tarfile.TarInfo("../../private")
            malicious.type = tarfile.SYMTYPE
            malicious.linkname = "/etc/passwd"
            archive.addfile(malicious)
        return stream.getvalue()

    host.mutate = add_member
    with pytest.raises(ValueError, match="unlisted_member"):
        sync_run(host, host.state, RUN, tmp_path / "store", LIMIT)


def test_transfer_accepts_ustar_padding_across_record_boundary(tmp_path):
    host = setup_host(tmp_path)
    archive = io.BytesIO()
    log = host.directory / "attempt-1.log"
    log.write_bytes(b"")
    export_run(host, CAMPAIGN, RUN, archive)
    archive.seek(0)
    with tarfile.open(fileobj=archive, mode="r:") as source:
        source.getmembers()
        padding_adjustment = (
            tarfile.RECORDSIZE - tarfile.BLOCKSIZE - source.offset
        ) % tarfile.RECORDSIZE
    log.write_bytes(b"x" * padding_adjustment)
    record = sync_run(host, host.state, RUN, tmp_path / "store", LIMIT)
    assert record["archive_bytes"] % tarfile.RECORDSIZE == 0


def test_campaign_and_run_digests_cannot_be_replayed(tmp_path):
    host = setup_host(tmp_path)
    store = tmp_path / "store"
    saved = sync_run(host, host.state, RUN, store, LIMIT)
    host.state["plan"]["plan_sha256"] = "0" * 64
    assert summarize(host.state, {RUN: saved})["verified_runs"] == 0
    with pytest.raises(ValueError, match="receipt_conflict"):
        sync_run(host, host.state, RUN, store, LIMIT)
    with pytest.raises(ValueError, match="invalid_run_id"):
        artifact_path(store, "../borrowed")


def _holdout_paths(tmp_path, *, overlap=False, unknown=False):
    train = tmp_path / "train.jsonl"
    dev = tmp_path / "dev.jsonl"
    final = tmp_path / "holdout.jsonl"
    calibration = tmp_path / "judge.json"
    train_row = {
        "record_id": "train",
        "group_id": "train-family",
        "split": "train",
        "language": "pl",
        "messages": [
            {"role": "user", "content": "Podaj tydzień."},
            {"role": "assistant", "content": "Siedem dni."},
        ],
        "supervision": [1],
        "quality_status": "accepted",
        "source_repo": "authored",
        "source_revision": "frozen",
        "source_record_id": "train",
        "license": "CC0",
        "review_note": "approved",
    }
    dev_row = {
        "record_id": "dev",
        "group_id": "dev-family",
        "split": "dev",
        "language": "pl",
        "messages": [{"role": "user", "content": "Podaj dzień."}],
        "task": "dialogue",
        "criteria": [
            {"id": "correct", "kind": "content", "description": "Right answer"}
        ],
    }
    holdout = {
        **dev_row,
        "record_id": "pilot",
        "group_id": "dev-family" if overlap else "pilot-family",
        "split": "pilot",
        "messages": [{"role": "user", "content": "Podaj miesiąc."}],
    }
    write_jsonl(train, [train_row])
    write_jsonl(dev, [dev_row])
    write_jsonl(final, [holdout])
    grade = {
        "criteria": {"correct": True},
        "polish_ok": True,
        "natural_ok": True,
        "critical_error": False,
        "reason": "Verified by reviewer",
    }
    fallback = {**grade, "criteria": {"correct": False}, "reason": "Rejected"}
    outputs = {"bad": fallback} if unknown else {"bad": fallback, "good": grade}
    atomic_json(
        calibration,
        {
            "schema_version": 1,
            "judge": "exact-v1",
            "dev_sha256": digest(final),
            "reviewer": "Operator",
            "cases": {"pilot": {"outputs": outputs, "fallback": fallback}},
        },
    )
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    return QualificationInputs(
        train=train,
        dev=dev,
        final_test=final,
        calibration=calibration,
        snapshot=snapshot,
        training_venv=venv,
        max_seconds=60,
    )


def _evaluate_fixture(command, log, timeout, run_id, model):
    assert timeout == 60
    assert run_id == RUN
    data, generation = map(Path, command[-5:-3])
    checkpoint = Path(command[-1].split("=", 1)[1])
    generation.mkdir()
    case = rows(data)[0]
    assert case["record_id"] == "pilot"
    assert case["split"] == "dev"
    responses = {
        "A": {"text": "bad", "finish": "stop", "error": None},
        "B": {"text": "good", "finish": "stop", "error": None},
    }
    write_jsonl(generation / "blind.jsonl", [{"case": case, "answers": responses}])
    write_jsonl(
        generation / "raw.jsonl", [{"case": case["record_id"], "answer": responses}]
    )
    atomic_json(
        generation / "unblind.json", {"pilot": {"A": "base", "B": checkpoint.name}}
    )
    pin = read_json(SNAPSHOT_PIN)
    assert model == pin["repo"]
    atomic_json(
        generation / "manifest.json",
        {
            "outputs": {name: digest(generation / name) for name in GENERATION_OUTPUTS},
            "models": {
                "base": {"base": True},
                checkpoint.name: {
                    name: digest(checkpoint / name)
                    for name in ("adapter_config.json", "adapter_model.safetensors")
                },
            },
            "data_sha256": digest(data),
            "snapshot_manifest_sha256": digest(SNAPSHOT_PIN),
            "model_repo": model,
            "revision": pin["revision"],
            "resumed_generations": 0,
            "generation_mode": "text",
            "max_prompt_tokens": 512,
            "max_new_tokens": 128,
            "seed": 56,
            "engine": {"torch": "pinned"},
            "template": "vendor",
            "do_sample": False,
            "enable_thinking": False,
        },
    )


@pytest.mark.parametrize(
    "scenario", ["qualified", "overlap", "unknown", "continuation"]
)
def test_final_holdout_gates_archive_and_catalog(tmp_path, scenario):
    spec = _holdout_paths(
        tmp_path, overlap=scenario == "overlap", unknown=scenario == "unknown"
    )
    host = setup_host(tmp_path, train_sha=digest(spec.train), dev_sha=digest(spec.dev))
    evidence = tmp_path / "evidence"
    academy = tmp_path / "academy"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    pins = {
        "final_test_sha256": digest(spec.final_test),
        "final_calibration_sha256": digest(spec.calibration),
    }
    kwargs = {"evaluator": _evaluate_fixture, **pins}
    if scenario == "continuation":
        host.state["plan"]["variants"] = [{"initial_adapter": {"id": "omni-p13-145"}}]
        with pytest.raises(
            ValueError, match="remote_text_final_parent_comparison_required"
        ):
            qualify(evidence, host.state, receipts, academy, spec, **kwargs)
        assert not (academy / "adapters").exists()
        return
    if scenario == "overlap":
        with pytest.raises(ValueError, match="group appears in multiple splits"):
            qualify(evidence, host.state, receipts, academy, spec, **kwargs)
        assert read_qualification(evidence, host.state, receipts, **pins) is None
        assert not (academy / "adapters").exists()
        return
    result = qualify(evidence, host.state, receipts, academy, spec, **kwargs)
    assert read_qualification(evidence, host.state, receipts, **pins) == result
    if scenario == "unknown":
        assert result["status"] == "incomplete_calibration"
        assert result["qualified"] is None
        assert not (academy / "adapters").exists()
    else:
        assert result["status"] == "passed"
        assert result["runtime"] == "omni-native-peft-text"
        _, adapter = resolve_adapter(academy, result["qualified"]["adapter_id"], RECIPE)
        assert adapter["weights_sha256"] == receipts[RUN]["checkpoints"][0]["sha256"]
        assert result["holdout_identity"]["dataset_sha256"] != digest(spec.dev)
        # Changing the sealed test may not select another candidate or repeat scoring.
        with pytest.raises(
            ValueError, match="remote_text_final_result_identity_mismatch"
        ):
            read_qualification(
                evidence,
                host.state,
                receipts,
                final_test_sha256=DEV,
                final_calibration_sha256=pins["final_calibration_sha256"],
            )


def test_pending_qualifier_waits_for_prepared_campaign_and_available_gpu(
    tmp_path, monkeypatch
):
    spec = _holdout_paths(tmp_path)
    host = setup_host(tmp_path, train_sha=digest(spec.train), dev_sha=digest(spec.dev))
    academy = tmp_path / "academy"
    queue = academy / "remote-text-final-inputs"
    queue.mkdir(parents=True, mode=0o700)
    directory = academy / "remote-text" / CAMPAIGN
    evidence = directory / "evidence"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    pins = {
        "final_test_sha256": digest(spec.final_test),
        "final_calibration_sha256": digest(spec.calibration),
    }
    record = {
        "campaign_id": CAMPAIGN,
        "status": "cleanup_pending",
        "plan": {
            "request": pins,
            "remote_plan_sha256": PLAN,
            "profile_identity": PROFILE,
        },
        "remote": host.state,
        "evidence": receipts,
    }
    atomic_json(queue / f"{CAMPAIGN}.json", spec.model_dump(mode="json"))
    atomic_json(directory / "state.json", record)
    assert qualify_pending(academy, evaluator=_evaluate_fixture) == {"status": "idle"}
    atomic_json(directory / "state.json", {**record, "status": "completed"})

    module = remote_text_qualification
    admission = module.RuntimeAdmission(tmp_path / "admission.sqlite3")
    monkeypatch.setattr(module, "get_runtime_admission", lambda: admission)

    def no_api(*_args, **_kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(module, "create_connection", no_api)
    busy = {"status": "busy", "campaign_id": CAMPAIGN}
    attempts = directory / "qualification-attempts.json"
    with module.file_lock(admission.database.parent / "academy-experiments.gpu.lock"):
        for _ in range(3):
            assert qualify_pending(academy) == busy
    lease = admission.acquire(owner="test", run_id="other", engine="test", model="test")
    try:
        assert qualify_pending(academy) == busy
    finally:
        assert lease.release()
    assert read_json(attempts) == {"attempts": 0}

    assert qualify_pending(academy, evaluator=_evaluate_fixture) == {
        "status": "passed",
        "campaign_id": CAMPAIGN,
    }
    assert qualify_pending(academy, evaluator=_evaluate_fixture) == {"status": "idle"}
    assert read_json(directory / "qualification-attempts.json") == {"attempts": 1}


def test_pending_transient_failure_has_bounded_retry(tmp_path):
    spec = _holdout_paths(tmp_path)
    host = setup_host(tmp_path, train_sha=digest(spec.train), dev_sha=digest(spec.dev))
    academy = tmp_path / "academy"
    queue = academy / "remote-text-final-inputs"
    queue.mkdir(parents=True, mode=0o700)
    directory = academy / "remote-text" / CAMPAIGN
    evidence = directory / "evidence"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    record = {
        "campaign_id": CAMPAIGN,
        "status": "completed",
        "plan": {
            "request": {
                "final_test_sha256": digest(spec.final_test),
                "final_calibration_sha256": digest(spec.calibration),
            },
            "remote_plan_sha256": PLAN,
            "profile_identity": PROFILE,
        },
        "remote": host.state,
        "evidence": receipts,
    }
    atomic_json(queue / f"{CAMPAIGN}.json", spec.model_dump(mode="json"))
    atomic_json(directory / "state.json", record)
    # Holdout contents changed after the operator froze its digest.
    spec.final_test.write_text("{}\n")
    for expected_attempt in (1, 2, 3):
        result = qualify_pending(academy, evaluator=_evaluate_fixture)
        assert result == {
            "status": "retry" if expected_attempt < 3 else "failed",
            "campaign_id": CAMPAIGN,
            "attempts": expected_attempt,
        }
    assert qualify_pending(academy, evaluator=_evaluate_fixture) == {"status": "idle"}
    assert not (academy / "adapters").exists()


def test_qualified_runtime_launch_uses_exclusive_ledger_and_cpu_process(
    tmp_path, monkeypatch
):
    module = remote_text_qualification
    host = module.RuntimeAdmission(tmp_path / "admission.sqlite3")
    monkeypatch.setattr(module, "get_runtime_admission", lambda: host)

    def no_api(*_args, **_kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(module, "create_connection", no_api)
    log = tmp_path / "ok.log"
    module._evaluate(
        [sys.executable, "-c", "import time; print('fixture'); time.sleep(0.15)"],
        log,
        4,
        RUN,
        "fixture-model",
    )
    assert log.read_text().strip() == "fixture"
    with pytest.raises(TimeoutError, match="inference_timed_out"):
        module._evaluate(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "timeout.log",
            1,
            RUN,
            "fixture-model",
        )
    # A terminated subprocess releases the lease after quiescence.
    lease = host.acquire(owner="test", run_id="verify", engine="test", model="test")
    assert lease.release()
    assert os.stat(log).st_size > 0
