"""
Tests for runtime profile configuration and capabilities contract.
"""

import pytest

from venom_core.services.profile_config import (
    RuntimeProfile,
    get_profile_capabilities,
    get_profile_description,
    validate_profile_requirements,
)


class TestRuntimeProfile:
    """Test RuntimeProfile enum and conversions."""

    def test_from_string_light(self):
        """Test parsing light profile variations."""
        assert RuntimeProfile.from_string("light") == RuntimeProfile.LIGHT
        assert RuntimeProfile.from_string("LIGHT") == RuntimeProfile.LIGHT
        assert RuntimeProfile.from_string("Light") == RuntimeProfile.LIGHT
        assert RuntimeProfile.from_string("privacy") == RuntimeProfile.LIGHT
        assert RuntimeProfile.from_string("local") == RuntimeProfile.LIGHT

    def test_from_string_llm_off(self):
        """Test parsing llm_off/api profile variations."""
        assert RuntimeProfile.from_string("llm_off") == RuntimeProfile.LLM_OFF
        assert RuntimeProfile.from_string("LLM_OFF") == RuntimeProfile.LLM_OFF
        assert RuntimeProfile.from_string("api") == RuntimeProfile.LLM_OFF
        assert RuntimeProfile.from_string("API") == RuntimeProfile.LLM_OFF
        assert RuntimeProfile.from_string("cloud") == RuntimeProfile.LLM_OFF

    def test_from_string_full(self):
        """Test parsing full profile variations."""
        assert RuntimeProfile.from_string("full") == RuntimeProfile.FULL
        assert RuntimeProfile.from_string("FULL") == RuntimeProfile.FULL
        assert RuntimeProfile.from_string("beast") == RuntimeProfile.FULL
        assert RuntimeProfile.from_string("extended") == RuntimeProfile.FULL

    def test_from_string_invalid(self):
        """Test error handling for invalid profile names."""
        with pytest.raises(ValueError, match="Unknown profile"):
            RuntimeProfile.from_string("invalid")
        with pytest.raises(ValueError, match="Unknown profile"):
            RuntimeProfile.from_string("unknown")
        with pytest.raises(ValueError, match="Unknown profile"):
            RuntimeProfile.from_string("")


class TestProfileCapabilities:
    """Test profile capabilities contract."""

    def test_light_capabilities(self):
        """Test LIGHT profile capabilities."""
        caps = get_profile_capabilities(RuntimeProfile.LIGHT)
        
        assert caps.profile == RuntimeProfile.LIGHT
        assert "backend" in caps.required_services
        assert "frontend" in caps.required_services
        assert "ollama" in caps.required_services
        assert "vllm" in caps.disabled_services
        assert caps.uses_local_llm is True
        assert caps.gpu_support is True
        assert caps.requires_onnx is False
        assert caps.env_overrides["ACTIVE_LLM_SERVER"] == "ollama"
        assert caps.env_overrides["LLM_WARMUP_ON_STARTUP"] == "true"
        assert len(caps.required_api_keys) == 0

    def test_llm_off_capabilities(self):
        """Test LLM_OFF profile capabilities."""
        caps = get_profile_capabilities(RuntimeProfile.LLM_OFF)
        
        assert caps.profile == RuntimeProfile.LLM_OFF
        assert "backend" in caps.required_services
        assert "frontend" in caps.required_services
        assert "ollama" in caps.disabled_services
        assert "vllm" in caps.disabled_services
        assert caps.uses_local_llm is False
        assert caps.gpu_support is False
        assert caps.requires_onnx is False
        assert caps.env_overrides["ACTIVE_LLM_SERVER"] == "none"
        assert caps.env_overrides["LLM_WARMUP_ON_STARTUP"] == "false"
        assert len(caps.required_api_keys) > 0
        assert "OPENAI_API_KEY" in caps.required_api_keys

    def test_full_capabilities(self):
        """Test FULL profile capabilities."""
        caps = get_profile_capabilities(RuntimeProfile.FULL)
        
        assert caps.profile == RuntimeProfile.FULL
        assert "backend" in caps.required_services
        assert "frontend" in caps.required_services
        assert "ollama" in caps.required_services
        assert caps.uses_local_llm is True
        assert caps.gpu_support is True
        assert caps.requires_onnx is False
        assert caps.env_overrides["ACTIVE_LLM_SERVER"] == "ollama"
        assert len(caps.required_api_keys) == 0


class TestProfileDescriptions:
    """Test profile description localization."""

    def test_english_descriptions(self):
        """Test English profile descriptions."""
        light_desc = get_profile_description(RuntimeProfile.LIGHT, "en")
        assert "Ollama" in light_desc
        assert "Privacy First" in light_desc
        
        api_desc = get_profile_description(RuntimeProfile.LLM_OFF, "en")
        assert "OpenAI" in api_desc or "Cloud" in api_desc
        assert "Low Hardware" in api_desc
        
        full_desc = get_profile_description(RuntimeProfile.FULL, "en")
        assert "Beast" in full_desc or "Extended" in full_desc

    def test_polish_descriptions(self):
        """Test Polish profile descriptions."""
        light_desc = get_profile_description(RuntimeProfile.LIGHT, "pl")
        assert "Ollama" in light_desc
        assert "Privacy First" in light_desc
        
        api_desc = get_profile_description(RuntimeProfile.LLM_OFF, "pl")
        assert "OpenAI" in api_desc or "cloud" in api_desc

    def test_german_descriptions(self):
        """Test German profile descriptions."""
        light_desc = get_profile_description(RuntimeProfile.LIGHT, "de")
        assert "Ollama" in light_desc
        assert "Privacy First" in light_desc

    def test_default_language(self):
        """Test default language fallback to English."""
        desc = get_profile_description(RuntimeProfile.LIGHT)
        assert len(desc) > 0
        # Should be English by default
        assert "Local" in desc or "Ollama" in desc


class TestProfileValidation:
    """Test profile requirements validation."""

    def test_light_validation_no_api_keys(self):
        """Test LIGHT profile doesn't require API keys."""
        is_valid, error = validate_profile_requirements(
            RuntimeProfile.LIGHT, 
            available_api_keys=set()
        )
        assert is_valid is True
        assert error is None

    def test_llm_off_validation_with_api_key(self):
        """Test LLM_OFF profile validation with API key."""
        is_valid, error = validate_profile_requirements(
            RuntimeProfile.LLM_OFF,
            available_api_keys={"OPENAI_API_KEY"}
        )
        assert is_valid is True
        assert error is None

    def test_llm_off_validation_without_api_key(self):
        """Test LLM_OFF profile validation without API key."""
        is_valid, error = validate_profile_requirements(
            RuntimeProfile.LLM_OFF,
            available_api_keys=set()
        )
        assert is_valid is False
        assert error is not None
        assert "requires at least one of" in error.lower()

    def test_llm_off_validation_with_any_key(self):
        """Test LLM_OFF accepts any of the supported API keys."""
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]:
            is_valid, error = validate_profile_requirements(
                RuntimeProfile.LLM_OFF,
                available_api_keys={key}
            )
            assert is_valid is True, f"Should accept {key}"
            assert error is None

    def test_full_validation_no_api_keys(self):
        """Test FULL profile doesn't require API keys."""
        is_valid, error = validate_profile_requirements(
            RuntimeProfile.FULL,
            available_api_keys=set()
        )
        assert is_valid is True
        assert error is None


class TestProfileContract:
    """Test profile contract consistency."""

    def test_all_profiles_have_descriptions(self):
        """Ensure all profiles have descriptions in all languages."""
        for profile in RuntimeProfile:
            caps = get_profile_capabilities(profile)
            assert len(caps.description_en) > 0
            assert len(caps.description_pl) > 0
            assert len(caps.description_de) > 0

    def test_all_profiles_have_services(self):
        """Ensure all profiles define required services."""
        for profile in RuntimeProfile:
            caps = get_profile_capabilities(profile)
            # All profiles should have at least backend and frontend
            assert "backend" in caps.required_services
            assert "frontend" in caps.required_services

    def test_llm_profiles_mutual_exclusion(self):
        """Test that profiles using LLM disable the opposite LLM service."""
        light = get_profile_capabilities(RuntimeProfile.LIGHT)
        full = get_profile_capabilities(RuntimeProfile.FULL)
        llm_off = get_profile_capabilities(RuntimeProfile.LLM_OFF)
        
        # LIGHT should have ollama, disable vllm
        assert "ollama" in light.required_services
        assert "vllm" in light.disabled_services
        
        # LLM_OFF should disable both
        assert "ollama" in llm_off.disabled_services
        assert "vllm" in llm_off.disabled_services
        
        # FULL should have ollama by default
        assert "ollama" in full.required_services

    def test_onnx_requirements_consistent(self):
        """Test ONNX requirements are consistent across profiles."""
        light = get_profile_capabilities(RuntimeProfile.LIGHT)
        llm_off = get_profile_capabilities(RuntimeProfile.LLM_OFF)
        full = get_profile_capabilities(RuntimeProfile.FULL)
        
        # None of the default profiles require ONNX
        assert light.requires_onnx is False
        assert llm_off.requires_onnx is False
        assert full.requires_onnx is False

    def test_api_key_requirements_only_for_cloud(self):
        """Test only cloud/API profile requires API keys."""
        light = get_profile_capabilities(RuntimeProfile.LIGHT)
        full = get_profile_capabilities(RuntimeProfile.FULL)
        llm_off = get_profile_capabilities(RuntimeProfile.LLM_OFF)
        
        # Local LLM profiles shouldn't require API keys
        assert len(light.required_api_keys) == 0
        assert len(full.required_api_keys) == 0
        
        # Cloud profile should require API keys
        assert len(llm_off.required_api_keys) > 0
