"""Exercise durable campaign transitions using a local fake experiment service."""

import os
from pathlib import Path

import pytest

from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    process_identity,
)
from venom_core.services.training_experiments.campaign import CampaignService
from venom_core.services.training_experiments.campaign_schema import CampaignSpec
from venom_core.services.training_experiments.retention import (
    Retention,
    file_fingerprint,
    read_object,
)


class FakeExperiments:
    identity = "a" * 64

    def __init__(self, root: Path):
        self.root = root
        self.calls = []
        self.automatic = False

    def validate(self, profile_id, recipe=None):
        assert profile_id == "fixture"
        return {
            "profile_id": profile_id,
            "recipe": {"steps": 2, **(recipe or {})},
            "identity": self.identity,
            "automatic_review": self.automatic,
            "workload": {"updates": 2, "tokens": 40},
        }

    def profiles(self):
        return [
            {
                "id": "fixture",
                "identity": self.identity,
                "automatic_review": self.automatic,
            }
        ]

    def free_storage_bytes(self, profile_id):
        assert profile_id == "fixture"
        return 10**9

    def run_dir(self, run_id):
        return self.root / "runs" / run_id

    def run_lock(self, run_id):
        return file_lock(self.run_dir(run_id) / ".state.lock")

    def status(self, run_id):
        return read_object(self.run_dir(run_id) / "state.json")

    def list_runs(self):
        return [self.status(path.name) for path in (self.root / "runs").glob("*")]

    def _save(self, state):
        atomic_json(self.run_dir(state["run_id"]) / "state.json", state)
        return state

    def start(
        self,
        profile_id,
        run_id,
        recipe=None,
        *,
        max_seconds=None,
        campaign_id=None,
        expected_identity=None,
        review_mode=None,
        expected_initial_adapter=None,
    ):
        assert max_seconds > 0 and expected_identity == self.identity
        self.calls.append(("start", run_id))
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True)
        return self._save(
            {
                "run_id": run_id,
                "profile_id": profile_id,
                "profile_identity": expected_identity,
                "campaign_id": campaign_id,
                "recipe": recipe,
                "status": "running",
                "stage": "train",
                "attempt": 1,
                "resume_available": False,
                "evaluation_available": False,
            }
        )

    def stop(self, run_id, *, campaign_id=None):
        assert campaign_id == self.status(run_id)["campaign_id"]
        self.calls.append(("stop", run_id))
        return self.update(run_id, status="stopped")

    def resume(self, run_id, *, max_seconds=None, campaign_id=None):
        assert campaign_id == self.status(run_id)["campaign_id"]
        return self._retry(run_id, "resume", "train", max_seconds)

    def evaluate(self, run_id, *, max_seconds=None, campaign_id=None):
        assert campaign_id == self.status(run_id)["campaign_id"]
        return self._retry(run_id, "evaluate", "generate", max_seconds)

    def _retry(self, run_id, action, stage, max_seconds):
        assert max_seconds > 0
        self.calls.append((action, run_id))
        return self.update(
            run_id,
            status="running",
            stage=stage,
            attempt=self.status(run_id)["attempt"] + 1,
        )

    def report(self, run_id):
        directory = self.run_dir(run_id)
        result = read_object(directory / "result.json")
        artifact = directory / "training" / "checkpoint-2" / "adapter_model.safetensors"
        result["artifacts"] = [{"available": artifact.is_file()}]
        return result

    def update(self, run_id, **changes):
        return self._save({**self.status(run_id), **changes})

    def finish(self, run_id, usable, critical=0):
        directory = self.run_dir(run_id)
        checkpoint = directory / "training" / "checkpoint-2"
        checkpoint.mkdir(parents=True)
        artifact = checkpoint / "adapter_model.safetensors"
        hashes = {}
        for name in (
            artifact.name,
            "optimizer.pt",
            "rng_state.pth",
            "scheduler.pt",
            "training_args.bin",
        ):
            path = checkpoint / name
            path.write_text(name)
            hashes[name] = file_fingerprint(path)
        atomic_json(checkpoint / "hashes.json", hashes)
        atomic_json(checkpoint / "trainer_state.json", {"global_step": 2})
        atomic_json(
            directory / "result.json",
            {
                "profile_identity": self.identity,
                "summaries": {
                    "base": {"total": {"n": 4, "usable": 2, "critical": 0}},
                    "candidate": {
                        "total": {"n": 4, "usable": usable, "critical": critical}
                    },
                },
            },
        )
        atomic_json(
            directory / "result-seal.json",
            {"result_sha256": file_fingerprint(directory / "result.json")},
        )
        self.update(run_id, status="succeeded", stage="done", resume_available=True)
        return artifact


def make_spec(*, campaign_id="series", count=3, **overrides):
    return CampaignSpec.model_validate(
        {
            "campaign_id": campaign_id,
            "profile_id": "fixture",
            "variants": [{"rank": 2 + n} for n in range(count)],
            "budget": {
                "max_trials": count,
                "max_updates": 10,
                "max_tokens": 200,
                "max_seconds": 50,
                "trial_seconds": 20,
                "max_retries": 1,
                "max_artifact_bytes": 100_000,
                "min_free_bytes": 0,
            },
            "retention": "discard_rejected",
            **overrides,
        }
    )


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def controller(tmp_path):
    experiments = FakeExperiments(tmp_path)
    clock = Clock()
    identity = process_identity(os.getpid())
    service = CampaignService(
        experiments,
        launch=lambda _campaign: identity,
        clock=clock,
    )
    return service, experiments, clock


def start(service, spec=None):
    spec = spec or make_spec()
    planned = service.plan(spec)
    assert service.plan(spec) == planned
    return service.start(spec.campaign_id, planned["plan"]["plan_sha256"])


def launch_next(service, campaign_id="series"):
    state = service.advance(campaign_id)
    trial = state["trials"][state["trial_index"]]
    assert trial["intent"]["action"] == "start"
    result = service.advance(campaign_id)
    assert result["trials"][state["trial_index"]]["status"] == "running"
    return trial["run_id"]


@pytest.mark.parametrize(
    ("usable", "critical", "approved"),
    [(3, 0, True), (2, 0, False), (4, 1, False)],
)
def test_automatic_campaign_runs_extension_only_after_a_qualified_gain(
    controller, usable, critical, approved
):
    service, experiments, clock = controller
    experiments.automatic = True
    start(
        service,
        make_spec(
            review_mode="automatic",
            retention="keep_all",
            extension={"initial_trials": 2, "min_usable_delta": 0.25},
        ),
    )
    first = launch_next(service)
    experiments.finish(first, usable=usable, critical=critical)
    service.advance("series")
    second = launch_next(service)
    experiments.finish(second, usable=2)
    service.advance("series")

    # The detached supervisor may restart between the first block and the extension.
    restored = CampaignService(experiments, clock=clock)
    if approved:
        third = launch_next(restored)
        experiments.finish(third, usable=4)
        state = restored.advance("series")
        assert state["selected_run_id"] == third
        assert state["extension_decision"]["run_id"] == first
        assert (
            state["extension_decision"]["result_sha256"]
            == state["trials"][0]["result_sha256"]
        )
        assert len(experiments.calls) == 3
    else:
        state = restored.advance("series")
        assert state["trials"][2]["status"] == "skipped"
        assert len(experiments.calls) == 2
    assert state["status"] == "succeeded"
    assert state["extension_decision"]["status"] == (
        "approved" if approved else "skipped"
    )


@pytest.mark.parametrize(
    ("usable", "expected_status", "decision"),
    [(2, "succeeded", "skipped"), (4, "timed_out", "approved")],
)
def test_extension_decision_precedes_full_trial_window(
    controller, usable, expected_status, decision
):
    service, experiments, clock = controller
    experiments.automatic = True
    clock.now = 1000.0
    budget = make_spec().budget.model_dump()
    spec = make_spec(
        review_mode="automatic",
        retention="keep_all",
        budget={**budget, "max_seconds": 600, "trial_seconds": 180},
        extension={"initial_trials": 2, "min_usable_delta": 0.25},
    )
    planned = service.plan(spec)
    service.start("series", planned["plan"]["plan_sha256"], cutoff_at=1420.0)
    first = launch_next(service)
    clock.now = 1120.0
    experiments.finish(first, usable=usable)
    service.advance("series")
    second = launch_next(service)
    clock.now = 1250.0
    experiments.finish(second, usable=2)
    service.advance("series")

    state = service.advance("series")
    assert state["status"] == expected_status
    assert state["extension_decision"]["status"] == decision
    assert state["trials"][2]["status"] == (
        "skipped" if decision == "skipped" else "pending"
    )
    assert len(experiments.calls) == 2


def test_fixed_series_keeps_winner_report_and_failed_trial(controller):
    service, experiments, _clock = controller
    start(service)
    first = launch_next(service)
    experiments.update(first, status="awaiting_review", stage="score")
    assert service.advance("series")["status"] == "awaiting_review"
    assert len(experiments.calls) == 1
    first_artifact = experiments.finish(first, usable=3)
    state = service.advance("series")
    assert state["selected_run_id"] == first
    assert first_artifact.exists()

    second = launch_next(service)
    experiments.update(second, status="failed", error="invalid_masks")
    state = service.advance("series")
    assert state["trials"][1]["error"] == "invalid_masks"

    third = launch_next(service)
    third_artifact = experiments.finish(third, usable=4)
    state = service.advance("series")
    assert state["status"] == "succeeded"
    assert state["selected_run_id"] == third
    assert [trial["status"] for trial in state["trials"]] == [
        "succeeded",
        "failed",
        "succeeded",
    ]
    assert third_artifact.exists()
    assert not first_artifact.exists()
    assert not state["trials"][0]["resume_available"]
    assert experiments.report(first)["summaries"]["candidate"]["total"]["usable"] == 3
    receipt = service.retention_apply(
        "series", state["retention_receipt"]["plan_sha256"]
    )
    assert receipt["removed_bytes"] > 0
    assert service.advance("series")["trial_index"] == 3
    assert len(experiments.calls) == 3


def test_completed_fixed_trial_is_ranked_even_when_observed_at_cutoff(controller):
    service, experiments, clock = controller
    experiments.automatic = True
    spec = make_spec(review_mode="automatic", retention="keep_all")
    planned = service.plan(spec)
    service.start("series", planned["plan"]["plan_sha256"], cutoff_at=130)
    first = launch_next(service)
    experiments.finish(first, usable=4)
    clock.now = 130
    state = service.advance("series")
    assert state["status"] == "timed_out"
    assert state["selected_run_id"] == first
    assert state["trials"][0]["result_sha256"]
    assert len(experiments.calls) == 1


def test_controller_adopts_committed_launch_and_preserves_budget(controller):
    service, experiments, clock = controller
    planned = start(service)
    state = service.advance("series")
    run = state["plan"]["variants"][0]
    experiments.start(
        "fixture",
        run["run_id"],
        run["recipe"],
        campaign_id="series",
        max_seconds=10,
        expected_identity=experiments.identity,
    )
    state["worker"] = None
    service._save(service.directory("series"), state)
    clock.now += 3
    assert service.status("series")["status"] == "interrupted"
    assert service.resume("series")["elapsed_seconds"] == 3
    resumed = service.advance("series")
    assert resumed["used_updates"] == 2
    assert resumed["used_tokens"] == 40
    assert resumed["trials"][0]["attempt"] == 1
    assert len(experiments.calls) == 1
    assert service.start("series", planned["plan"]["plan_sha256"]) == resumed


@pytest.mark.parametrize(
    ("count", "resources_active", "can_start"),
    [(1, False, True), (1, True, False), (2, False, False)],
)
def test_only_a_quiescent_final_review_can_share_campaign_catalog(
    controller, count, resources_active, can_start
):
    service, experiments, _ = controller
    start(service, make_spec(count=count))
    control = launch_next(service)
    experiments.update(control, status="awaiting_review", stage="score")
    assert service.advance("series")["status"] == "awaiting_review"
    experiments.update(control, resources_active=resources_active)
    plan = service.plan(make_spec(campaign_id="candidate", count=1))["plan"]
    if not can_start:
        with pytest.raises(ValueError, match="campaign_already_active"):
            service.start("candidate", plan["plan_sha256"])
        return

    assert service.start("candidate", plan["plan_sha256"])["status"] == "running"
    next_run = launch_next(service, "candidate")
    experiments.finish(control, usable=3)
    assert service.advance("series")["status"] == "succeeded"
    assert experiments.calls == [("start", control), ("start", next_run)]


def test_campaign_fails_closed_for_stale_profile_and_competing_start(controller):
    service, experiments, _clock = controller
    start(service)
    alternate = service.plan(make_spec(campaign_id="another"))
    with pytest.raises(ValueError, match="already_active"):
        service.start("another", alternate["plan"]["plan_sha256"])
    with pytest.raises(ValueError, match="plan_changed"):
        service.start("series", "f" * 64)
    service.advance("series")
    experiments.identity = "b" * 64
    blocked = service.advance("series")
    assert blocked["status"] == "blocked"
    assert blocked["error"] == "campaign_profile_changed"
    assert experiments.calls == []


def test_plan_bounds_and_evaluator_qualification(controller):
    service, experiments, _clock = controller
    with pytest.raises(ValueError, match="evaluator_not_qualified"):
        service.plan(make_spec(review_mode="automatic"))
    with pytest.raises(ValueError, match="duplicate_variant"):
        service.plan(make_spec(variants=[{}, {}]))
    spec = make_spec()
    spec.budget.max_tokens = 100
    with pytest.raises(ValueError, match="token_budget_exceeded"):
        service.plan(spec)
    experiments.automatic = True
    assert service.plan(make_spec(review_mode="automatic"))["status"] == "planned"
    with pytest.raises(ValueError, match="not_approved"):
        service.resume("series")
    with pytest.raises(ValueError, match="id_invalid"):
        service.status("../series")


def test_local_automatic_campaign_ranks_scored_trials_without_operator_review(
    controller,
):
    service, experiments, _clock = controller
    experiments.automatic = True
    start(service, make_spec(count=2, review_mode="automatic"))
    first = launch_next(service)
    experiments.finish(first, usable=3)
    assert service.advance("series")["selected_run_id"] == first

    second = launch_next(service)
    experiments.finish(second, usable=4)
    state = service.advance("series")
    assert state["status"] == "succeeded"
    assert state["selected_run_id"] == second
    assert all(trial.get("result_sha256") for trial in state["trials"])


def test_retry_and_operator_stop_preserve_allocated_budget(controller):
    service, experiments, clock = controller
    start(service)
    first = launch_next(service)
    experiments.update(first, status="failed", resume_available=True)
    reserved = service.advance("series")
    assert reserved["used_updates"] == 4
    assert reserved["used_tokens"] == 80
    assert reserved["retries"] == 1
    assert service.advance("series")["trials"][0]["attempt"] == 2
    assert experiments.calls[-1] == ("resume", first)
    clock.now += 4
    assert service.stop("series")["status"] == "stopping"
    assert service.advance("series")["status"] == "stopped"
    assert experiments.calls[-1] == ("stop", first)
    clock.now += 2
    assert service.resume("series")["elapsed_seconds"] == 6
    assert service.advance("series")["trial_index"] == 1
    assert service.status("series")["used_updates"] == 4


def test_retry_generation_after_final_checkpoint_does_not_charge_training(controller):
    service, experiments, _ = controller
    start(service)
    first = launch_next(service)
    experiments.update(
        first,
        status="failed",
        stage="generate",
        resume_available=False,
        evaluation_available=True,
    )

    reserved = service.advance("series")
    assert reserved["used_updates"] == 2
    assert reserved["used_tokens"] == 40
    assert reserved["retries"] == 1
    assert service.advance("series")["trials"][0]["attempt"] == 2
    assert experiments.calls[-1] == ("evaluate", first)


def test_timeout_stops_only_owned_run(controller):
    service, experiments, clock = controller
    start(service)
    first = launch_next(service)
    clock.now += 22
    state = service.advance("series")
    assert state["trials"][0]["status"] == "timed_out"
    assert experiments.calls[-1] == ("stop", first)
    second = launch_next(service)
    clock.now += 35
    state = service.advance("series")
    assert state["status"] == "timed_out"
    assert experiments.calls[-1] == ("stop", second)
    with pytest.raises(ValueError, match="resume_unavailable"):
        service.resume("series")


def test_artifact_budget_blocks_more_work(controller):
    service, experiments, _clock = controller
    spec = make_spec()
    spec.budget.max_artifact_bytes = 1
    start(service, spec)
    first = launch_next(service)
    state = service.advance("series")
    assert state["status"] == "blocked"
    assert state["error"] == "campaign_storage_budget_exhausted"
    assert experiments.calls[-1] == ("stop", first)
    assert state["trial_index"] == 0


def retained_series(controller):
    service, experiments, _clock = controller
    start(service)
    first = launch_next(service)
    first_artifact = experiments.finish(first, usable=3)
    service.advance("series")
    second = launch_next(service)
    second_artifact = experiments.finish(second, usable=4)
    state = service.status("series")
    state["selected_run_id"] = second
    state["trials"][1].update(
        status="succeeded",
        result_sha256=file_fingerprint(experiments.run_dir(second) / "result.json"),
    )
    return (
        Retention(experiments, service.directory("series")),
        state,
        first_artifact,
        second_artifact,
    )


def test_retention_rejects_changed_protection_or_file(controller):
    retention, state, rejected, winner = retained_series(controller)
    plan = retention.plan(state)
    run_id = state["trials"][0]["run_id"]
    retention.experiments.update(run_id, pinned=True)
    with pytest.raises(ValueError, match="retention_plan_changed"):
        retention.apply(state, plan["plan_sha256"])
    assert rejected.exists() and winner.exists()
    retention.experiments.update(run_id, pinned=False)
    original = rejected.read_text()
    rejected.write_text("x" * len(original))
    with pytest.raises(ValueError, match="artifact_file_changed"):
        retention.apply(state, plan["plan_sha256"])
    assert rejected.exists() and winner.exists()


def test_retention_recovers_unlink_without_completion_receipt(controller, monkeypatch):
    from venom_core.services.training_experiments import retention as module

    retention, state, rejected, winner = retained_series(controller)
    plan = retention.plan(state)
    atomic = module.atomic_json

    def interrupt_after_first_unlink(path, value):
        if path.name == "retention-pending.json" and value["files"]:
            raise OSError("simulated power failure")
        atomic(path, value)

    monkeypatch.setattr(module, "atomic_json", interrupt_after_first_unlink)
    with pytest.raises(OSError, match="power failure"):
        retention.apply(state, plan["plan_sha256"])
    assert not rejected.exists()
    assert winner.exists()
    monkeypatch.setattr(module, "atomic_json", atomic)
    receipt = retention.apply(state, plan["plan_sha256"])
    assert receipt["files"][0]["outcome"] == "absent_on_recovery"
    assert retention.apply(state, plan["plan_sha256"]) == receipt
    assert winner.exists()


def test_orphaned_runtime_blocks_next_trial_until_reaped(controller):
    service, experiments, _clock = controller
    start(service)
    run_id = launch_next(service)
    experiments.update(run_id, status="failed", resources_active=True)
    blocked = service.advance("series")
    assert blocked["error"] == "campaign_trial_quiescence_unconfirmed"
    assert blocked["trial_index"] == 0
    other = service.plan(make_spec(campaign_id="other"))
    with pytest.raises(ValueError, match="already_active"):
        service.start("other", other["plan"]["plan_sha256"])
    experiments.update(run_id, resources_active=False)
    service.resume("series")
    assert service.advance("series")["trial_index"] == 1
    assert experiments.calls == [("start", run_id)]


def test_retention_preserves_referenced_parent_and_rejects_symlink(controller):
    retention, state, rejected, winner = retained_series(controller)
    parent_id = state["trials"][0]["run_id"]
    reference = retention.experiments.run_dir("consumer")
    reference.mkdir()
    atomic_json(reference / "state.json", {"run_id": "consumer"})
    atomic_json(reference / "manifest.json", {"parent_run_id": parent_id})
    assert retention.plan(state)["files"] == []
    (reference / "manifest.json").unlink()
    original = rejected.read_bytes()
    outside = retention.experiments.root / "protected-test-file"
    outside.write_bytes(original)
    rejected.unlink()
    rejected.symlink_to(outside)
    with pytest.raises(ValueError, match="file_unmanaged"):
        retention.plan(state)
    assert outside.read_bytes() == original and winner.exists()


def test_detached_supervisor_drives_durable_state(controller, monkeypatch):
    from venom_core.services.training_experiments import campaign_worker

    service, experiments, _clock = controller
    planned = start(service, make_spec(count=1))
    run_id = planned["trials"][0]["run_id"]

    def complete_after_launch(_seconds):
        if experiments.calls == [("start", run_id)]:
            experiments.finish(run_id, usable=3)

    monkeypatch.setattr(campaign_worker.time, "sleep", complete_after_launch)
    campaign_worker.supervise(service, "series")
    result = service.status("series")
    assert result["status"] == "succeeded"
    assert result["selected_run_id"] == run_id
    assert result["worker"] is None


def test_retention_does_not_discard_alternative_when_winner_missing(controller):
    retention, state, rejected, winner = retained_series(controller)
    plan = retention.plan(state)
    assert plan["files"]
    winner.unlink()
    with pytest.raises(ValueError, match="retention_plan_changed"):
        retention.apply(state, plan["plan_sha256"])
    assert retention.plan(state)["files"] == []
    assert rejected.exists()


def test_campaign_http_plan_start_and_read(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from venom_core.api.routes import academy_experiment_campaigns as routes
    from venom_core.api.routes import academy_experiments

    service = CampaignService(
        FakeExperiments(tmp_path), launch=lambda _: process_identity(os.getpid())
    )
    monkeypatch.setattr(routes, "campaign_service", lambda: service)
    monkeypatch.setattr(academy_experiments.SETTINGS, "ENABLE_ACADEMY", True)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app, client=("127.0.0.1", 1234))
    prefix = "/api/v1/academy/experiments/campaigns"
    assert client.get(prefix).json()["campaigns"] == []
    plan = client.post(f"{prefix}/plan", json=make_spec().model_dump())
    assert plan.status_code == 200, plan.text
    digest = plan.json()["plan"]["plan_sha256"]
    assert (
        client.post(
            f"{prefix}/series/start", json={"plan_sha256": "b" * 64}
        ).status_code
        == 409
    )
    result = client.post(f"{prefix}/series/start", json={"plan_sha256": digest})
    assert result.status_code == 200, result.text
    assert client.get(f"{prefix}/series").json()["status"] == "running"
    assert client.get(f"{prefix}/series/report").json()["campaign_id"] == "series"
    assert client.post(f"{prefix}/series/stop").status_code == 200
    assert client.get(prefix).json()["campaigns"][0]["campaign_id"] == "series"


class FixtureSampler:
    def __init__(self):
        self.suggestions = [{"rank": 4}, {"rank": 5}, {"rank": 6}]
        self.assigned = {}
        self.outcomes = {}
        self.ask_count = 0
        self.tell_count = 0

    def ask(self, directory, plan, index):
        assert directory.name == plan["campaign_id"]
        self.ask_count += 1
        return self.assigned.setdefault(
            index, {"trial_number": index, "params": self.suggestions[index]}
        )

    def tell(self, _directory, _plan, number, outcome, value=None, constraints=None):
        self.tell_count += 1
        result = (outcome, value, constraints)
        assert self.outcomes.setdefault(number, result) == result


@pytest.fixture
def sampler(monkeypatch):
    from venom_core.services.training_experiments import optuna_backend

    fixture = FixtureSampler()
    monkeypatch.setattr(optuna_backend, "require_optuna", lambda: "4.9.0")
    monkeypatch.setattr(optuna_backend, "ask", fixture.ask)
    monkeypatch.setattr(
        optuna_backend, "assigned", lambda _directory, _plan, i: fixture.assigned.get(i)
    )
    monkeypatch.setattr(optuna_backend, "tell", fixture.tell)
    return fixture


def optimization_spec(*, count=3, **options):
    return make_spec(
        count=count,
        **{
            "strategy": "optuna",
            "variants": [],
            "search_space": {"rank": {"low": 4, "high": 6}},
            "sampler_seed": 21,
            **options,
        },
    )


def test_optuna_reconciles_ask_and_tell_across_state_write_crash(
    controller, sampler, monkeypatch
):
    service, experiments, _clock = controller
    planned = start(service, optimization_spec(count=1))
    original_save = service._save

    def crash_after_ask(directory, state):
        if state["trials"][0].get("intent"):
            raise SystemExit("crash between ask and campaign publication")
        original_save(directory, state)

    monkeypatch.setattr(service, "_save", crash_after_ask)
    with pytest.raises(SystemExit, match="publication"):
        service.advance("series")
    assert service.status("series")["used_updates"] == 0
    assert experiments.calls == []
    assert sampler.assigned.keys() == {0}

    monkeypatch.setattr(service, "_save", original_save)
    run_id = launch_next(service)
    assert planned["trials"][0]["run_id"] == run_id
    assert experiments.status(run_id)["recipe"]["rank"] == 4
    assert service.status("series")["used_updates"] == 2
    assert sampler.ask_count == 2
    experiments.finish(run_id, usable=3)

    def crash_after_tell(directory, state):
        if state["trial_index"] == 1:
            raise SystemExit("crash after durable outcome before cursor")
        original_save(directory, state)

    monkeypatch.setattr(service, "_save", crash_after_tell)
    with pytest.raises(SystemExit, match="cursor"):
        service.advance("series")
    assert service.status("series")["trial_index"] == 0
    assert sampler.outcomes == {0: ("COMPLETE", 0.25, [0.0, -0.25])}

    monkeypatch.setattr(service, "_save", original_save)
    recovered = service.advance("series")
    assert recovered["status"] == "succeeded"
    assert recovered["trials"][0]["optuna_trial_state"] == "COMPLETE"
    assert recovered["selected_run_id"] == run_id
    assert sampler.tell_count == 2
    assert experiments.calls == [("start", run_id)]


def test_optuna_distinguishes_duplicate_technical_failure_and_gate_rejection(
    controller, sampler
):
    service, experiments, _clock = controller
    sampler.suggestions[1] = sampler.suggestions[0]
    start(service, optimization_spec())
    rejected = launch_next(service)
    experiments.update(rejected, status="awaiting_review", stage="score")
    assert service.advance("series")["status"] == "awaiting_review"
    assert sampler.outcomes == {}

    experiments.finish(rejected, usable=4, critical=1)
    observed = service.advance("series")
    assert observed["selected_run_id"] is None
    assert observed["trials"][0]["gate_passed"] is False
    assert sampler.outcomes[0] == ("COMPLETE", 0.5, [0.25, -0.5])

    skipped = service.advance("series")
    assert skipped["trials"][1]["status"] == "skipped"
    assert skipped["trials"][1]["error"] == "campaign_duplicate_suggestion"
    assert skipped["used_tokens"] == 40
    assert sampler.outcomes[1] == ("FAIL", None, None)

    failed = launch_next(service)
    experiments.update(failed, status="failed", error="invalid_checkpoint")
    finished = service.advance("series")
    assert finished["status"] == "succeeded"
    assert finished["used_tokens"] == 80
    assert finished["trials"][2]["optuna_trial_state"] == "FAIL"
    assert "usable_delta" not in finished["trials"][2]
    assert sampler.outcomes[2] == ("FAIL", None, None)
    assert experiments.calls == [("start", rejected), ("start", failed)]


@pytest.mark.parametrize("params", [{"rank": 7}, {"rank": 4.0}, {"steps": 4}])
def test_optuna_blocks_unauthorized_suggestion_before_launch(
    controller, sampler, params
):
    service, experiments, _clock = controller
    sampler.suggestions[0] = params
    start(service, optimization_spec())
    blocked = service.advance("series")
    assert blocked["status"] == "blocked"
    assert blocked["error"] == "campaign_optuna_suggestion_invalid"
    assert blocked["used_updates"] == 0
    assert experiments.calls == []
    assert sampler.outcomes == {}


def test_optuna_preflight_checks_worst_case_for_every_slot(
    controller, sampler, monkeypatch
):
    service, experiments, _clock = controller
    validate = experiments.validate

    def expensive_corner(profile_id, recipe=None):
        checked = validate(profile_id, recipe)
        if (recipe or {}).get("rank") == 6:
            checked["workload"]["tokens"] = 90
        return checked

    monkeypatch.setattr(experiments, "validate", expensive_corner)
    spec = optimization_spec()
    with pytest.raises(ValueError, match="token_budget_exceeded"):
        service.plan(spec)
    assert sampler.assigned == {}
    assert experiments.calls == []


def test_optuna_expired_resume_reconciles_finished_outcome_without_more_work(
    controller, sampler
):
    service, experiments, clock = controller
    start(service, optimization_spec())
    run_id = launch_next(service)
    experiments.finish(run_id, usable=3)
    state = service.status("series")
    state["worker"] = None
    service._save(service.directory("series"), state)
    clock.now += 51

    assert service.resume("series")["status"] == "stopping"
    settled = service.advance("series")
    assert settled["status"] == "timed_out"
    assert settled["trials"][0]["optuna_trial_state"] == "COMPLETE"
    assert sampler.outcomes == {0: ("COMPLETE", 0.25, [0.0, -0.25])}
    assert experiments.calls == [("start", run_id)]


@pytest.mark.parametrize("elapsed", [21, 51])
def test_optuna_preserves_evaluation_completed_at_deadline(
    controller, sampler, monkeypatch, elapsed
):
    service, experiments, clock = controller
    start(service, optimization_spec())
    run_id = launch_next(service)

    def stop_after_evaluation(run_id, *, campaign_id):
        assert campaign_id == "series"
        experiments.finish(run_id, usable=3)
        return experiments.status(run_id)

    monkeypatch.setattr(experiments, "stop", stop_after_evaluation)
    clock.now += elapsed
    result = service.advance("series")
    assert result["trials"][0]["optuna_trial_state"] == "COMPLETE"
    assert result["selected_run_id"] == run_id
    assert sampler.outcomes == {0: ("COMPLETE", 0.25, [0.0, -0.25])}


def test_optuna_expiry_reconciles_unpublished_ask_without_starting_work(
    controller, sampler
):
    service, experiments, clock = controller
    state = start(service, optimization_spec())
    sampler.ask(service.directory("series"), state["plan"], 0)
    clock.now += 51
    expired = service.advance("series")

    assert expired["status"] == "timed_out"
    assert expired["trials"][0]["optuna_trial_state"] == "FAIL"
    assert expired["used_updates"] == 0
    assert sampler.ask_count == 1
    assert sampler.outcomes == {0: ("FAIL", None, None)}
    assert experiments.calls == []


def test_optuna_expired_launch_intent_is_reconciled(controller, sampler):
    service, experiments, clock = controller
    start(service, optimization_spec())
    assert service.advance("series")["trials"][0]["intent"]["action"] == "start"
    clock.now += 21

    expired = service.advance("series")
    assert expired["status"] == "timed_out"
    assert expired["trials"][0]["optuna_trial_state"] == "FAIL"
    assert sampler.outcomes == {0: ("FAIL", None, None)}
    assert experiments.calls == []


def test_fixed_campaign_does_not_need_optuna_and_preserves_old_plan(
    controller, monkeypatch
):
    from venom_core.services.training_experiments import optuna_backend

    service, experiments, _clock = controller

    def unavailable():
        raise ValueError("campaign_optuna_unavailable")

    monkeypatch.setattr(optuna_backend, "require_optuna", unavailable)
    first = service.plan(make_spec())
    assert not {"strategy", "sampler_seed", "search_space"} & first["plan"].keys()
    assert start(service)["plan"] == first["plan"]
    spec = optimization_spec(campaign_id="search")
    with pytest.raises(ValueError, match="optuna_unavailable"):
        service.plan(spec)
    assert experiments.calls == []


@pytest.fixture
def academy_dispatcher(controller, monkeypatch, tmp_path):
    from venom_core.core.dispatcher import TaskDispatcher
    from venom_core.execution.maf_runtime import AgentRuntime
    from venom_core.execution.skill_manager import SkillManager
    from venom_core.services.training_experiments import operator

    service, _, _ = controller
    monkeypatch.setattr(operator, "campaign_service", lambda: service)
    monkeypatch.setattr(operator.SETTINGS, "ENABLE_ACADEMY", True)
    dispatcher = TaskDispatcher.__new__(TaskDispatcher)
    dispatcher.skill_manager = SkillManager(
        AgentRuntime(), custom_skills_dir=str(tmp_path / "custom")
    )
    dispatcher.skill_manager.register_mcp_adapter(
        "academy",
        operator.AcademyCampaignAdapter(),
        skill_name="AcademyCampaignOperatorSkill",
    )
    return dispatcher


@pytest.mark.asyncio
async def test_operator_commands_share_campaign_and_resume_without_duplicate_launches(
    controller, academy_dispatcher, monkeypatch
):
    service, experiments, _ = controller
    launches = []
    original_launch = service._launch

    def launch(campaign_id):
        launches.append(campaign_id)
        return original_launch(campaign_id)

    monkeypatch.setattr(service, "_launch", launch)
    run = academy_dispatcher.dispatch_academy_campaign
    assert "/academy validate" in await run("/academy", "de")
    spec = make_spec(count=2).model_dump_json()
    preview = await run(f"/academy validate {spec}", "en")
    assert "Validated draft plan" in preview
    assert '"max_trials": 2' in preview
    assert service.list() == []
    planned = await run(f"/academy plan {spec}", "pl")
    state = service.status("series")
    digest = state["plan"]["plan_sha256"]
    assert f"/academy start series {digest}" in planned
    assert "dev_usable_delta" in planned
    enlarged_budget = {**state["plan"]["budget"], "max_updates": 12}
    changed = make_spec(count=2, budget=enlarged_budget).model_dump_json()
    assert "campaign_plan_conflict" in await run(f"/academy plan {changed}", "pl")
    assert service.status("series")["plan"]["plan_sha256"] == digest
    assert "campaign_plan_changed" in await run(
        f"/academy start series {'a' * 64}", "pl"
    )
    assert not launches

    start_command = f"/academy start series {digest}"
    started = await run(start_command, "en")
    repeated = await run(start_command, "en")
    assert "Execution ID** `series`" in started
    assert started == repeated
    assert "[Open campaign in Academy](/academy?campaign=series)" in started
    assert launches == ["series"]
    first = launch_next(service)
    experiments.finish(first, usable=3)
    service.advance("series")
    second = launch_next(service)
    assert "stopping" in await run("/academy stop series", "en")
    stopped = service.advance("series")
    assert stopped["status"] == "stopped"
    assert stopped["selected_run_id"] == first
    assert experiments.calls[-1] == ("stop", second)
    assert "Status** `stopped`" in await run("/academy status series", "de")
    assert "running" in await run("/academy resume series", "en")
    assert launches == ["series", "series"]
    comparison = await run("/academy compare series", "pl")
    assert "2/4 → 3/4" in comparison
    assert "Receptura do potwierdzenia w nowej kampanii" in comparison
    assert "brak danych" in comparison
    assert "poprawa" in comparison
    assert first in comparison
    assert second in comparison


@pytest.mark.asyncio
async def test_report_distinguishes_pruned_weights_and_missing_saved_metrics(
    controller, academy_dispatcher
):
    service, experiments, _ = controller
    start(service)
    first = launch_next(service)
    first_adapter = experiments.finish(first, usable=3)
    service.advance("series")
    second = launch_next(service)
    second_adapter = experiments.finish(second, usable=1, critical=1)
    service.advance("series")
    assert first_adapter.exists()
    assert not second_adapter.exists()
    output = await academy_dispatcher.dispatch_academy_campaign(
        "/academy report series", "en"
    )
    assert "Limits" in output
    assert '"max_trials": 3' in output
    assert "regression | unavailable" in output
    assert "second seed and an independent set" in output

    result = experiments.run_dir(first) / "result.json"
    result.write_text(result.read_text() + "\n")
    stale = await academy_dispatcher.dispatch_academy_campaign(
        "/academy report series", "en"
    )
    assert f"| `{first}` | `succeeded` | unavailable |" in stale
    assert "Recipe to confirm" not in stale


@pytest.mark.asyncio
async def test_operator_optuna_plan_freezes_space_without_launching(
    controller, academy_dispatcher, sampler
):
    service, experiments, _ = controller
    spec = optimization_spec().model_dump_json()
    text = await academy_dispatcher.dispatch_academy_campaign(
        f"/academy plan {spec}", "de"
    )
    assert '"search_space"' in text
    assert '"sampler_seed": 21' in text
    assert '"base_recipe"' in text
    assert service.status("series")["plan"]["strategy"] == "optuna"
    assert experiments.calls == []


@pytest.mark.asyncio
async def test_operator_tools_reject_untrusted_or_incomplete_input(
    controller, academy_dispatcher, monkeypatch
):
    from venom_core.services.training_experiments import operator

    service, experiments, _ = controller
    run = academy_dispatcher.dispatch_academy_campaign
    for text in [
        "/academy start series",
        "/academy status ../../other",
        "/academy resume series extra",
        "/academy delete series",
        "/academy start series " + "f" * 65,
        "/academy plan {}",
        "/academy validate " + "x" * 32768,
    ]:
        assert "campaign_command_invalid" in await run(text, "en")
    spec = make_spec(variants=[{"max_tokens": 32}]).model_dump_json()
    assert "campaign_parameter_unsupported" in await run(f"/academy plan {spec}", "en")
    with pytest.raises(PermissionError, match="campaign_operator_command_required"):
        await academy_dispatcher.skill_manager.invoke_mcp_tool(
            "academy",
            "start",
            {"command": {"action": "start", "campaign_id": "series"}},
        )
    mismatched_command = operator.CampaignCommand("status", "series")
    with pytest.raises(PermissionError, match="campaign_operator_command_required"):
        await academy_dispatcher.skill_manager.invoke_mcp_tool(
            "academy", "start", {"command": mismatched_command}
        )
    assert "campaign_evidence_missing" in await run("/academy status series", "en")
    monkeypatch.setattr(operator.SETTINGS, "ENABLE_ACADEMY", False)
    assert "experiment_academy_disabled" in await run("/academy status series", "en")
    assert service.list() == []
    assert experiments.calls == []


def test_campaign_chat_authorization_is_local_and_cannot_be_provided_in_json(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from venom_core.api.routes import tasks
    from venom_core.api.routes.academy_experiments import SETTINGS
    from venom_core.api.schemas.tasks import TaskRequest, TaskResponse

    app = FastAPI()
    app.include_router(tasks.router)
    submit = AsyncMock(return_value=TaskResponse(task_id=uuid4(), status="PENDING"))
    app.dependency_overrides[tasks.get_orchestrator] = lambda: SimpleNamespace(
        submit_task=submit
    )
    monkeypatch.setattr(SETTINGS, "ENABLE_ACADEMY", True)
    remote = TestClient(app)
    local = TestClient(app, client=("127.0.0.1", 12345))
    payload = {"content": "/academy status series"}
    assert remote.post("/api/v1/tasks", json=payload).status_code == 403
    assert (
        local.post(
            "/api/v1/tasks", json=payload, headers={"origin": "https://example.test"}
        ).status_code
        == 403
    )
    app.state.studio_runtime = object()
    assert local.post("/api/v1/tasks", json=payload).status_code == 409
    app.state.studio_runtime = None
    monkeypatch.setattr(SETTINGS, "ENABLE_ACADEMY", False)
    assert local.post("/api/v1/tasks", json=payload).status_code == 503
    assert submit.await_count == 0
    monkeypatch.setattr(SETTINGS, "ENABLE_ACADEMY", True)
    assert local.post("/api/v1/tasks", json=payload).status_code == 201
    assert submit.await_args.args[0]._academy_operator is True
    assert not TaskRequest.model_validate(
        {**payload, "_academy_operator": True}
    )._academy_operator
    assert (
        local.post(
            "/api/v1/tasks", json={"content": "normal", "forced_tool": "academy"}
        ).status_code
        == 201
    )
    assert not submit.await_args.args[0]._academy_operator


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["status", "stop"])
async def test_academy_task_runs_without_llm_and_persists_chat_history(
    monkeypatch, academy_dispatcher, action
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from venom_core.api.schemas.tasks import TaskRequest
    from venom_core.core.orchestrator import orchestrator_dispatch, orchestrator_submit
    from venom_core.services import vast_chat_runtime

    task = SimpleNamespace(id=uuid4(), status="PENDING")
    orch = MagicMock()
    orch.state_manager.create_task.return_value = task
    orch.state_manager.get_task.return_value = task
    orch.state_manager.update_status = AsyncMock()
    orch._broadcast_event = AsyncMock()
    orch.task_manager.register_task = AsyncMock()
    orch.task_manager.unregister_task = AsyncMock()
    orch.task_manager.is_paused = True
    orch.task_manager.check_capacity = AsyncMock(return_value=(False, 1))
    orch.task_dispatcher = academy_dispatcher
    orch.request_tracer = None
    orch._run_task = lambda task_id, request, fast_path: orchestrator_dispatch.run_task(
        orch, task_id, request, fast_path
    )
    preflight = AsyncMock(
        side_effect=AssertionError("Campaign must avoid provider preflight")
    )
    monkeypatch.setattr(vast_chat_runtime, "preflight", preflight)
    background = []
    monkeypatch.setattr(
        orchestrator_submit, "_spawn_background_task", background.append
    )

    request = TaskRequest(content=f"/academy {action} series", session_id="chat")
    with pytest.raises(PermissionError, match="campaign_operator_command_required"):
        await orchestrator_submit.submit_task(orch, request)
    assert orch.state_manager.create_task.call_count == 0

    request._academy_operator = True
    response = await orchestrator_submit.submit_task(orch, request)
    assert response.task_id == task.id
    assert response.llm_provider is None
    await background.pop()
    preflight.assert_not_awaited()
    orch.task_manager.check_capacity.assert_not_awaited()
    orch._refresh_kernel_if_needed.assert_not_called()
    assert orch._append_session_history.call_count == 2
    text = orch.state_manager.update_status.await_args.kwargs["result"]
    assert "campaign_evidence_missing" in text
    assert (
        orch.state_manager.update_context.call_args.args[1]["conversation_provider"][
            "operation"
        ]
        == "academy_campaign"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("command", [f"start series {'a' * 64}", "resume series"])
async def test_academy_start_and_resume_wait_for_queue_admission(monkeypatch, command):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from venom_core.api.schemas.tasks import TaskRequest
    from venom_core.core.orchestrator import orchestrator_submit

    task = SimpleNamespace(id=uuid4(), status="PENDING")
    orch = MagicMock()
    orch.state_manager.create_task.return_value = task
    orch.state_manager.get_task.return_value = task
    orch.request_tracer = None
    orch._run_task = AsyncMock()
    manager = orch.task_manager
    manager.is_paused = True
    manager.check_capacity = AsyncMock(side_effect=[(False, 1), (True, 0)])
    manager.register_task = AsyncMock()
    manager.unregister_task = AsyncMock()

    async def next_poll(_seconds):
        orch._run_task.assert_not_awaited()
        manager.register_task.assert_not_awaited()
        if manager.is_paused:
            manager.check_capacity.assert_not_awaited()
            manager.is_paused = False
        else:
            manager.check_capacity.assert_awaited_once()

    monkeypatch.setattr(
        orchestrator_submit,
        "asyncio",
        SimpleNamespace(sleep=next_poll, current_task=asyncio.current_task),
    )
    background = []
    monkeypatch.setattr(
        orchestrator_submit, "_spawn_background_task", background.append
    )

    request = TaskRequest(content=f"/academy {command}")
    request._academy_operator = True
    response = await orchestrator_submit.submit_task(orch, request)
    assert response.status == "PENDING"
    await background.pop()

    assert manager.check_capacity.await_count == 2
    manager.register_task.assert_awaited_once_with(task.id, asyncio.current_task())
    orch._run_task.assert_awaited_once_with(task.id, request, fast_path=False)
    manager.unregister_task.assert_awaited_once_with(task.id)


@pytest.fixture
def guarded_evidence(monkeypatch, controller):
    from venom_core.services.training_experiments import quality_native

    _service, experiments, _clock = controller
    identity = {
        "model": "fixture-model",
        "base_sha256": "1" * 64,
        "dataset_sha256": "2" * 64,
        "protocol_sha256": "3" * 64,
    }
    categories = {"a": "init", "b": "fallback", "c": "fallback", "d": "fallback"}

    def case_rows(hits, critical=()):
        return {
            key: {
                "category": category,
                "base": {"usable": key in {"a", "c"}, "critical": False},
                "candidate": {"usable": key in hits, "critical": key in critical},
            }
            for key, category in categories.items()
        }

    runtime = {"evaluation_engine": {"python": "3.14.8"}, "loss": "trainer_default"}
    train_sha256 = "7" * 64
    references = {
        "prior": {
            "identity": dict(identity),
            "split": "dev",
            "result_sha256": "4" * 64,
            "protected_case_ids": ["a"],
            "cases": case_rows({"c"}),
            "runtime": runtime,
            "train_sha256": train_sha256,
        }
    }
    records = {}

    def record(run_id, hits, critical=(), **overrides):
        data = {
            "identity": dict(identity),
            "split": "dev",
            "source": {
                "sha256": file_fingerprint(experiments.run_dir(run_id) / "result.json")
            },
            "cases": case_rows(hits, critical),
            "runtime": runtime,
            "train_sha256": train_sha256,
            **overrides,
        }
        records[run_id] = data
        return data

    monkeypatch.setattr(
        quality_native,
        "profile_context",
        lambda *_args, include_runtime=False: {
            "identity": {
                key: value
                for key, value in identity.items()
                if key != "protocol_sha256"
            },
            "case_categories": categories,
            "train_sha256": train_sha256,
            **({"runtime": runtime} if include_runtime else {}),
        },
    )
    monkeypatch.setattr(
        quality_native, "get_record", lambda _experiments, key: references[key]
    )
    monkeypatch.setattr(
        quality_native, "native_record", lambda _experiments, key: records[key]
    )
    return references, record


def guarded_spec(*, count=3, policy=None, optimized=False):
    arguments = {
        "quality_policy": (
            {
                "reference_record_ids": ["prior"],
                "min_category_usable_delta": {"init": 0.0},
            }
            if policy is None
            else policy
        ),
        "selection": {"min_usable_delta": 0.0, "max_critical_delta": 0.5},
    }
    factory = optimization_spec if optimized else make_spec
    return factory(count=count, **arguments)


def test_quality_guard_ranks_exact_hits_and_retains_unavailable_evidence(
    controller, guarded_evidence
):
    service, experiments, _clock = controller
    _references, record = guarded_evidence
    plan = service.validate(guarded_spec())
    assert plan["quality_policy"]["protected_case_ids"] == ["a", "c"]
    assert plan["quality_policy"]["references"] == [
        {"record_id": "prior", "result_sha256": "4" * 64}
    ]
    state = start(service, guarded_spec())
    assert state["plan"] == plan

    first = launch_next(service)
    worse_artifact = experiments.finish(first, usable=3, critical=1)
    record(first, {"b", "c", "d"}, {"d"})
    rejected = service.advance("series")
    assert rejected["selected_run_id"] is None
    guard = rejected["trials"][0]["quality_guard"]
    assert guard["status"] == "rejected"
    assert guard["lost_case_ids"] == ["a"]
    assert guard["new_critical_case_ids"] == ["d"]
    assert guard["category_deltas"]["init"]["usable_delta"] == -1.0
    assert worse_artifact.exists()

    second = launch_next(service)
    best_artifact = experiments.finish(second, usable=2)
    record(second, {"a", "c"})
    selected = service.advance("series")
    assert selected["selected_run_id"] == second
    assert selected["trials"][1]["quality_guard"]["status"] == "passed"
    assert best_artifact.exists()
    assert not worse_artifact.exists()

    third = launch_next(service)
    missing_artifact = experiments.finish(third, usable=4)
    missing = record(third, {"a", "b", "c", "d"})
    missing["cases"]["a"]["candidate"]["critical"] = None
    final = service.advance("series")
    assert final["status"] == "blocked"
    assert final["trial_index"] == 2
    assert final["selected_run_id"] == second
    assert final["trials"][2]["quality_guard"]["status"] == "blocked"
    assert final["trials"][2]["quality_guard"]["reasons"] == [
        {"code": "campaign_quality_case_evidence_missing"}
    ]
    assert missing_artifact.exists()
    missing["cases"]["a"]["candidate"]["critical"] = False
    service.resume("series")
    recovered = service.advance("series")
    assert recovered["status"] == "succeeded"
    assert recovered["selected_run_id"] == third
    assert experiments.calls == [("start", first), ("start", second), ("start", third)]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("split", "holdout", "campaign_quality_dev_required"),
        ("result_sha256", None, "campaign_quality_reference_unavailable"),
        ("cases", {}, "campaign_quality_case_coverage"),
    ],
)
def test_guard_refuses_incomparable_reference_before_campaign(
    controller, guarded_evidence, field, value, message
):
    service, experiments, _clock = controller
    references, _record = guarded_evidence
    references["prior"][field] = value
    spec = guarded_spec()
    with pytest.raises(ValueError, match=message):
        service.plan(spec)
    assert service.list() == []
    assert experiments.calls == []


def test_guard_rejects_unknown_case_or_category_before_work(
    controller, guarded_evidence
):
    service, experiments, _clock = controller
    unknown_case = guarded_spec(policy={"protected_case_ids": ["sealed-holdout"]})
    unknown_category = guarded_spec(
        policy={"min_category_usable_delta": {"unknown": 0}}
    )
    with pytest.raises(ValueError, match="campaign_quality_protected_case_unknown"):
        service.plan(unknown_case)
    with pytest.raises(ValueError, match="campaign_quality_category_unknown"):
        service.plan(unknown_category)
    assert experiments.calls == []


def test_stale_quality_reference_withdraws_winner_and_blocks_more_work(
    controller, guarded_evidence
):
    service, experiments, _clock = controller
    references, record = guarded_evidence
    start(service, guarded_spec())
    first = launch_next(service)
    artifact = experiments.finish(first, usable=3)
    record(first, {"a", "b", "c"})
    assert service.advance("series")["selected_run_id"] == first
    references["prior"]["result_sha256"] = "5" * 64
    status = service.status("series")
    assert status["selected_run_id"] is None
    assert status["quality_policy_error"] == "campaign_quality_reference_changed"
    with pytest.raises(ValueError, match="campaign_quality_reference_changed"):
        service.retention_plan("series")
    state = service.advance("series")
    assert state["status"] == "blocked"
    assert state["selected_run_id"] is None
    assert state["used_updates"] == 2
    assert artifact.exists()
    assert experiments.calls == [("start", first)]


def test_optuna_guard_keeps_measured_regression_separate_from_missing_evidence(
    controller, sampler, guarded_evidence
):
    service, experiments, _clock = controller
    _references, record = guarded_evidence
    start(service, guarded_spec(count=2, optimized=True))
    first = launch_next(service)
    experiments.finish(first, usable=3)
    record(first, {"b", "c", "d"})
    ranked = service.advance("series")
    assert ranked["selected_run_id"] is None
    assert sampler.outcomes[0] == ("COMPLETE", 0.25, [1.0, -0.25])

    second = launch_next(service)
    experiments.finish(second, usable=4)
    altered = record(second, {"a", "b", "c", "d"})
    altered["identity"]["protocol_sha256"] = "6" * 64
    final = service.advance("series")
    assert final["selected_run_id"] is None
    assert final["status"] == "blocked"
    assert final["trial_index"] == 1
    assert final["trials"][1]["quality_guard"]["status"] == "blocked"
    assert 1 not in sampler.outcomes
    altered["identity"]["protocol_sha256"] = "3" * 64
    service.resume("series")
    recovered = service.advance("series")
    assert recovered["status"] == "succeeded"
    assert recovered["selected_run_id"] == second
    assert sampler.outcomes[1] == ("COMPLETE", 0.5, [-0.5, -0.5])
    assert experiments.calls == [("start", first), ("start", second)]


def test_quality_guard_rejects_moved_critical_error_and_pins_actual_protocol(
    controller, guarded_evidence
):
    service, experiments, _clock = controller
    _references, record = guarded_evidence
    start(service, guarded_spec(count=2, policy={"protect_base_hits": True}))
    first = launch_next(service)
    experiments.finish(first, usable=2)
    measured = record(first, {"a", "c"}, {"b"})
    measured["cases"]["d"]["base"]["critical"] = True
    state = service.advance("series")
    guard = state["trials"][0]["quality_guard"]
    assert guard["status"] == "rejected"
    assert guard["new_critical_case_ids"] == ["b"]
    assert state["quality_protocol_sha256"] == "3" * 64

    second = launch_next(service)
    experiments.finish(second, usable=4)
    changed = record(second, {"a", "b", "c", "d"})
    changed["identity"]["protocol_sha256"] = "9" * 64
    completed = service.advance("series")
    assert completed["trials"][1]["quality_guard"]["status"] == "blocked"
    assert completed["selected_run_id"] is None


def test_draft_cannot_replace_pinned_training_data(tmp_path, monkeypatch):
    experiments = FakeExperiments(tmp_path)
    original = experiments.validate

    def validate(profile_id, recipe=None):
        verified = original(profile_id, recipe)
        verified["recipe"]["train_sha256"] = "b" * 64
        return verified

    monkeypatch.setattr(experiments, "validate", validate)
    spec = make_spec(count=1, variants=[{"train_sha256": "a" * 64}])
    service = CampaignService(experiments)
    with pytest.raises(ValueError, match="campaign_quality_training_identity_changed"):
        service.validate(spec)


def test_pinned_source_checks_train_and_runtime_before_campaign(
    controller, guarded_evidence
):
    service, experiments, _clock = controller
    references, _record = guarded_evidence
    source = references["prior"]
    spec = guarded_spec(policy={"source_record_id": "prior"})
    runtime = source["runtime"]
    source["runtime"] = {"loss": "unmatched"}
    with pytest.raises(ValueError, match="campaign_quality_runtime_identity_changed"):
        service.validate(spec)
    source["runtime"] = runtime
    source["train_sha256"] = "8" * 64
    with pytest.raises(ValueError, match="campaign_quality_training_identity_changed"):
        service.validate(spec)
    source["train_sha256"] = "7" * 64

    state = service.plan(spec)
    policy = state["plan"]["quality_policy"]
    assert policy["source_record"] == {
        "record_id": "prior",
        "result_sha256": "4" * 64,
        "train_sha256": "7" * 64,
        "runtime": runtime,
    }
    digest = state["plan"]["plan_sha256"]
    source["result_sha256"] = "8" * 64
    with pytest.raises(ValueError, match="campaign_quality_source_changed"):
        service.start("series", digest)
    assert experiments.calls == []


def test_pinned_source_rejects_mismatched_observed_runtime_and_reassesses_at_timeout(
    controller, guarded_evidence
):
    service, experiments, clock = controller
    references, record = guarded_evidence
    start(service, guarded_spec(count=1, policy={"source_record_id": "prior"}))
    run_id = launch_next(service)
    experiments.finish(run_id, usable=3)
    observed = record(run_id, {"a", "b", "c"}, runtime={"loss": "mismatch"})
    blocked = service.advance("series")
    assert blocked["status"] == "blocked"
    assert blocked["error"] == "campaign_quality_runtime_identity_changed"
    assert blocked["trial_index"] == 0
    assert blocked["selected_run_id"] is None

    clock.now += 51
    observed["runtime"] = references["prior"]["runtime"]
    assert service.resume("series")["status"] == "stopping"
    settled = service.advance("series")
    assert settled["status"] == "timed_out"
    assert settled["trials"][0]["quality_guard"]["status"] == "passed"
    assert settled["selected_run_id"] == run_id
    assert experiments.calls == [("start", run_id)]


def _automatic_final_controller(controller, monkeypatch):
    from venom_core.services.training_experiments import campaign, local_campaign_final

    service, experiments, clock = controller
    experiments.automatic = True
    frozen = {
        "inputs_id": "fresh",
        "reserve_seconds": 60,
        "inputs_sha256": "a" * 64,
        "final_test_sha256": "b" * 64,
        "final_calibration_sha256": "c" * 64,
    }
    monkeypatch.setattr(local_campaign_final, "freeze_inputs", lambda *_: frozen)
    monkeypatch.setattr(local_campaign_final, "pin_inputs", lambda *_: None)
    monkeypatch.setattr(
        campaign.quality_native, "frozen_evaluation_identity", lambda *_: {}
    )
    monkeypatch.setattr(service, "_verify_checkpoint_protocol", lambda *_: None)
    monkeypatch.setattr(service, "_verify_quality_winner", lambda *_: None)
    original_start = experiments.start

    def launch(*args, checkpoint_steps=None, **kwargs):
        run = original_start(*args, **kwargs)
        return experiments.update(run["run_id"], checkpoint_steps=checkpoint_steps)

    monkeypatch.setattr(experiments, "start", launch)

    def checkpoints(state, trial, _policy):
        trial["checkpoint_evaluations"] = [
            {
                "step": 2,
                "qualified": trial["usable_delta"] >= 0,
                "status": "succeeded",
                "result_sha256": trial["result_sha256"],
                "usable_delta": trial["usable_delta"],
                "critical_delta": trial["critical_delta"],
            }
        ]

    monkeypatch.setattr(service, "_record_checkpoint_results", checkpoints)
    spec = make_spec(
        count=1,
        review_mode="automatic",
        retention="keep_all",
        checkpoint_steps=[2],
        final_qualification={"inputs_id": "fresh", "reserve_seconds": 60},
        budget={
            **make_spec(count=1).budget.model_dump(),
            "max_seconds": 120,
            "trial_seconds": 30,
        },
    )
    return service, experiments, clock, spec


@pytest.mark.parametrize(
    "verdict", ["passed", "failed_quality", "incomplete_calibration"]
)
def test_one_normal_local_start_reaches_final_without_manual_command(
    controller, monkeypatch, verdict
):
    from venom_core.services.training_experiments import local_campaign_final

    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    started = start(service, spec)
    assert started["deadline_at"] == 220
    run = launch_next(service)
    experiments.finish(run, usable=3)
    clock.now += 10
    scheduled = service.advance("series")
    assert scheduled["phase"] == "qualification"
    assert scheduled["status"] == "qualifying"
    assert scheduled["selected_checkpoint_step"] == 2
    calls = []

    def evaluate(owner, state):
        assert owner is service
        calls.append(state["selected_run_id"])
        clock.now += 4
        return {"status": verdict, "qualified": None}

    monkeypatch.setattr(local_campaign_final, "_execute", evaluate)
    result = service.advance("series")
    assert calls == [run]
    assert result["phase"] == "complete"
    assert result["qualification_status"] == (
        "incomplete" if verdict == "incomplete_calibration" else verdict
    )
    assert result["elapsed_seconds"] == 14
    assert result["deadline_at"] == 220
    assert service.advance("series") == result
    assert len(calls) == 1


def test_local_final_retry_restart_uses_original_deadline(controller, monkeypatch):
    from venom_core.services.training_experiments import local_campaign_final

    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    service.advance("series")
    calls = []

    def failing(owner, state):
        local_campaign_final._check(owner, state["campaign_id"])
        calls.append(clock.now)
        raise OSError("temporary")

    monkeypatch.setattr(local_campaign_final, "_execute", failing)
    first = service.advance("series")
    assert first["qualification_status"] == "pending"
    assert first["qualification_attempts"] == 1
    first["worker"] = None
    service._save(service.directory("series"), first)
    clock.now = 221
    resumed = service.resume("series")
    assert resumed["deadline_at"] == 220
    result = service.advance("series")
    assert calls == [100]
    assert result["qualification_status"] == "incomplete"
    assert result["qualification"]["reason"] == "campaign_final_deadline_exhausted"
    assert result["elapsed_seconds"] == 121


def test_local_training_timeout_leaves_reserved_final_time(controller, monkeypatch):
    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    clock.now = 161
    scheduled = service.advance("series")
    assert scheduled["status"] == "qualifying"
    assert scheduled["training_status"] == "timed_out"
    assert scheduled["deadline_at"] - clock.now == 59


def test_local_no_eligible_candidate_is_a_quality_decision(controller, monkeypatch):
    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=1)
    result = service.advance("series")
    assert result["phase"] == "complete"
    assert result["selected_run_id"] is None
    assert result["qualification_status"] == "failed_quality"
    assert result["qualification"]["reason"] == "campaign_no_eligible_finalist"


def test_local_final_stop_prevents_evaluation(controller, monkeypatch):
    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    service.advance("series")
    assert service.stop("series")["status"] == "stopping"
    result = service.advance("series")
    assert result["qualification_status"] == "incomplete"
    assert result["qualification"]["reason"] == "campaign_final_stopped"


def test_local_final_busy_gpu_does_not_charge_retry_but_keeps_deadline(
    controller, monkeypatch
):
    from venom_core.services.training_experiments import local_campaign_final
    from venom_core.services.training_experiments.remote_text_qualification import (
        _QualificationDeferred,
    )

    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    service.advance("series")

    def busy(owner, state):
        local_campaign_final._check(owner, state["campaign_id"])
        raise _QualificationDeferred("remote_text_final_gpu_busy")

    monkeypatch.setattr(local_campaign_final, "_execute", busy)
    for _ in range(2):
        result = service.advance("series")
        assert result["qualification_attempts"] == 0
        assert result["qualification_status"] == "pending"
    clock.now = 221
    result = service.advance("series")
    assert result["qualification_status"] == "incomplete"
    assert result["qualification"]["reason"] == "campaign_final_deadline_exhausted"


def test_local_pending_recovers_interrupted_session_without_renewing_deadline(
    controller, monkeypatch
):
    from venom_core.services.training_experiments import campaign, local_campaign_final

    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    state = service.advance("series")
    state["worker"] = None
    service._save(service.directory("series"), state)
    monkeypatch.setattr(campaign, "CampaignService", lambda *_: service)
    assert local_campaign_final.resume_pending(experiments.root) == {
        "status": "qualifying",
        "campaign_id": "series",
    }
    assert service.status("series")["deadline_at"] == 220
    assert local_campaign_final.resume_pending(experiments.root) == {"status": "idle"}


def test_local_final_runtime_failure_is_bounded_and_reported(controller, monkeypatch):
    from venom_core.services.runtime_admission import RuntimeAdmissionError
    from venom_core.services.training_experiments import local_campaign_final

    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    service.advance("series")

    def failed(*_args):
        raise RuntimeAdmissionError("runtime_storage_unsafe")

    monkeypatch.setattr(local_campaign_final, "_execute", failed)
    assert service.advance("series")["qualification_status"] == "pending"
    result = service.advance("series")
    assert result["qualification_attempts"] == 2
    assert result["qualification_status"] == "incomplete"
    assert (
        result["qualification"]["reason"] == "campaign_final_runtime_admission_failed"
    )
    assert service.advance("series") == result


def test_system_supervisor_recovers_local_final_without_panel_polling(
    controller, monkeypatch
):
    from venom_core.services.training_experiments import campaign
    from venom_core.services.training_experiments import (
        remote_text_supervisor as supervisor,
    )

    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    state = service.advance("series")
    state["worker"] = None
    service._save(service.directory("series"), state)
    clock.now = 151
    monkeypatch.setattr(campaign, "CampaignService", lambda *_: service)
    launches = []
    identity = process_identity(os.getpid())
    monkeypatch.setattr(
        service, "_launch", lambda cid: launches.append(cid) or identity
    )
    iterations = []

    def tick(_seconds):
        iterations.append(True)
        if len(iterations) == 2:
            raise InterruptedError("test supervisor shutdown")

    monkeypatch.setattr(supervisor.time, "sleep", tick)
    with pytest.raises(InterruptedError, match="test supervisor shutdown"):
        supervisor.supervise(None, academy_root=experiments.root)
    restored = service._state(service.directory("series"))
    assert restored["status"] == "qualifying"
    assert restored["deadline_at"] == 220
    assert restored["qualification_attempts"] == 0
    assert launches == ["series"]


def test_system_recovery_quiesces_trials_when_frozen_inputs_changed(
    controller, monkeypatch
):
    from venom_core.services.training_experiments import campaign, local_campaign_final

    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    state = service._state(service.directory("series"))
    state["worker"] = None
    service._save(service.directory("series"), state)
    monkeypatch.setattr(campaign, "CampaignService", lambda *_: service)

    def changed(*_args):
        raise ValueError("campaign_final_inputs_changed")

    monkeypatch.setattr(local_campaign_final, "pin_inputs", changed)
    assert local_campaign_final.resume_pending(experiments.root)["status"] == "stopping"
    result = service.advance("series")
    assert experiments.status(run)["status"] == "stopped"
    assert result["phase"] == "complete"
    assert result["qualification_status"] == "incomplete"
    assert result["qualification"]["reason"] == "campaign_final_inputs_changed"


def test_local_recovery_failure_does_not_block_remote_cleanup(controller, monkeypatch):
    from types import SimpleNamespace

    from venom_core.services.training_experiments import (
        remote_text_supervisor as supervisor,
    )

    service, _experiments, _clock = controller
    calls = []

    def local_failure(_root):
        raise ValueError("campaign_final_inputs_changed")

    def remote_tick(campaign_id):
        calls.append(campaign_id)
        if campaign_id == "first":
            raise OSError("temporary")

    def shutdown(_seconds):
        raise InterruptedError("test supervisor shutdown")

    remote = SimpleNamespace(
        local=service,
        heartbeat=lambda: calls.append("heartbeat"),
        list=lambda: [
            {"campaign_id": "first", "status": "running"},
            {"campaign_id": "finished", "status": "completed"},
            {"campaign_id": "cleanup", "status": "cleanup_pending"},
        ],
        tick=remote_tick,
    )
    monkeypatch.setattr(supervisor, "resume_pending", local_failure)
    monkeypatch.setattr(supervisor.time, "sleep", shutdown)
    with pytest.raises(InterruptedError, match="test supervisor shutdown"):
        supervisor.supervise(remote)
    assert calls == ["heartbeat", "first", "cleanup"]


def _repeat_campaign(controller, guarded_evidence, monkeypatch):
    from venom_core.services.training_experiments import campaign

    service, experiments, clock = controller
    references, record = guarded_evidence
    parent = {"adapter_id": "fixture-parent", "weights_sha256": "8" * 64}
    references["prior"]["candidate_sha256"] = parent["weights_sha256"]
    for case_id, case in references["prior"]["cases"].items():
        case["candidate"]["usable"] = case_id in {"a", "c"}
    experiments.automatic = True
    original_validate = experiments.validate

    def validate(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        result["initial_adapter"] = parent
        result["workload"]["tokens"] = result["recipe"]["max_supervised_tokens"]
        return result

    original_start = experiments.start

    def launch(profile_id, run_id, recipe, **kwargs):
        recipe = {
            key: value for key, value in recipe.items() if key != "initial_adapter_id"
        }
        result = original_start(profile_id, run_id, recipe, **kwargs)
        return experiments.update(
            result["run_id"], initial_adapter=kwargs["expected_initial_adapter"]
        )

    monkeypatch.setattr(experiments, "validate", validate)
    monkeypatch.setattr(experiments, "start", launch)
    monkeypatch.setattr(campaign, "verify_adapter_entry", lambda *_: experiments.root)
    variants = [
        {
            "rank": 2,
            "learning_rate": lr,
            "seed": seed,
            "max_supervised_tokens": 40 if seed == 42 else 42,
        }
        for seed in (42, 43)
        for lr in (0.001, 0.002)
    ]
    spec = make_spec(
        count=4,
        variants=variants,
        review_mode="automatic",
        retention="keep_all",
        extension={
            "initial_trials": 2,
            "min_usable_delta": 0.25,
            "repeat_best_recipe": True,
        },
        quality_policy={
            "reference_record_ids": ["prior"],
            "parent_reference_record_id": "prior",
        },
        budget={
            **make_spec().budget.model_dump(),
            "max_trials": 3,
            "max_updates": 6,
            "max_tokens": 122,
        },
    )
    return service, experiments, clock, spec, record


@pytest.mark.parametrize("winner", [0, 1])
def test_repeat_best_runs_only_frozen_copy_of_parent_relative_winner_after_restart(
    controller, guarded_evidence, monkeypatch, winner
):
    import copy

    service, experiments, clock, spec, record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    planned = start(service, spec)
    frozen = copy.deepcopy(planned["plan"])
    initial = []
    for index in range(2):
        run = launch_next(service)
        initial.append(run)
        # Deliberately conflicting M0 diagnostics prove that parent_delta selects.
        experiments.finish(run, usable=3 if index == winner else 4)
        record(run, {"a", "b", "c"} if index == winner else {"a", "c"})
        service.advance("series")
    assert service.status("series")["selected_run_id"] == initial[winner]
    routed = service.advance("series")
    repeated = frozen["variants"][winner + 2]["run_id"]
    skipped = frozen["variants"][3 - winner]["run_id"]
    assert routed["extension_decision"]["repeat_run_id"] == repeated
    assert routed["extension_decision"]["run_id"] == initial[winner]
    assert routed["extension_decision"]["usable_delta"] == 0.25
    assert (
        next(item for item in routed["trials"] if item["run_id"] == skipped)["status"]
        == "skipped"
    )

    routed["worker"] = None
    service._save(service.directory("series"), routed)
    restored = CampaignService(
        experiments, clock=clock, launch=lambda _: process_identity(os.getpid())
    )
    restored.resume("series")
    for _ in range(2):
        restored.advance("series")
        if experiments.calls[-1] == ("start", repeated):
            break
    assert experiments.calls[-1] == ("start", repeated)
    assert (
        experiments.status(repeated)["recipe"]
        == frozen["variants"][winner + 2]["recipe"]
    )
    experiments.finish(repeated, usable=3)
    record(repeated, {"a", "b", "c"})
    finished = restored.advance("series")
    if finished["status"] == "running":
        finished = restored.advance("series")
    assert finished["status"] == "succeeded"
    assert len(experiments.calls) == 3
    assert finished["used_updates"] == 6
    assert finished["used_tokens"] == 122
    assert finished["plan"] == frozen
    assert finished["plan"]["budget"]["max_trials"] == 3


@pytest.mark.parametrize("critical", [False, True])
def test_repeat_best_skips_all_alternatives_without_protected_parent_gain(
    controller, guarded_evidence, monkeypatch, critical
):
    service, experiments, _clock, spec, record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    start(service, spec)
    for _ in range(2):
        run = launch_next(service)
        experiments.finish(run, usable=4)
        record(
            run, {"a", "b", "c"} if critical else {"a", "c"}, {"d"} if critical else ()
        )
        service.advance("series")
    finished = service.advance("series")
    assert finished["status"] == "succeeded"
    assert finished["extension_decision"]["status"] == "skipped"
    assert all(trial["status"] == "skipped" for trial in finished["trials"][2:])
    assert len(experiments.calls) == 2


@pytest.mark.parametrize(
    ("usable_hits", "full_hits", "reason", "parent_gain", "full_gain"),
    [
        (
            {"a", "b", "c", "d"},
            {"b", "c", "d"},
            "parent_full_pass_lost",
            0.5,
            0.25,
        ),
        ({"a", "c"}, {"a", "c"}, "parent_full_pass_no_gain", 0.0, 0.0),
        ({"a", "b", "c"}, {"a", "b", "c"}, None, 0.25, 0.25),
    ],
    ids=["higher-score-with-regression", "parent-tie", "retained-parent-gain"],
)
def test_automatic_checkpoint_campaign_gates_repetition_against_parent(
    controller,
    guarded_evidence,
    monkeypatch,
    usable_hits,
    full_hits,
    reason,
    parent_gain,
    full_gain,
):
    from venom_core.services.training_experiments import quality_native

    service, experiments, _clock, spec, record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    references, _ = guarded_evidence
    parent = references["prior"]
    for case in parent["cases"].values():
        case["candidate"]["passed"] = case["candidate"]["usable"]
    monkeypatch.setattr(
        quality_native, "frozen_evaluation_identity", lambda *_: parent["identity"]
    )
    launch = experiments.start

    def start_with_checkpoints(*args, checkpoint_steps, **kwargs):
        started = launch(*args, **kwargs)
        return experiments.update(started["run_id"], checkpoint_steps=checkpoint_steps)

    monkeypatch.setattr(experiments, "start", start_with_checkpoints)

    reports = {}
    native_records = {}

    def checkpoint_report(run_id, step):
        report_path = reports[run_id, step]
        return read_object(report_path), file_fingerprint(report_path)

    def completed_checkpoint(run_id, step):
        experiments.finish(run_id, usable=len(usable_hits))
        path = experiments.run_dir(run_id) / f"checkpoint-result-{step}.json"
        report = experiments.report(run_id)
        report["summaries"]["base"]["total"]["usable"] = 1
        report["checkpoint"] = {"step": step}
        atomic_json(path, report)
        reports[run_id, step] = path
        evidence = record(
            run_id, usable_hits, source={"sha256": file_fingerprint(path)}
        )
        for name, case in evidence["cases"].items():
            case["base"]["usable"] = name == "a"
            case["candidate"]["passed"] = name in full_hits
        native_records[run_id, step] = evidence

    monkeypatch.setattr(
        experiments, "checkpoint_report", checkpoint_report, raising=False
    )
    monkeypatch.setattr(
        quality_native,
        "native_record",
        lambda _experiments, rid, step: native_records[rid, step],
    )
    values = spec.model_dump()
    values["checkpoint_steps"] = [2]
    values["selection"].update(min_usable_delta=0.25, protect_parent_full_pass=True)
    values["quality_policy"]["protect_parent_full_pass"] = True
    start(service, CampaignSpec.model_validate(values))
    initial_runs = []
    for index in range(2):
        run_id = launch_next(service)
        initial_runs.append(run_id)
        completed_checkpoint(run_id, 2)
        result = service.advance("series")
        checkpoint = result["trials"][index]["checkpoint_evaluations"][0]
        guard = checkpoint["quality_guard"]
        assert checkpoint["m0_usable_delta"] == (len(usable_hits) - 1) / 4
        assert checkpoint["usable_delta"] == parent_gain
        assert guard["parent_delta"]["full_pass_delta"] == full_gain
        assert checkpoint["qualified"] is (reason is None)
        assert {row["code"] for row in guard["reasons"]} == (
            {reason} if reason else set()
        )
        assert guard["lost_parent_full_pass_case_ids"] == (
            ["a"] if reason == "parent_full_pass_lost" else []
        )

    if reason is not None:
        finished = service.advance("series")
        assert finished["selected_run_id"] is None
        assert finished["selected_checkpoint_step"] is None
        assert finished["extension_decision"]["status"] == "skipped"
        assert finished["repeat_confirmation"]["status"] == "failed_quality"
        assert experiments.calls == [("start", run) for run in initial_runs]
        return

    repeat = launch_next(service)
    selected = service.status("series")
    decision = selected["extension_decision"]
    assert decision["status"] == "approved"
    assert decision["run_id"] in initial_runs
    assert decision["checkpoint_step"] == 2
    assert decision["repeat_run_id"] == repeat
    assert selected["plan"]["variants"][2]["recipe"]["seed"] == 43
    completed_checkpoint(repeat, 2)
    service.advance("series")
    finished = service.advance("series")
    assert finished["status"] == "succeeded"
    assert finished["repeat_confirmation"]["status"] == "passed"
    assert finished["selected_checkpoint_step"] == 2
    assert experiments.calls == [("start", run) for run in (*initial_runs, repeat)]


@pytest.mark.parametrize("mutation", ["seed", "recipe", "duplicate", "budget"])
def test_repeat_best_freeze_rejects_unmatched_or_unbudgeted_alternative(
    controller, guarded_evidence, monkeypatch, mutation
):
    service, _experiments, _clock, spec, _record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    values = spec.model_dump()
    if mutation == "seed":
        values["variants"][2]["seed"] = 42
    elif mutation == "recipe":
        values["variants"][2]["rank"] = 3
    elif mutation == "duplicate":
        values["variants"][3]["learning_rate"] = 0.001
        values["variants"][3]["seed"] = 44
    else:
        values["budget"]["max_tokens"] = 121
    with pytest.raises(
        ValueError,
        match="repeat_recipe_mismatch|duplicate_variant|token_budget_exceeded",
    ):
        service.plan(CampaignSpec.model_validate(values))
    assert service.list() == []


def test_repeat_best_schema_requires_parent_and_single_repeat_budget(
    controller, guarded_evidence, monkeypatch
):
    _service, _experiments, _clock, spec, _record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    values = spec.model_dump()
    values["quality_policy"]["parent_reference_record_id"] = None
    with pytest.raises(ValueError, match="repeat_recipe_invalid"):
        CampaignSpec.model_validate(values)
    values = spec.model_dump()
    values["budget"]["max_trials"] = 2
    with pytest.raises(ValueError, match="trial_budget_exceeded"):
        CampaignSpec.model_validate(values)
    values = spec.model_dump()
    values["quality_policy"].update(
        parent_reference_record_id=None, protect_parent_full_pass=True
    )
    with pytest.raises(ValueError, match="parent_reference_missing"):
        CampaignSpec.model_validate(values)


def test_repeat_recipe_rejects_different_parent_before_planning(
    controller, guarded_evidence, monkeypatch
):
    service, experiments, _clock, spec, _record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    validated = experiments.validate

    def different(*args, **kwargs):
        result = validated(*args, **kwargs)
        if result["recipe"]["seed"] == 43:
            result["initial_adapter"] = {
                **result["initial_adapter"],
                "weights_sha256": "9" * 64,
            }
        return result

    monkeypatch.setattr(experiments, "validate", different)
    with pytest.raises(ValueError, match="repeat_parent_changed"):
        service.plan(spec)
    assert service.list() == []


def test_parent_full_pass_breaks_otherwise_equal_checkpoint_quality():
    from venom_core.services.training_experiments.campaign import _rank

    checkpoints = [
        {
            "step": 2,
            "qualified": True,
            "usable_delta": 0.25,
            "critical_delta": 0.0,
            "quality_guard": {
                "status": "passed",
                "parent_delta": {"full_pass_delta": delta},
            },
        }
        for delta in (0.25, 0.5)
    ]
    state = {
        "plan": {"checkpoint_steps": [2]},
        "trials": [
            {
                "run_id": f"trial-{index}",
                "status": "succeeded",
                "checkpoint_evaluations": [checkpoint],
            }
            for index, checkpoint in enumerate(checkpoints)
        ],
    }
    _rank(state)
    assert state["selected_run_id"] == "trial-1"
    assert state["selected_checkpoint_step"] == 2


@pytest.mark.parametrize(
    "full_delta,expected", [(None, False), (0.0, False), (0.125, False), (0.25, True)]
)
def test_full_parent_gain_must_meet_selection_threshold_for_repeat(
    full_delta, expected
):
    from venom_core.services.training_experiments.campaign import (
        _allow_extension,
        _passes_selection,
    )

    winner = {
        "run_id": "first",
        "usable_delta": 0.5,
        "critical_delta": 0.0,
        "result_sha256": "a" * 64,
        "quality_guard": {
            "status": "passed",
            "parent_delta": {"full_pass_delta": full_delta},
        },
    }
    selection = {
        "min_usable_delta": 0.25,
        "max_critical_delta": 0.0,
        "protect_parent_full_pass": True,
    }
    assert _passes_selection(winner, selection) is expected
    state = {
        "plan": {
            "selection": selection,
            "extension": {"initial_trials": 1, "min_usable_delta": 0.25},
        },
        "trial_index": 1,
        "selected_run_id": "first",
        "trials": [winner],
    }
    assert _allow_extension(state) is expected
    assert state["extension_decision"]["full_pass_delta"] == full_delta


@pytest.mark.parametrize(
    "outcome,confirmation_status",
    [("passed", "passed"), ("quality", "failed_quality"), ("execution", "incomplete")],
)
def test_repeat_is_required_confirmation_before_opening_holdout(
    controller, guarded_evidence, monkeypatch, outcome, confirmation_status
):
    from venom_core.services.training_experiments.local_campaign_final import transition

    service, experiments, _clock, spec, record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    start(service, spec)
    source = None
    for index in range(2):
        run = launch_next(service)
        if index == 0:
            source = run
        experiments.finish(run, usable=4 if index == 0 else 2)
        record(run, {"a", "b", "c", "d"} if index == 0 else {"a", "c"})
        service.advance("series")
    service.advance("series")  # select the first recipe's frozen seed-43 alternative
    launched = service.advance("series")
    repeated = launched["extension_decision"]["repeat_run_id"]
    if outcome == "execution":
        experiments.update(repeated, status="failed", resume_available=False)
    else:
        experiments.finish(repeated, usable=3 if outcome == "passed" else 2)
        record(repeated, {"a", "b", "c"} if outcome == "passed" else {"a", "c"})
    service.advance("series")
    finished = service.advance("series")  # consume the non-selected alternative
    proof = finished["repeat_confirmation"]
    assert proof["status"] == confirmation_status
    assert proof["source_run_id"] == source
    assert proof["repeat_run_id"] == repeated
    assert finished["selected_run_id"] == (source if outcome == "passed" else None)
    assert len(experiments.calls) == 3
    if outcome == "passed":
        assert proof["repeat_result_sha256"]
        assert proof["usable_delta"] == 0.25
        assert service.report("series")["repeat_confirmation"]["status"] == "passed"
        # The confirmation must remain valid even when the first seed is finalist.
        record(repeated, {"a", "b", "c"}, source={"sha256": "0" * 64})
        invalid = service.report("series")
        assert invalid["repeat_confirmation"]["status"] == "incomplete"
        assert invalid["selected_run_id"] is None

    # CampaignService uses this same final transition after confirming the repeat.
    finished["phase"] = "trials"
    finished["plan"]["final_qualification"] = {"inputs_id": "unopened"}
    transition(finished)
    assert finished["phase"] == ("qualification" if outcome == "passed" else "complete")
    if outcome != "passed":
        assert finished["qualification_status"] == confirmation_status
        assert finished["qualification"]["qualified"] is None


@pytest.mark.parametrize(
    "repeat_at_21,source_at_63,expected,final_step",
    [
        (0.0, 0.1, "failed_quality", None),
        (None, 0.1, "incomplete", None),
        (0.1, 0.1, "passed", 63),
        (0.1, 0.0, "passed", 21),
    ],
)
def test_repeat_confirms_same_training_dose_and_finalist_requires_both_seeds(
    repeat_at_21, source_at_63, expected, final_step
):
    from venom_core.services.training_experiments.campaign import _confirm_repeat

    def checkpoint(step, delta, digest_prefix):
        return {
            "step": step,
            "status": "succeeded",
            "result_sha256": digest_prefix * 64,
            "usable_delta": delta,
            "critical_delta": 0.0,
            "quality_guard": {
                "status": "passed",
                "parent_delta": {"full_pass_delta": delta},
            },
        }

    repeat_rows = [checkpoint(63, 0.5, "d")]
    if repeat_at_21 is not None:
        repeat_rows.insert(0, checkpoint(21, repeat_at_21, "c"))
    state = {
        "status": "succeeded",
        "selected_run_id": "source",
        "selected_checkpoint_step": 21,
        "plan": {
            "checkpoint_steps": [21, 63],
            "selection": {
                "min_usable_delta": 0.05,
                "max_critical_delta": 0.0,
                "protect_parent_full_pass": True,
            },
            "extension": {"repeat_best_recipe": True, "min_usable_delta": 0.05},
        },
        "extension_decision": {
            "status": "approved",
            "run_id": "source",
            "checkpoint_step": 21,
            "result_sha256": "a" * 64,
            "repeat_run_id": "repeat",
        },
        "trials": [
            {
                "run_id": "source",
                "status": "succeeded",
                "checkpoint_evaluations": [
                    checkpoint(21, 0.3, "a"),
                    checkpoint(63, source_at_63, "b"),
                ],
            },
            {
                "run_id": "repeat",
                "status": "succeeded",
                "checkpoint_evaluations": repeat_rows,
            },
        ],
    }
    _confirm_repeat(state)
    proof = state["repeat_confirmation"]
    assert proof["status"] == expected
    assert state["selected_checkpoint_step"] == final_step
    if expected == "passed":
        assert proof["source_checkpoint_step"] == proof["repeat_checkpoint_step"] == 21
        assert proof["finalist_checkpoint_step"] == final_step
        assert (
            proof["paired_source_result_sha256"]
            == ("b" if final_step == 63 else "a") * 64
        )
        assert (
            proof["paired_repeat_result_sha256"]
            == ("d" if final_step == 63 else "c") * 64
        )
    else:
        assert state["selected_run_id"] is None


def _original_incomplete_development_state():
    def checkpoint(step, usable, passed):
        return {
            "step": step,
            "status": "succeeded",
            "result_sha256": str(step % 10) * 64,
            "qualified": False,
            "usable_delta": (usable - 37) / 48,
            "critical_delta": 0.0,
            "quality_guard": {
                "status": "rejected",
                "parent_delta": {"full_pass_delta": (passed - 33) / 48},
            },
            "summaries": {
                "candidate": {"total": {"n": 48, "usable": usable, "passed": passed}}
            },
        }

    return {
        "status": "succeeded",
        "phase": "trials",
        "trial_index": 4,
        "selected_run_id": None,
        "selected_checkpoint_step": None,
        "qualification_status": "pending",
        "qualification_attempts": 0,
        "retries": 1,
        "deadline_at": 1794923315.6446989,
        "plan": {
            "checkpoint_steps": [21, 42, 63],
            "quality_policy": {"protect_parent_full_pass": True},
            "selection": {
                "min_usable_delta": 0.05,
                "max_critical_delta": 0,
                "protect_parent_full_pass": True,
            },
            "extension": {
                "repeat_best_recipe": True,
                "initial_trials": 2,
                "min_usable_delta": 0.05,
            },
            "final_qualification": {"inputs_id": "unopened"},
        },
        "extension_decision": {
            "status": "skipped",
            "run_id": None,
            "checkpoint_step": None,
        },
        "trials": [
            {
                "run_id": "trial01",
                "status": "failed",
                "stage": "score",
                "attempt": 2,
                "error": "experiment_checkpoint_baseline_changed",
                "checkpoint_evaluations": [
                    checkpoint(21, 38, 34),
                    {"step": 42, "status": "pending"},
                    {"step": 63, "status": "pending"},
                ],
            },
            {
                "run_id": "trial02",
                "status": "succeeded",
                "result_sha256": "b" * 64,
                "checkpoint_evaluations": [
                    checkpoint(21, 37, 33),
                    checkpoint(42, 36, 34),
                    checkpoint(63, 36, 34),
                ],
            },
            {"run_id": "trial03", "status": "skipped"},
            {"run_id": "trial04", "status": "skipped"},
        ],
    }


@pytest.mark.parametrize("with_repeat", [False, True])
@pytest.mark.parametrize(
    "evidence",
    [
        "failed_score",
        "missing_step",
        "pending_step",
        "missing_seal",
        "blocked_guard",
        "complete",
    ],
)
def test_no_candidate_requires_all_expected_development_evidence(with_repeat, evidence):
    import copy

    from venom_core.services.training_experiments.campaign import _confirm_repeat
    from venom_core.services.training_experiments.local_campaign_final import transition

    state = _original_incomplete_development_state()
    first, second = state["trials"][:2]
    if evidence != "failed_score":
        first.update(
            status="succeeded",
            result_sha256="a" * 64,
            checkpoint_evaluations=copy.deepcopy(second["checkpoint_evaluations"]),
        )
        rows = first["checkpoint_evaluations"]
        if evidence == "missing_step":
            rows.pop(1)
        elif evidence == "pending_step":
            rows[1]["status"] = "pending"
        elif evidence == "missing_seal":
            rows[1].pop("result_sha256")
        elif evidence == "blocked_guard":
            rows[1]["quality_guard"]["status"] = "blocked"
    if not with_repeat:
        state["plan"].pop("extension")
    before = copy.deepcopy(state)
    _confirm_repeat(state)
    transition(state)
    expected = "failed_quality" if evidence == "complete" else "incomplete"
    assert state["phase"] == "complete"
    assert state["qualification_status"] == expected
    assert state["qualification"]["qualified"] is None
    assert state["selected_run_id"] is None
    assert state["qualification_attempts"] == 0
    assert state["deadline_at"] == before["deadline_at"]
    assert state["retries"] == before["retries"] == 1
    assert state["trials"] == before["trials"]
    if evidence != "complete":
        assert state["qualification"]["reason"] == "campaign_development_incomplete"
    if with_repeat:
        assert state["repeat_confirmation"]["status"] == expected


def test_confirmed_finalist_survives_an_unrelated_failed_development_variant():
    import copy

    from venom_core.services.training_experiments.campaign import (
        _confirm_repeat,
        development_complete,
    )
    from venom_core.services.training_experiments.local_campaign_final import transition

    state = _original_incomplete_development_state()
    source = state["trials"][1]
    for row in source["checkpoint_evaluations"]:
        row.update(qualified=True, usable_delta=0.125, critical_delta=0.0)
        row["quality_guard"] = {
            "status": "passed",
            "parent_delta": {"full_pass_delta": 0.125},
        }
    repeated = {**copy.deepcopy(source), "run_id": "trial04"}
    state["trials"][3] = repeated
    state["selected_run_id"] = source["run_id"]
    state["selected_checkpoint_step"] = 21
    state["extension_decision"] = {
        "status": "approved",
        "run_id": source["run_id"],
        "checkpoint_step": 21,
        "result_sha256": source["checkpoint_evaluations"][0]["result_sha256"],
        "repeat_run_id": repeated["run_id"],
    }
    assert not development_complete(state)
    deadline = state["deadline_at"]
    _confirm_repeat(state)
    assert state["repeat_confirmation"]["status"] == "passed"
    assert state["selected_run_id"] in {"trial02", "trial04"}
    transition(state)
    assert state["phase"] == "qualification"
    assert state["status"] == "qualifying"
    assert state["qualification_status"] == "pending"
    assert state["deadline_at"] == deadline
    assert state["qualification_attempts"] == 0


@pytest.mark.parametrize("problem", ["empty", "quality_policy_error", "missing_result"])
def test_incomplete_development_without_checkpoints_is_not_quality_rejection(problem):
    from venom_core.services.training_experiments.campaign import development_complete

    state = {
        "plan": {},
        "trials": [{"status": "succeeded", "result_sha256": "a" * 64}],
    }
    assert development_complete(state)
    if problem == "empty":
        state["trials"] = [{"status": "skipped"}]
    elif problem == "quality_policy_error":
        state["quality_policy_error"] = "campaign_quality_evidence_changed"
    else:
        state["trials"][0].pop("result_sha256")
    assert not development_complete(state)


@pytest.mark.parametrize(
    "policy",
    [None, {"reference_record_ids": ["prior"], "parent_reference_record_id": "prior"}],
)
def test_selection_full_pass_requires_a_complete_parent_policy(policy):
    with pytest.raises(ValueError, match="parent_full_pass_policy_required"):
        make_spec(selection={"protect_parent_full_pass": True}, quality_policy=policy)


def test_retention_keeps_repeat_source_until_confirmation(controller):
    retention, state, source, _winner = retained_series(controller)
    state["extension_decision"] = {"run_id": state["trials"][0]["run_id"]}
    assert retention.plan(state)["files"] == []
    state["repeat_confirmation"] = {"status": "incomplete"}
    assert retention.plan(state)["files"] == []
    state["repeat_confirmation"] = {"status": "passed"}
    assert any(
        row["run_id"] == state["trials"][0]["run_id"]
        for row in retention.plan(state)["files"]
    )
    assert source.exists()


@pytest.mark.parametrize("event", ["receipt", "expired", "stopped"])
def test_local_final_waits_without_spending_retries(controller, monkeypatch, event):
    from unittest.mock import Mock

    from venom_core.services.training_experiments import local_campaign_final

    service, experiments, clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    state = service.advance("series")
    config = state["plan"]["final_qualification"]
    review_id = "final-" + "a" * 58
    config.update(conversation_review_required=True, conversation_review_id=review_id)
    directory = service.directory("series")
    service._save(directory, state)
    evaluator = Mock(return_value={"status": "failed_quality", "qualified": None})
    monkeypatch.setattr(local_campaign_final, "_execute", evaluator)

    for _ in range(2):
        waiting = service.advance("series")
        assert waiting["status"] == "qualifying"
        assert waiting["qualification_status"] == "pending_conversation_review"
        assert waiting["qualification_attempts"] == waiting["retries"] == 0
    evaluator.assert_not_called()

    if event == "receipt":
        receipt = (
            experiments.root
            / "local-text-qualification"
            / "series"
            / "evidence"
            / "conversation-reviews"
            / review_id
            / "receipt.json"
        )
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{}", encoding="utf-8")
    elif event == "expired":
        clock.now = state["deadline_at"]
    else:
        service.stop("series")

    final = service.advance("series")
    assert final["phase"] == "complete"
    if event == "receipt":
        evaluator.assert_called_once()
        assert final["qualification_attempts"] == 1
        assert final["qualification_status"] == "failed_quality"
    else:
        evaluator.assert_not_called()
        assert final["qualification_attempts"] == 0
        assert final["qualification_status"] == "incomplete"
        assert final["qualification"]["reason"] == (
            "campaign_final_deadline_exhausted"
            if event == "expired"
            else "campaign_final_stopped"
        )


def test_local_final_consumes_shared_retry_budget(controller, monkeypatch):
    from venom_core.services.training_experiments import local_campaign_final

    service, experiments, _clock, spec = _automatic_final_controller(
        controller, monkeypatch
    )
    start(service, spec)
    run = launch_next(service)
    experiments.finish(run, usable=3)
    state = service.advance("series")
    state["retries"] = state["plan"]["budget"]["max_retries"]
    service._save(service.directory("series"), state)
    calls = []

    def failing(*_args):
        calls.append(True)
        raise OSError("temporary")

    monkeypatch.setattr(local_campaign_final, "_execute", failing)
    result = service.advance("series")
    assert result["qualification_attempts"] == 1
    assert result["qualification_status"] == "incomplete"
    service.advance("series")
    assert calls == [True]


@pytest.mark.parametrize("failure", ["heartbeat", "list"])
def test_remote_supervisor_read_failure_keeps_local_recovery(
    controller, monkeypatch, failure
):
    from venom_core.services.training_experiments import (
        remote_text_supervisor as supervisor,
    )

    _service, experiments, _clock = controller
    local = []
    monkeypatch.setattr(supervisor, "resume_pending", lambda _root: local.append(True))

    class Remote:
        local = type("Local", (), {"experiments": experiments})()

        def heartbeat(self):
            if failure == "heartbeat":
                raise OSError("heartbeat unavailable")

        def list(self):
            if failure == "list":
                raise ValueError("bad remote state")
            return []

    ticks = []

    def stop_after_two(_seconds):
        ticks.append(True)
        if len(ticks) == 2:
            raise InterruptedError("shutdown")

    monkeypatch.setattr(supervisor.time, "sleep", stop_after_two)
    remote = Remote()
    with pytest.raises(InterruptedError, match="shutdown"):
        supervisor.supervise(remote, academy_root=experiments.root)
    assert local == [True, True]


def test_repeat_selection_recovers_after_stop_before_extension(
    controller, guarded_evidence, monkeypatch
):
    service, experiments, _clock, spec, record = _repeat_campaign(
        controller, guarded_evidence, monkeypatch
    )
    start(service, spec)
    first = None
    for index in range(2):
        run = launch_next(service)
        if index == 0:
            first = run
        experiments.finish(run, usable=4 if index == 0 else 2)
        record(run, {"a", "b", "c", "d"} if index == 0 else {"a", "c"})
        service.advance("series")
    service.stop("series")
    stopped = service.advance("series")
    assert stopped["selected_run_id"] is None
    service.resume("series")
    resumed = service.advance("series")
    assert resumed["extension_decision"]["status"] == "approved"
    assert resumed["extension_decision"]["run_id"] == first


def test_selection_rejects_unavailable_parent_critical_metric_without_exception():
    from venom_core.services.training_experiments.campaign import (
        _parent_metrics,
        _passes_selection,
    )

    item = {"usable_delta": 0.25, "critical_delta": 0.0}
    _parent_metrics(
        item, {"parent_delta": {"usable_delta": 0.25, "critical_delta": None}}
    )
    assert item["critical_delta"] is None
    assert not _passes_selection(
        item, {"min_usable_delta": 0.0, "max_critical_delta": 0.0}
    )


def test_review_refresh_updates_only_requested_checkpoint_rows():
    from venom_core.services.training_experiments.campaign import CampaignService

    service = object.__new__(CampaignService)
    service._verify_quality_policy = lambda _plan: None
    service._assess_checkpoint = lambda _state, _run, step, _policy: {
        "step": step,
        "status": "succeeded",
        "result_sha256": f"new-{step}",
    }
    passed = {"step": 13, "status": "succeeded", "result_sha256": "approved-A"}
    pending = {
        "step": 26,
        "status": "succeeded",
        "result_sha256": "old-B",
        "conversation_review_status": "pending",
    }
    state = {"plan": {"checkpoint_steps": [13, 26]}}
    trial = {"run_id": "run", "checkpoint_evaluations": [passed, pending]}

    service._record_checkpoint_results(state, trial, None, steps={26})

    assert trial["checkpoint_evaluations"] == [
        passed,
        {"step": 26, "status": "succeeded", "result_sha256": "new-26"},
    ]


def test_review_refresh_assesses_pending_steps_once_per_trial(tmp_path, monkeypatch):
    from venom_core.services.training_experiments import campaign
    from venom_core.services.training_experiments.conversation_review import (
        checkpoint_review_id,
    )

    service = object.__new__(CampaignService)
    service.directory = lambda _campaign_id: tmp_path
    calls = []
    service._record_checkpoint_results = (
        lambda _state, trial, _policy, *, steps: calls.append((trial["run_id"], steps))
    )
    monkeypatch.setattr(campaign, "_rank", lambda _state: None)
    trial = {
        "run_id": "run",
        "status": "succeeded",
        "checkpoint_evaluations": [
            {"step": step, "conversation_review_status": "pending"} for step in (13, 26)
        ],
    }
    state = {
        "campaign_id": "series",
        "plan": {"conversation_review": {"receipt_id_prefix": "review"}},
        "trials": [trial],
    }
    for step in (13, 26):
        receipt = (
            tmp_path
            / "conversation-reviews"
            / checkpoint_review_id("review", "run", step)
            / "receipt.json"
        )
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{}", encoding="utf-8")

    service._refresh_pending_conversation_reviews(state)

    assert calls == [("run", {13, 26})]


@pytest.mark.parametrize("final_qualification", [False, True])
def test_review_change_keeps_campaign_blocked(final_qualification, tmp_path):
    service = object.__new__(CampaignService)
    state = {
        "status": "awaiting_review",
        "training_status": "succeeded",
        "phase": "trials",
        "error": None,
        "plan": {
            "conversation_review": {},
            "final_qualification": {"enabled": True} if final_qualification else None,
        },
    }
    service._state = lambda _directory: state
    service._review_selection = lambda current: current.update(
        status="blocked",
        phase="complete",
        qualification_status="incomplete",
        quality_policy_error="campaign_quality_conversation_review_changed",
        error="campaign_quality_conversation_review_changed",
        worker=None,
    )
    service._save = lambda _directory, current: current

    result = service._advance_conversation_review(tmp_path)

    assert result["status"] == "blocked"
    assert result["phase"] == "complete"
    assert result["qualification_status"] == "incomplete"


@pytest.mark.parametrize("decision", ["PASS", "STOP"])
def test_checkpoint_review_template_advances_campaign_after_registration(
    tmp_path, monkeypatch, decision
):
    from tests.test_academy_conversation_review import _checkpoint_campaign
    from venom_core.services.training_experiments.campaign import _rank
    from venom_core.services.training_experiments.conversation_review import (
        prepare_checkpoint_review,
        register_review_request,
    )
    from venom_core.services.training_experiments.local_campaign_final import transition

    service, plan, run_id, panel, p13, candidate, _, _ = _checkpoint_campaign(
        tmp_path, monkeypatch
    )
    state = {
        "campaign_id": plan["campaign_id"],
        "plan": plan,
        "phase": "trials",
        "status": "succeeded",
        "training_status": "succeeded",
        "started_at": None,
        "elapsed_seconds": 0,
        "worker": None,
        "final_qualification": {"inputs_id": "final", "reserve_seconds": 30},
        "trials": [{"run_id": run_id, "status": "succeeded"}],
    }
    pending = service._assess_checkpoint(state, run_id, 13, None)
    pending["quality_guard"] = {"status": "passed"}
    state["trials"][0]["checkpoint_evaluations"] = [pending]
    _rank(state)
    transition(state)
    assert state["status"] == "awaiting_review"

    directory = service.directory(plan["campaign_id"])
    directory.mkdir(parents=True, exist_ok=True)
    service._save(directory, state)
    request = prepare_checkpoint_review(pending, panel)
    request.update(reviewer_id="operator", reviewer_note="Full conversation review")
    with pytest.raises(ValueError, match="conversation_review_.*_verdict_invalid"):
        register_review_request(tmp_path, request)
    assert service.advance(plan["campaign_id"])["status"] == "awaiting_review"

    if decision == "STOP":
        candidate["C000"]["T0"]["critical"] = True
    request.update(p13=p13, candidate=candidate)
    receipt = register_review_request(tmp_path, request)
    assert receipt["status"] == decision
    assert register_review_request(tmp_path, request) == receipt

    resumed = service.advance(plan["campaign_id"])
    item = resumed["trials"][0]["checkpoint_evaluations"][0]
    assert item["conversation_review_status"] == decision.lower()
    if decision == "PASS":
        assert item["qualified"] is True
        assert resumed["selected_run_id"] == run_id
        assert resumed["phase"] == "qualification"
    else:
        assert item["qualified"] is False
        assert resumed["selected_run_id"] is None
        assert resumed["qualification_status"] == "failed_quality"
