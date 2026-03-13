from __future__ import annotations

from dataclasses import dataclass

from venom_core.core.models import TaskRequest


@dataclass(frozen=True)
class ExecutionTemplateDecision:
    template_id: str
    source: str


def resolve_api_skill_template(
    request: TaskRequest,
    intent: str,
) -> ExecutionTemplateDecision | None:
    """Resolve deterministic API/Skill template for top integration paths."""
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()

    if forced_tool in {"calendar"}:
        return ExecutionTemplateDecision(
            template_id="calendar_event_ops_v1",
            source="forced_tool",
        )
    if forced_tool in {"github", "git"}:
        return ExecutionTemplateDecision(
            template_id="github_repo_ops_v1",
            source="forced_tool",
        )
    if forced_tool in {"file", "fs", "filesystem"}:
        return ExecutionTemplateDecision(
            template_id="filesystem_ops_v1",
            source="forced_tool",
        )

    if normalized_intent in {"VERSION_CONTROL", "RELEASE_PROJECT"}:
        return ExecutionTemplateDecision(
            template_id="github_repo_ops_v1",
            source="intent",
        )
    if normalized_intent in {"FILE_OPERATION", "DOCUMENTATION", "CODE_GENERATION"}:
        return ExecutionTemplateDecision(
            template_id="filesystem_ops_v1",
            source="intent",
        )
    if normalized_intent in {"TIME_REQUEST", "INFRA_STATUS", "STATUS_REPORT"}:
        return ExecutionTemplateDecision(
            template_id="system_ops_v1",
            source="intent",
        )

    return None
