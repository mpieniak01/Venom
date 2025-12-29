"""Slash commands: mapowanie prefiksow na provider/tool/intencje."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SlashCommandResult:
    token: str
    cleaned: str
    forced_provider: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_intent: Optional[str] = None


LLM_PROVIDER_ALIASES = {
    "gem": "google-gemini",
    "gpt": "openai",
}

# Mapowanie alias -> intent (gdzie mamy jednoznaczny agent)
TOOL_INTENT_ALIASES = {
    "assistant": "GENERAL_CHAT",
    "browser": "RESEARCH",
    "chrono": "TIME_REQUEST",
    "complexity": "COMPLEX_PLANNING",
    "compose": "CODE_GENERATION",
    "core": "STATUS_REPORT",
    "docs": "DOCUMENTATION",
    "file": "FILE_OPERATION",
    "git": "VERSION_CONTROL",
    "github": "RESEARCH",
    "gcal": "GENERAL_CHAT",
    "hf": "RESEARCH",
    "input": "E2E_TESTING",
    "media": "RESEARCH",
    "parallel": "COMPLEX_PLANNING",
    "platform": "VERSION_CONTROL",
    "render": "DOCUMENTATION",
    "research": "RESEARCH",
    "shell": "CODE_GENERATION",
    "test": "E2E_TESTING",
    "web": "RESEARCH",
}


def parse_slash_command(content: str) -> Optional[SlashCommandResult]:
    if not content:
        return None
    stripped = content.lstrip()
    if not stripped.startswith("/"):
        return None

    token = ""
    for ch in stripped[1:]:
        if ch.isalnum() or ch in ("-", "_"):
            token += ch
            continue
        break
    if not token:
        return None

    remaining = stripped[1 + len(token) :].lstrip()

    if token in LLM_PROVIDER_ALIASES:
        return SlashCommandResult(
            token=token,
            cleaned=remaining,
            forced_provider=LLM_PROVIDER_ALIASES[token],
        )

    if token in TOOL_INTENT_ALIASES:
        return SlashCommandResult(
            token=token,
            cleaned=remaining,
            forced_tool=token,
            forced_intent=TOOL_INTENT_ALIASES[token],
        )

    return SlashCommandResult(token=token, cleaned=remaining)


def resolve_forced_intent(forced_tool: str) -> Optional[str]:
    if not forced_tool:
        return None
    return TOOL_INTENT_ALIASES.get(forced_tool)


def normalize_forced_provider(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return LLM_PROVIDER_ALIASES.get(value, value)
