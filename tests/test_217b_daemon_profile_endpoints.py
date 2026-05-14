"""Testy Fazy 3 (217B): endpointy /v1/daemon/profile w multi_runtime.

Weryfikują:
1. GET /v1/daemon/profile zwraca MultiRuntimeProfileResponse z aktywnego stanu demona.
2. POST /v1/daemon/profile z polami live — applied=True, brak reload.
3. POST /v1/daemon/profile z cache_implementation — soft_reload, applied=False.
4. POST /v1/daemon/profile z model_id — hard_restart, applied=False.
5. POST /v1/daemon/profile z precision — odrzucenie (unsupported).
6. POST /v1/daemon/profile mieszane: live+unsupported.
7. Stary POST /v1/daemon/config nadal działa (backward compat).
8. 503 gdy daemon niezainicjalizowany.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import services.multi_runtime.main as runtime_main
from services.multi_runtime.engine import ReloadSignal


def _make_params_dict(**kw):
    return {
        "max_new_tokens": 128,
        "enable_thinking": False,
        "image_token_budget": 280,
        "reasoning_summary_enabled": False,
        "emotion_detection_enabled": False,
        "emotion_response_style_enabled": False,
        "cache_implementation": None,
        **kw,
    }


def _make_status_dict(**kw):
    base = {
        "target_model": "google/gemma-4-E2B-it",
        "assistant_model": None,
        "mode": "target_only",
        "target_loaded": True,
        "assistant_loaded": False,
        "params": _make_params_dict(),
        "vram": {
            "backend": "cpu",
            "allocated_mb": 0,
            "reserved_mb": 0,
            "total_mb": 0,
            "free_mb": 0,
        },
        "pending_reload": False,
        "reload_reason": None,
    }
    base.update(kw)
    return base


def _daemon_stub(status_dict=None, update_signal=ReloadSignal.NONE):
    stub = MagicMock()
    stub.status.return_value = status_dict or _make_status_dict()
    stub.update_params.return_value = update_signal
    stub._target_id = "google/gemma-4-E2B-it"  # noqa: SLF001
    stub.is_ready.return_value = True
    return stub


def _client_with(daemon):
    runtime_main._daemon = daemon  # noqa: SLF001
    runtime_main._warming = False
    runtime_main._startup_error = None
    return TestClient(runtime_main.app)


# ---------------------------------------------------------------------------
# GET /v1/daemon/profile
# ---------------------------------------------------------------------------


def test_get_profile_returns_200():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.get("/v1/daemon/profile")
    assert resp.status_code == 200


def test_get_profile_runtime_id():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    assert data["runtime_id"] == "multi_runtime"


def test_get_profile_contains_profile_object():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    assert "profile" in data
    assert data["profile"]["model_id"] == "google/gemma-4-E2B-it"


def test_get_profile_daemon_reachable_true():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    assert data["daemon_reachable"] is True


def test_get_profile_apply_matrix_present():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    matrix = data["apply_matrix"]
    assert matrix["model_id"] == "hard_restart"
    assert matrix["max_new_tokens"] == "live"
    assert matrix["cache_implementation"] == "soft_reload"
    assert matrix["precision"] == "unsupported"


def test_get_profile_supported_options_present():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    opts = data["supported_options"]
    assert "cache_implementation" in opts


def test_get_profile_reflects_active_params():
    params = _make_params_dict(max_new_tokens=512, enable_thinking=True)
    stub = _daemon_stub(
        status_dict=_make_status_dict(
            target_model="google/gemma-4-1B-it",
            params=params,
        )
    )
    client = _client_with(stub)
    data = client.get("/v1/daemon/profile").json()
    profile = data["profile"]
    assert profile["model_id"] == "google/gemma-4-1B-it"
    assert profile["max_new_tokens"] == 512
    assert profile["enable_thinking"] is True


def test_get_profile_503_when_daemon_not_initialized():
    runtime_main._daemon = None  # noqa: SLF001
    client = TestClient(runtime_main.app)
    resp = client.get("/v1/daemon/profile")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /v1/daemon/profile — live fields
# ---------------------------------------------------------------------------


def test_update_profile_live_fields_applied_true():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile",
        json={"max_new_tokens": 256, "enable_thinking": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] is True
    assert data["required_apply_mode"] == "live"
    assert "max_new_tokens" in data["accepted"]
    assert data["rejected"] == []


def test_update_profile_live_fields_calls_update_params():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    client = _client_with(stub)
    client.post(
        "/v1/daemon/profile",
        json={"max_new_tokens": 512, "image_token_budget": 560},
    )
    stub.update_params.assert_called_once_with(
        max_new_tokens=512, image_token_budget=560
    )


def test_update_profile_emotion_flags_live():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile",
        json={
            "emotion_detection_enabled": True,
            "emotion_response_style_enabled": True,
        },
    )
    data = resp.json()
    assert data["applied"] is True
    assert data["required_apply_mode"] == "live"


# ---------------------------------------------------------------------------
# POST /v1/daemon/profile — soft_reload fields
# ---------------------------------------------------------------------------


def test_update_profile_cache_impl_requires_soft_reload():
    stub = _daemon_stub(update_signal=ReloadSignal.SOFT_RELOAD)
    client = _client_with(stub)
    resp = client.post("/v1/daemon/profile", json={"cache_implementation": "static"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["required_apply_mode"] == "soft_reload"
    assert data["applied"] is False
    assert "cache_implementation" in data["accepted"]


def test_update_profile_invalid_cache_impl_rejected():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile", json={"cache_implementation": "nonexistent_strategy"}
    )
    data = resp.json()
    assert len(data["rejected"]) == 1
    assert data["rejected"][0]["field"] == "cache_implementation"
    assert data["rejected"][0]["reason"] == "unsupported_combination"


# ---------------------------------------------------------------------------
# POST /v1/daemon/profile — hard_restart fields
# ---------------------------------------------------------------------------


def test_update_profile_model_id_requires_hard_restart():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/profile", json={"model_id": "google/gemma-4-1B-it"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["required_apply_mode"] == "hard_restart"
    assert data["applied"] is False
    assert "model_id" in data["accepted"]


def test_update_profile_model_id_does_not_call_update_params():
    stub = _daemon_stub()
    client = _client_with(stub)
    client.post("/v1/daemon/profile", json={"model_id": "google/gemma-4-1B-it"})
    stub.update_params.assert_not_called()


def test_update_profile_assistant_model_id_hard_restart():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile", json={"assistant_model_id": "google/gemma-4-1B-it"}
    )
    data = resp.json()
    assert data["required_apply_mode"] == "hard_restart"
    assert data["applied"] is False


# ---------------------------------------------------------------------------
# POST /v1/daemon/profile — unsupported fields
# ---------------------------------------------------------------------------


def test_update_profile_precision_rejected():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/profile", json={"precision": "int4"})
    data = resp.json()
    assert len(data["rejected"]) == 1
    assert data["rejected"][0]["field"] == "precision"
    assert data["rejected"][0]["reason"] == "precision_not_supported_for_runtime"
    assert data["accepted"] == {}


def test_update_profile_quantization_backend_rejected():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile", json={"quantization_backend": "bitsandbytes"}
    )
    data = resp.json()
    assert data["rejected"][0]["reason"] == "quantization_backend_unavailable"


def test_update_profile_device_target_rejected():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/profile", json={"device_target": "cuda"})
    data = resp.json()
    assert data["rejected"][0]["field"] == "device_target"


# ---------------------------------------------------------------------------
# POST /v1/daemon/profile — mixed scenarios
# ---------------------------------------------------------------------------


def test_update_profile_mixed_live_and_unsupported():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    client = _client_with(stub)
    resp = client.post(
        "/v1/daemon/profile",
        json={"max_new_tokens": 512, "precision": "int4"},
    )
    data = resp.json()
    assert "max_new_tokens" in data["accepted"]
    assert len(data["rejected"]) == 1
    assert data["required_apply_mode"] == "live"
    assert data["applied"] is True


def test_update_profile_empty_request():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/profile", json={})
    data = resp.json()
    assert data["accepted"] == {}
    assert data["rejected"] == []
    assert data["applied"] is False


# ---------------------------------------------------------------------------
# Backward compat: POST /v1/daemon/config still works
# ---------------------------------------------------------------------------


def test_legacy_daemon_config_still_works():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={"max_new_tokens": 64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reload_signal"] == "none"


# ---------------------------------------------------------------------------
# 503 when daemon not initialized
# ---------------------------------------------------------------------------


def test_update_profile_503_when_daemon_not_initialized():
    runtime_main._daemon = None  # noqa: SLF001
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/profile", json={"max_new_tokens": 128})
    assert resp.status_code == 503
