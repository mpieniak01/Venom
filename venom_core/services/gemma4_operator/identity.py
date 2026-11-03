"""Bind an explicitly selected Ollama variant to the training checkpoint."""

from __future__ import annotations

import re
from typing import Any

from .material import digest
from .profile import GemmaProfile

OLLAMA_TAG = "gemma4:12b-it-q4_K_M"
_SHA = re.compile(r"[a-f0-9]{64}")


def bind_ollama(
    profile: GemmaProfile, model: dict[str, Any], observed: dict[str, Any]
) -> dict[str, Any]:
    """Check vendor metadata without claiming to recover a source from quantization."""
    profile.validate()
    if not isinstance(model, dict) or not isinstance(observed, dict):
        raise ValueError("gemma_binding_metadata_invalid")
    if model.get("name") != OLLAMA_TAG:
        raise ValueError("gemma_binding_explicit_12b_tag_required")
    raw_digest = model.get("digest")
    if not isinstance(raw_digest, str):
        raise ValueError("gemma_binding_digest_invalid")
    fingerprint = raw_digest.removeprefix("sha256:")
    if not _SHA.fullmatch(fingerprint):
        raise ValueError("gemma_binding_digest_invalid")
    details = observed.get("details", {})
    info = observed.get("model_info", {})
    if not isinstance(details, dict) or not isinstance(info, dict):
        raise ValueError("gemma_binding_metadata_invalid")
    expected = {
        "general.architecture": "gemma4",
        "general.parameter_count": 11907350576,
        "gemma4.block_count": 48,
        "gemma4.embedding_length": 3840,
    }
    if any(info.get(key) != value for key, value in expected.items()):
        raise ValueError("gemma_binding_architecture_mismatch")
    if (
        details.get("family") != "gemma4"
        or details.get("quantization_level") != "Q4_K_M"
        or details.get("format") != "gguf"
    ):
        raise ValueError("gemma_binding_variant_mismatch")
    capabilities = observed.get("capabilities", [])
    if not isinstance(capabilities, list) or not all(
        isinstance(v, str) for v in capabilities
    ):
        raise ValueError("gemma_binding_capabilities_invalid")
    if not {"completion", "vision", "tools"} <= set(capabilities):
        raise ValueError("gemma_binding_capabilities_missing")
    result = {
        "schema_version": 1,
        "kind": "gemma4_training_runtime_binding",
        "training_checkpoint": profile.identity(),
        "ollama": {
            "tag": OLLAMA_TAG,
            "digest": fingerprint,
            "format": details.get("format"),
            "quantization": "Q4_K_M",
            "architecture": expected,
            "capabilities": sorted(set(capabilities)),
        },
        "vendor_source": {
            "base_repository": info.get("general.base_model.0.repo_url"),
            "checkpoint_revision_verified": False,
            "qualification": "vendor_tag_and_architecture_metadata_only",
        },
        "deployment_strategy": "merge_exact_training_base_then_convert_and_import",
        "existing_vendor_blob_adapter_injection_qualified": False,
        "required_evaluations": ["tools", "summary", "translation", "vision", "audio"],
        "training_started": False,
        "activation_authorized": False,
    }
    result["binding_sha256"] = digest(result)
    return result
