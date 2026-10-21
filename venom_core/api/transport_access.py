"""Public access boundary for the shared operator entry and localhost administration.

The Node entry overwrites transport metadata. Only a loopback TCP peer may supply
it. A shared LAN entry never proves localhost, including Windows portproxy relays.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from venom_core.config import SETTINGS

_LOCALHOSTS = {"127.0.0.1", "::1", "localhost"}
_SHARED_ENTRY_SCOPE_KEY = "venom.shared_entry"
_PROXY_HEADERS = {
    b"x-venom-proxy",
    b"x-venom-client-address",
    b"x-venom-shared-entry",
}


def is_shared_entry(request: Request | None) -> bool:
    scope = getattr(request, "scope", {})
    return isinstance(scope, Mapping) and bool(
        scope.get(_SHARED_ENTRY_SCOPE_KEY, False)
    )


def is_localhost_request(request: Request) -> bool:
    return bool(
        request.client
        and request.client.host in _LOCALHOSTS
        and not is_shared_entry(request)
    )


def require_operator_request(request: Request) -> None:
    """Explicit opt-in for operator routes; route tokens/mutation guards still apply."""
    if is_localhost_request(request):
        return
    origins = {
        value.strip().rstrip("/")
        for value in SETTINGS.VENOM_LAN_ORIGINS.split(",")
        if value.strip()
    }
    origin = request.headers.get("origin", "").rstrip("/")
    host = request.headers.get("host", "").lower()
    allowed_hosts = {urlsplit(value).netloc.lower() for value in origins}
    allowed_origin = origin in origins if origin else request.method in {"GET", "HEAD"}
    if (
        SETTINGS.VENOM_OPERATOR_ACCESS == "trusted_lan"
        and request.scope.get("venom.verified_proxy", False)
        and host in allowed_hosts
        and allowed_origin
    ):
        return
    raise HTTPException(
        status_code=403, detail={"reason_code": "OPERATOR_ACCESS_DENIED"}
    )


class TransportAccessMiddleware:
    """ASGI-only metadata normalization; HTTP/SSE/WS bodies are never buffered."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            headers = dict(scope.get("headers", []))
            peer = scope.get("client")
            if (
                peer
                and peer[0] in _LOCALHOSTS
                and headers.get(b"x-venom-proxy") == b"1"
            ):
                # A proxy marker never proves localhost when its provenance is
                # incomplete. Valid metadata below can establish the exact policy.
                scope[_SHARED_ENTRY_SCOPE_KEY] = True
                try:
                    address = str(
                        ipaddress.ip_address(
                            headers.get(b"x-venom-client-address", b"").decode("ascii")
                        )
                    )
                except ValueError:
                    address = ""
                if address:
                    scope["client"] = (address, 0)
                    scope["venom.verified_proxy"] = True
                    scope[_SHARED_ENTRY_SCOPE_KEY] = (
                        headers.get(b"x-venom-shared-entry") == b"1"
                        or SETTINGS.VENOM_OPERATOR_ACCESS == "trusted_lan"
                    )
            scope["headers"] = [
                (key, value)
                for key, value in scope.get("headers", [])
                if key not in _PROXY_HEADERS
            ]
        await self.app(scope, receive, send)
