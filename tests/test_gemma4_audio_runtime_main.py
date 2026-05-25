from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import services.multi_runtime.main as runtime_main
import venom_core.api.audio_stream as audio_stream_mod
import venom_core.main as core_main
from services.multi_runtime.engine import MultiRuntimeDaemon


def _make_test_daemon(engine_stub) -> MultiRuntimeDaemon:
    """Construct a daemon wired to a pre-built engine stub."""
    daemon = MultiRuntimeDaemon(cache_dir="models_cache/hf")
    daemon._target_engine = engine_stub  # noqa: SLF001
    return daemon


def test_extract_text_prompt_from_openai_messages_prefers_latest_user_text() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "pierwszy"}]},
        {"role": "user", "content": "drugi"},
    ]

    assert runtime_main._extract_text_prompt_from_openai_messages(messages) == "drugi"  # noqa: SLF001


def test_extract_image_urls_from_openai_messages() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "opisz"}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.test/a.png"},
                },
                {"type": "image_url", "image_url": "https://example.test/b.png"},
            ],
        },
    ]
    assert runtime_main._extract_image_urls_from_openai_messages(messages) == [  # noqa: SLF001
        "https://example.test/a.png",
        "https://example.test/b.png",
    ]


def test_extract_transcription_and_answer_from_generation_parses_json_payload() -> None:
    transcription, answer = (
        runtime_main._extract_transcription_and_answer_from_generation(  # noqa: SLF001
            '{"transcription":"Co to jest prostokąt?","answer":"Prostokąt to czworokąt."}'
        )
    )
    assert transcription == "Co to jest prostokąt?"
    assert answer == "Prostokąt to czworokąt."


def test_extract_transcription_and_answer_from_generation_falls_back_to_raw_text() -> (
    None
):
    transcription, answer = (
        runtime_main._extract_transcription_and_answer_from_generation(  # noqa: SLF001
            "To jest zwykła odpowiedź."
        )
    )
    assert transcription is None
    assert answer == "To jest zwykła odpowiedź."


def test_build_voice_session_record_exposes_native_audio_contract():
    record = audio_stream_mod._build_voice_session_record(
        Path("session-a"),
        {
            "voice_pipeline_mode": "native_multi_runtime",
            "pipeline_id": "multi_runtime_piper",
            "decoder_source": "multi_runtime",
            "native_audio_ms": 123.0,
            "transcription": "Co to?",
            "transcription_used_for_generation": "Co to?",
            "request_id": "req-1",
            "trace_id": "trace-1",
            "audio_hash": "hash-1",
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
    assert record["execution_trace_annotations"][2]["note"] == "model response"
    assert record["trace_inconsistent"] is False
    assert record["request_id"] == "req-1"
    assert record["trace_id"] == "trace-1"
    assert record["audio_hash"] == "hash-1"


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

    with pytest.raises(RuntimeError, match="audio endpoint is not configured"):
        await handler._invoke_multi_runtime(wav_path, 17)


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


def test_chat_completions_uses_pydantic_payload_and_sampling(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "to jest odpowiedz", 0.25

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "google/gemma-4-E2B-it",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Ile to 5*5?"}]}
            ],
            "max_tokens": 77,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "to jest odpowiedz"
    assert captured["max_new_tokens"] == 77
    assert captured["do_sample"] is True
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert body["usage"]["prompt_tokens"] >= 1
    assert body["usage"]["completion_tokens"] == max(1, len("to jest odpowiedz") // 4)


def test_chat_completions_accepts_image_urls(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "ok", 0.05

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    async def _fake_image_from_url(_url: str):
        return object()

    monkeypatch.setattr(runtime_main, "_image_from_url", _fake_image_from_url)

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "co jest na obrazku"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.test/image.png"},
                        },
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert isinstance(captured.get("images"), list)
    assert len(captured["images"]) == 1


def test_chat_completions_accepts_data_image_urls(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            captured.update(kwargs)
            return "ok", 0.05

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    def _fake_image_from_data_field(_data: str):
        return object()

    monkeypatch.setattr(
        runtime_main, "_image_from_data_field", _fake_image_from_data_field
    )

    client = TestClient(runtime_main.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,Zm9v"},
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert isinstance(captured.get("images"), list)
    assert len(captured["images"]) == 1


def test_validate_image_url_rejects_private_hosts() -> None:
    runtime_main._validate_image_url("https://example.com/a.png")  # noqa: SLF001
    try:
        runtime_main._validate_image_url("http://127.0.0.1/a.png")  # noqa: SLF001
    except ValueError as exc:
        assert "Local/private hosts" in str(exc)
    else:
        raise AssertionError("Expected ValueError for private host")


def test_validate_image_url_honors_allowlist(monkeypatch) -> None:
    monkeypatch.setenv(
        "GEMMA4_AUDIO_IMAGE_ALLOWED_HOSTS", "example.com,cdn.example.com"
    )
    runtime_main._validate_image_url("https://example.com/a.png")  # noqa: SLF001
    try:
        runtime_main._validate_image_url("https://evil.example/a.png")  # noqa: SLF001
    except ValueError as exc:
        assert "not allowed by policy" in str(exc)
    else:
        raise AssertionError("Expected ValueError for disallowed host")


def test_image_from_path_blocks_when_policy_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "a.png"
    sample.write_bytes(b"not-an-image")
    monkeypatch.delenv("GEMMA4_AUDIO_IMAGE_INPUT_DIR", raising=False)
    try:
        runtime_main._image_from_path(str(sample))  # noqa: SLF001
    except ValueError as exc:
        assert "disabled by policy" in str(exc)
    else:
        raise AssertionError("Expected ValueError when local file loading disabled")


def test_image_from_path_rejects_outside_allowed_dir(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.png"
    allowed.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"not-an-image")
    monkeypatch.setenv("GEMMA4_AUDIO_IMAGE_INPUT_DIR", str(allowed))
    try:
        runtime_main._image_from_path(str(outside))  # noqa: SLF001
    except ValueError as exc:
        assert "outside allowed input directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError for path traversal/outside path")


def test_chat_completions_rejects_streaming(monkeypatch) -> None:
    class EngineStub:
        model_id = "m"

        def is_loaded(self) -> bool:
            return True

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    client = TestClient(runtime_main.app)

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hej"}], "stream": True},
    )

    assert response.status_code == 400
    assert "Streaming is not supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_completions_does_not_decrement_inflight_when_reservation_fails(
    monkeypatch,
) -> None:
    class EngineStub:
        model_id = "google/gemma-4-E2B-it"

        def is_loaded(self) -> bool:
            return True

        def respond(self, _audio, **kwargs):
            return "ok", 0.01

    daemon = _make_test_daemon(EngineStub())
    monkeypatch.setattr(runtime_main, "_daemon", daemon)

    @asynccontextmanager
    async def _reserve_fail(_daemon):
        raise RuntimeError("reservation failed")
        yield None  # pragma: no cover

    called = {"decrement": 0}

    async def _decrement_track() -> int:
        called["decrement"] += 1
        return 0

    monkeypatch.setattr(runtime_main, "_reserve_ready_engine", _reserve_fail)
    monkeypatch.setattr(runtime_main, "_decrement_respond_inflight", _decrement_track)

    payload = runtime_main.ChatCompletionRequest(
        model="google/gemma-4-E2B-it",
        messages=[runtime_main.ChatCompletionMessage(role="user", content="hej")],
    )

    with pytest.raises(runtime_main.HTTPException, match="reservation failed"):
        await runtime_main.chat_completions(payload)

    assert called["decrement"] == 0


@pytest.mark.asyncio
async def test_respond_returns_503_before_inflight_when_model_not_loaded(
    monkeypatch,
) -> None:
    class EngineStub:
        def is_loaded(self) -> bool:
            return False

    class DaemonStub:
        def active_engine(self):
            return EngineStub()

    monkeypatch.setattr(runtime_main, "get_daemon", lambda: DaemonStub())

    calls = {"inc": 0, "dec": 0}

    async def _increment_ok() -> None:
        calls["inc"] += 1

    async def _decrement_ok() -> int:
        calls["dec"] += 1
        return 0

    monkeypatch.setattr(runtime_main, "_increment_respond_inflight", _increment_ok)
    monkeypatch.setattr(runtime_main, "_decrement_respond_inflight", _decrement_ok)

    request = runtime_main.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/respond",
            "headers": [],
            "query_string": b"",
        }
    )

    with pytest.raises(runtime_main.HTTPException) as exc_info:
        await runtime_main.respond(request)

    assert exc_info.value.status_code == 503
    assert calls["inc"] == 0
    assert calls["dec"] == 0
