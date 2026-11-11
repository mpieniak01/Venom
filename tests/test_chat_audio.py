"""Audio never generates an LLM turn and cancellation drains native work."""

import asyncio
import base64
import io
import json
import wave
from contextlib import asynccontextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from PIL import Image

from venom_core.api import omni_native_voice
from venom_core.api.dependencies import get_session_store
from venom_core.api.studio_routes import include_studio_routes
from venom_core.services import (
    chat_audio,
    omni_native_dialogue,
    omni_pilot,
    omni_pilot_screen,
)
from venom_core.services.session_store import SessionStore


@pytest_asyncio.fixture
async def rig(monkeypatch, tmp_path):
    engine = SimpleNamespace(
        transcribe_checked=AsyncMock(return_value="hello"),
        speak=AsyncMock(return_value=b"\x01\x00" * 100),
        voice=SimpleNamespace(output_sample_rate=22050),
    )
    admission = SimpleNamespace(operation=Mock(side_effect=lambda **_: nullcontext()))
    monkeypatch.setattr(chat_audio, "get_runtime_admission", lambda: admission)
    app = FastAPI()
    include_studio_routes(app)
    app.state.audio_engine = engine
    store = SessionStore(str(tmp_path / "history.json"))
    app.dependency_overrides[get_session_store] = lambda: store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://localhost",
    ) as client:
        yield client, engine, admission


def _pilot_image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("encoded", [False, True])
async def test_pilot_retains_and_replaces_the_session_screen_for_followups(
    rig, monkeypatch, encoded
):
    """Resolve later speech against the last validated screen in the same session."""
    client, engine, _ = rig
    runtime = SimpleNamespace(
        endpoint="http://127.0.0.1:11434", model_name="lfm3-omni:2b"
    )
    monkeypatch.setattr(omni_pilot, "active_pilot_runtime", lambda: runtime)
    monkeypatch.setattr(
        omni_pilot,
        "require_local_capability",
        AsyncMock(return_value={"capabilities": ["audio", "vision", "tools"]}),
    )
    recognize = AsyncMock(
        side_effect=[
            "Co zrobić z komunikatem na dole?",
            "A jeśli komunikat wróci?",
            "Chodziło mi o komunikat na górze.",
            "Co zrobić z komunikatem po lewej?",
            "A po prawej?",
        ]
    )
    monkeypatch.setattr(omni_pilot, "transcribe_pcm_audio", recognize)
    request_payloads = []
    first_screen = {
        "layout": "vertical",
        "cards": [
            {"code": "VEN-413", "color": "brown"},
            {"code": "VEN-401", "color": "red"},
        ],
    }
    next_screen = {
        "layout": "horizontal",
        "cards": [
            {"code": "VEN-503", "color": "blue"},
            {"code": "VEN-207", "color": "red"},
        ],
    }
    messages = iter(
        [
            {"content": json.dumps(first_screen)},
            {"content": "Najpierw otwórz ponownie sesję."},
            {"content": json.dumps({"action": "previous_source", "code": "VEN-401"})},
            {"content": "Sprawdź ustawienia sesji i spróbuj zalogować się ponownie."},
            {"content": "Najpierw wybierz mniejszy obraz."},
            {"content": json.dumps(next_screen)},
            {"content": "Najpierw odczekaj 30 sekund."},
            {"content": "Najpierw sprawdź uprawnienie mikrofonu w przeglądarce."},
        ]
    )

    async def post(_url, *, json, **_kwargs):
        request_payloads.append(deepcopy(json))
        return httpx.Response(200, json={"done": True, "message": next(messages)})

    @asynccontextmanager
    async def http(**_kwargs):
        yield SimpleNamespace(apost=post)

    monkeypatch.setattr(omni_pilot, "TrafficControlledHttpClient", http)
    data = {"session_id": "pilot", "sample_rate": "16000", "language": "pl"}
    image = _pilot_image()
    pcm = b"\x00\x10" * 100
    files = {"audio": ("recording.pcm", pcm)}
    if encoded:

        def decode(command, **_options):
            assert command[command.index("-f") + 1] == "matroska"
            assert command[command.index("-protocol_whitelist") + 1] == "file"
            assert command[command.index("-t") + 1] == "61"
            assert Path(command[command.index("-i") + 1]).read_bytes() == b"webm"
            with wave.open(command[-1], "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(chat_audio.subprocess, "run", decode)
        files = {"audio": ("recording.webm", b"webm", "audio/webm;codecs=opus")}
    result = await client.post(
        "/api/v1/chat/audio/multimodal-turn",
        data=data,
        files={**files, "image": ("capture.png", image)},
    )
    assert result.status_code == 200
    source = result.json()["sources"][0]
    assert "VEN-401" in source
    assert result.json()["text"].startswith("Najpierw otwórz ponownie sesję.")
    assert request_payloads[0]["format"] == omni_pilot_screen.SCREEN_SCHEMA
    assert request_payloads[0]["messages"][-1]["images"] == [
        base64.b64encode(image).decode("ascii")
    ]
    recognize.assert_awaited_once_with(
        runtime.endpoint, runtime.model_name, pcm, 16000, "pl"
    )
    assert request_payloads[1]["messages"][-1] == {
        "role": "user",
        "content": "Co zrobić z komunikatem na dole?",
    }

    followup = await client.post(
        "/api/v1/chat/audio/multimodal-turn", data=data, files=files
    )
    assert followup.status_code == 200
    assert followup.json()["sources"] == [source]
    assert followup.json()["text"] == (
        "Sprawdź ustawienia sesji i spróbuj zalogować się ponownie."
    )
    assert request_payloads[3]["messages"][1:] == request_payloads[2]["messages"][1:]
    assert not any(
        "Źródło:" in message["content"]
        for message in request_payloads[3]["messages"][1:]
    )

    correction = await client.post(
        "/api/v1/chat/audio/multimodal-turn", data=data, files=files
    )
    assert correction.status_code == 200
    assert correction.json()["sources"][0].startswith("VEN-413")
    source_message, question = request_payloads[4]["messages"]
    assert "VEN-413" in source_message["content"]
    assert "VEN-401" not in source_message["content"]
    assert question == {"role": "user", "content": "Chodziło mi o komunikat na górze."}

    changed_screen = await client.post(
        "/api/v1/chat/audio/multimodal-turn",
        data=data,
        files={**files, "image": ("next-capture.png", image)},
    )
    assert changed_screen.status_code == 200
    assert changed_screen.json()["sources"][0].startswith("VEN-503")
    replacement_followup = await client.post(
        "/api/v1/chat/audio/multimodal-turn", data=data, files=files
    )
    assert replacement_followup.status_code == 200
    assert replacement_followup.json()["sources"][0].startswith("VEN-207")

    other_session = await client.post(
        "/api/v1/chat/audio/multimodal-turn",
        data={**data, "session_id": "another"},
        files=files,
    )
    assert other_session.status_code == 200
    assert other_session.json()["sources"] == []
    assert recognize.await_count == 5
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observation, status, choice",
    [
        (
            {"status": "online", "models": ["lfm3-omni:2b"]},
            "loaded",
            "read_local_omni_status",
        ),
        ({"status": "online", "models": []}, "not_loaded", "read_local_omni_status"),
        (
            {"status": "unverified", "models": None},
            "unavailable",
            "read_local_omni_status",
        ),
        (None, None, "clarify"),
    ],
)
async def test_pilot_runtime_read_preserves_prior_document(
    rig, monkeypatch, observation, status, choice
):
    client, _, _ = rig
    runtime = SimpleNamespace(
        endpoint="http://127.0.0.1:11434", model_name="lfm3-omni:2b"
    )
    monkeypatch.setattr(omni_pilot, "active_pilot_runtime", lambda: runtime)
    monkeypatch.setattr(
        omni_pilot,
        "require_local_capability",
        AsyncMock(return_value={"capabilities": ["vision"]}),
    )
    question = "Czy lokalny model Omni jest załadowany?"
    monkeypatch.setattr(
        omni_pilot,
        "transcribe_pcm_audio",
        AsyncMock(
            side_effect=[
                "Sprawdź komunikat VEN-401.",
                question,
                "A co, jeśli poprzedni komunikat wróci?",
            ]
        ),
    )
    inventory = AsyncMock(return_value={"ollama": observation})
    monkeypatch.setattr(omni_pilot, "runtime_inventory", inventory)
    replies = [
        {
            "content": json.dumps(
                {"layout": "single", "cards": [{"code": "VEN-401", "color": "red"}]}
            )
        },
        {"content": "Otwórz ponownie sesję."},
        {"content": json.dumps({"action": choice})},
    ]
    if status in {"loaded", "not_loaded"}:
        # Invalid model output cannot turn a read into an invented confirmation.
        replies.append({"content": '"Usługa została ponownie uruchomiona."'})
    replies.extend(
        [
            {"content": '{"action":"previous_source","code":"VEN-401"}'},
            {"content": "Sprawdź ustawienia sesji."},
        ]
    )
    model = AsyncMock(side_effect=replies)
    monkeypatch.setattr(omni_pilot, "_chat", model)
    data = {"session_id": "stage8", "sample_rate": "16000", "language": "pl"}
    audio = {"audio": ("voice.pcm", b"\x00\x10" * 100)}
    url = "/api/v1/chat/audio/multimodal-turn"
    document = await client.post(
        url, data=data, files={**audio, "image": ("camera.jpg", _pilot_image())}
    )
    assert document.status_code == 200
    result = await client.post(url, data=data, files=audio)
    assert result.status_code == 200
    if status is None:
        inventory.assert_not_awaited()
        assert result.json()["text"].startswith("Czy mam sprawdzić")
    else:
        inventory.assert_awaited_once_with({"ollama": runtime.endpoint})
        if status == "unavailable":
            assert result.json()["text"].startswith("Nie udało się odczytać")
        else:
            assert result.json()["text"] == omni_pilot._RUNTIME_REPLIES[status][0]
    assert result.json()["sources"] == (
        [omni_pilot.RUNTIME_SOURCE] if status in {"loaded", "not_loaded"} else []
    )

    silence = await client.post(
        url, data=data, files={"audio": ("silence.pcm", bytes(3200))}
    )
    assert silence.status_code == 200
    assert silence.json()["no_speech"] is True
    followup = await client.post(url, data=data, files=audio)
    assert followup.status_code == 200
    assert followup.json()["sources"] == document.json()["sources"]
    assert {"role": "user", "content": question} in model.await_args_list[-2].args[3]


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Co zrobić z drugim komunikatem?", (True, "VEN-401")),
        ("Który jest na górze?", (True, "VEN-413")),
        ("Sprawdź czerwony komunikat.", (True, None)),
        ("Sprawdź niebieski komunikat.", (True, None)),
        ("Sprawdź czerwony i zielony komunikat.", (True, None)),
        ("Sprawdź komunikat z prawej strony.", (True, None)),
        ("Sprawdź ten komunikat.", (False, None)),
        ("Wyjaśnij błąd przesyłania obrazu.", (True, "VEN-413")),
        ("Sprawdź kod VN503.", (True, "VEN-503")),
    ],
)
def test_pilot_resolves_only_an_unambiguous_screen_reference(question, expected):
    screen = omni_pilot_screen.parse_screen(
        {
            "layout": "vertical",
            "cards": [
                {"code": "VEN-413", "color": "red"},
                {"code": "VEN-401", "color": "red"},
            ],
        }
    )
    documents = json.loads(omni_pilot.DOCUMENTATION.read_text())
    assert omni_pilot_screen.resolve_reference(question, screen, documents) == expected


@pytest.mark.parametrize(
    "inventory",
    [
        {"layout": "diagonal", "cards": []},
        {"layout": "single", "cards": []},
        {"layout": "vertical", "cards": [None, {"code": "VEN-401", "color": "red"}]},
        {"layout": "single", "cards": [{"code": "../secret", "color": "red"}]},
        {"layout": "single", "cards": [{"code": "VEN-401", "color": "infrared"}]},
    ],
)
def test_pilot_rejects_a_malformed_screen_inventory(inventory):
    assert omni_pilot_screen.parse_screen(inventory) is None


def test_pilot_does_not_reuse_an_old_inventory_after_a_screen_reset():
    history = [
        {
            "mode": "omni_pilot",
            "omni_pilot_screen": {
                "layout": "single",
                "cards": [{"code": "VEN-401", "color": "red"}],
            },
        },
        {"mode": "omni_pilot", "omni_pilot_screen": None},
    ]
    assert omni_pilot_screen.previous_screen(history) is None


@pytest.mark.parametrize(
    "content,previous,expected",
    [
        ("invalid JSON", "VEN-401", None),
        ('{"action":"lookup_pilot_documentation","code":"../secrets"}', None, None),
        ('{"action":"lookup_pilot_documentation","code":"VEN-４０１"}', None, None),
        (
            '{"action":"lookup_pilot_documentation","code":"VEN-401","path":"/tmp"}',
            None,
            None,
        ),
        ('{"action":"shell","code":"VEN-401"}', None, None),
        ('{"action":"clarify","code":""}', "VEN-401", None),
        ('{"action":"previous_source","code":""}', None, None),
        ('{"action":"previous_source","code":""}', "VEN-401", "VEN-401"),
        ('{"action":"previous_source","code":"VEN-401"}', "VEN-401", "VEN-401"),
        ('{"action":"previous_source","code":"VEN-413"}', "VEN-401", None),
    ],
)
def test_pilot_selection_can_only_dispatch_a_valid_document_lookup(
    content, previous, expected
):
    """Reject arbitrary actions and malformed documentation codes."""
    documents = json.loads(omni_pilot.DOCUMENTATION.read_text())
    assert (
        omni_pilot._selected_code({"content": content}, previous, documents) == expected
    )


def test_pilot_exact_title_does_not_resolve_when_two_entries_match():
    """A duplicate label must ask for clarification instead of choosing a source."""
    documents = {
        "VEN-401": {"title": "VEN-401 · Sesja wygasła"},
        "VEN-999": {"title": "VEN-999 · Sesja wygasła"},
    }
    content = json.dumps({"action": omni_pilot.TOOL_NAME, "code": "Sesja wygasła"})
    assert omni_pilot._selected_code({"content": content}, None, documents) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "invalid_image",
        "missing_image",
        "bad_type",
        "bad_media",
        "decode_failed",
        "empty_recording",
        "decoder_unavailable",
    ],
)
async def test_pilot_rejects_unusable_media_before_inference(rig, monkeypatch, error):
    """Return validation errors or a clarification without calling the model."""
    client, _, _ = rig
    runtime = SimpleNamespace(
        endpoint="http://127.0.0.1:11434", model_name="lfm3-omni:2b"
    )
    monkeypatch.setattr(omni_pilot, "active_pilot_runtime", lambda: runtime)
    upstream = AsyncMock()
    monkeypatch.setattr(omni_pilot, "require_local_capability", upstream)
    data = {"session_id": "pilot", "sample_rate": "16000", "language": "pl"}
    files = {"audio": ("recording.pcm", b"\x00\x10" * 100)}
    url = "/api/v1/chat/audio/multimodal-turn"
    if error == "bad_type":
        result = await client.post(url, content=b"bad")
        assert result.status_code == 415
    elif error in {
        "bad_media",
        "decode_failed",
        "empty_recording",
        "decoder_unavailable",
    }:
        mime = "text/plain" if error == "bad_media" else "audio/webm"
        recording = b"" if error == "empty_recording" else b"broken"

        def decode(*_args, **_kwargs):
            if error == "decoder_unavailable":
                raise FileNotFoundError("ffmpeg")
            return SimpleNamespace(returncode=1, stderr="invalid input")

        monkeypatch.setattr(chat_audio.subprocess, "run", decode)
        result = await client.post(
            url, data=data, files={"audio": ("voice", recording, mime)}
        )
        assert result.status_code == (503 if error == "decoder_unavailable" else 422)
    elif error == "invalid_image":
        result = await client.post(
            url, data=data, files={**files, "image": ("bad.png", b"x")}
        )
        assert result.status_code == 422
    else:
        result = await client.post(url, data=data, files=files)
        assert result.status_code == 200
        assert result.json()["sources"] == []
        assert "Dołącz obraz" in result.json()["text"]
    upstream.assert_not_awaited()


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


@pytest.fixture
def omni_runtime(monkeypatch):
    from venom_core.api.routes import chat_audio as routes
    from venom_core.services import ollama_audio

    runtime = SimpleNamespace(
        provider="ollama",
        model_name="lfm3-omni:2b",
        endpoint="http://127.0.0.1:11434/v1",
        host_local=True,
    )
    show = AsyncMock(
        return_value={
            "capabilities": ["audio", "speech"],
            "voices": ["female-polish"],
        }
    )
    monkeypatch.setattr(routes, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(ollama_audio.OllamaClient, "get_model_show", show)
    return runtime, show


@pytest.mark.asyncio
@pytest.mark.parametrize("host_ready", [True, False])
async def test_empty_omni_transcript_keeps_native_route_even_when_host_is_available(
    rig, omni_runtime, monkeypatch, host_ready
):
    from venom_core.services import ollama_audio

    client, engine, _ = rig
    native = AsyncMock(return_value="")
    monkeypatch.setattr(ollama_audio, "transcribe_pcm_audio", native)
    if not host_ready:
        client._transport.app.state.audio_engine = None

    response = await client.post(
        "/api/v1/chat/audio/transcribe?session_id=existing&language=pl&prefer_native=true",
        content=b"\x01\x00" * 80,
        headers={"content-type": "application/octet-stream"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "existing",
        "text": "",
        "pipeline": "ollama_audio",
    }
    native.assert_awaited_once()
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
async def test_omni_dictation_and_conversation_use_separate_decoders(
    rig, omni_runtime, monkeypatch
):
    from venom_core.services import ollama_audio

    client, engine, _ = rig
    runtime, show = omni_runtime
    wire = AsyncMock(return_value="sprawdź szkic")
    monkeypatch.setattr(ollama_audio, "transcribe_pcm_audio", wire)
    base = "/api/v1/chat/audio/transcribe?session_id=one&language=pl"
    pcm = b"\x01\x00" * 80
    headers = {"content-type": "application/octet-stream"}
    response = await client.post(
        base + "&prefer_native=true", content=pcm, headers=headers
    )
    assert response.json() == {
        "session_id": "one",
        "text": "sprawdź szkic",
        "pipeline": "ollama_audio",
    }
    wire.assert_awaited_once_with(
        runtime.endpoint, runtime.model_name, pcm, 16000, "pl"
    )
    engine.transcribe_checked.assert_not_awaited()

    response = await client.post(base, content=pcm, headers=headers)
    assert response.json()["pipeline"] == "host_stt"
    runtime.endpoint = "https://remote.invalid/v1"
    response = await client.post(
        base + "&prefer_native=true", content=pcm, headers=headers
    )
    assert response.json()["pipeline"] == "host_stt"
    show.assert_awaited_once()


@pytest.mark.asyncio
async def test_omni_tts_closes_streamed_wav_header(rig, omni_runtime, monkeypatch):
    from contextlib import asynccontextmanager

    from venom_core.services import ollama_audio

    client, engine, _ = rig
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * 80)
    stream = bytearray(output.getvalue())
    stream[40:44] = b"\xfe\xff\xff\xff"
    requests = []

    async def chunks():
        yield stream[:44]
        yield stream[44:]

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def astream(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            yield SimpleNamespace(aiter_bytes=chunks)

    monkeypatch.setattr(
        ollama_audio, "TrafficControlledHttpClient", lambda **_: Client()
    )
    body = {"session_id": "one", "text": "Odpowiedź", "prefer_native": True}
    response = await client.post("/api/v1/chat/audio/speak", json=body)
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.content), "rb") as audio:
        assert (audio.getframerate(), audio.getnframes()) == (24000, 80)
    assert requests == [
        (
            "POST",
            "http://127.0.0.1:11434/v1/audio/speech",
            {
                "json": {
                    "model": "lfm3-omni:2b",
                    "input": "Odpowiedź",
                    "voice": "female-polish",
                    "response_format": "wav",
                },
                "disable_retry": True,
            },
        )
    ]
    engine.speak.assert_not_awaited()
    response = await client.post(
        "/api/v1/chat/audio/speak", json={**body, "language": "de"}
    )
    assert response.status_code == 503
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_voice_pipeline_catalog_checks_local_capabilities_without_loading(
    rig, omni_runtime, monkeypatch
):
    """Advertise local model metadata without using any audio or inference endpoint."""
    from venom_core.config import SETTINGS
    from venom_core.services import ollama_audio

    client, engine, _ = rig
    runtime, show = omni_runtime
    runtime.model_name = "gemma4-e4b-ab-qlora85:q8_0"
    tags = AsyncMock(
        return_value={
            "models": [
                {"name": runtime.model_name},
                {"name": "gemma4:e4b"},
                {"name": "gemma4:remote-cloud"},
                {"name": "gemma4:remote", "remote_host": "https://example.invalid"},
                {"name": "other:latest"},
            ]
        }
    )
    monkeypatch.setattr(ollama_audio.OllamaClient, "list_tags", tags)
    monkeypatch.setattr(SETTINGS, "VOICE_ROUTE_PROFILE", "auto")
    monkeypatch.setattr(SETTINGS, "AUDIO_DECODER_PROFILE", "auto")
    monkeypatch.setattr(SETTINGS, "AUDIO_DECODER_CHAIN", "")
    path = "/api/v1/chat/audio/pipelines"
    assert (await client.get(path)).json() == {
        "active_model": runtime.model_name,
        "gemma_models": [runtime.model_name, "gemma4:e4b"],
        "omni_model": "lfm3-omni:2b",
    }
    assert (await client.get(path + "?language=de")).json()["omni_model"] is None
    assert (await client.get(path + "?surface=voice&language=de")).json()[
        "omni_model"
    ] == "lfm3-omni:2b"
    monkeypatch.setattr(SETTINGS, "AUDIO_DECODER_PROFILE", "faster_whisper")
    assert (await client.get(path + "?surface=voice")).json()["omni_model"] is None
    show.return_value["remote_model"] = "remote"
    assert (await client.get(path)).json()["omni_model"] is None
    runtime.endpoint = "https://example.invalid"
    show.reset_mock()
    tags.reset_mock()
    assert (await client.get(path)).json() == {
        "active_model": None,
        "gemma_models": [],
        "omni_model": None,
    }
    show.assert_not_awaited()
    tags.assert_not_awaited()
    engine.transcribe_checked.assert_not_awaited()
    engine.speak.assert_not_awaited()


@pytest.fixture
def native_runtime(monkeypatch):
    runtime = SimpleNamespace(provider="ollama", model_name="lfm3-omni:2b")

    @asynccontextmanager
    async def guard(**_kwargs):
        yield

    monkeypatch.setattr(omni_pilot, "active_pilot_runtime", lambda: runtime)
    monkeypatch.setattr(omni_native_voice, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(omni_native_voice, "runtime_request_guard", guard)
    monkeypatch.setattr(
        omni_native_dialogue, "native_dialogue_available", lambda _: True
    )
    return runtime


def _native_test_wav() -> bytes:
    wav = io.BytesIO()
    with wave.open(wav, "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x10\x00" * 100)
    return wav.getvalue()


@pytest.mark.asyncio
async def test_native_studio_returns_one_wav_and_retains_only_its_session_context(
    rig, native_runtime, monkeypatch
):
    client, engine, _ = rig
    store = client._transport.app.dependency_overrides[get_session_store]()
    store.append_message(
        "native-one", {"role": "user", "content": "Kontekst operatora"}
    )
    pcm = b"\x00\x10" * 80
    wav = _native_test_wav()
    image = _pilot_image()
    generated = AsyncMock(
        side_effect=[
            omni_native_dialogue.NativeDialogueResult(
                "interleaved",
                "Pierwsza",
                wav,
                False,
                {"generate": 25},
                generation_count=1,
            ),
            omni_native_dialogue.NativeDialogueResult(
                "interleaved", None, None, True, {}
            ),
            omni_native_dialogue.NativeDialogueResult(
                "interleaved", "Druga", wav, False, {}, generation_count=1
            ),
            omni_native_dialogue.NativeDialogueResult(
                "audio", None, wav, False, {}, generation_count=1
            ),
        ]
    )
    monkeypatch.setattr(omni_native_dialogue, "generate_native_turn", generated)
    cascade = AsyncMock()
    monkeypatch.setattr(omni_pilot, "answer", cascade)

    async def turn(session, mode, samples, attachment=None):
        files = {"audio": ("question.pcm", samples, "application/octet-stream")}
        if attachment is not None:
            files["image"] = ("frame.png", attachment, "image/png")
        return await client.post(
            "/api/v1/chat/audio/multimodal-turn",
            data={
                "session_id": session,
                "sample_rate": "16000",
                "language": "pl",
                "generation_mode": mode,
            },
            files=files,
        )

    first = await turn("native-one", "interleaved", pcm, image)
    assert first.status_code == 200
    assert first.json()["text"] == "Pierwsza"
    assert first.json()["generation_count"] == 1
    assert base64.b64decode(first.json()["audio_base64"]) == wav
    silent = await turn("native-one", "interleaved", bytes(len(pcm)))
    assert silent.status_code == 200
    assert silent.json()["no_speech"] is True
    assert "audio_base64" not in silent.json()
    store.append_message("native-one", {"role": "user", "content": "Poprawka pisemna"})
    followup = await turn("native-one", "interleaved", pcm)
    assert followup.status_code == 200
    assert followup.json()["text"] == "Druga"
    assert generated.await_args_list[2].args[3] == image
    assert generated.await_args_list[2].args[4] == [
        {"role": "user", "content": "Kontekst operatora"},
        {"role": "user", "pcm": pcm, "sample_rate": 16000},
        {"role": "assistant", "content": "Pierwsza"},
        {"role": "user", "content": "Poprawka pisemna"},
    ]
    audio_only = await turn("native-two", "audio", pcm)
    assert audio_only.status_code == 200
    assert audio_only.json()["text"] is None
    assert base64.b64decode(audio_only.json()["audio_base64"]) == wav
    generated.assert_awaited_with(native_runtime, pcm, 16000, None, [], mode="audio")
    assert [row["content"] for row in store.get_history("native-one")] == [
        "Kontekst operatora",
        "[Nagranie głosowe]",
        "Pierwsza",
        "Poprawka pisemna",
        "[Nagranie głosowe]",
        "Druga",
    ]
    assert store.get_history("native-two")[-1]["content"] == "[Odpowiedź głosowa]"
    cascade.assert_not_awaited()
    engine.speak.assert_not_awaited()
    engine.transcribe_checked.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "available", "status", "reason"),
    [
        ("text", True, 422, "omni_native_invalid_input"),
        ("interleaved", False, 503, "omni_native_unavailable"),
    ],
)
async def test_native_studio_refuses_invalid_or_unavailable_mode_without_cascade(
    rig, native_runtime, monkeypatch, mode, available, status, reason
):
    client, _, _ = rig
    monkeypatch.setattr(
        omni_native_dialogue, "native_dialogue_available", lambda _: available
    )
    generate = AsyncMock()
    cascade = AsyncMock()
    monkeypatch.setattr(omni_native_dialogue, "generate_native_turn", generate)
    monkeypatch.setattr(omni_pilot, "answer", cascade)
    response = await client.post(
        "/api/v1/chat/audio/multimodal-turn",
        data={"session_id": "s", "sample_rate": "16000", "generation_mode": mode},
        files={"audio": ("voice.pcm", b"\x00\x10", "application/octet-stream")},
    )
    assert response.status_code == status
    assert response.json()["detail"]["reason_code"] == reason
    generate.assert_not_awaited()
    cascade.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_studio_cancels_the_worker_on_http_disconnect(
    native_runtime, monkeypatch
):
    from fastapi import HTTPException, Request

    from venom_core.api.routes.chat_audio import _await_native_turn

    started = asyncio.Event()
    drained = asyncio.Event()

    async def generate(*_args, **_kwargs):
        started.set()
        try:
            await asyncio.Future()
        finally:
            drained.set()

    async def receive():
        await started.wait()
        return {"type": "http.disconnect"}

    monkeypatch.setattr(omni_native_dialogue, "generate_native_turn", generate)
    with pytest.raises(HTTPException) as failure:
        await _await_native_turn(
            Request({"type": "http"}, receive),
            native_runtime,
            b"\x00\x10",
            16000,
            None,
            [],
            "audio",
        )
    assert failure.value.status_code == 499
    assert drained.is_set()


@pytest.mark.asyncio
async def test_native_pipeline_choices_only_advertise_configured_local_polish_omni(
    rig, native_runtime, monkeypatch
):
    from venom_core.api.routes import chat_audio as routes

    client, _, _ = rig
    native_runtime.endpoint = "http://127.0.0.1:11434"
    monkeypatch.setattr(routes, "get_active_llm_runtime", lambda: native_runtime)
    monkeypatch.setattr(routes.ollama_audio, "is_host_ollama", lambda _: True)
    monkeypatch.setattr(
        routes.ollama_audio, "installed_gemma_models", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        routes.ollama_audio, "has_omni_voice", AsyncMock(return_value=True)
    )
    url = "/api/v1/chat/audio/pipelines"
    polish = await client.get(url, params={"language": "pl"})
    assert polish.json()["native_dialogue_modes"] == ["interleaved", "audio"]
    german = await client.get(url, params={"language": "de"})
    assert "native_dialogue_modes" not in german.json()
    monkeypatch.setattr(
        omni_native_dialogue, "native_dialogue_available", lambda _: False
    )
    disabled = await client.get(url, params={"language": "pl"})
    assert "native_dialogue_modes" not in disabled.json()
    assert disabled.json()["omni_model"] == "lfm3-omni:2b"
