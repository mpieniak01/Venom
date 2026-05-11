"""Tests for the TTS runtime API endpoints (PR 213)."""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import venom_core.main as main_module


def _localhost_request() -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


def _remote_request() -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))


class TestGetTtsRuntime:
    @pytest.mark.asyncio
    async def test_returns_dict_with_required_fields(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(main_module, "audio_engine", None)

        data = await main_module.get_tts_runtime(_localhost_request())

        assert "tts_engine" in data
        assert "available_engines" in data
        assert "engine_status" in data
        assert "current_option_id" in data
        assert "options" in data
        assert "fallback_enabled" in data
        assert "fallback_target" in data

    @pytest.mark.asyncio
    async def test_default_engine_is_piper_local(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(main_module, "audio_engine", None)

        data = await main_module.get_tts_runtime(_localhost_request())

        assert data["tts_engine"] == "piper_local"

    @pytest.mark.asyncio
    async def test_piper_options_use_audio_engine_model_path(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module,
            "audio_engine",
            SimpleNamespace(voice=SimpleNamespace(model_path="/tmp/runtime.onnx")),
        )

        data = await main_module.get_tts_runtime(_localhost_request())

        assert data["current_option_id"] == "/tmp/runtime.onnx"

    @pytest.mark.asyncio
    async def test_available_engines_contains_both_engines(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(main_module, "audio_engine", None)

        data = await main_module.get_tts_runtime(_localhost_request())

        engine_ids = [e["engine_id"] for e in data["available_engines"]]
        assert "piper_local" in engine_ids
        assert "fish_speech" in engine_ids

    @pytest.mark.asyncio
    async def test_fish_speech_status_disabled_when_not_enabled(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(main_module, "audio_engine", None)

        data = await main_module.get_tts_runtime(_localhost_request())

        assert data["engine_status"]["fish_speech"] == "disabled"

    @pytest.mark.asyncio
    async def test_fallback_enabled_and_target_is_piper(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(main_module, "audio_engine", None)

        data = await main_module.get_tts_runtime(_localhost_request())

        assert data["fallback_enabled"] is True
        assert data["fallback_target"] == "piper_local"

    def test_requires_localhost(self) -> None:
        from fastapi import HTTPException

        from venom_core.main import _require_localhost_request

        with pytest.raises(HTTPException) as exc_info:
            _require_localhost_request(_remote_request())
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_fish_speech_options_returned_when_active_engine(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "fish_speech")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"
        )
        monkeypatch.setattr(main_module, "audio_engine", None)
        piper_models_called = {"count": 0}

        def _raise_if_called():
            piper_models_called["count"] += 1
            raise AssertionError("Piper models should not be queried for fish_speech")

        monkeypatch.setattr(main_module, "_list_available_tts_models", _raise_if_called)

        data = await main_module.get_tts_runtime(_localhost_request())

        assert data["tts_engine"] == "fish_speech"
        assert len(data["options"]) == 1
        assert data["options"][0]["id"] == "fishaudio/fish-speech-1.5"
        assert piper_models_called["count"] == 0


class TestPostTtsRuntime:
    @pytest.mark.asyncio
    async def test_switch_to_fish_speech_returns_success(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "audio_engine", None)
        monkeypatch.setattr(main_module, "audio_stream_handler", None)
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"
        )

        from venom_core.services import config_manager as cm_mod

        monkeypatch.setattr(cm_mod.config_manager, "update_config", lambda x: None)
        mock_service_sync = AsyncMock(
            return_value={
                "fish_speech_service_action": "start",
                "fish_speech_service_ok": True,
            }
        )
        monkeypatch.setattr(
            main_module,
            "_sync_fish_speech_runtime_process",
            mock_service_sync,
        )

        payload = SimpleNamespace(tts_engine="fish_speech")
        result = await main_module.update_tts_runtime(payload, _localhost_request())

        assert result["status"] == "success"
        assert result["tts_engine"] == "fish_speech"
        assert "engine_status" in result
        mock_service_sync.assert_awaited_once_with("fish_speech")

    @pytest.mark.asyncio
    async def test_switch_to_piper_returns_success(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "audio_engine", None)
        monkeypatch.setattr(main_module, "audio_stream_handler", None)
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "fish_speech")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"
        )

        from venom_core.services import config_manager as cm_mod

        monkeypatch.setattr(cm_mod.config_manager, "update_config", lambda x: None)
        mock_service_sync = AsyncMock(
            return_value={
                "fish_speech_service_action": "stop",
                "fish_speech_service_ok": True,
            }
        )
        monkeypatch.setattr(
            main_module,
            "_sync_fish_speech_runtime_process",
            mock_service_sync,
        )

        payload = SimpleNamespace(tts_engine="piper_local")
        result = await main_module.update_tts_runtime(payload, _localhost_request())

        assert result["status"] == "success"
        assert result["tts_engine"] == "piper_local"
        mock_service_sync.assert_awaited_once_with("piper_local")

    @pytest.mark.asyncio
    async def test_invalid_engine_raises_400(self, monkeypatch) -> None:
        from fastapi import HTTPException

        payload = SimpleNamespace(tts_engine="banana_tts")
        with pytest.raises(HTTPException) as exc_info:
            await main_module.update_tts_runtime(payload, _localhost_request())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_updates_audio_engine_when_present(self, monkeypatch) -> None:
        mock_engine = AsyncMock()
        mock_engine.set_tts_engine = AsyncMock(
            return_value={"tts_engine": "fish_speech", "tts_engine_changed": True}
        )
        monkeypatch.setattr(main_module, "audio_engine", mock_engine)
        monkeypatch.setattr(main_module, "audio_stream_handler", None)
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"
        )

        from venom_core.services import config_manager as cm_mod

        monkeypatch.setattr(cm_mod.config_manager, "update_config", lambda x: None)
        monkeypatch.setattr(
            main_module,
            "_sync_fish_speech_runtime_process",
            AsyncMock(
                return_value={
                    "fish_speech_service_action": "start",
                    "fish_speech_service_ok": True,
                }
            ),
        )

        payload = SimpleNamespace(tts_engine="fish_speech")
        await main_module.update_tts_runtime(payload, _localhost_request())

        mock_engine.set_tts_engine.assert_called_once()
        call_args = mock_engine.set_tts_engine.call_args
        assert call_args[0][0] == "fish_speech"

    @pytest.mark.asyncio
    async def test_updates_separate_handler_engine_when_present(
        self, monkeypatch
    ) -> None:
        global_engine = AsyncMock()
        global_engine.set_tts_engine = AsyncMock(
            return_value={"tts_engine": "fish_speech", "tts_engine_changed": True}
        )
        handler_engine = AsyncMock()
        handler_engine.set_tts_engine = AsyncMock(
            return_value={"tts_engine": "fish_speech", "tts_engine_changed": True}
        )
        monkeypatch.setattr(main_module, "audio_engine", global_engine)
        monkeypatch.setattr(
            main_module,
            "audio_stream_handler",
            SimpleNamespace(audio_engine=handler_engine),
        )
        monkeypatch.setattr(main_module.SETTINGS, "TTS_ENGINE", "piper_local")
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"
        )

        from venom_core.services import config_manager as cm_mod

        monkeypatch.setattr(cm_mod.config_manager, "update_config", lambda x: None)
        monkeypatch.setattr(
            main_module,
            "_sync_fish_speech_runtime_process",
            AsyncMock(
                return_value={
                    "fish_speech_service_action": "start",
                    "fish_speech_service_ok": True,
                }
            ),
        )

        payload = SimpleNamespace(tts_engine="fish_speech")
        await main_module.update_tts_runtime(payload, _localhost_request())

        global_engine.set_tts_engine.assert_awaited_once()
        handler_engine.set_tts_engine.assert_awaited_once()

    def test_piper_compatibility_endpoint_still_has_correct_fields(
        self, monkeypatch
    ) -> None:
        """Regression: existing /api/v1/audio/tts/models endpoint unaffected."""
        monkeypatch.setattr(main_module, "_list_available_tts_models", lambda: [])
        monkeypatch.setattr(main_module, "audio_engine", None)
        monkeypatch.setattr(main_module.SETTINGS, "TTS_MODEL_PATH", "")

        import asyncio

        result = asyncio.run(main_module.list_audio_tts_models(_localhost_request()))
        assert "models" in result
        assert "current_model_path" in result


class TestGetFishSpeechEngineStatus:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_not_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", False)
        status = await main_module._get_fish_speech_engine_status()
        assert status == "disabled"

    @pytest.mark.asyncio
    async def test_returns_ready_when_daemon_healthy(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", True)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch(
            "venom_core.perception.fish_speech_tts_client.FishSpeechTtsClient",
            return_value=mock_client,
        ):
            status = await main_module._get_fish_speech_engine_status()

        assert status == "ready"

    @pytest.mark.asyncio
    async def test_returns_offline_when_daemon_not_healthy(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", True)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=False)
        mock_client.aclose = AsyncMock()

        with patch(
            "venom_core.perception.fish_speech_tts_client.FishSpeechTtsClient",
            return_value=mock_client,
        ):
            status = await main_module._get_fish_speech_engine_status()

        assert status == "offline"

    @pytest.mark.asyncio
    async def test_returns_error_when_client_construction_fails(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(main_module.SETTINGS, "FISH_SPEECH_ENABLED", True)
        monkeypatch.setattr(
            main_module.SETTINGS, "FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"
        )

        with patch(
            "venom_core.perception.fish_speech_tts_client.FishSpeechTtsClient",
            side_effect=RuntimeError("boom"),
        ):
            status = await main_module._get_fish_speech_engine_status()

        assert status == "error"


class TestAudioStatusEndpointFastLane:
    @pytest.mark.asyncio
    async def test_marks_fish_speech_fallback_when_offline(self, monkeypatch) -> None:
        class DummyHandler:
            def get_status(self, operator_agent=None):
                del operator_agent
                return {
                    "enabled": True,
                    "connected_clients": 1,
                    "active_recordings": 0,
                    "message": "",
                    "tts_engine": "fish_speech",
                    "tts_fallback": False,
                    "tts_ready": False,
                }

            def get_latest_voice_session(self):
                return None

        monkeypatch.setattr(main_module, "audio_stream_handler", DummyHandler())
        monkeypatch.setattr(
            main_module,
            "_get_fish_speech_engine_status",
            AsyncMock(return_value="offline"),
        )
        monkeypatch.setattr(
            main_module,
            "_build_voice_runtime_snapshot",
            AsyncMock(return_value={"runtime_id": "fish_speech"}),
        )
        monkeypatch.setattr(main_module, "operator_agent", object())
        request = SimpleNamespace(url_for=lambda name: f"https://example.test/{name}")

        status = await main_module.audio_status_endpoint(request)

        assert status["tts_engine"] == "fish_speech"
        assert status["tts_fallback"] is True
        assert status["tts_ready"] is True


class TestSyncFishSpeechRuntimeProcessFastLane:
    @pytest.mark.asyncio
    async def test_missing_script_returns_skipped(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.Path, "exists", lambda self: False)

        result = await main_module._sync_fish_speech_runtime_process("fish_speech")

        assert result["fish_speech_service_action"] == "start"
        assert result["fish_speech_service_skipped"] is True
        assert result["fish_speech_service_reason"] == "script_missing"

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.Path, "exists", lambda self: True)

        class DummyProcess:
            def __init__(self):
                self.returncode = None
                self.kill_called = False

            async def communicate(self):
                raise asyncio.TimeoutError

            def kill(self):
                self.kill_called = True

            async def wait(self):
                return None

        dummy_process = DummyProcess()

        async def _fake_create_subprocess_exec(*args, **kwargs):
            del args, kwargs
            return dummy_process

        monkeypatch.setattr(
            main_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
        )

        result = await main_module._sync_fish_speech_runtime_process("fish_speech")

        assert dummy_process.kill_called is True
        assert result["fish_speech_service_ok"] is False
        assert result["fish_speech_service_stderr"] == "timeout"

    @pytest.mark.asyncio
    async def test_success_returns_stdout_and_exit_code(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module.Path, "exists", lambda self: True)

        class DummyProcess:
            def __init__(self):
                self.returncode = 0

            async def communicate(self):
                return b"done\n", b""

        async def _fake_create_subprocess_exec(*args, **kwargs):
            del args, kwargs
            return DummyProcess()

        monkeypatch.setattr(
            main_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
        )

        result = await main_module._sync_fish_speech_runtime_process("piper_local")

        assert result["fish_speech_service_action"] == "stop"
        assert result["fish_speech_service_ok"] is True
        assert result["fish_speech_service_exit_code"] == 0
        assert result["fish_speech_service_stdout"] == "done"


class TestFishSpeechEngineFastLane:
    def _reset_engine_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import services.fish_speech_runtime.engine as engine_module

        monkeypatch.setattr(engine_module, "_engine_instance", None, raising=False)

    def _prepare_source_checkout(self, source_root: Path, with_inference: bool) -> None:
        (source_root / "tools" / "server").mkdir(parents=True)
        (source_root / "tools" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "model_manager.py").write_text(
            textwrap.dedent(
                """
                class _DummyDecoder:
                    class spec_transform:
                        sample_rate = 24000


                class ModelManager:
                    def __init__(self, **kwargs):
                        self.kwargs = kwargs
                        self.tts_inference_engine = type(
                            "DummyEngine",
                            (object,),
                            {"decoder_model": _DummyDecoder()},
                        )()
                """
            )
        )
        if with_inference:
            (source_root / "tools" / "schema.py").write_text(
                textwrap.dedent(
                    """
                    class ServeTTSRequest:
                        def __init__(self, **kwargs):
                            self.__dict__.update(kwargs)
                    """
                )
            )
            (source_root / "tools" / "server" / "inference.py").write_text(
                textwrap.dedent(
                    """
                    import numpy as np


                    def inference_wrapper(req, engine):
                        del req, engine
                        yield np.zeros(240, dtype=np.float32)
                    """
                )
            )

    def _prepare_snapshot(
        self,
        cache_dir: Path,
        snapshot_name: str,
        mtime: float,
    ) -> Path:
        snapshot_dir = (
            cache_dir
            / "models--fishaudio--fish-speech-1.5"
            / "snapshots"
            / snapshot_name
        )
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.pth").write_bytes(b"model")
        (snapshot_dir / "tokenizer.tiktoken").write_text("tokenizer")
        (snapshot_dir / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth").write_bytes(
            b"decoder"
        )
        os.utime(snapshot_dir, (mtime, mtime))
        return snapshot_dir

    def test_engine_loads_newest_snapshot_in_fast_lane(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        self._reset_engine_singleton(monkeypatch)
        for module_name in list(sys.modules):
            if module_name == "tools" or module_name.startswith("tools."):
                sys.modules.pop(module_name, None)

        source_root = tmp_path / "fish-speech-src"
        self._prepare_source_checkout(source_root, with_inference=False)

        cache_dir = tmp_path / "cache"
        old_snapshot = self._prepare_snapshot(cache_dir, "aaa_old", 1_000_000_000.0)
        new_snapshot = self._prepare_snapshot(cache_dir, "zzz_new", 1_000_000_100.0)
        assert old_snapshot.exists()
        assert new_snapshot.exists()

        monkeypatch.setenv("FISH_SPEECH_SOURCE_DIR", str(source_root))
        monkeypatch.setenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5")
        monkeypatch.setenv("FISH_SPEECH_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("FISH_SPEECH_DEVICE", "cpu")

        from services.fish_speech_runtime.engine import FishSpeechEngine

        engine = FishSpeechEngine(
            model_id="fishaudio/fish-speech-1.5",
            cache_dir=str(cache_dir),
            device="cpu",
        )

        assert engine.load() is True
        assert engine.is_loaded is True
        assert engine._model_manager.kwargs["llama_checkpoint_path"] == str(
            new_snapshot
        )
        assert engine._model_manager.kwargs["decoder_checkpoint_path"] == str(
            new_snapshot / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
        )
        assert engine._sample_rate == 24000

    def test_engine_synthesize_uses_source_inference_wrapper_in_fast_lane(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        self._reset_engine_singleton(monkeypatch)
        for module_name in list(sys.modules):
            if module_name == "tools" or module_name.startswith("tools."):
                sys.modules.pop(module_name, None)

        source_root = tmp_path / "fish-speech-src"
        self._prepare_source_checkout(source_root, with_inference=True)

        cache_dir = tmp_path / "cache"
        self._prepare_snapshot(cache_dir, "abc123", 1_000_000_000.0)

        monkeypatch.setenv("FISH_SPEECH_SOURCE_DIR", str(source_root))
        monkeypatch.setenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5")
        monkeypatch.setenv("FISH_SPEECH_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("FISH_SPEECH_DEVICE", "cpu")

        from services.fish_speech_runtime.engine import FishSpeechEngine

        engine = FishSpeechEngine(
            model_id="fishaudio/fish-speech-1.5",
            cache_dir=str(cache_dir),
            device="cpu",
        )

        assert engine.load() is True
        wav_bytes = engine.synthesize("co to jest kwadrat?")
        assert wav_bytes.startswith(b"RIFF")
        assert len(wav_bytes) > 44
