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

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

import services.gemma4_audio_runtime.main as runtime_main
from services.gemma4_audio_runtime.engine import (
    Gemma4AudioEngine,
    Gemma4Daemon,
    InferenceError,
    ModelLoadError,
    ReloadSignal,
    RuntimeMode,
    _free_vram,
    _get_vram_info,
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


# ---------------------------------------------------------------------------
# Gemma4AudioEngine — unit coverage
# ---------------------------------------------------------------------------


class TestAudioEngineUnit:
    def test_clean_generated_text_removes_special_tokens(self):
        result = Gemma4AudioEngine._clean_generated_text(
            "<bos>hello<turn|> world<|turn>"
        )
        assert result == "hello world"

    def test_clean_generated_text_collapses_whitespace(self):
        result = Gemma4AudioEngine._clean_generated_text("  foo   bar  ")
        assert result == "foo bar"

    def test_build_prompt_math_task(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        prompt = engine._build_prompt_for_task("math-5x5", None, "default")
        assert "5 razy 5" in prompt

    def test_build_prompt_transcribe_task(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        prompt = engine._build_prompt_for_task("transcribe", None, "default")
        assert "Transcribe" in prompt

    def test_build_prompt_with_question(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        prompt = engine._build_prompt_for_task(None, "Jak masz na imię?", "default")
        assert "Jak masz na imię?" in prompt

    def test_build_prompt_default(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        assert engine._build_prompt_for_task(None, None, "fallback") == "fallback"

    def test_build_prompt_blank_question_falls_through_to_default(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        assert engine._build_prompt_for_task(None, "   ", "default") == "default"

    def test_unload_clears_model_and_processor(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        engine.model = MagicMock()
        engine.processor = MagicMock()
        engine.unload()
        assert engine.model is None
        assert engine.processor is None

    def test_is_loaded_false_when_both_none(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        assert engine.is_loaded() is False

    def test_is_loaded_false_when_model_only(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        engine.model = MagicMock()
        assert engine.is_loaded() is False

    def test_is_loaded_true_when_both_set(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        engine.model = MagicMock()
        engine.processor = MagicMock()
        assert engine.is_loaded() is True

    def test_respond_raises_when_not_loaded(self):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        with pytest.raises(InferenceError, match="not loaded"):
            engine.respond(np.zeros(16000, dtype=np.float32), 16000)

    def test_respond_raises_on_normalize_failure(self, monkeypatch):
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        engine.model = MagicMock()
        engine.processor = MagicMock()
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.normalize_audio",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("bad audio")),
        )
        with pytest.raises(InferenceError, match="normalize"):
            engine.respond(np.zeros(16000, dtype=np.float32), 16000)

    def _setup_respond(self, monkeypatch):
        """Shared setup: engine with mocked normalize_audio and get_audio_duration."""
        engine = Gemma4AudioEngine(model_id="m", cache_dir="/tmp")
        engine.model = MagicMock()
        engine.processor = MagicMock()
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.normalize_audio",
            lambda arr, sr, **kw: (arr, sr),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine.get_audio_duration",
            lambda arr, sr: 1.0,
        )
        # apply_chat_template returns a dict so **inputs works in generate()
        engine.processor.apply_chat_template.return_value = {}
        engine.model.generate.return_value = [[1, 2, 3]]
        engine.processor.decode.return_value = "<bos>hej<|turn>"
        return engine

    def test_respond_success_basic(self, monkeypatch):
        engine = self._setup_respond(monkeypatch)
        audio = np.zeros(16000, dtype=np.float32)
        text, dur = engine.respond(audio, 16000)
        assert text == "hej"
        assert dur == 1.0

    def test_respond_with_system_prompt(self, monkeypatch):
        engine = self._setup_respond(monkeypatch)
        audio = np.zeros(16000, dtype=np.float32)

        captured_messages: list = []

        def capture(msgs, **kw):
            captured_messages.extend(msgs)
            return {}

        engine.processor.apply_chat_template.side_effect = capture
        engine.processor.decode.return_value = "ok"

        engine.respond(audio, 16000, system_prompt="Be concise.")
        roles = [m["role"] for m in captured_messages]
        assert "system" in roles

    def test_respond_enable_thinking_typeerror_fallback(self, monkeypatch):
        engine = self._setup_respond(monkeypatch)
        audio = np.zeros(16000, dtype=np.float32)

        call_count = [0]

        def _apply_template(msgs, **kw):
            call_count[0] += 1
            if "enable_thinking" in kw:
                raise TypeError("unexpected kwarg enable_thinking")
            return {}

        engine.processor.apply_chat_template.side_effect = _apply_template
        engine.processor.decode.return_value = "result"

        text, _ = engine.respond(audio, 16000, enable_thinking=True)
        assert text == "result"
        assert call_count[0] == 2

    def test_respond_cache_implementation_typeerror_fallback(self, monkeypatch):
        engine = self._setup_respond(monkeypatch)
        audio = np.zeros(16000, dtype=np.float32)

        generate_calls: list[dict] = []

        def _generate(**kw):
            generate_calls.append(dict(kw))
            if "cache_implementation" in kw:
                raise TypeError("unsupported cache_implementation")
            return [[1]]

        engine.model.generate.side_effect = _generate
        engine.processor.decode.return_value = "ok"

        text, _ = engine.respond(audio, 16000, cache_implementation="static")
        assert text == "ok"
        assert len(generate_calls) == 2
        assert "cache_implementation" not in generate_calls[1]

    def test_transcribe_delegates_to_respond(self, monkeypatch):
        engine = self._setup_respond(monkeypatch)
        engine.processor.decode.return_value = "hello"
        audio = np.zeros(16000, dtype=np.float32)
        result = engine.transcribe(audio, 16000)
        assert result == "hello"

    def test_load_success_mocked_transformers(self, monkeypatch):
        fake_transformers = MagicMock()
        fake_processor = MagicMock()
        fake_model = MagicMock()

        fake_transformers.AutoProcessor.from_pretrained.return_value = fake_processor

        fake_cls = MagicMock()
        fake_cls.from_pretrained.return_value = fake_model
        fake_transformers.AutoModelForMultimodalLM = fake_cls

        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        engine = Gemma4AudioEngine(model_id="model/x", cache_dir="/tmp")
        engine.load()

        assert engine.processor is fake_processor
        assert engine.model is fake_model
        assert engine.model_class_name == "AutoModelForMultimodalLM"

    def test_load_falls_back_to_causallm(self, monkeypatch):
        fake_transformers = MagicMock()
        fake_processor = MagicMock()
        fake_model = MagicMock()

        fake_transformers.AutoProcessor.from_pretrained.return_value = fake_processor
        fake_transformers.AutoModelForMultimodalLM = None
        fake_transformers.AutoModelForImageTextToText = None

        fake_causallm = MagicMock()
        fake_causallm.from_pretrained.return_value = fake_model
        fake_transformers.AutoModelForCausalLM = fake_causallm

        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        engine = Gemma4AudioEngine(model_id="model/x", cache_dir="/tmp")
        engine.load()

        assert engine.model is fake_model
        assert engine.model_class_name == "AutoModelForCausalLM"

    def test_load_raises_model_load_error_when_processor_fails(self, monkeypatch):
        fake_transformers = MagicMock()
        fake_transformers.AutoProcessor.from_pretrained.side_effect = OSError("no file")
        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        engine = Gemma4AudioEngine(model_id="model/x", cache_dir="/tmp")
        with pytest.raises(ModelLoadError, match="processor"):
            engine.load()

    def test_load_raises_when_all_model_classes_fail(self, monkeypatch):
        fake_transformers = MagicMock()
        fake_processor = MagicMock()
        fake_transformers.AutoProcessor.from_pretrained.return_value = fake_processor

        failing_cls = MagicMock()
        failing_cls.from_pretrained.side_effect = RuntimeError("nope")
        fake_transformers.AutoModelForMultimodalLM = failing_cls
        fake_transformers.AutoModelForImageTextToText = failing_cls
        fake_transformers.AutoModelForCausalLM = failing_cls

        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

        engine = Gemma4AudioEngine(model_id="model/x", cache_dir="/tmp")
        with pytest.raises(ModelLoadError, match="any candidate class"):
            engine.load()


class TestVRAMHelpers:
    def test_free_vram_no_torch(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "torch", None)
        _free_vram()  # must not raise

    def test_get_vram_info_returns_cpu_when_no_torch(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "torch", None)
        info = _get_vram_info()
        assert info.backend == "cpu"

    def test_get_vram_info_cuda_path(self, monkeypatch):
        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = True
        fake_torch.cuda.memory_allocated.return_value = 512 * 1024**2
        fake_torch.cuda.memory_reserved.return_value = 768 * 1024**2
        props = MagicMock()
        props.total_memory = 8192 * 1024**2
        fake_torch.cuda.get_device_properties.return_value = props

        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        info = _get_vram_info()

        assert info.backend == "cuda"
        assert info.allocated_mb == 512.0
        assert info.total_mb == 8192.0

    def test_get_vram_info_returns_cpu_when_cuda_not_available(self, monkeypatch):
        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = False
        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        info = _get_vram_info()
        assert info.backend == "cpu"


class TestDaemonExtended:
    def test_constructor_with_model_id(self):
        daemon = Gemma4Daemon(cache_dir="/tmp", model_id="custom/model")
        assert daemon._target_id == "custom/model"  # noqa: SLF001

    def test_constructor_with_max_new_tokens(self):
        daemon = Gemma4Daemon(cache_dir="/tmp", max_new_tokens=512)
        assert daemon._params.max_new_tokens == 512  # noqa: SLF001

    def test_constructor_defaults(self):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        assert daemon._target_id == Gemma4Daemon.DEFAULT_TARGET  # noqa: SLF001
        assert daemon._params.max_new_tokens == 128  # noqa: SLF001

    def test_active_engine_raises_when_not_ready(self):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        with pytest.raises(RuntimeError, match="not loaded"):
            daemon.active_engine()

    def test_fallback_hard_restart_on_non_default_target(self, monkeypatch):
        daemon = _make_daemon()
        daemon._target_id = "custom/model"  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )
        daemon._target_engine.unload = lambda: None  # noqa: SLF001

        signal = daemon.fallback()

        assert signal == ReloadSignal.HARD_RESTART
        assert daemon._target_id == Gemma4Daemon.DEFAULT_TARGET  # noqa: SLF001
        assert "fallback" in daemon._reload_reason  # noqa: SLF001

    def test_fallback_soft_reload_when_cache_was_set(self, monkeypatch):
        daemon = _make_daemon()
        daemon._params.cache_implementation = "static"  # noqa: SLF001
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.engine._free_vram", lambda: None
        )
        daemon._target_engine.unload = lambda: None  # noqa: SLF001

        signal = daemon.fallback()

        assert signal == ReloadSignal.SOFT_RELOAD
        assert daemon._params.cache_implementation is None  # noqa: SLF001

    def test_update_params_propagates_to_assistant_engine(self):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst")
        daemon.update_params(max_new_tokens=256)
        assert daemon._assistant_engine.default_max_new_tokens == 256  # noqa: SLF001

    def test_status_reports_raw_thinking_from_engine_state(self):
        daemon = _make_daemon()
        daemon._target_engine.last_raw_thinking_available = True  # noqa: SLF001
        st = daemon.status()
        assert st["raw_thinking_available"] is True
        assert st["reasoning_summary_status"] == "raw_available"

    def test_is_ready_false_when_no_target_engine(self):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        assert daemon.is_ready() is False


# ---------------------------------------------------------------------------
# main.py — API endpoint coverage
# ---------------------------------------------------------------------------


def _ready_daemon() -> Gemma4Daemon:
    """Return daemon with a loaded target engine stub."""

    class _ReadyEngine:
        model_id = "google/gemma-4-E2B-it"
        default_max_new_tokens = 128

        def is_loaded(self):
            return True

        def respond(self, audio, **kw):
            return "ok", 1.0

        def unload(self):
            pass

    daemon = Gemma4Daemon(cache_dir="/tmp")
    daemon._target_engine = _ReadyEngine()  # noqa: SLF001
    return daemon


class TestMainHealthStatus:
    def test_health_ok(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_warming(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", True)
        client = TestClient(runtime_main.app)
        r = client.get("/health")
        assert r.json()["status"] == "warming"

    def test_health_model_not_loaded(self, monkeypatch):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/health")
        assert r.json()["status"] == "error"

    def test_health_no_daemon_startup_error(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        monkeypatch.setattr(runtime_main, "_warming", False)
        monkeypatch.setattr(runtime_main, "_startup_error", "boom")
        client = TestClient(runtime_main.app)
        r = client.get("/health")
        assert r.json()["status"] == "error"
        assert "boom" in r.json()["message"]

    def test_health_no_daemon_warming(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        monkeypatch.setattr(runtime_main, "_warming", True)
        monkeypatch.setattr(runtime_main, "_startup_error", None)
        client = TestClient(runtime_main.app)
        r = client.get("/health")
        assert r.json()["status"] == "warming"

    def test_v1_health_delegates(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_status_running(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/status")
        body = r.json()
        assert body["status"] == "running"
        assert body["model_loaded"] is True

    def test_status_warming(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", True)
        client = TestClient(runtime_main.app)
        r = client.get("/status")
        assert r.json()["status"] == "warming"

    def test_status_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/status")
        assert r.json()["status"] == "error"
        assert r.json()["model_loaded"] is False

    def test_root_returns_service_name(self, monkeypatch):
        client = TestClient(runtime_main.app)
        r = client.get("/")
        assert r.status_code == 200
        assert "Gemma 4" in r.json()["service"]


class TestMainListModels:
    def test_list_models_target_only(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        client = TestClient(runtime_main.app)
        r = client.get("/v1/models")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["role"] == "target"

    def test_list_models_with_assistant(self, monkeypatch):
        daemon = _make_daemon(assistant_loaded=True, assistant_id="asst/model")
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.get("/v1/models")
        data = r.json()["data"]
        roles = [m["role"] for m in data]
        assert "assistant" in roles

    def test_list_models_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.get("/v1/models")
        assert r.status_code == 503


class TestMainDaemonControlEndpoints:
    def test_daemon_status_success(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        client = TestClient(runtime_main.app)
        r = client.get("/v1/daemon/status")
        assert r.status_code == 200
        body = r.json()
        assert body["target_loaded"] is True
        assert "params" in body
        assert "vram" in body

    def test_daemon_status_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.get("/v1/daemon/status")
        assert r.status_code == 503

    def test_daemon_config_none_signal(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/config", json={"max_new_tokens": 64})
        assert r.status_code == 200
        assert r.json()["reload_signal"] == "none"

    def test_daemon_config_soft_reload_signal(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/config", json={"cache_implementation": "static"})
        assert r.status_code == 200
        assert r.json()["reload_signal"] == "soft_reload"

    def test_daemon_config_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/config", json={"max_new_tokens": 64})
        assert r.status_code == 503

    def test_daemon_reload_409_during_warmup(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr(runtime_main, "_warming", True)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/reload")
        assert r.status_code == 409
        assert "warm" in r.json()["detail"].lower()

    def test_daemon_reload_503_not_ready(self, monkeypatch):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/reload")
        assert r.status_code == 503

    def test_daemon_reload_success(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_warming", False)

        reload_called = []

        daemon = _ready_daemon()
        daemon.soft_reload = lambda: reload_called.append(True) or "test_reason"  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/reload")
        assert r.status_code == 200
        assert reload_called

    def test_daemon_restart_success(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", _ready_daemon())
        monkeypatch.setattr("asyncio.sleep", lambda _: None)
        monkeypatch.setattr("os.execv", lambda *a: None)

        client = TestClient(runtime_main.app, raise_server_exceptions=False)
        r = client.post("/v1/daemon/restart")
        assert r.status_code == 200
        assert r.json()["status"] == "restarting"

    def test_daemon_assistant_attach_success(self, monkeypatch):
        daemon = _ready_daemon()
        attach_calls: list[str] = []
        daemon.attach_assistant = lambda model_id: attach_calls.append(model_id)  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/assistant/attach", json={"model_id": "asst/model"})
        assert r.status_code == 200
        assert attach_calls == ["asst/model"]

    def test_daemon_assistant_attach_target_not_ready(self, monkeypatch):
        daemon = Gemma4Daemon(cache_dir="/tmp")
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/assistant/attach", json={"model_id": "asst/model"})
        assert r.status_code == 503

    def test_daemon_assistant_detach_success(self, monkeypatch):
        detach_calls: list = []
        daemon = _ready_daemon()
        daemon.detach_assistant = lambda: detach_calls.append(True)  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/assistant/detach")
        assert r.status_code == 200
        assert detach_calls

    def test_daemon_fallback_soft_reload(self, monkeypatch):
        daemon = _ready_daemon()
        daemon.fallback = lambda: ReloadSignal.SOFT_RELOAD  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/fallback")
        assert r.status_code == 200
        assert r.json()["reload_signal"] == "soft_reload"

    def test_daemon_fallback_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/fallback")
        assert r.status_code == 503

    def test_warmup_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.post("/warmup")
        assert r.status_code == 503

    def test_warmup_success(self, monkeypatch):
        daemon = _ready_daemon()
        daemon._target_engine.respond = lambda *a, **kw: ("hello", 0.5)  # type: ignore[union-attr]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.post("/warmup")
        assert r.status_code == 200
        assert r.json()["status"] == "warmed"

    def test_get_engine_returns_active_engine(self, monkeypatch):
        daemon = _ready_daemon()
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        engine = runtime_main.get_engine()
        assert engine is daemon._target_engine  # noqa: SLF001

    def test_status_includes_model_info_when_loaded(self, monkeypatch):
        daemon = _ready_daemon()
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        monkeypatch.setattr(runtime_main, "_warming", False)
        client = TestClient(runtime_main.app)
        r = client.get("/status")
        body = r.json()
        assert body["model_info"] is not None
        assert "model_id" in body["model_info"]

    def test_daemon_reload_returns_target_model(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_warming", False)
        daemon = _ready_daemon()
        daemon.soft_reload = lambda: "test_reason"  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/reload")
        assert r.status_code == 200
        assert "target_model" in r.json()

    def test_daemon_fallback_hard_restart_signal(self, monkeypatch):
        daemon = _ready_daemon()
        daemon.fallback = lambda: ReloadSignal.HARD_RESTART  # type: ignore[method-assign]
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.post("/v1/daemon/fallback")
        assert r.status_code == 200
        assert r.json()["reload_signal"] == "hard_restart"


class TestMainRespondEndpoint:
    def _make_respond_daemon(self, respond_fn=None):
        class _Engine:
            model_id = "google/gemma-4-E2B-it"
            default_max_new_tokens = 128

            def is_loaded(self):
                return True

            def respond(self, audio, **kw):
                if respond_fn:
                    return respond_fn(audio, **kw)
                return "generated text", 1.0

            def unload(self):
                pass

        daemon = Gemma4Daemon(cache_dir="/tmp")
        daemon._target_engine = _Engine()  # noqa: SLF001
        return daemon

    def test_respond_text_only_no_audio(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", self._make_respond_daemon())
        client = TestClient(runtime_main.app)
        r = client.post(
            "/v1/respond",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "What do you hear?"}],
                    }
                ]
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["text"] == "generated text"

    def test_respond_returns_400_when_no_content(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", self._make_respond_daemon())
        client = TestClient(runtime_main.app)
        r = client.post(
            "/v1/respond",
            json={"messages": [{"role": "user", "content": []}]},
        )
        assert r.status_code == 400

    def test_respond_503_when_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.post(
            "/v1/respond",
            json={
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "hello"}]}
                ]
            },
        )
        assert r.status_code == 503

    def test_respond_inference_error_returns_500(self, monkeypatch):
        def _failing_respond(audio, **kw):
            raise InferenceError("GPU exploded")

        daemon = self._make_respond_daemon(respond_fn=_failing_respond)
        monkeypatch.setattr(runtime_main, "_daemon", daemon)
        client = TestClient(runtime_main.app)
        r = client.post(
            "/v1/respond",
            json={
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "boom"}]}
                ]
            },
        )
        assert r.status_code == 500

    def test_transcribe_endpoint_no_daemon(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", None)
        client = TestClient(runtime_main.app)
        r = client.post(
            "/audio/transcribe",
            files={"audio": ("test.wav", b"fake", "audio/wav")},
        )
        assert r.status_code == 503

    def test_transcribe_endpoint_bad_audio(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", self._make_respond_daemon())
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.main.audio_from_bytes",
            lambda b: (_ for _ in ()).throw(ValueError("bad")),
        )
        client = TestClient(runtime_main.app)
        r = client.post(
            "/audio/transcribe",
            files={"audio": ("test.wav", b"fake", "audio/wav")},
        )
        assert r.status_code == 400

    def test_transcribe_endpoint_success(self, monkeypatch):
        monkeypatch.setattr(runtime_main, "_daemon", self._make_respond_daemon())
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.main.audio_from_bytes",
            lambda b: (np.zeros(16000, dtype=np.float32), 16000),
        )
        monkeypatch.setattr(
            "services.gemma4_audio_runtime.main.get_audio_duration",
            lambda arr, sr: 1.0,
        )

        class _EngineWithTranscribe:
            model_id = "google/gemma-4-E2B-it"

            def is_loaded(self):
                return True

            def transcribe(self, audio, sr, **kw):
                return "hello world"

            def unload(self):
                pass

        daemon = Gemma4Daemon(cache_dir="/tmp")
        daemon._target_engine = _EngineWithTranscribe()  # noqa: SLF001
        monkeypatch.setattr(runtime_main, "_daemon", daemon)

        client = TestClient(runtime_main.app)
        r = client.post(
            "/audio/transcribe",
            files={"audio": ("test.wav", b"fake", "audio/wav")},
        )
        assert r.status_code == 200
        assert r.json()["text"] == "hello world"
