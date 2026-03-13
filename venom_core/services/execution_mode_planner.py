from __future__ import annotations

from dataclasses import dataclass

from venom_core.core.models import TaskRequest


@dataclass(frozen=True)
class ExecutionModeDecision:
    execution_mode: str
    fallback_reason: str | None = None
    reason_code: str | None = None


API_SKILL_TOOLS = {
    "calendar",
    "github",
    "git",
    "file",
    "fs",
    "filesystem",
}

BROWSER_AUTOMATION_TOOLS = {
    "browser",
    "web",
    "http",
    "network",
}

GUI_FALLBACK_TOOLS = {
    "desktop",
    "vision",
    "ghost",
    "ui",
    "input",
}

API_SKILL_INTENTS = {
    "VERSION_CONTROL",
    "FILE_OPERATION",
    "DOCUMENTATION",
    "RELEASE_PROJECT",
    "STATUS_REPORT",
    "INFRA_STATUS",
    "TIME_REQUEST",
}

BROWSER_AUTOMATION_INTENTS = {
    "RESEARCH",
    "KNOWLEDGE_SEARCH",
    "E2E_TESTING",
}

GUI_FALLBACK_INTENTS = {
    "DESKTOP_AUTOMATION",
    "VISION_CONTROL",
}


def decide_execution_mode(
    request: TaskRequest, intent: str | None
) -> ExecutionModeDecision:
    """Select execution mode with deterministic priority: API/Skill -> Browser -> GUI fallback."""
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()

    if forced_tool in API_SKILL_TOOLS:
        return ExecutionModeDecision(execution_mode="api_skill")
    if normalized_intent in API_SKILL_INTENTS:
        return ExecutionModeDecision(execution_mode="api_skill")

    if forced_tool in BROWSER_AUTOMATION_TOOLS:
        return ExecutionModeDecision(execution_mode="browser_automation")
    if normalized_intent in BROWSER_AUTOMATION_INTENTS:
        return ExecutionModeDecision(execution_mode="browser_automation")

    if forced_tool in GUI_FALLBACK_TOOLS:
        return ExecutionModeDecision(
            execution_mode="gui_fallback",
            fallback_reason="forced_gui_tool",
            reason_code="EXECUTION_MODE_GUI_FALLBACK_FORCED_TOOL",
        )
    if normalized_intent in GUI_FALLBACK_INTENTS:
        return ExecutionModeDecision(
            execution_mode="gui_fallback",
            fallback_reason="intent_requires_gui_path",
            reason_code="EXECUTION_MODE_GUI_FALLBACK_INTENT",
        )

    return ExecutionModeDecision(execution_mode="api_skill")
