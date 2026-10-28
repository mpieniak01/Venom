"""Connection tests use fake Vast, loopback-shaped HTTP transport and fake SSH."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import digest
from venom_core.services.vast_chat_connection import (
    ManagedTunnel,
    VastChatConnection,
    _models,
)
from venom_core.services.vast_environments.startup import startup

DIGEST = "d" * 64


class FakeTunnel:
    endpoint = "http://127.0.0.1:55444"

    def __init__(self):
        self.running = True
        self.close_count = 0

    def alive(self):
        return self.running

    def close(self):
        self.running = False
        self.close_count += 1


@pytest.fixture
def connection(tmp_path):
    svc, plan, _ = source_service.__wrapped__(tmp_path)
    plan.profile.mode = "ollama"
    plan.profile.model = "demo:latest"
    plan.profile.model_digest = DIGEST
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    svc.client.instance.return_value.update(host_id=3, machine_id=4)
    svc.client.reset_mock()
    tunnel = FakeTunnel()
    requests = []
    responses = {
        "/api/version": {"version": "0.40.11"},
        "/api/tags": {
            "models": [
                {"name": "hf.co/a/long-model", "digest": DIGEST, "size": 17},
                {"name": "demo:latest", "digest": DIGEST, "size": 17},
            ]
        },
        "/api/show": {"capabilities": ["completion"], "parameters": "num_ctx 4096"},
    }

    def handler(request):
        requests.append(request)
        value = responses[request.url.path]
        if isinstance(value, int):
            return httpx.Response(value)
        return httpx.Response(200, json=value)

    settings = SimpleNamespace(VAST_API_KEY=SecretStr("test-key"))
    manager = VastChatConnection(
        settings,
        journal=svc.journal,
        client_factory=Mock(return_value=svc.client),
        tunnel_factory=Mock(return_value=tunnel),
        http_factory=lambda **kwargs: httpx.Client(
            **kwargs, transport=httpx.MockTransport(handler)
        ),
    )
    return manager, svc, plan, tunnel, requests, responses


def test_attach_probes_own_instance_and_deduplicates_remote_catalog(connection):
    manager, svc, plan, tunnel, requests, _ = connection
    state = manager.attach(plan.plan_id)
    assert state["available"] and state["endpoint"] == tunnel.endpoint + "/v1"
    assert state["target_id"] == f"ollama@vast:{plan.plan_id}:88"
    assert [row["name"] for row in state["models"]] == ["demo:latest"]
    assert all(request.url.host == "127.0.0.1" for request in requests)
    svc.client.create.assert_not_called()
    svc.client.set_state.assert_not_called()
    assert all(request.method == "GET" for request in requests)


def test_status_without_refresh_has_no_network_and_tracks_child_exit(connection):
    manager, svc, plan, tunnel, requests, _ = connection
    state = manager.attach(plan.plan_id)
    total = len(requests)
    svc.client.reset_mock()
    assert manager.status(refresh=False) == state
    assert len(requests) == total
    svc.client.instance.assert_not_called()
    tunnel.running = False
    value = manager.status(refresh=False)
    assert not value["available"] and value["endpoint"] is None
    assert value["target_id"] == state["target_id"]
    assert value["error"] == "vast.tunnel_failed"


@pytest.mark.parametrize("change", ["stopped", "machine", "missing", "http", "version"])
def test_failed_refresh_revokes_old_endpoint_and_closes_tunnel(connection, change):
    manager, svc, plan, tunnel, _, responses = connection
    state = manager.attach(plan.plan_id)
    if change == "stopped":
        svc.client.instance.return_value["actual_status"] = "stopped"
    elif change == "machine":
        svc.client.instance.return_value["machine_id"] = 999
    elif change == "missing":
        svc.client.instance.side_effect = VastError("vast.http_error", 404)
    elif change == "version":
        responses["/api/version"] = {"version": ""}
    else:
        responses["/api/tags"] = 500
    result = manager.status()
    assert not result["available"] and result["endpoint"] is None
    assert result["models"] == []
    assert result["target_id"] == state["target_id"]
    assert tunnel.close_count == 1
    svc.client.close.assert_called_once()
    with pytest.raises(VastError, match="vast.chat_unavailable"):
        manager.require_available()


def test_restart_loads_identity_only_and_does_not_connect(connection):
    manager, svc, plan, _, _, _ = connection
    original = manager.attach(plan.plan_id)
    manager.close()
    factory = Mock()
    restarted = VastChatConnection(
        manager.settings, journal=svc.journal, client_factory=factory
    )
    value = restarted.status()
    assert not value["available"] and value["endpoint"] is None
    assert value["target_id"] == original["target_id"]
    assert value["generation"] != original["generation"]
    assert value["error"] == "vast.chat_attach_required"
    factory.assert_not_called()
    intent = svc.journal.root / "chat-target.json"
    assert intent.stat().st_mode & 0o777 == 0o600
    assert "55444" not in intent.read_text()


def test_detach_forgets_intent_and_never_stops_instance(connection):
    manager, svc, plan, tunnel, _, _ = connection
    before = manager.attach(plan.plan_id)
    result = manager.detach()
    assert result["target_id"] is None and not result["available"]
    assert result["generation"] != before["generation"]
    assert tunnel.close_count == 1
    svc.client.destroy.assert_not_called()
    svc.client.set_state.assert_not_called()
    restarted = VastChatConnection(manager.settings, journal=svc.journal)
    assert restarted.status()["target_id"] is None


@pytest.mark.parametrize("plan_id", ["../bad", "/tmp/bad", "a" * 31])
def test_reject_unmanaged_plan_id_before_network(connection, plan_id):
    manager, *_ = connection
    with pytest.raises(VastError, match="vast.invalid_plan_id"):
        manager.attach(plan_id)
    manager.client_factory.assert_not_called()


def test_inspect_plan_cannot_be_attached_as_ollama(connection):
    manager, svc, plan, *_ = connection
    plan.profile.mode = "inspect"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.chat_ollama_plan_required"):
        manager.attach(plan.plan_id)
    manager.client_factory.assert_not_called()


def test_model_metadata_comes_from_same_target_without_generation(connection):
    manager, _, plan, _, requests, _ = connection
    manager.attach(plan.plan_id)
    assert manager.model_details("demo:latest")["capabilities"] == ["completion"]
    show = [r for r in requests if r.url.path == "/api/show"]
    assert len(show) == 1 and json.loads(show[0].content) == {"model": "demo:latest"}
    with pytest.raises(VastError, match="vast.chat_model_missing"):
        manager.model_details("local-only:latest")
    assert len([r for r in requests if r.url.path == "/api/show"]) == 1


@pytest.mark.parametrize(
    "row",
    [
        {"name": "x", "digest": "bad", "size": 1},
        {"name": "x bad", "digest": DIGEST, "size": 1},
        {"name": "x", "digest": DIGEST, "size": -1},
        {"name": "x", "digest": DIGEST, "size": True},
    ],
)
def test_invalid_catalog_never_becomes_available(row):
    with pytest.raises(VastError, match="vast.chat_models_invalid"):
        _models({"models": [row]})


def test_invalid_or_oversized_catalog():
    for value in ({}, {"models": None}, {"models": [{}] * 257}):
        with pytest.raises(VastError, match="vast.chat_models_invalid"):
            _models(value)


def test_invalid_persisted_intent_cannot_escape_journal(connection):
    manager, svc, *_ = connection
    svc.journal.write(
        svc.journal.root / "chat-target.json",
        {"target": {"plan_id": "../escape", "instance_id": 88}},
    )
    restarted = VastChatConnection(manager.settings, journal=svc.journal)
    assert restarted.status()["error"] == "vast.chat_intent_invalid"


def test_ssh_uses_strict_existing_args_and_closes_child(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    args = ["ssh", "-o", "StrictHostKeyChecking=yes", "root@fixture.test"]
    monkeypatch.setattr(
        "venom_core.services.vast_chat_connection.ssh_args",
        lambda plan, instance: args.copy(),
    )
    popen = Mock(return_value=process)
    monkeypatch.setattr(
        "venom_core.services.vast_chat_connection.subprocess.Popen", popen
    )
    monkeypatch.setattr(
        "venom_core.services.vast_chat_connection.socket.create_connection",
        Mock(return_value=Mock(__enter__=Mock(), __exit__=Mock())),
    )
    tunnel = ManagedTunnel(Mock(), {})
    called = popen.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in called
    assert "127.0.0.1:11434" in " ".join(called)
    tunnel.close()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)


def test_ssh_failed_start_and_termination_timeout_are_bounded(monkeypatch):
    process = Mock()
    process.poll.return_value = 1
    process.wait.side_effect = [None]
    monkeypatch.setattr(
        "venom_core.services.vast_chat_connection.ssh_args",
        lambda plan, instance: ["ssh", "root@fixture.test"],
    )
    monkeypatch.setattr(
        "venom_core.services.vast_chat_connection.subprocess.Popen",
        Mock(return_value=process),
    )
    with pytest.raises(VastError, match="vast.tunnel_failed"):
        ManagedTunnel(Mock(), {})
    tunnel = object.__new__(ManagedTunnel)
    tunnel.process = process
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("ssh", 5), None]
    tunnel.close()
    process.kill.assert_called_once()


def test_failed_attach_does_not_leave_client_or_tunnel(connection):
    manager, svc, plan, tunnel, _, responses = connection
    responses["/api/tags"] = {"models": [{"name": "bad"}]}
    with pytest.raises(VastError, match="vast.chat_models_invalid"):
        manager.attach(plan.plan_id)
    assert tunnel.close_count == 1
    svc.client.close.assert_called_once()
    assert manager.status(False)["endpoint"] is None


def test_stopped_instance_attach_never_opens_ssh(connection):
    manager, svc, plan, _, _, _ = connection
    svc.client.instance.return_value["actual_status"] = "stopped"
    with pytest.raises(VastError, match="vast.chat_instance_unavailable"):
        manager.attach(plan.plan_id)
    manager.tunnel_factory.assert_not_called()
    assert not manager.status(False)["available"]


def test_empty_catalog_has_no_models_and_does_not_install_them(connection):
    manager, svc, plan, _, requests, responses = connection
    responses["/api/tags"] = {"models": []}
    state = manager.attach(plan.plan_id)
    assert state["available"] and state["models"] == []
    svc.client.create.assert_not_called()
    assert not any(request.url.path == "/api/pull" for request in requests)


def test_metadata_failure_closes_transport(connection):
    manager, _, plan, tunnel, _, responses = connection
    manager.attach(plan.plan_id)
    responses["/api/show"] = 500
    with pytest.raises(VastError, match="vast.chat_unavailable"):
        manager.model_details("demo:latest")
    assert tunnel.close_count == 1
    assert not manager.status(False)["available"]


def test_json_response_limit_cancels_connection(connection):
    manager, _, plan, tunnel, _, responses = connection
    responses["/api/tags"] = {"models": [], "padding": "x" * 2_000_000}
    with pytest.raises(VastError, match="vast.chat_response_limit"):
        manager.attach(plan.plan_id)
    assert tunnel.close_count == 1


def test_show_rejects_non_object_response(connection):
    manager, _, plan, tunnel, _, responses = connection
    manager.attach(plan.plan_id)
    responses["/api/show"] = []
    with pytest.raises(VastError, match="vast.chat_unavailable"):
        manager.model_details("demo:latest")
    assert tunnel.close_count == 1


def test_conditional_detach_cannot_close_other_plan_after_race(connection):
    manager, _svc, plan, tunnel, _requests, _responses = connection
    before = manager.attach(plan.plan_id)
    with pytest.raises(VastError, match="vast.chat_detach_target_changed"):
        manager.detach(expected_plan_id="f" * 32)
    assert tunnel.alive()
    assert manager.status(refresh=False)["target_id"] == before["target_id"]
    result = manager.detach(expected_plan_id=plan.plan_id)
    assert not result["available"] and result["target_id"] is None
    assert not tunnel.alive()
