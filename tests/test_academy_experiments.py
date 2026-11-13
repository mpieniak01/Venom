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
from venom_core.api.routes import academy_experiments as routes
from venom_core.services.remote_training.lifecycle import atomic_json, process_identity
from venom_core.services.runtime_admission import RuntimeAdmission
from venom_core.services.training_experiments import worker as worker_module
from venom_core.services.training_experiments.evidence import latest_checkpoint
from venom_core.services.training_experiments.profiles import digest
from venom_core.services.training_experiments.service import ExperimentService
from venom_core.services.training_experiments.worker import Worker


def write_rows(path: Path, data: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")


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
        "recipe": {"steps": 4, "save_every": 2},
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
