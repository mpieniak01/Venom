"""Moduł: operator - agent interfejsu głosowo-sprzętowego."""

import re
from typing import Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory

from venom_core.agents.base import BaseAgent
from venom_core.infrastructure.hardware_pi import HardwareBridge
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


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

    async def process(self, input_text: str) -> str:
        """
        Przetwarza komendę głosową i zwraca odpowiedź zoptymalizowaną dla TTS.

        Args:
            input_text: Transkrybowany tekst z STT

        Returns:
            Krótka odpowiedź gotowa do syntezy mowy
        """
        logger.info(f"OperatorAgent przetwarza: {input_text}")

        # Sprawdź czy to komenda sprzętowa
        if await self._is_hardware_command(input_text):
            return await self._handle_hardware_command(input_text)

        # W przeciwnym wypadku, deleguj do LLM z kontekstem głosowym
        return await self._generate_voice_response(input_text)

    async def _is_hardware_command(self, text: str) -> bool:
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
            # Status Rider-Pi
            if "status" in text_lower and ("rider" in text_lower or "pi" in text_lower):
                info = await self.hardware_bridge.get_system_info()
                if info:
                    temp = info.get("cpu_temp", "N/A")
                    memory = info.get("memory_usage_percent", "N/A")
                    return f"Rider Pi działa. Temperatura CPU: {temp} stopni. Użycie pamięci: {memory} procent."
                else:
                    return "Nie udało się pobrać statusu Rider Pi."

            # Temperatura
            elif "temperatura" in text_lower:
                temp = await self.hardware_bridge.read_sensor("cpu_temp")
                if temp:
                    return f"Temperatura CPU na Rider Pi wynosi {temp:.1f} stopni Celsjusza."
                else:
                    return "Nie udało się odczytać temperatury."

            # GPIO control
            elif "włącz" in text_lower and "gpio" in text_lower:
                # Wyciągnij numer pinu (bardzo prosta heurystyka)
                match = re.search(r"gpio\s*(\d+)", text_lower)
                if match:
                    pin = int(match.group(1))
                    success = await self.hardware_bridge.set_gpio(pin, True)
                    if success:
                        return f"GPIO {pin} włączony."
                    else:
                        return f"Nie udało się włączyć GPIO {pin}."
                else:
                    return "Nie rozpoznano numeru pinu. Spróbuj ponownie."

            elif "wyłącz" in text_lower and "gpio" in text_lower:
                match = re.search(r"gpio\s*(\d+)", text_lower)
                if match:
                    pin = int(match.group(1))
                    success = await self.hardware_bridge.set_gpio(pin, False)
                    if success:
                        return f"GPIO {pin} wyłączony."
                    else:
                        return f"Nie udało się wyłączyć GPIO {pin}."
                else:
                    return "Nie rozpoznano numeru pinu. Spróbuj ponownie."

            # Procedura awaryjna
            elif "procedura awaryjna" in text_lower:
                if "reset" in text_lower:
                    success = await self.hardware_bridge.emergency_procedure(
                        "reset_gpio"
                    )
                    if success:
                        return "Procedura awaryjna reset GPIO wykonana."
                    else:
                        return "Nie udało się wykonać procedury awaryjnej."
                else:
                    return "Nieznana procedura awaryjna. Dostępne: reset GPIO."

            else:
                return "Nie rozpoznano komendy sprzętowej. Spróbuj inaczej sformułować."

        except Exception as e:
            logger.error(f"Błąd podczas obsługi komendy sprzętowej: {e}")
            return "Wystąpił błąd podczas wykonywania komendy sprzętowej."

    async def _generate_voice_response(self, input_text: str) -> str:
        """
        Generuje odpowiedź głosową przy użyciu LLM.

        Args:
            input_text: Tekst wejściowy

        Returns:
            Odpowiedź zoptymalizowana dla TTS
        """
        try:
            # Dodaj wiadomość użytkownika
            self.chat_history.add_user_message(input_text)

            # Ustawienia wykonania
            settings = OpenAIChatPromptExecutionSettings(
                service_id="chat",
                max_tokens=150,  # Krótkie odpowiedzi
                temperature=0.7,
            )

            # Pobierz usługę czatu
            chat_service: Any = self.kernel.get_service(service_id="chat")

            # Wygeneruj odpowiedź
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=self.chat_history,
                settings=settings,
                enable_functions=False,
            )

            assistant_message = str(response)

            # Dodaj do historii
            self.chat_history.add_assistant_message(assistant_message)

            # Ogranicz historię (tylko ostatnie 10 wiadomości)
            if len(self.chat_history.messages) > 10:
                # Zachowaj system prompt
                system_msg = self.chat_history.messages[0]
                self.chat_history.messages = [system_msg] + self.chat_history.messages[
                    -9:
                ]

            logger.info(f"OperatorAgent odpowiedź: {assistant_message}")
            return assistant_message

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")
            return "Przepraszam, wystąpił błąd. Spróbuj ponownie."

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

            settings = OpenAIChatPromptExecutionSettings(
                service_id="chat",
                max_tokens=100,
                temperature=0.5,
            )

            chat_service: Any = self.kernel.get_service(service_id="chat")
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
