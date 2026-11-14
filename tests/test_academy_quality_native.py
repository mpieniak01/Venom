"""Read quality evidence from Academy reports and verify the local API boundary."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy_experiment_campaigns as routes
from venom_core.services.training_experiments.profiles import MODEL, digest, stable_hash
from venom_core.services.training_experiments.quality import QualityStore
from venom_core.services.training_experiments.quality_native import (
    evaluation_identity,
    get_record,
    native_record,
    profile_context,
)
from venom_core.services.training_experiments.service import ExperimentService


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return digest(path)


@pytest.fixture
def sealed_run(tmp_path):
    service = ExperimentService(tmp_path)
    run = service.run_dir("test-native")
    dev = tmp_path / "dev.jsonl"
    dev.write_text(json.dumps({"record_id": "a", "task": "init", "split": "dev"}))
    profile = {
        "label": "Pilot",
        "dataset": "Polish",
        "model": MODEL,
        "snapshot": "/models/pin",
        "training_venv": "trainer",
        "train": "train.jsonl",
        "dev": "dev.jsonl",
        "train_sha256": "a" * 64,
        "dev_sha256": digest(dev),
        "calibration_sha256": None,
    }
    write(tmp_path / "profiles/pilot.json", profile)
    manifest = {"profile": profile, "recipe": {"rank": 4}, "calibration": None}
    write(run / "manifest.json", manifest)
    write(
        run / "state.json", {"status": "succeeded", "profile_id": "pilot", "attempt": 1}
    )
    generation = run / "evaluation-1"
    gen_manifest = {
        "model_repo": MODEL,
        "data_sha256": profile["dev_sha256"],
        "snapshot_manifest_sha256": profile_context(service, "pilot", "manual")[
            "identity"
        ]["base_sha256"],
        "revision": "rev",
        "max_prompt_tokens": 4096,
        "max_new_tokens": 512,
        "seed": 42,
        "engine": {"torch": "example"},
        "template": "vendor",
        "generation_mode": "text",
        "do_sample": False,
        "enable_thinking": False,
    }
    generation_hash = write(generation / "manifest.json", gen_manifest)
    mapping_hash = write(
        generation / "unblind.json", {"a": {"A": "checkpoint-1", "B": "base"}}
    )
    raw_hash = write(generation / "raw.jsonl", {"text": "raw"})
    blind_hash = write(generation / "blind.jsonl", {"text": "blind"})
    generation_seal = write(
        generation / "generation-seal.json",
        {
            "manifest.json": generation_hash,
            "unblind.json": mapping_hash,
            "raw.jsonl": raw_hash,
            "blind.jsonl": blind_hash,
        },
    )
    judgment_hash = write(
        generation / "judgments.json",
        [
            {"record_id": "a", "label": "A", "critical_error": True},
            {"record_id": "a", "label": "B", "critical_error": False},
        ],
    )
    report = {
        "run_id": "test-native",
        "checkpoint": {"step": 1},
        "dev_sha256": profile["dev_sha256"],
        "manifest_sha256": stable_hash(manifest),
        "generation_sha256": generation_seal,
        "judgment_sha256": judgment_hash,
        "verdicts": {"candidate": {"a": {"usable": 0}}, "base": {"a": {"usable": 1}}},
    }
    result_hash = write(run / "result.json", report)
    write(run / "result-seal.json", {"result_sha256": result_hash})
    return service, gen_manifest


def test_sealed_result_preserves_paired_critical_evidence(sealed_run):
    service, generation = sealed_run
    row = get_record(service, "test-native")
    assert row["identity"] == evaluation_identity(generation, None)
    assert row["cases"]["a"] == {
        "category": "init",
        "base": {"usable": True, "critical": False},
        "candidate": {"usable": False, "critical": True},
    }
    assert row["source"]["sha256"] == digest(
        service.run_dir("test-native") / "result.json"
    )
    assert evaluation_identity(generation, "f" * 64) != row["identity"]


@pytest.mark.parametrize(
    "relative",
    [
        "result.json",
        "evaluation-1/judgments.json",
        "evaluation-1/manifest.json",
        "evaluation-1/unblind.json",
        "evaluation-1/generation-seal.json",
        "evaluation-1/raw.jsonl",
        "evaluation-1/blind.jsonl",
    ],
)
def test_native_result_fails_closed_if_bound_file_changes(sealed_run, relative):
    service, _ = sealed_run
    write(service.run_dir("test-native") / relative, {})
    with pytest.raises(ValueError, match="experiment_quality_evidence_changed"):
        native_record(service, "test-native")


def test_quality_routes_use_native_store_and_enforce_local_access(
    monkeypatch, sealed_run
):
    service, _ = sealed_run
    monkeypatch.setattr(routes, "experiment_service", lambda: service)
    from venom_core.api.routes import academy_experiments

    monkeypatch.setattr(academy_experiments.SETTINGS, "ENABLE_ACADEMY", True)
    app = FastAPI()
    app.include_router(routes.router)
    base = "/api/v1/academy/experiments/campaigns/quality"
    with TestClient(app, client=("127.0.0.1", 59000)) as client:
        assert client.get(base).json()["records"][0]["record_id"] == "test-native"
        response = client.get(f"{base}/test-native/analysis")
        assert response.status_code == 200, response.text
        assert response.json()["record"]["record_id"] == "test-native"
        assert client.get(f"{base}/missing/analysis").status_code == 404
    with TestClient(app, client=("192.0.2.42", 59000)) as client:
        assert client.get(base).status_code == 403


def test_imported_and_native_ids_do_not_shadow_each_other(sealed_run):
    service, _ = sealed_run
    observed = native_record(service, "test-native")
    copy = {key: value for key, value in observed.items() if key != "result_sha256"}
    copy["source"]["identity"] = "archived"
    QualityStore(service.root).import_record(copy)
    assert get_record(service, "test-native")["source"]["identity"] == "test-native"
    assert (
        get_record(service, "history:test-native")["source"]["identity"] == "archived"
    )
    assert {row["record_id"] for row in routes.list_records(service)["records"]} == {
        "test-native",
        "history:test-native",
    }
    analysis = routes.analyze_record(service, "history:test-native", "test-native")
    assert analysis["record"]["record_id"] == "history:test-native"
    assert analysis["reference_id"] == "test-native"


def test_sealed_run_is_visible_before_success_state_is_saved(sealed_run):
    service, _ = sealed_run
    write(
        service.run_dir("test-native") / "state.json",
        {
            "status": "awaiting_review",
            "profile_id": "pilot",
            "attempt": 1,
        },
    )
    assert native_record(service, "test-native")["cases"]["a"]["base"]["usable"]
    assert routes.list_records(service)["records"][0]["record_id"] == "test-native"


def test_profile_context_verifies_installed_runtime_metadata(sealed_run):
    service, _ = sealed_run
    with pytest.raises(ValueError, match="campaign_quality_runtime_unverified"):
        profile_context(service, "pilot", "manual", include_runtime=True)
    sites = service.root / "trainer/lib/python3.14/site-packages"
    for name in ("torch", "transformers", "peft"):
        metadata = sites / f"{name}-1.0.dist-info" / "METADATA"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(f"Name: {name}\nVersion: 1.0\n", encoding="utf-8")
    context = profile_context(service, "pilot", "manual", include_runtime=True)
    assert context["train_sha256"] == "a" * 64
    assert context["runtime"] == {
        "loss": "trainer_default",
        "evaluation_engine": {"torch": "1.0", "transformers": "1.0", "peft": "1.0"},
    }


@pytest.mark.parametrize("checkpoint_steps", [None, [1]])
def test_external_disposition_keeps_native_review_pending(sealed_run, checkpoint_steps):
    service, generation_manifest = sealed_run
    run_id = "test-native"
    run = service.run_dir(run_id)
    record = native_record(service, run_id)
    record.pop("result_sha256")
    record.update(record_id="external-evaluation", outcome="REVISE")
    record["source"]["kind"] = "historical"
    checkpoint_hash = "a" * 64
    generation = run / "evaluation-1"
    seal = json.loads((generation / "generation-seal.json").read_text())
    manifest = {
        **generation_manifest,
        "outputs": {
            name: value for name, value in seal.items() if name != "manifest.json"
        },
        "models": {"checkpoint-1": {"adapter_model.safetensors": checkpoint_hash}},
    }
    seal["manifest.json"] = write(generation / "manifest.json", manifest)
    write(generation / "generation-seal.json", seal)
    (run / "result-seal.json").unlink()
    write(
        run / "state.json",
        {
            "run_id": run_id,
            "profile_id": "pilot",
            "status": "awaiting_review",
            "checkpoint_step": 1,
            "checkpoint_sha256": checkpoint_hash,
            "attempt": 1,
            **({"checkpoint_steps": checkpoint_steps} if checkpoint_steps else {}),
        },
    )
    assert "external_review" not in service.status(run_id)
    record["reviewed_run"] = {
        "run_id": run_id,
        "checkpoint_sha256": checkpoint_hash,
        "generation_manifest_sha256": seal["manifest.json"],
    }
    QualityStore(service.root).import_record(record)

    status = service.list_runs()[0]
    assert status["status"] == "awaiting_review"
    assert status["actions"]["review"]
    assert status["external_review"] == {
        "record_id": "history:external-evaluation",
        "outcome": "REVISE",
    }
    write(generation / "raw.jsonl", {})
    assert "external_review" not in service.status(run_id)
