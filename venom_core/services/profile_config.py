"""
Profile configuration and capabilities contract for Venom runtime.

Defines the explicit semantics for each runtime profile:
- light: same selected provider and interactive features, background work paused
- llm_off: API/cloud-only (no local LLM), minimal hardware requirements
- full: configured application capabilities; provider selection is independent
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class RuntimeProfile(str, Enum):
    """Runtime profile types with explicit semantics."""

    LIGHT = "light"
    LLM_OFF = "llm_off"
    FULL = "full"

    @classmethod
    def from_string(cls, value: str) -> "RuntimeProfile":
        """Convert string to RuntimeProfile, handling aliases."""
        value_lower = value.lower().strip()
        if value_lower in ("light", "privacy", "local"):
            return cls.LIGHT
        elif value_lower in ("llm_off", "api", "cloud"):
            return cls.LLM_OFF
        elif value_lower in ("full", "beast", "extended"):
            return cls.FULL
        else:
            raise ValueError(
                f"Unknown profile: {value}. Expected: light|llm_off|api|full"
            )


@dataclass(frozen=True)
class ProfileCapabilities:
    """Capabilities and constraints for a runtime profile."""

    profile: RuntimeProfile
    # Services that should be running
    required_services: Set[str] = field(default_factory=set)
    # Services that should be stopped/disabled
    disabled_services: Set[str] = field(default_factory=set)
    # Environment variable overrides
    env_overrides: Dict[str, str] = field(default_factory=dict)
    # Required external API keys (if any)
    required_api_keys: List[str] = field(default_factory=list)
    # Whether GPU is supported/recommended
    gpu_support: bool = False
    # Whether local LLM is used
    uses_local_llm: bool = True
    # Whether ONNX dependencies are required
    requires_onnx: bool = False
    # Human-readable description
    description_en: str = ""
    description_pl: str = ""
    description_de: str = ""


# Profile definitions - single source of truth
PROFILE_DEFINITIONS: Dict[RuntimeProfile, ProfileCapabilities] = {
    RuntimeProfile.LIGHT: ProfileCapabilities(
        profile=RuntimeProfile.LIGHT,
        required_services={"backend", "frontend"},
        disabled_services=set(),
        env_overrides={
            "LLM_WARMUP_ON_STARTUP": "false",
            "VENOM_PAUSE_BACKGROUND_TASKS": "true",
            "ENABLE_AUTO_DOCUMENTATION": "false",
            "ENABLE_AUTO_GARDENING": "false",
        },
        required_api_keys=[],
        gpu_support=True,  # Optional, but supported
        uses_local_llm=True,
        requires_onnx=False,
        description_en="Light: selected provider, background tasks paused",
        description_pl="Light: wybrany silnik, zadania tła wstrzymane",
        description_de="Light: gewählter Anbieter, Hintergrundaufgaben pausiert",
    ),
    RuntimeProfile.LLM_OFF: ProfileCapabilities(
        profile=RuntimeProfile.LLM_OFF,
        required_services={"backend", "frontend"},
        disabled_services={"ollama", "vllm"},
        env_overrides={
            "ACTIVE_LLM_SERVER": "none",
            "LLM_WARMUP_ON_STARTUP": "false",
        },
        required_api_keys=[
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
        ],  # At least one required
        gpu_support=False,
        uses_local_llm=False,
        requires_onnx=False,
        description_en="Cloud: OpenAI/Anthropic + Next.js - Low Hardware Req",
        description_pl="cloud: OpenAI/Anthropic + Next.js - Low Hardware Req",
        description_de="cloud: OpenAI/Anthropic + Next.js - Low Hardware Req",
    ),
    RuntimeProfile.FULL: ProfileCapabilities(
        profile=RuntimeProfile.FULL,
        required_services={"backend", "frontend"},  # Default to ollama
        disabled_services=set(),  # Can enable vllm via ACTIVE_LLM_SERVER
        env_overrides={},
        required_api_keys=[],
        gpu_support=True,
        uses_local_llm=True,
        requires_onnx=False,  # Optional extras
        description_en="Full: configured application features",
        description_pl="Full: skonfigurowane funkcje aplikacji",
        description_de="Full: konfigurierte Anwendungsfunktionen",
    ),
}


def get_profile_capabilities(profile: RuntimeProfile) -> ProfileCapabilities:
    """Get capabilities for a given profile."""
    return PROFILE_DEFINITIONS[profile]


def validate_profile_requirements(
    profile: RuntimeProfile, available_api_keys: Set[str]
) -> tuple[bool, Optional[str]]:
    """
    Validate that profile requirements are met.

    Returns:
        (is_valid, error_message)
    """
    capabilities = get_profile_capabilities(profile)

    # Check API keys for API profile
    if capabilities.required_api_keys and not capabilities.uses_local_llm:
        has_any_key = any(
            key in available_api_keys for key in capabilities.required_api_keys
        )
        if not has_any_key:
            return False, (
                f"Profile '{profile.value}' requires at least one of: "
                f"{', '.join(capabilities.required_api_keys)}"
            )

    return True, None


def get_profile_description(profile: RuntimeProfile, lang: str = "en") -> str:
    """Get human-readable profile description in specified language."""
    capabilities = get_profile_capabilities(profile)
    lang_lower = lang.lower()

    if lang_lower == "pl":
        return capabilities.description_pl
    elif lang_lower == "de":
        return capabilities.description_de
    else:
        return capabilities.description_en
