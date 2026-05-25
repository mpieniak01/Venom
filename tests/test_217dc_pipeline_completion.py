"""Tests for 217DC pipeline completion scope.

Covers:
- ImagePreprocessorStage (resize, RGB, EXIF)
- RuntimePolicyResolver VRAM-aware economy_mode
- AudioOutputStage fallback paths
- RetrievalStage _run_in_new_loop
- Engine quantization routing (mocked)
- MultiRuntimeEngine precision/quantization_backend in DaemonParams
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from PIL import Image

from services.multi_runtime.components import build_component_snapshot
from services.multi_runtime.diagnostics import ExecutionDiagnostics
from services.multi_runtime.policies import RuntimePolicyResolver
from services.multi_runtime.stages.audio_output import AudioOutputStage, _clean_text
from services.multi_runtime.stages.base import StageContext
from services.multi_runtime.stages.image_preprocessor import (
    ImagePreprocessorStage,
    _normalize_image,
)
from services.multi_runtime.stages.retrieval import RetrievalStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    images: list | None = None,
    policy_overrides: dict | None = None,
    state: dict | None = None,
    daemon_status: dict | None = None,
) -> StageContext:
    from services.multi_runtime.policies import ExecutionPolicy

    policy = ExecutionPolicy(**(policy_overrides or {}))
    return StageContext(
        request_payload=MagicMock(),
        daemon_status=daemon_status or {"params": {}, "vram": {"backend": "cpu"}},
        text_content="test",
        audio_array=None,
        sample_rate=16000,
        images=images or [],
        diagnostics=ExecutionDiagnostics(),
        state={"policy": policy, **(state or {})},
    )


def _make_image(w: int, h: int, mode: str = "RGB") -> Image.Image:
    return Image.new(mode, (w, h), color=0)


def _daemon_status(**overrides) -> dict:
    base = {
        "target_model": "test/model",
        "assistant_model": None,
        "target_loaded": True,
        "assistant_loaded": False,
        "supports_image_input": True,
        "vram": {"backend": "cuda", "free_mb": 4096},
        "params": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ImagePreprocessorStage
# ---------------------------------------------------------------------------


def test_image_preprocessor_skips_with_no_images() -> None:
    ctx = _make_context(images=[])
    ImagePreprocessorStage().run(ctx)
    assert ctx.state["preprocessed_images"] == []
    assert any(
        t.name == "image_preprocessor" and t.outcome == "skipped"
        for t in ctx.diagnostics.execution_trace
    )


def test_image_preprocessor_converts_rgba_to_rgb() -> None:
    img = _make_image(200, 200, "RGBA")
    ctx = _make_context(images=[img])
    ImagePreprocessorStage().run(ctx)
    result = ctx.state["preprocessed_images"]
    assert len(result) == 1
    assert result[0].mode == "RGB"


def test_image_preprocessor_converts_palette_to_rgb() -> None:
    img = _make_image(200, 200, "P")
    ctx = _make_context(images=[img])
    ImagePreprocessorStage().run(ctx)
    assert ctx.state["preprocessed_images"][0].mode == "RGB"


def test_image_preprocessor_resizes_oversized_image() -> None:
    img = _make_image(2048, 1024, "RGB")
    ctx = _make_context(images=[img])
    with patch(
        "services.multi_runtime.stages.image_preprocessor._max_image_dim",
        return_value=512,
    ):
        ImagePreprocessorStage().run(ctx)
    result = ctx.state["preprocessed_images"][0]
    assert max(result.size) <= 512


def test_image_preprocessor_preserves_aspect_ratio() -> None:
    img = _make_image(2000, 1000, "RGB")
    ctx = _make_context(images=[img])
    with patch(
        "services.multi_runtime.stages.image_preprocessor._max_image_dim",
        return_value=1000,
    ):
        ImagePreprocessorStage().run(ctx)
    result = ctx.state["preprocessed_images"][0]
    w, h = result.size
    assert abs(w / h - 2.0) < 0.01


def test_normalize_image_small_image_unchanged() -> None:
    img = _make_image(100, 50, "RGB")
    result, _ = _normalize_image(img, 1024)
    assert result.size == (100, 50)


# ---------------------------------------------------------------------------
# RuntimePolicyResolver — VRAM-aware economy_mode
# ---------------------------------------------------------------------------


def test_policy_resolver_economy_off_when_vram_ample() -> None:
    status = _daemon_status(vram={"backend": "cuda", "free_mb": 8192})
    status["params"]["economy_mode"] = "off"
    policy = RuntimePolicyResolver().resolve(
        daemon_status=status, has_images=False, has_audio=False
    )
    assert policy.economy_mode == "off"


def test_policy_resolver_economy_auto_when_vram_low() -> None:
    status = _daemon_status(vram={"backend": "cuda", "free_mb": 512})
    status["params"]["economy_mode"] = "off"
    with patch(
        "services.multi_runtime.policies._economy_vram_threshold", return_value=2048
    ):
        policy = RuntimePolicyResolver().resolve(
            daemon_status=status, has_images=False, has_audio=False
        )
    assert policy.economy_mode == "auto"


def test_policy_resolver_explicit_free_vram_mb_overrides_status() -> None:
    status = _daemon_status(vram={"backend": "cuda", "free_mb": 8000})
    status["params"]["economy_mode"] = "off"
    with patch(
        "services.multi_runtime.policies._economy_vram_threshold", return_value=2048
    ):
        policy = RuntimePolicyResolver().resolve(
            daemon_status=status,
            has_images=False,
            has_audio=False,
            free_vram_mb=256,
        )
    assert policy.economy_mode == "auto"


def test_policy_resolver_economy_auto_profile_stays_auto() -> None:
    status = _daemon_status(vram={"backend": "cuda", "free_mb": 8192})
    status["params"]["economy_mode"] = "auto"
    policy = RuntimePolicyResolver().resolve(
        daemon_status=status, has_images=False, has_audio=False
    )
    assert policy.economy_mode == "auto"


def test_policy_resolver_no_free_mb_falls_back_to_backend_check() -> None:
    status = _daemon_status()
    status["vram"] = {"backend": "cpu"}
    policy = RuntimePolicyResolver().resolve(
        daemon_status=status, has_images=False, has_audio=False
    )
    assert policy.economy_mode == "auto"


# ---------------------------------------------------------------------------
# AudioOutputStage
# ---------------------------------------------------------------------------


def test_audio_output_skipped_when_mode_off() -> None:
    ctx = _make_context(policy_overrides={"audio_output_mode": "off"})
    AudioOutputStage().run(ctx)
    assert any(
        t.name == "audio_output" and t.outcome == "skipped"
        for t in ctx.diagnostics.execution_trace
    )
    assert ctx.state.get("audio_bytes") is None


def test_audio_output_degraded_when_tts_component_unavailable() -> None:
    ctx = _make_context(
        policy_overrides={"audio_output_mode": "voice_first"},
        state={
            "generated_text": "Hello world",
            "policy": __import__(
                "services.multi_runtime.policies", fromlist=["ExecutionPolicy"]
            ).ExecutionPolicy(audio_output_mode="voice_first"),
        },
    )
    ctx.diagnostics.component_snapshot = [
        {"component_id": "tts_component", "available": False, "health": "degraded"}
    ]
    AudioOutputStage().run(ctx)
    assert any(
        t.name == "audio_output" and t.outcome == "degraded"
        for t in ctx.diagnostics.execution_trace
    )


def test_audio_output_degraded_when_model_file_missing() -> None:
    from services.multi_runtime.policies import ExecutionPolicy

    ctx = _make_context(
        state={
            "generated_text": "Hello",
            "policy": ExecutionPolicy(audio_output_mode="voice_first"),
        }
    )
    ctx.diagnostics.component_snapshot = [
        {"component_id": "tts_component", "available": True, "health": "ok"}
    ]
    with patch(
        "services.multi_runtime.stages.audio_output._find_tts_model_path",
        return_value=None,
    ):
        AudioOutputStage().run(ctx)
    assert any("not found" in d for d in ctx.diagnostics.degradation_reasons)


def test_audio_output_degraded_when_piper_not_installed() -> None:
    from pathlib import Path

    from services.multi_runtime.policies import ExecutionPolicy

    ctx = _make_context(
        state={
            "generated_text": "Hello",
            "policy": ExecutionPolicy(audio_output_mode="voice_first"),
        }
    )
    ctx.diagnostics.component_snapshot = [
        {"component_id": "tts_component", "available": True, "health": "ok"}
    ]
    with (
        patch(
            "services.multi_runtime.stages.audio_output._find_tts_model_path",
            return_value=Path("/fake/model.onnx"),
        ),
        patch(
            "services.multi_runtime.stages.audio_output._synthesize",
            side_effect=ImportError("No module named 'piper'"),
        ),
    ):
        AudioOutputStage().run(ctx)
    assert any("not installed" in d for d in ctx.diagnostics.degradation_reasons)


def test_audio_output_writes_audio_bytes_and_sample_rate() -> None:
    from pathlib import Path

    from services.multi_runtime.policies import ExecutionPolicy

    ctx = _make_context(
        policy_overrides={"audio_output_mode": "voice_first"},
        state={
            "generated_text": "Hello **world**",
            "policy": ExecutionPolicy(audio_output_mode="voice_first"),
        },
    )
    ctx.diagnostics.component_snapshot = [
        {"component_id": "tts_component", "available": True, "health": "ok"}
    ]
    with (
        patch(
            "services.multi_runtime.stages.audio_output._find_tts_model_path",
            return_value=Path("/fake/model.onnx"),
        ),
        patch(
            "services.multi_runtime.stages.audio_output._synthesize",
            return_value=(b"wav-bytes", 24000),
        ),
    ):
        AudioOutputStage().run(ctx)

    assert ctx.state["audio_bytes"] == "d2F2LWJ5dGVz"
    assert ctx.state["audio_sample_rate"] == 24000
    assert any(
        t.name == "audio_output" and t.outcome == "ok"
        for t in ctx.diagnostics.execution_trace
    )


def test_clean_text_removes_markdown() -> None:
    raw = "**Bold** `code` [link](http://x.com) # header"
    result = _clean_text(raw)
    assert "**" not in result
    assert "`" not in result
    assert "link" in result
    assert "http" not in result


# ---------------------------------------------------------------------------
# RetrievalStage._run_in_new_loop
# ---------------------------------------------------------------------------


def test_run_in_new_loop_handles_non_coroutine() -> None:
    result = RetrievalStage._run_in_new_loop("hello")
    assert result == "hello"


def test_run_in_new_loop_executes_coroutine() -> None:
    async def _coro() -> str:
        return "async_result"

    result = RetrievalStage._run_in_new_loop(_coro())
    assert result == "async_result"


def test_run_in_new_loop_safe_when_called_from_thread() -> None:
    """Verify _run_in_new_loop works even if called inside asyncio.to_thread."""

    async def _coro() -> int:
        return 42

    async def _outer() -> int:
        return await asyncio.to_thread(RetrievalStage._run_in_new_loop, _coro())

    result = asyncio.run(_outer())
    assert result == 42


def test_retrieval_stage_uses_graph_service_when_available() -> None:
    from services.multi_runtime.policies import ExecutionPolicy

    async def _graph_search(text: str, max_hops: int = 2, limit: int = 4) -> str:
        return "graph result: node A -> node B"

    graph_service = MagicMock()
    graph_service.local_search = _graph_search
    vector_store = MagicMock()
    vector_store.search = MagicMock(return_value=[])

    ctx = _make_context(
        policy_overrides={"retrieval_mode": "always"},
        state={"policy": ExecutionPolicy(retrieval_mode="always")},
    )
    ctx.text_content = "compare graph relationship between A and B"

    stage = RetrievalStage(graph_service=graph_service, vector_store=vector_store)
    stage.run(ctx)

    assert ctx.state["retrieval_context"] == "graph result: node A -> node B"
    assert ctx.diagnostics.retrieval_route == "graph"
    assert ctx.diagnostics.retrieval_used is True
    vector_store.search.assert_not_called()


# ---------------------------------------------------------------------------
# Engine — quantization parameter routing (mocked)
# ---------------------------------------------------------------------------


def test_engine_build_load_kwargs_auto_precision() -> None:
    from services.multi_runtime.engine import MultiRuntimeEngine

    engine = MultiRuntimeEngine("fake/model", "/tmp/cache", precision="auto")
    transformers_mock = MagicMock()
    kwargs = engine._build_load_kwargs(transformers_mock)
    assert "dtype" in kwargs or "device_map" in kwargs


def test_engine_build_load_kwargs_float16() -> None:
    import pytest

    torch = pytest.importorskip("torch")
    from services.multi_runtime.engine import MultiRuntimeEngine

    engine = MultiRuntimeEngine("fake/model", "/tmp/cache", precision="float16")
    transformers_mock = MagicMock()
    kwargs = engine._build_load_kwargs(transformers_mock)
    assert kwargs.get("torch_dtype") == torch.float16


def test_engine_build_load_kwargs_bfloat16() -> None:
    import pytest

    torch = pytest.importorskip("torch")
    from services.multi_runtime.engine import MultiRuntimeEngine

    engine = MultiRuntimeEngine("fake/model", "/tmp/cache", precision="bfloat16")
    transformers_mock = MagicMock()
    kwargs = engine._build_load_kwargs(transformers_mock)
    assert kwargs.get("torch_dtype") == torch.bfloat16


def test_engine_build_bnb_config_returns_none_when_unavailable() -> None:
    from services.multi_runtime.engine import MultiRuntimeEngine

    with patch.dict("sys.modules", {"bitsandbytes": None}):
        result = MultiRuntimeEngine._build_bnb_config(MagicMock(), "int4")
    assert result is None


def test_engine_build_load_kwargs_bnb_fallback_to_float16_when_unavailable() -> None:
    import pytest

    torch = pytest.importorskip("torch")
    from services.multi_runtime.engine import MultiRuntimeEngine

    engine = MultiRuntimeEngine(
        "fake/model",
        "/tmp/cache",
        precision="int4",
        quantization_backend="bitsandbytes",
    )
    transformers_mock = MagicMock()
    with patch.object(MultiRuntimeEngine, "_build_bnb_config", return_value=None):
        kwargs = engine._build_load_kwargs(transformers_mock)
    assert kwargs.get("torch_dtype") == torch.float16


def test_engine_write_audio_wav_fallback_without_soundfile(tmp_path) -> None:
    from services.multi_runtime.engine import MultiRuntimeEngine

    out = tmp_path / "fallback.wav"
    audio = [0.0, 0.25, -0.25, 1.0, -1.0]
    with patch("services.multi_runtime.engine.sf", None):
        MultiRuntimeEngine._write_audio_wav(out, audio, 16000)
    assert out.exists()
    assert out.stat().st_size > 44


def test_daemon_params_defaults_precision() -> None:
    from services.multi_runtime.engine import DaemonParams

    p = DaemonParams()
    assert p.precision == "auto"
    assert p.quantization_backend is None
    assert p.device_target == "auto"


def test_update_params_precision_triggers_soft_reload() -> None:
    from services.multi_runtime.engine import MultiRuntimeDaemon as Daemon
    from services.multi_runtime.engine import ReloadSignal

    with patch("services.multi_runtime.engine.MultiRuntimeEngine") as MockEngine:
        MockEngine.return_value.load = MagicMock()
        d = Daemon(model_id="test/model", cache_dir="/tmp/cache")
        signal = d.update_params(precision="float16")
    assert signal == ReloadSignal.SOFT_RELOAD


def test_update_params_quantization_backend_triggers_soft_reload() -> None:
    from services.multi_runtime.engine import MultiRuntimeDaemon as Daemon
    from services.multi_runtime.engine import ReloadSignal

    with patch("services.multi_runtime.engine.MultiRuntimeEngine") as MockEngine:
        MockEngine.return_value.load = MagicMock()
        d = Daemon(model_id="test/model", cache_dir="/tmp/cache")
        signal = d.update_params(quantization_backend="bitsandbytes")
    assert signal == ReloadSignal.SOFT_RELOAD


def test_update_params_device_target_triggers_soft_reload() -> None:
    from services.multi_runtime.engine import MultiRuntimeDaemon as Daemon
    from services.multi_runtime.engine import ReloadSignal

    with patch("services.multi_runtime.engine.MultiRuntimeEngine") as MockEngine:
        MockEngine.return_value.load = MagicMock()
        d = Daemon(model_id="test/model", cache_dir="/tmp/cache")
        signal = d.update_params(device_target="cuda")
    assert signal == ReloadSignal.SOFT_RELOAD


def test_component_snapshot_reports_bitsandbytes_backend_for_quantized_main_model() -> (
    None
):
    snapshot = build_component_snapshot(
        {
            "target_model": "test/model",
            "assistant_model": None,
            "target_loaded": True,
            "assistant_loaded": False,
            "supports_image_input": True,
            "vram": {"backend": "cuda", "free_mb": 4096},
            "params": {"precision": "int4", "quantization_backend": "bitsandbytes"},
        }
    )
    main_model = next(item for item in snapshot if item["component_id"] == "main_model")
    assert main_model["backend"] == "bitsandbytes"
