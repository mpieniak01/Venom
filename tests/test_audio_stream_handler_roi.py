import asyncio
import json

import numpy as np
import pytest

from venom_core.api.audio_stream import AudioStreamHandler


@pytest.mark.asyncio
async def test_handle_control_message_start_stop(monkeypatch):
    handler = AudioStreamHandler(audio_engine=None)
    connection_id = 123
    handler.active_connections[connection_id] = {
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
        connection_id, json.dumps({"command": "start_recording"}), None
    )
    assert handler.active_connections[connection_id]["is_speaking"] is True
    assert sent[-1]["type"] == "recording_started"
    handler.active_connections[connection_id]["audio_buffer"].append(
        np.array([1, 2, 3], dtype=np.int16)
    )

    await handler._handle_control_message(
        connection_id, json.dumps({"command": "stop_recording"}), None
    )
    assert processed


def test_detect_voice_activity_threshold():
    handler = AudioStreamHandler(vad_threshold=0.05)
    silent = np.zeros(512, dtype=np.int16)
    loud = np.ones(512, dtype=np.int16) * 5000

    assert bool(handler._detect_voice_activity(silent)) is False
    assert bool(handler._detect_voice_activity(loud)) is True
