"""Core-owned integration declarations. These describe support, never API health."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from venom_core.api.schemas.integrations import IntegrationEntry
from venom_core.api.schemas.system import AuthType, ConnectionDirection

MODELS_PANEL = "/models"


@dataclass(frozen=True)
class Definition:
    id: str
    label: str
    keys: tuple[str, ...] = ()
    flag: str | None = None
    kind: Literal[
        "api", "module", "runtime", "infrastructure", "catalog", "notifications"
    ] = "api"
    capabilities: tuple[str, ...] = ()
    panel: str | None = None
    cli: bool = False
    location: Literal["local", "lan", "cloud", "unknown"] = "cloud"
    description: str | None = None
    methods: tuple[str, ...] = ()
    source_component: str = "Venom"
    auth_type: AuthType | None = None
    direction: ConnectionDirection = ConnectionDirection.OUTBOUND


DEFINITIONS = (
    Definition(
        "stable-diffusion",
        "Stable Diffusion",
        capabilities=("image_generation",),
        location="local",
        description="Generowanie obrazów (Automatic1111)",
        methods=("POST /sdapi/v1/txt2img", "GET /sdapi/v1/options"),
        source_component="Image Generator",
    ),
    Definition(
        "vast",
        "Vast.ai",
        ("VAST_API_KEY",),
        kind="infrastructure",
        capabilities=("gpu_environments", "billing"),
        cli=True,
    ),
    Definition(
        "openai",
        "OpenAI API",
        ("OPENAI_API_KEY",),
        capabilities=("model_inference",),
        panel=MODELS_PANEL,
        description="Modele językowe i multimodalne OpenAI",
        methods=(
            "POST /v1/chat/completions",
            "POST /v1/embeddings",
            "POST /v1/images/generations",
        ),
        source_component="Model Router",
    ),
    Definition(
        "google",
        "Google AI Studio",
        ("GOOGLE_API_KEY",),
        capabilities=("model_inference",),
        panel=MODELS_PANEL,
        description="Modele Gemini",
        methods=("POST /v1beta/models/{model}:generateContent",),
        source_component="Model Router",
    ),
    Definition(
        "huggingface",
        "Hugging Face Hub",
        (),
        "ENABLE_HF_INTEGRATION",
        "catalog",
        ("model_catalog",),
        MODELS_PANEL,
        description="Pobieranie modeli i metadanych",
        methods=("GET /api/models/{model_id}", "GET /api/datasets"),
        source_component="Model Manager",
    ),
    Definition(
        "github",
        "GitHub",
        ("GITHUB_TOKEN", "GITHUB_REPO_NAME"),
        capabilities=("repository_operations",),
    ),
    Definition(
        "slack",
        "Slack",
        ("SLACK_WEBHOOK_URL",),
        kind="notifications",
        capabilities=("notifications",),
    ),
    Definition(
        "discord",
        "Discord",
        ("DISCORD_WEBHOOK_URL",),
        kind="notifications",
        capabilities=("notifications",),
    ),
    Definition(
        "tavily", "Tavily AI Search", ("TAVILY_API_KEY",), capabilities=("web_search",)
    ),
    Definition("duckduckgo", "DuckDuckGo", capabilities=("web_search",)),
    Definition(
        "google-calendar",
        "Google Calendar API",
        ("GOOGLE_CALENDAR_CREDENTIALS_PATH", "GOOGLE_CALENDAR_TOKEN_PATH"),
        "ENABLE_GOOGLE_CALENDAR",
        capabilities=("calendar",),
        description="Integracja z kalendarzem użytkownika",
        methods=("GET /calendars/primary/events", "POST /calendars/primary/events"),
        source_component="Calendar Skill",
        auth_type=AuthType.OAUTH,
        direction=ConnectionDirection.BIDIRECTIONAL,
    ),
)


def configured_value(settings: object, key: str) -> bool:
    value = getattr(settings, key, None)
    if value is None:
        return False
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return bool(value and str(value).strip())


def core_catalog(settings: object) -> list[IntegrationEntry]:
    entries = []
    for item in DEFINITIONS:
        configured = all(configured_value(settings, key) for key in item.keys)
        if item.id == "google-calendar":
            configured = configured and all(
                Path(str(getattr(settings, key, ""))).is_file() for key in item.keys
            )
        enabled = bool(getattr(settings, item.flag, False)) if item.flag else True
        state = "unverified"
        if not enabled:
            state = "disabled"
        elif configured and item.keys:
            state = "configured"
        if enabled and not configured:
            state = "unconfigured"
        access: list[Literal["panel", "cli", "api"]] = ["api"]
        if item.panel:
            access.append("panel")
        if item.cli:
            access.append("cli")
        entries.append(
            IntegrationEntry(
                id="core:" + item.id,
                label=item.label,
                scope="external",
                kind=item.kind,
                location=item.location,
                configuration=("configured" if configured else "unconfigured")
                if item.keys
                else "not_required",
                activation="enabled" if enabled else "disabled",
                state=state,
                resource_support="supported" if item.id == "vast" else "not_applicable",
                can_probe=item.id == "vast" and configured,
                capabilities=list(item.capabilities),
                configuration_keys=list(item.keys),
                access=access,
                panel_path=item.panel,
                documentation_url="https://github.com/mpieniak01/Venom/blob/main/docs/integrations/vast.md"
                if item.id == "vast"
                else None,
                reason_code="feature_disabled" if not enabled else "not_probed",
            )
        )
    return entries
