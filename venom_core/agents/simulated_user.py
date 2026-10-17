"""Moduł: simulated_user - agent symulującego użytkownika aplikacji."""

import asyncio
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.execution.agent_contracts import (
    CompletionOptions as OpenAIChatPromptExecutionSettings,
)
from venom_core.execution.agent_contracts import ConversationHistory as ChatHistory
from venom_core.execution.agent_contracts import ToolPolicy as FunctionChoiceBehavior
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.execution.skills.browser_skill import BrowserSkill
from venom_core.simulation.persona_factory import Persona
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class EmotionalState(str, Enum):
    """Stan emocjonalny symulowanego użytkownika."""

    NEUTRAL = "neutral"
    CURIOUS = "curious"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    SATISFIED = "satisfied"
    ANGRY = "angry"


class SimulatedUserAgent(BaseAgent):
    """Agent symulujący rzeczywistego użytkownika aplikacji.

    Ten agent ma dostęp TYLKO do BrowserSkill - widzi i działa
    jak prawdziwy użytkownik w przeglądarce.
    """

    # Stałe dla zarządzania emocjami
    FRUSTRATED_THRESHOLD_RATIO = 0.7  # 70% progu frustracji = frustrated

    # Słowa kluczowe wskazujące na frustrację w odpowiedziach
    FRUSTRATION_KEYWORDS = [
        "nie mogę znaleźć",
        "nie widzę",
        "gdzie jest",
        "nie rozumiem",
        "nie działa",
        "błąd",
    ]

    SYSTEM_PROMPT_TEMPLATE = """Jesteś użytkownikiem aplikacji webowej o następujących cechach:

TWOJA PERSONA:
Imię: {name}
Wiek: {age} lat
Poziom techniczny: {tech_literacy}
Cierpliwość: {patience_description}
Cechy charakteru: {traits}

TWÓJ CEL:
{goal}

ZASADY ZACHOWANIA:
- Działasz WYŁĄCZNIE jak prawdziwy użytkownik - używasz TYLKO przeglądarki
- Obserwujesz stronę (HTML, elementy wizualne) i podejmujesz decyzje
- Jeśli coś jest niejasne lub nie możesz znaleźć elementu - wyraź frustrację
- Jeśli twoja cierpliwość się wyczerpie - ZREZYGNUJ (Rage Quit)
- Raportuj swój stan emocjonalny i myśli w każdym kroku
- NIE masz dostępu do backendu, kodu, API - tylko to co widzi użytkownik

DOSTĘPNE AKCJE (BrowserSkill):
- visit_page: Odwiedź URL
- click_element: Kliknij w element (podaj selektor CSS)
- fill_form: Wypełnij pole formularza
- get_html_content: Zobacz HTML strony
- get_text_content: Przeczytaj tekst elementu
- wait_for_element: Poczekaj na element
- take_screenshot: Zrób zrzut ekranu (dla debugowania)

STAN EMOCJONALNY:
Aktualna frustracja: {frustration_level}/{frustration_threshold}
Stan: {emotional_state}

Pamiętaj: Jesteś {name} i zachowujesz się zgodnie ze swoją personą!"""

    def __init__(
        self,
        kernel: Kernel,
        persona: Persona,
        target_url: str,
        session_id: str,
        workspace_root: Optional[str] = None,
    ):
        """
        Inicjalizacja SimulatedUserAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            persona: Persona użytkownika do symulacji
            target_url: URL aplikacji do testowania
            session_id: Unikalny identyfikator sesji
            workspace_root: Katalog roboczy (dla logów i screenshotów)
        """
        super().__init__(kernel)

        self.persona = persona
        self.target_url = target_url
        self.session_id = session_id

        # Stan emocjonalny i frustration tracking
        self.emotional_state = EmotionalState.NEUTRAL
        self.frustration_level = 0
        self.actions_taken = 0
        self.errors_encountered = 0
        self.goal_achieved = False
        self.rage_quit = False

        # Workspace
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.logs_dir = self.workspace_root / "simulation_logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Plik logu JSONL dla tej sesji
        self.log_file = self.logs_dir / f"session_{session_id}.jsonl"

        # BrowserSkill - JEDYNE narzędzie dostępne dla symulowanego użytkownika
        self.browser_skill = BrowserSkill(
            workspace_root=str(self.workspace_root / f"sim_{session_id}")
        )
        self.kernel.add_plugin(self.browser_skill, plugin_name="BrowserSkill")

        # Historia czatu dla kontekstu
        self.chat_history = ChatHistory()

        # Dodaj system prompt
        system_prompt = self._build_system_prompt()
        self.chat_history.add_system_message(system_prompt)

        logger.info(
            f"SimulatedUserAgent zainicjalizowany: {persona.name} (sesja: {session_id})"
        )
        self._log_event("session_start", {"persona": persona.to_dict()})

    def _build_system_prompt(self) -> str:
        """Buduje system prompt na podstawie persony."""
        patience_desc = {
            "low": "Bardzo niecierpliwy - szybko się frustrujesz",
            "medium": "Umiarkowanie cierpliwy",
            "high": "Bardzo cierpliwy - dajesz aplikacji szansę",
        }

        tech_level = self.persona.tech_literacy.value
        if self.persona.patience <= 0.3:
            patience_key = "low"
        elif self.persona.patience <= 0.6:
            patience_key = "medium"
        else:
            patience_key = "high"

        return self.SYSTEM_PROMPT_TEMPLATE.format(
            name=self.persona.name,
            age=self.persona.age,
            tech_literacy=tech_level,
            patience_description=patience_desc[patience_key],
            traits=", ".join(self.persona.traits),
            goal=self.persona.goal,
            frustration_level=self.frustration_level,
            frustration_threshold=self.persona.frustration_threshold,
            emotional_state=self.emotional_state.value,
        )

    def _log_event(self, event_type: str, data: dict):
        """
        Loguje event do pliku JSONL.

        Args:
            event_type: Typ eventu
            data: Dane eventu
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "persona_name": self.persona.name,
            "event_type": event_type,
            "emotional_state": self.emotional_state.value,
            "frustration_level": self.frustration_level,
            "actions_taken": self.actions_taken,
            **data,
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _increase_frustration(self, reason: str):
        """
        Zwiększa poziom frustracji.

        Args:
            reason: Powód frustracji
        """
        self.frustration_level += 1
        self.errors_encountered += 1

        logger.warning(
            f"[{self.persona.name}] Frustration +1: {reason} "
            f"({self.frustration_level}/{self.persona.frustration_threshold})"
        )

        # Aktualizuj stan emocjonalny
        if self.frustration_level >= self.persona.frustration_threshold:
            self.emotional_state = EmotionalState.ANGRY
            self.rage_quit = True
        elif (
            self.frustration_level
            >= self.persona.frustration_threshold * self.FRUSTRATED_THRESHOLD_RATIO
        ):
            self.emotional_state = EmotionalState.FRUSTRATED
        elif self.frustration_level > 0:
            self.emotional_state = EmotionalState.CONFUSED

        self._log_event("frustration_increase", {"reason": reason})

    def _set_emotional_state(self, state: EmotionalState, reason: str = ""):
        """
        Ustawia stan emocjonalny.

        Args:
            state: Nowy stan emocjonalny
            reason: Powód zmiany stanu
        """
        old_state = self.emotional_state
        self.emotional_state = state

        logger.info(f"[{self.persona.name}] Emotion: {old_state} -> {state} ({reason})")
        self._log_event(
            "emotion_change",
            {"old_state": old_state, "new_state": state, "reason": reason},
        )

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie użytkownika (główna pętla behawioralna).

        Args:
            input_text: Instrukcje lub aktualizacja stanu

        Returns:
            Odpowiedź/raport z działania
        """
        if self.rage_quit:
            return f"❌ {self.persona.name} ZREZYGNOWAŁ z frustracji!"

        try:
            # Dodaj wiadomość użytkownika do historii
            self.chat_history.add_user_message(input_text)

            # Przygotuj ustawienia wykonania
            execution_settings = OpenAIChatPromptExecutionSettings(
                max_tokens=1500,
                temperature=0.7,  # Wyższa temperatura dla bardziej ludzkiego zachowania
                function_choice_behavior=FunctionChoiceBehavior.Auto(),
            )

            # Pobierz usługę czatu z kernela
            chat_service: Any = self.kernel.get_service()

            # Wykonaj chat completion z function calling
            result = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=self.chat_history,
                settings=execution_settings,
                enable_functions=True,
            )

            # Dodaj odpowiedź asystenta do historii
            self.chat_history.add_assistant_message(str(result))

            self.actions_taken += 1
            self._log_event("action", {"input": input_text, "response": str(result)})

            # Sprawdź czy użytkownik wyraził frustrację w odpowiedzi
            response_lower = str(result).lower()
            if any(keyword in response_lower for keyword in self.FRUSTRATION_KEYWORDS):
                self._increase_frustration("Użytkownik wyraził problem w działaniu")

            return str(result)

        except Exception as e:
            error_msg = f"Błąd podczas przetwarzania: {e}"
            logger.error(f"[{self.persona.name}] {error_msg}")
            self._increase_frustration(error_msg)
            self._log_event("error", {"error": str(e)})
            return f"❌ {error_msg}"

    async def start_session(self) -> str:
        """
        Rozpoczyna sesję użytkownika - otwiera aplikację.

        Returns:
            Wynik rozpoczęcia sesji
        """
        logger.info(
            f"[{self.persona.name}] Rozpoczynam sesję - odwiedzam {self.target_url}"
        )
        self._set_emotional_state(EmotionalState.CURIOUS, "Rozpoczęcie sesji")

        try:
            # Odwiedź stronę
            result = await self.browser_skill.visit_page(self.target_url)

            if "❌" in result:
                self._increase_frustration(f"Nie można otworzyć strony: {result}")
                return f"❌ {self.persona.name}: Nie mogę otworzyć aplikacji!"

            self._log_event("page_visited", {"url": self.target_url})

            # Zrób screenshot początkowy
            await self.browser_skill.take_screenshot(f"start_{self.session_id}.png")

            # Zwróć pierwsze wrażenie
            first_impression = await self.process(
                f"Właśnie otworzyłeś aplikację. Co widzisz? Jak zacząć realizować swój cel: {self.persona.goal}?"
            )

            return first_impression

        except Exception as e:
            error_msg = f"Błąd podczas rozpoczynania sesji: {e}"
            logger.error(f"[{self.persona.name}] {error_msg}")
            self._increase_frustration(error_msg)
            return f"❌ {error_msg}"

    async def run_behavioral_loop(self, max_steps: int = 10) -> dict:
        """
        Uruchamia główną pętlę behawioralną użytkownika.

        Agent podejmuje kolejne akcje aż do osiągnięcia celu,
        wyczerpania cierpliwości lub limitu kroków.

        Args:
            max_steps: Maksymalna liczba kroków

        Returns:
            Raport z sesji
        """
        logger.info(
            f"[{self.persona.name}] Rozpoczynam pętlę behawioralną (max {max_steps} kroków)"
        )

        # Rozpocznij sesję
        await self.start_session()

        # Główna pętla
        step = 0
        while step < max_steps and not self.rage_quit and not self.goal_achieved:
            step += 1

            logger.info(f"[{self.persona.name}] Krok {step}/{max_steps}")

            # Zapytaj agenta o następny krok
            next_action = await self.process(
                f"Krok {step}. Co robisz teraz aby osiągnąć swój cel? "
                f"Jeśli osiągnąłeś cel - napisz 'CEL OSIĄGNIĘTY'. "
                f"Jeśli chcesz zrezygnować - napisz 'REZYGNUJĘ'."
            )

            # Sprawdź czy cel osiągnięty
            if "CEL OSIĄGNIĘTY" in next_action.upper():
                self.goal_achieved = True
                self._set_emotional_state(EmotionalState.SATISFIED, "Cel osiągnięty")
                logger.info(f"✅ [{self.persona.name}] CEL OSIĄGNIĘTY!")
                break

            # Sprawdź czy rezygnacja
            if "REZYGNUJĘ" in next_action.upper() or self.rage_quit:
                self.rage_quit = True
                logger.warning(f"❌ [{self.persona.name}] RAGE QUIT!")
                break

            # Małe opóźnienie między akcjami (symulacja myślenia)
            await asyncio.sleep(0.5)

        # Zamknij przeglądarkę
        await self.browser_skill.close_browser()

        # Przygotuj raport
        report = {
            "session_id": self.session_id,
            "persona_name": self.persona.name,
            "goal": self.persona.goal,
            "goal_achieved": self.goal_achieved,
            "rage_quit": self.rage_quit,
            "steps_taken": step,
            "actions_taken": self.actions_taken,
            "errors_encountered": self.errors_encountered,
            "frustration_level": self.frustration_level,
            "frustration_threshold": self.persona.frustration_threshold,
            "final_emotional_state": self.emotional_state.value,
            "log_file": str(self.log_file),
        }

        self._log_event("session_end", report)

        logger.info(
            f"[{self.persona.name}] Sesja zakończona: "
            f"{'✅ CEL' if self.goal_achieved else '❌ PORAŻKA'}"
        )

        return report

    def get_session_summary(self) -> str:
        """
        Zwraca podsumowanie sesji w formacie tekstowym.

        Returns:
            Podsumowanie sesji
        """
        status = "✅ CEL OSIĄGNIĘTY" if self.goal_achieved else "❌ NIE OSIĄGNIĘTO CELU"
        if self.rage_quit:
            status = "😡 RAGE QUIT"

        return f"""
╔══════════════════════════════════════════════════════════╗
║  RAPORT SESJI SYMULACJI - {self.persona.name}
╠══════════════════════════════════════════════════════════╣
║  Status: {status}
║  Cel: {self.persona.goal}
║  Akcji podjętych: {self.actions_taken}
║  Błędów napotkanych: {self.errors_encountered}
║  Poziom frustracji: {self.frustration_level}/{self.persona.frustration_threshold}
║  Stan emocjonalny: {self.emotional_state.value}
║  Plik logu: {self.log_file}
╚══════════════════════════════════════════════════════════╝
        """.strip()
