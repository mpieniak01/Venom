"""CPU-only evidence checks for one Gemma model across Venom task stages.

A matching report establishes identity consistency only. It cannot qualify GPU
execution, authorize training, or activate a model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from venom_core.core.model_registry_types import (
    ModelCapabilities,
    ModelMetadata,
    ModelProvider,
    ModelStatus,
)
from venom_core.services.gemma4_operator.profile import GemmaProfile
from venom_core.utils.runtime_names import MULTI_RUNTIME_ID

_REQUEST_FIELDS = frozenset(
    {"precision", "backend", "backend_version", "artifact_sha256"}
)
_PRECISIONS = frozenset({"bf16", "nf4"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}")


def expected_identity(
    profile: GemmaProfile, requested: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind the runtime request to the immutable model and asset profile."""
    profile.validate()
    if not isinstance(requested, Mapping) or set(requested) != _REQUEST_FIELDS:
        raise ValueError("gemma_runtime_request_fields_invalid")
    for name in ("precision", "backend", "backend_version"):
        value = requested[name]
        if not isinstance(value, str) or not _LABEL.fullmatch(value):
            raise ValueError("gemma_runtime_request_label_invalid:" + name)
    if requested["precision"] not in _PRECISIONS:
        raise ValueError("gemma_runtime_precision_unsupported")
    artifact = requested["artifact_sha256"]
    if not isinstance(artifact, str) or not _SHA256.fullmatch(artifact):
        raise ValueError("gemma_runtime_artifact_hash_invalid")
    return {
        "model": profile.model,
        "revision": profile.revision,
        "loader": profile.loader,
        "context": profile.context,
        "enable_thinking": profile.enable_thinking,
        "files": dict(profile.files),
        **dict(requested),
    }


def registry_metadata(profile: GemmaProfile) -> dict[str, Any]:
    """Describe a candidate without installing or activating it in the registry."""
    profile.validate()
    metadata = ModelMetadata(
        name=profile.model,
        provider=ModelProvider.HUGGINGFACE,
        display_name=(
            "Gemma 4 E4B IT" if profile.model.endswith("E4B-it") else "Gemma 4 12B IT"
        ),
        status=ModelStatus.AVAILABLE,
        runtime=MULTI_RUNTIME_ID,
        capabilities=ModelCapabilities(
            supports_system_role=True,
            supports_function_calling=True,
            allowed_roles=["system", "user", "assistant", "tool"],
            max_context_length=profile.context,
        ),
    )
    return metadata.to_dict()


def _identity_mismatches(
    expected: Mapping[str, Any], observed: Any, prefix: str
) -> list[str]:
    if not isinstance(observed, Mapping):
        return [prefix + ".identity_missing"]
    mismatches = []
    for name, value in expected.items():
        actual = observed.get(name)
        # bool is an int subclass: True must not attest a numeric context.
        if type(actual) is not type(value) or actual != value:
            mismatches.append(prefix + "." + name)
    return mismatches


def _stage_mismatches(
    expected: Mapping[str, Any], stages: Any
) -> tuple[list[str], list[str]]:
    if not isinstance(stages, list):
        return ["stages.invalid"], []
    mismatches = []
    names = []
    for index, stage in enumerate(stages):
        prefix = f"stages[{index}]"
        if (
            not isinstance(stage, Mapping)
            or not isinstance(stage.get("stage"), str)
            or not _LABEL.fullmatch(stage["stage"])
        ):
            mismatches.append(prefix + ".stage_invalid")
            continue
        names.append(stage["stage"])
        mismatches.extend(_identity_mismatches(expected, stage.get("identity"), prefix))
    return mismatches, names


def readiness_report(
    profile: GemmaProfile,
    requested: Mapping[str, Any],
    observed: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate supplied backend evidence; never contact a server or load weights."""
    expected = expected_identity(profile, requested)
    mismatches: list[str] = []
    stage_names: list[str] = []
    if observed is not None:
        if not isinstance(observed, Mapping):
            mismatches.append("runtime.observation_invalid")
        else:
            mismatches.extend(
                _identity_mismatches(expected, observed.get("identity"), "runtime")
            )
            stage_errors, stage_names = _stage_mismatches(
                expected, observed.get("stages", [])
            )
            mismatches.extend(stage_errors)
    if observed is None:
        status = "PREPARED"
    elif mismatches:
        status = "MISMATCH"
    else:
        status = "IDENTITY_MATCH"
    return {
        "schema_version": 1,
        "status": status,
        "evidence_scope": "supplied_identity_only",
        "expected": expected,
        "mismatches": mismatches,
        "stage_count": len(stage_names),
        "same_model_evidence_consistent": len(set(stage_names)) >= 2 and not mismatches,
        "registry_metadata": registry_metadata(profile),
        "activation_ready": False,
        "gpu_qualified": False,
        "tool_loop_qualified": False,
        "training_state": "deferred_remote",
        "training_authorized": False,
    }
