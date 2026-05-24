"""Canonical mode contracts for voice, text chat, and Venom agent flows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VOICE_EXECUTION_CONTEXT = "voice_command"
VOICE_HISTORY_SCOPE = "ephemeral_no_text_chat_inheritance"

TEXT_CHAT_EXECUTION_CONTEXT = "text_chat_session"
TEXT_CHAT_HISTORY_SCOPE = "persistent_until_stack_restart"

VENOM_AGENT_EXECUTION_CONTEXT = "operator_execution_context"
VENOM_AGENT_HISTORY_SCOPE = "operator_task_context"

MODE_CONTRACTS: dict[str, dict[str, str]] = {
    "voice": {
        "execution_context": VOICE_EXECUTION_CONTEXT,
        "history_scope": VOICE_HISTORY_SCOPE,
        "session_memory_policy": "ephemeral",
    },
    "text_chat": {
        "execution_context": TEXT_CHAT_EXECUTION_CONTEXT,
        "history_scope": TEXT_CHAT_HISTORY_SCOPE,
        "session_memory_policy": "persistent",
    },
    "venom_agent": {
        "execution_context": VENOM_AGENT_EXECUTION_CONTEXT,
        "history_scope": VENOM_AGENT_HISTORY_SCOPE,
        "session_memory_policy": "task_scoped",
    },
}


def mode_contracts_payload() -> dict[str, dict[str, Any]]:
    """Return a defensive copy for API payloads."""
    return deepcopy(MODE_CONTRACTS)
