"""Local Polish image-and-voice pilot backed by a bounded documentation tool."""

from __future__ import annotations

import asyncio
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
from venom_core.services.ollama_audio import (
    OMNI_MODEL_ID,
    encode_pcm_audio,
    require_local_capability,
)
from venom_core.utils.llm_runtime import LLMRuntimeInfo, get_active_llm_runtime

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BASE64 = ((MAX_IMAGE_BYTES + 2) // 3) * 4
MAX_IMAGE_PIXELS = 4096 * 2160
MAX_HISTORY_ROWS = 6
TOOL_NAME = "lookup_pilot_documentation"
DOCUMENTATION = Path(__file__).with_name("omni_pilot_documentation.json")
USER_LABEL = "[Pytanie głosowe]"
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
    "Rozpoznaj polskie polecenie z nagrania. Jeśli użytkownik wskazuje komunikat, "
    "użyj obrazu i odczytaj dokładny kod wskazanego komunikatu. "
    "Wtedy wybierz lookup_pilot_documentation i wpisz ten kod w polu code. "
    "Jeśli użytkownik dopytuje o poprzedni komunikat, wybierz previous_source "
    "i zostaw code puste. Jeśli polecenie lub wskazany element są niejednoznaczne, "
    "wybierz clarify i zostaw code puste. Wybierz jedną akcję. Zwróć tylko JSON."
)
ANSWER_FROM_SOURCE = (
    "Odpowiedz krótko po polsku na pytanie z nagrania. Pierwszą zalecaną czynność "
    "podaj na początku. Korzystaj wyłącznie z wyniku odczytu dokumentacji poniżej. "
    "Zwróć samą treść odpowiedzi bez Markdown."
)


@dataclass(frozen=True)
class PilotAnswer:
    text: str
    code: str | None = None
    sources: tuple[str, ...] = ()


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
    """Keep bounded user and assistant text for the model context."""
    return [
        {"role": str(row["role"]), "content": str(row["content"])[:1000]}
        for row in history[-MAX_HISTORY_ROWS:]
        if row.get("role") in ("user", "assistant")
        and isinstance(row.get("content"), str)
    ]


def previous_code(history: list[dict[str, object]]) -> str | None:
    """Read the source code from the latest completed pilot reply, if present."""
    for row in reversed(history):
        if row.get("mode") != "omni_pilot" or row.get("role") != "assistant":
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
    selection: bool = False,
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
            "num_predict": 96 if selection else 256,
        },
    }
    if selection:
        payload["format"] = SELECTION_SCHEMA
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


def _selected_code(message: dict[str, Any], prior_code: str | None) -> str | None:
    """Accept only a valid document lookup or an explicit request for the previous source."""
    try:
        selected = json.loads(_text(message))
    except json.JSONDecodeError:
        return None
    if not isinstance(selected, dict) or selected.keys() != {"action", "code"}:
        return None
    if selected["action"] == "previous_source" and selected["code"] == "":
        return prior_code
    if selected["action"] != TOOL_NAME or not isinstance(selected["code"], str):
        return None
    code = selected["code"].strip().upper()
    return code if re.fullmatch(r"VEN-\d{3}", code, flags=re.ASCII) else None


def _text(message: dict[str, Any]) -> str:
    """Return stripped text content or an empty string for malformed replies."""
    value = message.get("content")
    return value.strip() if isinstance(value, str) else ""


async def answer(
    runtime: LLMRuntimeInfo,
    pcm: bytes,
    rate: int,
    image: bytes | None,
    history: list[dict[str, object]],
) -> PilotAnswer:
    """Resolve a Polish media turn against the frozen pilot documentation."""
    samples = np.frombuffer(pcm, dtype="<i2")
    if not samples.size or np.max(np.abs(samples.astype(np.int32))) < 64:
        return PilotAnswer("Nie słyszę pytania. Nagraj je jeszcze raz.")
    if image is None and not any(row.get("mode") == "omni_pilot" for row in history):
        return PilotAnswer("Dołącz obraz komunikatu i zadaj pytanie jeszcze raz.")

    docs = json.loads(DOCUMENTATION.read_text(encoding="utf-8"))
    prior_code = previous_code(history) if image is None else None
    prompt = SELECT_TOOL
    if prior_code in docs:
        prompt += f" Zweryfikowany kod poprzedniego komunikatu to {prior_code}."
    media = [base64.b64encode(image).decode("ascii")] if image is not None else []
    media.append(await asyncio.to_thread(encode_pcm_audio, samples, rate))
    turn = {"role": "user", "content": "", "images": media}
    history_messages = history_rows(history)
    client = OllamaClient(runtime.endpoint or "")
    show = await require_local_capability(client.endpoint, runtime.model_name, "audio")
    if "vision" not in show.get("capabilities", ()):
        raise RuntimeError("omni_pilot_capability_unavailable")
    async with TrafficControlledHttpClient(provider="ollama", timeout=90.0) as http:
        first = await _chat(
            http,
            client.endpoint,
            runtime.model_name,
            [{"role": "system", "content": prompt}, *history_messages, turn],
            selection=True,
        )
        code = _selected_code(first, prior_code)
        if code is None:
            return PilotAnswer(CLARIFY)
        document = docs.get(code)
        if document is None:
            return PilotAnswer(f"Dokumentacja pilotażu nie zawiera kodu {code}.")
        source_prompt = (
            ANSWER_FROM_SOURCE + "\n" + json.dumps(document, ensure_ascii=False)
        )
        final = await _chat(
            http,
            client.endpoint,
            runtime.model_name,
            [
                {"role": "system", "content": source_prompt},
                {
                    "role": "user",
                    "content": "Wyjaśnij komunikat i podaj pierwszy krok z dokumentacji.",
                },
            ],
        )
    text = _text(final)
    # The frozen entry starts with its required first action. Use the verified
    # text if the generated summary drops or changes that action.
    first_step = document["content"].partition(". ")[0].rstrip(".")
    if first_step.casefold() not in text.casefold() or final.get("tool_calls"):
        text = document["content"]
    return PilotAnswer(text, code, (document["title"],))


def conversation_pair(
    answer: PilotAnswer, *, has_image: bool
) -> list[dict[str, object]]:
    """Store text and source context without retaining raw media."""
    user = "[Pytanie głosowe z obrazem]" if has_image else USER_LABEL
    return [
        {"role": "user", "content": user, "mode": "omni_pilot"},
        {
            "role": "assistant",
            "content": answer.text,
            "mode": "omni_pilot",
            "omni_pilot_code": answer.code,
        },
    ]
