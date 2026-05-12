from venom_core.core.ollama_runtime_capabilities import (
    OllamaRuntimeCapabilities,
    _resolve_compatibility_profile,
    normalize_ollama_show_payload,
)


def test_normalize_ollama_show_payload_marks_legacy_text_only():
    payload = {
        "capabilities": ["completion"],
        "details": {
            "family": "gemma3",
            "parameter_size": "4B",
            "quantization_level": "Q4_K_M",
        },
        "model_info": {"general.context_length": 8192},
    }

    caps = normalize_ollama_show_payload(
        model_name="gemma3:4b",
        payload=payload,
        endpoint="http://localhost:11434",
    )

    assert caps.compatibility_profile == "legacy_text_only"
    assert caps.capabilities["text_completion"] is True
    assert caps.capabilities["vision_input"] is False
    assert caps.capabilities["audio_input"] is False
    assert caps.probe_status == "metadata_only"
    assert caps.context_length == 8192


def test_normalize_ollama_show_payload_marks_multimodal_audio():
    payload = {
        "capabilities": ["completion", "vision", "audio", "tools", "thinking"],
        "details": {
            "family": "gemma4",
            "parameter_size": "8.0B",
            "quantization_level": "Q4_K_M",
        },
        "model_info": {"gemma4.context_length": 131072},
    }

    caps = normalize_ollama_show_payload(
        model_name="gemma4:latest",
        payload=payload,
        endpoint="http://localhost:11434",
    )

    assert caps.compatibility_profile == "multimodal_audio"
    assert caps.capabilities["vision_input"] is True
    assert caps.capabilities["audio_input"] is True
    assert caps.capabilities["tool_calling"] is True
    assert caps.capabilities["thinking"] is True
    assert caps.fallbacks["stt"] == "faster_whisper"


def test_compatibility_profile_resolution_covers_all_profiles():
    assert _resolve_compatibility_profile({"audio"}) == "multimodal_audio"
    assert _resolve_compatibility_profile({"vision"}) == "vision_text"
    assert _resolve_compatibility_profile({"tools"}) == "text_tools"
    assert _resolve_compatibility_profile({"thinking"}) == "text_thinking"
    assert _resolve_compatibility_profile(set()) == "legacy_text_only"


def test_normalize_ollama_show_payload_handles_invalid_context_and_to_dict():
    caps = normalize_ollama_show_payload(
        model_name="fallback-model",
        payload={
            "capabilities": ["completion"],
            "details": {"parameter_size": "1B", "context_length": "not-a-number"},
            "model_info": {},
        },
        endpoint="http://localhost:11434/",
        probe_status="verified",
    )

    assert isinstance(caps, OllamaRuntimeCapabilities)
    assert caps.endpoint == "http://localhost:11434"
    assert caps.context_length is None
    payload = caps.to_dict()
    assert payload["model_name"] == "fallback-model"
    assert payload["probe_status"] == "verified"
    assert payload["capabilities"]["text_completion"] is True


def test_aggregate_probe_status_prefers_verified_for_optional_probe_failures():
    from venom_core.core.ollama_runtime_probe import _aggregate_probe_status

    assert _aggregate_probe_status({"show": {"status": "verified"}}) == "verified"
    assert (
        _aggregate_probe_status(
            {
                "show": {"status": "verified"},
                "audio": {"status": "metadata_only"},
            }
        )
        == "metadata_only"
    )
    assert (
        _aggregate_probe_status(
            {
                "show": {"status": "verified"},
                "thinking": {"status": "failed"},
            }
        )
        == "verified"
    )
    assert (
        _aggregate_probe_status(
            {
                "show": {"status": "metadata_only"},
                "vision": {"status": "metadata_only"},
            }
        )
        == "metadata_only"
    )
