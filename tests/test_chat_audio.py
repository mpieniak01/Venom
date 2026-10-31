"""Audio never generates an LLM turn and cancellation drains native work."""

import asyncio
import io
import wave
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from venom_core.api.routes.chat_audio import router
from venom_core.services import chat_audio


@pytest_asyncio.fixture
async def rig(monkeypatch):
    engine = SimpleNamespace(
        transcribe_checked=AsyncMock(return_value="hello"),
        speak=AsyncMock(return_value=b"\x01\x00" * 100),
        voice=SimpleNamespace(output_sample_rate=22050),
    )
    admission = SimpleNamespace(operation=Mock(side_effect=lambda **_: nullcontext()))
    monkeypatch.setattr(chat_audio, "get_runtime_admission", lambda: admission)
    app = FastAPI()
    app.include_router(router)
    app.state.audio_engine = engine
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://localhost",
    ) as client:
        yield client, engine, admission


@pytest.mark.asyncio
async def test_transcription_uses_existing_engine_and_preserves_session_language(rig):
    client, engine, admission = rig
    response = await client.post(
        "/api/v1/chat/audio/transcribe?session_id=one&sample_rate=16000&language=de",
        content=b"\x01\x00" * 80,
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "session_id": "one",
        "text": "hello",
        "pipeline": "host_stt",
    }
    args, kwargs = engine.transcribe_checked.await_args
    assert args[0].shape == (80,)
    assert kwargs == {"language": "de", "sample_rate": 16000}
    engine.speak.assert_not_awaited()
    admission.operation.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,content_type,status",
    [
        (b"", "application/octet-stream", 422),
        (b"x", "application/octet-stream", 422),
        (b"valid", "audio/webm", 415),
    ],
)
async def test_invalid_audio_never_enters_a_model(rig, body, content_type, status):
    client, engine, _ = rig
    response = await client.post(
        "/api/v1/chat/audio/transcribe?session_id=one",
        content=body,
        headers={"content-type": content_type},
    )
    assert response.status_code == status
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
async def test_pcm_duration_limit_is_checked_before_inference(rig):
    client, engine, _ = rig
    response = await client.post(
        "/api/v1/chat/audio/transcribe?session_id=one&sample_rate=8000",
        content=b"\x00" * (8000 * 60 * 2 + 2),
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 413
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
async def test_speech_is_pcm_wav_using_host_quality_without_transcription(rig):
    client, engine, _ = rig
    response = await client.post(
        "/api/v1/chat/audio/speak", json={"session_id": "one", "text": "answer"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    with wave.open(io.BytesIO(response.content), "rb") as audio:
        assert (
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getframerate(),
            audio.getnframes(),
        ) == (1, 2, 22050, 100)
    engine.speak.assert_awaited_once_with("answer")
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_tts_and_cross_site_do_not_enter_audio_engine(rig):
    client, engine, _ = rig
    response = await client.post(
        "/api/v1/chat/audio/speak", json={"session_id": "one", "text": " "}
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/v1/chat/audio/speak",
        json={"session_id": "one", "text": "answer"},
        headers={"origin": "https://foreign.invalid", "sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403
    engine.speak.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_engine_returns_explicit_failure(rig):
    client, engine, _ = rig
    engine.speak.return_value = None
    response = await client.post(
        "/api/v1/chat/audio/speak", json={"session_id": "one", "text": "answer"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "audio_synthesis_failed"


@pytest.mark.asyncio
async def test_cancel_keeps_admission_until_real_native_completion(monkeypatch):
    entered = asyncio.Event()
    finish = asyncio.Event()
    events = []

    class Operation:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *_):
            events.append("exit")

    admission = SimpleNamespace(operation=lambda **_: Operation())
    monkeypatch.setattr(chat_audio, "get_runtime_admission", lambda: admission)

    async def native():
        entered.set()
        await finish.wait()
        events.append("native_done")
        return "ok"

    waiter = asyncio.create_task(chat_audio.complete_audio_work(native))
    await entered.wait()
    waiter.cancel()
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.sleep(0)
    assert not waiter.done()
    assert events == ["enter"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert events == ["enter", "native_done", "exit"]


@pytest.mark.asyncio
async def test_tts_fallback_is_not_reported_as_working_voice(rig):
    client, engine, _ = rig
    engine.voice.is_fallback_mode = True
    response = await client.post(
        "/api/v1/chat/audio/speak", json={"session_id": "one", "text": "answer"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "audio_synthesis_failed"


@pytest.mark.asyncio
async def test_native_transcription_failure_is_not_reported_as_silence(rig):
    client, engine, _ = rig
    engine.transcribe_checked.side_effect = RuntimeError("native failure")
    response = await client.post(
        "/api/v1/chat/audio/transcribe?session_id=one",
        content=b"\x01\x00",
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "audio_transcription_failed"


@pytest.mark.asyncio
async def test_missing_host_engine_has_readiness_error(rig):
    client, _, _ = rig
    client._transport.app.state.audio_engine = None
    response = await client.post(
        "/api/v1/chat/audio/speak", json={"session_id": "one", "text": "answer"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "audio_not_ready"
