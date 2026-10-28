"""Manual tunnel commands never rent resources or forward credentials."""

import json
from unittest.mock import MagicMock

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
