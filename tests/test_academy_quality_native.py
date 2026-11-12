"""Read quality evidence from Academy reports and verify the local API boundary."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy_experiment_campaigns as routes
from venom_core.services.training_experiments.profiles import MODEL, digest, stable_hash
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
        "training_venv": "/opt/train",
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
    generation_seal = write(
        generation / "generation-seal.json",
        {
            "manifest.json": generation_hash,
            "unblind.json": mapping_hash,
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
