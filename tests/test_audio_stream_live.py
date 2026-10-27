"""Explicitly blocked physical Gemma audio cases; never needed for ROI coverage."""

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

import venom_core.api.audio_stream as audio_stream_mod
from tests.test_audio_stream_handler_roi import _add_connection, _make_handler

_VOICE_SESSION_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "data/audio/voice_sessions/20260525_115459_349506_137042488529824_a633d1bb"
)
_VOICE_FIXTURE_WAV = _VOICE_SESSION_FIXTURE / "recording.wav"
_VOICE_FIXTURE_WEBM = _VOICE_SESSION_FIXTURE / "original.webm"
_GEMMA4_LIVE_AUDIO_MODEL_CACHE = (
    Path(__file__).resolve().parents[1]
    / "models_cache/hf/models--google--gemma-4-E2B-it/snapshots"
)


def _live_gemma4_audio_enabled() -> bool:
    """Enable live Gemma4 audio probing only on machines with local model cache."""
    return bool(
        os.environ.get("GEMMA4_LIVE_AUDIO_TESTS") == "1"
        and _VOICE_FIXTURE_WAV.exists()
        and _VOICE_FIXTURE_WEBM.exists()
        and any(_GEMMA4_LIVE_AUDIO_MODEL_CACHE.glob("*"))
    )


@lru_cache(maxsize=1)
def _real_gemma4_transcription() -> str:
    """Return the real native Gemma4 transcription for the checked-in voice sample."""
    if not _live_gemma4_audio_enabled():
        pytest.skip("Live Gemma4 audio probe is not enabled")

    from scripts.dev.multi_runtime_direct_ingest_probe import (
        DEFAULT_MODEL_ID,
        _build_messages,
        _build_prompt,
        _load_model,
        _normalize_answer,
        _normalize_audio,
        _run_inference,
    )

    tmpdir = Path(tempfile.mkdtemp(prefix="gemma4_voice_roi_"))
    normalized = _normalize_audio(_VOICE_FIXTURE_WAV, tmpdir)
    model, processor, _ = _load_model(DEFAULT_MODEL_ID)
    prompt = _build_prompt(
        "Transcribe the speech in the audio. Return only the transcription, with no bullets and no extra commentary.",
        "",
        "transcribe",
    )
    messages = _build_messages(normalized.normalized_path, prompt)
    generated_text = _run_inference(
        model=model,
        processor=processor,
        messages=messages,
        max_new_tokens=64,
    )
    return _normalize_answer(generated_text, "transcribe")


@pytest.mark.unsafe_direct_runtime
@pytest.mark.asyncio
async def test_process_encoded_audio_buffer_full_flow(monkeypatch, tmp_path):
    """Encoded pipeline should persist and use the native Gemma4 audio path."""
    if not _live_gemma4_audio_enabled():
        pytest.skip("Live Gemma4 audio probe is not enabled")
    handler = _make_handler()
    cid = 31
    _add_connection(handler, cid)
    handler.active_connections[cid]["voice_mode"] = "summary"
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    audio_engine = MagicMock()
    audio_engine.speak = AsyncMock(return_value=np.array([10, 11], dtype=np.int16))
    handler.audio_engine = audio_engine

    sent = []
    audio_sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    async def fake_send_audio(_cid, audio_data):
        audio_sent.append(audio_data)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    monkeypatch.setattr(handler, "_send_audio", fake_send_audio)
    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )

    async def _invoke_multi_runtime(_wav_path, _cid):
        transcript = _real_gemma4_transcription()
        return {
            "text": transcript,
            "transcription": transcript,
            "response_text": transcript,
            "model": "google/gemma-4-E2B-it",
            "execution_trace": [
                "input_router",
                "image_preprocessor",
                "ocr_or_vision",
                "retrieval",
                "main_generation",
                "assistant_postprocess",
                "audio_output",
            ],
            "selected_policy": "balanced|vlm_only|off|off|off|off",
            "selected_image_strategy": "vlm_only",
            "retrieval_used": False,
            "retrieval_context_items": 0,
            "retrieval_route": "none",
            "assistant_used": False,
            "economy_mode_activated": False,
            "degradation_reasons": [],
            "component_snapshot": [],
            "raw_thinking_available": False,
        }

    monkeypatch.setattr(handler, "_invoke_multi_runtime", _invoke_multi_runtime)
    monkeypatch.setattr(
        handler,
        "_build_runtime_metadata",
        lambda _operator_agent=None: {
            "stt_model": "base",
            "stt_device": "cpu",
            "stt_compute_type": "int8",
            "llm_service_id": "chat",
            "llm_model": "gemma3:4b",
            "tts_model_path": "/tmp/voice.onnx",
            "tts_fallback": False,
            "tts_sample_rate": 22050,
        },
    )

    webm_bytes = _VOICE_FIXTURE_WEBM.read_bytes()
    await handler._process_encoded_audio_buffer(
        cid,
        [webm_bytes[: len(webm_bytes) // 2], webm_bytes[len(webm_bytes) // 2 :]],
        operator_agent=MagicMock(),
        mime_type="audio/webm;codecs=opus",
    )

    assert any(msg.get("status") == "decode" for msg in sent)
    assert any(msg.get("status") == "native_audio" for msg in sent)
    assert any(msg.get("type") == "transcription" for msg in sent)
    assert any(msg.get("type") == "response_text" for msg in sent)
    assert any(msg.get("status") == "tts" for msg in sent)
    assert any(msg.get("type") == "complete" for msg in sent)
    assert audio_sent
    audio_engine.speak.assert_awaited_once()
    session_path = next(tmp_path.iterdir())
    metadata = json.loads((session_path / "metadata.json").read_text())
    assert metadata["pipeline_id"] == "multi_runtime_piper"
    assert metadata["audio_input_status"] == "verified"
    assert metadata["decoder_source"] == "multi_runtime"
    assert metadata["transcription"] == _real_gemma4_transcription()
    assert metadata["response_text"] == _real_gemma4_transcription()


@pytest.mark.unsafe_direct_runtime
@pytest.mark.asyncio
async def test_process_audio_buffer_runs_normal_flow(monkeypatch, tmp_path):
    if not _live_gemma4_audio_enabled():
        pytest.skip("Live Gemma4 audio probe is not enabled")
    handler = _make_handler()
    cid = 81
    _add_connection(handler, cid, is_speaking=True)
    handler.audio_engine = MagicMock()
    handler.audio_engine.speak = AsyncMock(
        return_value=np.array([1, 2], dtype=np.int16)
    )

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    send_audio = AsyncMock()
    monkeypatch.setattr(handler, "_send_audio", send_audio)
    monkeypatch.setattr(handler, "_persist_voice_session", lambda *a, **k: tmp_path)
    monkeypatch.setattr(handler, "_update_voice_session_metadata", lambda *a, **k: None)
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda *_a, **_k: {"rt": 1})
    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )

    async def _invoke_multi_runtime(_wav_path, _cid):
        transcript = _real_gemma4_transcription()
        return {
            "text": transcript,
            "transcription": transcript,
            "response_text": transcript,
            "model": "google/gemma-4-E2B-it",
        }

    monkeypatch.setattr(handler, "_invoke_multi_runtime", _invoke_multi_runtime)

    wav_audio, wav_sr = handler._load_wav_int16(_VOICE_FIXTURE_WAV)

    await handler._process_audio_buffer(
        cid,
        [wav_audio],
        MagicMock(),
        sample_rate=wav_sr,
    )

    assert any(msg.get("status") == "native_audio" for msg in sent)
    assert any(msg.get("type") == "transcription" for msg in sent)
    assert any(msg.get("type") == "response_text" for msg in sent)
    assert any(msg.get("status") == "tts" for msg in sent)
    assert any(msg.get("type") == "complete" for msg in sent)
    assert send_audio.await_count == 1
