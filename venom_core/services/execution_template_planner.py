from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from venom_core.core.models import TaskRequest


@dataclass(frozen=True, slots=True)
class ExecutionTemplateDecision:
    template_id: str
    source: str


class BrowserProfilePolicy(TypedDict):
    verify_checks: list[str]
    required_artifacts: list[str]
    timeout_seconds: int
    max_retries: int
    fail_closed: bool


FORCED_TOOL_TEMPLATE_MAP = {
    "calendar": "calendar_event_ops_v1",
    "github": "github_repo_ops_v1",
    "git": "github_repo_ops_v1",
    "file": "filesystem_ops_v1",
    "fs": "filesystem_ops_v1",
    "filesystem": "filesystem_ops_v1",
}

INTENT_TEMPLATE_MAP = {
    "VERSION_CONTROL": "github_repo_ops_v1",
    "RELEASE_PROJECT": "github_repo_ops_v1",
    "FILE_OPERATION": "filesystem_ops_v1",
    "DOCUMENTATION": "filesystem_ops_v1",
    "CODE_GENERATION": "filesystem_ops_v1",
    "TIME_REQUEST": "system_ops_v1",
    "INFRA_STATUS": "system_ops_v1",
    "STATUS_REPORT": "system_ops_v1",
}

CRITICAL_BROWSER_KEYWORDS = {
    "critical",
    "payment",
    "delete",
    "production",
    "prod",
}

SMOKE_BROWSER_KEYWORDS = {
    "smoke",
    "quick",
    "sanity",
}

BROWSER_PROFILE_POLICY: dict[str, BrowserProfilePolicy] = {
    "smoke": {
        "verify_checks": ["page_status_ok", "critical_element_visible"],
        "required_artifacts": ["screenshot"],
        "timeout_seconds": 30,
        "max_retries": 1,
        "fail_closed": False,
    },
    "functional": {
        "verify_checks": [
            "page_status_ok",
            "critical_element_visible",
            "result_assertion",
        ],
        "required_artifacts": ["screenshot", "dom_snapshot"],
        "timeout_seconds": 60,
        "max_retries": 2,
        "fail_closed": False,
    },
    "critical": {
        "verify_checks": [
            "page_status_ok",
            "critical_element_visible",
            "result_assertion",
            "audit_trace_complete",
        ],
        "required_artifacts": ["screenshot", "dom_snapshot", "network_log"],
        "timeout_seconds": 90,
        "max_retries": 0,
        "fail_closed": True,
    },
}

FORCED_TOOL_TEMPLATE_DECISIONS = {
    tool: ExecutionTemplateDecision(template_id=template_id, source="forced_tool")
    for tool, template_id in FORCED_TOOL_TEMPLATE_MAP.items()
}

INTENT_TEMPLATE_DECISIONS = {
    intent: ExecutionTemplateDecision(template_id=template_id, source="intent")
    for intent, template_id in INTENT_TEMPLATE_MAP.items()
}

TOKEN_SEPARATOR_TRANSLATION = str.maketrans({"_": " ", "-": " "})


def _normalize_lower(value: object | None) -> str:
    return str(value or "").strip().lower()


def _normalize_upper(value: object | None) -> str:
    return str(value or "").strip().upper()


def _content_tokens(content: str) -> list[str]:
    return content.translate(TOKEN_SEPARATOR_TRANSLATION).split()


def resolve_api_skill_template(
    request: TaskRequest,
    intent: str,
) -> ExecutionTemplateDecision | None:
    """Resolve deterministic API/Skill template for top integration paths."""
    forced_tool = _normalize_lower(request.forced_tool)
    normalized_intent = _normalize_upper(intent)

    forced_tool_template = FORCED_TOOL_TEMPLATE_DECISIONS.get(forced_tool)
    if forced_tool_template is not None:
        return forced_tool_template

    intent_template = INTENT_TEMPLATE_DECISIONS.get(normalized_intent)
    if intent_template is not None:
        return intent_template

    return None


def resolve_browser_profile(request: TaskRequest, intent: str) -> str:
    """Resolve deterministic browser profile: smoke, functional or critical."""
    normalized_intent = _normalize_upper(intent)
    content_lower = _normalize_lower(request.content)

    if normalized_intent == "E2E_TESTING":
        return "critical"

    has_smoke_keyword = False
    for token in _content_tokens(content_lower):
        if token in CRITICAL_BROWSER_KEYWORDS:
            return "critical"
        if token in SMOKE_BROWSER_KEYWORDS:
            has_smoke_keyword = True

    if has_smoke_keyword:
        return "smoke"
    return "functional"


def resolve_browser_execution_contract(profile: str) -> dict[str, object]:
    """Build deterministic browser execution contract for selected profile."""
    normalized_profile = str(profile or "functional").strip().lower()
    policy = BROWSER_PROFILE_POLICY.get(
        normalized_profile,
        BROWSER_PROFILE_POLICY["functional"],
    )
    return {
        "profile": normalized_profile,
        "verify_checks": list(policy["verify_checks"]),
        "required_artifacts": list(policy["required_artifacts"]),
        "retry_policy": {
            "max_retries": policy["max_retries"],
            "terminal_fail_closed": policy["fail_closed"],
        },
        "timeout_seconds": policy["timeout_seconds"],
    }
