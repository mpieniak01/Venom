"""Resolve Studio's public source intent against conversation history."""

from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_grounding import (
    grounding_follow_up,
    grounding_kind,
    is_rss_read_request,
    rss_editorial_query,
)
from venom_core.services.chat_policy.direct_calculator import (
    plan_studio_calculator_command,
)
from venom_core.services.chat_policy.qualified_chat_revisions import (
    lookup_forbidden,
    lookup_text_outside_quoted_task,
    public_lookup_query,
    source_revision_hint,
)
from venom_core.services.public_source_evidence import (
    PublicSourceEvidence,
    asks_about_previous_scope,
    previous_public_fact_context,
    previous_scope_reply,
    previous_verified_fact_reply,
)


@dataclass(frozen=True)
class StudioSourcePlan:
    query: str | None
    explicit_rss: bool
    scope_reply: str | None
    prior_context: str
    retained_evidence: PublicSourceEvidence | None


def _previous_evidence(history: list[dict[str, object]]) -> PublicSourceEvidence | None:
    if len(history) < 2:
        return None
    user, assistant = history[-2:]
    if (
        user.get("role") != "user"
        or assistant.get("role") != "assistant"
        or not assistant.get("request_id")
        or user.get("request_id") != assistant.get("request_id")
        or assistant.get("status") != "COMPLETED"
        or assistant.get("finish_reason") == "length"
    ):
        return None
    return PublicSourceEvidence.from_record(assistant.get("public_source_evidence"))


def plan_studio_source(
    message: str,
    history: list[HistoryMessage],
    history_records: list[dict[str, object]],
    *,
    local_qualification: bool,
    provided_information_only: bool,
    use_notes: bool = False,
) -> StudioSourcePlan:
    """Resolve source reuse and external lookup intent without executing a read."""
    if not use_notes and plan_studio_calculator_command(message) is not None:
        return StudioSourcePlan(None, False, None, "", None)
    previous_users = [turn.content for turn in history if turn.role == "user"]
    previous = previous_users[-1] if previous_users else ""
    query: str | None = grounding_follow_up(
        lookup_text_outside_quoted_task(message), previous
    )
    prior_evidence = _previous_evidence(history_records) if not use_notes else None
    explicit_rss = (
        local_qualification and query is not None and is_rss_read_request(query)
    )
    scope_reply, prior_context = _previous_source_context(
        message, prior_evidence, local_qualification, explicit_rss
    )
    query = _lookup_query(
        message,
        previous_users,
        query,
        local_qualification,
        provided_information_only,
        scope_reply,
        prior_context,
    )
    if explicit_rss and query is not None:
        query = rss_editorial_query(query)
    if query is not None and grounding_kind(query, use_notes=use_notes) is None:
        query = None
    return StudioSourcePlan(
        query,
        explicit_rss,
        scope_reply,
        prior_context,
        prior_evidence if prior_context else None,
    )


def _previous_source_context(
    message: str,
    prior_evidence: PublicSourceEvidence | None,
    local_qualification: bool,
    explicit_rss: bool,
) -> tuple[str | None, str]:
    scope_reply = None
    if asks_about_previous_scope(message) and not explicit_rss:
        scope_reply = previous_scope_reply(prior_evidence)
    if local_qualification and not explicit_rss and scope_reply is None:
        scope_reply = previous_verified_fact_reply(message, prior_evidence)
    prior_context = (
        "" if explicit_rss else previous_public_fact_context(message, prior_evidence)
    )
    return scope_reply, prior_context


def _lookup_query(
    message: str,
    previous_users: list[str],
    query: str | None,
    local_qualification: bool,
    provided_information_only: bool,
    scope_reply: str | None,
    prior_context: str,
) -> str | None:
    if (
        scope_reply
        or prior_context
        or provided_information_only
        or lookup_forbidden(message, previous_users)
    ):
        return None
    if local_qualification and source_revision_hint(message):
        return None
    if query is None:
        return None
    return public_lookup_query(query) if local_qualification else query
