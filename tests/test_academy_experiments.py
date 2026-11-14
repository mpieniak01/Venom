"""Exercise the public Academy run path without GPU or a live judge."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from scripts.academy.omni_pl_chat_recipe import LANGUAGE_TARGET_MODULES
from venom_core.api.routes import academy_experiments as routes
from venom_core.services.gemma4_operator.profile import PINNED_REVISIONS
from venom_core.services.gemma4_operator.training import target_modules_for
from venom_core.services.remote_training.lifecycle import atomic_json, process_identity
from venom_core.services.runtime_admission import RuntimeAdmission
from venom_core.services.training_experiments import worker as worker_module
from venom_core.services.training_experiments.evidence import latest_checkpoint
from venom_core.services.training_experiments.profiles import (
    Profile,
    digest,
    recipe_for,
)
from venom_core.services.training_experiments.service import ExperimentService
from venom_core.services.training_experiments.worker import Worker
from venom_core.services.training_model_specs import model_training_specs


def write_rows(path: Path, data: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")


def test_model_specs_follow_trainers() -> None:
    omni, e4b, twelve_b = model_training_specs()
    assert omni["target_modules"] == list(LANGUAGE_TARGET_MODULES)
    assert set(omni["target_modules"]) >= {"w1", "w2", "w3"}
    assert omni["legacy_recipe_default"] == ["q_proj", "v_proj"]
    for gemma in (e4b, twelve_b):
        assert gemma["revision"] == PINNED_REVISIONS[gemma["model"]]
        assert gemma["target_modules"] == target_modules_for(gemma["model"])
    assert e4b["status"] == "trained_candidate_below_acceptance"
    assert twelve_b["status"] == "remote_gpu_smoke_required"


def test_model_specs_route(setup) -> None:
    _, client, *_ = setup
    response = client.get("/api/v1/academy/experiments/model-specs")
    assert response.status_code == 200
    assert [item["model"] for item in response.json()["models"]] == [
        item["model"] for item in model_training_specs()
    ]


def test_profile_requires_explicit_lora_scope() -> None:
    profile = Profile(
        label="test",
        dataset="test",
        snapshot="snapshot",
        training_venv="venv",
        train="train.jsonl",
        dev="dev.jsonl",
        train_sha256="a" * 64,
        dev_sha256="b" * 64,
    )
    with pytest.raises(ValueError, match="experiment_target_modules_required"):
        recipe_for(profile, None)
    assert recipe_for(profile, {"target_modules": ["w1", "w2", "w3"]})[
        "target_modules"
    ] == ["w1", "w2", "w3"]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "experiments"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    (root / "model").mkdir()
    (root / "runtime/bin").mkdir(parents=True)
    (root / "runtime/bin/python").touch()
    messages = [{"role": "user", "content": "Powiedz OK."}]
    train = {
        "record_id": "train-1",
        "group_id": "train-group",
        "split": "train",
        "messages": [*messages, {"role": "assistant", "content": "OK"}],
    }
    dev = {
        "record_id": "dev-1",
        "group_id": "dev-group",
        "split": "dev",
        "task": "chat",
        "messages": messages,
        "criteria": [
            {"id": "answer", "kind": "content", "description": "Odpowiedź potwierdza."}
        ],
    }
    write_rows(root / "train.jsonl", [train])
    write_rows(root / "dev.jsonl", [dev])
    profile = {
        "label": "Pinned smoke",
        "dataset": "Smoke",
        "snapshot": "model",
        "training_venv": "runtime",
        "train": "train.jsonl",
        "dev": "dev.jsonl",
        "train_sha256": digest(root / "train.jsonl"),
        "dev_sha256": digest(root / "dev.jsonl"),
        "recipe": {"steps": 4, "save_every": 2, "target_modules": ["q_proj", "v_proj"]},
    }
    atomic_json(profiles / "smoke.json", profile)
    launches = []

    def launcher(root, run_id, attempt):
        launches.append((root, run_id, attempt))
        return process_identity(os.getpid())

    svc = ExperimentService(root, launcher=launcher)
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(routes.SETTINGS, "ENABLE_ACADEMY", True)
    monkeypatch.setattr(routes, "experiment_service", lambda: svc)
    client = TestClient(app, client=("127.0.0.1", 1234))
    return svc, client, app, profile, train, dev, launches


def write_checkpoint(root: Path, step: int) -> Path:
    cp = root / "training" / f"checkpoint-{step}"
    cp.mkdir(parents=True)
    for name in CHECKPOINT_FILES:
        content = (
            json.dumps({"global_step": step}) if name == "trainer_state.json" else name
        )
        (cp / name).write_text(content, encoding="utf-8")
    atomic_json(
        cp / "hashes.json", {name: digest(cp / name) for name in CHECKPOINT_FILES}
    )
    return cp


def grade(label: str, good: bool) -> dict:
    return {
        "record_id": "dev-1",
        "label": label,
        "criteria": {"answer": good},
        "polish_ok": True,
        "natural_ok": True,
        "critical_error": not good,
        "reason": "reviewed",
    }


def fake_work(monkeypatch, service, dev, *, training: bool = True):
    def execute(worker, command, gpu_fd):
        destination = Path(command[4])
        if command[1].endswith("omni_pl_chat_p1.sh"):
            if command[6] == "preflight":
                destination.mkdir()
            elif training:
                write_checkpoint(worker.directory, 4)
            return
        destination.mkdir()
        answers = {
            "A": {"text": "OK", "finish": "stop", "error": None},
            "B": {"text": "Brak", "finish": "stop", "error": None},
        }
        write_rows(destination / "blind.jsonl", [{"case": dev, "answers": answers}])
        write_rows(destination / "raw.jsonl", [{"text": "generated"}])
        atomic_json(destination / "manifest.json", {"schema_version": 1})
        atomic_json(
            destination / "unblind.json",
            {"dev-1": {"A": command[-1].split("=")[0], "B": "base"}},
        )

    host = RuntimeAdmission(service.root / "host.sqlite3")
    monkeypatch.setattr(
        "venom_core.services.training_experiments.worker.get_runtime_admission",
        lambda: host,
    )
    monkeypatch.setattr(Worker, "prepare_gpu", lambda *args, **kwargs: None)
    monkeypatch.setattr(Worker, "execute", execute)
    monkeypatch.setattr(
        "venom_core.services.training_experiments.worker.validate_dev_cases",
        lambda cases: None,
    )


def test_academy_runs_and_seals_review(setup, monkeypatch):
    svc, client, _, profile, _, dev, launches = setup
    prefix = "/api/v1/academy/experiments"
    assert client.get(f"{prefix}/profiles").json()["profiles"][0]["id"] == "smoke"
    assert client.get(f"{prefix}/runs").json() == {"runs": []}
    payload = {"profile_id": "smoke", "run_id": "run-1"}
    start = client.post(f"{prefix}/runs", json=payload)
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "queued"
    assert client.post(f"{prefix}/runs", json=payload).json()["attempt"] == 1
    assert len(launches) == 1
    assert (
        client.post(
            f"{prefix}/runs", json={**payload, "recipe": {"rank": 8}}
        ).status_code
        == 409
    )
    fake_work(monkeypatch, svc, dev)
    Worker(svc, "run-1", 1).run()
    run_url = f"{prefix}/runs/run-1"
    view = client.get(run_url).json()
    assert view["status"] == "awaiting_review", view
    assert client.get(f"{run_url}/logs").json() == {"logs": ""}
    assert (
        client.get(f"{run_url}/review").json()["answers"][0]["answers"]["A"]["text"]
        == "OK"
    )
    assert client.get(f"{run_url}/report").status_code == 404
    assert (
        client.post(
            f"{run_url}/judgments", json={"judgments": [grade("A", True)]}
        ).status_code
        == 409
    )
    judgments = [grade("A", True), grade("B", False)]
    assert (
        client.post(f"{run_url}/judgments", json={"judgments": judgments}).json()[
            "status"
        ]
        == "succeeded"
    )
    result = client.get(f"{run_url}/report").json()
    assert result["summaries"]["candidate"]["total"]["usable"] == 1
    assert result["summaries"]["base"]["total"]["usable"] == 0
    assert result["cases"][0]["candidate"]["text"] == "OK"
    assert result["artifacts"][0]["available"] is True
    assert client.get(f"{run_url}/review").status_code == 409
    cp = svc.run_dir("run-1") / "training/checkpoint-4"
    (cp / "adapter_model.safetensors").unlink()
    assert client.get(f"{run_url}/report").json()["artifacts"][0]["available"] is False
    assert client.get(f"{prefix}/runs").json()["runs"][0]["status"] == "succeeded"


def test_stop_resume_retry_and_orphan(setup, monkeypatch):
    svc, client, _, _, _, dev, _ = setup
    fake_work(monkeypatch, svc, dev)
    svc.start("smoke", "run-2")
    cp = write_checkpoint(svc.run_dir("run-2"), 2)
    svc.stop("run-2")
    Worker(svc, "run-2", 1).run()
    assert svc.status("run-2")["status"] == "stopped"
    assert svc.status("run-2")["resume_available"]
    assert svc.resume("run-2")["attempt"] == 2
    (cp / "optimizer.pt").unlink()
    assert latest_checkpoint(cp.parent, resume=True) is None
    state = svc.store.read("run-2")
    state["supervisor"] = None
    svc._save(state)
    assert svc.status("run-2")["status"] == "failed"
    assert svc.evaluate("run-2")["attempt"] == 3
    Worker(svc, "run-2", 3).run()
    assert svc.status("run-2")["status"] == "awaiting_review"
    assert svc.stop("run-2")["status"] == "stopped"
    assert (
        client.post("/api/v1/academy/experiments/runs/run-2/resume").status_code == 409
    )


def test_data_profile_and_transport_guards(setup, monkeypatch):
    svc, client, app, profile, train, dev, launches = setup
    prefix = "/api/v1/academy/experiments"
    remote = TestClient(app, client=("192.0.2.1", 1234))
    assert remote.get(f"{prefix}/runs").status_code == 403
    monkeypatch.setattr(routes.SETTINGS, "ENABLE_ACADEMY", False)
    assert client.get(f"{prefix}/runs").status_code == 503
    monkeypatch.setattr(routes.SETTINGS, "ENABLE_ACADEMY", True)
    assert (
        client.post(
            f"{prefix}/runs", json={"profile_id": "smoke", "run_id": "../escape"}
        ).status_code
        == 422
    )
    assert svc.validate("smoke")["workload"]["updates"] == 4
    with pytest.raises(ValueError, match="profile_changed"):
        svc.start("smoke", "bad-identity", expected_identity="x")
    write_rows(svc.root / "dev.jsonl", [{**dev, "group_id": train["group_id"]}])
    with pytest.raises(ValueError, match="data_changed"):
        svc.start("smoke", "changed")
    profile["dev_sha256"] = digest(svc.root / "dev.jsonl")
    atomic_json(svc.root / "profiles/smoke.json", profile)
    with pytest.raises(ValueError, match="overlapping"):
        svc.validate("smoke")
    assert not launches


def test_qualified_deterministic_review_and_seal(setup, monkeypatch):
    svc, _, _, profile, _, dev, _ = setup
    path = svc.root / "profiles/smoke.calibration.json"
    atomic_json(
        path,
        {
            "schema_version": 1,
            "judge": "exact-v1",
            "dev_sha256": profile["dev_sha256"],
            "reviewer": "fixture",
            "cases": {
                "dev-1": {
                    "outputs": {"OK": grade("A", True)},
                    "fallback": grade("B", False),
                }
            },
        },
    )
    profile["calibration_sha256"] = digest(path)
    atomic_json(svc.root / "profiles/smoke.json", profile)
    assert svc.profiles()[0]["automatic_review"] is True
    fake_work(monkeypatch, svc, dev)
    svc.start("smoke", "automatic")
    Worker(svc, "automatic", 1).run()
    assert svc.status("automatic")["status"] == "succeeded"
    p = svc.run_dir("automatic") / "result.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="result_changed"):
        svc.report("automatic")


def test_shared_worker_admission_has_exclusive_lease(tmp_path):
    from venom_core.services.runtime_admission import (
        RuntimeAdmission,
        RuntimeAdmissionError,
    )

    database = tmp_path / "ledger.sqlite3"
    app = RuntimeAdmission(database)
    worker = RuntimeAdmission.for_training_worker(database)
    with app.operation(kind="generation"):
        with pytest.raises(RuntimeAdmissionError):
            worker.acquire(owner="training", run_id="r1", engine="omni", model="omni")
    lease = worker.acquire(owner="training", run_id="r1", engine="omni", model="omni")
    with pytest.raises(RuntimeAdmissionError):
        with app.operation(kind="generation"):
            pytest.fail("generation admitted while training owns the host")
    with lease.operation(kind="lifecycle", confirm_quiescent=lambda: True):
        assert worker.snapshot()["status"] == "owned"
    assert lease.release()
    assert app.snapshot()["status"] == "available"


def test_campaign_owns_retries_and_history_does_not_restore_weights(setup, tmp_path):
    svc, _, _, _, _, _, _ = setup
    svc.start("smoke", "owned", campaign_id="batch")
    assert svc.status("owned")["actions"]["stop"] is False
    with pytest.raises(ValueError, match="campaign_controls_run"):
        svc.stop("owned")
    assert svc.stop("owned", campaign_id="batch")["stop_requested"]
    old = tmp_path / "historic.json"
    atomic_json(
        old,
        {
            "selected": "checkpoint-62",
            "summaries": {
                "base": {"total": {"n": 4, "usable": 1}},
                "checkpoint-62": {"total": {"n": 4, "usable": 2}},
            },
            "verdicts": {"base": {}, "checkpoint-62": {}},
        },
    )
    assert svc.import_results("p6", old)["resume_available"] is False
    assert svc.import_results("p6", old)["status"] == "succeeded"
    assert svc.report("p6")["artifacts"][0] == {
        "kind": "adapter",
        "available": False,
        "step": 62,
    }


def test_worker_stops_before_model_load_when_release_fails(setup, monkeypatch):
    svc, _, _, _, _, dev, _ = setup
    fake_work(monkeypatch, svc, dev)
    host = RuntimeAdmission(svc.root / "host.sqlite3")

    def reject_release(worker, lease, *, offline):
        assert host.snapshot()["owner"] == "academy-experiment"
        raise ValueError("experiment_gpu_release_failed")

    monkeypatch.setattr(
        "venom_core.services.training_experiments.worker.get_runtime_admission",
        lambda: host,
    )
    monkeypatch.setattr(Worker, "prepare_gpu", reject_release)
    svc.start("smoke", "release-failed")
    Worker(svc, "release-failed", 1).run()
    assert svc.status("release-failed")["error"] == "experiment_gpu_release_failed"
    assert not (svc.run_dir("release-failed") / "training").exists()
    assert "owner" not in host.snapshot()


@pytest.mark.parametrize("verified", [True, False])
def test_local_api_must_verify_training_lease(setup, monkeypatch, verified):
    svc, _, _, _, _, _, _ = setup
    svc.start("smoke", "gpu-release")
    worker = Worker(svc, "gpu-release", 1)
    host = RuntimeAdmission(svc.root / "host.sqlite3")
    lease = host.acquire(
        owner="academy-experiment",
        run_id="gpu-release",
        engine="omni-training",
        model="omni",
    )
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("API_PROXY_TARGET", raising=False)
    monkeypatch.setattr(
        worker_module,
        "dotenv_values",
        lambda path: {"API_PROXY_TARGET": "http://127.0.0.1:8800"},
    )

    def respond(request):
        assert str(request.url) == "http://127.0.0.1:8800/api/v1/system/models/release"
        host.validate_training_cleanup(
            request.headers[worker_module.TRAINING_CLEANUP_HEADER]
        )
        receipt = {"released": True, "memory_before": {}, "memory_after": {}}
        if verified:
            receipt["training_lease_verified"] = True
        return httpx.Response(200, json=receipt)

    client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    monkeypatch.setattr(worker_module.httpx, "Client", lambda **kwargs: client)
    receipt_path = worker.directory / "gpu-release-1.json"
    if verified:
        worker.prepare_gpu(lease, offline=False)
        assert json.loads(receipt_path.read_text())["training_lease_verified"] is True
    else:
        with pytest.raises(ValueError, match="experiment_gpu_release_failed"):
            worker.prepare_gpu(lease, offline=False)
        assert not receipt_path.exists()
    assert lease.release()


def test_standalone_training_releases_under_the_lease(setup, monkeypatch):
    svc, _, _, _, _, _, _ = setup
    svc.start("smoke", "offline")
    worker = Worker(svc, "offline", 1)
    host = RuntimeAdmission(svc.root / "host.sqlite3")
    monkeypatch.setattr(worker_module, "probe_socket", lambda: FakeSocket(111))
    lease = host.acquire(
        owner="academy-experiment",
        run_id="offline",
        engine="omni-training",
        model="omni",
    )
    monkeypatch.setattr(worker_module, "LlmServerController", lambda settings: object())

    async def release(controller, *, training_capability):
        with host.training_cleanup(training_capability):
            return {"released": True, "training_lease_verified": True}

    monkeypatch.setattr(worker_module, "release_all_runtime_models", release)
    worker.prepare_gpu(lease, offline=True)
    assert (worker.directory / "gpu-release-1.json").exists()
    monkeypatch.setattr(worker_module, "probe_socket", lambda: FakeSocket(0))
    with pytest.raises(ValueError, match="experiment_gpu_release_failed"):
        worker.prepare_gpu(lease, offline=True)
    assert lease.release()


class FakeSocket:
    def __init__(self, result):
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def settimeout(self, timeout):
        pass

    def connect_ex(self, endpoint):
        return self.result


def install_fixture_adapter(root: Path, adapter_id: str = "fixture-adapter"):
    from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN

    directory = root / "adapters" / adapter_id
    directory.mkdir(parents=True)
    config_path = directory / "adapter_config.json"
    weights_path = directory / "adapter_model.safetensors"
    pin = json.loads(SNAPSHOT_PIN.read_text(encoding="utf-8"))
    atomic_json(
        config_path,
        {
            "base_model_name_or_path": pin["repo"],
            "bias": "none",
            "lora_alpha": 8,
            "lora_dropout": 0.0,
            "peft_type": "LORA",
            "r": 4,
            "target_modules": r"model\.language_model\..*\.(q_proj|v_proj)",
            "task_type": "CAUSAL_LM",
        },
    )
    weights_path.write_bytes(b"synthetic tensor fixture")
    entry = {
        "schema_version": 1,
        "adapter_id": adapter_id,
        "label": "Testowy adapter",
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_sha256": digest(SNAPSHOT_PIN),
        "config_sha256": digest(config_path),
        "weights_sha256": digest(weights_path),
        "source": {"identity": "fixture source", "sha256": "a" * 64},
    }
    atomic_json(directory / "adapter.json", entry)
    atomic_json(
        directory / "hashes.json",
        {
            config_path.name: entry["config_sha256"],
            weights_path.name: entry["weights_sha256"],
        },
    )
    return directory, entry


def adapter_campaign_plan(campaign_id="warm"):
    return {
        "campaign_id": campaign_id,
        "profile_id": "smoke",
        "variants": [{}, {"initial_adapter_id": "fixture-adapter"}],
        "budget": {
            "max_trials": 2,
            "max_updates": 8,
            "max_tokens": 8192,
            "max_seconds": 3600,
            "trial_seconds": 120,
            "max_retries": 0,
            "max_artifact_bytes": 2**30,
            "min_free_bytes": 0,
        },
        "retention": "discard_rejected",
    }


def test_adapter_catalog_and_fixed_campaign_plan_http(setup, monkeypatch, capsys):
    from scripts.academy.experiments import main as experiments_cli
    from venom_core.api.routes import academy_experiment_campaigns
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, client, app, _, _, _, launches = setup
    directory, entry = install_fixture_adapter(service.root)
    campaign = CampaignService(service, launch=lambda _: process_identity(os.getpid()))
    monkeypatch.setattr(
        academy_experiment_campaigns, "campaign_service", lambda: campaign
    )
    app.include_router(academy_experiment_campaigns.router)
    prefix = "/api/v1/academy/experiments"
    assert client.get(f"{prefix}/adapters").json() == {"adapters": [entry]}
    experiments_cli(["--root", str(service.root), "adapters"])
    assert json.loads(capsys.readouterr().out) == [entry]

    spec = adapter_campaign_plan()
    response = client.post(f"{prefix}/campaigns/plan", json=spec)
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]
    fresh, warm = plan["variants"]
    assert "initial_adapter" not in fresh
    assert fresh["recipe"] == warm["recipe"]
    assert warm["initial_adapter"] == entry
    assert client.get(f"{prefix}/campaigns/warm/report").json()["plan"] == plan
    assert client.post(f"{prefix}/campaigns/plan", json=spec).json()["plan"] == plan

    entry["source"]["sha256"] = "b" * 64
    atomic_json(directory / "adapter.json", entry)
    denied = client.post(
        f"{prefix}/campaigns/warm/start", json={"plan_sha256": plan["plan_sha256"]}
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["detail"]["code"] == "experiment_initial_adapter_changed"
    assert campaign.status("warm")["status"] == "planned"
    assert not launches

    preview = campaign.validate(CampaignSpec.model_validate(spec))
    assert preview["plan_sha256"] != plan["plan_sha256"]
    assert preview["variants"][1]["initial_adapter"] == entry

    spec["campaign_id"] = "warm-after-change"
    spec["variants"].reverse()
    accepted = client.post(f"{prefix}/campaigns/plan", json=spec).json()["plan"]
    assert (
        client.post(
            f"{prefix}/campaigns/warm-after-change/start",
            json={"plan_sha256": accepted["plan_sha256"]},
        ).status_code
        == 200
    )
    campaign.advance("warm-after-change")
    campaign.advance("warm-after-change")
    warm_id = accepted["variants"][0]["run_id"]
    assert launches == [(service.root, warm_id, 1)]
    assert client.get(f"{prefix}/runs/{warm_id}").json()["initial_adapter"] == entry


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("adapter_model.safetensors", "experiment_initial_adapter_changed"),
        ("adapter_config.json", "experiment_initial_adapter_changed"),
        ("hashes.json", "experiment_initial_adapter_changed"),
        ("base", "experiment_initial_adapter_incompatible"),
        ("snapshot_profile", "campaign_profile_changed"),
        ("symlink", "experiment_initial_adapter_invalid"),
    ],
)
def test_catalog_mutation_rejects_activation(setup, name, expected, tmp_path):
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, _, _, profile, _, _, launches = setup
    directory, entry = install_fixture_adapter(service.root)
    campaign = CampaignService(service)
    state = campaign.plan(CampaignSpec.model_validate(adapter_campaign_plan()))
    if name == "snapshot_profile":
        atomic_json(
            service.root / "profiles" / "smoke.json",
            {**profile, "snapshot": "different-model"},
        )
    elif name == "base":
        atomic_json(directory / "adapter.json", {**entry, "revision": "b" * 40})
    elif name == "symlink":
        config = directory / "adapter_config.json"
        link_target = tmp_path / "outside-config.json"
        config.rename(link_target)
        config.symlink_to(link_target)
    else:
        (directory / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match=expected):
        campaign.start("warm", state["plan"]["plan_sha256"])
    assert campaign.status("warm")["status"] == "planned"
    assert service.adapters() == ([entry] if name == "snapshot_profile" else [])
    assert not launches


def test_catalog_rejects_path_id_missing_entry_and_wrong_modules(setup):
    service, _, _, _, _, _, _ = setup
    install_fixture_adapter(service.root)
    for overrides, error in (
        ({"initial_adapter_id": "../fixture-adapter"}, "invalid"),
        ({"initial_adapter_id": None}, "invalid"),
        ({"initial_adapter_id": "unknown"}, "missing"),
        (
            {"initial_adapter_id": "fixture-adapter", "target_modules": ["q_proj"]},
            "incompatible",
        ),
    ):
        with pytest.raises(ValueError, match=f"experiment_initial_adapter_{error}"):
            service.validate("smoke", overrides)


def test_warm_start_and_resume_use_separate_training_state(setup, monkeypatch):
    from venom_core.services.training_experiments.adapters import runner_identity

    service, client, _, _, _, dev, _ = setup
    directory, entry = install_fixture_adapter(service.root)
    prefix = "/api/v1/academy/experiments"
    response = client.post(
        f"{prefix}/runs",
        json={
            "profile_id": "smoke",
            "run_id": "warm",
            "recipe": {"initial_adapter_id": entry["adapter_id"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["initial_adapter"] == entry
    assert "initial_adapter_id" not in response.json()["recipe"]
    assert service._manifest("warm")["initial_adapter"] == entry
    path = service.run_dir("warm")
    handoff = runner_identity(entry)

    fake_work(monkeypatch, service, dev)
    original_execute = Worker.execute
    commands = []

    def execute(worker, command, gpu_fd):
        if command[1].endswith("omni_pl_chat_p1.sh"):
            target = Path(command[4])
            mode = command[6]
            assert Path(command[8]) == directory
            assert json.loads(Path(command[9]).read_text(encoding="utf-8")) == handoff
            commands.append((mode, Path(command[9]).name))
            if mode == "preflight":
                target.mkdir()
                atomic_json(target / "preflight.json", {"initial_adapter": handoff})
            elif mode == "control":
                write_checkpoint(path, 2)
                raise TimeoutError("experiment_time_limit")
            elif mode == "resume":
                assert (target / "checkpoint-2" / "optimizer.pt").exists()
                write_checkpoint(path, 4)
                atomic_json(
                    target / "resume.json",
                    {
                        "initial_adapter": handoff,
                        "state_source": "checkpoint",
                        "fresh_optimizer": False,
                        "loaded_tensors": 8,
                    },
                )
        else:
            original_execute(worker, command, gpu_fd)

    monkeypatch.setattr(Worker, "execute", execute)
    Worker(service, "warm", 1).run()
    assert service.status("warm")["status"] == "timed_out"
    assert service.status("warm")["resume_available"]
    response = client.post(f"{prefix}/runs/warm/resume")
    assert response.status_code == 200, response.text
    assert response.json()["initial_adapter"] == entry
    Worker(service, "warm", 2).run()
    assert service.status("warm")["status"] == "awaiting_review"
    assert commands == [
        ("preflight", "initial-adapter-1.json"),
        ("control", "initial-adapter-1.json"),
        ("preflight", "initial-adapter-2.json"),
        ("resume", "initial-adapter-2.json"),
    ]
    assert (
        service.submit("warm", [grade("A", True), grade("B", False)])["initial_adapter"]
        == entry
    )
    assert service.report("warm")["initial_adapter"] == entry
    assert digest(directory / "adapter_model.safetensors") == entry["weights_sha256"]


def test_worker_rejects_invalid_warm_resume_receipt(setup):
    from venom_core.services.training_experiments.adapters import runner_identity

    service, _, _, _, _, _, _ = setup
    directory, entry = install_fixture_adapter(service.root)
    receipt = directory / "fixture-train-receipt.json"
    atomic_json(
        receipt,
        {
            "initial_adapter": runner_identity(entry),
            "state_source": "initial_adapter",
            "fresh_optimizer": True,
            "loaded_tensors": 8,
        },
    )
    Worker._verify_initial_adapter_receipt(receipt, entry, "control")
    with pytest.raises(ValueError, match="experiment_initial_adapter_receipt_invalid"):
        Worker._verify_initial_adapter_receipt(receipt, entry, "resume")


def test_retention_prunes_rejected_warm_checkpoint_and_preserves_catalog(
    setup, monkeypatch
):
    from venom_core.services.training_experiments.adapters import runner_identity
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, _, _, _, _, dev, _ = setup
    source, entry = install_fixture_adapter(service.root)
    before = {path.name: digest(path) for path in source.iterdir()}
    campaign = CampaignService(service, launch=lambda _: process_identity(os.getpid()))
    spec = adapter_campaign_plan()
    spec["variants"].reverse()
    state = campaign.plan(CampaignSpec.model_validate(spec))
    variants = state["plan"]["variants"]
    warm_run, fresh_run = [row["run_id"] for row in variants]
    campaign.start("warm", state["plan"]["plan_sha256"])

    fake_work(monkeypatch, service, dev)
    original_execute = Worker.execute

    def execute(worker, command, gpu_fd):
        original_execute(worker, command, gpu_fd)
        if worker.run_id != warm_run or not command[1].endswith("omni_pl_chat_p1.sh"):
            return
        target = Path(command[4])
        receipt = {"initial_adapter": runner_identity(entry)}
        if command[6] == "preflight":
            atomic_json(target / "preflight.json", receipt)
        else:
            atomic_json(
                target / "control.json",
                {
                    **receipt,
                    "state_source": "initial_adapter",
                    "fresh_optimizer": True,
                    "loaded_tensors": 8,
                },
            )

    monkeypatch.setattr(Worker, "execute", execute)
    for run_id, candidate_good in ((warm_run, False), (fresh_run, True)):
        campaign.advance("warm")
        campaign.advance("warm")
        assert service.status(run_id)["status"] == "queued"
        Worker(service, run_id, 1).run()
        assert campaign.advance("warm")["status"] == "awaiting_review"
        service.submit(
            run_id, [grade("A", candidate_good), grade("B", not candidate_good)]
        )
        state = campaign.advance("warm")

    assert state["status"] == "succeeded"
    assert state["selected_run_id"] == fresh_run
    assert state["retention_receipt"]["removed_bytes"] > 0
    warm_report = service.report(warm_run)
    assert warm_report["artifacts"][0]["available"] is False
    assert warm_report["initial_adapter"] == entry
    assert service.report(fresh_run)["artifacts"][0]["available"] is True
    assert {path.name: digest(path) for path in source.iterdir()} == before
    assert service.adapters() == [entry]


@pytest.fixture
def audited_profile(setup, monkeypatch):
    from venom_core.services.training_experiments import data_audit

    service, _, _, profile, train, _, _ = setup
    root = service.root
    files = {
        "chat_template.jinja": "template_sha256",
        "tokenizer.json": "tokenizer_sha256",
        "tokenizer_config.json": "tokenizer_config_sha256",
        "config.json": "model_config_sha256",
    }
    pin_path = root / "fixture-snapshot-pin.json"
    for name in files:
        (root / "model" / name).write_text(name, encoding="utf-8")
    pin = {
        "repo": "LiquidAI/LFM3-Omni-2B",
        "revision": "a" * 40,
        "files": {name: {"sha256": digest(root / "model" / name)} for name in files},
    }
    atomic_json(pin_path, pin)
    monkeypatch.setattr(data_audit, "SNAPSHOT_PIN", pin_path)

    versions = {"transformers": "5.22.2", "tokenizers": "0.22"}
    site = root / "runtime" / "lib" / "python3.14" / "site-packages"
    for name, version in versions.items():
        info = site / f"{name}-{version}.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")

    taxonomy_path = root / "profiles" / "smoke.taxonomy.json"
    report_path = root / "profiles" / "smoke.data-audit.json"
    taxonomy = {
        "schema_version": 1,
        "records": {train["record_id"]: {"group": "replay", "skill": "state_add"}},
    }
    counts = {
        "records": 1,
        "supervised_tokens": 3,
        "input_tokens": 12,
        "max_input_tokens": 12,
        "max_supervised_tokens": 3,
    }
    groups = {"replay": counts, "fresh": dict.fromkeys(counts, 0)}
    report = {
        "schema_version": 1,
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_sha256": digest(pin_path),
        "train_sha256": profile["train_sha256"],
        "dev_sha256": profile["dev_sha256"],
        "tokenization": {
            **versions,
            "max_tokens": 1024,
            **{field: pin["files"][name]["sha256"] for name, field in files.items()},
        },
        "totals": counts,
        "groups": groups,
        "skills": {"state_add": groups},
        "leakage": {
            "normalization": "nfkc_casefold_whitespace_v1",
            "supervised_prefix_matches": 0,
            "final_user_matches": 0,
            "duplicate_train_records": 0,
        },
    }
    policy = {
        "groups": {"replay": {"min_supervised_tokens": 3}},
        "skills": {"state_add": {"replay": {"min_records": 1}}},
    }

    def seal():
        atomic_json(taxonomy_path, taxonomy)
        report["taxonomy_sha256"] = digest(taxonomy_path)
        atomic_json(report_path, report)
        atomic_json(
            root / "profiles" / "smoke.json",
            {
                **profile,
                "data_audit": {
                    "report_sha256": digest(report_path),
                    "taxonomy_sha256": digest(taxonomy_path),
                    "policy": policy,
                },
            },
        )

    seal()
    return report, report_path, taxonomy, taxonomy_path, policy, seal


def revised_audit_spec():
    spec = adapter_campaign_plan()
    spec["campaign_id"] = "audit"
    spec["variants"] = [{}, {"rank": 8}]
    return spec


def test_audit_legacy_hashes_and_http_campaign_acceptance(
    setup, audited_profile, monkeypatch, capsys
):
    from scripts.academy.experiments import main as experiments_cli
    from venom_core.api.routes import academy_experiment_campaigns
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, client, app, profile, _, _, _ = setup
    _, _, _, _, _, seal = audited_profile
    campaign = CampaignService(service, launch=lambda _: process_identity(os.getpid()))
    spec = revised_audit_spec()
    monkeypatch.setattr(
        academy_experiment_campaigns, "campaign_service", lambda: campaign
    )
    app.include_router(academy_experiment_campaigns.router)
    prefix = "/api/v1/academy/experiments"

    plan = client.post(f"{prefix}/campaigns/plan", json=spec).json()["plan"]
    assert plan["data_audit"]["status"] == "passed"
    assert "data_audit" not in plan["variants"][0]
    assert (
        client.get(f"{prefix}/profiles").json()["profiles"][0]["data_audit"]
        == plan["data_audit"]
    )
    experiments_cli(["--root", str(service.root), "audit", "smoke"])
    assert json.loads(capsys.readouterr().out) == plan["data_audit"]
    assert client.get(f"{prefix}/campaigns/audit/report").json()["plan"] == plan

    approval = {"plan_sha256": plan["plan_sha256"]}
    assert (
        client.post(f"{prefix}/campaigns/audit/start", json=approval).status_code == 200
    )
    campaign.advance("audit")
    campaign.advance("audit")
    run = service.status(plan["variants"][0]["run_id"])
    assert run["data_audit"] == plan["data_audit"]
    assert service._manifest(run["run_id"])["data_audit"] == plan["data_audit"]

    atomic_json(service.root / "profiles" / "smoke.json", profile)
    legacy = campaign.validate(CampaignSpec.model_validate(spec))
    assert "data_audit" not in legacy
    assert legacy["plan_sha256"] != plan["plan_sha256"]
    legacy_run = service.start("smoke", "legacy-run")
    assert "data_audit" not in legacy_run
    assert "data_audit" not in service._manifest("legacy-run")["profile"]
    assert service.start("smoke", "legacy-run")["attempt"] == 1
    seal()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "missing"),
        ("payload", "changed"),
        ("taxonomy", "changed"),
        ("train", "changed"),
        ("dev", "changed"),
        ("snapshot", "incompatible"),
        ("runtime", "incompatible"),
    ],
)
def test_pinned_data_audit_revalidated_before_activation(
    setup, audited_profile, mutation, reason
):
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, _, _, _, _, _, launches = setup
    _, report_path, _, taxonomy_path, _, _ = audited_profile
    campaign = CampaignService(service)
    planned = campaign.plan(CampaignSpec.model_validate(revised_audit_spec()))
    targets = {
        "payload": report_path,
        "taxonomy": taxonomy_path,
        "train": service.root / "train.jsonl",
        "dev": service.root / "dev.jsonl",
        "snapshot": service.root / "model/tokenizer.json",
        "runtime": service.root
        / "runtime/lib/python3.14/site-packages/tokenizers-0.22.dist-info/METADATA",
    }
    if mutation == "missing":
        report_path.unlink()
    else:
        payload = b"changed"
        if mutation == "runtime":
            payload = b"Name: tokenizers\nVersion: 1.0\n"
        targets[mutation].write_bytes(payload)
    with pytest.raises(ValueError, match=f"^experiment_data_audit_{reason}$"):
        campaign.start("audit", planned["plan"]["plan_sha256"])
    assert not launches
    assert campaign.status("audit")["status"] == "planned"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("totals", "invalid"),
        ("taxonomy", "invalid"),
        ("duplicate_keys", "invalid"),
        ("skill_totals", "invalid"),
        ("missing_skill", "invalid"),
        ("leakage", "leakage"),
        ("duplicates", "leakage"),
        ("threshold", "threshold"),
        ("provenance", "incompatible"),
        ("max_tokens", "incompatible"),
    ],
)
def test_audit_profile_remains_visible_when_planning_is_blocked(
    setup, audited_profile, mutation, reason
):
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    service, client, _, _, _, _, launches = setup
    report, report_path, taxonomy, taxonomy_path, policy, seal = audited_profile
    spec = revised_audit_spec()
    if mutation == "totals":
        report["totals"] = {
            **report["totals"],
            "input_tokens": 13,
            "max_input_tokens": 13,
        }
    elif mutation == "taxonomy":
        taxonomy["records"]["train-1"]["group"] = "fresh"
    elif mutation == "skill_totals":
        counts = dict(report["totals"], records=2, supervised_tokens=5)
        report["skills"]["state_add"] = {**report["groups"], "replay": counts}
    elif mutation == "missing_skill":
        report["skills"]["other"] = report["skills"].pop("state_add")
    elif mutation == "leakage":
        report["leakage"]["final_user_matches"] = 1
    elif mutation == "duplicates":
        report["leakage"]["duplicate_train_records"] = 1
    elif mutation == "threshold":
        policy["skills"]["state_sub"] = {"replay": {"min_records": 1}}
    elif mutation == "provenance":
        report["revision"] = "b" * 40
    elif mutation == "max_tokens":
        spec["variants"][1]["max_tokens"] = 2048
    seal()
    if mutation == "duplicate_keys":
        profile_path = service.root / "profiles/smoke.json"
        published = json.loads(profile_path.read_text(encoding="utf-8"))
        taxonomy_path.write_text(
            '{"schema_version": 1, "records": {"train-1": {"group": "fresh", '
            '"group": "replay", "skill": "state_add"}}}',
            encoding="utf-8",
        )
        published["data_audit"]["taxonomy_sha256"] = digest(taxonomy_path)
        report["taxonomy_sha256"] = digest(taxonomy_path)
        atomic_json(report_path, report)
        published["data_audit"]["report_sha256"] = digest(report_path)
        atomic_json(profile_path, published)
    error = f"experiment_data_audit_{reason}"
    summary = client.get("/api/v1/academy/experiments/profiles").json()["profiles"][0][
        "data_audit"
    ]
    if mutation != "max_tokens":
        assert summary["status"] == "blocked"
        assert summary["error"] == error
    else:
        assert summary["status"] == "passed"
    if mutation == "threshold":
        assert summary["violations"] == [
            {
                "group": "replay",
                "skill": "state_sub",
                "metric": "records",
                "actual": 0,
                "minimum": 1,
            }
        ]
    campaign = CampaignService(service)
    candidate = CampaignSpec.model_validate(spec)
    with pytest.raises(ValueError, match=error):
        campaign.plan(candidate)
    assert not launches


@pytest.mark.parametrize("mismatch", [False, True])
def test_run_reconciles_audit_with_real_preflight_receipt_before_training(
    setup, audited_profile, monkeypatch, mismatch
):
    service, _, _, _, _, dev, _ = setup
    report, _, _, _, _, _ = audited_profile
    start = service.start("smoke", "audit-run")
    assert start["data_audit"]["report"] == report

    fake_work(monkeypatch, service, dev)
    original_execute = Worker.execute
    commands = []

    def execute(worker, command, gpu_fd):
        commands.append(command[6])
        original_execute(worker, command, gpu_fd)
        if command[6] == "preflight":
            receipt = {**report["totals"], "train_sha256": report["train_sha256"]}
            if mismatch:
                receipt["supervised_tokens"] += 1
            atomic_json(Path(command[4]) / "preflight.json", receipt)

    monkeypatch.setattr(Worker, "execute", execute)
    Worker(service, "audit-run", 1).run()
    result = service.status("audit-run")
    if mismatch:
        assert result["status"] == "failed"
        assert result["error"] == "experiment_data_audit_incompatible"
        assert commands == ["preflight"]
    else:
        assert result["status"] == "awaiting_review"
        assert commands[:2] == ["preflight", "control"]
        service.submit("audit-run", [grade("A", True), grade("B", False)])
        assert service.report("audit-run")["data_audit"] == start["data_audit"]


@pytest.fixture
def checkpoint_campaign(setup, monkeypatch):
    from scripts.academy.omni_pl_chat_evaluate import (
        _evaluation_manifest,
        blind_mapping,
    )
    from venom_core.services.training_experiments import quality_native
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec
    from venom_core.services.training_experiments.checkpoint_evaluation import (
        inspect_steps,
    )
    from venom_core.services.training_experiments.profiles import read_json

    service, client, _, profile, _, dev, _ = setup
    versions = dict.fromkeys(("torch", "transformers", "peft"), "test")
    monkeypatch.setattr(
        quality_native,
        "_profile_runtime",
        lambda _: {
            "evaluation_engine": versions,
            "loss": "trainer_default",
        },
    )
    monkeypatch.setattr(
        "scripts.academy.omni_pl_chat_evaluate.version", versions.__getitem__
    )
    campaign = CampaignService(service, launch=lambda _: process_identity(os.getpid()))
    spec = adapter_campaign_plan("steps")
    spec["variants"] = [{}]
    spec["checkpoint_steps"] = [2, 4]
    spec["budget"]["max_retries"] = 1
    spec["quality_policy"] = {"no_new_critical": True}
    spec["selection"] = {"min_usable_delta": 0.1}
    frozen = CampaignSpec.model_validate(spec)
    plan = campaign.plan(frozen)["plan"]
    run_id = plan["variants"][0]["run_id"]
    commands = []
    controls = {"generation_error": False}

    fake_work(monkeypatch, service, dev)

    def execute(worker, command, gpu_fd):
        output = Path(command[4])
        output.mkdir()
        if command[1].endswith("omni_pl_chat_p1.sh"):
            mode = command[6]
            commands.append(mode)
            if mode == "control":
                for step in (2, 4):
                    cp = write_checkpoint(worker.directory, step)
                    weights = cp / "adapter_model.safetensors"
                    weights.write_text(f"step-{step}")
                    hashes = read_json(cp / "hashes.json")
                    hashes[weights.name] = digest(weights)
                    atomic_json(cp / "hashes.json", hashes)
            return
        commands.append("evaluate")
        assert command[6:8] == ["--resume-partial", "base"]
        assert [item.split("=")[0] for item in command[8:]] == [
            "checkpoint-2",
            "checkpoint-4",
        ]
        if controls.pop("generation_error", False):
            raise RuntimeError("experiment_child_failed")
        inputs = inspect_steps(worker.directory / "training", [2, 4])
        tags = ["base", *inputs]
        mapping = blind_mapping([dev], tags)
        raw = [
            {
                "case": "dev-1",
                "model": tag,
                "label": label,
                "response": {"text": tag, "finish": "stop", "error": None},
            }
            for label, tag in mapping["dev-1"].items()
        ]
        answers = {row["label"]: row["response"] for row in raw}
        write_rows(output / "raw.jsonl", raw)
        write_rows(output / "blind.jsonl", [{"case": dev, "answers": answers}])
        atomic_json(output / "unblind.json", mapping)
        manifest = _evaluation_manifest(
            read_json(quality_native.SNAPSHOT_PIN), profile["dev_sha256"], [dev], inputs
        )
        outputs = {
            name: digest(output / name)
            for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
        }
        atomic_json(
            output / "manifest.json",
            {
                **manifest,
                "generation_identity_sha256": "a" * 64,
                "outputs": outputs,
            },
        )

    monkeypatch.setattr(Worker, "execute", execute)
    return campaign, frozen, plan, run_id, commands, controls, service, client


def _start_checkpoint_test(campaign, plan):
    campaign.start("steps", plan["plan_sha256"])
    campaign.advance("steps")
    campaign.advance("steps")


def _review_checkpoint_test(client, run_id, step, candidate_good):
    from scripts.academy.omni_pl_chat_evaluate import blind_mapping

    prefix = f"/api/v1/academy/experiments/runs/{run_id}"
    bundle = client.get(prefix + "/review").json()
    assert bundle["checkpoint_step"] == step
    mapping = blind_mapping(bundle["cases"], ["base", f"checkpoint-{step}"])["dev-1"]
    grades = [
        grade(label, tag != "base" and candidate_good) for label, tag in mapping.items()
    ]
    # Base judgments are identical across steps. Critical errors can still be new on
    # the candidate independently of the base's usability.
    for item in grades:
        item["critical_error"] = False
    submission = {"checkpoint_step": step, "judgments": grades}
    stale = client.post(
        prefix + "/judgments", json={**submission, "checkpoint_step": 1}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "experiment_checkpoint_review_changed"
    response = client.post(prefix + "/judgments", json=submission)
    assert response.status_code == 200, response.text
    assert client.post(prefix + "/judgments", json=submission).status_code == 409


@pytest.mark.parametrize("qualifying", [True, False])
def test_checkpoint_campaign_retries_generation_and_ranks_only_qualified_steps(
    checkpoint_campaign, qualifying
):
    from venom_core.services.training_experiments.quality_history import list_records
    from venom_core.services.training_experiments.quality_native import get_record

    campaign, _, plan, run_id, commands, controls, service, client = checkpoint_campaign
    _start_checkpoint_test(campaign, plan)
    controls["generation_error"] = True
    Worker(service, run_id, 1).run()
    status = service.status(run_id)
    assert status["status"] == "failed"
    assert status["evaluation_available"] is True
    retry = campaign.advance("steps")
    assert retry["trials"][0]["intent"]["action"] == "evaluate"
    campaign.advance("steps")
    Worker(service, run_id, 2).run()
    assert commands == ["preflight", "control", "evaluate", "evaluate"]
    assert campaign.advance("steps")["status"] == "awaiting_review"
    assert service.status(run_id)["review_checkpoint_step"] == 2

    _review_checkpoint_test(client, run_id, 2, qualifying)
    assert service.status(run_id)["review_checkpoint_step"] == 4
    assert service.checkpoint_report(run_id, 2)[0]["checkpoint"]["step"] == 2
    assert campaign.advance("steps")["selected_run_id"] is None
    _review_checkpoint_test(client, run_id, 4, False)
    state = campaign.advance("steps")
    assert state["status"] == "succeeded"
    assert state["selected_checkpoint_step"] == (2 if qualifying else None)
    assert state["selected_run_id"] == (run_id if qualifying else None)
    assert state["used_updates"] == 4
    assert state["retries"] == 1
    assert [
        item["step"] for item in service.report(run_id)["checkpoint_evaluations"]
    ] == [2, 4]
    totals = campaign.evaluations(state)[run_id]
    expected_step = 2 if qualifying else 4
    assert totals["step"] == expected_step
    assert [entry["step"] for entry in totals["checkpoints"]] == [2, 4]
    assert campaign.retention_plan("steps")["files"] == []
    assert (
        service.run_dir(run_id) / "training/checkpoint-2/adapter_model.safetensors"
    ).is_file()
    records = list_records(service)["records"]
    assert [record["record_id"] for record in records] == [
        f"checkpoint:{run_id}:2",
        f"checkpoint:{run_id}:4",
    ]
    assert (
        get_record(service, f"checkpoint:{run_id}:2")["source"]["identity"]
        == f"checkpoint:{run_id}:2"
    )
    with pytest.raises(ValueError, match="experiment_checkpoint_step_required"):
        get_record(service, run_id)


def test_missing_checkpoint_report_blocks_candidate(checkpoint_campaign):
    campaign, _, plan, run_id, _, _, service, client = checkpoint_campaign
    _start_checkpoint_test(campaign, plan)
    Worker(service, run_id, 1).run()
    _review_checkpoint_test(client, run_id, 2, True)
    _review_checkpoint_test(client, run_id, 4, False)
    source = service.run_dir(run_id) / "checkpoint-evaluations/4/result.json"
    source.unlink()
    state = campaign.advance("steps")
    assert state["status"] == "blocked"
    assert state["selected_run_id"] is None
    assert state["selected_checkpoint_step"] is None


@pytest.mark.parametrize("steps", [[4, 2], [2, 2], [1, 2, 3, 4, 5]])
def test_checkpoint_campaign_rejects_invalid_step_list(checkpoint_campaign, steps):
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    _, spec, _, _, _, _, _, _ = checkpoint_campaign
    values = {**spec.model_dump(), "checkpoint_steps": steps}
    with pytest.raises(ValueError):
        CampaignSpec.model_validate(values)


@pytest.mark.parametrize("steps", [[1, 4], [2, 6]])
def test_checkpoint_campaign_rejects_steps_outside_save_schedule(
    checkpoint_campaign, steps
):
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    campaign, spec, _, _, _, _, _, _ = checkpoint_campaign
    candidate = CampaignSpec.model_validate(
        {**spec.model_dump(), "checkpoint_steps": steps}
    )
    with pytest.raises(ValueError, match="campaign_checkpoint_steps_invalid"):
        campaign.validate(candidate)


def test_checkpoint_review_rejects_conflicting_baseline_flags(checkpoint_campaign):
    from scripts.academy.omni_pl_chat_evaluate import blind_mapping

    campaign, _, plan, run_id, _, _, service, client = checkpoint_campaign
    _start_checkpoint_test(campaign, plan)
    Worker(service, run_id, 1).run()
    _review_checkpoint_test(client, run_id, 2, True)
    prefix = f"/api/v1/academy/experiments/runs/{run_id}"
    bundle = client.get(prefix + "/review").json()
    mapping = blind_mapping(bundle["cases"], ["base", "checkpoint-4"])["dev-1"]
    grades = [grade(label, True) for label in mapping]
    response = client.post(
        prefix + "/judgments", json={"checkpoint_step": 4, "judgments": grades}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "experiment_checkpoint_baseline_changed"
    assert service.status(run_id)["review_checkpoint_step"] == 4
    _review_checkpoint_test(client, run_id, 4, False)


def test_checkpoint_campaign_revalidates_installed_generation_protocol(
    checkpoint_campaign, monkeypatch
):
    from venom_core.services.training_experiments import quality_native

    campaign, _, plan, _, _, _, _, _ = checkpoint_campaign
    monkeypatch.setattr(
        quality_native,
        "_profile_runtime",
        lambda _: {
            "evaluation_engine": dict.fromkeys(
                ("torch", "transformers", "peft"), "changed"
            )
        },
    )
    with pytest.raises(ValueError, match="campaign_checkpoint_protocol_changed"):
        campaign.start("steps", plan["plan_sha256"])


@pytest.mark.parametrize("lost_winner", [False, True])
def test_checkpoint_retention_requires_the_exact_early_selected_artifact(
    checkpoint_campaign, lost_winner
):
    from venom_core.services.training_experiments.campaign_schema import CampaignSpec

    campaign, spec, _, _, _, _, service, client = checkpoint_campaign
    values = spec.model_dump()
    values["campaign_id"] = "steps-twin"
    values["variants"] = [{}, {"rank": 8}]
    plan = campaign.plan(CampaignSpec.model_validate(values))["plan"]
    campaign.start("steps-twin", plan["plan_sha256"])
    first = plan["variants"][0]["run_id"]
    winning_weights = (
        service.run_dir(first) / "training/checkpoint-2/adapter_model.safetensors"
    )
    other_weights = (
        service.run_dir(first) / "training/checkpoint-4/adapter_model.safetensors"
    )

    for variant in plan["variants"]:
        run_id = variant["run_id"]
        campaign.advance("steps-twin")
        campaign.advance("steps-twin")
        Worker(service, run_id, 1).run()
        _review_checkpoint_test(client, run_id, 2, run_id == first)
        _review_checkpoint_test(client, run_id, 4, False)
        state = campaign.advance("steps-twin")
        if lost_winner and run_id == first:
            winning_weights.unlink()

    second = plan["variants"][1]["run_id"]
    alternative = (
        service.run_dir(second) / "training/checkpoint-2/adapter_model.safetensors"
    )
    assert state["selected_checkpoint_step"] == 2
    assert state["selected_run_id"] == first
    assert other_weights.is_file()
    if lost_winner:
        assert alternative.is_file()
        assert "retention_receipt" not in state
    else:
        assert winning_weights.is_file()
        assert not alternative.exists()
        assert state["retention_receipt"]["removed_bytes"] > 0
        assert (
            service.checkpoint_report(second, 2)[0]["artifacts"][0]["available"]
            is False
        )


def test_dialogue_judge_keeps_blind_review_and_charges_once(setup, monkeypatch):
    from venom_core.services.training_experiments import dialogue_judge as judge

    svc, client, _, _, _, _, _ = setup
    directory = svc.run_dir("dialogue")
    directory.mkdir(parents=True)
    case = {
        "record_id": "dialogue-a",
        "language": "pl",
        "messages": [
            {"role": "user", "content": "Powiedz OK."},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "Powtórz."},
        ],
        "criteria": [
            {"id": "answer", "kind": "content", "description": "Używa słowa OK"}
        ],
        "source_repo": "meta",
    }
    incomplete = {"text": "Urwana", "finish": "length"}
    items = [
        {
            "case": case,
            "answers": {
                "A": {"text": "OK", "finish": "stop", "model": "base-hidden"},
                "B": incomplete,
            },
        },
        {
            "case": {**case, "record_id": "single", "messages": case["messages"][:1]},
            "answers": {"A": {"text": "OK", "finish": "stop"}},
        },
        {"case": {**case, "record_id": "failed"}, "answers": {"A": incomplete}},
        {
            "case": {**case, "record_id": "en", "language": "en"},
            "answers": {"A": {"text": "OK", "finish": "stop"}},
        },
    ]
    bundle = {
        "checkpoint_step": 4,
        "answers": items,
        "cases": [item["case"] for item in items],
    }
    monkeypatch.setattr(svc, "review", lambda _: bundle)
    monkeypatch.setattr(judge.openrouter_runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(judge.openrouter_runtime, "cloud_allowed", lambda: True)
    monkeypatch.setattr(judge.openrouter_runtime, "credential", lambda: "test-key")
    real_client = httpx.Client
    submitted = []

    def model(request):
        assert request.url == judge.openrouter_runtime.ENDPOINT
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        submitted.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "gen-test",
                "model": judge.MODEL,
                "provider": "Wafer",
                "usage": {"cost": 0.000051},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "pass": True,
                                    "critical": False,
                                    "reason": "Powtarza OK.",
                                }
                            )
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(
        judge.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(model), **kwargs),
    )
    base = "/api/v1/academy/experiments/runs/dialogue/review"
    assert client.get(base).json()["dialogue_judge"] == {
        "model": judge.MODEL,
        "available": True,
        "case_ids": ["dialogue-a"],
    }
    assert not submitted
    body = {"record_id": "dialogue-a", "checkpoint_step": 4}
    url = base + "/dialogue-judge"
    assert (
        client.post(
            url, json=body, headers={"Origin": "https://example.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json=body, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert not submitted
    assert (
        client.post(url, json={**body, "checkpoint_step": 2}).json()["detail"]["code"]
        == "experiment_checkpoint_review_changed"
    )
    for record_id in ("single", "failed", "missing", "en"):
        assert (
            client.post(url, json={**body, "record_id": record_id}).json()["detail"][
                "code"
            ]
            == "experiment_judge_case_ineligible"
        )
    monkeypatch.setattr(judge.openrouter_runtime, "cloud_allowed", lambda: False)
    assert (
        client.post(url, json=body).json()["detail"]["code"]
        == "experiment_judge_unavailable"
    )
    assert not submitted
    monkeypatch.setattr(judge.openrouter_runtime, "cloud_allowed", lambda: True)
    result = client.post(url, json=body).json()
    assert result["answers"]["A"]["verdict"]["pass"] is True
    assert result["answers"]["A"]["cost_usd"] == "0.000051"
    monkeypatch.setattr(judge.openrouter_runtime, "cloud_allowed", lambda: False)
    assert client.post(url, json=body).json() == result
    assert len(submitted) == 1
    payload = submitted[0]
    assert payload["provider"]["only"] == ["wafer/us"]
    assert payload["provider"]["zdr"] is True
    assert payload["provider"]["allow_fallbacks"] is False
    assert payload["provider"]["data_collection"] == "deny"
    assert payload["provider"]["max_price"] == {
        "prompt": 0.038,
        "completion": 0.5,
        "request": 0,
    }
    assert json.loads(payload["messages"][1]["content"]) == {
        "history": case["messages"],
        "rubric": case["criteria"],
        "answer": "OK",
    }
    assert not (directory / "judgments.json").exists()


@pytest.mark.parametrize(
    ("variation", "expected_cost"),
    [
        ("timeout", None),
        ("invalid_json", "0.00003"),
        ("wrong_model", "0.00003"),
        ("length", "0.00003"),
        ("invalid_verdict", "0.00003"),
        ("rate_limit", None),
    ],
)
def test_dialogue_judge_preserves_billing_for_failed_verdicts(variation, expected_cost):
    from venom_core.services.training_experiments import dialogue_judge as judge

    def model(request):
        if variation == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if variation == "rate_limit":
            return httpx.Response(429, json={"error": {"code": 429}})
        return httpx.Response(
            200,
            json={
                "id": "gen-test",
                "model": "other" if variation == "wrong_model" else judge.MODEL,
                "provider": "Wafer",
                "usage": {"cost": 0.00003},
                "choices": [
                    {
                        "finish_reason": "length" if variation == "length" else "stop",
                        "message": {
                            "content": "{broken"
                            if variation == "invalid_json"
                            else "{}"
                        },
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(model)) as client:
        result = judge.judge_answer(client, {"messages": []})
    assert result["status"] == "failed"
    assert result["cost_usd"] == expected_cost
    assert "verdict" not in result
