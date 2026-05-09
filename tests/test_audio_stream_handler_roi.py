import asyncio
import base64
import json
import os
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
    await handler._handle_audio_data(cid, b"encoded-audio", operator_agent=None)
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

    await handler._handle_audio_data(
        cid, np.zeros(32, dtype=np.int16), operator_agent=None
    )
    await asyncio.sleep(0.05)

    assert processed
    assert handler.active_connections[cid]["is_speaking"] is False
    assert handler.active_connections[cid]["audio_buffer"] == []
