"""Manual tunnel commands never rent resources or forward credentials."""

import json
from unittest.mock import MagicMock

import httpx
import pytest

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services import vast_chat_cli as cli


@pytest.mark.parametrize(
    "base",
    [
        "http://evil",
        "http://127.0.0.1@evil",
        "http://localhost/x",
        "http://localhost?q=x",
        "file:///tmp/api",
    ],
)
def test_reject_nonlocal_api(base):
    with pytest.raises(VastError):
        cli.api_url(base)


@pytest.mark.parametrize(
    "command,path,method",
    [
        ("chat-status", "", "GET"),
        ("chat-detach", "/detach", "POST"),
        ("chat-attach", "/attach", "POST"),
    ],
)
def test_manual_api(monkeypatch, command, path, method):
    client = MagicMock()
    client.request.return_value.is_success = True
    client.request.return_value.json.return_value = {"available": True}
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(cli.httpx, "Client", factory)
    assert cli.admin(command, "http://127.0.0.1:8800", "a" * 32) == {"available": True}
    args, kwargs = client.request.call_args
    assert args == (method, "http://127.0.0.1:8800/api/v1/system/vast-chat" + path)
    assert kwargs["json"] == (
        {"plan_id": "a" * 32} if command in {"chat-attach", "chat-detach"} else None
    )
    assert factory.call_args.kwargs["follow_redirects"] is False
    assert factory.call_args.kwargs["trust_env"] is False


def test_cleanup_only_detaches_matching_plan(monkeypatch, tmp_path):
    from venom_core.services import vast_chat_connection as transport

    monkeypatch.setattr(transport, "ROOT", tmp_path)
    admin = MagicMock(return_value={"plan_id": "a" * 32})
    monkeypatch.setattr(cli, "admin", admin)
    cli.detach_plan("a" * 32)
    admin.assert_not_called()
    intent = tmp_path / "chat-target.json"
    intent.write_text(json.dumps({"target": {"plan_id": "b" * 32}}))
    cli.detach_plan("a" * 32)
    admin.assert_not_called()
    intent.write_text(json.dumps({"target": {"plan_id": "a" * 32}}))
    cli.detach_plan("a" * 32)
    assert [call.args[0] for call in admin.call_args_list] == [
        "chat-status",
        "chat-detach",
    ]


def test_cleanup_rejects_corrupt_intent(monkeypatch, tmp_path):
    from venom_core.services import vast_chat_connection as transport

    monkeypatch.setattr(transport, "ROOT", tmp_path)
    (tmp_path / "chat-target.json").write_text("bad")
    with pytest.raises(VastError):
        cli.detach_plan("a" * 32)


@pytest.mark.parametrize("target", ["bad", [], 1, True])
def test_detach_rejects_invalid_target_shape(monkeypatch, tmp_path, target):
    from venom_core.services import vast_chat_connection as transport

    monkeypatch.setattr(transport, "ROOT", tmp_path)
    (tmp_path / "chat-target.json").write_text(json.dumps({"target": target}))
    with pytest.raises(VastError, match="vast.chat_intent_invalid"):
        cli.detach_plan("a" * 32)


@pytest.mark.parametrize(
    "code",
    [
        "vast.chat_api_rejected",
        "vast.chat_api_unavailable",
        "vast.chat_api_unreachable",
    ],
)
def test_cleanup_only_ignores_connection_refusal(monkeypatch, tmp_path, code):
    from venom_core.services import vast_chat_connection as transport

    monkeypatch.setattr(transport, "ROOT", tmp_path)
    (tmp_path / "chat-target.json").write_text(
        json.dumps({"target": {"plan_id": "a" * 32}})
    )
    admin = MagicMock(side_effect=VastError(code))
    monkeypatch.setattr(cli, "admin", admin)
    if code == "vast.chat_api_unreachable":
        cli.detach_plan("a" * 32)
    else:
        with pytest.raises(VastError, match=code):
            cli.detach_plan("a" * 32)
    admin.assert_called_once_with("chat-status", cli.DEFAULT_API)


@pytest.mark.parametrize(
    "error,code",
    [
        (httpx.ConnectError("refused"), "vast.chat_api_unreachable"),
        (httpx.ReadTimeout("timeout"), "vast.chat_api_unavailable"),
    ],
)
def test_admin_distinguishes_connection_failure_from_timeout(monkeypatch, error, code):
    factory = MagicMock()
    factory.return_value.__enter__.return_value.request.side_effect = error
    monkeypatch.setattr(cli.httpx, "Client", factory)
    with pytest.raises(VastError, match=code):
        cli.admin("chat-status")
