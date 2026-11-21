"""Resolve Studio's public source intent against conversation history."""

from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_grounding import (
    grounding_follow_up,
    is_rss_read_request,
    rss_editorial_query,
)
from venom_core.services.chat_policy.qualified_chat_revisions import (
    lookup_forbidden,
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
) -> StudioSourcePlan:
    """Resolve source reuse and external lookup intent without executing a read."""
    previous_users = [turn.content for turn in history if turn.role == "user"]
    previous = previous_users[-1] if previous_users else ""
    query = grounding_follow_up(message, previous)
    prior_evidence = (
        _previous_evidence(history_records) if local_qualification else None
    )
    explicit_rss = local_qualification and is_rss_read_request(message)
    scope_reply = (
        previous_scope_reply(prior_evidence)
        if local_qualification
        and asks_about_previous_scope(message)
        and not explicit_rss
        else None
    )
    if local_qualification and not explicit_rss and scope_reply is None:
        scope_reply = previous_verified_fact_reply(message, prior_evidence)
    prior_context = (
        "" if explicit_rss else previous_public_fact_context(message, prior_evidence)
    )
    if (
        scope_reply
        or prior_context
        or provided_information_only
        or lookup_forbidden(message, previous_users)
    ):
        query = None
    elif local_qualification:
        query = None if source_revision_hint(message) else public_lookup_query(query)
    if explicit_rss and query is not None:
        query = rss_editorial_query(query)
    return StudioSourcePlan(query, explicit_rss, scope_reply, prior_context)
