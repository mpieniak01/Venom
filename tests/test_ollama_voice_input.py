"""Native speech preserves real WAV data and guarded conversation routing."""

import base64
import io
import wave
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from venom_core.api import audio_stream as stream
from venom_core.services import ollama_audio as audio


@pytest.fixture(autouse=True)
def automatic_voice_route(monkeypatch):
    monkeypatch.setattr(stream.SETTINGS, "VOICE_ROUTE_PROFILE", "auto")
    monkeypatch.setattr(stream.SETTINGS, "AUDIO_DECODER_CHAIN", "")


def wav_file(tmp_path, rate=44100, channels=1, width=2, frames=4410):
    path = tmp_path / "input.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames * channels * width))
    return path


def test_audio_is_real_resampled_wav_not_path_or_headerless_pcm(tmp_path):
    encoded = audio.encode_audio_input(wav_file(tmp_path))
    raw = base64.b64decode(encoded)
    assert raw[:4] == b"RIFF"
    with wave.open(io.BytesIO(raw)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (
            1,
            2,
            16000,
        )
        assert wav.getnframes() == 1600


def test_existing_16khz_input_preserves_samples(tmp_path):
    path = wav_file(tmp_path, rate=16000, frames=1600)
    assert base64.b64decode(audio.encode_audio_input(path)) == path.read_bytes()


@pytest.mark.parametrize("kwargs", [{"channels": 2}, {"width": 1}, {"frames": 0}])
def test_reject_invalid_or_empty_audio(tmp_path, kwargs):
    path = wav_file(tmp_path, **kwargs)
    with pytest.raises(ValueError):
        audio.encode_audio_input(path)


def test_large_audio_rejected_before_read(monkeypatch):
    path = SimpleNamespace(
        stat=lambda: SimpleNamespace(st_size=audio.MAX_AUDIO_BYTES + 1)
    )
    with pytest.raises(ValueError, match="too_large"):
        audio.encode_audio_input(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caps,expected", [(["audio"], True), (["completion"], False), ([], False)]
)
async def test_audio_support_comes_from_model_metadata_not_model_name(
    monkeypatch, caps, expected
):
    show = AsyncMock(return_value={"capabilities": caps})
    monkeypatch.setattr(
        audio, "OllamaClient", lambda _: SimpleNamespace(get_model_show=show)
    )
    assert (
        await audio.supports_audio("http://local/v1", "another-family:small")
        is expected
    )
    show.assert_awaited_once_with("another-family:small")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        ({"done": True, "message": {"content": "  nagranie  "}}, "nagranie"),
        ({"done": True, "message": {"content": ""}}, ""),
        ({"done": False}, None),
        (
            {"done": True, "done_reason": "length", "message": {"content": "partial"}},
            None,
        ),
        ({"done": True, "error": "failure"}, None),
        ({"done": True, "message": None}, None),
        ({"done": True, "message": {"content": 12}}, None),
    ],
)
async def test_native_request_separates_system_instruction_and_audio(
    monkeypatch, tmp_path, response, expected
):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["provider"] == "ollama"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def apost(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(json=lambda: response)

    monkeypatch.setattr(audio, "TrafficControlledHttpClient", Client)
    path = wav_file(tmp_path)
    if expected is None:
        with pytest.raises(RuntimeError):
            await audio.transcribe_audio(
                "http://127.0.0.1:11434/v1", "custom-model", path
            )
    else:
        assert (
            await audio.transcribe_audio(
                "http://127.0.0.1:11434/v1", "custom-model", path
            )
            == expected
        )
    url, kwargs = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert kwargs["disable_retry"] is True
    payload = kwargs["json"]
    assert payload["model"] == "custom-model"
    assert payload["think"] is False
    assert payload["stream"] is False
    system, user = payload["messages"]
    assert system["role"] == "system"
    assert user["role"] == "user"
    assert user["content"] == ""
    assert base64.b64decode(user["images"][0]).startswith(b"RIFF")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,busy,profile,supported,expected",
    [
        ("ollama", False, "auto", True, "ollama_audio"),
        ("ollama", False, "auto", False, "faster_whisper"),
        ("ollama", True, "auto", True, "faster_whisper"),
        ("ollama", False, "faster_whisper", True, "faster_whisper"),
        ("vllm", False, "auto", True, "faster_whisper"),
    ],
)
async def test_decoder_respects_capability_explicit_choice_and_busy_runtime(
    monkeypatch, provider, busy, profile, supported, expected
):
    handler = object.__new__(stream.AudioStreamHandler)
    handler._resolve_audio_decoder_plan = lambda: {
        "effective": "faster_whisper",
        "selected": "faster_whisper",
        "should_try_native": False,
        "fallback_reason": "",
    }
    handler._audio_decoder_profile = lambda: profile
    runtime = SimpleNamespace(
        provider=provider, endpoint="http://local/v1", model_name="small"
    )
    monkeypatch.setattr(stream, "get_active_llm_runtime", lambda: runtime)
    from contextlib import contextmanager

    @contextmanager
    def operation(**kwargs):
        if busy:
            raise stream.RuntimeAdmissionError()
        yield

    monkeypatch.setattr(
        stream,
        "get_runtime_admission",
        lambda: SimpleNamespace(operation=operation),
    )
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=True))
    monkeypatch.setattr(audio, "supports_audio", AsyncMock(return_value=supported))
    plan = await handler._resolve_voice_input_decoder_plan()
    assert plan["effective"] == expected
    assert plan["guarded_voice"] is True


@pytest.mark.asyncio
async def test_unguarded_whisper_plan_is_preserved(monkeypatch):
    handler = object.__new__(stream.AudioStreamHandler)
    plan = {"effective": "faster_whisper"}
    handler._resolve_audio_decoder_plan = lambda: plan
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=False))
    monkeypatch.setattr(
        stream, "get_active_llm_runtime", lambda: SimpleNamespace(provider="vllm")
    )
    monkeypatch.setattr(
        stream,
        "get_runtime_admission",
        lambda: SimpleNamespace(snapshot=lambda: {"status": "available"}),
    )
    assert await handler._resolve_voice_input_decoder_plan() is plan


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript", ["Ile wynosi pi?", "", None])
async def test_native_transcript_uses_shared_authorized_agent_pipeline(
    monkeypatch, tmp_path, transcript
):
    handler = object.__new__(stream.AudioStreamHandler)
    updates = []
    handler._update_voice_session_metadata = lambda _path, value: updates.append(value)
    handler._run_whisper_llm_pipeline = AsyncMock()
    handler._elapsed_ms = lambda _: 1.0
    runtime = SimpleNamespace(
        provider="ollama", endpoint="http://local/v1", model_name="audio-model"
    )
    monkeypatch.setattr(stream, "get_active_llm_runtime", lambda: runtime)

    @asynccontextmanager
    async def guard(**kwargs):
        assert kwargs["provider"] == "ollama"
        yield

    monkeypatch.setattr(stream, "runtime_request_guard", guard)
    transcription = AsyncMock(return_value=transcript)
    if transcript is None:
        transcription.side_effect = RuntimeError("decoder_failed")
    monkeypatch.setattr(audio, "transcribe_audio", transcription)
    args = dict(
        connection_id=1,
        session_dir=tmp_path,
        wav_path=tmp_path / "audio.wav",
        timings_ms={},
        total_started_at=0,
        operator_agent=object(),
        decoder_plan={"effective": "ollama_audio"},
    )
    if transcript is None:
        with pytest.raises(RuntimeError, match="decoder_failed"):
            await handler._handle_decoder_plan_pre_stt(**args)
        assert updates[-1]["audio_input_status"] == "failed"
        handler._run_whisper_llm_pipeline.assert_not_awaited()
    else:
        assert await handler._handle_decoder_plan_pre_stt(**args) is True
        call = handler._run_whisper_llm_pipeline.call_args.kwargs
        assert call["transcription"] == transcript
        assert call["pipeline_id"] == "ollama_audio_llm_piper"
        assert updates[-1]["decoder_source"] == "ollama"
        assert updates[-1]["audio_input_status"] == (
            "verified" if transcript else "empty"
        )


def test_resampling_without_optional_scipy(monkeypatch, tmp_path):
    import builtins

    original = builtins.__import__

    def without_scipy(name, *args, **kwargs):
        if name == "scipy.signal":
            raise ImportError("optional dependency absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_scipy)
    with wave.open(
        io.BytesIO(base64.b64decode(audio.encode_audio_input(wav_file(tmp_path))))
    ) as result:
        assert result.getframerate() == 16000
        assert result.getnframes() == 1600


@pytest.mark.asyncio
async def test_actual_nested_admission_allows_native_voice(monkeypatch, tmp_path):
    from venom_core.services.runtime_admission import RuntimeAdmission

    admission = RuntimeAdmission(tmp_path / "voice.sqlite3")
    handler = object.__new__(stream.AudioStreamHandler)
    handler._resolve_audio_decoder_plan = lambda: {"effective": "faster_whisper"}
    handler._audio_decoder_profile = lambda: "auto"
    monkeypatch.setattr(stream, "get_runtime_admission", lambda: admission)
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=True))
    monkeypatch.setattr(
        stream,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            provider="ollama", endpoint="http://fixture", model_name="audio-model"
        ),
    )
    monkeypatch.setattr(audio, "supports_audio", AsyncMock(return_value=True))
    with admission.operation(kind="voice_prepare"):
        assert admission.snapshot()["status"] == "busy"
        plan = await handler._resolve_voice_input_decoder_plan()
        assert plan["effective"] == "ollama_audio"


@pytest.mark.asyncio
async def test_actual_foreign_experiment_keeps_whisper(monkeypatch, tmp_path):
    from venom_core.services.runtime_admission import RuntimeAdmission

    admission = RuntimeAdmission(tmp_path / "voice.sqlite3")
    lease = admission.acquire(
        owner="experiment", run_id="fixture", engine="other", model="other"
    )
    handler = object.__new__(stream.AudioStreamHandler)
    handler._resolve_audio_decoder_plan = lambda: {"effective": "faster_whisper"}
    handler._audio_decoder_profile = lambda: "auto"
    monkeypatch.setattr(stream, "get_runtime_admission", lambda: admission)
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=True))
    monkeypatch.setattr(
        stream,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            provider="ollama", endpoint="http://fixture", model_name="audio-model"
        ),
    )
    support = AsyncMock(return_value=True)
    monkeypatch.setattr(audio, "supports_audio", support)
    try:
        plan = await handler._resolve_voice_input_decoder_plan()
        assert plan["effective"] == "faster_whisper"
        support.assert_not_awaited()
    finally:
        assert lease.release()


@pytest.mark.asyncio
async def test_empty_transcript_finishes_voice_ui_without_generation(tmp_path):
    handler = object.__new__(stream.AudioStreamHandler)
    handler._send_json = AsyncMock()
    await handler._run_whisper_llm_pipeline(
        connection_id=1,
        session_dir=tmp_path,
        transcription="",
        timings_ms={},
        total_started_at=0,
        operator_agent=None,
        pipeline_id="ollama_audio_llm_piper",
    )
    assert handler._send_json.await_args_list[-1].args == (1, {"type": "complete"})


@pytest.mark.parametrize("rate", [1, 7999, 192001])
def test_unsupported_rate_rejected_before_resampling(tmp_path, rate):
    path = wav_file(tmp_path, rate=rate, frames=8)
    with pytest.raises(ValueError, match="unsupported_sample_rate"):
        audio.encode_audio_input(path)


def test_expanded_wav_is_bounded_before_allocating_output(monkeypatch, tmp_path):
    path = wav_file(tmp_path, rate=8000, frames=100)
    assert path.stat().st_size < 300
    monkeypatch.setattr(audio, "MAX_AUDIO_BYTES", 300)
    with pytest.raises(ValueError, match="audio_output_too_large"):
        audio.encode_audio_input(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,profile,chain,valid,expected",
    [
        ("runtime_lokalny", "auto", "", True, "faster_whisper"),
        ("venom-agent", "auto", "", True, "faster_whisper"),
        ("gemma4", "auto", "", False, "none"),
        ("auto", "auto", "faster_whisper", True, "faster_whisper"),
        ("auto", "gemma_native", "", True, "faster_whisper"),
        ("auto", "auto", "", False, "none"),
    ],
)
async def test_native_selection_preserves_route_contract(
    monkeypatch, route, profile, chain, valid, expected
):
    handler = object.__new__(stream.AudioStreamHandler)
    plan = {"effective": "faster_whisper" if valid else "none"}
    handler._resolve_audio_decoder_plan = lambda: plan
    monkeypatch.setattr(stream.SETTINGS, "VOICE_ROUTE_PROFILE", route)
    monkeypatch.setattr(stream.SETTINGS, "AUDIO_DECODER_PROFILE", profile)
    monkeypatch.setattr(stream.SETTINGS, "AUDIO_DECODER_CHAIN", chain)
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=False))
    monkeypatch.setattr(
        stream,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            provider="ollama", endpoint="http://fixture", model_name="audio-model"
        ),
    )
    support = AsyncMock(return_value=True)
    monkeypatch.setattr(audio, "supports_audio", support)
    result = await handler._resolve_voice_input_decoder_plan()
    assert result["effective"] == expected
    support.assert_not_awaited()


def test_declared_frames_cannot_allocate_beyond_the_input_file(monkeypatch, tmp_path):
    import struct
    from unittest.mock import Mock

    path = wav_file(tmp_path, rate=192000, frames=8)
    data = bytearray(path.read_bytes())
    data[40:44] = struct.pack("<I", 4_000_000)
    path.write_bytes(data)
    read = Mock(side_effect=AssertionError("read before validating frame count"))
    monkeypatch.setattr(wave.Wave_read, "readframes", read)
    with pytest.raises(ValueError, match="invalid_frame_count"):
        audio.encode_audio_input(path)
    read.assert_not_called()
