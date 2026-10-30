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
    assert row["phase"] == "planned"
    assert not row["billing_possible"]
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
    assert row["phase"] == "ready"
    assert row["connected"]
    assert row["billing_possible"]
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
    assert op.call_count == 2
    assert op.call_args.args[-1] is False
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
    assert f.m.row(f.p.plan_id)["phase"] == "interrupted"
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
    assert row["phase"] == "destroyed"
    assert not row["billing_possible"]
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
    f.svc.journal.path("e" * 32, ".management.json").write_text("{}")
    f.m.settings.VAST_API_KEY = SecretStr("fake")
    overview = f.m.overview()
    assert overview["configured"]
    assert overview["reason"] is None
    invalid = next(
        row for row in overview["environments"] if row["plan_id"] == "e" * 32
    )
    assert invalid["error"] == "vast.management_journal_invalid"
    assert invalid["billing_possible"]
    assert not invalid["connected"]


def test_server_owned_profile_and_ssh_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_SSH_ROOTS", (tmp_path,))
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
    input_under_test = Mock(side_effect=OSError("private"))
    with pytest.raises(HTTPException) as e:
        routes.invoke(input_under_test)
    assert e.value.detail == "vast.management_unavailable"


def test_operation_lock_prevents_refresh_cleanup_and_provision_races(f):
    from venom_core.services.vast_environments.store import Journal

    journal = Journal(f.m.journal.root / "management-locks")
    with journal.lock(f.p.plan_id):
        for action in (
            lambda: f.m.refresh(f.p.plan_id),
            lambda: f.m.change(f.p.plan_id, "stop"),
        ):
            with pytest.raises(VastError, match="vast.plan_busy"):
                action()
    f.svc.client.create.assert_not_called()
    f.connection.attach.assert_not_called()


def test_pending_cleanup_never_reattaches_and_get_confirms_destroyed(f):
    order(f)
    f.m.change(f.p.plan_id, "destroy")
    row = f.m.refresh(f.p.plan_id)
    assert row["phase"] == "destroy_requested"
    assert not row["connected"]
    assert f.connection.attach.call_count == 1
    f.m.change(f.p.plan_id, "destroy")
    f.svc.client.destroy.assert_called_once()
    f.svc.client.instance.side_effect = VastError("vast.http_error", 404)
    row = f.m.overview()["environments"][0]
    assert row["phase"] == "destroyed"
    assert not row["billing_possible"]


def test_operator_can_cancel_interrupted_queue_without_rental(f):
    f.m.order(f.p.plan_id, False)
    f.m.owner = "new-api-process"
    assert f.m.row(f.p.plan_id)["phase"] == "interrupted"
    assert f.m.change(f.p.plan_id, "destroy")["phase"] == "cancelled"
    run(f)  # late scheduler callback must not revive cancelled intent
    f.svc.client.create.assert_not_called()
    assert f.m.row(f.p.plan_id)["phase"] == "cancelled"


def test_provision_waits_for_initial_startup_lock_instead_of_skipping_install(f):
    assert "flock -w 120 9" in startup(f.p.profile, download_model=True)
    assert "ollama pull" in startup(f.p.profile, download_model=True)
    assert "flock -n 9 || exit 0" in startup(f.p.profile)


def test_bad_historical_record_does_not_block_valid_profile_or_offers(f):
    old = f.svc.journal.path(f.p.plan_id, ".record.json")
    record = json.loads(old.read_text())
    record["state"] = True  # malformed legacy provider state
    old.write_text(json.dumps(record))
    before = old.read_bytes()
    info = f.m.overview()
    assert info["configured"]
    assert info["reason"] is None
    assert info["environments"][0]["error"] == "vast.management_journal_invalid"
    assert f.m.search(30)["offers"]
    assert old.read_bytes() == before
    f.svc.client.create.assert_not_called()


def test_worker_waits_for_short_operation_lock_instead_of_losing_order(f):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from venom_core.services.vast_environments.store import Journal

    f.m.order(f.p.plan_id, False)
    entered = Event()

    def invoke_worker():
        entered.set()
        run(f)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Journal(f.m.journal.root / "management-locks").lock(f.p.plan_id):
            future = pool.submit(invoke_worker)
            assert entered.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
            f.svc.client.create.assert_not_called()
        future.result(timeout=2)
    assert f.m.row(f.p.plan_id)["phase"] == "ready"
    f.svc.client.create.assert_called_once()


@pytest.mark.parametrize("bad_state", [True, 7, {"state": "running"}, ["running"]])
def test_invalid_provider_status_does_not_corrupt_durable_record(f, bad_state):
    f.svc.create(f.p.plan_id)
    f.svc.client.instance.return_value["actual_status"] = bad_state
    with pytest.raises(VastError, match="vast.instance_status_invalid"):
        f.svc.reconcile(f.p.plan_id)
    record = f.svc.journal.record(f.p.plan_id)
    assert record.state == "unknown"
    assert all(isinstance(item["state"], str) for item in record.events)
    assert record.instance_id == 88


@pytest.mark.parametrize("escape", ["outside", "symlink", "known-hosts"])
def test_ssh_profile_cannot_probe_or_use_files_outside_private_stores(
    tmp_path, monkeypatch, escape
):
    store = tmp_path / "ssh"
    store.mkdir()
    key = store / "key"
    key.write_text("private-fixture")
    (store / "key.pub").write_text("public-fixture")
    outside = tmp_path / "outside"
    outside.write_text("not-an-SSH-credential")
    known = store / "known_hosts"
    identity = key
    if escape == "outside":
        identity = outside
    elif escape == "symlink":
        identity = store / "linked"
        identity.symlink_to(outside)
    else:
        known = outside
    monkeypatch.setattr(config, "TRUSTED_SSH_ROOTS", (store,))
    monkeypatch.setattr(
        config,
        "ssh_profile",
        lambda _: {"identity_file": str(identity), "known_hosts": str(known)},
    )
    with pytest.raises(VastError, match="vast.invalid_ssh_profile"):
        config.ssh_paths()


def test_cli_history_is_not_presented_as_a_current_management_order(f):
    row = f.m.plan(12, 30, Decimal("0.5"), Decimal("1"))
    plan_id = row["plan_id"]
    f.svc.journal.path(plan_id, ".management.json").unlink()
    f.m.client_factory.reset_mock()
    overview = f.m.overview()
    assert all(item["plan_id"] != plan_id for item in overview["environments"])
    entry = next(item for item in overview["history"] if item["plan_id"] == plan_id)
    assert entry["state"] == "planned"
    assert not entry["connected"]
    f.m.client_factory.assert_not_called()
    f.connection.attach.assert_not_called()
    assert f.svc.journal.path(plan_id, ".plan.json").exists()


def test_damaged_cli_attempt_remains_visible_in_history(f):
    plan_id = f.p.plan_id
    f.svc.journal.path(plan_id, ".management.json").unlink()
    f.svc.journal.path(plan_id, ".record.json").write_text("{}")
    overview = f.m.overview()
    assert overview["environments"] == []
    assert overview["history"][0]["plan_id"] == plan_id
    assert overview["history"][0]["error"] == "vast.management_journal_invalid"
    assert not overview["history"][0]["connected"]
    f.m.client_factory.assert_not_called()


def test_attached_cli_plan_remains_history_with_observed_connection(f):
    f.svc.journal.path(f.p.plan_id, ".management.json").unlink()
    f.connection.attach(f.p.plan_id)
    overview = f.m.overview()
    assert overview["environments"] == []
    assert overview["history"][0]["plan_id"] == f.p.plan_id
    assert overview["history"][0]["phase"] == "planned"
    assert overview["history"][0]["connected"] is True
    f.m.client_factory.assert_not_called()


def test_search_only_returns_eligible_offers_sorted_by_exact_hourly_rate_before_limit(
    f, monkeypatch
):
    def assessed(offer_id, price, status="eligible"):
        value = f.p.assessment.model_copy(deep=True)
        value.offer["id"] = offer_id
        value.status = status
        value.quote.hourly_usd = Decimal(price)
        value.quote.total_usd = Decimal(price) / 2
        return value

    rejected = [assessed(i, "0.01", "ineligible") for i in range(1, 106)]
    rows = [
        *rejected,
        assessed(202, "0.123449"),
        assessed(203, "0.123441"),
        assessed(201, "0.2"),
        assessed(204, "0.01", "unknown"),
    ]
    monkeypatch.setattr(management.Environments, "search", lambda self, profile: rows)
    offers = f.m.search(30)["offers"]
    assert [item["offer_id"] for item in offers] == [203, 202, 201]
    assert offers[0]["hourly_usd"] == "0.123441"
    assert offers[0]["total_usd"] == "0.0617205"
    f.svc.client.create.assert_not_called()


def test_search_limits_after_price_ordering_with_stable_id_ties(f, monkeypatch):
    rows = []
    for offer_id in range(105, 0, -1):
        value = f.p.assessment.model_copy(deep=True)
        value.offer["id"] = offer_id
        value.quote.hourly_usd = Decimal("0.2")
        rows.append(value)
    monkeypatch.setattr(management.Environments, "search", lambda self, profile: rows)
    assert [item["offer_id"] for item in f.m.search(30)["offers"]] == list(
        range(1, 101)
    )


@pytest.mark.parametrize("field", ["hourly_usd", "total_usd"])
@pytest.mark.parametrize(
    "price", [None, Decimal("NaN"), Decimal("Infinity"), Decimal("-1")]
)
def test_search_hides_unusable_prices_even_if_assessment_says_eligible(
    f, monkeypatch, field, price
):
    value = f.p.assessment.model_copy(deep=True)
    setattr(value.quote, field, price)
    monkeypatch.setattr(
        management.Environments, "search", lambda self, profile: [value]
    )
    assert f.m.search(30)["offers"] == []


@pytest.mark.parametrize("offer_id", [None, True, 0, -1])
def test_search_hides_unusable_offer_id(f, monkeypatch, offer_id):
    value = f.p.assessment.model_copy(deep=True)
    value.offer["id"] = offer_id
    monkeypatch.setattr(
        management.Environments, "search", lambda self, profile: [value]
    )
    assert f.m.search(30)["offers"] == []


def test_search_qualifies_candidates_beyond_first_provider_hundred(f):
    base = f.svc.client.offers.return_value[0]
    candidates = [
        {**base, "id": number, "cpu_arch": "incompatible"} for number in range(1, 101)
    ]
    candidates.append(
        {
            **base,
            "id": 1001,
            "search": {"totalHour": "0.123441", "diskHour": "0.02"},
        }
    )
    f.svc.client.offers.reset_mock()
    f.svc.client.offers.side_effect = lambda disk, filters, *, limit: candidates[:limit]
    offers = f.m.search(30)["offers"]
    assert [item["offer_id"] for item in offers] == [1001]
    assert offers[0]["hourly_usd"] == "0.123441"
    assert all(
        call.kwargs["limit"] == 1000 for call in f.svc.client.offers.call_args_list
    )
    f.svc.client.create.assert_not_called()


@pytest.mark.parametrize("usd", ["0", "0.123456789"])
def test_billing_displays_only_recorded_provider_amounts(f, usd):
    record = f.svc.journal.record(f.p.plan_id)
    record.reports["costs"] = {
        "currency": "USD",
        "status": "provisional",
        "provider_reported": {"usd": usd},
        "estimate": {"usd": "999"},
    }
    f.svc.journal.save_record(record)
    result = f.m.row(f.p.plan_id)
    assert result["billing_status"] == "reported"
    assert result["billed_usd"] == usd
    f.m.client_factory.assert_not_called()


@pytest.mark.parametrize(
    "state,expected",
    [
        ("planned", "not_applicable"),
        ("destroyed", "unverified"),
        ("failed", "unverified"),
    ],
)
def test_missing_billing_is_a_status_and_never_a_zero_amount(f, state, expected):
    record = f.svc.journal.record(f.p.plan_id)
    record.state = state
    f.svc.journal.save_record(record)
    result = f.m.row(f.p.plan_id)
    assert result["billing_status"] == expected
    assert result["billed_usd"] is None
    f.m.client_factory.assert_not_called()


@pytest.mark.parametrize(
    "report",
    [
        {
            "currency": "USD",
            "status": "unavailable",
            "provider_reported": {"usd": None},
        },
        {
            "currency": "USD",
            "status": "unavailable",
            "provider_reported": {"usd": "NaN"},
        },
        {
            "currency": "USD",
            "status": "unavailable",
            "provider_reported": {"usd": "-1"},
        },
    ],
)
def test_unavailable_billing_ignores_estimates_and_invalid_amounts(f, report):
    record = f.svc.journal.record(f.p.plan_id)
    record.reports["costs"] = {**report, "estimate": {"usd": "0.5"}}
    f.svc.journal.save_record(record)
    result = f.m.row(f.p.plan_id)
    assert result["billing_status"] == "unavailable"
    assert result["billed_usd"] is None


def test_api_billing_sync_is_cached_offline_and_links_history(api, f):
    root = "/api/v1/vast/environments"
    record = f.svc.journal.record(f.p.plan_id)
    record.instance_id, record.state, record.submitted_at = 88, "destroyed", now()
    f.svc.journal.save_record(record)
    f.svc.client.account.return_value = {"credit": "8.9", "balance": 0}
    f.svc.client.charges.return_value = [{"source": "instance-88", "amount": "0.01"}]
    assert api.post(root + "/billing/sync", json={"unknown": True}).status_code == 422
    response = api.post(root + "/billing/sync", json={})
    assert response.status_code == 200
    assert response.json()["credit_usd"] == "8.9"
    assert "instances" not in response.json()
    count = f.svc.client.charges.call_count
    result = api.get(root).json()
    assert result["environments"][0]["billed_usd"] == "0.31"
    assert result["billing"]["total_usd"] == "0.31"
    assert f.svc.client.charges.call_count == count
    assert api.post(root + "/billing/sync", json={}).status_code == 200
    assert f.svc.client.charges.call_count == count
    assert api.post(root + "/billing/sync", json={"reconcile": True}).status_code == 200
    assert f.svc.client.charges.call_count == count * 2
    f.m.is_enabled = lambda: False
    assert api.post(root + "/billing/sync", json={}).status_code == 503
    assert api.get(root).json()["billing"]["total_usd"] == "0.31"
    f.svc.client.create.assert_not_called()


def test_legacy_billing_marks_incomplete_provider_amount_as_partial(f):
    record = f.svc.journal.record(f.p.plan_id)
    record.reports["costs"] = {
        "currency": "USD",
        "status": "provisional",
        "provider_reported": {"usd": "0.25", "unknown_amounts": 1},
    }
    f.svc.journal.save_record(record)
    assert f.m.row(f.p.plan_id)["billing_status"] == "partial"
    assert f.m.row(f.p.plan_id)["billed_usd"] == "0.25"
