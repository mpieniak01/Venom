"""Controller acceptance without a provider account or GPU."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy_experiment_campaigns as routes
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services.remote_training.transport import TransportError
from venom_core.services.training_experiments import remote_text
from venom_core.services.training_experiments.campaign import CampaignService
from venom_core.services.training_experiments.remote_text import (
    RemoteTextService,
    RemoteTextSpec,
)

PLAN = "a" * 64
PROFILE = "b" * 64
RENTAL = "c" * 32
RUN = "campaign-night-01"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_text, "ensure_data_mutation_allowed", lambda _: None)
    local, rental, host = Mock(), Mock(), Mock()
    local.experiments.root = tmp_path
    local.validate.return_value = {"plan_sha256": PLAN, "profile_identity": PROFILE}
    rental.validate.return_value = {
        "cleanup_reserve_seconds": 180,
        "estimated_microusd": 500_000,
        "max_upload_bytes": 1000,
    }
    rental.cleanup.return_value = {"state": "destroyed"}
    rental.cost.return_value = {"estimated_microusd": 400_000}
    clock = Mock(return_value=1000.0)
    service = RemoteTextService(local, rental, lambda *_: host, clock=clock)
    spec = RemoteTextSpec.model_validate(
        {
            "environment_plan_id": RENTAL,
            "max_cost_microusd": 800_000,
            "campaign": {
                "campaign_id": "night",
                "profile_id": "pl_chat",
                "variants": [{}, {"rank": 8}],
                "review_mode": "automatic",
                "budget": {
                    "max_trials": 2,
                    "max_updates": 400,
                    "max_tokens": 500_000,
                    "max_seconds": 600,
                    "trial_seconds": 180,
                    "max_retries": 1,
                    "max_artifact_bytes": 1000,
                    "min_free_bytes": 0,
                },
            },
        }
    )
    host.plan.return_value = {"plan": {"plan_sha256": PLAN}, "status": "planned"}
    host.start.return_value = _remote("running")
    host.stop.return_value = _remote("stopped")
    return service, spec, clock, rental, host


def _remote(status, *, evaluated=False):
    return {
        "campaign_id": "night",
        "plan": {"plan_sha256": PLAN, "profile_identity": PROFILE},
        "cutoff_at": 1420.0,
        "status": status,
        "trials": [
            {"run_id": RUN, "status": "succeeded", "result_sha256": PROFILE}
            if evaluated
            else {"run_id": RUN, "status": "running"}
        ],
    }


def _launch(service, spec):
    planned = service.plan(spec)
    service.heartbeat()
    return service.start("night", planned["plan_sha256"])


def test_api_start_is_idempotent_and_controller_collects_then_cleans(
    setup, monkeypatch
):
    service, spec, _, rental, host = setup
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.require_experiment_access] = lambda: None
    monkeypatch.setattr(routes, "remote_text_service", lambda: service)
    client = TestClient(app)
    base = "/api/v1/academy/experiments/campaigns/remote/text"
    rental.validate.side_effect = VastError("vast.text_budget_exceeded")
    rejected = client.post(f"{base}/plan", json=spec.model_dump())
    assert rejected.status_code == 409
    assert rejected.json() == {
        "detail": {"code": "campaign_remote_cost_budget_exceeded"}
    }
    rental.validate.side_effect = None
    plan = client.post(f"{base}/plan", json=spec.model_dump())
    assert plan.status_code == 200
    rental.acquire.assert_not_called()
    start = {"plan_sha256": plan.json()["plan_sha256"]}
    assert client.post(f"{base}/night/start", json=start).status_code == 409
    service.heartbeat()
    queued = client.post(f"{base}/night/start", json=start).json()
    assert queued["status"] == "queued"
    assert queued["search_cutoff_at"] == 1420.0 and queued["deadline_at"] == 1600.0
    assert client.post(f"{base}/night/start", json=start).json() == queued
    assert client.get(base).json()["campaigns"] == [queued]
    assert service.tick("night")["status"] == "running"
    host.start.assert_called_once_with("night", PLAN, cutoff_at=1420.0)
    host.status.return_value = _remote("succeeded", evaluated=True)
    actions = []
    monkeypatch.setattr(
        remote_text,
        "sync_run",
        lambda *_args, **_kwargs: actions.append("synced") or {"archive_bytes": 20},
    )
    monkeypatch.setattr(
        remote_text,
        "summarize",
        lambda *_: {"outcome": "PROVISIONAL", "best_observed": {"run_id": RUN}},
    )
    rental.cleanup.side_effect = lambda *_args, **_kwargs: (
        actions.append("destroyed") or {"state": "destroyed"}
    )
    result = service.tick("night")
    assert actions == ["synced", "destroyed"]
    assert (
        result["status"] == "completed" and result["result"]["outcome"] == "PROVISIONAL"
    )
    assert client.get(f"{base}/night").json() == result
    assert service.tick("night") == result
    rental.cleanup.assert_called_once()


def test_lost_start_reply_and_controller_restart_preserve_cutoff(setup):
    service, spec, clock, rental, host = setup
    _launch(service, spec)
    host.start.side_effect = TransportError("remote_ssh_timeout", retryable=True)
    assert service.tick("night")["status"] == "queued"
    clock.return_value = 1421.0
    host.status.return_value = _remote("running")
    rental.cleanup.return_value = {"state": "cleanup_pending"}
    restored = RemoteTextService(service.local, rental, service.host, clock=clock)
    result = restored.tick("night")
    assert result["search_cutoff_at"] == 1420.0
    assert result["status"] == "cleanup_pending"
    assert result["result"]["outcome"] == "INCONCLUSIVE"
    host.stop.assert_called_once_with("night")
    host.start.assert_called_once()
    rental.cleanup.return_value = {"state": "destroyed"}
    assert restored.tick("night")["status"] == "completed"


def test_no_ssh_response_after_deadline_does_not_hold_vm(setup):
    service, spec, clock, rental, host = setup
    _launch(service, spec)
    clock.return_value = 1600.0
    result = service.tick("night")
    assert result["status"] == "completed"
    assert result["result"]["outcome"] == "INCONCLUSIVE"
    host.start.assert_not_called()
    host.status.assert_not_called()
    rental.cleanup.assert_called_once_with(RENTAL, campaign_id="night")


def test_controller_completes_after_confirmed_stop_without_destroying_vm(setup):
    service, spec, clock, rental, _ = setup
    _launch(service, spec)
    clock.return_value = 1600.0
    rental.cleanup.return_value = {"state": "stopped"}
    state = service.tick("night")
    assert state["status"] == "completed"
    assert state["cleanup"]["state"] == "stopped"
    assert service.tick("night") == state


def test_profile_mismatch_never_starts_training(setup):
    service, spec, _, rental, host = setup
    _launch(service, spec)
    host.plan.return_value = {"plan": {"plan_sha256": PROFILE}, "status": "planned"}
    host.status.side_effect = TransportError("remote_text_not_found")
    result = service.tick("night")
    host.start.assert_not_called()
    rental.cleanup.assert_called_once_with(RENTAL, campaign_id="night")
    assert result["status"] == "completed"


def test_partial_upload_retried_and_stop_intent_is_durable(setup, monkeypatch):
    service, spec, _, _, host = setup
    _launch(service, spec)
    service.tick("night")
    service.stop("night")
    host.status.return_value = _remote("succeeded", evaluated=True)
    sync = Mock(
        side_effect=[
            TransportError("remote_text_fetch_failed", retryable=True),
            {"archive_bytes": 1},
        ]
    )
    monkeypatch.setattr(remote_text, "sync_run", sync)
    monkeypatch.setattr(remote_text, "summarize", lambda *_: {"outcome": "PROVISIONAL"})
    assert service.tick("night")["status"] == "finalizing"
    result = service.tick("night")
    assert result["status"] == "completed"
    assert result["stop_requested"] and RUN in result["evidence"]
    assert sync.call_count == 2


def test_local_review_profile_rejected_without_rental(setup):
    service, spec, _, rental, _ = setup
    spec.campaign.review_mode = "manual"
    with pytest.raises(ValueError, match="campaign_remote_automatic_review_required"):
        service.plan(spec)
    rental.validate.assert_not_called()


def test_remote_campaign_pins_same_starting_adapter_in_each_variant(setup):
    service, spec, _, _, host = setup
    for variant in spec.campaign.variants:
        variant["initial_adapter_id"] = "omni-p13-145"
    _launch(service, spec)
    service.tick("night")
    request = host.plan.call_args.args[0]
    assert [variant["initial_adapter_id"] for variant in request["variants"]] == [
        "omni-p13-145",
        "omni-p13-145",
    ]
    host.start.assert_called_once()


def test_remote_campaign_rejects_mixed_parents_and_base_only_qualification(setup):
    service, spec, _, rental, _ = setup
    spec.campaign.variants[0]["initial_adapter_id"] = "omni-p13-145"
    with pytest.raises(ValueError, match="campaign_remote_mixed_parents"):
        service.plan(spec)
    spec.campaign.variants[1]["initial_adapter_id"] = "omni-p13-145"
    spec.final_test_sha256 = PLAN
    spec.final_calibration_sha256 = PROFILE
    with pytest.raises(ValueError, match="campaign_remote_parent_holdout_required"):
        service.plan(spec)
    rental.validate.assert_not_called()


def test_completed_remote_campaign_exposes_only_sealed_qualification(
    setup, monkeypatch
):
    service, spec, _, _, host = setup
    spec.final_test_sha256 = PLAN
    spec.final_calibration_sha256 = PROFILE
    _launch(service, spec)
    service.tick("night")
    host.status.return_value = _remote("succeeded")
    assert service.tick("night")["result"]["best_qualified"] is None
    qualified = {"run_id": RUN, "adapter_id": "qualified-test"}
    read = Mock(return_value={"status": "passed", "qualified": qualified})
    monkeypatch.setattr(remote_text, "read_qualification", read)
    result = service.status("night")
    assert result["qualification_status"] == "passed"
    assert result["result"]["outcome"] == "QUALIFIED"
    assert result["result"]["best_qualified"] == qualified
    assert read.call_args.kwargs == {
        "final_test_sha256": PLAN,
        "final_calibration_sha256": PROFILE,
    }


def test_remote_trial_needs_full_window_and_cutoff_cannot_be_extended(
    tmp_path, monkeypatch
):
    from venom_core.services.training_experiments import campaign as campaign_module

    monkeypatch.setattr(campaign_module, "ensure_data_mutation_allowed", lambda _: None)
    experiments = Mock()
    experiments.root = tmp_path
    clock = Mock(return_value=1000.0)
    launch = Mock(return_value=None)
    service = CampaignService(experiments, launch=launch, clock=clock)
    payload = {
        "campaign_id": "night",
        "variants": [{"run_id": RUN}],
        "budget": {"max_seconds": 120, "trial_seconds": 90},
    }
    plan = {**payload, "plan_sha256": campaign_module.fingerprint(payload)}
    directory = service.directory("night")
    directory.mkdir(parents=True)
    service._save(directory, campaign_module._initial_state(plan))
    monkeypatch.setattr(service, "_verify_activation_inputs", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "_run", lambda *_a: None)
    state = service.start("night", plan["plan_sha256"], cutoff_at=1100.0)
    assert state["cutoff_at"] == 1100.0
    with pytest.raises(ValueError, match="campaign_execution_cutoff_changed"):
        service.start("night", plan["plan_sha256"], cutoff_at=1150.0)
    clock.return_value = 1011.0
    terminal = service.advance("night")
    assert terminal["status"] == "timed_out"
    assert terminal["trials"][0]["status"] == "pending"
