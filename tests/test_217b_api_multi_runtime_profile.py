"""Testy Fazy 4 (217B): endpointy API systemowego dla multi_runtime_profile.

Weryfikują:
1. GET /api/v1/runtime/multi-runtime/profile — proxy do daemona lub fallback.
2. POST /api/v1/runtime/multi-runtime/profile — proxy do daemona z jawnym apply_mode.
3. 503 gdy daemon niedostępny.
4. Brak kolizji z POST /api/v1/runtime/{service}/{action}.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_runtime as runtime_routes


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(runtime_routes.router)
    return TestClient(app, raise_server_exceptions=False)


def _daemon_profile_payload(
    *,
    model_id: str = "google/gemma-4-E2B-it",
    max_new_tokens: int = 128,
    enable_thinking: bool = False,
    daemon_reachable: bool = True,
) -> dict:
    return {
        "runtime_id": "multi_runtime",
        "daemon_reachable": daemon_reachable,
        "profile": {
            "profile_id": "default",
            "display_name": "Default",
            "runtime_id": "multi_runtime",
            "compatibility": "multi_runtime_native",
            "model_id": model_id,
            "assistant_model_id": None,
            "cache_implementation": None,
            "max_new_tokens": max_new_tokens,
            "image_token_budget": 280,
            "enable_thinking": enable_thinking,
            "reasoning_summary_enabled": False,
            "emotion_detection_enabled": False,
            "emotion_response_style_enabled": False,
            "precision": "int4",
            "quantization_backend": "bitsandbytes",
            "device_target": "auto",
        },
        "apply_matrix": {
            "model_id": "hard_restart",
            "assistant_model_id": "hard_restart",
            "cache_implementation": "soft_reload",
            "max_new_tokens": "live",
            "image_token_budget": "live",
            "enable_thinking": "live",
            "reasoning_summary_enabled": "live",
            "emotion_detection_enabled": "live",
            "emotion_response_style_enabled": "live",
            "precision": "soft_reload",
            "quantization_backend": "soft_reload",
            "device_target": "unsupported",
        },
        "supported_options": {
            "cache_implementation": [None, "static", "dynamic", "offloaded"],
            "precision": ["auto", "float16", "bfloat16", "float32", "int4", "int8"],
            "device_target": ["auto", "cpu", "cuda"],
            "quantization_backend": [None, "bitsandbytes"],
        },
    }


def _update_response_payload(
    *,
    accepted: dict | None = None,
    rejected: list | None = None,
    required_apply_mode: str = "live",
    applied: bool = True,
) -> dict:
    return {
        "accepted": accepted or {},
        "rejected": rejected or [],
        "required_apply_mode": required_apply_mode,
        "applied": applied,
        "message": "1 field(s) accepted (requires live).",
    }


# ---------------------------------------------------------------------------
# GET /api/v1/runtime/multi-runtime/profile
# ---------------------------------------------------------------------------


def test_get_profile_proxies_to_daemon():
    profile_payload = _daemon_profile_payload()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = profile_payload

    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        resp = _client().get("/api/v1/runtime/multi-runtime/profile")

    assert resp.status_code == 200
    data = resp.json()
    assert data["runtime_id"] == "multi_runtime"
    assert data["daemon_reachable"] is True
    assert data["profile"]["model_id"] == "google/gemma-4-E2B-it"


def test_get_profile_apply_matrix_forwarded():
    profile_payload = _daemon_profile_payload()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = profile_payload

    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        data = _client().get("/api/v1/runtime/multi-runtime/profile").json()

    assert data["apply_matrix"]["max_new_tokens"] == "live"
    assert data["apply_matrix"]["cache_implementation"] == "soft_reload"
    assert data["apply_matrix"]["model_id"] == "hard_restart"
    assert data["apply_matrix"]["precision"] == "soft_reload"


def test_get_profile_fallback_when_daemon_unreachable():
    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        resp = _client().get("/api/v1/runtime/multi-runtime/profile")

    assert resp.status_code == 200
    data = resp.json()
    assert data["daemon_reachable"] is False
    assert data["runtime_id"] == "multi_runtime"


def test_get_profile_fallback_contains_default_profile():
    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        data = _client().get("/api/v1/runtime/multi-runtime/profile").json()

    assert "profile" in data
    assert "apply_matrix" in data
    assert "supported_options" in data


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/multi-runtime/profile
# ---------------------------------------------------------------------------


def test_post_profile_live_update_proxied():
    update_payload = _update_response_payload(
        accepted={"max_new_tokens": 512},
        required_apply_mode="live",
        applied=True,
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = update_payload

    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        resp = _client().post(
            "/api/v1/runtime/multi-runtime/profile",
            json={"max_new_tokens": 512},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["required_apply_mode"] == "live"
    assert data["applied"] is True
    assert data["accepted"]["max_new_tokens"] == 512


def test_post_profile_soft_reload_forwarded():
    update_payload = _update_response_payload(
        accepted={"cache_implementation": "static"},
        required_apply_mode="soft_reload",
        applied=False,
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = update_payload

    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        data = (
            _client()
            .post(
                "/api/v1/runtime/multi-runtime/profile",
                json={"cache_implementation": "static"},
            )
            .json()
        )

    assert data["required_apply_mode"] == "soft_reload"
    assert data["applied"] is False


def test_post_profile_503_when_daemon_unreachable():
    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        resp = _client().post(
            "/api/v1/runtime/multi-runtime/profile",
            json={"max_new_tokens": 256},
        )

    assert resp.status_code == 503
    assert "multi_runtime" in resp.json()["detail"].lower()


def test_post_profile_daemon_500_forwarded():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "internal error"

    with patch("venom_core.api.routes.system_runtime.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        resp = _client().post(
            "/api/v1/runtime/multi-runtime/profile",
            json={"max_new_tokens": 256},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Routing: brak kolizji z /runtime/{service}/{action}
# ---------------------------------------------------------------------------


def test_service_action_endpoint_still_reachable():
    with (
        patch.object(
            runtime_routes.runtime_controller,
            "get_all_services_status",
            return_value=[],
        ),
        patch(
            "venom_core.api.routes.system_runtime.system_deps.get_service_monitor",
            return_value=None,
        ),
    ):
        resp = _client().get("/api/v1/runtime/status")
    assert resp.status_code == 200
