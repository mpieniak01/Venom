"""Local Polish image-and-voice pilot with bounded read-only tools."""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import numpy as np
from PIL import Image

from venom_core.core.model_registry_clients import OllamaClient
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.services.model_runtime_inventory import runtime_inventory
from venom_core.services.ollama_audio import (
    OMNI_MODEL_ID,
    require_local_capability,
    transcribe_pcm_audio,
)
from venom_core.services.omni_pilot_screen import (
    CODE,
    SCREEN_PROMPT,
    SCREEN_SCHEMA,
    PilotScreen,
    parse_screen,
    previous_screen,
    resolve_reference,
)
from venom_core.utils.llm_runtime import LLMRuntimeInfo, get_active_llm_runtime

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BASE64 = ((MAX_IMAGE_BYTES + 2) // 3) * 4
MAX_IMAGE_PIXELS = 4096 * 2160
MAX_HISTORY_ROWS = 6
TOOL_NAME = "lookup_pilot_documentation"
RUNTIME_TOOL_NAME = "read_local_omni_status"
RUNTIME_SOURCE = "Lokalna Ollama · /api/ps"
_RUNTIME_SUBJECT = re.compile(r"\b(?:omni|ollam\w*|model\w*)\b", re.I)
_RUNTIME_STATUS = re.compile(r"\b(?:stan|status|działa|załadowan\w*)\b", re.I)
_RUNTIME_SELECTION = {
    "type": "object",
    "properties": {"action": {"enum": [RUNTIME_TOOL_NAME, "clarify"]}},
    "required": ["action"],
    "additionalProperties": False,
}
_RESUME_DOCUMENT = re.compile(
    r"\b(?:wracam|wróć|wróćmy) do poprzedniego komunikatu\b", re.I
)
_RUNTIME_PROMPT = (
    "Wybierz read_local_omni_status tylko wtedy, gdy użytkownik prosi o odczyt "
    "bieżącego stanu lokalnej Ollamy lub bieżącego modelu. W tej rozmowie bieżący "
    "model to Omni. Pytanie, czy model jest załadowany, jest prośbą o odczyt stanu "
    "nawet przy niedokładnie rozpoznanej nazwie. Gdy użytkownik wymienia inny "
    "znany model albo pyta o instrukcję, wybierz clarify. Zwróć obiekt JSON z action."
)
_RUNTIME_REPLIES = {
    "loaded": (
        "Lokalny model Omni jest załadowany.",
        "Ollama zgłasza, że model Omni jest załadowany.",
    ),
    "not_loaded": (
        "Lokalny model Omni nie jest załadowany.",
        "Ollama odpowiada, ale model Omni nie jest obecnie załadowany.",
    ),
}
DOCUMENTATION = Path(__file__).with_name("omni_pilot_documentation.json")
USER_LABEL = "[Pytanie głosowe]"
NO_SPEECH = "Nie słyszę pytania. Nagraj je jeszcze raz."
CLARIFY = "Który komunikat mam sprawdzić? Wskaż go dokładniej lub podaj jego kod."
SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"enum": [TOOL_NAME, "previous_source", "clarify"]},
        "code": {"type": "string"},
    },
    "required": ["action", "code"],
    "additionalProperties": False,
}
SELECT_TOOL = (
    "Rozpoznaj polskie polecenie użytkownika. Jeśli użytkownik wskazuje komunikat, "
    "użyj obrazu i odczytaj dokładny kod wskazanego komunikatu. "
    "Wtedy wybierz lookup_pilot_documentation i wpisz ten kod w polu code. "
    "Jeśli użytkownik dopytuje o poprzedni komunikat, wybierz previous_source "
    "i zostaw code puste. Jeśli polecenie lub wskazany element są niejednoznaczne, "
    "wybierz clarify i zostaw code puste. Wybierz jedną akcję. Zwróć tylko JSON."
)
ANSWER_FROM_SOURCE = (
    "Odpowiedz krótko po polsku na bieżące pytanie użytkownika. Jeśli użytkownik "
    "pyta o konkretny szczegół, podaj go wprost. Przy pytaniu ogólnym zacznij od "
    "pierwszego zalecanego kroku. Fakty i zalecenia bierz wyłącznie z wpisu "
    "dokumentacji poniżej. Gdy wpis nie odpowiada na pytanie, powiedz, "
    "że brakuje tej informacji. Źródło podaje aplikacja. Zwróć tylko odpowiedź bez Markdown."
)


@dataclass(frozen=True)
class PilotAnswer:
    text: str
    code: str | None = None
    sources: tuple[str, ...] = ()
    screen: PilotScreen | None = None
    question: str | None = None
    tool: str | None = None
    tool_status: str | None = None
    no_speech: bool = False


def local_omni(runtime: LLMRuntimeInfo) -> bool:
    """Limit the pilot to the expected Omni model on a loopback Ollama host."""
    return (
        runtime.provider == "ollama"
        and runtime.model_name == OMNI_MODEL_ID
        and runtime.host_local is not False
        and bool(runtime.endpoint)
        and urlsplit(runtime.endpoint or "").hostname
        in {"localhost", "127.0.0.1", "::1"}
    )


def active_pilot_runtime() -> LLMRuntimeInfo | None:
    """Return the active runtime if it meets the pilot's local-only contract."""
    runtime = get_active_llm_runtime()
    return runtime if local_omni(runtime) else None


def validate_image(image: bytes) -> None:
    """Verify JPEG or PNG integrity and enforce encoded and decoded size limits."""
    if not image or len(image) > MAX_IMAGE_BYTES:
        raise ValueError("omni_pilot_invalid_image")
    try:
        with Image.open(io.BytesIO(image), formats=["JPEG", "PNG"]) as decoded:
            if decoded.width * decoded.height > MAX_IMAGE_PIXELS:
                raise ValueError("omni_pilot_invalid_image")
            decoded.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("omni_pilot_invalid_image") from exc


def decode_image(encoded: object) -> bytes:
    """Decode a bounded Base64 image from a WebSocket control message."""
    if not isinstance(encoded, str) or len(encoded) > MAX_IMAGE_BASE64:
        raise ValueError("omni_pilot_invalid_image")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("omni_pilot_invalid_image") from exc


def history_rows(history: list[dict[str, object]]) -> list[dict[str, str]]:
    """Keep bounded conversation text with source attribution out of the prompt."""
    messages: list[dict[str, str]] = []
    for row in history[-MAX_HISTORY_ROWS:]:
        role, content = row.get("role"), row.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if role == "assistant" and row.get("mode") == "omni_pilot":
            content = content.partition("\n\nŹródło: ")[0]
        messages.append({"role": str(role), "content": content[:1000]})
    return messages


def previous_code(history: list[dict[str, object]]) -> str | None:
    """Read the source code from the latest completed pilot reply, if present."""
    for row in reversed(history):
        if row.get("mode") != "omni_pilot" or row.get("role") != "assistant":
            continue
        if row.get("omni_pilot_tool") == RUNTIME_TOOL_NAME:
            continue
        code = row.get("omni_pilot_code")
        return code if isinstance(code, str) else None
    return None


async def _chat(
    http: TrafficControlledHttpClient,
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one bounded Ollama request and reject incomplete replies."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 384 if schema is SCREEN_SCHEMA else 256,
        },
    }
    if schema is not None:
        payload["format"] = schema
    response = await http.apost(
        f"{endpoint}/api/chat", json=payload, disable_retry=True
    )
    result = response.json()
    message = result.get("message")
    if (
        result.get("error")
        or result.get("done") is not True
        or result.get("done_reason") == "length"
        or not isinstance(message, dict)
    ):
        raise RuntimeError("omni_pilot_incomplete_response")
    return message


def _selected_code(
    message: dict[str, Any],
    prior_code: str | None,
    documents: dict[str, dict[str, str]],
) -> str | None:
    """Resolve a lookup by code or an exact unique title in the frozen corpus."""
    try:
        selected = json.loads(_text(message))
    except json.JSONDecodeError:
        return None
    if not isinstance(selected, dict) or selected.keys() != {"action", "code"}:
        return None
    if selected["action"] == "previous_source":
        return prior_code if selected["code"] in ("", prior_code) else None
    if selected["action"] != TOOL_NAME or not isinstance(selected["code"], str):
        return None
    code = selected["code"].strip().upper()
    if CODE.fullmatch(code):
        return code
    label = selected["code"].strip().casefold()
    matches = [
        key
        for key, document in documents.items()
        if label and document["title"].partition(" · ")[2].casefold() == label
    ]
    return matches[0] if len(matches) == 1 else None


def _text(message: dict[str, Any]) -> str:
    """Return stripped text content or an empty string for malformed replies."""
    value = message.get("content")
    return value.strip() if isinstance(value, str) else ""


def _json_string(message: dict[str, Any]) -> str:
    try:
        value = json.loads(_text(message))
    except json.JSONDecodeError:
        return ""
    return value if isinstance(value, str) else ""


async def _answer_runtime_status(
    http: TrafficControlledHttpClient,
    endpoint: str,
    model: str,
    question: str,
    screen: PilotScreen | None,
) -> PilotAnswer:
    """Let Omni select one read, and constrain the reply to the observed outcome."""
    selection = await _chat(
        http,
        endpoint,
        model,
        [
            {"role": "system", "content": _RUNTIME_PROMPT},
            {"role": "user", "content": question},
        ],
        schema=_RUNTIME_SELECTION,
    )
    try:
        action = json.loads(_text(selection))
    except json.JSONDecodeError:
        action = None
    if action != {"action": RUNTIME_TOOL_NAME}:
        return PilotAnswer(
            "Czy mam sprawdzić stan lokalnego modelu Omni?",
            screen=screen,
            question=question,
            tool=RUNTIME_TOOL_NAME,
            tool_status="not_called",
        )
    observation = (await runtime_inventory({"ollama": endpoint}))["ollama"]
    if observation["status"] != "online":
        return PilotAnswer(
            "Nie udało się odczytać stanu lokalnego modelu Omni.",
            screen=screen,
            question=question,
            tool=RUNTIME_TOOL_NAME,
            tool_status="unavailable",
        )
    state = "loaded" if model in observation["models"] else "not_loaded"
    replies = _RUNTIME_REPLIES[state]
    response = await _chat(
        http,
        endpoint,
        model,
        [
            {
                "role": "system",
                "content": (
                    "Wybierz krótką odpowiedź zgodną z wynikiem odczytu. "
                    f"Wynik narzędzia: {state}. Zwróć napis JSON."
                ),
            },
            {"role": "user", "content": question},
        ],
        schema={"type": "string", "enum": list(replies)},
    )
    selected = _json_string(response)
    return PilotAnswer(
        selected if selected in replies else replies[0],
        sources=(RUNTIME_SOURCE,),
        screen=screen,
        question=question,
        tool=RUNTIME_TOOL_NAME,
        tool_status=state,
    )


async def answer(
    runtime: LLMRuntimeInfo,
    pcm: bytes,
    rate: int,
    image: bytes | None,
    history: list[dict[str, object]],
) -> PilotAnswer:
    """Resolve a Polish media turn with the pilot documentation or a runtime read."""
    screen = previous_screen(history) if image is None else None
    samples = np.frombuffer(pcm, dtype="<i2")
    if not samples.size or np.max(np.abs(samples.astype(np.int32))) < 64:
        return PilotAnswer(NO_SPEECH, screen=screen, no_speech=True)
    if image is None and not any(row.get("mode") == "omni_pilot" for row in history):
        return PilotAnswer("Dołącz obraz komunikatu i zadaj pytanie jeszcze raz.")

    docs = json.loads(DOCUMENTATION.read_text(encoding="utf-8"))
    prior_code = previous_code(history) if image is None else None
    client = OllamaClient(runtime.endpoint or "")
    show = await require_local_capability(client.endpoint, runtime.model_name, "audio")
    if "vision" not in show.get("capabilities", ()):
        raise RuntimeError("omni_pilot_capability_unavailable")

    question = await transcribe_pcm_audio(
        client.endpoint, runtime.model_name, pcm, rate, "pl"
    )
    if not question:
        return PilotAnswer(NO_SPEECH, screen=screen, no_speech=True)
    async with TrafficControlledHttpClient(provider="ollama", timeout=90.0) as http:
        if image is not None:
            inventory = await _chat(
                http,
                client.endpoint,
                runtime.model_name,
                [
                    {"role": "system", "content": SCREEN_PROMPT},
                    {
                        "role": "user",
                        "content": "",
                        "images": [base64.b64encode(image).decode("ascii")],
                    },
                ],
                schema=SCREEN_SCHEMA,
            )
            try:
                screen = parse_screen(json.loads(_text(inventory)))
            except json.JSONDecodeError:
                screen = None

        referenced, code = resolve_reference(question, screen, docs)
        if (
            not referenced
            and _RUNTIME_SUBJECT.search(question)
            and _RUNTIME_STATUS.search(question)
        ):
            return await _answer_runtime_status(
                http, client.endpoint, runtime.model_name, question, screen
            )
        if not referenced:
            if image is not None:
                if screen is not None and screen["layout"] == "single":
                    code = screen["cards"][0]["code"]
            elif prior_code in docs and _RESUME_DOCUMENT.search(question):
                code = prior_code
            elif prior_code in docs:
                prompt = (
                    SELECT_TOOL
                    + f" Zweryfikowany kod poprzedniego komunikatu to {prior_code}. "
                    "Jeśli pytanie dotyczy poprzedniego komunikatu, wybierz previous_source "
                    "także wtedy, gdy użytkownik nie powtórzył jego kodu."
                )
                first = await _chat(
                    http,
                    client.endpoint,
                    runtime.model_name,
                    [
                        {"role": "system", "content": prompt},
                        *history_rows(history),
                        {"role": "user", "content": question},
                    ],
                    schema=SELECTION_SCHEMA,
                )
                if _selected_code(first, prior_code, docs) == prior_code:
                    code = prior_code
        if code is None:
            return PilotAnswer(CLARIFY, screen=screen, question=question)
        document = docs.get(code)
        if document is None:
            return PilotAnswer(
                f"Dokumentacja pilotażu nie zawiera kodu {code}.",
                screen=screen,
                question=question,
                tool=TOOL_NAME,
                tool_status="not_found",
            )
        source_prompt = (
            ANSWER_FROM_SOURCE + "\n" + json.dumps(document, ensure_ascii=False)
        )
        previous_turn = history[-2:]
        answer_history = (
            history_rows(previous_turn)
            if previous_turn and previous_turn[-1].get("omni_pilot_code") == code
            else []
        )
        final = await _chat(
            http,
            client.endpoint,
            runtime.model_name,
            [
                {"role": "system", "content": source_prompt},
                *answer_history,
                {"role": "user", "content": question},
            ],
        )
    text = _text(final).partition("\n\nŹródło: ")[0].rstrip()
    if not text or final.get("tool_calls"):
        text = document["content"]
    return PilotAnswer(
        text,
        code,
        (document["title"],),
        screen,
        question=question,
        tool=TOOL_NAME,
        tool_status="ok",
    )


def conversation_pair(
    answer: PilotAnswer, *, has_image: bool
) -> list[dict[str, object]]:
    """Store text and source context without retaining raw media."""
    user = answer.question or (
        "[Pytanie głosowe z obrazem]" if has_image else USER_LABEL
    )
    text = answer.text
    if answer.sources:
        text += "\n\nŹródło: " + answer.sources[0]
    return [
        {"role": "user", "content": user, "mode": "omni_pilot"},
        {
            "role": "assistant",
            "content": text,
            "mode": "omni_pilot",
            "omni_pilot_code": answer.code,
            "omni_pilot_screen": answer.screen,
            "omni_pilot_tool": answer.tool,
            "omni_pilot_tool_status": answer.tool_status,
        },
    ]
