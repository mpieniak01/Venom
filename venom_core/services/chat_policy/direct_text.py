"""History and system instructions for direct text chat."""

import re

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.config import DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT, SETTINGS

CONVERSATION_HISTORY_POLICY = (
    "Odpowiedz na ostatnią wiadomość użytkownika. Korzystaj z historii przy dopytaniach. "
    "Najnowsze ustalenia użytkownika mają pierwszeństwo. Wcześniejsze odpowiedzi asystenta mogą być błędne. "
    "Zastosuj format wymagany w ostatniej wiadomości."
)
# A stated decision or correction is different from a question about an earlier reply.
_STATED_UPDATE = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:"
    r"ustalenie\s+(?:to|jest)|ustaliliśmy|ustalam(?:y)?|umówiliśmy\s+się"
    r"|zmiana\s+(?:ustalenia|zamówienia|decyzji|planu)"
    r"|zmieniam(?:y)?\s+(?:ustalenie|zamówienie|decyzję|plan)"
    r"|(?:poprawka|korekta)(?=\s|[:.!]|$)"
    r")\b[^.!?]*(?:[.!]|$)",
    re.IGNORECASE,
)


def retry_without_previous_attempts(request: SimpleChatRequest) -> SimpleChatRequest:
    """Keep distinct earlier turns while retrying the same last question."""
    history = request.history
    end = len(history)
    question = request.content.strip()
    while (
        end >= 2
        and history[end - 2].role == "user"
        and history[end - 1].role == "assistant"
        and history[end - 2].content.strip() == question
    ):
        end -= 2
    return (
        request.model_copy(update={"history": history[:end]})
        if end < len(history)
        else request
    )


def simple_system_prompt(
    request: SimpleChatRequest,
    system_context: str,
    *,
    plain_omni: bool = False,
    plain_gemma: bool = False,
) -> str:
    system_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    if (
        request.studio_normal or plain_omni
    ) and system_prompt == DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT:
        system_prompt = ""
    if (
        plain_omni
        and any(turn.role == "assistant" for turn in request.history)
        and not system_prompt
    ):
        system_prompt = CONVERSATION_HISTORY_POLICY
    if plain_gemma and system_prompt in {"", DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT}:
        system_prompt = CONVERSATION_HISTORY_POLICY
    if system_context:
        system_prompt = "\n\n".join(filter(None, (system_prompt, system_context)))
    return system_prompt


def prepare_omni_history(request: SimpleChatRequest) -> SimpleChatRequest:
    request = retry_without_previous_attempts(request)
    if _STATED_UPDATE.search(request.content):
        # Earlier assistant replies can contradict an explicit current decision.
        return request.model_copy(
            update={
                "history": [turn for turn in request.history if turn.role == "user"]
            }
        )
    return request
