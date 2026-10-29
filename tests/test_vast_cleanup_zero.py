"""Account-empty acceptance never deletes unrelated resources or retries creation."""

import json
from decimal import Decimal
from unittest.mock import Mock, call, patch

import pytest

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import digest
from venom_core.services.vast_environments.cleanup_zero import (
    ZeroCheckError,
    cleanup_zero,
    trial_zero,
    verify_zero,
)
from venom_core.services.vast_environments.cli import dispatch, parser
from venom_core.services.vast_environments.startup import startup


@pytest.fixture
def service(tmp_path):
    svc, plan, offer = source_service.__wrapped__(tmp_path)
    plan.profile.mode = "ollama"
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.client.instance.return_value.update(
        label="venom-" + plan.plan_id,
        host_id=offer["host_id"],
        machine_id=offer["machine_id"],
    )
    return svc, plan, offer


def removed(svc):
    svc.client.instance.side_effect = VastError("vast.http_error", 404)
    svc.client.instances.return_value = []


def test_cleanup_confirms_deleted_and_full_inventory(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.client.destroy.side_effect = lambda _: removed(svc)
    before = Mock()
    result = cleanup_zero(svc, plan.plan_id, before_destroy=before)
    assert result["zero_confirmed"] is True
    assert result["instance_count"] == 0
    before.assert_called_once_with(plan.plan_id)
    svc.client.destroy.assert_called_once_with(88)
    assert svc.journal.path(plan.plan_id, ".zero.json").is_file()


def test_cleanup_retains_unrelated_stopped_instance(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)

    def destroy(_):
        svc.client.instance.side_effect = VastError("vast.http_error", 404)
        svc.client.instances.return_value = [{"id": 77, "actual_status": "stopped"}]

    svc.client.destroy.side_effect = destroy
    with pytest.raises(ZeroCheckError, match="vast.account_not_empty") as caught:
        cleanup_zero(svc, plan.plan_id)
    assert caught.value.report["instance_ids"] == [77]
    assert caught.value.report["instance_deleted"] is True
    svc.client.destroy.assert_called_once_with(88)


def test_destroy_ack_and_empty_list_do_not_prove_target_deleted(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    ticks = iter([0, 1])
    with pytest.raises(ZeroCheckError, match="vast.cleanup_unconfirmed"):
        cleanup_zero(svc, plan.plan_id, 1, clock=lambda: next(ticks))
    svc.client.destroy.assert_called_once()


def test_cleanup_ambiguous_destroy_is_observed_not_replayed(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)

    def destroy(_):
        removed(svc)
        raise VastError("vast.transport_error", ambiguous=True)

    svc.client.destroy.side_effect = destroy
    assert cleanup_zero(svc, plan.plan_id)["zero_confirmed"] is True
    svc.client.destroy.assert_called_once()


def test_cleanup_inflight_destroy_is_not_replayed(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.export(plan.plan_id)
    svc.change(plan.plan_id, "destroy")
    removed(svc)
    assert cleanup_zero(svc, plan.plan_id)["zero_confirmed"]
    svc.client.destroy.assert_called_once()


def test_cleanup_detach_failure_does_not_destroy(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    with pytest.raises(ZeroCheckError, match="vast.detach_unconfirmed"):
        cleanup_zero(
            svc,
            plan.plan_id,
            before_destroy=Mock(side_effect=VastError("vast.detach_unconfirmed")),
        )
    svc.client.destroy.assert_not_called()


@pytest.mark.parametrize("rows", [[{"id": 88}, {"id": 88}], [{"id": True}], [{}]])
def test_verify_zero_rejects_invalid_inventory(service, rows):
    svc, _, _ = service
    svc.client.instances.return_value = rows
    with pytest.raises(ZeroCheckError, match="vast.invalid_inventory") as caught:
        verify_zero(svc)
    assert caught.value.report["instance_count"] is None


@pytest.mark.parametrize("code", ["vast.pagination_limit", "vast.transport_error"])
def test_verify_zero_failed_or_incomplete_read_is_not_zero(service, code):
    svc, _, _ = service
    svc.client.instances.side_effect = VastError(code)
    with pytest.raises(ZeroCheckError) as caught:
        verify_zero(svc)
    assert caught.value.report["zero_confirmed"] is False
    assert caught.value.report["instance_count"] is None


def test_cleanup_inventory_read_error_cannot_pass(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)

    def destroy(_):
        svc.client.instance.side_effect = VastError("vast.http_error", 404)
        svc.client.instances.side_effect = VastError("vast.http_error", 403)

    svc.client.destroy.side_effect = destroy
    with pytest.raises(ZeroCheckError) as caught:
        cleanup_zero(svc, plan.plan_id)
    assert caught.value.report["instance_count"] is None


def test_trial_requires_empty_baseline(service):
    svc, plan, _ = service
    svc.client.instances.return_value = [{"id": 77}]
    with pytest.raises(ZeroCheckError, match="vast.account_not_empty"):
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()


def test_trial_ollama_profile_required(service):
    svc, plan, _ = service
    plan.profile.mode = "inspect"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.trial_ollama_profile_required"):
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()


def test_trial_success_uses_inspection_and_guaranteed_cleanup(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with patch(
        "venom_core.services.vast_environments.cleanup_zero.workload",
        side_effect=[
            {"ssh": "ready", "reasons": []},
            {"startup": "completed"},
            {
                "runtime": "ready",
                "acceptance_scope": "engine_only",
                "generation_tested": False,
            },
        ],
    ) as inspect:
        result = trial_zero(svc, plan.plan_id, accept_new_host_key=True)
    assert result["success"] and result["cleanup"]["zero_confirmed"]
    assert result["engine"]["generation_tested"] is False
    assert inspect.call_args_list == [
        call(svc, plan.plan_id, "inspect", True),
        call(svc, plan.plan_id, "provision", False),
        call(svc, plan.plan_id, "ready", False),
    ]
    svc.client.create.assert_called_once()


def test_trial_inspection_failure_still_cleans_up(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with (
        patch(
            "venom_core.services.vast_environments.cleanup_zero.workload",
            side_effect=VastError("vast.ssh_failed"),
        ),
        pytest.raises(ZeroCheckError) as caught,
    ):
        trial_zero(svc, plan.plan_id)
    assert caught.value.report["error"] == "vast.ssh_failed"
    assert caught.value.report["cleanup"]["zero_confirmed"]
    assert not caught.value.report["success"]


def test_trial_wait_nonfinal_does_not_inspect(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with (
        patch.object(svc, "wait", return_value=Mock(state="loading")),
        patch("venom_core.services.vast_environments.cleanup_zero.workload") as inspect,
        pytest.raises(ZeroCheckError, match="vast.trial_host_not_running"),
    ):
        trial_zero(svc, plan.plan_id)
    inspect.assert_not_called()
    svc.client.destroy.assert_called_once()


def test_trial_ambiguous_create_never_retries(service):
    svc, plan, _ = service
    svc.client.create.side_effect = VastError("vast.transport_error", ambiguous=True)
    with pytest.raises(ZeroCheckError) as caught:
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_called_once()
    svc.client.destroy.assert_not_called()
    assert caught.value.report["cleanup"]["zero_confirmed"] is False


def test_cli_zero_dispatch_and_timeout_validation(service):
    svc, _, _ = service
    assert dispatch(parser().parse_args(["verify-zero"]), svc)["zero_confirmed"]
    with pytest.raises(VastError, match="vast.invalid_timeout"):
        cleanup_zero(svc, "unused", 0)


def test_cleanup_repeat_is_idempotent(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.client.destroy.side_effect = lambda _: removed(svc)
    assert cleanup_zero(svc, plan.plan_id)["zero_confirmed"]
    assert cleanup_zero(svc, plan.plan_id)["zero_confirmed"]
    svc.client.destroy.assert_called_once()


def test_concurrent_cleanup_cannot_destroy_an_active_trial(service):
    from venom_core.services.vast_environments.cleanup_zero import _workflow

    svc, plan, _ = service
    with _workflow(svc, plan.plan_id):
        with pytest.raises(VastError, match="vast.plan_busy"):
            trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()
    svc.client.destroy.assert_not_called()


def test_interrupted_trial_still_cleans_up_without_false_success(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with (
        patch(
            "venom_core.services.vast_environments.cleanup_zero.workload",
            side_effect=KeyboardInterrupt,
        ),
        pytest.raises(ZeroCheckError, match="vast.trial_interrupted") as caught,
    ):
        trial_zero(svc, plan.plan_id)
    assert caught.value.report["success"] is False
    assert caught.value.report["cleanup"]["zero_confirmed"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 99},
        {"id": True},
        {"label": "venom-other-plan"},
        {"label": None},
        {"host_id": 99},
        {"machine_id": 99},
        {"host_id": None},
        {"machine_id": None},
        {"machine_id": True},
    ],
)
def test_cleanup_refuses_wrong_or_incomplete_provider_identity(service, changes):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.client.instance.return_value.update(changes)
    with pytest.raises(
        ZeroCheckError, match="vast.cleanup_instance_mismatch"
    ) as caught:
        cleanup_zero(svc, plan.plan_id)
    assert caught.value.report["zero_confirmed"] is False
    svc.client.destroy.assert_not_called()


def test_cleanup_refuses_tampered_record_id_referencing_foreign_host(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    record = svc.journal.record(plan.plan_id)
    record.instance_id = 99
    svc.journal.save_record(record)
    plan.profile.mode = "ollama"
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.client.instance.return_value.update(
        id=99,
        label="someone-elses-host",
        host_id=30,
        machine_id=40,
    )
    with pytest.raises(ZeroCheckError, match="vast.cleanup_instance_mismatch"):
        cleanup_zero(svc, plan.plan_id)
    svc.client.destroy.assert_not_called()


def test_cleanup_unknown_observation_never_uses_cached_identity(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.reconcile(plan.plan_id)
    svc.client.instance.side_effect = VastError("vast.http_error", 503)
    with pytest.raises(ZeroCheckError, match="vast.http_error"):
        cleanup_zero(svc, plan.plan_id)
    svc.client.destroy.assert_not_called()


def test_cleanup_already_destroyed_uses_fresh_inventory_without_provider_identity(
    service,
):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    record = svc.journal.record(plan.plan_id)
    record.state = "destroyed"
    record.instance = {}
    svc.journal.save_record(record)
    svc.client.instance.side_effect = VastError("vast.http_error", 404)
    svc.client.instances.return_value = []
    assert cleanup_zero(svc, plan.plan_id)["zero_confirmed"]
    svc.client.destroy.assert_not_called()
    svc.client.instance.assert_not_called()


@pytest.mark.parametrize(
    "key,value",
    [
        ("host_id", None),
        ("host_id", 0),
        ("host_id", True),
        ("machine_id", None),
        ("machine_id", 0),
        ("machine_id", True),
    ],
)
def test_cleanup_requires_valid_positive_plan_host_snapshot(service, key, value):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    plan.assessment.offer[key] = value
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(ZeroCheckError, match="vast.cleanup_instance_mismatch"):
        cleanup_zero(svc, plan.plan_id)
    svc.client.destroy.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"model": "model", "model_digest": "digest"},
        {"model_digest": "digest"},
        {"download_gb": Decimal(1)},
    ],
)
def test_trial_rejects_model_or_download_before_renting(service, values):
    svc, plan, _ = service
    plan.profile = plan.profile.model_copy(update=values)
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.trial_engine_only_profile_required"):
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()


@pytest.mark.parametrize(
    "stage_result,error",
    [
        ({"startup": "failed"}, "vast.provision_failed"),
        ({"runtime": "unknown"}, "vast.trial_engine_not_ready"),
    ],
)
def test_trial_unready_engine_still_destroys(service, stage_result, error):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    stages = [{"ssh": "ready", "reasons": []}]
    if error == "vast.trial_engine_not_ready":
        stages.append({"startup": "completed"})
    stages.append(stage_result)
    with (
        patch(
            "venom_core.services.vast_environments.cleanup_zero.workload",
            side_effect=stages,
        ),
        pytest.raises(ZeroCheckError, match=error) as caught,
    ):
        trial_zero(svc, plan.plan_id)
    assert caught.value.report["cleanup"]["zero_confirmed"]
    assert caught.value.report["success"] is False


def test_trial_unexpected_wait_failure_still_destroys_instance(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with patch.object(svc, "wait", side_effect=ValueError("bad response")):
        with pytest.raises(
            ZeroCheckError, match="vast.trial_unexpected_error"
        ) as caught:
            trial_zero(svc, plan.plan_id)
    assert caught.value.report["error_type"] == "ValueError"
    assert caught.value.report["cleanup"]["zero_confirmed"] is True
    svc.client.destroy.assert_called_once_with(88)


def test_cleanup_can_destroy_owned_host_when_local_api_is_not_listening(
    service, tmp_path, monkeypatch
):
    from venom_core.services import vast_chat_cli, vast_chat_connection

    svc, plan, _ = service
    svc.create(plan.plan_id)
    monkeypatch.setattr(vast_chat_connection, "ROOT", tmp_path)
    (tmp_path / "chat-target.json").write_text(
        json.dumps({"target": {"plan_id": plan.plan_id}})
    )
    monkeypatch.setattr(
        vast_chat_cli, "admin", Mock(side_effect=VastError("vast.chat_api_unreachable"))
    )
    svc.client.destroy.side_effect = lambda _: removed(svc)
    result = cleanup_zero(svc, plan.plan_id, before_destroy=vast_chat_cli.detach_plan)
    assert result["zero_confirmed"]
    svc.client.destroy.assert_called_once_with(88)
