"""Tests for 214A daemon management endpoints in gemma4_audio_runtime.main."""

from __future__ import annotations

from fastapi.testclient import TestClient

import services.gemma4_audio_runtime.main as runtime_main


class _EngineStub:
    model_id = "google/gemma-4-E2B-it"
    default_max_new_tokens = 64

    def is_loaded(self) -> bool:
        return True

    def unload(self) -> None:
        pass


def _patch_engine(monkeypatch, loaded: bool = True) -> _EngineStub:
    stub = _EngineStub()
    stub.is_loaded = lambda: loaded  # type: ignore[method-assign]
    monkeypatch.setattr(runtime_main, "_engine", stub)
    monkeypatch.setattr(runtime_main, "_warming", False)
    monkeypatch.setattr(runtime_main, "_startup_error", None)
    return stub


def _reset_daemon_state(monkeypatch) -> None:
    monkeypatch.setattr(runtime_main, "_daemon_max_new_tokens", 64)
    monkeypatch.setattr(runtime_main, "_daemon_enable_thinking", False)
    monkeypatch.setattr(runtime_main, "_daemon_cache_implementation", None)
    monkeypatch.setattr(runtime_main, "_pending_reload", False)
    monkeypatch.setattr(runtime_main, "_reload_reason", None)
    monkeypatch.setattr(runtime_main, "_assistant_model_id", None)
    monkeypatch.setattr(runtime_main, "_assistant_engine", None)


# ── GET /v1/daemon/status ────────────────────────────────────────────────────


def test_daemon_status_returns_target_model(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.get("/v1/daemon/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_model"] == "google/gemma-4-E2B-it"
    assert data["target_loaded"] is True
    assert data["mode"] == "target_only"


def test_daemon_status_returns_params(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    data = client.get("/v1/daemon/status").json()
    assert data["params"]["max_new_tokens"] == 64
    assert data["params"]["enable_thinking"] is False
    assert data["params"]["cache_implementation"] is None


def test_daemon_status_includes_vram_field(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    data = client.get("/v1/daemon/status").json()
    assert "vram" in data
    assert data["vram"]["backend"] in ("cpu", "cuda")


def test_daemon_status_no_engine_shows_not_loaded(monkeypatch) -> None:
    monkeypatch.setattr(runtime_main, "_engine", None)
    monkeypatch.setattr(runtime_main, "_warming", False)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    data = client.get("/v1/daemon/status").json()
    assert data["target_loaded"] is False


def test_daemon_status_pending_reload_flag(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(runtime_main, "_pending_reload", True)
    monkeypatch.setattr(runtime_main, "_reload_reason", "cache_implementation changed")
    client = TestClient(runtime_main.app)
    data = client.get("/v1/daemon/status").json()
    assert data["pending_reload"] is True
    assert data["reload_reason"] == "cache_implementation changed"


def test_daemon_status_assistant_mode(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(
        runtime_main, "_assistant_model_id", "google/gemma-4-E2B-it-assistant"
    )
    assistant_stub = _EngineStub()
    assistant_stub.model_id = "google/gemma-4-E2B-it-assistant"
    monkeypatch.setattr(runtime_main, "_assistant_engine", assistant_stub)
    client = TestClient(runtime_main.app)
    data = client.get("/v1/daemon/status").json()
    assert data["mode"] == "target_with_assistant"
    assert data["assistant_model"] == "google/gemma-4-E2B-it-assistant"
    assert data["assistant_loaded"] is True


# ── POST /v1/daemon/config ───────────────────────────────────────────────────


def test_daemon_config_updates_max_new_tokens(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={"max_new_tokens": 256})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"]["max_new_tokens"] == 256
    assert data["reload_signal"] == "none"


def test_daemon_config_enable_thinking(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={"enable_thinking": True})
    assert resp.status_code == 200
    assert resp.json()["applied"]["enable_thinking"] is True


def test_daemon_config_cache_change_triggers_soft_reload(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={"cache_implementation": "static"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reload_signal"] == "soft_reload"
    assert data["applied"]["cache_implementation"] == "static"
    assert runtime_main._pending_reload is True  # noqa: SLF001


def test_daemon_config_same_cache_no_reload(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(runtime_main, "_daemon_cache_implementation", "static")
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={"cache_implementation": "static"})
    assert resp.json()["reload_signal"] == "none"


def test_daemon_config_null_cache_clears_implementation(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(runtime_main, "_daemon_cache_implementation", "static")
    monkeypatch.setattr(runtime_main, "_pending_reload", True)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={"cache_implementation": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"]["cache_implementation"] is None
    assert runtime_main._pending_reload is False  # noqa: SLF001


def test_daemon_config_empty_body_is_no_op(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/config", json={})
    assert resp.status_code == 200
    assert resp.json()["reload_signal"] == "none"


# ── POST /v1/daemon/reload ───────────────────────────────────────────────────


def test_daemon_reload_returns_204(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)

    async def _noop_init(*_a, **_kw) -> None:
        pass

    monkeypatch.setattr(runtime_main, "initialize_engine", _noop_init)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/reload")
    assert resp.status_code == 204


def test_daemon_reload_clears_pending_flag(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(runtime_main, "_pending_reload", True)
    monkeypatch.setattr(runtime_main, "_reload_reason", "cache_implementation changed")

    async def _noop_init(*_a, **_kw) -> None:
        pass

    monkeypatch.setattr(runtime_main, "initialize_engine", _noop_init)
    client = TestClient(runtime_main.app)
    client.post("/v1/daemon/reload")
    assert runtime_main._pending_reload is False  # noqa: SLF001
    assert runtime_main._reload_reason is None  # noqa: SLF001


# ── POST /v1/daemon/fallback ─────────────────────────────────────────────────


def test_daemon_fallback_detaches_assistant(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(
        runtime_main, "_assistant_model_id", "google/gemma-4-E2B-it-drafter"
    )
    monkeypatch.setattr(runtime_main, "_assistant_engine", _EngineStub())
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/fallback")
    assert resp.status_code == 200
    assert resp.json()["reload_signal"] == "none"
    assert runtime_main._assistant_model_id is None  # noqa: SLF001
    assert runtime_main._assistant_engine is None  # noqa: SLF001


def test_daemon_fallback_no_assistant_is_noop(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/fallback")
    assert resp.status_code == 200


# ── POST /v1/daemon/assistant/detach ─────────────────────────────────────────


def test_daemon_detach_returns_204(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    monkeypatch.setattr(runtime_main, "_assistant_model_id", "drafter")
    monkeypatch.setattr(runtime_main, "_assistant_engine", _EngineStub())
    client = TestClient(runtime_main.app)
    resp = client.post("/v1/daemon/assistant/detach")
    assert resp.status_code == 204
    assert runtime_main._assistant_model_id is None  # noqa: SLF001


# ── CORS headers ─────────────────────────────────────────────────────────────


def test_daemon_status_cors_header(monkeypatch) -> None:
    _patch_engine(monkeypatch)
    _reset_daemon_state(monkeypatch)
    client = TestClient(runtime_main.app)
    resp = client.get("/v1/daemon/status", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
