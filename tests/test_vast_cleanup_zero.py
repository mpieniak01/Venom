"""Account-empty acceptance never deletes unrelated resources or retries creation."""

from unittest.mock import Mock, patch

import pytest

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services.vast_environments.cleanup_zero import (
    ZeroCheckError,
    cleanup_zero,
    trial_zero,
    verify_zero,
)
from venom_core.services.vast_environments.cli import dispatch, parser


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


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


def test_trial_requires_inspect_and_empty_baseline(service):
    svc, plan, _ = service
    svc.client.instances.return_value = [{"id": 77}]
    with pytest.raises(ZeroCheckError, match="vast.account_not_empty"):
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()


def test_trial_inspect_profile_required(service):
    svc, plan, _ = service
    plan.profile.mode = "ollama"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.trial_inspect_profile_required"):
        trial_zero(svc, plan.plan_id)
    svc.client.create.assert_not_called()


def test_trial_success_uses_inspection_and_guaranteed_cleanup(service):
    svc, plan, _ = service
    svc.client.destroy.side_effect = lambda _: removed(svc)
    with patch(
        "venom_core.services.vast_environments.cleanup_zero.workload",
        return_value={"ssh": "ready", "reasons": []},
    ) as inspect:
        result = trial_zero(svc, plan.plan_id, accept_new_host_key=True)
    assert result["success"] and result["cleanup"]["zero_confirmed"]
    inspect.assert_called_once_with(svc, plan.plan_id, "inspect", True)
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
