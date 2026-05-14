"""Testy kontraktu Fazy 1 (217B): multi_runtime_profile_service.

Weryfikują:
1. Rozdzielenie semantyki systemu (full|light|llm_off) od multi_runtime_profile.
2. Poprawność macierzy apply_mode.
3. Walidację partial-update: pola akceptowane / odrzucane.
4. Budowę profilu z parametrów demona.
5. Brak kolizji nazw między systemowym profilem a profilem runtime.
"""

from __future__ import annotations

import pytest

from venom_core.api.schemas.multi_runtime_profile import (
    MultiRuntimeApplyMatrix,
    MultiRuntimeProfile,
    MultiRuntimeProfileUpdateRequest,
)
from venom_core.services.multi_runtime_profile_service import (
    APPLY_MATRIX,
    SYSTEM_RUNTIME_PROFILES,
    apply_mode_for_field,
    assert_not_system_profile,
    build_default_profile,
    build_profile_from_daemon_params,
    build_profile_response,
    is_system_runtime_profile,
    required_apply_mode,
    validate_profile_update,
)

# ---------------------------------------------------------------------------
# Macierz apply_mode
# ---------------------------------------------------------------------------


def test_apply_matrix_live_fields():
    live_fields = [
        "max_new_tokens",
        "enable_thinking",
        "image_token_budget",
        "reasoning_summary_enabled",
        "emotion_detection_enabled",
        "emotion_response_style_enabled",
    ]
    for field in live_fields:
        assert apply_mode_for_field(field) == "live", f"{field} should be live"


def test_apply_matrix_soft_reload_fields():
    assert apply_mode_for_field("cache_implementation") == "soft_reload"


def test_apply_matrix_hard_restart_fields():
    assert apply_mode_for_field("model_id") == "hard_restart"
    assert apply_mode_for_field("assistant_model_id") == "hard_restart"


def test_apply_matrix_unsupported_fields():
    unsupported = ["precision", "quantization_backend", "device_target"]
    for field in unsupported:
        assert apply_mode_for_field(field) == "unsupported", (
            f"{field} should be unsupported"
        )


def test_apply_matrix_unknown_field_returns_unsupported():
    assert apply_mode_for_field("nonexistent_field") == "unsupported"


def test_apply_matrix_covers_all_profile_fields():
    profile_fields = set(MultiRuntimeProfile.model_fields) - {
        "profile_id",
        "display_name",
        "runtime_id",
        "compatibility",
    }
    matrix_fields = set(APPLY_MATRIX)
    assert profile_fields == matrix_fields, (
        f"Missing from APPLY_MATRIX: {profile_fields - matrix_fields}, "
        f"extra in APPLY_MATRIX: {matrix_fields - profile_fields}"
    )


def test_apply_matrix_schema_matches_service():
    schema_matrix = MultiRuntimeApplyMatrix()
    for field, mode in APPLY_MATRIX.items():
        assert getattr(schema_matrix, field) == mode, (
            f"Schema and service disagree on {field}: "
            f"schema={getattr(schema_matrix, field)}, service={mode}"
        )


# ---------------------------------------------------------------------------
# required_apply_mode — hierarchia trybów
# ---------------------------------------------------------------------------


def test_required_apply_mode_all_live():
    assert required_apply_mode(["max_new_tokens", "enable_thinking"]) == "live"


def test_required_apply_mode_soft_reload_wins_over_live():
    assert (
        required_apply_mode(["max_new_tokens", "cache_implementation"]) == "soft_reload"
    )


def test_required_apply_mode_hard_restart_wins_over_all():
    assert (
        required_apply_mode(["max_new_tokens", "cache_implementation", "model_id"])
        == "hard_restart"
    )


def test_required_apply_mode_only_unsupported_returns_unsupported():
    assert required_apply_mode(["precision", "quantization_backend"]) == "unsupported"


def test_required_apply_mode_unsupported_ignored_when_accepted_present():
    result = required_apply_mode(["max_new_tokens", "precision"])
    assert result == "live"


def test_required_apply_mode_empty_list():
    assert required_apply_mode([]) == "unsupported"


# ---------------------------------------------------------------------------
# Budowanie profilu
# ---------------------------------------------------------------------------


def test_build_default_profile_uses_model_id():
    p = build_default_profile("google/gemma-4-E2B-it")
    assert p.model_id == "google/gemma-4-E2B-it"
    assert p.runtime_id == "multi_runtime"
    assert p.compatibility == "multi_runtime_native"
    assert p.assistant_model_id is None


def test_build_profile_from_daemon_params():
    p = build_profile_from_daemon_params(
        target_model="google/gemma-4-E2B-it",
        assistant_model="google/gemma-4-1B-it",
        daemon_params={
            "max_new_tokens": 256,
            "enable_thinking": True,
            "image_token_budget": 560,
            "reasoning_summary_enabled": True,
            "emotion_detection_enabled": False,
            "emotion_response_style_enabled": False,
            "cache_implementation": "static",
        },
    )
    assert p.model_id == "google/gemma-4-E2B-it"
    assert p.assistant_model_id == "google/gemma-4-1B-it"
    assert p.max_new_tokens == 256
    assert p.enable_thinking is True
    assert p.image_token_budget == 560
    assert p.reasoning_summary_enabled is True
    assert p.cache_implementation == "static"


def test_build_profile_response_envelope():
    p = build_default_profile("test/model")
    resp = build_profile_response(p, daemon_reachable=True)
    assert resp.runtime_id == "multi_runtime"
    assert resp.profile is p
    assert resp.daemon_reachable is True
    assert resp.apply_matrix is not None
    assert resp.supported_options is not None


# ---------------------------------------------------------------------------
# Walidacja partial-update
# ---------------------------------------------------------------------------


def test_validate_live_fields_accepted():
    req = MultiRuntimeProfileUpdateRequest(
        max_new_tokens=256,
        enable_thinking=True,
        image_token_budget=560,
    )
    result = validate_profile_update(req)
    assert result.rejected == []
    assert result.accepted["max_new_tokens"] == 256
    assert result.accepted["enable_thinking"] is True
    assert result.required_apply_mode == "live"
    assert result.applied is False


def test_validate_soft_reload_field_accepted():
    req = MultiRuntimeProfileUpdateRequest(cache_implementation="static")
    result = validate_profile_update(req)
    assert result.rejected == []
    assert result.accepted["cache_implementation"] == "static"
    assert result.required_apply_mode == "soft_reload"


def test_validate_model_id_requires_hard_restart():
    req = MultiRuntimeProfileUpdateRequest(model_id="google/gemma-4-1B-it")
    result = validate_profile_update(req)
    assert result.rejected == []
    assert result.required_apply_mode == "hard_restart"


def test_validate_unsupported_precision_rejected():
    req = MultiRuntimeProfileUpdateRequest(precision="int4")
    result = validate_profile_update(req)
    assert len(result.rejected) == 1
    assert result.rejected[0].field == "precision"
    assert result.rejected[0].reason == "precision_not_supported_for_runtime"
    assert result.accepted == {}
    assert result.required_apply_mode == "unsupported"


def test_validate_quantization_backend_rejected():
    req = MultiRuntimeProfileUpdateRequest(quantization_backend="bitsandbytes")
    result = validate_profile_update(req)
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == "quantization_backend_unavailable"


def test_validate_device_target_rejected():
    req = MultiRuntimeProfileUpdateRequest(device_target="cuda")
    result = validate_profile_update(req)
    assert len(result.rejected) == 1
    assert result.rejected[0].field == "device_target"
    assert result.rejected[0].reason == "unsupported_field"


def test_validate_mixed_accepted_and_rejected():
    req = MultiRuntimeProfileUpdateRequest(
        max_new_tokens=512,
        precision="int4",
        quantization_backend="bitsandbytes",
    )
    result = validate_profile_update(req)
    assert "max_new_tokens" in result.accepted
    assert len(result.rejected) == 2
    assert result.required_apply_mode == "live"


def test_validate_invalid_cache_implementation_rejected():
    req = MultiRuntimeProfileUpdateRequest(cache_implementation="nonexistent_strategy")
    result = validate_profile_update(req)
    assert len(result.rejected) == 1
    assert result.rejected[0].field == "cache_implementation"
    assert result.rejected[0].reason == "unsupported_combination"


def test_validate_none_cache_implementation_accepted():
    req = MultiRuntimeProfileUpdateRequest(cache_implementation=None)
    result = validate_profile_update(req)
    assert result.rejected == []
    assert result.accepted == {}


def test_validate_empty_request():
    req = MultiRuntimeProfileUpdateRequest()
    result = validate_profile_update(req)
    assert result.accepted == {}
    assert result.rejected == []
    assert result.required_apply_mode == "unsupported"


# ---------------------------------------------------------------------------
# Rozdzielenie profili systemowych od multi_runtime_profile
# ---------------------------------------------------------------------------


def test_system_runtime_profiles_constant():
    assert SYSTEM_RUNTIME_PROFILES == {"full", "light", "llm_off"}


def test_is_system_runtime_profile_recognizes_all_system_profiles():
    assert is_system_runtime_profile("full") is True
    assert is_system_runtime_profile("light") is True
    assert is_system_runtime_profile("llm_off") is True


def test_is_system_runtime_profile_case_insensitive():
    assert is_system_runtime_profile("FULL") is True
    assert is_system_runtime_profile("Light") is True


def test_is_system_runtime_profile_rejects_multi_runtime_names():
    assert is_system_runtime_profile("multi_runtime") is False
    assert is_system_runtime_profile("default") is False
    assert is_system_runtime_profile("low_vram") is False
    assert is_system_runtime_profile("") is False
    assert is_system_runtime_profile(None) is False  # type: ignore[arg-type]


def test_assert_not_system_profile_passes_for_multi_runtime_names():
    assert_not_system_profile("default")
    assert_not_system_profile("low_vram")
    assert_not_system_profile("multi_runtime")


def test_assert_not_system_profile_raises_for_system_profiles():
    for name in ("full", "light", "llm_off"):
        with pytest.raises(ValueError, match="system runtime profile"):
            assert_not_system_profile(name)


# ---------------------------------------------------------------------------
# Kontrakt regresji: profile schema ma runtime_id=multi_runtime
# ---------------------------------------------------------------------------


def test_profile_runtime_id_is_multi_runtime():
    p = build_default_profile("any/model")
    assert p.runtime_id == "multi_runtime"


def test_profile_compatibility_is_multi_runtime_native():
    p = build_default_profile("any/model")
    assert p.compatibility == "multi_runtime_native"
