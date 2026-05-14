from services.multi_runtime.components import build_component_snapshot
from services.multi_runtime.pipeline import MultiRuntimePipeline, PipelineRequestData
from services.multi_runtime.policies import RuntimePolicyResolver
from services.multi_runtime.router import route_inputs


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


class _Payload:
    task = None
    question = None
    system_prompt = None
    max_new_tokens = 64
    temperature = None
    top_p = None
    do_sample = None


def test_pipeline_trace_includes_retrieval_stage() -> None:
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
