"""Tests for the TTS runtime API endpoints (PR 213)."""

from __future__ import annotations

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
