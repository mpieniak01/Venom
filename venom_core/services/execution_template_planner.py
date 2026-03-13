from __future__ import annotations

from dataclasses import dataclass

from venom_core.core.models import TaskRequest


@dataclass(frozen=True)
class ExecutionTemplateDecision:
    template_id: str
    source: str


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

BROWSER_PROFILE_POLICY = {
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


def resolve_api_skill_template(
    request: TaskRequest,
    intent: str,
) -> ExecutionTemplateDecision | None:
    """Resolve deterministic API/Skill template for top integration paths."""
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()

    forced_tool_template = FORCED_TOOL_TEMPLATE_MAP.get(forced_tool)
    if forced_tool_template is not None:
        return ExecutionTemplateDecision(
            template_id=forced_tool_template,
            source="forced_tool",
        )

    intent_template = INTENT_TEMPLATE_MAP.get(normalized_intent)
    if intent_template is not None:
        return ExecutionTemplateDecision(
            template_id=intent_template,
            source="intent",
        )

    return None


def resolve_browser_profile(request: TaskRequest, intent: str) -> str:
    """Resolve deterministic browser profile: smoke, functional or critical."""
    normalized_intent = str(intent or "").strip().upper()
    content_lower = str(request.content or "").strip().lower()
    tokens = set(content_lower.replace("_", " ").replace("-", " ").split())

    if normalized_intent == "E2E_TESTING" or tokens.intersection(
        CRITICAL_BROWSER_KEYWORDS
    ):
        return "critical"
    if tokens.intersection(SMOKE_BROWSER_KEYWORDS):
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
