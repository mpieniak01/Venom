"""Runtime identity evidence is consistent without claiming live qualification."""

from dataclasses import replace
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator.profile import GemmaProfile
from venom_core.services.gemma4_operator.runtime import (
    expected_identity,
    readiness_report,
    registry_metadata,
)


def profile():
    return GemmaProfile.load(Path("config/gemma4_operator_profile.json"))


def requested():
    return {
        "precision": "nf4",
        "backend": "transformers",
        "backend_version": "5.17.0",
        "artifact_sha256": "a" * 64,
    }


def observed():
    identity = expected_identity(profile(), requested())
    return {
        "identity": identity,
        "stages": [
            {"stage": name, "identity": dict(identity)}
            for name in ("interpret", "plan", "act", "finish")
        ],
    }


def test_preparation_never_claims_installed_active_or_trained():
    result = readiness_report(profile(), requested())
    assert result["status"] == "PREPARED"
    assert result["training_state"] == "deferred_remote"
    assert result["registry_metadata"]["status"] == "available"
    assert result["registry_metadata"]["runtime"] == "multi_runtime"
    assert result["registry_metadata"]["local_path"] is None
    assert result["registry_metadata"]["installed_at"] is None
    assert not result["activation_ready"]
    assert not result["same_model_evidence_consistent"]


def test_matching_evidence_is_not_gpu_or_tool_loop_qualification():
    result = readiness_report(profile(), requested(), observed())
    assert result["status"] == "IDENTITY_MATCH"
    assert result["stage_count"] == 4
    assert result["same_model_evidence_consistent"]
    assert not result["gpu_qualified"]
    assert not result["tool_loop_qualified"]
    assert not result["activation_ready"]
    assert not result["training_authorized"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "google/gemma-4-E4B-it"),
        ("revision", "b" * 40),
        ("loader", "AutoModelForCausalLM"),
        ("precision", "bf16"),
        ("backend", "ollama"),
        ("backend_version", "5.18.0"),
        ("artifact_sha256", "b" * 64),
        ("context", True),
        ("enable_thinking", True),
        ("files", {}),
    ],
)
def test_each_effective_identity_field_must_match(field, value):
    data = observed()
    data["identity"][field] = value
    result = readiness_report(profile(), requested(), data)
    assert result["status"] == "MISMATCH"
    assert "runtime." + field in result["mismatches"]
    assert not result["same_model_evidence_consistent"]


def test_same_model_in_initial_response_does_not_allow_stage_fallback():
    data = observed()
    data["stages"][2]["identity"]["model"] = "different/model"
    result = readiness_report(profile(), requested(), data)
    assert result["status"] == "MISMATCH"
    assert result["mismatches"] == ["stages[2].model"]
    assert not result["same_model_evidence_consistent"]


@pytest.mark.parametrize(
    "data,error",
    [
        ({}, "runtime.identity_missing"),
        ({"identity": {}}, "runtime.model"),
        ({"identity": None}, "runtime.identity_missing"),
    ],
)
def test_missing_evidence_cannot_qualify(data, error):
    result = readiness_report(profile(), requested(), data)
    assert result["status"] == "MISMATCH"
    assert error in result["mismatches"]


@pytest.mark.parametrize("stages", [None, {}, [{"stage": ""}], [None]])
def test_invalid_stage_evidence_fails_closed(stages):
    data = observed()
    data["stages"] = stages
    result = readiness_report(profile(), requested(), data)
    assert result["status"] == "MISMATCH"


def test_identity_only_evidence_does_not_claim_same_model_loop():
    result = readiness_report(
        profile(), requested(), {"identity": expected_identity(profile(), requested())}
    )
    assert result["status"] == "IDENTITY_MATCH"
    assert not result["same_model_evidence_consistent"]


@pytest.mark.parametrize(
    "change",
    [
        {"precision": ""},
        {"precision": "fp10"},
        {"precision": "gguf-q4_k_m"},
        {"backend": " shell command "},
        {"backend_version": None},
        {"artifact_sha256": "a" * 63},
    ],
)
def test_invalid_requested_config_rejected_before_io(change):
    with pytest.raises(ValueError, match="gemma_runtime_"):
        readiness_report(profile(), {**requested(), **change})


def test_unknown_or_missing_requested_fields_are_rejected():
    with pytest.raises(ValueError, match="request_fields_invalid"):
        expected_identity(profile(), {**requested(), "activation_ready": True})
    with pytest.raises(ValueError, match="request_fields_invalid"):
        expected_identity(profile(), {})


def test_profile_context_is_qualified_limit_not_advertised_maximum():
    configured = replace(profile(), context=2048)
    entry = registry_metadata(configured)
    assert entry["capabilities"]["max_context_length"] == 2048
    assert entry["capabilities"]["supports_function_calling"]
    assert "tool" in entry["capabilities"]["allowed_roles"]


def test_one_stage_or_repeated_stage_cannot_claim_same_model_across_stages():
    for stages in ([{"stage": "act"}], [{"stage": "act"}, {"stage": "act"}]):
        identity = expected_identity(profile(), requested())
        data = {
            "identity": identity,
            "stages": [{**stage, "identity": dict(identity)} for stage in stages],
        }
        result = readiness_report(profile(), requested(), data)
        assert result["status"] == "IDENTITY_MATCH"
        assert not result["same_model_evidence_consistent"]


def test_observation_not_mapping_is_explicit_mismatch():
    assert readiness_report(profile(), requested(), [])["mismatches"] == [
        "runtime.observation_invalid"
    ]


@pytest.mark.parametrize("model", ["google/gemma-4-12B-it", "gemma-4-12b-it"])
def test_unqualified_gemma_is_not_local_academy_trainable(model):
    from venom_core.services.academy.trainable_catalog_service import (
        get_model_non_trainable_reason,
    )

    for metadata in (None, {"training_runtime": "huggingface"}):
        assert (
            get_model_non_trainable_reason(
                model, provider="huggingface", model_metadata=metadata
            )
            == "Gemma 4 12B training is deferred to remote host qualification"
        )


def test_existing_other_hf_models_keep_trainability_policy():
    from venom_core.services.academy.trainable_catalog_service import (
        get_model_non_trainable_reason,
    )

    assert (
        get_model_non_trainable_reason("google/gemma-3-4b-it", provider="huggingface")
        is None
    )


def test_mutated_profile_is_revalidated_before_exposing_registry_or_identity():
    invalid = profile()
    object.__setattr__(invalid, "model", "unrelated/model")
    with pytest.raises(ValueError, match="gemma_profile_model_invalid"):
        expected_identity(invalid, requested())
    with pytest.raises(ValueError, match="gemma_profile_model_invalid"):
        registry_metadata(invalid)
