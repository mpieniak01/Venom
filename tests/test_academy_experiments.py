"""Exercise the public Academy run path without GPU or a live judge."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from venom_core.api.routes import academy_experiments as routes
from venom_core.services.remote_training.lifecycle import atomic_json, process_identity
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

    class Host:
        database = service.root / "host.sqlite3"
        enabled = False

    monkeypatch.setattr(
        "venom_core.services.training_experiments.worker.get_runtime_admission", Host
    )
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
