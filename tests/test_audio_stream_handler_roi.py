import asyncio
import base64
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

import venom_core.api.audio_stream as audio_stream_mod
from venom_core.api.audio_stream import AudioStreamHandler, get_audio_stream_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(**kwargs) -> AudioStreamHandler:
    """Return a fresh handler with no audio engine."""
    return AudioStreamHandler(audio_engine=None, **kwargs)


def _add_connection(handler: AudioStreamHandler, cid: int, is_speaking: bool = False):
    """Register a fake connection on the handler."""
    ws = MagicMock()
    ws.send_text = AsyncMock()
    handler.active_connections[cid] = {
        "websocket": ws,
        "audio_buffer": [],
        "audio_bytes_buffer": [],
        "is_speaking": is_speaking,
        "sample_rate": 16000,
        "channels": 1,
        "speech_detected": False,
        "recording_format": "pcm16",
        "mime_type": "",
        "audio_config": {},
        "voice_mode": "standard",
    }
    return ws


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_initialization_defaults():
    """Handler initialises with expected defaults."""
    handler = AudioStreamHandler()
    assert handler.audio_engine is None
    assert handler.vad_threshold == pytest.approx(0.5)
    assert handler.silence_duration == pytest.approx(1.5)
    assert handler.active_connections == {}


def test_initialization_custom_values():
    """Custom constructor arguments are stored correctly."""
    handler = AudioStreamHandler(vad_threshold=0.1, silence_duration=2.0)
    assert handler.vad_threshold == pytest.approx(0.1)
    assert handler.silence_duration == pytest.approx(2.0)


def test_get_status_reports_basic_state():
    """get_status returns state useful for UI and healthchecks."""
    handler = _make_handler(vad_threshold=0.2, silence_duration=1.0)
    cid = 42
    _add_connection(handler, cid, is_speaking=True)

    status = handler.get_status(operator_agent=object())

    assert status["enabled"] is False
    assert status["connected_clients"] == 1
    assert status["active_recordings"] == 1
    assert status["vad_threshold"] == pytest.approx(0.2)
    assert status["silence_duration"] == pytest.approx(1.0)
    assert status["operator_ready"] is True
    assert status["stt_backend"] is None
    assert status["tts_backend"] is None
    assert "dependencies" in status


def test_get_status_reports_loaded_backends_and_dependencies(monkeypatch):
    """get_status exposes backend metadata when the engine is ready."""
    handler = _make_handler()

    class DummyWhisper:
        model = object()
        model_size = "base"
        device = "cpu"

    class DummyVoice:
        voice = object()
        model_path = "/tmp/voice.onnx"
        is_fallback_mode = False

    handler.audio_engine = MagicMock()
    handler.audio_engine.whisper = DummyWhisper()
    handler.audio_engine.voice = DummyVoice()
    monkeypatch.setattr(
        audio_stream_mod.shutil, "which", lambda _name: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr(
        audio_stream_mod.importlib.util,
        "find_spec",
        lambda name: object()
        if name in {"faster_whisper", "piper", "sounddevice"}
        else None,
    )

    status = handler.get_status(operator_agent=object())

    assert status["enabled"] is True
    assert status["stt_backend"] == "faster-whisper"
    assert status["stt_ready"] is True
    assert status["tts_backend"] == "piper"
    assert status["tts_ready"] is True
    assert status["tts_fallback"] is False
    assert status["dependencies"] == {
        "ffmpeg": True,
        "faster_whisper": True,
        "piper": True,
        "sounddevice": True,
    }


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------


def test_get_audio_stream_handler_returns_same_instance(monkeypatch):
    """get_audio_stream_handler returns the same singleton on repeated calls."""
    monkeypatch.setattr(audio_stream_mod, "audio_stream_handler", None)
    first = get_audio_stream_handler()
    second = get_audio_stream_handler()
    assert first is second
    # Cleanup
    monkeypatch.setattr(audio_stream_mod, "audio_stream_handler", None)


def test_get_audio_stream_handler_creates_instance(monkeypatch):
    """get_audio_stream_handler creates a new instance when none exists."""
    monkeypatch.setattr(audio_stream_mod, "audio_stream_handler", None)
    handler = get_audio_stream_handler()
    assert isinstance(handler, AudioStreamHandler)
    monkeypatch.setattr(audio_stream_mod, "audio_stream_handler", None)


# ---------------------------------------------------------------------------
# _send_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_json_calls_websocket_send_text():
    """_send_json serialises data and delegates to websocket.send_text."""
    handler = _make_handler()
    cid = 1
    ws = _add_connection(handler, cid)

    await handler._send_json(cid, {"type": "pong"})

    ws.send_text.assert_called_once()
    sent_payload = json.loads(ws.send_text.call_args[0][0])
    assert sent_payload["type"] == "pong"


@pytest.mark.asyncio
async def test_send_json_missing_connection_is_silent():
    """_send_json does nothing when the connection_id is not registered."""
    handler = _make_handler()
    # No connection registered – must not raise
    await handler._send_json(999, {"type": "ok"})


# ---------------------------------------------------------------------------
# _send_audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_audio_encodes_base64():
    """_send_audio sends a JSON message with base64-encoded audio."""
    handler = _make_handler()
    cid = 2
    ws = _add_connection(handler, cid)

    audio = np.array([100, 200, 300], dtype=np.int16)
    await handler._send_audio(cid, audio)

    ws.send_text.assert_called_once()
    msg = json.loads(ws.send_text.call_args[0][0])
    assert msg["type"] == "audio_response"
    # Verify that the audio field is valid base64
    decoded = base64.b64decode(msg["audio"])
    assert decoded == audio.tobytes()


@pytest.mark.asyncio
async def test_send_audio_missing_connection_is_silent():
    """_send_audio does nothing when the connection_id is not registered."""
    handler = _make_handler()
    audio = np.zeros(64, dtype=np.int16)
    await handler._send_audio(999, audio)


# ---------------------------------------------------------------------------
# _handle_control_message  (start / stop / ping / invalid JSON)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_control_message_start_stop(monkeypatch):
    """start_recording sets is_speaking=True; stop_recording triggers processing."""
    handler = _make_handler()
    cid = 123
    handler.active_connections[cid] = {
        "websocket": None,
        "audio_buffer": [np.array([1, 2], dtype=np.int16)],
        "audio_bytes_buffer": [],
        "is_speaking": False,
        "sample_rate": 16000,
        "channels": 1,
        "speech_detected": False,
        "recording_format": "pcm16",
        "mime_type": "",
        "audio_config": {},
        "voice_mode": "standard",
    }

    sent = []
    processed = []

    async def fake_send_json(_cid, payload):
        await asyncio.sleep(0)
        sent.append(payload)

    async def fake_process(_cid, _buffer, _agent, sample_rate=16000):
        await asyncio.sleep(0)
        processed.append(True)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    monkeypatch.setattr(handler, "_process_audio_buffer", fake_process)

    await handler._handle_control_message(
        cid, json.dumps({"command": "start_recording"}), None
    )
    assert handler.active_connections[cid]["is_speaking"] is True
    assert sent[-1]["type"] == "recording_started"
    handler.active_connections[cid]["audio_buffer"].append(
        np.array([1, 2, 3], dtype=np.int16)
    )

    await handler._handle_control_message(
        cid, json.dumps({"command": "stop_recording"}), None
    )
    assert processed


@pytest.mark.asyncio
async def test_handle_websocket_registers_and_cleans_up_connection():
    """handle_websocket should register connection state and clean up on disconnect."""
    handler = _make_handler()
    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive = AsyncMock(side_effect=audio_stream_mod.WebSocketDisconnect())

    await handler.handle_websocket(websocket, operator_agent=None)

    websocket.accept.assert_awaited_once()
    assert handler.active_connections == {}


@pytest.mark.asyncio
async def test_handle_websocket_routes_text_and_bytes(monkeypatch):
    """handle_websocket should dispatch text commands and raw bytes."""
    handler = _make_handler()
    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive = AsyncMock(
        side_effect=[
            {"text": json.dumps({"command": "ping"})},
            {"bytes": b"pcm-data"},
            audio_stream_mod.WebSocketDisconnect(),
        ]
    )

    control_calls = []
    byte_calls = []

    async def fake_control(connection_id, message, operator_agent):
        control_calls.append((connection_id, message, operator_agent))

    def fake_audio(connection_id, payload, operator_agent):
        byte_calls.append((connection_id, payload, operator_agent))

    monkeypatch.setattr(handler, "_handle_control_message", fake_control)
    monkeypatch.setattr(handler, "_handle_audio_data", fake_audio)

    await handler.handle_websocket(websocket, operator_agent="agent")

    assert control_calls
    assert control_calls[0][1] == json.dumps({"command": "ping"})
    assert byte_calls
    assert byte_calls[0][1] == b"pcm-data"


@pytest.mark.asyncio
async def test_handle_control_message_start_stop_encoded(monkeypatch):
    """Encoded MediaRecorder chunks use the encoded processing path."""
    handler = _make_handler()
    cid = 124
    _add_connection(handler, cid)

    processed = []

    async def fake_send_json(_cid, _payload):
        await asyncio.sleep(0)

    async def fake_process(_cid, chunks, _agent, mime_type=""):
        processed.append((chunks, mime_type))

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    monkeypatch.setattr(handler, "_process_encoded_audio_buffer", fake_process)

    await handler._handle_control_message(
        cid,
        json.dumps(
            {
                "command": "start_recording",
                "format": "mediarecorder",
                "mime_type": "audio/webm;codecs=opus",
            }
        ),
        None,
    )
    handler._handle_audio_data(cid, b"encoded-audio", operator_agent=None)
    await handler._handle_control_message(
        cid, json.dumps({"command": "stop_recording"}), None
    )

    assert processed == [([b"encoded-audio"], "audio/webm;codecs=opus")]


@pytest.mark.asyncio
async def test_handle_control_message_audio_config_updates_connection(monkeypatch):
    """audio_config primes the connection before recording starts."""
    handler = _make_handler()
    cid = 125
    _add_connection(handler, cid)

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)

    await handler._handle_control_message(
        cid,
        json.dumps(
            {
                "command": "audio_config",
                "sample_rate": 48000,
                "channels": 1,
                "format": "mediarecorder",
                "mime_type": "audio/webm;codecs=opus",
            }
        ),
        None,
    )

    conn = handler.active_connections[cid]
    assert conn["sample_rate"] == 48000
    assert conn["recording_format"] == "mediarecorder"
    assert conn["mime_type"] == "audio/webm;codecs=opus"
    assert conn["audio_config"] == {
        "sample_rate": 48000,
        "channels": 1,
        "format": "mediarecorder",
        "mime_type": "audio/webm;codecs=opus",
    }
    assert sent[-1]["type"] == "audio_config"
    assert sent[-1]["status"] == "ok"


@pytest.mark.asyncio
async def test_handle_control_message_voice_mode_updates_connection(monkeypatch):
    """voice_mode command updates the per-connection processing mode."""
    handler = _make_handler()
    cid = 126
    _add_connection(handler, cid)

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)

    await handler._handle_control_message(
        cid,
        json.dumps({"command": "voice_mode", "mode": "deep_analysis"}),
        None,
    )

    conn = handler.active_connections[cid]
    assert conn["voice_mode"] == "deep_analysis"
    assert sent[-1]["type"] == "voice_mode"
    assert sent[-1]["mode"] == "deep_analysis"


@pytest.mark.asyncio
async def test_process_audio_buffer_uses_voice_mode(monkeypatch, tmp_path):
    """Voice mode should be forwarded to the operator agent."""
    handler = _make_handler()
    cid = 127
    _add_connection(handler, cid)
    handler.active_connections[cid]["voice_mode"] = "action_items"
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    audio_engine = MagicMock()
    audio_engine.whisper = None
    audio_engine.voice = None
    audio_engine.listen = AsyncMock(return_value="co robić dalej?")
    audio_engine.speak = AsyncMock(return_value=np.zeros(16000, dtype=np.int16))
    handler.audio_engine = audio_engine

    operator_agent = MagicMock()
    operator_agent._resolve_chat_service_id.return_value = "chat"
    operator_agent.process = AsyncMock(return_value="Wykonaj krok 1.")

    await handler._process_audio_buffer(
        cid,
        [np.ones(16000, dtype=np.int16)],
        operator_agent=operator_agent,
        sample_rate=16000,
    )

    operator_agent.process.assert_awaited()
    args, kwargs = operator_agent.process.await_args
    assert args[0] == "co robić dalej?"
    assert kwargs["mode"] == "action_items"


@pytest.mark.asyncio
async def test_handle_control_message_ping_responds_pong(monkeypatch):
    """ping command returns a pong response."""
    handler = _make_handler()
    cid = 10
    _add_connection(handler, cid)

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    await handler._handle_control_message(cid, json.dumps({"command": "ping"}), None)

    assert any(m.get("type") == "pong" for m in sent)


@pytest.mark.asyncio
async def test_handle_control_message_invalid_json_does_not_raise():
    """Invalid JSON is handled gracefully (no exception propagated)."""
    handler = _make_handler()
    cid = 20
    _add_connection(handler, cid)
    # Must not raise
    await handler._handle_control_message(cid, "not_valid_json{{{", None)


# ---------------------------------------------------------------------------
# _detect_voice_activity
# ---------------------------------------------------------------------------


def test_detect_voice_activity_threshold():
    """VAD returns False for silent audio and True for loud audio."""
    handler = _make_handler(vad_threshold=0.05)
    silent = np.zeros(512, dtype=np.int16)
    loud = np.ones(512, dtype=np.int16) * 5000

    assert bool(handler._detect_voice_activity(silent)) is False
    assert bool(handler._detect_voice_activity(loud)) is True


def test_detect_voice_activity_empty_array_returns_false():
    """VAD returns False for an empty array (edge case)."""
    handler = _make_handler()
    empty = np.array([], dtype=np.int16)
    # Should not raise and should explicitly classify empty chunk as no voice.
    result = handler._detect_voice_activity(empty)
    assert result is False


def test_persist_voice_session_writes_wav_and_metadata(monkeypatch, tmp_path):
    """Voice sessions should be stored on disk for later inspection."""
    handler = _make_handler()
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    audio, audio_stats = handler._normalize_recorded_audio(
        np.array([0, 32767, -32768], dtype=np.int16)
    )
    session_dir = handler._persist_voice_session(
        connection_id=123,
        audio=audio,
        sample_rate=44100,
        audio_stats=audio_stats,
    )

    wav_path = session_dir / "recording.wav"
    metadata_path = session_dir / "metadata.json"

    assert wav_path.exists()
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["connection_id"] == 123
    assert metadata["sample_rate"] == 44100
    assert metadata["samples"] == 3
    assert metadata["session_id"] == session_dir.name
    assert metadata["wav_path"] == str(wav_path)
    assert "gain_applied" in metadata
    assert "peak_before_normalization" in metadata
    assert "rms_after_normalization" in metadata


def test_persist_encoded_voice_session_with_bytes_input(monkeypatch, tmp_path):
    """Encoded voice sessions should persist bytes input and metadata."""
    handler = _make_handler()
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    class DummyResult:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        audio_stream_mod.subprocess, "run", lambda *a, **k: DummyResult()
    )
    monkeypatch.setattr(
        handler,
        "_load_wav_int16",
        lambda _path: (np.array([1, 2], dtype=np.int16), 16000),
    )

    session_dir = handler._persist_encoded_voice_session(
        connection_id=321,
        encoded_audio=b"fake-webm-bytes",
        mime_type="audio/webm;codecs=opus",
    )

    metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["connection_id"] == 321
    assert metadata["input_format"] == "mediarecorder"
    assert metadata["mime_type"] == "audio/webm;codecs=opus"
    assert metadata["sample_rate"] == 16000
    assert metadata["session_id"] == session_dir.name
    assert (session_dir / "original.webm").exists()


def test_persist_encoded_voice_session_with_chunk_list(monkeypatch, tmp_path):
    """Encoded voice sessions should also accept iterables of chunks."""
    handler = _make_handler()
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    class DummyResult:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        audio_stream_mod.subprocess, "run", lambda *a, **k: DummyResult()
    )
    monkeypatch.setattr(
        handler,
        "_load_wav_int16",
        lambda _path: (np.array([3, 4, 5], dtype=np.int16), 44100),
    )

    session_dir = handler._persist_encoded_voice_session(
        connection_id=322,
        encoded_audio=[b"chunk-a", b"chunk-b"],
        mime_type="audio/ogg",
    )

    metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["connection_id"] == 322
    assert metadata["sample_rate"] == 44100
    assert metadata["samples"] == 3
    assert (session_dir / "original.bin").exists()


def test_get_latest_voice_session_returns_most_recent_session(monkeypatch, tmp_path):
    """Handler should point UI to the newest stored voice session."""
    handler = _make_handler()
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    older = tmp_path / "20250101_010101_1"
    newer = tmp_path / "20250102_010101_2"
    tiny = tmp_path / "20250103_010101_3"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    tiny.mkdir(parents=True)

    for session_dir, label in ((older, "old"), (newer, "new"), (tiny, "tiny")):
        wav_path = session_dir / "recording.wav"
        wav_path.write_bytes(b"RIFFTEST")
        metadata = {
            "created_at": f"{label}-created",
            "duration_sec": 0.1
            if label == "tiny"
            else (1.5 if label == "old" else 2.5),
            "sample_rate": 44100 if label == "old" else 16000,
            "samples": 1024 if label == "tiny" else 8192,
            "transcription": f"{label}-text",
            "response_text": f"{label}-response",
            "timings_ms": {"stt_ms": 120.0, "total_backend_ms": 450.0},
            "runtime": {"llm_model": "gemma3:4b", "stt_model": "base"},
        }
        (session_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False),
            encoding="utf-8",
        )
        mtime = (
            1_700_000_000
            if label == "old"
            else (1_700_000_100 if label == "new" else 1_700_000_200)
        )
        os.utime(session_dir / "metadata.json", (mtime, mtime))
        os.utime(wav_path, (mtime, mtime))

    latest = handler.get_latest_voice_session()

    assert latest is not None
    assert latest["session_id"] == "20250102_010101_2"
    assert latest["transcription"] == "new-text"
    assert latest["response_text"] == "new-response"
    assert latest["sample_rate"] == 16000
    assert latest["session_id"] == "20250102_010101_2"
    assert latest["timings_ms"] == {"stt_ms": 120.0, "total_backend_ms": 450.0}
    assert latest["runtime"] == {"llm_model": "gemma3:4b", "stt_model": "base"}


def test_collect_latest_voice_session_record_handles_edge_cases(monkeypatch, tmp_path):
    """Collector should skip invalid sessions and preserve defaults."""
    root = tmp_path / "voice_sessions"
    root.mkdir(parents=True)
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", root)

    missing = root / "20260101_010101_1"
    missing.mkdir()

    invalid = root / "20260102_010101_2"
    invalid.mkdir()
    (invalid / "recording.wav").write_bytes(b"RIFFTEST")
    (invalid / "metadata.json").write_text("{not-json}", encoding="utf-8")

    tiny = root / "20260103_010101_3"
    tiny.mkdir()
    (tiny / "recording.wav").write_bytes(b"RIFFTEST")
    (tiny / "metadata.json").write_text(
        json.dumps(
            {
                "duration_sec": 0.1,
                "samples": 10,
                "created_at": "tiny",
            }
        ),
        encoding="utf-8",
    )

    valid = root / "20260104_010101_4"
    valid.mkdir()
    wav_path = valid / "recording.wav"
    wav_path.write_bytes(b"RIFFTEST")
    (valid / "metadata.json").write_text(
        json.dumps(
            {
                "duration_sec": 1.0,
                "samples": 8192,
                "voice_mode": "summary",
                "created_at": "valid",
            }
        ),
        encoding="utf-8",
    )

    os.utime(invalid / "metadata.json", (1_700_000_000, 1_700_000_000))
    os.utime((invalid / "recording.wav"), (1_700_000_000, 1_700_000_000))
    os.utime(tiny / "metadata.json", (1_700_000_100, 1_700_000_100))
    os.utime((tiny / "recording.wav"), (1_700_000_100, 1_700_000_100))
    os.utime(valid / "metadata.json", (1_700_000_200, 1_700_000_200))
    os.utime((valid / "recording.wav"), (1_700_000_200, 1_700_000_200))

    latest = audio_stream_mod.collect_latest_voice_session_record(root)

    assert latest is not None
    assert latest["session_id"] == valid.name
    assert latest["voice_mode"] == "summary"
    assert latest["created_at"] == "valid"
    assert "wav_path" not in latest


def test_collect_latest_voice_session_record_returns_none_for_missing_root(tmp_path):
    """Missing root should return None without raising."""
    assert (
        audio_stream_mod.collect_latest_voice_session_record(tmp_path / "missing")
        is None
    )


def test_is_voice_session_eligible_handles_invalid_metadata():
    """Eligibility helper should be tolerant to malformed metadata."""
    assert audio_stream_mod._is_voice_session_eligible(
        {"duration_sec": "bad", "samples": object()}
    )
    assert not audio_stream_mod._is_voice_session_eligible(
        {"duration_sec": 0.1, "samples": 999999}
    )
    assert not audio_stream_mod._is_voice_session_eligible(
        {"duration_sec": 1.0, "samples": 10}
    )


def test_build_voice_session_record_includes_runtime_fields(tmp_path):
    """Collected record should expose added runtime metadata fields."""
    record = audio_stream_mod._build_voice_session_record(
        tmp_path / "session-a",
        {
            "created_at": "2026-05-11T08:00:00Z",
            "duration_sec": 1.25,
            "sample_rate": 16000,
            "input_format": "mediarecorder",
            "mime_type": "audio/webm",
            "voice_mode": "summary",
            "timings_ms": {"stt_ms": 12.0},
            "runtime": {"provider": "gemma4_audio"},
            "pipeline_id": "gemma4_audio_piper",
            "audio_runtime_provider": "gemma4_audio",
            "audio_runtime_model": "google/gemma-4-E2B-it",
            "audio_input_status": "verified",
            "fallback_reason": None,
            "native_audio_ms": 111.0,
            "runtime_log_path": "logs/gemma4_audio_service.log",
            "transcription": "piec razy piec",
            "response_text": "25",
        },
    )

    assert record["session_id"] == "session-a"
    assert record["voice_mode"] == "summary"
    assert record["runtime"] == {"provider": "gemma4_audio"}
    assert record["pipeline_id"] == "gemma4_audio_piper"
    assert record["audio_runtime_provider"] == "gemma4_audio"
    assert record["audio_runtime_model"] == "google/gemma-4-E2B-it"
    assert record["audio_input_status"] == "verified"
    assert record["runtime_log_path"] == "logs/gemma4_audio_service.log"
    assert record["transcription"] == "piec razy piec"


def test_build_voice_session_insights_payload_delegates_to_voice_metadata(monkeypatch):
    captured = {}

    def fake_build_voice_session_insights(**kwargs):
        captured.update(kwargs)
        return {"summary": "ok", "emotion_label": "curious"}

    monkeypatch.setattr(
        audio_stream_mod,
        "build_voice_session_insights",
        fake_build_voice_session_insights,
    )

    payload = audio_stream_mod._build_voice_session_insights_payload(
        transcript="ile to jest dwa razy dwa",
        response="dwa razy dwa to cztery",
        voice_mode="summary",
        pipeline_id="gemma4_audio_piper",
        reasoning_summary_enabled=True,
        emotion_detection_enabled=True,
        emotion_response_style_enabled=False,
        raw_thinking_available=True,
    )

    assert payload == {"summary": "ok", "emotion_label": "curious"}
    assert captured == {
        "transcript": "ile to jest dwa razy dwa",
        "response": "dwa razy dwa to cztery",
        "voice_mode": "summary",
        "pipeline_id": "gemma4_audio_piper",
        "reasoning_summary_enabled": True,
        "emotion_detection_enabled": True,
        "emotion_response_style_enabled": False,
        "raw_thinking_available": True,
    }


def test_create_voice_session_dir_uses_unique_names(monkeypatch, tmp_path):
    """Voice session directories should not collide for rapid consecutive calls."""
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    first = audio_stream_mod._create_voice_session_dir(17)
    second = audio_stream_mod._create_voice_session_dir(17)

    assert first.exists()
    assert second.exists()
    assert first != second
    assert first.parent == tmp_path
    assert second.parent == tmp_path


def test_create_voice_session_dir_retries_after_collision(monkeypatch, tmp_path):
    """Directory creation should retry on FileExistsError."""
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    original_mkdir = audio_stream_mod.Path.mkdir
    calls = {"count": 0}

    def flaky_mkdir(path_obj, parents=False, exist_ok=False):
        calls["count"] += 1
        if calls["count"] == 1:
            raise FileExistsError
        return original_mkdir(path_obj, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(audio_stream_mod.Path, "mkdir", flaky_mkdir)

    created = audio_stream_mod._create_voice_session_dir(18)

    assert created.exists()
    assert calls["count"] >= 2


def test_get_latest_voice_session_falls_back_to_filesystem(monkeypatch, tmp_path):
    """Handler should fall back to filesystem scan when no in-memory latest exists."""
    handler = _make_handler()
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)
    monkeypatch.setattr(
        audio_stream_mod,
        "collect_latest_voice_session_record",
        lambda _root: {"session_id": "from_fs"},
    )

    latest = handler.get_latest_voice_session()

    assert latest is not None
    assert latest["session_id"] == "from_fs"


def test_build_runtime_metadata_and_tts_sample_rate():
    """Runtime snapshot should surface STT/TTS model fields and sample rate."""
    handler = _make_handler()

    class DummyWhisper:
        model_size = "base"
        device = "cpu"
        compute_type = "int8"

    class DummyVoice:
        model_path = "/tmp/voice.onnx"
        is_fallback_mode = False
        output_sample_rate = 24000

    handler.audio_engine = MagicMock()
    handler.audio_engine.whisper = DummyWhisper()
    handler.audio_engine.voice = DummyVoice()

    operator_agent = MagicMock()
    operator_agent._resolve_chat_service_id.return_value = "local"

    runtime = handler._build_runtime_metadata(operator_agent)

    assert runtime["stt_model"] == "base"
    assert runtime["stt_device"] == "cpu"
    assert runtime["stt_compute_type"] == "int8"
    assert runtime["llm_service_id"] == "local"
    assert runtime["tts_model_path"] == "/tmp/voice.onnx"
    assert runtime["tts_fallback"] is False
    assert runtime["tts_sample_rate"] == 24000

    handler.audio_engine.voice.output_sample_rate = None
    assert handler._get_tts_sample_rate() == 22050


def test_gemma4_audio_helper_urls_and_selection(monkeypatch):
    """Gemma4 helper URLs should normalize /v1 origin and selected state."""
    handler = _make_handler()

    monkeypatch.setattr(
        audio_stream_mod.SETTINGS,
        "GEMMA4_AUDIO_ENDPOINT",
        "http://localhost:8014/v1/",
        raising=False,
    )
    monkeypatch.setattr(
        audio_stream_mod.SETTINGS, "GEMMA4_AUDIO_ENABLED", True, raising=False
    )
    monkeypatch.setattr(
        audio_stream_mod.SETTINGS, "ACTIVE_LLM_SERVER", "gemma4_audio", raising=False
    )

    assert handler._gemma4_audio_service_origin() == "http://localhost:8014"
    assert handler._gemma4_audio_respond_url() == "http://localhost:8014/v1/respond"
    assert handler._gemma4_audio_health_url() == "http://localhost:8014/health"
    assert handler._gemma4_audio_runtime_selected() is True

    monkeypatch.setattr(
        audio_stream_mod.SETTINGS, "ACTIVE_LLM_SERVER", "ollama", raising=False
    )
    assert handler._gemma4_audio_runtime_selected() is False


@pytest.mark.asyncio
async def test_gemma4_audio_health_ok_handles_success_and_failures(monkeypatch):
    """Health check should accept ok/warming and reject invalid responses."""
    handler = _make_handler()
    monkeypatch.setattr(
        handler, "_gemma4_audio_health_url", lambda: "http://runtime/health"
    )

    responses = iter(
        [
            SimpleNamespace(status_code=200, json=lambda: {"status": "warming"}),
            SimpleNamespace(status_code=503, json=lambda: {"status": "down"}),
        ]
    )

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url):
            return next(responses)

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _AsyncClient)

    assert await handler._gemma4_audio_health_ok() is True
    assert await handler._gemma4_audio_health_ok() is False

    monkeypatch.setattr(handler, "_gemma4_audio_health_url", lambda: "")
    assert await handler._gemma4_audio_health_ok() is False


@pytest.mark.asyncio
async def test_invoke_gemma4_audio_runtime_builds_request_and_validates_response(
    monkeypatch, tmp_path
):
    """Gemma4 runtime request should send multipart payload and parse text result."""
    handler = _make_handler()
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(
        audio_stream_mod.SETTINGS,
        "SIMPLE_MODE_SYSTEM_PROMPT",
        "system prompt",
        raising=False,
    )
    monkeypatch.setattr(
        audio_stream_mod.SETTINGS,
        "GEMMA4_AUDIO_MAX_NEW_TOKENS",
        77,
        raising=False,
    )
    monkeypatch.setattr(
        audio_stream_mod.SETTINGS,
        "GEMMA4_AUDIO_MODEL_ID",
        "google/gemma-4-E2B-it",
        raising=False,
    )
    monkeypatch.setattr(
        handler, "_gemma4_audio_respond_url", lambda: "http://runtime/v1/respond"
    )
    monkeypatch.setattr(
        audio_stream_mod.Path,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("sync Path.open() should not be used")
        ),
    )

    calls = {}

    class _AsyncBinaryFile:
        def __init__(self, path: str):
            self.path = path

    class _AsyncOpenContext:
        def __init__(self, path, mode):
            self.path = path
            self.mode = mode

        async def __aenter__(self):
            return _AsyncBinaryFile(str(self.path))

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_open_file(path, mode):
        calls["open_file"] = (str(path), mode)
        return _AsyncOpenContext(path, mode)

    monkeypatch.setattr(audio_stream_mod.anyio, "open_file", _fake_open_file)

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, files=None):
            calls["url"] = url
            calls["data"] = data
            calls["files"] = files
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "text": "25",
                    "model": "google/gemma-4-E2B-it",
                    "duration_ms": 123,
                },
                text="",
            )

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _AsyncClient)

    result = await handler._invoke_gemma4_audio_runtime(wav_path, 17)

    assert result["text"] == "25"
    assert result["response_text"] == "25"
    assert result["connection_id"] == 17
    assert calls["open_file"] == (str(wav_path), "rb")
    assert calls["url"] == "http://runtime/v1/respond"
    request_payload = json.loads(calls["data"]["request"])
    assert request_payload["task"] == "question"
    assert request_payload["max_new_tokens"] == 77
    assert request_payload["messages"][0]["content"][0] == {
        "type": "audio",
        "path": "recording.wav",
    }
    assert calls["files"]["audio"][0] == "recording.wav"


@pytest.mark.asyncio
async def test_invoke_gemma4_audio_runtime_raises_for_http_and_empty_text(
    monkeypatch, tmp_path
):
    """Gemma4 runtime should reject HTTP errors and empty text payloads."""
    handler = _make_handler()
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")
    monkeypatch.setattr(
        handler, "_gemma4_audio_respond_url", lambda: "http://runtime/v1/respond"
    )

    class _HttpErrorClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, files=None):
            return SimpleNamespace(status_code=503, json=lambda: {}, text="down")

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _HttpErrorClient)

    with pytest.raises(RuntimeError, match="Gemma4 audio runtime HTTP 503: down"):
        await handler._invoke_gemma4_audio_runtime(wav_path, 7)

    class _EmptyTextClient(_HttpErrorClient):
        async def post(self, url, data=None, files=None):
            return SimpleNamespace(status_code=200, json=lambda: {"text": ""}, text="")

    monkeypatch.setattr(audio_stream_mod.httpx, "AsyncClient", _EmptyTextClient)

    with pytest.raises(RuntimeError, match="returned an empty response"):
        await handler._invoke_gemma4_audio_runtime(wav_path, 8)


@pytest.mark.asyncio
async def test_process_native_gemma4_audio_pipeline_handles_selection_and_fallbacks(
    monkeypatch, tmp_path
):
    """Native pipeline should short-circuit cleanly before whisper fallback."""
    handler = _make_handler()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    wav_path = session_dir / "recording.wav"
    wav_path.write_bytes(b"wav")
    timings_ms = {}

    monkeypatch.setattr(handler, "_gemma4_audio_runtime_selected", lambda: False)
    assert (
        await handler._process_native_gemma4_audio_pipeline(
            1, session_dir, wav_path, timings_ms, 0.0, MagicMock()
        )
        is False
    )

    handler.audio_engine = MagicMock()
    monkeypatch.setattr(handler, "_gemma4_audio_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler,
        "_gemma4_audio_runtime_snapshot",
        lambda: {"audio_runtime_provider": "gemma4_audio"},
    )
    monkeypatch.setattr(
        handler, "_gemma4_audio_health_ok", AsyncMock(return_value=False)
    )
    update_calls = []
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: update_calls.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _agent: {"llm": "x"})
    monkeypatch.setattr(handler, "_connection_voice_mode", lambda _cid: "standard")

    assert (
        await handler._process_native_gemma4_audio_pipeline(
            2, session_dir, wav_path, timings_ms, 0.0, MagicMock()
        )
        is False
    )
    assert update_calls[-1]["pipeline_id"] == "whisper_llm_piper"
    assert update_calls[-1]["fallback_reason"] == "gemma4_audio health check failed"


@pytest.mark.asyncio
async def test_process_native_gemma4_audio_pipeline_success(monkeypatch, tmp_path):
    """Native pipeline success should update metadata and send TTS response."""
    handler = _make_handler()
    handler.audio_engine = MagicMock()
    handler.audio_engine.speak = AsyncMock(
        return_value=np.array([1, 2], dtype=np.int16)
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    wav_path = session_dir / "recording.wav"
    wav_path.write_bytes(b"wav")
    timings_ms = {}
    sent_json = []
    sent_audio = []
    update_calls = []

    monkeypatch.setattr(handler, "_gemma4_audio_runtime_selected", lambda: True)
    monkeypatch.setattr(
        handler,
        "_gemma4_audio_runtime_snapshot",
        lambda: {"audio_runtime_provider": "gemma4_audio"},
    )
    monkeypatch.setattr(
        handler, "_gemma4_audio_health_ok", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handler,
        "_invoke_gemma4_audio_runtime",
        AsyncMock(return_value={"text": "piec razy piec", "response_text": "25"}),
    )
    monkeypatch.setattr(
        handler,
        "_update_voice_session_metadata",
        lambda _dir, payload: update_calls.append(payload),
    )
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda _agent: {"llm": "x"})
    monkeypatch.setattr(handler, "_connection_voice_mode", lambda _cid: "summary")
    monkeypatch.setattr(
        handler,
        "_send_json",
        AsyncMock(side_effect=lambda cid, payload: sent_json.append(payload)),
    )
    monkeypatch.setattr(
        handler,
        "_send_audio",
        AsyncMock(side_effect=lambda cid, audio: sent_audio.append(audio)),
    )
    monkeypatch.setattr(handler, "_elapsed_ms", lambda _started: 12.5)

    result = await handler._process_native_gemma4_audio_pipeline(
        3, session_dir, wav_path, timings_ms, 0.0, MagicMock()
    )

    assert result is True
    assert sent_json[0] == {"type": "processing", "status": "native_audio"}
    assert sent_json[1]["type"] == "transcription"
    assert sent_json[1]["text"] == "piec razy piec"
    assert sent_json[2] == {"type": "response_text", "text": "25"}
    assert sent_json[-1] == {"type": "complete"}
    assert len(sent_audio) == 1
    assert update_calls[0]["pipeline_id"] == "gemma4_audio_piper"
    assert update_calls[0]["transcription"] == "piec razy piec"
    assert update_calls[1]["pipeline_id"] == "gemma4_audio_piper"


# ---------------------------------------------------------------------------
# _process_audio_buffer – no audio engine path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_audio_buffer_no_engine_sends_error(monkeypatch):
    """Without an audio engine _process_audio_buffer sends an error message."""
    handler = _make_handler()  # audio_engine=None
    cid = 30
    _add_connection(handler, cid)

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)

    audio_buffer = [np.array([1, 2, 3], dtype=np.int16)]
    await handler._process_audio_buffer(cid, audio_buffer, operator_agent=None)

    types = [m.get("type") for m in sent]
    assert "error" in types or "processing" in types


@pytest.mark.asyncio
async def test_process_encoded_audio_buffer_full_flow(monkeypatch, tmp_path):
    """Encoded pipeline should persist, transcribe, answer and emit audio."""
    handler = _make_handler()
    cid = 31
    _add_connection(handler, cid)
    handler.active_connections[cid]["voice_mode"] = "summary"
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    session_dir = tmp_path / "20260509_000000_31"
    session_dir.mkdir(parents=True)
    (session_dir / "recording.wav").write_bytes(b"RIFFTEST")

    audio_engine = MagicMock()
    audio_engine.transcribe_file = MagicMock(return_value="co to jest?")
    audio_engine.speak = AsyncMock(return_value=np.array([10, 11], dtype=np.int16))
    handler.audio_engine = audio_engine

    operator_agent = MagicMock()
    operator_agent.process = AsyncMock(return_value="To jest test.")
    operator_agent._resolve_chat_service_id.return_value = "chat"

    sent = []
    audio_sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    async def fake_send_audio(_cid, audio_data):
        audio_sent.append(audio_data)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    monkeypatch.setattr(handler, "_send_audio", fake_send_audio)
    monkeypatch.setattr(
        handler, "_persist_encoded_voice_session", lambda *a, **k: session_dir
    )
    monkeypatch.setattr(
        handler,
        "_load_wav_int16",
        lambda _path: (np.array([100, 200], dtype=np.int16), 16000),
    )
    monkeypatch.setattr(
        handler,
        "_normalize_recorded_audio",
        lambda audio: (
            audio,
            {
                "gain_applied": 1.0,
                "peak_before_normalization": 0.1,
                "dc_offset": 0.0,
            },
        ),
    )
    monkeypatch.setattr(handler, "_write_wav", lambda *a, **k: None)
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

    await handler._process_encoded_audio_buffer(
        cid,
        [b"encoded-chunk-a", b"encoded-chunk-b"],
        operator_agent=operator_agent,
        mime_type="audio/webm;codecs=opus",
    )

    assert any(msg.get("status") == "decode" for msg in sent)
    assert any(msg.get("status") == "stt" for msg in sent)
    assert any(msg.get("status") == "thinking" for msg in sent)
    assert any(msg.get("status") == "tts" for msg in sent)
    assert any(msg.get("type") == "complete" for msg in sent)
    assert audio_sent
    operator_agent.process.assert_awaited_once()
    audio_engine.speak.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_encoded_audio_buffer_without_audio_engine_sends_error(
    monkeypatch, tmp_path
):
    """Encoded pipeline should fail cleanly when the engine is missing."""
    handler = _make_handler()
    cid = 32
    _add_connection(handler, cid)
    monkeypatch.setattr(audio_stream_mod, "VOICE_SESSION_ROOT", tmp_path)

    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True)
    (session_dir / "recording.wav").write_bytes(b"RIFFTEST")

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    monkeypatch.setattr(
        handler, "_persist_encoded_voice_session", lambda *a, **k: session_dir
    )
    monkeypatch.setattr(
        handler,
        "_load_wav_int16",
        lambda _path: (np.array([1, 2], dtype=np.int16), 16000),
    )
    monkeypatch.setattr(
        handler,
        "_normalize_recorded_audio",
        lambda audio: (audio, {"gain_applied": 1.0, "peak_before_normalization": 0.1}),
    )
    monkeypatch.setattr(handler, "_write_wav", lambda *a, **k: None)

    await handler._process_encoded_audio_buffer(
        cid,
        [b"encoded-chunk"],
        operator_agent=None,
        mime_type="audio/webm;codecs=opus",
    )

    assert any(msg.get("type") == "error" for msg in sent)


@pytest.mark.asyncio
async def test_handle_audio_data_auto_finalizes_on_silence(monkeypatch):
    """Silent chunks should auto-finalize a recording even without stop_recording."""
    handler = _make_handler(vad_threshold=0.1, silence_duration=0.0)
    cid = 77
    _add_connection(handler, cid, is_speaking=True)
    handler.active_connections[cid]["audio_buffer"] = [np.ones(32, dtype=np.int16)]
    handler.active_connections[cid]["speech_detected"] = True

    processed = []

    async def fake_process(
        connection_id, audio_buffer, operator_agent, sample_rate=16000
    ):
        processed.append(
            (connection_id, len(audio_buffer), operator_agent, sample_rate)
        )

    monkeypatch.setattr(handler, "_process_audio_buffer", fake_process)

    handler._handle_audio_data(cid, np.zeros(32, dtype=np.int16), operator_agent=None)
    await asyncio.sleep(0.05)

    assert processed
    assert handler.active_connections[cid]["is_speaking"] is False
    assert handler.active_connections[cid]["audio_buffer"] == []


@pytest.mark.asyncio
async def test_schedule_silence_finalize_reraises_cancelled_error(monkeypatch):
    """Cancelled silence-finalize tasks should clean up and propagate cancellation."""
    handler = _make_handler(vad_threshold=0.1, silence_duration=60.0)
    cid = 78
    _add_connection(handler, cid, is_speaking=True)
    handler.active_connections[cid]["audio_buffer"] = [np.ones(32, dtype=np.int16)]
    handler.active_connections[cid]["speech_detected"] = True

    handler._schedule_silence_finalize(cid, operator_agent=None, sample_rate=16000)
    task = handler.active_connections[cid]["silence_finalize_task"]
    assert isinstance(task, asyncio.Task)

    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert handler.active_connections[cid]["silence_finalize_task"] is None


@pytest.mark.asyncio
async def test_process_audio_buffer_runs_normal_flow(monkeypatch, tmp_path):
    handler = _make_handler()
    cid = 81
    _add_connection(handler, cid, is_speaking=True)
    handler.audio_engine = MagicMock()
    handler.audio_engine.listen = AsyncMock(return_value="co to jest?")
    handler.audio_engine.speak = AsyncMock(
        return_value=np.array([1, 2], dtype=np.int16)
    )

    class DummyAgent:
        def _resolve_chat_service_id(self):
            return "chat"

        async def process(self, text, mode="standard"):
            return f"odpowiedź: {text}:{mode}"

    sent = []

    async def fake_send_json(_cid, payload):
        sent.append(payload)

    monkeypatch.setattr(handler, "_send_json", fake_send_json)
    send_audio = AsyncMock()
    monkeypatch.setattr(handler, "_send_audio", send_audio)
    monkeypatch.setattr(handler, "_persist_voice_session", lambda *a, **k: tmp_path)
    monkeypatch.setattr(handler, "_update_voice_session_metadata", lambda *a, **k: None)
    monkeypatch.setattr(handler, "_build_runtime_metadata", lambda *_a, **_k: {"rt": 1})

    await handler._process_audio_buffer(
        cid,
        [np.array([1, 2, 3], dtype=np.int16)],
        DummyAgent(),
        sample_rate=16000,
    )

    assert any(msg.get("status") == "stt" for msg in sent)
    assert any(msg.get("type") == "transcription" for msg in sent)
    assert any(msg.get("status") == "thinking" for msg in sent)
    assert any(msg.get("status") == "tts" for msg in sent)
    assert any(msg.get("type") == "complete" for msg in sent)
    assert send_audio.await_count == 1
