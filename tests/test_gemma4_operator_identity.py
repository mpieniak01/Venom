"""The training target cannot silently follow a moving Ollama alias."""

from pathlib import Path

import pytest

from venom_core.services.gemma4_operator.identity import OLLAMA_TAG, bind_ollama
from venom_core.services.gemma4_operator.material import digest
from venom_core.services.gemma4_operator.profile import GemmaProfile

PROFILE = Path("config/gemma4_operator_profile.json")


def observed():
    return {
        "details": {
            "family": "gemma4",
            "format": "gguf",
            "quantization_level": "Q4_K_M",
        },
        "model_info": {
            "general.architecture": "gemma4",
            "general.parameter_count": 11907350576,
            "gemma4.block_count": 48,
            "gemma4.embedding_length": 3840,
            "general.base_model.0.repo_url": "https://huggingface.co/google/gemma-4-12B",
        },
        "capabilities": ["vision", "tools", "completion", "audio", "thinking"],
    }


def test_explicit_variant_is_bound_without_fabricating_vendor_revision():
    result = bind_ollama(
        GemmaProfile.load(PROFILE), {"name": OLLAMA_TAG, "digest": "a" * 64}, observed()
    )
    fingerprint = result.pop("binding_sha256")
    assert digest(result) == fingerprint
    assert result["vendor_source"]["checkpoint_revision_verified"] is False
    assert result["existing_vendor_blob_adapter_injection_qualified"] is False
    assert result["training_checkpoint"]["model"] == "google/gemma-4-12B-it"
    assert (
        result["deployment_strategy"]
        == "merge_exact_training_base_then_convert_and_import"
    )


@pytest.mark.parametrize("tag", ["gemma4:latest", "gemma4:e4b", "gemma4:12b"])
def test_alias_does_not_select_a_different_training_model(tag):
    profile = GemmaProfile.load(PROFILE)
    model = {"name": tag, "digest": "a" * 64}
    data = observed()
    with pytest.raises(ValueError, match="explicit_12b"):
        bind_ollama(profile, model, data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("general.parameter_count", 7500000000),
        ("gemma4.block_count", 35),
        ("gemma4.embedding_length", 2560),
    ],
)
def test_other_architecture_cannot_be_accepted(key, value):
    profile = GemmaProfile.load(PROFILE)
    model = {"name": OLLAMA_TAG, "digest": "a" * 64}
    data = observed()
    data["model_info"][key] = value
    with pytest.raises(ValueError, match="architecture_mismatch"):
        bind_ollama(profile, model, data)


def test_text_only_backend_cannot_claim_multimodal_binding():
    profile = GemmaProfile.load(PROFILE)
    model = {"name": OLLAMA_TAG, "digest": "a" * 64}
    data = observed()
    data["capabilities"] = ["completion"]
    with pytest.raises(ValueError, match="capabilities_missing"):
        bind_ollama(profile, model, data)
