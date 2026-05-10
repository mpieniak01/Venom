from venom_core.core.ollama_runtime_capabilities import normalize_ollama_show_payload


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
