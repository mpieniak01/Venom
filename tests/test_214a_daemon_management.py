"""Tests for 214A daemon management endpoints in gemma4_audio_runtime.main."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import services.multi_runtime.main as runtime_main
from services.multi_runtime.engine import ReloadSignal


def _make_vram_dict(**kw):
    return {
        "backend": "cpu",
        "allocated_mb": 0,
        "reserved_mb": 0,
        "total_mb": 0,
        "free_mb": 0,
        **kw,
    }


def _make_params_dict(**kw):
    return {
        "max_new_tokens": 64,
        "enable_thinking": False,
        "reasoning_summary_enabled": False,
        "emotion_detection_enabled": False,
        "emotion_response_style_enabled": False,
        "cache_implementation": None,
        "device_target": "auto",
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
        "active_runtime_config": _make_params_dict(),
        "staged_runtime_config": _make_params_dict(),
        "quantization_effective": False,
        "quantization_effective_reason": "no_quantization_requested",
        "vram": _make_vram_dict(),
        "pending_reload": False,
        "reload_reason": None,
    }
    base.update(kw)
    return base


def _daemon_stub(status_dict=None, update_signal=ReloadSignal.NONE):
    """Build a MagicMock that looks like MultiRuntimeDaemon."""
    stub = MagicMock()
    stub.status.return_value = status_dict or _make_status_dict()
    stub.update_params.return_value = update_signal
    stub._target_id = "google/gemma-4-E2B-it"  # noqa: SLF001
    stub.is_ready.return_value = True
    stub.soft_reload.return_value = "manual_reload"
    stub.fallback.return_value = ReloadSignal.NONE
    return stub


def _client_with(daemon):
    runtime_main._daemon = daemon  # noqa: SLF001
    runtime_main._warming = False
    runtime_main._startup_error = None
    return TestClient(runtime_main.app)


# ── GET /v1/daemon/status ────────────────────────────────────────────────────


def test_daemon_status_returns_target_model():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.get("/v1/daemon/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_model"] == "google/gemma-4-E2B-it"
    assert data["target_loaded"] is True
    assert data["mode"] == "target_only"


def test_daemon_status_returns_params():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert data["params"]["max_new_tokens"] == 64
    assert data["params"]["enable_thinking"] is False
    assert data["params"]["reasoning_summary_enabled"] is False
    assert data["params"]["emotion_detection_enabled"] is False
    assert data["params"]["emotion_response_style_enabled"] is False
    assert data["params"]["cache_implementation"] is None
    assert data["params"]["device_target"] == "auto"


def test_daemon_status_includes_vram_field():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert "vram" in data
    assert data["vram"]["backend"] in ("cpu", "cuda")


def test_daemon_status_includes_component_snapshot_metadata():
    stub = _daemon_stub()
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert isinstance(data.get("component_snapshot_version"), str)
    assert data["component_snapshot_version"]
    assert isinstance(data.get("component_snapshot_timestamp_ms"), int)
    assert data["component_snapshot_timestamp_ms"] > 0


def test_daemon_status_no_daemon_returns_503():
    runtime_main._daemon = None  # noqa: SLF001
    runtime_main._warming = False
    client = TestClient(runtime_main.app, raise_server_exceptions=False)
    resp = client.get("/v1/daemon/status")
    assert resp.status_code == 503


def test_daemon_status_pending_reload_flag():
    stub = _daemon_stub(
        status_dict=_make_status_dict(
            pending_reload=True, reload_reason="cache_implementation changed"
        )
    )
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert data["pending_reload"] is True
    assert data["reload_reason"] == "cache_implementation changed"


def test_daemon_status_includes_active_and_staged_runtime_config():
    stub = _daemon_stub(
        status_dict=_make_status_dict(
            active_runtime_config=_make_params_dict(
                precision="float16",
                quantization_backend=None,
                device_target="cuda",
            ),
            staged_runtime_config=_make_params_dict(
                precision="int4",
                quantization_backend="bitsandbytes",
                device_target="cuda",
            ),
            quantization_effective=False,
            quantization_effective_reason="requested_int_quantization_not_active",
        )
    )
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert data["active_runtime_config"]["precision"] == "float16"
    assert data["staged_runtime_config"]["precision"] == "int4"
    assert data["quantization_effective"] is False
    assert (
        data["quantization_effective_reason"] == "requested_int_quantization_not_active"
    )


def test_daemon_status_assistant_mode():
    stub = _daemon_stub(
        status_dict=_make_status_dict(
            assistant_model="google/gemma-4-E2B-it-assistant",
            mode="target_with_assistant",
            assistant_loaded=True,
        )
    )
    client = _client_with(stub)
    data = client.get("/v1/daemon/status").json()
    assert data["mode"] == "target_with_assistant"
    assert data["assistant_model"] == "google/gemma-4-E2B-it-assistant"
    assert data["assistant_loaded"] is True


# ── POST /v1/daemon/config ───────────────────────────────────────────────────


def test_daemon_config_updates_max_new_tokens():
    stub = _daemon_stub()
    stub.status.return_value = _make_status_dict(
        params=_make_params_dict(max_new_tokens=256)
    )
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={"max_new_tokens": 256})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"]["max_new_tokens"] == 256
    assert data["reload_signal"] == "none"


def test_daemon_config_enable_thinking():
    stub = _daemon_stub()
    stub.status.return_value = _make_status_dict(
        params=_make_params_dict(enable_thinking=True)
    )
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={"enable_thinking": True})
    assert resp.status_code == 200
    assert resp.json()["applied"]["enable_thinking"] is True


def test_daemon_config_cache_change_triggers_soft_reload():
    stub = _daemon_stub(update_signal=ReloadSignal.SOFT_RELOAD)
    stub.status.return_value = _make_status_dict(
        params=_make_params_dict(cache_implementation="static"),
        pending_reload=True,
        reload_reason="cache_implementation changed to 'static'",
    )
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={"cache_implementation": "static"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reload_signal"] == "soft_reload"
    assert data["applied"]["cache_implementation"] == "static"
    # /v1/daemon/config forwards only explicitly provided fields.
    stub.update_params.assert_called_once_with(cache_implementation="static")


def test_daemon_config_same_cache_no_reload():
    stub = _daemon_stub(update_signal=ReloadSignal.NONE)
    stub.status.return_value = _make_status_dict(
        params=_make_params_dict(cache_implementation="static")
    )
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={"cache_implementation": "static"})
    assert resp.json()["reload_signal"] == "none"


def test_daemon_config_empty_body_is_no_op():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/config", json={})
    assert resp.status_code == 200
    assert resp.json()["reload_signal"] == "none"


# ── POST /v1/daemon/reload ───────────────────────────────────────────────────


def test_daemon_reload_returns_200():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/reload")
    assert resp.status_code == 200


def test_daemon_reload_calls_soft_reload():
    stub = _daemon_stub()
    client = _client_with(stub)
    client.post("/v1/daemon/reload")
    stub.soft_reload.assert_called_once()


# ── POST /v1/daemon/restart ──────────────────────────────────────────────────


def test_daemon_restart_returns_200():
    stub = _daemon_stub()
    client = _client_with(stub)
    # Patch os.execv so the process doesn't actually replace itself in CI.
    with patch("services.multi_runtime.main.os.execv"):
        resp = client.post("/v1/daemon/restart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "restarting"


# ── POST /v1/daemon/fallback ─────────────────────────────────────────────────


def test_daemon_fallback_returns_reload_signal():
    stub = _daemon_stub()
    stub.fallback.return_value = ReloadSignal.NONE
    stub._target_id = "google/gemma-4-E2B-it"  # noqa: SLF001
    client = _client_with(stub)
    resp = client.post("/v1/daemon/fallback")
    assert resp.status_code == 200
    assert resp.json()["reload_signal"] == "none"


def test_daemon_fallback_calls_fallback():
    stub = _daemon_stub()
    client = _client_with(stub)
    client.post("/v1/daemon/fallback")
    stub.fallback.assert_called_once()


# ── POST /v1/daemon/assistant/attach ─────────────────────────────────────────


def test_daemon_assistant_attach_returns_200():
    stub = _daemon_stub()
    stub.status.return_value = _make_status_dict(
        assistant_model="google/gemma-4-E2B-it-drafter",
        mode="target_with_assistant",
        assistant_loaded=True,
    )
    client = _client_with(stub)
    with patch("services.multi_runtime.main.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = None
        resp = client.post(
            "/v1/daemon/assistant/attach",
            json={"model_id": "google/gemma-4-E2B-it-drafter"},
        )
    assert resp.status_code == 200
    assert resp.json()["assistant_model"] == "google/gemma-4-E2B-it-drafter"


# ── POST /v1/daemon/assistant/detach ─────────────────────────────────────────


def test_daemon_detach_calls_detach_assistant():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.post("/v1/daemon/assistant/detach")
    assert resp.status_code == 200
    stub.detach_assistant.assert_called_once()


# ── CORS headers ─────────────────────────────────────────────────────────────


def test_daemon_status_cors_header():
    stub = _daemon_stub()
    client = _client_with(stub)
    resp = client.get("/v1/daemon/status", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
