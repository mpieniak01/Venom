"""Native speech preserves real WAV data and guarded conversation routing."""

import asyncio
import base64
import io
import json
import sys
import wave
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from venom_core.api import audio_stream as stream
from venom_core.services import ollama_audio as audio
from venom_core.services import omni_native_dialogue as native
from venom_core.utils.llm_runtime import LLMRuntimeInfo


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


def test_existing_16khz_input_preserves_samples(monkeypatch, tmp_path):
    def unexpected(_name):
        raise AssertionError("16 kHz input must not import optional SciPy")

    monkeypatch.setattr(audio, "import_module", unexpected)
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
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * 4410)
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
    assert system == {"role": "system", "content": "Perform ASR in Polish."}
    assert user["role"] == "user"
    assert user["content"] == ""
    assert base64.b64decode(user["images"][0]).startswith(b"RIFF")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,model,busy,profile,supported,expected",
    [
        ("ollama", "small", False, "auto", True, "ollama_audio"),
        ("ollama", "small", False, "auto", False, "faster_whisper"),
        ("ollama", "small", True, "auto", True, "faster_whisper"),
        ("ollama", "small", False, "faster_whisper", True, "faster_whisper"),
        ("vllm", "small", False, "auto", True, "faster_whisper"),
        ("ollama", "gemma4:e4b", False, "auto", True, "ollama_audio"),
        ("ollama", "gemma4:e4b", False, "auto", False, "faster_whisper"),
        ("ollama", "gemma4:e4b", False, "faster_whisper", True, "faster_whisper"),
        ("ollama", "gemma4:e4b", True, "auto", True, "faster_whisper"),
        ("ollama", "gemma4-e4b-ab-qlora85:q8_0", False, "auto", True, "ollama_audio"),
    ],
)
async def test_decoder_respects_capability_explicit_choice_and_busy_runtime(
    monkeypatch, provider, model, busy, profile, supported, expected
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
        provider=provider,
        endpoint="http://127.0.0.1:11434/v1",
        model_name=model,
        host_local=True,
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
    def without_scipy(name):
        assert name == "scipy.signal"
        raise ImportError("optional dependency absent")

    monkeypatch.setattr(audio, "import_module", without_scipy)
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
    assert handler._send_json.await_args_list[-1].args == (
        1,
        {"type": "complete", "status": "no_transcript"},
    )


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


def test_optional_resampler_receives_typed_samples_and_ratio(monkeypatch, tmp_path):
    import numpy as np

    calls = []

    def resample(samples, up, down):
        assert samples.dtype == np.float32
        calls.append((up, down))
        return np.full(1600, 3.0, dtype=np.float32)

    def load(name):
        assert name == "scipy.signal"
        return SimpleNamespace(resample_poly=resample)

    monkeypatch.setattr(audio, "import_module", load)
    with wave.open(
        io.BytesIO(base64.b64decode(audio.encode_audio_input(wav_file(tmp_path))))
    ) as result:
        assert result.getframerate() == 16000
        samples = np.frombuffer(result.readframes(result.getnframes()), dtype="<i2")
    assert calls == [(160, 441)]
    assert samples.size == 1600
    assert (samples == 3).all()


def test_missing_optional_resampler_name_keeps_numpy_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "import_module", lambda _name: SimpleNamespace())
    with wave.open(
        io.BytesIO(base64.b64decode(audio.encode_audio_input(wav_file(tmp_path))))
    ) as result:
        assert result.getframerate() == 16000
        assert result.getnframes() == 1600


def test_resampler_runtime_error_does_not_silently_select_fallback(
    monkeypatch, tmp_path
):
    def fail(*_args):
        raise AttributeError("resampler implementation failed")

    monkeypatch.setattr(
        audio, "import_module", lambda _name: SimpleNamespace(resample_poly=fail)
    )
    path = wav_file(tmp_path)
    with pytest.raises(AttributeError, match="resampler implementation failed"):
        audio.encode_audio_input(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("native_speech", [True, False])
async def test_full_omni_sends_native_pcm_or_reports_missing_capability(
    monkeypatch, tmp_path, native_speech
):
    """Deliver native audio or stop before transcription when speech is unavailable."""
    import json

    handler = object.__new__(stream.AudioStreamHandler)
    websocket = SimpleNamespace(send_text=AsyncMock())
    handler.active_connections = {1: {"websocket": websocket, "voice_mode": "standard"}}
    handler.audio_engine = SimpleNamespace(speak=AsyncMock())
    handler._update_voice_session_metadata = lambda *_: None
    handler._build_runtime_metadata = lambda _: {"llm_provider": "ollama"}
    runtime = SimpleNamespace(
        provider="ollama",
        endpoint="http://localhost:11434",
        model_name=audio.OMNI_MODEL_ID,
        host_local=True,
    )
    monkeypatch.setattr(stream, "get_active_llm_runtime", lambda: runtime)

    @asynccontextmanager
    async def guard(**_):
        yield

    monkeypatch.setattr(stream, "runtime_request_guard", guard)
    ask = AsyncMock(return_value="Test reply.")
    monkeypatch.setattr(stream, "_invoke_operator_agent", ask)
    transcribe = AsyncMock(return_value="Test question.")
    monkeypatch.setattr(audio, "transcribe_audio", transcribe)
    monkeypatch.setattr(
        audio,
        "require_local_capability",
        AsyncMock(
            return_value={
                "capabilities": ["audio", "speech"] if native_speech else ["audio"],
                "voices": ["female-polish"],
            }
        ),
    )
    pcm = b"\x01\x00\x02\x00"
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    synthesize = AsyncMock(return_value=output.getvalue())
    monkeypatch.setattr(audio, "synthesize_speech", synthesize)
    args = dict(
        connection_id=1,
        session_dir=tmp_path,
        wav_path=tmp_path / "sample.wav",
        timings_ms={},
        total_started_at=0,
        operator_agent=object(),
        decoder_plan={"effective": "ollama_audio"},
    )
    if not native_speech:
        with pytest.raises(RuntimeError, match="ollama_omni_voice_unavailable"):
            await handler._handle_decoder_plan_pre_stt(**args)
        transcribe.assert_not_awaited()
        ask.assert_not_awaited()
        synthesize.assert_not_awaited()
    else:
        assert await handler._handle_decoder_plan_pre_stt(**args) is True
        transcribe.assert_awaited_once()
        ask.assert_awaited_once()
        synthesize.assert_awaited_once_with(
            runtime.endpoint, runtime.model_name, "Test reply.", voice="female-polish"
        )
        events = [
            json.loads(call.args[0]) for call in websocket.send_text.await_args_list
        ]
        assert events[-1] == {"type": "complete"}
        assert events[-2]["type"] == "audio_response"
        assert events[-2]["sample_rate"] == 24000
        assert base64.b64decode(events[-2]["audio"]) == pcm
    handler.audio_engine.speak.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("host_available", [True, False])
async def test_omni_ordinary_voice_remains_native_when_host_is_available(
    monkeypatch, host_available
):
    """Host availability must not replace the selected Omni audio pipeline."""
    handler = object.__new__(stream.AudioStreamHandler)
    handler.audio_engine = object() if host_available else None
    handler._resolve_audio_decoder_plan = lambda: {
        "effective": "faster_whisper",
        "selected": "faster_whisper",
        "should_try_native": False,
        "fallback_reason": "",
    }
    handler._audio_decoder_profile = lambda: "auto"
    handler._voice_route_profile = lambda: "auto"
    monkeypatch.setattr(stream, "has_voice_providers", AsyncMock(return_value=False))
    monkeypatch.setattr(
        stream,
        "get_runtime_admission",
        lambda: SimpleNamespace(
            operation=lambda **_: nullcontext(),
        ),
    )
    monkeypatch.setattr(
        stream,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            provider="ollama",
            endpoint="http://127.0.0.1:11434",
            model_name=audio.OMNI_MODEL_ID,
            host_local=True,
        ),
    )
    assert (await handler._resolve_voice_input_decoder_plan())["effective"] == (
        "ollama_audio"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [16000, 44100, 48000])
async def test_full_wav_and_studio_pcm_have_identical_native_requests(
    monkeypatch, tmp_path, rate
):
    import numpy as np

    # Non-silent signal makes a dropped buffer or changed sample order visible.
    samples = (np.sin(np.arange(rate // 5) * 2 * np.pi * 440 / rate) * 1200).astype(
        "<i2"
    )
    path = tmp_path / "question.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(samples.tobytes())
    native = AsyncMock(return_value="pytanie")
    monkeypatch.setattr(audio, "_transcribe", native)
    assert await audio.transcribe_audio("http://local", "omni", path) == "pytanie"
    assert (
        await audio.transcribe_pcm_audio(
            "http://local", "omni", samples.tobytes(), rate, "pl"
        )
        == "pytanie"
    )
    assert native.await_args_list[0] == native.await_args_list[1]
    with wave.open(io.BytesIO(base64.b64decode(native.call_args.args[2]))) as wav:
        result = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        assert wav.getframerate() == 16000
        assert result.size in (3199, 3200)
        # The rate conversion must preserve duration, amplitude and pitch.
        assert 800 < np.sqrt(np.mean(result.astype(float) ** 2)) < 900
        assert (
            abs(np.argmax(abs(np.fft.rfft(result))) * 16000 / result.size - 440) < 0.2
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["full", "studio"])
async def test_digital_silence_skips_native_inference(monkeypatch, tmp_path, surface):
    native = AsyncMock(side_effect=AssertionError("silence reached model"))
    monkeypatch.setattr(audio, "_transcribe", native)
    if surface == "full":
        result = await audio.transcribe_audio(
            "http://local", "omni", wav_file(tmp_path)
        )
    else:
        result = await audio.transcribe_pcm_audio(
            "http://local", "omni", bytes(32000), 16000, "pl"
        )
    assert result == ""
    native.assert_not_awaited()


@pytest.mark.asyncio
async def test_quiet_nonzero_speech_is_not_discarded(monkeypatch):
    native = AsyncMock(return_value="cichy głos")
    monkeypatch.setattr(audio, "_transcribe", native)
    result = await audio.transcribe_pcm_audio(
        "http://local",
        "omni",
        b"\x01\x00\xff\xff" * 8000,
        16000,
        "pl",
        context_length=8192,
    )
    assert result == "cichy głos"
    assert native.call_args.args[-1] == 8192


@pytest.mark.asyncio
@pytest.mark.parametrize("pcm", [b"", b"\x01"])
async def test_invalid_pcm_is_not_reported_as_silence(monkeypatch, pcm):
    native = AsyncMock()
    monkeypatch.setattr(audio, "_transcribe", native)
    with pytest.raises(ValueError):
        await audio.transcribe_pcm_audio("http://local", "omni", pcm, 16000, "pl")
    native.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [16000, 44100, 48000])
async def test_capture_padding_does_not_change_native_asr_request(monkeypatch, rate):
    import numpy as np

    # Keep quiet nonzero edges and an intentional pause inside the utterance.
    speech = np.array([1, 2, -200, 400, 0, 0, 0, -30, -1], dtype="<i2")
    native = AsyncMock(return_value="pytanie")
    monkeypatch.setattr(audio, "_transcribe", native)
    for leading, trailing in [(0, 0), (rate // 3, rate), (rate // 3 + 1536, rate // 2)]:
        framed = np.pad(speech, (leading, trailing))
        await audio.transcribe_pcm_audio(
            "http://local", "omni", framed.tobytes(), rate, "pl"
        )
    assert native.await_count == 3
    assert (
        native.await_args_list[0]
        == native.await_args_list[1]
        == native.await_args_list[2]
    )
    assert native.call_args.args[2] == audio.encode_pcm_audio(speech, rate)


def test_riff_boundary_truncates_pcm_even_with_trailing_file_bytes(tmp_path):
    import struct

    path = wav_file(tmp_path, rate=16000, frames=80)
    data = bytearray(path.read_bytes())
    # The file has enough bytes, but the RIFF chunk ends halfway through PCM.
    data[4:8] = struct.pack("<I", 36 + 80)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="invalid_frame_count"):
        audio.encode_audio_input(path)


@pytest.mark.asyncio
async def test_full_direct_bypasses_operator_and_keeps_connection_history(
    monkeypatch, tmp_path
):
    from venom_core.api.schemas.llm_simple import HistoryMessage
    from venom_core.services import direct_voice

    handler = object.__new__(stream.AudioStreamHandler)
    websocket = SimpleNamespace(send_text=AsyncMock())
    handler.active_connections = {
        1: {"websocket": websocket, "voice_mode": "direct"},
        2: {"websocket": websocket, "voice_mode": "direct"},
    }
    handler.audio_engine = None
    handler._update_voice_session_metadata = lambda *_: None
    handler._build_runtime_metadata = lambda _: {
        "llm_provider": "ollama",
        "llm_model": "omni",
    }
    calls = []

    async def reply(content, history, *, session_id):
        calls.append((content, list(history), session_id))
        return "Cztery boki.", [
            *history,
            HistoryMessage(role="user", content=content),
            HistoryMessage(role="assistant", content="Cztery boki."),
        ]

    monkeypatch.setattr(direct_voice, "complete_direct_turn", reply)
    operator = AsyncMock(side_effect=AssertionError("Direct dispatched to Operator"))
    monkeypatch.setattr(stream, "_invoke_operator_agent", operator)
    for connection_id, question in [
        (1, "Co to jest kwadrat?"),
        (1, "Ile ma boków?"),
        (2, "status"),
    ]:
        await handler._run_whisper_llm_pipeline(
            connection_id=connection_id,
            session_dir=tmp_path,
            transcription=question,
            timings_ms={},
            total_started_at=0,
            operator_agent=None,
            empty_agent_response_log_suffix="",
        )
    assert calls[0][1] == calls[2][1] == []
    assert [x.content for x in calls[1][1]] == ["Co to jest kwadrat?", "Cztery boki."]
    assert calls[0][2] == calls[1][2] != calls[2][2]
    assert handler._voice_contract_payload(1) == {
        "execution_context": "direct",
        "history_scope": "connection",
        "voice_mode": "direct",
    }
    operator.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "first_score", "second_score", "expected", "calls"),
    [
        ("pl", -0.15, -0.05, "pierwsza", 1),
        ("pl", None, -0.05, "pierwsza", 1),
        ("en", -0.9, -0.1, "pierwsza", 1),
        ("pl", -0.9, -0.2, "druga", 2),
        ("pl", -0.9, -0.85, "pierwsza", 2),
        ("pl", -0.9, None, "pierwsza", 2),
        ("pl", -0.9, "timeout", "pierwsza", 2),
    ],
)
async def test_uncertain_polish_omni_compares_one_faster_decode(
    monkeypatch, language, first_score, second_score, expected, calls
):
    sent = []

    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def apost(self, url, *, json, disable_retry):
            assert url == "http://127.0.0.1:11434/api/chat"
            assert disable_retry
            sent.append(json)
            score, text = (
                (first_score, "pierwsza") if len(sent) == 1 else (second_score, "druga")
            )
            if score == "timeout":
                raise TimeoutError
            result = {"done": True, "message": {"content": text}}
            if score is not None:
                result["logprobs"] = [
                    {"token": ".", "logprob": -10.0},
                    {"token": text, "logprob": score},
                ]
            return SimpleNamespace(json=lambda: result)

    monkeypatch.setattr(audio, "TrafficControlledHttpClient", Client)
    pcm = b"\x01\x00\xff\xff" * 800
    result = await audio.transcribe_pcm_audio(
        "http://127.0.0.1:11434/v1", audio.OMNI_MODEL_ID, pcm, 16000, language
    )
    assert result == expected
    assert len(sent) == calls
    assert sent[0].get("logprobs", False) is (language == "pl")
    if calls == 2:
        assert sent[0]["messages"][0] == sent[1]["messages"][0]
        encoded = sent[1]["messages"][1]["images"][0]
        with wave.open(io.BytesIO(base64.b64decode(encoded))) as wav:
            assert wav.getframerate() == 16000
            assert wav.getnframes() in (1481, 1482)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gemma4:e4b", "gemma4-e4b-ab-qlora85:q8_0"])
async def test_gemma_asr_places_transcription_task_with_audio(monkeypatch, model):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def apost(self, url, **kwargs):
            calls.append(kwargs["json"])
            return SimpleNamespace(
                json=lambda: {"done": True, "message": {"content": "Pytanie"}}
            )

    monkeypatch.setattr(audio, "TrafficControlledHttpClient", Client)
    assert (
        await audio.transcribe_pcm_audio(
            "http://local", model, b"\x01\x00" * 160, 16000, "pl"
        )
        == "Pytanie"
    )
    payload = calls[0]
    assert len(calls) == 1
    assert payload["model"] == model
    assert payload["think"] is False
    assert len(payload["messages"]) == 1
    user = payload["messages"][0]
    assert user["role"] == "user"
    assert user["content"].startswith(
        "Transcribe the following speech segment in Polish into Polish text."
    )
    assert base64.b64decode(user["images"][0]).startswith(b"RIFF")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "show, expected",
    [
        ({"capabilities": ["audio"]}, True),
        ({"capabilities": ["audio"], "remote_host": "remote.example"}, False),
        ({"capabilities": ["completion"]}, False),
    ],
)
async def test_native_audio_requires_local_model_capability(
    monkeypatch, show, expected
):
    monkeypatch.setattr(
        audio.OllamaClient, "get_model_show", AsyncMock(return_value=show)
    )
    assert (
        await audio.supports_audio("http://127.0.0.1:11434", "gemma4:e4b") is expected
    )


@pytest.fixture
def native_runtime(monkeypatch, tmp_path):
    snapshot = tmp_path / "snapshot"
    (snapshot / "audio_tokenizer").mkdir(parents=True)
    for filename in (
        "config.json",
        "model.safetensors",
        "audio_tokenizer/model.safetensors",
    ):
        (snapshot / filename).touch()
    monkeypatch.setenv("OMNI_NATIVE_SNAPSHOT", str(snapshot))
    return LLMRuntimeInfo(
        "ollama",
        audio.OMNI_MODEL_ID,
        "http://127.0.0.1:11434",
        "local",
        "dev",
        host_local=True,
    )


def test_native_dialogue_only_lists_installed_local_snapshot(
    native_runtime, monkeypatch
):
    assert native.native_dialogue_available(native_runtime)
    remote = LLMRuntimeInfo(
        "ollama",
        audio.OMNI_MODEL_ID,
        "http://127.0.0.1:11434",
        "local",
        "dev",
        host_local=False,
    )
    assert not native.native_dialogue_available(remote)
    monkeypatch.setenv("OMNI_NATIVE_SNAPSHOT", "relative")
    assert not native.native_dialogue_available(native_runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,text", [("audio", None), ("interleaved", "Róże")])
async def test_native_dialogue_preserves_original_media_and_one_response(
    native_runtime, monkeypatch, tmp_path, mode, text
):
    raw = wav_file(tmp_path, rate=24000, frames=400).read_bytes()
    invocation = AsyncMock(
        return_value=json.dumps(
            {
                "model_revision": native.NATIVE_MODEL_REVISION,
                "generation_count": 1,
                "text": text,
                "wav": base64.b64encode(raw).decode("ascii"),
                "timings_ms": {"load": 10, "prepare": 4, "generate": 4, "decode": 4},
                "peak_reserved_mib": 4380,
            }
        ).encode()
    )
    monkeypatch.setattr(native, "_invoke", invocation)
    pcm = b"\x01\x01" * 400
    image = b"image from the validated transport"
    prior = [
        {"role": "user", "pcm": pcm, "sample_rate": 16000},
        {"role": "assistant", "content": "Tulipany"},
    ]
    result = await native.generate_native_turn(
        native_runtime, pcm, 16000, image, prior, mode=mode
    )
    assert result.wav == raw
    assert result.text == text
    assert result.generation_count == 1
    invocation.assert_awaited_once()
    request = json.loads(invocation.call_args.args[1])
    assert base64.b64decode(request["pcm"]) == pcm
    assert base64.b64decode(request["image"]) == image
    assert base64.b64decode(request["history"][0]["pcm"]) == pcm
    assert request["history"][1]["content"] == "Tulipany"


@pytest.mark.asyncio
async def test_native_dialogue_rejects_bad_media_and_skips_silence(
    native_runtime, monkeypatch
):
    invocation = AsyncMock()
    monkeypatch.setattr(native, "_invoke", invocation)
    with pytest.raises(native.NativeDialogueError, match="omni_native_invalid_input"):
        await native.generate_native_turn(
            native_runtime, b"\x00", 16000, None, [], mode="audio"
        )
    result = await native.generate_native_turn(
        native_runtime, bytes(400), 16000, None, [], mode="audio"
    )
    assert result.no_speech
    assert result.generation_count == 0
    invocation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output, error",
    [
        (b'{"error":"omni_native_gpu_busy"}', "omni_native_gpu_busy"),
        (b"not json", "omni_native_invalid_output"),
        (b'{"model_revision":"unexpected"}', "omni_native_invalid_output"),
    ],
)
async def test_native_dialogue_surfaces_worker_failure_without_fallback(
    native_runtime, monkeypatch, output, error
):
    invocation = AsyncMock(return_value=output)
    monkeypatch.setattr(native, "_invoke", invocation)
    with pytest.raises(native.NativeDialogueError, match=error):
        await native.generate_native_turn(
            native_runtime, b"\x01\x01" * 400, 16000, None, [], mode="audio"
        )
    invocation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux sandbox lifecycle"
)
@pytest.mark.parametrize("cancel_during_start", [False, True])
async def test_native_worker_is_reaped_before_returning_cancelled(
    monkeypatch, tmp_path, cancel_during_start
):
    spawned = asyncio.Event()
    release_spawn = asyncio.Event()
    original = asyncio.create_subprocess_exec
    workers = []

    async def spawn(*_args, **kwargs):
        worker = await original(
            sys.executable, "-c", "import time; time.sleep(60)", **kwargs
        )
        workers.append(worker)
        spawned.set()
        if cancel_during_start:
            await release_spawn.wait()
        return worker

    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(native._invoke(tmp_path, b"{}"))
    await asyncio.wait_for(spawned.wait(), timeout=5)
    task.cancel()
    if cancel_during_start:
        await asyncio.sleep(0)
        assert not task.done()
        release_spawn.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert len(workers) == 1
    assert workers[0].returncode is not None
