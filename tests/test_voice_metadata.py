from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.api.audio_stream as audio_stream_mod
import venom_core.main as core_main
from venom_core.utils.voice_metadata import (
    build_voice_reasoning_summary,
    build_voice_session_insights,
    build_voice_trace_annotations,
    infer_voice_emotion,
    infer_voice_session_mode,
)


def test_infer_voice_emotion_returns_neutral_for_empty_text():
    label, confidence, source = infer_voice_emotion("", "")

    assert label == "neutral"
    assert confidence == 0.0
    assert source == "none"


def test_infer_voice_emotion_detects_question_as_confusion():
    label, confidence, source = infer_voice_emotion(
        transcript="Co to jest kwadrat?",
        response="To figura geometryczna.",
    )

    assert label == "confused"
    assert confidence > 0.15
    assert source == "hybrid"


def test_infer_voice_emotion_avoids_false_positive_on_short_substrings():
    label, confidence, source = infer_voice_emotion(
        transcript="To jest okno, a nie zagadka.",
        response="Terazyk to tylko przykład.",
    )

    assert label == "neutral"
    assert confidence == 0.15
    assert source == "hybrid"


def test_infer_voice_emotion_detects_frustration_from_keywords():
    label, confidence, source = infer_voice_emotion(
        transcript="To nie dziala, mam problem i wszystko sie zawiesza.",
        response="",
    )

    assert label == "frustrated"
    assert confidence > 0.4
    assert source == "transcript"


def test_infer_voice_emotion_uses_response_source_when_no_transcript():
    label, confidence, source = infer_voice_emotion(
        transcript="",
        response="Super, dzięki!",
    )

    assert label == "positive"
    assert confidence > 0.15
    assert source == "response"


def test_infer_voice_emotion_marks_urgency_from_exclamation_marks():
    label, confidence, source = infer_voice_emotion(
        transcript="To jest pilne!!!",
        response="",
    )

    assert label == "urgent"
    assert confidence > 0.5
    assert source == "transcript"


def test_build_voice_reasoning_summary_returns_none_when_disabled():
    assert build_voice_reasoning_summary() is None


def test_build_voice_reasoning_summary_includes_enabled_fields():
    summary = build_voice_reasoning_summary(
        transcript="Ile to jest dwa razy dwa?",
        response="Dwa razy dwa to cztery.",
        voice_mode="summary",
        pipeline_id="gemma4_audio_piper",
        raw_thinking_available=True,
        reasoning_summary_enabled=True,
        emotion_label="curious",
    )

    assert summary is not None
    assert "pipeline=gemma4_audio_piper" in summary
    assert "mode=summary" in summary
    assert "input=Ile to jest dwa razy dwa?" in summary
    assert "output=Dwa razy dwa to cztery." in summary
    assert "emotion=curious" in summary
    assert "thinking=available" in summary
    assert "summary=enabled" in summary


def test_build_voice_session_insights_reports_reasoning_and_emotion():
    payload = build_voice_session_insights(
        transcript="To nie dziala, masakra, wszystko sie zawiesza.",
        response="",
        voice_mode="deep",
        pipeline_id="gemma4_audio_native",
        reasoning_summary_enabled=True,
        emotion_detection_enabled=True,
        emotion_response_style_enabled=True,
        raw_thinking_available=False,
    )

    assert payload["reasoning_summary_enabled"] is True
    assert payload["reasoning_summary_status"] == "summary"
    assert payload["raw_thinking_available"] is False
    assert payload["emotion_detection_enabled"] is True
    assert payload["emotion_response_style_enabled"] is True
    assert payload["emotion_label"] == "frustrated"
    assert payload["emotion_confidence"] is not None
    assert payload["emotion_source"] == "transcript"
    assert payload["reasoning_summary"] is not None


def test_build_voice_session_insights_prefers_raw_thinking_status():
    payload = build_voice_session_insights(
        transcript="",
        response="",
        voice_mode="standard",
        pipeline_id="gemma4_audio_native",
        reasoning_summary_enabled=False,
        emotion_detection_enabled=False,
        emotion_response_style_enabled=False,
        raw_thinking_available=True,
    )

    assert payload["reasoning_summary_status"] == "raw_available"
    assert payload["reasoning_summary"] is not None
    assert payload["emotion_label"] is None
    assert payload["emotion_confidence"] is None
    assert payload["emotion_source"] == "none"


def test_infer_voice_session_mode_prefers_native_audio_for_multi_runtime():
    assert (
        infer_voice_session_mode(
            voice_pipeline_mode="native_multi_runtime",
            pipeline_id="multi_runtime_piper",
            decoder_source="multi_runtime",
            native_audio_ms=1234.0,
        )
        == "native_audio"
    )


def test_infer_voice_session_mode_covers_fallback_and_unknown_paths():
    assert (
        infer_voice_session_mode(voice_pipeline_mode="whisper_llm_piper")
        == "whisper_llm_piper"
    )
    assert infer_voice_session_mode(pipeline_id="multi_runtime_piper") == "native_audio"
    assert infer_voice_session_mode(decoder_source="faster_whisper") == (
        "whisper_llm_piper"
    )
    assert infer_voice_session_mode(native_audio_ms=1.0) == "native_audio"
    assert infer_voice_session_mode() == "unknown"


def test_build_voice_trace_annotations_marks_audio_only_no_ops():
    annotations = build_voice_trace_annotations(
        [
            "input_router",
            "image_preprocessor",
            "ocr_or_vision",
            "retrieval",
            "main_generation",
            "assistant_postprocess",
            "audio_output",
        ],
        voice_pipeline_mode="native_multi_runtime",
        pipeline_id="multi_runtime_piper",
        decoder_source="multi_runtime",
        native_audio_ms=1234.0,
    )

    assert [item["status"] for item in annotations[:4]] == [
        "active",
        "no-op",
        "no-op",
        "no-op",
    ]
    assert annotations[4]["note"] == "model response"
    assert annotations[5]["note"] == "response shaping"
    assert annotations[6]["note"] == "tts output"


def test_build_voice_trace_annotations_returns_empty_for_blank_trace():
    assert build_voice_trace_annotations([]) == []


def test_build_voice_session_record_exposes_native_audio_contract():
    record = audio_stream_mod._build_voice_session_record(
        Path("session-a"),
        {
            "voice_pipeline_mode": "native_multi_runtime",
            "pipeline_id": "multi_runtime_piper",
            "decoder_source": "multi_runtime",
            "native_audio_ms": 123.0,
            "execution_trace": [
                "input_router",
                "image_preprocessor",
                "main_generation",
                "audio_output",
            ],
        },
    )

    assert record["voice_session_mode"] == "native_audio"
    assert record["execution_trace_mode"] == "audio_only"
    assert record["execution_trace_annotations"][1]["status"] == "no-op"


def test_whisper_fallback_helpers_expose_runtime_contract():
    capabilities = core_main._build_whisper_fallback_runtime_capabilities("vllm")
    pipeline = core_main._build_whisper_fallback_voice_pipeline("vllm")
    snapshot = core_main._build_whisper_fallback_voice_runtime_snapshot(
        SimpleNamespace(
            runtime_id="vllm@localhost",
            provider="vllm",
            model_name="qwen3.5:latest",
            endpoint="http://localhost:8000",
            config_hash="abc",
        )
    )

    assert capabilities["compatibility_profile"] == "whisper_llm_piper_fallback"
    assert capabilities["fallbacks"]["voice_fallback_pipeline"] == "whisper_llm_piper"
    assert pipeline["stt"] == "faster_whisper"
    assert pipeline["tts"] == "piper"
    assert snapshot["voice_pipeline"]["profile"] == "whisper_llm_piper_fallback"


def test_build_voice_runtime_state_reports_switching_and_failed():
    runtime_snapshot = {
        "runtime_id": "ollama@localhost",
        "provider": "ollama",
        "model_name": "qwen3.5:latest",
    }
    latest_session = {
        "audio_runtime_provider": "ollama",
        "audio_runtime_model": "qwen3.5:latest",
        "pipeline_id": "whisper_llm_piper",
        "created_at": "2026-05-24T09:12:00+00:00",
    }
    runtime_alignment = core_main._build_voice_runtime_alignment(
        runtime_snapshot=runtime_snapshot,
        latest_session=latest_session,
    )

    switching_state = core_main._build_voice_runtime_state(
        runtime_snapshot=runtime_snapshot,
        latest_session=latest_session,
        runtime_alignment=runtime_alignment,
        runtime_switch_gate={"in_progress": True, "to_runtime": "multi_runtime"},
        last_runtime_switch={"reason": "manual switch"},
    )

    failed_state = core_main._build_voice_runtime_state(
        runtime_snapshot=runtime_snapshot,
        latest_session=latest_session,
        runtime_alignment=runtime_alignment,
        runtime_switch_gate={"in_progress": False},
        last_runtime_switch={"reason": "switch error: denied"},
    )

    assert switching_state["switch"]["state"] == "switching"
    assert switching_state["response"]["matches_active"] is True
    assert failed_state["switch"]["state"] == "failed"


@pytest.mark.asyncio
async def test_audio_status_endpoint_includes_runtime_state(monkeypatch):
    class DummyHandler:
        def get_status(self, operator_agent=None):
            return {
                "enabled": True,
                "connected_clients": 1,
                "active_recordings": 0,
                "message": "ok",
            }

        def get_latest_voice_session(self):
            return {
                "session_id": "session-1",
                "created_at": "2026-05-24T09:12:00+00:00",
                "audio_runtime_provider": "ollama",
                "audio_runtime_model": "qwen3.5:latest",
            }

    monkeypatch.setattr(core_main, "audio_stream_handler", DummyHandler())
    monkeypatch.setattr(core_main, "operator_agent", object())
    monkeypatch.setattr(
        core_main,
        "_build_voice_runtime_snapshot",
        AsyncMock(
            return_value={
                "runtime_id": "ollama@localhost",
                "provider": "ollama",
                "model_name": "qwen3.5:latest",
            }
        ),
    )
    monkeypatch.setattr(
        core_main,
        "get_last_runtime_switch_event",
        lambda: {"at_utc": "2026-05-24T09:00:00+00:00"},
    )
    request = SimpleNamespace(url_for=lambda name: f"https://example.test/{name}")

    status = await core_main.audio_status_endpoint(request)

    assert status["runtime_alignment"]["response_runtime_fresh"] is True
    assert status["runtime_state"]["response"]["matches_active"] is True
    assert status["runtime_state"]["switch"]["state"] == "ready"


@pytest.mark.asyncio
async def test_audio_status_endpoint_without_handler_reports_idle_runtime_state(
    monkeypatch,
):
    monkeypatch.setattr(core_main, "audio_stream_handler", None)
    monkeypatch.setattr(core_main, "get_last_runtime_switch_event", lambda: None)
    monkeypatch.setattr(
        core_main,
        "_build_voice_runtime_snapshot",
        AsyncMock(
            return_value={
                "runtime_id": "ollama@localhost",
                "provider": "ollama",
                "model_name": "qwen3.5:latest",
            }
        ),
    )
    request = SimpleNamespace(url_for=lambda name: f"https://example.test/{name}")

    status = await core_main.audio_status_endpoint(request)

    assert status["enabled"] is False
    assert status["runtime_state"]["switch"]["state"] == "idle"
    assert status["runtime_alignment"]["response_runtime_fresh"] is False


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_covers_non_ollama_and_ollama_paths(
    monkeypatch,
):
    core_main._voice_runtime_snapshot_cache["entry"] = None
    monkeypatch.setattr(
        core_main,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            runtime_id="vllm@localhost",
            provider="vllm",
            model_name="gemma4:latest",
            endpoint="http://localhost:8000",
            config_hash="cfg-non-ollama",
        ),
    )

    non_ollama_snapshot = await core_main._build_voice_runtime_snapshot()
    assert non_ollama_snapshot["voice_pipeline"]["profile"] == (
        "whisper_llm_piper_fallback"
    )

    monkeypatch.setattr(
        core_main,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            runtime_id="ollama@localhost",
            provider="ollama",
            model_name="",
            endpoint="",
            config_hash="cfg-metadata-only",
        ),
    )
    metadata_only_snapshot = await core_main._build_voice_runtime_snapshot()
    assert metadata_only_snapshot["voice_pipeline"]["stt"] == "faster_whisper"

    runtime = SimpleNamespace(
        runtime_id="ollama@localhost",
        provider="ollama",
        model_name="qwen3.5:latest",
        endpoint="http://localhost:11434",
        config_hash="cfg-native",
    )
    core_main._voice_runtime_snapshot_cache["entry"] = None
    monkeypatch.setattr(core_main, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        core_main, "OllamaClient", lambda endpoint: SimpleNamespace(endpoint=endpoint)
    )
    monkeypatch.setattr(
        core_main,
        "probe_ollama_runtime_capabilities",
        AsyncMock(
            return_value=SimpleNamespace(
                to_dict=lambda: {
                    "compatibility_profile": "multimodal_audio",
                    "fallbacks": {"tts": "native"},
                    "probes": {"voice_contract": {"status": "ok"}},
                }
            )
        ),
    )
    monkeypatch.setattr(
        core_main,
        "resolve_voice_pipeline",
        lambda _caps: SimpleNamespace(
            to_dict=lambda: {
                "profile": "ollama_native_audio",
                "stt": "native_audio",
                "tts": "native_tts",
            }
        ),
    )

    native_snapshot = await core_main._build_voice_runtime_snapshot()
    assert native_snapshot["voice_pipeline"]["profile"] == (
        "whisper_llm_piper_fallback"
    )
    assert (
        native_snapshot["runtime_capabilities"]["fallbacks"]["voice_fallback_pipeline"]
        == "whisper_llm_piper"
    )
    assert native_snapshot["runtime_capabilities"]["fallbacks"]["tts"] == "piper"


def test_multi_runtime_transcribe_url_follows_service_origin(monkeypatch):
    handler = audio_stream_mod.AudioStreamHandler()
    monkeypatch.setattr(
        handler,
        "_multi_runtime_service_origin",
        lambda: "http://localhost:8014",
    )

    assert (
        handler._multi_runtime_transcribe_url()
        == "http://localhost:8014/audio/transcribe"
    )


@pytest.mark.asyncio
async def test_invoke_multi_runtime_rejects_missing_urls(monkeypatch, tmp_path):
    handler = audio_stream_mod.AudioStreamHandler()
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(handler, "_multi_runtime_respond_url", lambda: "")
    monkeypatch.setattr(handler, "_multi_runtime_transcribe_url", lambda: "")

    with pytest.raises(RuntimeError, match="audio endpoint is not configured"):
        await handler._invoke_multi_runtime(wav_path, 17)

    monkeypatch.setattr(
        handler, "_multi_runtime_respond_url", lambda: "http://runtime/v1/respond"
    )

    with pytest.raises(RuntimeError, match="transcription endpoint is not configured"):
        await handler._invoke_multi_runtime(wav_path, 18)


@pytest.mark.asyncio
async def test_audio_stream_native_pipeline_missing_engine_and_incomplete_result(
    monkeypatch, tmp_path
):
    handler = audio_stream_mod.AudioStreamHandler()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    wav_path = session_dir / "recording.wav"
    wav_path.write_bytes(b"wav")
    sent_json = []
    update_calls = []

    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler,
        "_send_json",
        AsyncMock(side_effect=lambda _cid, payload: sent_json.append(payload)),
    )

    assert (
        await handler._process_native_multi_runtime_pipeline(
            5, session_dir, wav_path, {}, 0.0, MagicMock()
        )
        is True
    )
    assert sent_json[0]["type"] == "error"

    handler.audio_engine = MagicMock()
    handler.audio_engine.speak = AsyncMock(return_value=b"audio")
    monkeypatch.setattr(
        handler,
        "_multi_runtime_runtime_snapshot",
        lambda: {"audio_runtime_provider": "multi_runtime"},
    )
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handler,
        "_invoke_multi_runtime",
        AsyncMock(return_value={"text": "", "response_text": ""}),
    )
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: update_calls.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _agent: {"llm": "x"})
    sent_json.clear()

    assert (
        await handler._process_native_multi_runtime_pipeline(
            6, session_dir, wav_path, {}, 0.0, MagicMock()
        )
        is True
    )
    assert any(item.get("type") == "error" for item in sent_json)
    assert update_calls[0]["audio_input_status"] == "failed"


@pytest.mark.asyncio
async def test_invoke_multi_runtime_covers_http_and_text_fallback_branches(
    monkeypatch, tmp_path
):
    handler = audio_stream_mod.AudioStreamHandler()
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(
        handler, "_multi_runtime_respond_url", lambda: "http://runtime/v1/respond"
    )
    monkeypatch.setattr(
        handler,
        "_multi_runtime_transcribe_url",
        lambda: "http://runtime/audio/transcribe",
    )

    class _AsyncBinaryFile:
        async def read(self):
            return b"fake-wave-content"

    class _AsyncOpenContext:
        async def __aenter__(self):
            return _AsyncBinaryFile()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_open_file(path, mode):
        return _AsyncOpenContext()

    monkeypatch.setattr(audio_stream_mod.anyio, "open_file", _fake_open_file)

    class _TranscribeErrorClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, files=None):
            if url.endswith("/audio/transcribe"):
                return SimpleNamespace(status_code=500, json=lambda: {}, text="down")
            return SimpleNamespace(
                status_code=200, json=lambda: {"text": "ok"}, text=""
            )

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _TranscribeErrorClient)
    with pytest.raises(RuntimeError, match="audio/transcribe"):
        await handler._invoke_multi_runtime(wav_path, 11)

    class _EmptyTranscribeClient(_TranscribeErrorClient):
        async def post(self, url, data=None, files=None):
            if url.endswith("/audio/transcribe"):
                return SimpleNamespace(
                    status_code=200, json=lambda: {"text": "   "}, text=""
                )
            return SimpleNamespace(
                status_code=200, json=lambda: {"text": "ok"}, text=""
            )

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _EmptyTranscribeClient)
    with pytest.raises(RuntimeError, match="empty transcription"):
        await handler._invoke_multi_runtime(wav_path, 12)

    class _GeneratedTextClient(_TranscribeErrorClient):
        async def post(self, url, data=None, files=None):
            if url.endswith("/audio/transcribe"):
                return SimpleNamespace(
                    status_code=200, json=lambda: {"text": "Ile?"}, text=""
                )
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"generated_text": "42", "message": {"content": "40"}},
                text="",
            )

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _GeneratedTextClient)
    generated_result = await handler._invoke_multi_runtime(wav_path, 13)
    assert generated_result["text"] == "Ile?"
    assert generated_result["response_text"] == "42"

    class _MessageContentClient(_TranscribeErrorClient):
        async def post(self, url, data=None, files=None):
            if url.endswith("/audio/transcribe"):
                return SimpleNamespace(
                    status_code=200, json=lambda: {"text": "Co to?"}, text=""
                )
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "response_text": "",
                    "generated_text": "",
                    "message": {"content": "40"},
                },
                text="",
            )

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _MessageContentClient)
    message_result = await handler._invoke_multi_runtime(wav_path, 14)
    assert message_result["text"] == "Co to?"
    assert message_result["response_text"] == "40"


@pytest.mark.asyncio
async def test_process_native_multi_runtime_pipeline_reports_native_failure(
    monkeypatch, tmp_path
):
    handler = audio_stream_mod.AudioStreamHandler()
    handler.audio_engine = MagicMock()
    handler.audio_engine.speak = AsyncMock(return_value=bytearray(b"audio"))
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    wav_path = session_dir / "recording.wav"
    wav_path.write_bytes(b"wav")
    timings_ms = {}
    sent_json = []
    update_calls = []

    monkeypatch.setattr(handler, "_multi_runtime_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler,
        "_multi_runtime_runtime_snapshot",
        lambda: {"audio_runtime_provider": "multi_runtime"},
    )
    monkeypatch.setattr(
        handler, "_multi_runtime_health_ok", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handler,
        "_invoke_multi_runtime",
        AsyncMock(side_effect=RuntimeError("native boom")),
    )
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: update_calls.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _agent: {"llm": "x"})
    monkeypatch.setattr(
        handler,
        "_send_json",
        AsyncMock(side_effect=lambda _cid, payload: sent_json.append(payload)),
    )
    monkeypatch.setattr(handler, "_send_audio", AsyncMock())

    result = await handler._process_native_multi_runtime_pipeline(
        15, session_dir, wav_path, timings_ms, 0.0, MagicMock()
    )

    assert result is True
    assert any(item.get("type") == "error" for item in sent_json)
    assert update_calls[0]["audio_input_status"] == "failed"
    assert update_calls[0]["pipeline_id"] == "multi_runtime_piper"
