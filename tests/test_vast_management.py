"""Operator rental flow, with provider and provisioner doubles only."""

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.test_vast_operations import service as source_service
from venom_core.api.routes import vast_environments as routes
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, digest, now
from venom_core.services import vast_management as management
from venom_core.services import vast_management_config as config
from venom_core.services.vast_environments.startup import startup


@pytest.fixture
def f(tmp_path, monkeypatch):
    svc, plan, offer = source_service.__wrapped__(tmp_path)
    plan.profile.mode, plan.profile.model = "ollama", "fixture:latest"
    plan.profile.model_digest, plan.profile.download_gb = "d" * 64, Decimal("1")
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    offer["internet_down_cost_per_tb"] = 0
    svc.client.instance.return_value.update(host_id=3, machine_id=4)
    path = tmp_path / "profile.json"
    path.write_text(plan.profile.model_dump_json())
    settings = SimpleNamespace(
        VAST_API_KEY=SecretStr("fake"), VAST_CHAT_PROFILE_FILE=str(path)
    )
    monkeypatch.setattr(
        config, "ssh_paths", lambda: (tmp_path / "identity", tmp_path / "known_hosts")
    )
    state = {"available": False, "plan_id": None, "models": []}
    connection = Mock(journal=svc.journal)
    connection.status.side_effect = lambda refresh=False: dict(state)

    def attach(pid, **kwargs):
        state.update(
            available=True,
            plan_id=pid,
            models=[{"name": plan.profile.model, "digest": plan.profile.model_digest}],
        )
        return dict(state)

    def detach(**kwargs):
        state.update(available=False, plan_id=None, models=[])

    connection.attach.side_effect, connection.detach.side_effect = attach, detach
    actions, calls = [], []
    manager = management.VastManagement(
        settings,
        connection,
        client_factory=Mock(return_value=svc.client),
        launch=lambda fn, pid: actions.append((fn, pid)),
        sleep=lambda _: None,
    )
    manager._save(plan.plan_id, phase="planned", authorized=False)
    monkeypatch.setattr(
        management,
        "workload",
        lambda svc, pid, op, trust: calls.append((op, trust)) or {},
    )
    return SimpleNamespace(
        m=manager,
        svc=svc,
        p=plan,
        state=state,
        connection=connection,
        actions=actions,
        calls=calls,
    )


def run(f):
    fn, pid = f.actions.pop()
    fn(pid)


def order(f):
    f.m.order(f.p.plan_id, True)
    run(f)


def test_offline_discovery_search_and_plan(f):
    assert f.m.overview()["configured"]
    f.m.client_factory.assert_not_called()
    found = f.m.search(30)
    assert found["offers"][0]["status"] == "eligible"
    row = f.m.plan(12, 30, Decimal("0.5"), Decimal("1"))
    assert row["phase"] == "planned" and not row["billing_possible"]
    assert "identity" not in json.dumps(row)
    f.svc.client.create.assert_not_called()


def test_order_autoattaches_without_generation_or_selection(f):
    assert f.m.order(f.p.plan_id, True)["phase"] == "queued"
    assert f.m.order(f.p.plan_id, True)["phase"] == "queued"
    assert len(f.actions) == 1
    for _ in range(3):
        assert f.m.overview()["environments"][0]["phase"] == "queued"
        assert f.m.refresh(f.p.plan_id)["phase"] == "queued"
    f.m.client_factory.assert_not_called()
    run(f)
    row = f.m.row(f.p.plan_id)
    assert row["phase"] == "ready" and row["connected"] and row["billing_possible"]
    assert f.calls == [("inspect", True), ("provision", True)]
    f.connection.attach.assert_called_once_with(
        f.p.plan_id, expected_model=(f.p.profile.model, f.p.profile.model_digest)
    )
    assert f.m.refresh(f.p.plan_id)["connected"]
    f.m.order(f.p.plan_id, True)
    f.svc.client.create.assert_called_once()


@pytest.mark.parametrize("ambiguous", [True, False])
def test_failed_create_never_retries(f, ambiguous):
    f.svc.client.create.side_effect = VastError(
        "vast.transport_error", ambiguous=ambiguous
    )
    order(f)
    assert f.m.row(f.p.plan_id)["phase"] == "error"
    f.m.order(f.p.plan_id, False)
    f.svc.client.create.assert_called_once()
    assert not f.calls


def test_restart_is_offline_and_interrupted(f):
    f.m.order(f.p.plan_id, False)
    other = management.VastManagement(f.m.settings, f.connection, client_factory=Mock())
    assert other.row(f.p.plan_id)["phase"] == "interrupted"
    other.order(f.p.plan_id, False)
    other.client_factory.assert_not_called()


@pytest.mark.parametrize(
    "fault,code",
    [
        ("disabled", "vast.management_disabled"),
        ("expired", "vast.plan_expired"),
        ("foreign", "vast.management_plan_required"),
        ("selected", "vast.management_target_selected"),
        ("connected", "vast.management_target_connected"),
    ],
)
def test_preflight_prevents_rental(f, fault, code):
    if fault == "disabled":
        f.m.is_enabled = lambda: False
    if fault == "expired":
        f.p.expires_at = now() - timedelta(seconds=1)
        f.p.checksum = f.p.calculate_checksum()
        f.svc.journal.save_plan(f.p)
    if fault == "foreign":
        f.svc.journal.path(f.p.plan_id, ".management.json").unlink()
    if fault == "selected":
        f.m.selection = lambda: {"target_id": "ollama@vast:other:42"}
    if fault == "connected":
        f.state.update(available=True, plan_id="b" * 32)
    with pytest.raises(VastError, match=code):
        f.m.order(f.p.plan_id, False)
    assert not f.actions


def test_other_order_is_blocked(f):
    f.m.order(f.p.plan_id, False)
    row = f.m.plan(12, 30, Decimal("0.5"), Decimal("1"))
    with pytest.raises(VastError, match="vast.management_existing_order"):
        f.m.order(row["plan_id"], False)


def test_worker_failure_and_corrupt_journal(f):
    f.m.launch = Mock(side_effect=RuntimeError("fixture"))
    with pytest.raises(VastError, match="vast.management_worker_failed"):
        f.m.order(f.p.plan_id, False)
    assert f.m.row(f.p.plan_id)["phase"] == "error"
    f.svc.journal.path(f.p.plan_id, ".management.json").write_text("[]")
    with pytest.raises(VastError, match="vast.management_journal_invalid"):
        f.m.row(f.p.plan_id)


def test_provision_failure_keeps_billed_resource_visible(f, monkeypatch):
    monkeypatch.setattr(
        management, "workload", Mock(side_effect=VastError("vast.provision_failed"))
    )
    order(f)
    assert f.m.row(f.p.plan_id)["billing_possible"]
    assert f.m.row(f.p.plan_id)["error"] == "vast.provision_failed"
    f.svc.client.destroy.assert_not_called()


def test_not_running_and_disabled_during_setup(f):
    f.svc.client.instance.return_value["actual_status"] = "stopped"
    order(f)
    assert f.m.row(f.p.plan_id)["error"] == "vast.management_not_running"
    f.m.is_enabled = lambda: False
    with pytest.raises(VastError, match="vast.management_disabled"):
        f.m._attach(f.p.plan_id)
    with pytest.raises(VastError, match="vast.management_disabled"):
        f.m._await_ssh(f.svc, f.p.plan_id, False)


def test_ssh_retry_bounded_and_opt_in(f, monkeypatch):
    op = Mock(side_effect=[VastError("vast.ssh_failed"), {}])
    monkeypatch.setattr(management, "workload", op)
    f.m._await_ssh(f.svc, f.p.plan_id, False)
    assert op.call_count == 2 and op.call_args.args[-1] is False
    op.side_effect = VastError("vast.ssh_failed")
    op.reset_mock()
    with pytest.raises(VastError):
        f.m._await_ssh(f.svc, f.p.plan_id, False)
    assert op.call_count == 12


def test_digest_mismatch_never_connects(f):
    f.connection.attach.side_effect = None
    f.connection.attach.return_value = {
        "available": True,
        "models": [{"name": f.p.profile.model, "digest": "x" * 64}],
    }
    order(f)
    assert f.m.row(f.p.plan_id)["error"] == "vast.management_model_not_ready"
    assert not f.m.row(f.p.plan_id)["connected"]
    assert f.connection.detach.call_count == 12


def test_refresh_restores_only_existing_provisioned_order(f):
    order(f)
    f.state.update(available=False, plan_id=None)
    f.m.owner = "restart"
    assert f.m.row(f.p.plan_id)["phase"] == "connecting"
    assert f.m.refresh(f.p.plan_id)["connected"]
    assert len(f.calls) == 2
    f.svc.client.instance.return_value["actual_status"] = "stopped"
    assert f.m.refresh(f.p.plan_id)["phase"] == "stopped"
    f.svc.client.instance.side_effect = VastError("vast.transport_error")
    assert f.m.refresh(f.p.plan_id)["error"] == "vast.transport_error"


def test_cleanup_works_when_provider_disabled(f):
    f.m.order(f.p.plan_id, False)
    with pytest.raises(VastError, match="vast.management_busy"):
        f.m.change(f.p.plan_id, "stop")
    run(f)
    assert f.m.change(f.p.plan_id, "stop")["phase"] == "stop_requested"
    f.m.is_enabled = lambda: False
    assert f.m.change(f.p.plan_id, "destroy")["phase"] == "destroy_requested"
    f.svc.client.set_state.assert_called_once_with(88, "stopped")
    f.svc.client.destroy.assert_called_once_with(88)
    assert f.svc.journal.path(f.p.plan_id, ".export.json").exists()
    f.svc.client.instance.side_effect = VastError("vast.http_error", 404)
    row = f.m.refresh(f.p.plan_id)
    assert row["phase"] == "destroyed" and not row["billing_possible"]
    with pytest.raises(VastError):
        f.m.change(f.p.plan_id, "start")


def test_bad_profile_credentials_and_journal_do_not_break_discovery(f):
    path = f.m.settings.VAST_CHAT_PROFILE_FILE
    f.m.settings.VAST_CHAT_PROFILE_FILE = "/missing/fixture.json"
    assert not f.m.overview()["configured"]
    f.m.settings.VAST_CHAT_PROFILE_FILE = path
    f.m.settings.VAST_API_KEY = SecretStr("")
    assert f.m.overview()["reason"] == "vast.missing_api_key"
    f.svc.journal.path("e" * 32, ".plan.json").write_text("{}")
    f.m.settings.VAST_API_KEY = SecretStr("fake")
    assert f.m.overview()["reason"] == "vast.management_journal_invalid"


def test_server_owned_profile_and_ssh_contract(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    settings = SimpleNamespace(VAST_CHAT_PROFILE_FILE=str(path))
    with pytest.raises(VastError):
        config.profile(settings)
    p = WorkloadProfile(name="fake", cpu_arch="arm64", image="test@sha256:" + "a" * 64)
    path.write_text(p.model_dump_json())
    with pytest.raises(VastError):
        config.profile(settings)
    p.mode, p.model, p.model_digest, p.download_gb = (
        "ollama",
        "test",
        "bad",
        Decimal("1"),
    )
    path.write_text(p.model_dump_json())
    with pytest.raises(VastError):
        config.profile(settings)
    monkeypatch.setattr(
        config,
        "ssh_profile",
        lambda _: {
            "identity_file": str(tmp_path / "key"),
            "known_hosts": str(tmp_path / "hosts"),
        },
    )
    with pytest.raises(VastError):
        config.ssh_paths()
    (tmp_path / "key").write_text("fake")
    (tmp_path / "key.pub").write_text("fake")
    assert config.ssh_paths() == (tmp_path / "key", tmp_path / "hosts")


@pytest.fixture
def api(f, monkeypatch):
    monkeypatch.setattr(management, "manager", lambda: f.m)
    monkeypatch.setattr(routes, "require_localhost_request", lambda request: None)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    return TestClient(app)


def test_api_schema_and_confirmation(api, f):
    root = "/api/v1/vast/environments"
    assert api.get(root).status_code == 200
    assert api.post(root + "/search", json={"duration_minutes": 30}).status_code == 200
    reply = api.post(
        root + "/plans",
        json={
            "offer_id": 12,
            "duration_minutes": 30,
            "max_hourly_usd": "0.5",
            "max_total_usd": "1",
        },
    )
    assert reply.status_code == 200
    path = root + "/" + reply.json()["plan_id"]
    for body in ({}, {"confirmed": False}, {"confirmed": True, "unknown": 1}):
        assert api.post(path + "/order", json=body).status_code == 422
    assert (
        api.post(
            path + "/order", json={"confirmed": True, "accept_new_host_key": True}
        ).status_code
        == 202
    )
    assert api.post(path + "/refresh").status_code == 200
    assert api.post(root + "/bad/order", json={"confirmed": True}).status_code == 422
    assert api.post(root + "/search", json={"duration_minutes": 0}).status_code == 422
    f.svc.client.create.assert_not_called()


def test_api_cleanup_errors_and_origin_guard(api, f):
    root = "/api/v1/vast/environments"
    assert api.get(root, headers={"Origin": "https://attacker.test"}).status_code == 403
    assert api.get(root, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert api.get(root, headers={"Origin": "http://localhost:3300"}).status_code == 200
    path = root + "/" + f.p.plan_id
    assert api.post(path + "/stop", json={"confirmed": False}).status_code == 422
    order(f)
    assert api.post(path + "/stop", json={"confirmed": True}).status_code == 200
    assert api.post(path + "/destroy", json={"confirmed": True}).status_code == 200
    f.m.is_enabled = lambda: False
    assert api.post(root + "/search", json={"duration_minutes": 30}).status_code == 503
    with pytest.raises(HTTPException) as e:
        routes.invoke(Mock(side_effect=OSError("private")))
    assert e.value.detail == "vast.management_unavailable"
