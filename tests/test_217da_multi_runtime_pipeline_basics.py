from services.multi_runtime.components import build_component_snapshot
from services.multi_runtime.diagnostics import ExecutionDiagnostics
from services.multi_runtime.pipeline import MultiRuntimePipeline, PipelineRequestData
from services.multi_runtime.policies import RuntimePolicyResolver
from services.multi_runtime.router import route_inputs
from services.multi_runtime.stages.assistant_postprocess import (
    AssistantPostprocessStage,
)
from services.multi_runtime.stages.base import StageContext
from services.multi_runtime.stages.ocr_or_vision import OcrOrVisionStage
from services.multi_runtime.stages.retrieval import RetrievalStage


def _daemon_status(**overrides):
    base = {
        "target_model": "google/gemma-4-E2B-it",
        "assistant_model": None,
        "target_loaded": True,
        "assistant_loaded": False,
        "supports_image_input": True,
        "vram": {"backend": "cuda"},
    }
    base.update(overrides)
    return base


def test_policy_resolver_selects_vision_priority_for_image_only() -> None:
    policy = RuntimePolicyResolver().resolve(
        daemon_status=_daemon_status(), has_images=True, has_audio=False
    )
    assert policy.execution_mode == "vision_priority"
    assert policy.image_strategy == "vlm_only"


def test_route_inputs_classifies_audio_as_primary() -> None:
    route = route_inputs(
        text_content="co slychac",
        has_audio=True,
        image_count=1,
        image_strategy="vlm_only",
    )
    assert route.primary_modality == "audio"
    assert route.has_images is True


def test_component_snapshot_exposes_main_model() -> None:
    snapshot = build_component_snapshot(_daemon_status())
    component_ids = {item["component_id"] for item in snapshot}
    assert "main_model" in component_ids
    assert "retrieval_component" in component_ids


class _FakeEngine:
    model_id = "fake/model"

    def respond(self, *_args, **_kwargs):
        return "ok", 0.0


class _FakeDaemon:
    def respond_with_assistant(self, **_kwargs):
        return "assistant revised", 0.0


class _Payload:
    task = None
    question = None
    system_prompt = None
    max_new_tokens = 64
    temperature = None
    top_p = None
    do_sample = None


def test_pipeline_trace_includes_retrieval_stage(monkeypatch) -> None:
    class _FakeVectorStore:
        def search(self, query, limit=3):
            assert query == "test"
            assert limit == 3
            return [{"text": "retrieved chunk", "metadata": {}, "score": 0.1}]

    monkeypatch.setattr(
        "services.multi_runtime.stages.retrieval.VectorStore", _FakeVectorStore
    )
    daemon_status = _daemon_status(
        params={
            "enable_thinking": False,
            "cache_implementation": None,
            "execution_mode": "balanced",
            "image_strategy": "vlm_only",
            "retrieval_mode": "always",
            "audio_output_mode": "off",
            "assistant_mode": "off",
            "economy_mode": "off",
        }
    )
    result = MultiRuntimePipeline(_FakeEngine()).execute(
        daemon_status=daemon_status,
        request=PipelineRequestData(
            request_payload=_Payload(),
            text_content="test",
            audio_array=None,
            sample_rate=16000,
            images=[],
        ),
    )
    assert "retrieval" in result.diagnostics.trace_names()
    assert result.diagnostics.retrieval_used is True
    assert result.diagnostics.retrieval_context_items == 1


def test_component_snapshot_reflects_policy_modes(monkeypatch) -> None:
    monkeypatch.setenv("TTS_MODEL_PATH", "/tmp/missing-voice.onnx")
    snapshot = build_component_snapshot(
        _daemon_status(
            assistant_model="assistant/model",
            params={
                "retrieval_mode": "always",
                "audio_output_mode": "voice_first",
                "assistant_mode": "attached",
                "image_strategy": "ocr_first",
            },
        )
    )
    by_id = {item["component_id"]: item for item in snapshot}
    assert by_id["retrieval_component"]["enabled"] is True
    assert by_id["embedding_component"]["enabled"] is True
    assert by_id["tts_component"]["enabled"] is True
    assert by_id["assistant_model"]["enabled"] is True
    assert by_id["image_input"]["last_error"] is not None


def test_retrieval_stage_uses_vector_store_results(monkeypatch) -> None:
    class _FakeVectorStore:
        def search(self, query, limit=3):
            assert query == "jak dziala pamiec?"
            assert limit == 3
            return [
                {"text": "fragment 1", "metadata": {}, "score": 0.1},
                {"text": "fragment 2", "metadata": {}, "score": 0.2},
            ]

    monkeypatch.setattr(
        "services.multi_runtime.stages.retrieval.VectorStore", _FakeVectorStore
    )
    context = StageContext(
        request_payload=_Payload(),
        daemon_status=_daemon_status(params={"retrieval_mode": "always"}),
        text_content="jak dziala pamiec?",
        audio_array=None,
        sample_rate=16000,
        images=[],
        diagnostics=ExecutionDiagnostics(),
        state={
            "policy": RuntimePolicyResolver().resolve(
                daemon_status=_daemon_status(params={"retrieval_mode": "always"}),
                has_images=False,
                has_audio=False,
            )
        },
    )
    RetrievalStage().run(context)
    assert context.state["retrieval_context"] == "fragment 1\n\nfragment 2"
    assert context.diagnostics.retrieval_used is True
    assert context.diagnostics.retrieval_context_items == 2


def test_ocr_stage_degrades_when_backend_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(OcrOrVisionStage, "_ocr_available", staticmethod(lambda: False))
    policy = RuntimePolicyResolver().resolve(
        daemon_status=_daemon_status(params={"image_strategy": "ocr_first"}),
        has_images=True,
        has_audio=False,
    )
    context = StageContext(
        request_payload=_Payload(),
        daemon_status=_daemon_status(params={"image_strategy": "ocr_first"}),
        text_content="odczytaj",
        audio_array=None,
        sample_rate=16000,
        images=["fake-image"],
        diagnostics=ExecutionDiagnostics(),
        state={"policy": policy, "preprocessed_images": ["fake-image"]},
    )
    OcrOrVisionStage().run(context)
    assert context.state["image_execution_path"] == "vlm_only"
    assert context.diagnostics.selected_image_strategy == "vlm_only"
    assert context.diagnostics.degradation_reasons


def test_assistant_stage_uses_daemon_when_available() -> None:
    policy = RuntimePolicyResolver().resolve(
        daemon_status=_daemon_status(
            assistant_model="assistant/model",
            assistant_loaded=True,
            params={"assistant_mode": "attached"},
        ),
        has_images=False,
        has_audio=False,
    )
    context = StageContext(
        request_payload=_Payload(),
        daemon_status=_daemon_status(
            assistant_model="assistant/model",
            assistant_loaded=True,
            params={"assistant_mode": "attached"},
        ),
        text_content="hello",
        audio_array=None,
        sample_rate=16000,
        images=[],
        diagnostics=ExecutionDiagnostics(),
        state={"policy": policy, "generated_text": "draft"},
    )
    AssistantPostprocessStage(_FakeDaemon()).run(context)
    assert context.state["generated_text"] == "assistant revised"
    assert context.diagnostics.assistant_used is True


def test_retrieval_stage_marks_economy_mode_degradation() -> None:
    policy = RuntimePolicyResolver().resolve(
        daemon_status=_daemon_status(
            params={"retrieval_mode": "auto", "economy_mode": "auto"}
        ),
        has_images=False,
        has_audio=False,
    )
    context = StageContext(
        request_payload=_Payload(),
        daemon_status=_daemon_status(
            params={"retrieval_mode": "auto", "economy_mode": "auto"}
        ),
        text_content="dlaczego to dziala?",
        audio_array=None,
        sample_rate=16000,
        images=[],
        diagnostics=ExecutionDiagnostics(),
        state={"policy": policy},
    )
    RetrievalStage().run(context)
    assert context.diagnostics.economy_mode_activated is True
    assert context.diagnostics.degradation_reasons
