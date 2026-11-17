"""Fault and provenance coverage for the remote text campaign evidence transfer."""

import hashlib
import io
import json
import os
import sys
import tarfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from scripts.academy.omni_pl_chat_data import write_jsonl
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.training_experiments import local_semantic_judge as semantic
from venom_core.services.training_experiments import (
    remote_text_local,
    remote_text_qualification,
)
from venom_core.services.training_experiments import worker as worker_module
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
from venom_core.services.training_experiments.remote_text_local import (
    collect_local,
    pin_local,
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
    tmp_path,
    *,
    n_usable=2,
    checkpoint_eval=False,
    train_sha=DEV,
    dev_sha=DEV,
    parent=None,
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
    if parent is not None:
        manifest["initial_adapter"] = parent
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


def _holdout_paths(tmp_path, *, overlap=False, unknown=False, size=1):
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
    holdout_cases = [
        holdout
        if not index
        else {
            **holdout,
            "record_id": f"pilot-{index}",
            "messages": [{"role": "user", "content": f"Zadanie {index}."}],
        }
        for index in range(size)
    ]
    write_jsonl(final, holdout_cases)
    grade = {
        "criteria": {"correct": True},
        "polish_ok": True,
        "natural_ok": True,
        "critical_error": False,
        "reason": "Verified by reviewer",
    }
    fallback = {**grade, "criteria": {"correct": False}, "reason": "Rejected"}
    outputs = (
        {"bad": fallback}
        if unknown
        else {
            "bad": fallback,
            "good": grade,
            "critical": {**fallback, "critical_error": True},
        }
    )
    atomic_json(
        calibration,
        {
            "schema_version": 1,
            "judge": "exact-v1",
            "dev_sha256": digest(final),
            "reviewer": "Operator",
            "cases": {
                case["record_id"]: {"outputs": outputs, "fallback": fallback}
                for case in holdout_cases
            },
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


def _evaluate_fixture(command, log, timeout, run_id, model, *, outcomes=None):
    assert timeout == 60
    assert run_id == RUN
    base_index = command.index("base")
    data, generation = map(Path, command[base_index - 3 : base_index - 1])
    checkpoints = dict(value.split("=", 1) for value in command[base_index + 1 :])
    generation.mkdir()
    mapping = dict(zip("ABC", ["base", *checkpoints]))
    outcomes = outcomes or [("bad", "good")]
    blind = []
    for case, texts in zip(rows(data), outcomes, strict=True):
        assert case["split"] == "dev"
        answers = {
            label: {"text": text, "finish": "stop", "error": None}
            for label, text in zip(mapping, texts, strict=True)
        }
        blind.append({"case": case, "answers": answers})
    write_jsonl(generation / "blind.jsonl", blind)
    write_jsonl(
        generation / "raw.jsonl",
        [{"case": row["case"]["record_id"], "answer": row["answers"]} for row in blind],
    )
    atomic_json(
        generation / "unblind.json",
        {row["case"]["record_id"]: mapping for row in blind},
    )
    pin = read_json(SNAPSHOT_PIN)
    assert model == pin["repo"]
    atomic_json(
        generation / "manifest.json",
        {
            "outputs": {name: digest(generation / name) for name in GENERATION_OUTPUTS},
            "models": {
                "base": {"base": True},
                **{
                    tag: {
                        name: digest(Path(checkpoint) / name)
                        for name in ("adapter_config.json", "adapter_model.safetensors")
                    }
                    for tag, checkpoint in checkpoints.items()
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


@pytest.mark.parametrize("scenario", ["qualified", "overlap", "unknown"])
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


def _parent_entry(academy, tmp_path):
    hashes = _checkpoint(tmp_path, 39)
    source = tmp_path / "training" / "checkpoint-39"
    destination = academy / "adapters" / "source-adapter"
    destination.mkdir(parents=True)
    pin = read_json(SNAPSHOT_PIN)
    parent = {
        "schema_version": 1,
        "adapter_id": destination.name,
        "label": "Pinned parent",
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_sha256": digest(SNAPSHOT_PIN),
        "config_sha256": hashes["adapter_config.json"],
        "weights_sha256": hashes["adapter_model.safetensors"],
        "source": {"identity": "parent-run", "sha256": DEV},
    }
    files = {k: hashes[k] for k in ("adapter_config.json", "adapter_model.safetensors")}
    for name in files:
        (destination / name).write_bytes((source / name).read_bytes())
    atomic_json(destination / "adapter.json", parent)
    atomic_json(destination / "hashes.json", files)
    return parent


def _continued_campaign(tmp_path, *, eligible_manifest=True):
    spec = _holdout_paths(tmp_path, size=3)
    academy = tmp_path / "academy"
    parent = _parent_entry(academy, tmp_path)
    host = setup_host(
        tmp_path,
        train_sha=digest(spec.train),
        dev_sha=digest(spec.dev),
        parent=parent if eligible_manifest else None,
    )
    host.state["plan"]["variants"] = [
        {"run_id": RUN, "initial_adapter": parent, "recipe": RECIPE},
        {"run_id": "campaign-text-1-02", "initial_adapter": parent, "recipe": RECIPE},
    ]
    host.state["plan"]["budget"] = {"max_artifact_bytes": LIMIT}
    pins = {
        "final_test_sha256": digest(spec.final_test),
        "final_calibration_sha256": digest(spec.calibration),
    }
    return spec, academy, parent, host, pins


@pytest.fixture
def semantic_audit(tmp_path, monkeypatch):
    root = tmp_path / "judge-audit"
    root.mkdir()
    monkeypatch.setenv("VENOM_ACADEMY_JUDGE_AUDIT_ROOT", str(root))
    (root / "judge-calls").mkdir()
    model, model_sha, version = "gemma4:12b-it-q4_K_M", "d" * 64, "0.40.14"

    def write(name, value):
        path = root / name
        atomic_json(path, value)
        return digest(path)

    panel, accepted, rejected, reviews, style, semantics = [], [], {}, [], {}, {}
    for family in range(12):
        answers = []
        case = {
            "id": f"group-{family}",
            "messages": [],
            "criteria": [{"description": "test", "id": "correct"}],
            "answers": answers,
        }
        count = 5 if family < 6 else 4 if family < 9 else 6
        for index in range(count):
            identity = f"case-{family}-{index}"
            answer = {"id": identity, "text": "Dowód testowy"}
            answers.append(answer)
            positive = index < 2
            if positive:
                accepted.append(identity)
            else:
                rejected[identity] = {"critical": True}
            contrast = 2 if family < 9 else 4
            language = {
                "polish_ok": index != contrast or family < 6,
                "natural_ok": index != contrast + 1 or family < 6,
            }
            if family >= 6 and (positive or index in {contrast, contrast + 1}):
                style[identity] = language
            is_injection = family >= 9 and index == 3
            if family >= 9 and index == 2:
                semantics[identity] = {
                    "atoms": {"correct": "contradicted"},
                    "unsupported": "yes",
                    "injection": False,
                }
            if is_injection:
                semantics[identity] = {"injection": True}
            grade = {
                "atoms": {"correct": "supported" if positive else "contradicted"},
                "unsupported": "no" if positive else "yes",
                "injection": is_injection,
                "reason": "fixed fixture",
                **language,
            }
            response = {
                "model": model,
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(grade)},
            }
            request = semantic._request(
                model,
                {
                    "messages": [],
                    "criteria": case["criteria"],
                    "evidence": [],
                    "candidate": answer["text"],
                },
                ["correct"],
            )
            reviews.append(
                {
                    "id": identity,
                    "case": case["id"],
                    "finish": "stop",
                    "grade": grade,
                    "call_sha256": write(
                        f"judge-calls/{identity}.json",
                        {"request": request, "response": response},
                    ),
                }
            )
        panel.append(case)

    gold = write(
        "qualification-gold.json",
        {
            "accepted": accepted,
            "rejected": rejected,
            "expected_style": style,
            "challenge_cases": [item["id"] for item in panel[-3:]],
            "expected_semantics": semantics,
        },
    )
    panel_sha = write("qualification-panel.json", {"cases": panel})
    manifest = write("qualification-manifest.json", {})
    protocol = write(
        "judge-protocol.json",
        {
            "system": semantic.PROMPT,
            "options": semantic.OPTIONS,
            "model": model,
            "model_sha256": model_sha,
            "ollama": {"version": version},
            "execution_order": [row["id"] for row in reviews],
            "panel_sha256": panel_sha,
            "gold_sha256": gold,
            "manifest_sha256": manifest,
        },
    )
    result = write("judge-result.json", {"protocol_sha256": protocol, "rows": reviews})
    receipt = {
        "schema_version": 1,
        "model": model,
        "model_sha256": model_sha,
        "ollama_version": version,
        "prompt_sha256": semantic.PROMPT_SHA256,
        "protocol_sha256": protocol,
        "gold_sha256": gold,
        "result_sha256": result,
        "true_positives": 24,
        "positive_total": 24,
        "false_positives": 0,
        "negative_total": 36,
        "families_covered": 12,
        "families_total": 12,
    }
    return {"judge_qualification": receipt}, root


def test_semantic_audit_rechecks_hashes_and_derived_false_positive_gate(semantic_audit):
    settings, root = semantic_audit
    pin = semantic.qualification(settings)
    assert pin.true_positives == 24
    result_path = root / "judge-result.json"
    result = read_json(result_path)
    result["rows"][2]["grade"] = result["rows"][0]["grade"]
    atomic_json(result_path, result)
    with pytest.raises(ValueError, match="audit_changed"):
        semantic.qualification(settings)
    settings["judge_qualification"]["result_sha256"] = digest(result_path)
    with pytest.raises(ValueError, match="audit_call_changed"):
        semantic.qualification(settings)
    call = root / "judge-calls" / f"{result['rows'][2]['id']}.json"
    updated = read_json(call)
    updated["response"]["message"]["content"] = json.dumps(result["rows"][2]["grade"])
    atomic_json(call, updated)
    result["rows"][2]["call_sha256"] = digest(call)
    atomic_json(result_path, result)
    settings["judge_qualification"]["result_sha256"] = digest(result_path)
    with pytest.raises(ValueError, match="audit_acceptance_invalid"):
        semantic.qualification(settings)


def test_semantic_wrong_language_and_injection_cannot_bypass_correct_atoms():
    case = {"criteria": [{"id": "correct", "kind": "content"}]}
    complete = {
        "atoms": {"correct": "supported"},
        "unsupported": "no",
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "ok",
    }
    answer = {"text": "Mailbox 42."}
    wrong_language = semantic._Decision.model_validate({**complete, "polish_ok": False})
    grade = semantic._grade(wrong_language, {}, case, answer)
    assert grade["criteria"]["correct"] is True
    assert not grade["polish_ok"]
    assert not semantic._supported(wrong_language)
    injected = semantic._Decision.model_validate({**complete, "injection": True})
    grade = semantic._grade(injected, {}, case, answer)
    assert grade["critical_error"]
    assert not grade["criteria"]["correct"]
    response = {
        "model": "review",
        "done": True,
        "done_reason": "stop",
        "message": {
            "content": json.dumps(complete),
            "thinking": "unexpected",
        },
    }
    assert semantic._decode(response, ["correct"], "review") is None


def test_dev_worker_scores_outside_run_lock_and_commits_same_review(
    tmp_path, monkeypatch
):
    from contextlib import contextmanager

    service = Mock()
    service.run_dir.return_value = tmp_path
    worker = worker_module.Worker(service, RUN, 1)
    worker.deadline = worker_module.time.monotonic() + 30
    state = {"run_id": RUN, "attempt": 1, "stop_requested": False}
    service.store.read.return_value = state
    service._review_inputs.return_value = (tmp_path, tmp_path / "dev.jsonl")
    bundle = {"sentinel": "blinded answers"}
    calibration = {"judge": semantic.JUDGE}
    monkeypatch.setattr(worker_module, "review_data", lambda *_: bundle)
    locked = False

    @contextmanager
    def lock(_):
        nonlocal locked
        locked = True
        try:
            yield
        finally:
            locked = False

    service.run_lock.side_effect = lock
    grades = [{"label": "A", "model_review_call": {"request_sha256": DEV}}]

    def review(config, prompt_bundle, run_id, seconds, *, check):
        assert not locked
        assert config == calibration
        assert prompt_bundle is bundle
        assert run_id == RUN
        assert 0 < seconds <= 30
        check()
        return grades

    monkeypatch.setattr(semantic, "review_bundle", review)

    def save(record, judgments, *, checkpoint_step):
        assert locked
        assert record == state
        assert judgments == grades
        assert checkpoint_step is None

    service._commit.side_effect = save
    worker._score_calibration(state, calibration)
    service._commit.assert_called_once()


@pytest.mark.parametrize("scenario", ["pass", "inconclusive", "wrong-model"])
def test_semantic_final_seals_every_arm_and_qualifies_unseen_phrasing(
    tmp_path,
    monkeypatch,
    semantic_audit,
    scenario,
):
    inconclusive = scenario == "inconclusive"
    qualification, _ = semantic_audit
    spec, academy, _, host, pins = _continued_campaign(tmp_path)
    calibration = {
        **qualification,
        "judge": semantic.JUDGE,
        "schema_version": 1,
        "dev_sha256": pins["final_test_sha256"],
        "reviewer": "Operator fixture",
        "cases": {
            case["record_id"]: {
                "claims": {
                    "correct": {
                        "kind": "value",
                        "field_aliases": ["limit wysyłki"],
                        "value_aliases": ["14 dni"],
                    }
                }
            }
            for case in rows(spec.final_test)
        },
    }
    atomic_json(spec.calibration, calibration)
    pins["final_calibration_sha256"] = digest(spec.calibration)
    evidence = tmp_path / "evidence"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    api = []
    expected = qualification["judge_qualification"]
    module = remote_text_qualification
    admission = module.RuntimeAdmission(tmp_path / "judge-ledger.sqlite3")
    monkeypatch.setattr(semantic, "get_runtime_admission", lambda: admission)
    monkeypatch.setattr(module.Worker, "release_gpu", lambda *_a, **_kw: {})

    def respond(request):
        api.append(request.url.path)
        assert request.url.host == "127.0.0.1"
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": expected["ollama_version"]})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": expected["model"],
                            "digest": DEV
                            if scenario == "wrong-model"
                            else expected["model_sha256"],
                        }
                    ]
                },
            )
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        data = json.loads(request.content)
        assert data["model"] == expected["model"]
        if request.url.path == "/api/generate":
            assert data["keep_alive"] == 0
            return httpx.Response(200, json={})
        assert data["options"] == semantic.OPTIONS
        assert data["messages"][0]["content"] == semantic.PROMPT
        assert data["format"] == semantic.schema_for(["correct"])
        candidate = json.loads(data["messages"][1]["content"])["candidate"]
        atom = {
            "Zamówienie można wysłać w ciągu dwóch tygodni.": "supported",
            "W źródle pominięto termin.": "omitted",
            "Być może dwa tygodnie.": "unclear",
        }[candidate]
        content = json.dumps(
            {
                "atoms": {"correct": atom},
                "unsupported": "no",
                "injection": False,
                "reason": "fixture",
                "polish_ok": True,
                "natural_ok": True,
            }
        )
        return httpx.Response(
            200,
            json={
                "model": expected["model"],
                "done": True,
                "done_reason": "stop",
                "message": {"content": content},
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        semantic.httpx,
        "Client",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )

    def evaluator(*args):
        _evaluate_fixture(
            *args,
            outcomes=[
                (
                    "W źródle pominięto termin.",
                    "Być może dwa tygodnie."
                    if inconclusive
                    else "Zamówienie można wysłać w ciągu dwóch tygodni.",
                    "W źródle pominięto termin.",
                )
            ]
            * 3,
        )

    if scenario == "wrong-model":
        with pytest.raises(ValueError, match="runtime_identity_changed"):
            qualify(
                evidence,
                host.state,
                receipts,
                academy,
                spec,
                evaluator=lambda *_: pytest.fail(
                    "GPU generation before judge preflight"
                ),
                **pins,
            )
        assert api == ["/api/tags"]
        return
    result = qualify(
        evidence, host.state, receipts, academy, spec, evaluator=evaluator, **pins
    )
    assert result["calibration_protocol"]["judge_qualification"] == expected
    assert result["status"] == ("incomplete_calibration" if inconclusive else "passed")
    assert (result["qualified"] is None) == inconclusive
    assert result["unverifiable_answers"] == (3 if inconclusive else 0)
    retained = (
        evidence
        / "final-qualification"
        / result["evidence_name"]
        / "generation"
        / "judgments.json"
    )
    assert digest(retained) == result["judgments_sha256"]
    assert len(read_json(retained)) == api.count("/api/chat") == 9
    assert all(
        item["model_review_call"]["request_sha256"] for item in read_json(retained)
    )
    assert api.count("/api/generate") == 1
    assert (
        read_qualification(evidence, host.state, receipts, academy_root=academy, **pins)
        == result
    )
    assert (
        qualify(
            evidence, host.state, receipts, academy, spec, evaluator=evaluator, **pins
        )
        == result
    )
    assert api.count("/api/chat") == 9
    lease = admission.acquire(owner="test", run_id="done", engine="test", model="test")
    assert lease.release()


@pytest.mark.parametrize(
    ("outcomes", "status", "blocker"),
    [
        (
            [("good", "good", "good"), ("bad", "good", "bad"), ("bad", "bad", "bad")],
            "passed",
            None,
        ),
        (
            [("bad", "bad", "good"), ("bad", "good", "bad"), ("bad", "good", "bad")],
            "failed_quality",
            "lost_parent_usable_case_ids",
        ),
        (
            [
                ("critical", "good", "critical"),
                ("critical", "critical", "bad"),
                ("bad", "good", "bad"),
            ],
            "failed_quality",
            "new_parent_critical_case_ids",
        ),
        (
            [
                ("critical", "good", "critical"),
                ("bad", "critical", "critical"),
                ("bad", "good", "bad"),
            ],
            "failed_quality",
            "new_m0_critical_case_ids",
        ),
        (
            [("bad", "good", "good"), ("bad", "bad", "bad"), ("bad", "bad", "bad")],
            "failed_quality",
            None,
        ),
        (
            [
                ("bad", "good", "unknown-parent"),
                ("bad", "bad", "bad"),
                ("bad", "bad", "bad"),
            ],
            "incomplete_calibration",
            None,
        ),
    ],
)
def test_continuation_requires_parent_gain_retention_and_per_case_critical_protection(
    tmp_path, outcomes, status, blocker
):
    spec, academy, parent, host, pins = _continued_campaign(tmp_path)
    evidence = tmp_path / "evidence"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    executions = []

    def evaluate(*args):
        executions.append(1)
        _evaluate_fixture(*args, outcomes=outcomes)

    def finalize():
        return qualify(
            evidence, host.state, receipts, academy, spec, evaluator=evaluate, **pins
        )

    result = finalize()
    assert result["status"] == status
    assert result["binding"]["parent"] == {"entry": parent, "recipe": RECIPE}
    assert finalize() == result
    assert executions == [1]
    assert (
        read_qualification(evidence, host.state, receipts, academy_root=academy, **pins)
        == result
    )
    if blocker:
        assert result["parent_comparison"][blocker] == [
            "pilot" if "lost" in blocker else "pilot-1"
        ]
        assert result["parent_comparison"]["parent_usable_delta"] > 0
    if status == "passed":
        assert result["parent_comparison"]["parent_usable_delta"] == 1 / 3
        assert result["parent_comparison"]["m0_usable_delta"] == 1 / 3
        assert set(result["summaries"]) == {"base", "parent", "candidate"}
        _, published = resolve_adapter(
            academy, result["qualified"]["adapter_id"], RECIPE
        )
        assert published["source"]["identity"] == RUN
        # A sealed result cannot hide loss of the measured final evidence or a changed parent.
        path = (
            evidence
            / "final-qualification"
            / result["evidence_name"]
            / "generation"
            / "raw.jsonl"
        )
        original = path.read_bytes()
        path.unlink()
        with pytest.raises(FileNotFoundError):
            finalize()
        path.write_bytes(original)
        (
            academy / "adapters" / parent["adapter_id"] / "adapter_model.safetensors"
        ).write_text("changed")
        with pytest.raises(ValueError, match="experiment_initial_adapter_changed"):
            finalize()
        with pytest.raises(ValueError, match="experiment_initial_adapter_changed"):
            read_qualification(
                evidence, host.state, receipts, academy_root=academy, **pins
            )
    else:
        assert result["qualified"] is None
        assert [path.name for path in (academy / "adapters").glob("text-*")] == []


@pytest.mark.parametrize(
    "problem", ["manifest_parent", "catalog_parent", "generation_hash"]
)
def test_continuation_will_not_publish_incomplete_parent_provenance(tmp_path, problem):
    spec, academy, parent, host, pins = _continued_campaign(
        tmp_path, eligible_manifest=problem != "manifest_parent"
    )
    evidence = tmp_path / "evidence"
    receipts = {RUN: sync_run(host, host.state, RUN, evidence, LIMIT)}
    expected = "remote_text_final_parent_manifest_mismatch"
    if problem == "catalog_parent":
        (academy / "adapters" / parent["adapter_id"] / "adapter_config.json").unlink()
        expected = "experiment_initial_adapter_invalid"
    elif problem == "generation_hash":
        expected = "remote_text_final_generation_identity_mismatch"

    def evaluate(command, *args):
        assert problem == "generation_hash"
        _evaluate_fixture(command, *args, outcomes=[("bad", "good", "bad")] * 3)
        generation = Path(command[command.index("base") - 2])
        manifest = read_json(generation / "manifest.json")
        manifest["models"]["checkpoint-99999"]["adapter_model.safetensors"] = DEV
        atomic_json(generation / "manifest.json", manifest)

    with pytest.raises(ValueError, match=expected):
        qualify(
            evidence, host.state, receipts, academy, spec, evaluator=evaluate, **pins
        )
    assert not list((academy / "adapters").glob("text-*"))


def test_local_holdout_pins_precede_start_and_use_verified_campaign_export(tmp_path):
    spec, academy, _, host, pins = _continued_campaign(tmp_path)
    directory = academy / "campaigns" / CAMPAIGN
    directory.mkdir(parents=True)
    run = academy / "runs" / RUN
    run.parent.mkdir()
    host.directory.rename(run)
    atomic_json(directory / "state.json", {**host.state, "started_at": 1.0})
    with pytest.raises(ValueError, match="local_pins_required_before_start"):
        pin_local(academy, CAMPAIGN, **pins)
    atomic_json(
        directory / "state.json",
        {**host.state, "status": "planned", "started_at": None},
    )
    pin = pin_local(academy, CAMPAIGN, **pins)
    with pytest.raises(ValueError, match="campaign_not_finished"):
        collect_local(academy, CAMPAIGN)
    atomic_json(directory / "state.json", {**host.state, "started_at": 1.0})
    assert pin_local(academy, CAMPAIGN, **pins) == pin
    with pytest.raises(ValueError, match="local_pins_changed"):
        pin_local(academy, CAMPAIGN, **{**pins, "final_test_sha256": "0" * 64})
    evidence, state, receipts, captured = collect_local(academy, CAMPAIGN)
    assert evidence == academy / "local-text-qualification" / CAMPAIGN / "evidence"
    assert captured == pins
    assert receipts[RUN]["result_sha256"] == host.state["trials"][0]["result_sha256"]
    decision = qualify(
        evidence,
        state,
        receipts,
        academy,
        spec,
        source="local",
        evaluator=lambda *args: _evaluate_fixture(
            *args, outcomes=[("bad", "good", "bad")] * 3
        ),
        **captured,
    )
    assert decision["status"] == "passed"
    assert decision["binding"]["source"] == "local"
    assert collect_local(academy, CAMPAIGN)[2] == receipts
    host.state["plan"]["plan_sha256"] = "0" * 64
    atomic_json(directory / "state.json", {**host.state, "started_at": 1.0})
    with pytest.raises(ValueError, match="local_pins_changed"):
        collect_local(academy, CAMPAIGN)


def test_local_evidence_stops_streaming_after_fetch_deadline(tmp_path, monkeypatch):
    clock = iter((10.0, 10.5, 11.0))
    monkeypatch.setattr(remote_text_local, "monotonic", lambda: next(clock))

    def export(_campaign, campaign_id, run_id, stream):
        assert campaign_id == CAMPAIGN
        assert run_id == RUN
        assert stream.write(b"first") == 5
        stream.write(b"expired")

    monkeypatch.setattr(remote_text_local, "export_run", export)
    target = tmp_path / "evidence.tar"
    evidence = remote_text_local._LocalEvidence(Mock())
    with pytest.raises(TimeoutError, match="remote_text_evidence_fetch_timeout"):
        evidence.fetch(CAMPAIGN, RUN, target, LIMIT, timeout=1)
    assert target.read_bytes() == b"first"


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


@pytest.mark.parametrize("release_action", ["ok", "invalid-receipt", "timeout"])
def test_local_qualification_uses_api_owner_cleanup_and_releases_lease(
    tmp_path, monkeypatch, release_action
):
    module = remote_text_qualification
    host = module.RuntimeAdmission(tmp_path / "admission.sqlite3")
    host.claim_host()
    monkeypatch.setattr(host, "claim_offline_host", lambda: False)
    monkeypatch.setattr(module, "get_runtime_admission", lambda: host)
    monkeypatch.setattr(module.Worker, "_local_api_port", lambda: 8800)
    client = Mock()
    receipt = {"released": release_action == "ok", "training_lease_verified": True}
    active_cleanup = None

    def post(url, *, headers):
        nonlocal active_cleanup
        assert url == "http://127.0.0.1:8800/api/v1/system/models/release"
        capability = headers[worker_module.TRAINING_CLEANUP_HEADER]
        host.validate_training_cleanup(capability)
        if release_action == "timeout":
            active_cleanup = host.training_cleanup(capability)
            active_cleanup.__enter__()
            raise httpx.ReadTimeout("still releasing models")
        return Mock(json=lambda: receipt)

    client.post.side_effect = post

    def open_client(*, timeout, trust_env):
        assert timeout == 5
        assert trust_env is False
        return nullcontext(client)

    monkeypatch.setattr(worker_module.httpx, "Client", open_client)
    log = tmp_path / "evaluation.log"
    command = [sys.executable, "-c", "print('evaluated')"]

    if release_action == "ok":
        module._evaluate(command, log, 5, RUN, "fixture-model", shared_runtime=True)
        assert log.read_text().strip() == "evaluated"
        assert read_json(log.with_name("gpu-release.json")) == receipt
    else:
        with pytest.raises(ValueError, match="experiment_gpu_release_failed"):
            module._evaluate(command, log, 5, RUN, "fixture-model", shared_runtime=True)
        assert not log.exists()
    if release_action == "timeout":
        try:
            assert active_cleanup is not None
            assert host.snapshot()["owner"] == "academy-experiment"
            assert host.snapshot()["active_operations"] == 1
        finally:
            if active_cleanup is not None:
                active_cleanup.__exit__(None, None, None)
    client.post.assert_called_once()
    lease = host.acquire(owner="test", run_id="verify", engine="test", model="test")
    assert lease.release()
