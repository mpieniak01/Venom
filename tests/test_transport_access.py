"""The shared entry grants operator access without impersonating localhost."""

import pytest
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from venom_core.api.routes import academy, knowledge
from venom_core.api.routes.permission_denied_contract import resolve_actor_from_request
from venom_core.api.routes.system_config import require_localhost_request
from venom_core.api.transport_access import (
    TransportAccessMiddleware,
    is_localhost_request,
    require_operator_request,
)
from venom_core.config import SETTINGS


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(SETTINGS, "VENOM_OPERATOR_ACCESS", "trusted_lan")
    monkeypatch.setattr(
        SETTINGS, "VENOM_LAN_ORIGINS", "http://venom.test:3300,http://localhost:3300"
    )
    app = FastAPI()
    app.add_middleware(TransportAccessMiddleware)

    @app.api_route("/operator", methods=["GET", "POST"])
    def operator(request: Request):
        require_operator_request(request)
        return {"host": request.client.host, "local": is_localhost_request(request)}

    @app.get("/admin")
    def admin(request: Request):
        require_localhost_request(request)
        return {"ok": True}

    @app.get("/academy-admin")
    def academy_admin(request: Request):
        try:
            academy.require_localhost_request(request)
        except academy.AcademyRouteError as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        return {"ok": True}

    @app.get("/knowledge-admin")
    def knowledge_admin(request: Request):
        knowledge._enforce_knowledge_entries_access(request)
        return {"ok": True}

    @app.get("/audit-actor")
    def audit_actor(request: Request):
        return {"actor": resolve_actor_from_request(request)}

    @app.get("/metadata")
    def metadata(request: Request):
        return {
            "host": request.client.host,
            "verified": request.scope.get("venom.verified_proxy", False),
            "headers": dict(request.headers),
        }

    @app.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        await socket.send_json(
            {"verified": socket.scope.get("venom.verified_proxy", False)}
        )
        await socket.close()

    return app


def proxy_headers(address="192.168.1.10", shared="1"):
    return {
        "host": "venom.test:3300",
        "origin": "http://venom.test:3300",
        "x-venom-proxy": "1",
        "x-venom-client-address": address,
        "x-venom-shared-entry": shared,
    }


def test_shared_proxy_grants_operator_but_never_admin(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = proxy_headers()
        assert client.post("/operator", headers=headers).json() == {
            "host": "192.168.1.10",
            "local": False,
        }
        assert client.get("/admin", headers=headers).status_code == 403


def test_windows_loopback_relay_and_forged_localhost_cannot_be_admin(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = proxy_headers("127.0.0.1")
        headers.update(
            {
                "host": "localhost:3300",
                "origin": "http://localhost:3300",
                "x-forwarded-for": "127.0.0.1",
            }
        )
        assert client.post("/operator", headers=headers).status_code == 200
        assert client.get("/admin", headers=headers).status_code == 403


def test_direct_local_api_keeps_local_administration(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        assert client.get("/admin").status_code == 200


@pytest.mark.parametrize("address", ["192.168.1.44", "203.0.113.1"])
def test_untrusted_peer_cannot_forge_proxy_metadata(app, address):
    with TestClient(app, client=(address, 12000)) as client:
        headers = proxy_headers("127.0.0.1", "0")
        assert client.post("/operator", headers=headers).status_code == 403
        assert client.get("/admin", headers=headers).status_code == 403
        response = client.get("/metadata", headers=headers).json()
        assert response["verified"] is False
        assert response["host"] == address
        assert "x-venom-proxy" not in response["headers"]


@pytest.mark.parametrize(
    "origin,host",
    [
        ("http://evil.test:3300", "venom.test:3300"),
        ("", "venom.test:3300"),
        ("http://venom.test:3300", "evil.test:3300"),
    ],
)
def test_operator_mutations_require_exact_configured_host_and_origin(app, origin, host):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = {**proxy_headers(), "origin": origin, "host": host}
        assert client.post("/operator", headers=headers).status_code == 403


def test_secure_profile_does_not_enable_lan_operator(app, monkeypatch):
    monkeypatch.setattr(SETTINGS, "VENOM_OPERATOR_ACCESS", "secure")
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        assert client.get("/operator", headers=proxy_headers()).status_code == 403


@pytest.mark.parametrize("profile", ["secure", "trusted_lan"])
@pytest.mark.parametrize("address", [None, "bad", "é", ""])
def test_invalid_metadata_cannot_inherit_loopback_privileges(
    app, monkeypatch, profile, address
):
    monkeypatch.setattr(SETTINGS, "VENOM_OPERATOR_ACCESS", profile)
    headers = {**proxy_headers(address, "0"), "x-authenticated-user": "admin"}
    if address is None:
        headers.pop("x-venom-client-address")
    if address == "é":
        # ASGI accepts raw header bytes; HTTPX restricts Python str headers to ASCII.
        headers["x-venom-client-address"] = address.encode("utf-8")
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        assert client.get("/metadata", headers=headers).json()["verified"] is False
        assert client.post("/operator", headers=headers).status_code == 403
        for path in ("/admin", "/academy-admin", "/knowledge-admin"):
            assert client.get(path, headers=headers).status_code == 403
        assert client.get("/audit-actor", headers=headers).json() == {
            "actor": "client:127.0.0.1"
        }


def test_valid_secure_loopback_proxy_metadata_preserves_local_access(app, monkeypatch):
    monkeypatch.setattr(SETTINGS, "VENOM_OPERATOR_ACCESS", "secure")
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = proxy_headers("127.0.0.1", "0")
        assert client.get("/metadata", headers=headers).json()["verified"] is True
        assert client.get("/admin", headers=headers).status_code == 200
        assert client.post("/operator", headers=headers).json()["local"] is True


def test_proxy_metadata_is_removed_after_normalization(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = proxy_headers()
        response = client.get("/metadata", headers=headers).json()
        assert response["verified"] is True
        assert not any(name.startswith("x-venom-") for name in response["headers"])


def test_plain_asgi_middleware_does_not_touch_lifespan(app):
    with TestClient(app) as client:
        assert client.get("/metadata").status_code == 200


def test_websocket_metadata_uses_the_same_unbuffered_boundary(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        with client.websocket_connect("/ws", headers=proxy_headers()) as socket:
            assert socket.receive_json() == {"verified": True}


@pytest.mark.parametrize("path", ["/academy-admin", "/knowledge-admin"])
def test_other_local_only_routes_reject_shared_loopback_relay(app, path):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        assert client.get(path).status_code == 200
        headers = proxy_headers("127.0.0.1")
        headers.update({"host": "localhost:3300", "origin": "http://localhost:3300"})
        assert client.get(path, headers=headers).status_code == 403


def test_shared_loopback_relay_cannot_assert_an_audit_identity(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = {**proxy_headers("127.0.0.1"), "x-authenticated-user": "admin"}
        assert client.get("/audit-actor", headers=headers).json() == {
            "actor": "client:127.0.0.1"
        }


def test_backend_lan_profile_fails_closed_when_entry_profile_is_misconfigured(app):
    with TestClient(app, client=("127.0.0.1", 12000)) as client:
        headers = proxy_headers("127.0.0.1", "0")
        assert client.get("/admin", headers=headers).status_code == 403
        assert client.get("/academy-admin", headers=headers).status_code == 403
