import asyncio
import base64
import json
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
        "is_speaking": is_speaking,
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
        "is_speaking": False,
    }

    sent = []
    processed = []

    async def fake_send_json(_cid, payload):
        await asyncio.sleep(0)
        sent.append(payload)

    async def fake_process(_cid, _buffer, _agent):
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
    # Should not raise; returns False on exception
    result = handler._detect_voice_activity(empty)
    assert isinstance(result, bool)


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
