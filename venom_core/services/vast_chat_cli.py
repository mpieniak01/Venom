"""Manual commands address the existing API owner, never spawn another tunnel."""

import json
from urllib.parse import urlparse

import httpx

from venom_core.infrastructure.providers.vast.client import VastError

DEFAULT_API = "http://127.0.0.1:8800"


def api_url(base: str) -> str:
    try:
        parsed = urlparse(base)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError
        parsed.port
    except ValueError:
        raise VastError("vast.chat_local_api_required") from None
    return base.rstrip("/") + "/api/v1/system/vast-chat"


def admin(command: str, base: str = DEFAULT_API, plan_id: str | None = None) -> dict:
    url = api_url(base)
    method, body = "GET", None
    if command == "chat-attach":
        method, url, body = "POST", url + "/attach", {"plan_id": plan_id}
    elif command == "chat-detach":
        method, url = "POST", url + "/detach"
        body = {"plan_id": plan_id} if plan_id is not None else None
    elif command != "chat-status":
        raise VastError("vast.invalid_action")
    try:
        with httpx.Client(
            timeout=60, trust_env=False, follow_redirects=False
        ) as client:
            response = client.request(method, url, json=body)
            if not response.is_success:
                raise VastError("vast.chat_api_rejected", response.status_code)
            result = response.json()
        if not isinstance(result, dict):
            raise ValueError
        return result
    except httpx.ConnectError:
        raise VastError("vast.chat_api_unreachable") from None
    except (httpx.HTTPError, ValueError):
        raise VastError("vast.chat_api_unavailable") from None


def detach_plan(plan_id: str, base: str = DEFAULT_API) -> None:
    from venom_core.services.vast_chat_connection import ROOT

    path = ROOT / "chat-target.json"
    if not path.exists():
        return
    try:
        intent = json.loads(path.read_text()).get("target")
    except (OSError, ValueError, AttributeError):
        raise VastError("vast.chat_intent_invalid") from None
    if intent is None:
        return
    if not isinstance(intent, dict):
        raise VastError("vast.chat_intent_invalid")
    if intent.get("plan_id") != plan_id:
        return
    try:
        status = admin("chat-status", base)
    except VastError as error:
        # A refused connection cannot service a detach. A responding API error or
        # timeout is not proof that its active target can be disregarded.
        if error.code == "vast.chat_api_unreachable":
            return
        raise
    if status.get("plan_id") not in {None, plan_id}:
        raise VastError("vast.chat_detach_target_changed")
    admin("chat-detach", base, plan_id)
