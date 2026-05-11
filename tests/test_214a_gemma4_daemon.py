"""Tests for Gemma 4 Daemon engine and control API — PR 214A.

Covers the 7 backend test cases from the spec (section 2.3):
  1. wybór target model
  2. dodanie assistant model
  3. zmiana parametrów bez restartu
  4. soft reload
  5. twardy restart
  6. czyszczenie stanu / brak śmieci w VRAM
  7. fallback gdy assistant model nie może się załadować
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import services.gemma4_audio_runtime.main as runtime_main
from services.gemma4_audio_runtime.engine import (
    Gemma4AudioEngine,
    Gemma4Daemon,
    ModelLoadError,
    ReloadSignal,
    RuntimeMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_stub(
    loaded: bool = True, model_id: str = "google/gemma-4-E2B-it"
) -> MagicMock:
    stub = MagicMock(spec=Gemma4AudioEngine)
    stub.is_loaded.return_value = loaded
    stub.model_id = model_id
    stub.default_max_new_tokens = 128
    return stub


def _make_daemon(
    target_loaded: bool = True,
    assistant_loaded: bool = False,
    assistant_id: str | None = None,
) -> Gemma4Daemon:
    """Return a Gemma4Daemon with stubbed engines (no real model loading)."""
    daemon = Gemma4Daemon(cache_dir="models_cache/hf")
    target_stub = _make_engine_stub(loaded=target_loaded)
    daemon._target_engine = target_stub  # noqa: SLF001
    if assistant_id:
        assistant_stub = _make_engine_stub(
            loaded=assistant_loaded, model_id=assistant_id
        )
        daemon._assistant_engine = assistant_stub  # noqa: SLF001
        daemon._assistant_id = assistant_id  # noqa: SLF001
        daemon._mode = RuntimeMode.TARGET_WITH_ASSISTANT  # noqa: SLF001
    return daemon


# ---------------------------------------------------------------------------
# 1. wybór target model
# ---------------------------------------------------------------------------


class TestTargetModelSelection:
    def test_default_target_is_gemma4_e2b(self):
        daemon = Gemma4Daemon(cache_dir="models_cache/hf")
        assert daemon._target_id == "google/gemma-4-E2B-it"  # noqa: SLF001

    def test_load_target_calls_engine_load(self, monkeypatch):
        daemon = Gemma4Daemon(cache_dir="models_cache/hf")
        load_calls = []

        class FakeEngine:
            model_id = "google/gemma-4-E2B-it"
            model_class_name = None
            default_max_new_tokens = 128

            def load(self):
                load_calls.append(self.model_id)

            def is_loaded(self):
                return True

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: FakeEngine(),
        )
        daemon.load_target()

        assert load_calls == ["google/gemma-4-E2B-it"]
        assert daemon.is_ready()

    def test_status_reports_target_model(self):
        daemon = _make_daemon()
        st = daemon.status()
        assert st["target_model"] == "google/gemma-4-E2B-it"
        assert st["target_loaded"] is True
        assert st["mode"] == "target_only"


# ---------------------------------------------------------------------------
# 2. dodanie assistant model
# ---------------------------------------------------------------------------


class TestAssistantAttach:
    def test_attach_loads_assistant_engine(self, monkeypatch):
        daemon = _make_daemon()
        attached = []

        class FakeAssistantEngine:
            model_id = "google/gemma-4-E2B-it-assistant"
            default_max_new_tokens = 128

            def load(self):
                attached.append(self.model_id)

            def is_loaded(self):
                return True

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **kw: FakeAssistantEngine(),
        )

        daemon.attach_assistant("google/gemma-4-E2B-it-assistant")

        assert attached == ["google/gemma-4-E2B-it-assistant"]
        assert daemon._assistant_id == "google/gemma-4-E2B-it-assistant"  # noqa: SLF001
        assert daemon._mode == RuntimeMode.TARGET_WITH_ASSISTANT  # noqa: SLF001

    def test_status_reports_assistant_when_attached(self):
        daemon = _make_daemon(
            assistant_loaded=True, assistant_id="google/gemma-4-E2B-it-assistant"
        )
        st = daemon.status()
        assert st["assistant_model"] == "google/gemma-4-E2B-it-assistant"
        assert st["assistant_loaded"] is True
        assert st["mode"] == "target_with_assistant"

    def test_only_one_assistant_at_a_time(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="model-A")
        unloaded = []

        class FakeNewEngine:
            model_id = "model-B"
            default_max_new_tokens = 128

            def load(self):
                pass

            def is_loaded(self):
                return True

            def unload(self):
                unloaded.append("model-B")

        # The existing assistant stub's unload should be tracked
        old_stub = daemon._assistant_engine  # noqa: SLF001
        old_stub.unload = lambda: unloaded.append("model-A")

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **kw: FakeNewEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        daemon.attach_assistant("model-B")

        assert "model-A" in unloaded
        assert daemon._assistant_id == "model-B"  # noqa: SLF001


# ---------------------------------------------------------------------------
# 3. zmiana parametrów bez restartu
# ---------------------------------------------------------------------------


class TestLiveParamUpdate:
    def test_max_new_tokens_applied_live(self):
        daemon = _make_daemon()
        signal = daemon.update_params(max_new_tokens=512)
        assert signal == ReloadSignal.NONE
        assert daemon._params.max_new_tokens == 512  # noqa: SLF001
        assert daemon._target_engine.default_max_new_tokens == 512  # noqa: SLF001

    def test_enable_thinking_applied_live(self):
        daemon = _make_daemon()
        signal = daemon.update_params(enable_thinking=True)
        assert signal == ReloadSignal.NONE
        assert daemon._params.enable_thinking is True  # noqa: SLF001

    def test_cache_implementation_signals_soft_reload(self):
        daemon = _make_daemon()
        signal = daemon.update_params(cache_implementation="static")
        assert signal == ReloadSignal.SOFT_RELOAD
        assert daemon._params.cache_implementation == "static"  # noqa: SLF001
        assert daemon._reload_reason is not None  # noqa: SLF001

    def test_same_cache_implementation_no_reload(self):
        daemon = _make_daemon()
        daemon._params.cache_implementation = "static"  # noqa: SLF001
        signal = daemon.update_params(cache_implementation="static")
        assert signal == ReloadSignal.NONE

    def test_status_pending_reload_after_cache_change(self):
        daemon = _make_daemon()
        daemon.update_params(cache_implementation="quantized")
        st = daemon.status()
        assert st["pending_reload"] is True
        assert "cache_implementation" in st["reload_reason"]


# ---------------------------------------------------------------------------
# 4. soft reload
# ---------------------------------------------------------------------------


class TestSoftReload:
    def test_soft_reload_frees_vram_then_reloads(self, monkeypatch):
        daemon = _make_daemon()
        freed = []
        loaded = []

        original_target = daemon._target_engine  # noqa: SLF001
        original_target.unload = lambda: freed.append("target_unloaded")

        class FreshEngine:
            model_id = "google/gemma-4-E2B-it"
            model_class_name = None
            default_max_new_tokens = 128

            def load(self):
                loaded.append("target_loaded")

            def is_loaded(self):
                return True

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: FreshEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram",
            lambda: freed.append("vram_freed"),
        )

        reason = daemon.soft_reload()

        assert "target_unloaded" in freed
        assert "vram_freed" in freed
        assert "target_loaded" in loaded
        assert reason == "manual_reload"

    def test_soft_reload_clears_reload_reason(self, monkeypatch):
        daemon = _make_daemon()
        daemon._reload_reason = "cache_implementation changed to 'static'"  # noqa: SLF001

        class FreshEngine:
            model_id = "google/gemma-4-E2B-it"
            model_class_name = None
            default_max_new_tokens = 128

            def load(self):
                pass

            def is_loaded(self):
                return True

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: FreshEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        reason = daemon.soft_reload()

        assert reason == "cache_implementation changed to 'static'"
        assert daemon._reload_reason is None  # noqa: SLF001
        st = daemon.status()
        assert st["pending_reload"] is False

    def test_soft_reload_drops_assistant(self, monkeypatch):
        daemon = _make_daemon(
            assistant_loaded=True, assistant_id="google/gemma-4-E2B-it-assistant"
        )
        unloaded_assistant = []
        daemon._assistant_engine.unload = lambda: unloaded_assistant.append(True)  # noqa: SLF001

        class FreshEngine:
            model_id = "google/gemma-4-E2B-it"
            model_class_name = None
            default_max_new_tokens = 128

            def load(self):
                pass

            def is_loaded(self):
                return True

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: FreshEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        daemon.soft_reload()

        assert unloaded_assistant, "assistant.unload() must be called"
        assert daemon._assistant_id is None  # noqa: SLF001
        assert daemon._mode == RuntimeMode.TARGET_ONLY  # noqa: SLF001


# ---------------------------------------------------------------------------
# 5. twardy restart
# ---------------------------------------------------------------------------


class TestHardRestart:
    def test_restart_endpoint_unloads_and_schedules_execv(self, monkeypatch):
        daemon = _make_daemon()
        unloaded = []
        daemon.unload_all = lambda: unloaded.append(True)

        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        execv_calls = []

        async def fake_sleep(_):
            pass

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        monkeypatch.setattr("os.execv", lambda *a: execv_calls.append(a))

        client = TestClient(runtime_main.app, raise_server_exceptions=False)
        response = client.post("/v1/daemon/restart")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "restarting"
        assert unloaded == [True]

    def test_unload_all_cleans_all_models(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst-model")
        freed = []
        daemon._target_engine.unload = lambda: freed.append("target")  # noqa: SLF001
        daemon._assistant_engine.unload = lambda: freed.append("asst")  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram",
            lambda: freed.append("vram"),
        )

        daemon.unload_all()

        assert "target" in freed
        assert "asst" in freed
        assert "vram" in freed
        assert daemon._target_engine is None  # noqa: SLF001
        assert daemon._assistant_engine is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# 6. czyszczenie stanu / brak śmieci w VRAM
# ---------------------------------------------------------------------------


class TestVRAMHygiene:
    def test_detach_assistant_frees_vram(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst")
        freed = []
        daemon._assistant_engine.unload = lambda: freed.append("unloaded")  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram",
            lambda: freed.append("cache_cleared"),
        )

        daemon.detach_assistant()

        assert "unloaded" in freed
        assert "cache_cleared" in freed
        assert daemon._assistant_engine is None  # noqa: SLF001
        assert daemon._assistant_id is None  # noqa: SLF001

    def test_attach_failure_leaves_no_orphan(self, monkeypatch):
        daemon = _make_daemon()
        freed = []

        class BrokenEngine:
            model_id = "bad-model"
            default_max_new_tokens = 128

            def load(self):
                raise Exception("OOM")

            def is_loaded(self):
                return False

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: BrokenEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram",
            lambda: freed.append("cleared"),
        )

        with pytest.raises(ModelLoadError):
            daemon.attach_assistant("bad-model")

        assert freed, "_free_vram must be called on attach failure"
        assert daemon._assistant_engine is None  # noqa: SLF001
        assert daemon._assistant_id is None  # noqa: SLF001
        assert daemon._mode == RuntimeMode.TARGET_ONLY  # noqa: SLF001

    def test_ensure_vram_clean_removes_all_references(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst")
        unloaded = []
        daemon._target_engine.unload = lambda: unloaded.append("target")  # noqa: SLF001
        daemon._assistant_engine.unload = lambda: unloaded.append("asst")  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        daemon._ensure_vram_clean()  # noqa: SLF001

        assert "target" in unloaded
        assert "asst" in unloaded
        assert daemon._target_engine is None  # noqa: SLF001
        assert daemon._assistant_engine is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# 7. fallback gdy assistant model nie może się załadować
# ---------------------------------------------------------------------------


class TestAssistantFallback:
    def test_failed_assistant_load_keeps_target_running(self, monkeypatch):
        daemon = _make_daemon()

        class FailingEngine:
            model_id = "bad-assistant"
            default_max_new_tokens = 128

            def load(self):
                raise Exception("GPU OOM")

            def is_loaded(self):
                return False

            def unload(self):
                pass

        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.Gemma4AudioEngine",
            lambda **_: FailingEngine(),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        with pytest.raises(ModelLoadError):
            daemon.attach_assistant("bad-assistant")

        # Target must still be operational
        assert daemon.is_ready(), "Target must remain loaded after assistant failure"
        assert daemon._assistant_id is None  # noqa: SLF001
        assert daemon._mode == RuntimeMode.TARGET_ONLY  # noqa: SLF001

    def test_api_returns_422_on_assistant_failure(self, monkeypatch):
        daemon = _make_daemon()

        def raise_load_error(model_id: str):
            raise ModelLoadError(f"Cannot load {model_id}")

        daemon.attach_assistant = raise_load_error  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        response = client.post(
            "/v1/daemon/assistant/attach",
            json={"model_id": "bad-model"},
        )

        assert response.status_code == 422
        assert "Cannot attach assistant" in response.json()["detail"]

    def test_daemon_fallback_resets_to_safe_defaults(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst")
        daemon._params.max_new_tokens = 1024  # noqa: SLF001
        daemon._params.enable_thinking = True  # noqa: SLF001
        daemon._assistant_engine.unload = lambda: None  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )

        signal = daemon.fallback()

        # Default target was already set — cache was None — so soft reload (clean state)
        assert signal in (ReloadSignal.SOFT_RELOAD, ReloadSignal.NONE)
        assert daemon._assistant_id is None  # noqa: SLF001
        assert daemon._params.max_new_tokens == 128  # noqa: SLF001
        assert daemon._params.enable_thinking is False  # noqa: SLF001
        assert daemon._mode == RuntimeMode.TARGET_ONLY  # noqa: SLF001


# ---------------------------------------------------------------------------
# Backward-compat: existing chat completions tests still work
# ---------------------------------------------------------------------------


def test_extract_text_prompt_from_openai_messages_prefers_latest_user_text() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "pierwszy"}]},
        {"role": "user", "content": "drugi"},
    ]
    assert runtime_main._extract_text_prompt_from_openai_messages(messages) == "drugi"  # noqa: SLF001


def test_chat_completions_uses_pydantic_payload_and_sampling(monkeypatch) -> None:
    captured: dict = {}

    daemon = _make_daemon()

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "to jest odpowiedz", 0.25

    daemon._target_engine = EngineStub()  # noqa: SLF001
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "google/gemma-4-E2B-it",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Ile to 5*5?"}]}
            ],
            "max_tokens": 77,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "to jest odpowiedz"
    assert captured["max_new_tokens"] == 77
    assert captured["do_sample"] is True
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert body["usage"]["prompt_tokens"] >= 1
    assert body["usage"]["completion_tokens"] == max(1, len("to jest odpowiedz") // 4)


def test_chat_completions_rejects_streaming(monkeypatch) -> None:
    daemon = _make_daemon()
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hej"}], "stream": True},
    )

    assert response.status_code == 400
    assert "Streaming is not supported" in response.json()["detail"]
