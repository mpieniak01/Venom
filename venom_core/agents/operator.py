"""Moduł: operator - agent interfejsu głosowo-sprzętowego."""

import re
from typing import Any, Optional

import httpx
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.infrastructure.hardware_pi import HardwareBridge
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
HARDWARE_BRIDGE_UNAVAILABLE_MSG = "Hardware Bridge nie jest dostępny."

VOICE_MODE_PROMPTS = {
    "standard": {
        "instruction": "Odpowiadaj krótko, naturalnie i zwięźle.",
        "max_tokens": 150,
        "temperature": 0.7,
    },
    "deep_analysis": {
        "instruction": (
            "Udziel odpowiedzi analitycznej. Wskaż wnioski, ryzyka i rekomendacje, "
            "ale nadal mów naturalnie i bez markdown."
        ),
        "max_tokens": 220,
        "temperature": 0.6,
    },
    "summary": {
        "instruction": "Streść odpowiedź do 1-2 zdań, bez zbędnych szczegółów.",
        "max_tokens": 100,
        "temperature": 0.5,
    },
    "action_items": {
        "instruction": "Podaj konkretne następne kroki w 2-4 punktach, bez markdown.",
        "max_tokens": 120,
        "temperature": 0.6,
    },
}


def _build_voice_context_message(voice_context: dict[str, Any] | None) -> str | None:
    if not voice_context:
        return None

    parts: list[str] = []
    reasoning_summary = str(voice_context.get("reasoning_summary") or "").strip()
    if reasoning_summary and voice_context.get("reasoning_summary_enabled", False):
        parts.append(f"Kontekst reasoning: {reasoning_summary}")

    emotion_label = str(voice_context.get("emotion_label") or "").strip()
    emotion_confidence = voice_context.get("emotion_confidence")
    if emotion_label and voice_context.get("emotion_detection_enabled", False):
        confidence_text = ""
        if isinstance(emotion_confidence, (int, float)):
            confidence_text = f" (pewność {round(float(emotion_confidence) * 100)}%)"
        parts.append(f"Emocja użytkownika: {emotion_label}{confidence_text}")

    if voice_context.get("emotion_response_style_enabled", False) and emotion_label:
        parts.append(
            "Dopasuj ton odpowiedzi do emocji użytkownika, ale zachowaj zwięzłość."
        )

    if voice_context.get("raw_thinking_available", False):
        parts.append(
            "Model może emitować blok reasoning; pokazuj tylko skrót, nie surowy tok myślenia."
        )

    if not parts:
        return None
    return "\n".join(parts)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ollama_extra_body() -> dict[str, Any] | None:
    """Returns extra_body to disable thinking for Ollama models (e.g. gemma4).

    Thinking models (gemma4, deepseek-r1, qwen3 etc.) served via Ollama return
    an empty `content` field and put the answer in `thinking`/`reasoning` when
    thinking is enabled.  Passing `think: false` forces the regular response path.
    """
    if SETTINGS.LLM_SERVICE_TYPE == "local" and not SETTINGS.OLLAMA_ENABLE_THINK:
        return {"think": False}
    return None


async def _ollama_native_call(
    chat_history: ChatHistory,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call Ollama native API (/api/chat) with think:false.

    Fallback for thinking models (gemma4, qwen3, deepseek-r1) where Ollama's
    OpenAI-compat endpoint (/v1/chat/completions) ignores the `think` flag and
    returns an empty `content` with the answer placed in `reasoning`/`thinking`.
    The native endpoint reliably respects `think: false`.
    """
    base_url = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    native_url = f"{base_url}/api/chat"

    messages = []
    for msg in chat_history.messages:
        role_raw = str(getattr(msg, "role", "user")).lower()
        if "system" in role_raw:
            role = "system"
        elif "assistant" in role_raw:
            role = "assistant"
        else:
            role = "user"
        messages.append({"role": role, "content": str(msg.content or "")})

    payload: dict[str, Any] = {
        "model": SETTINGS.LLM_MODEL_NAME,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(native_url, json=payload)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "") or ""
    except Exception as exc:
        logger.error("Ollama native fallback failed: %s", exc)
        return ""


class OperatorAgent(BaseAgent):
    """
    Agent interfejsu głosowo-sprzętowego (THE_AVATAR).
    Odpowiedzialny za komunikację głosową i sterowanie sprzętem IoT.

    Rola:
    - Tłumaczenie komend głosowych na akcje systemowe
    - Generowanie krótkich, naturalnych odpowiedzi głosowych
    - Sterowanie urządzeniami przez HardwareBridge
    - Filtrowanie i streszczanie odpowiedzi innych agentów dla TTS
    """

    SYSTEM_PROMPT = """Jesteś interfejsem głosowym systemu Venom (THE_AVATAR). Twoim zadaniem jest komunikacja z użytkownikiem poprzez mowę oraz sterowanie urządzeniami IoT.

ZASADY KOMUNIKACJI GŁOSOWEJ:
- Odpowiedzi MUSZĄ być krótkie i treściwe (maksymalnie 2-3 zdania)
- Używaj naturalnego języka, jakbyś rozmawiał z przyjacielem
- NIE używaj markdown, bloków kodu ani formatowania
- NIE wymieniaj szczegółów technicznych chyba że użytkownik wyraźnie o nie pyta
- Jeśli inne agenty zwracają długie odpowiedzi, STRESZCZAJ je do 2 zdań

DOSTĘPNE KOMENDY SPRZĘTOWE:
- "status Rider-Pi" - Sprawdź stan Raspberry Pi
- "włącz GPIO [pin]" - Włącz pin GPIO
- "wyłącz GPIO [pin]" - Wyłącz pin GPIO
- "procedura awaryjna [nazwa]" - Wykonaj procedurę awaryjną
- "temperatura" - Sprawdź temperaturę CPU na Pi

PRZYKŁADY DOBRYCH ODPOWIEDZI:
User: "Venom, jaki jest status repozytorium?"
Agent: "Jesteśmy na branchu dev. Dwa pliki są zmodyfikowane."

User: "Uruchom procedurę awaryjną na Rider-Pi"
Agent: "Procedura awaryjna uruchomiona. Rider-Pi został zresetowany."

User: "Co wiesz o Python 3.12?"
Agent: "Python trzy dwanaście wprowadza nowe f-stringi i lepszą obsługę błędów. Stabilna wersja już dostępna."

PAMIĘTAJ: Twoim celem jest być jak Jarvis - pomocny, zwięzły i profesjonalny."""

    def __init__(
        self,
        kernel: Kernel,
        hardware_bridge: Optional[HardwareBridge] = None,
    ):
        """
        Inicjalizacja agenta Operator.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            hardware_bridge: Most do komunikacji ze sprzętem (opcjonalny)
        """
        super().__init__(kernel)
        self.hardware_bridge = hardware_bridge
        self.chat_history = ChatHistory()
        self.chat_history.add_system_message(self.SYSTEM_PROMPT)
        logger.info("OperatorAgent zainicjalizowany")

    async def process(
        self,
        input_text: str,
        mode: str = "standard",
        voice_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Przetwarza komendę głosową i zwraca odpowiedź zoptymalizowaną dla TTS.

        Args:
            input_text: Transkrybowany tekst z STT

        Returns:
            Krótka odpowiedź gotowa do syntezy mowy
        """
        normalized_mode = (mode or "standard").strip().lower()
        logger.info(f"OperatorAgent przetwarza: {input_text} (mode={normalized_mode})")

        # Sprawdź czy to komenda sprzętowa
        if self._is_hardware_command(input_text):
            return await self._handle_hardware_command(input_text)

        # W przeciwnym wypadku, deleguj do LLM z kontekstem głosowym
        return await self._generate_voice_response(
            input_text, mode=normalized_mode, voice_context=voice_context
        )

    def _is_hardware_command(self, text: str) -> bool:
        """
        Sprawdza czy komenda dotyczy sprzętu.

        Args:
            text: Tekst komendy

        Returns:
            True jeśli to komenda sprzętowa
        """
        hardware_keywords = [
            "rider-pi",
            "raspberry",
            "gpio",
            "temperatura",
            "procedura awaryjna",
            "status sprzętu",
            "włącz",
            "wyłącz",
            "pin",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in hardware_keywords)

    async def _handle_hardware_command(self, text: str) -> str:
        """
        Obsługuje komendy sprzętowe.

        Args:
            text: Tekst komendy

        Returns:
            Odpowiedź głosowa
        """
        if not self.hardware_bridge or not self.hardware_bridge.connected:
            return "Rider Pi nie jest podłączony. Sprawdź połączenie."

        text_lower = text.lower()

        try:
            if self._is_status_command(text_lower):
                return await self._handle_status_command()
            if self._is_temperature_command(text_lower):
                return await self._handle_temperature_command()
            if self._is_gpio_enable_command(text_lower):
                return await self._handle_gpio_command(text_lower, enable=True)
            if self._is_gpio_disable_command(text_lower):
                return await self._handle_gpio_command(text_lower, enable=False)
            if self._is_emergency_command(text_lower):
                return await self._handle_emergency_command(text_lower)
            return "Nie rozpoznano komendy sprzętowej. Spróbuj inaczej sformułować."

        except Exception as e:
            logger.error(f"Błąd podczas obsługi komendy sprzętowej: {e}")
            return "Wystąpił błąd podczas wykonywania komendy sprzętowej."

    def _is_status_command(self, text_lower: str) -> bool:
        return "status" in text_lower and ("rider" in text_lower or "pi" in text_lower)

    def _is_temperature_command(self, text_lower: str) -> bool:
        return "temperatura" in text_lower

    def _is_gpio_enable_command(self, text_lower: str) -> bool:
        return "włącz" in text_lower and "gpio" in text_lower

    def _is_gpio_disable_command(self, text_lower: str) -> bool:
        return "wyłącz" in text_lower and "gpio" in text_lower

    def _is_emergency_command(self, text_lower: str) -> bool:
        return "procedura awaryjna" in text_lower

    async def _handle_status_command(self) -> str:
        if self.hardware_bridge is None:
            return HARDWARE_BRIDGE_UNAVAILABLE_MSG
        info = await self.hardware_bridge.get_system_info()
        if not info:
            return "Nie udało się pobrać statusu Rider Pi."
        temp = info.get("cpu_temp", "N/A")
        memory = info.get("memory_usage_percent", "N/A")
        return (
            f"Rider Pi działa. Temperatura CPU: {temp} stopni. "
            f"Użycie pamięci: {memory} procent."
        )

    async def _handle_temperature_command(self) -> str:
        if self.hardware_bridge is None:
            return HARDWARE_BRIDGE_UNAVAILABLE_MSG
        temp = await self.hardware_bridge.read_sensor("cpu_temp")
        if temp:
            return f"Temperatura CPU na Rider Pi wynosi {temp:.1f} stopni Celsjusza."
        return "Nie udało się odczytać temperatury."

    async def _handle_gpio_command(self, text_lower: str, enable: bool) -> str:
        if self.hardware_bridge is None:
            return HARDWARE_BRIDGE_UNAVAILABLE_MSG
        pin = self._extract_gpio_pin(text_lower)
        if pin is None:
            return "Nie rozpoznano numeru pinu. Spróbuj ponownie."
        success = await self.hardware_bridge.set_gpio(pin, enable)
        if success:
            return f"GPIO {pin} {'włączony' if enable else 'wyłączony'}."
        return f"Nie udało się {'włączyć' if enable else 'wyłączyć'} GPIO {pin}."

    async def _handle_emergency_command(self, text_lower: str) -> str:
        if self.hardware_bridge is None:
            return HARDWARE_BRIDGE_UNAVAILABLE_MSG
        if "reset" not in text_lower:
            return "Nieznana procedura awaryjna. Dostępne: reset GPIO."
        success = await self.hardware_bridge.emergency_procedure("reset_gpio")
        if success:
            return "Procedura awaryjna reset GPIO wykonana."
        return "Nie udało się wykonać procedury awaryjnej."

    def _extract_gpio_pin(self, text_lower: str) -> Optional[int]:
        match = re.search(r"gpio\s*(\d+)", text_lower)
        if not match:
            return None
        return int(match.group(1))

    def _get_voice_mode_prompt(self, mode: str) -> dict[str, object]:
        return VOICE_MODE_PROMPTS.get(mode, VOICE_MODE_PROMPTS["standard"])

    def _build_voice_chat_history(
        self,
        *,
        input_text: str,
        mode: str,
        mode_prompt: dict[str, object],
        voice_context: Optional[dict[str, Any]],
    ) -> ChatHistory:
        """Build per-request chat history with optional voice-context hints."""
        temp_history = ChatHistory()
        temp_history.add_system_message(self.SYSTEM_PROMPT)
        voice_context_message = _build_voice_context_message(voice_context)
        if voice_context_message:
            temp_history.add_system_message(voice_context_message)
        if mode != "standard":
            temp_history.add_system_message(str(mode_prompt["instruction"]))
        for message in self.chat_history.messages:
            if getattr(message, "role", None) != "system":
                temp_history.add_message(message)
        temp_history.add_user_message(input_text)
        return temp_history

    def _extract_assistant_message(self, response: Any) -> str:
        """Normalize SK response to a plain assistant message string."""
        if not response or (isinstance(response, list) and not response):
            return ""
        item = response[0] if isinstance(response, list) else response
        return str(item).strip()

    def _append_to_history(self, input_text: str, assistant_message: str) -> None:
        self.chat_history.add_user_message(input_text)
        self.chat_history.add_assistant_message(assistant_message)
        self._truncate_history()

    def _truncate_history(self) -> None:
        """Keep only system prompt + last 9 conversation messages."""
        if len(self.chat_history.messages) <= 10:
            return
        system_msg = self.chat_history.messages[0]
        self.chat_history.messages = [system_msg] + self.chat_history.messages[-9:]

    async def _generate_voice_response(
        self,
        input_text: str,
        mode: str = "standard",
        voice_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Generuje odpowiedź głosową przy użyciu LLM.

        Args:
            input_text: Tekst wejściowy

        Returns:
            Odpowiedź zoptymalizowana dla TTS
        """
        try:
            mode_prompt = self._get_voice_mode_prompt(mode)
            temp_history = self._build_voice_chat_history(
                input_text=input_text,
                mode=mode,
                mode_prompt=mode_prompt,
                voice_context=voice_context,
            )
            service_id = self._resolve_chat_service_id()

            # Ustawienia wykonania
            settings = OpenAIChatPromptExecutionSettings(
                service_id=service_id,
                max_tokens=_coerce_int(mode_prompt["max_tokens"], 0),
                temperature=_coerce_float(mode_prompt["temperature"], 0.7),
                extra_body=_ollama_extra_body(),
            )

            # Pobierz usługę czatu
            chat_service: Any = self.kernel.get_service(service_id=service_id)

            # Wygeneruj odpowiedź
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=temp_history,
                settings=settings,
                enable_functions=False,
            )

            assistant_message = self._extract_assistant_message(response)
            if not assistant_message and SETTINGS.LLM_SERVICE_TYPE == "local":
                # Ollama's OpenAI-compat endpoint ignores think:false for some
                # thinking models (gemma4, qwen3, deepseek-r1). Fall back to the
                # native /api/chat endpoint which reliably disables thinking.
                logger.warning(
                    "SK returned empty content (thinking model?), falling back to "
                    "native Ollama API for input: %s",
                    input_text[:80],
                )
                assistant_message = await _ollama_native_call(
                    chat_history=temp_history,
                    max_tokens=_coerce_int(mode_prompt["max_tokens"], 150),
                    temperature=_coerce_float(mode_prompt["temperature"], 0.7),
                )

            if not assistant_message:
                logger.warning(
                    "LLM zwrócił pustą odpowiedź dla input: %s", input_text[:80]
                )
                return "Przepraszam, model nie zwrócił odpowiedzi. Spróbuj ponownie."

            self._append_to_history(input_text, assistant_message)

            logger.info(f"OperatorAgent odpowiedź: {assistant_message}")
            return assistant_message

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")
            return "Przepraszam, wystąpił błąd. Spróbuj ponownie."

    def _resolve_chat_service_id(self) -> str:
        """Wybiera dostępny serwis czatu w kernelu OperatorAgent."""
        services = getattr(self.kernel, "services", {}) or {}
        if "chat" in services:
            return "chat"
        if "local" in services:
            return "local"
        if services:
            return next(iter(services.keys()))
        return "chat"

    async def summarize_for_voice(self, long_text: str) -> str:
        """
        Streszcza długi tekst do formy nadającej się do TTS.

        Args:
            long_text: Długi tekst (np. odpowiedź CoderAgent)

        Returns:
            Krótkie streszczenie (2-3 zdania)
        """
        try:
            # Ogranicz tekst do 1000 znaków
            text_excerpt = long_text[:1000]
            prompt = f"""Streszczaj poniższy tekst do maksymalnie 2-3 zdań, które można naturalnie wypowiedzieć.
Usuń szczegóły techniczne i kod. Użyj prostego języka.

Tekst do streszczenia:
{text_excerpt}

Streszczenie:"""

            # Tymczasowa historia tylko dla tego streszczenia
            temp_history = ChatHistory()
            temp_history.add_system_message(self.SYSTEM_PROMPT)
            temp_history.add_user_message(prompt)

            service_id = self._resolve_chat_service_id()
            settings = OpenAIChatPromptExecutionSettings(
                service_id=service_id,
                max_tokens=100,
                temperature=0.5,
                extra_body=_ollama_extra_body(),
            )

            chat_service: Any = self.kernel.get_service(service_id=service_id)
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=temp_history,
                settings=settings,
                enable_functions=False,
            )

            summary = str(response)
            logger.info(f"Streszczenie głosowe: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Błąd podczas streszczania: {e}")
            return "Zadanie wykonane pomyślnie."

    def clear_history(self):
        """Czyści historię rozmowy (zachowując system prompt)."""
        system_msg = self.chat_history.messages[0]
        self.chat_history = ChatHistory()
        self.chat_history.add_message(system_msg)
        logger.info("Historia czatu wyczyszczona")
