"""
Moduł: ghost_agent - Ghost Agent (Upiór) - operator GUI (RPA).

Ghost Agent to specjalny agent zdolny do fizycznej interakcji z interfejsem
systemu operacyjnego. Używa vision grounding do lokalizacji elementów
i input skill do wykonywania akcji.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import ImageGrab
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.execution.skills.input_skill import InputSkill
from venom_core.perception.vision_grounding import VisionGrounding
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ActionStep:
    """Reprezentacja pojedynczego kroku akcji."""

    def __init__(
        self,
        action_type: str,
        description: str,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicjalizacja kroku akcji.

        Args:
            action_type: Typ akcji ('locate', 'click', 'type', 'hotkey', 'wait')
            description: Opis kroku
            params: Parametry akcji
        """
        self.action_type = action_type
        self.description = description
        self.params = params or {}
        self.status = "pending"  # pending, running, success, failed
        self.result = None


class GhostAgent(BaseAgent):
    """
    Ghost Agent - operator GUI (RPA - Robotic Process Automation).

    Rola: Operator interfejsu użytkownika
    Odpowiedzialność:
    - Fizyczna interakcja z GUI (klikanie, pisanie)
    - Lokalizacja elementów wizualnych
    - Wykonywanie sekwencji akcji
    - Weryfikacja rezultatów

    Pętla OODA (Observe-Orient-Decide-Act):
    1. Observe: Zrób screenshot
    2. Orient: Zlokalizuj element (vision grounding)
    3. Decide: Zdecyduj o następnym kroku
    4. Act: Wykonaj akcję (klik, wpisanie tekstu)
    """

    SYSTEM_PROMPT = """Jesteś Ghost Agent - operator GUI (RPA - Robotic Process Automation).

TWOJA ROLA:
- Fizycznie sterujesz myszą i klawiaturą aby wykonywać zadania w aplikacjach
- Widzisz ekran (screenshot) i rozpoznajesz elementy UI
- Działasz metodycznie: najpierw OBSERWUJ, potem DZIAŁAJ, następnie WERYFIKUJ

MOŻLIWOŚCI:
1. Lokalizacja: Znajdź element na ekranie po opisie (np. "czerwony przycisk Save")
2. Klikanie: Kliknij w określone miejsce
3. Pisanie: Wpisz tekst w aktywnym polu
4. Skróty: Użyj skrótów klawiszowych (np. Ctrl+S)

PROTOKÓŁ BEZPIECZEŃSTWA:
- Zawsze weryfikuj czy element istnieje PRZED kliknięciem
- Czekaj na załadowanie się interfejsu (min 1s między akcjami)
- Jeśli nie jesteś pewien, zrób screenshot i oceń sytuację
- Ruch myszy do rogu (0,0) NATYCHMIAST przerywa operację (Fail-Safe)

PRZYKŁADOWY WORKFLOW:
Zadanie: "Otwórz notatnik i napisz 'Hello'"
1. Naciśnij Win+R (otworzy Run dialog)
2. Czekaj 1s
3. Wpisz "notepad"
4. Naciśnij Enter
5. Czekaj 2s (na otwarcie notatnika)
6. Wpisz "Hello"

Pamiętaj: Działaj POWOLI i OSTROŻNIE. Lepiej zrobić więcej screenshots niż ryzykować."""

    def __init__(
        self,
        kernel: Kernel,
        max_steps: Optional[int] = None,
        step_delay: Optional[float] = None,
        verification_enabled: Optional[bool] = None,
        safety_delay: Optional[float] = None,
    ):
        """
        Inicjalizacja Ghost Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            max_steps: Maksymalna liczba kroków do wykonania (domyślnie z SETTINGS)
            step_delay: Opóźnienie między krokami w sekundach (domyślnie z SETTINGS)
            verification_enabled: Czy włączyć weryfikację po każdym kroku (domyślnie z SETTINGS)
            safety_delay: Opóźnienie bezpieczeństwa dla operacji input (domyślnie z SETTINGS)
        """
        super().__init__(kernel)

        # Sprawdź czy Ghost Agent jest włączony w konfiguracji
        if not SETTINGS.ENABLE_GHOST_AGENT:
            logger.warning(
                "Ghost Agent jest wyłączony w konfiguracji (ENABLE_GHOST_AGENT=False). "
                "Aby go włączyć, ustaw ENABLE_GHOST_AGENT=True w .env lub config.py"
            )

        # Użyj wartości z SETTINGS jako domyślnych
        self.max_steps = (
            max_steps if max_steps is not None else SETTINGS.GHOST_MAX_STEPS
        )
        self.step_delay = (
            step_delay if step_delay is not None else SETTINGS.GHOST_STEP_DELAY
        )
        self.verification_enabled = (
            verification_enabled
            if verification_enabled is not None
            else SETTINGS.GHOST_VERIFICATION_ENABLED
        )
        self.safety_delay = (
            safety_delay if safety_delay is not None else SETTINGS.GHOST_SAFETY_DELAY
        )

        # Inicjalizuj komponenty
        self.vision = VisionGrounding()
        self.input_skill = InputSkill(safety_delay=self.safety_delay)

        # Historia wykonanych kroków
        self.action_history: List[ActionStep] = []

        # Stan agenta
        self.is_running = False
        self.emergency_stop = False

        logger.info(
            f"GhostAgent zainicjalizowany (max_steps={self.max_steps}, "
            f"step_delay={self.step_delay}s, verification={self.verification_enabled}, "
            f"safety_delay={self.safety_delay}s)"
        )

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie i wykonuje sekwencję akcji GUI.

        Args:
            input_text: Opis zadania (np. "Otwórz Spotify i włącz następną piosenkę")

        Returns:
            Raport z wykonania zadania
        """
        # Sprawdź czy agent jest włączony
        if not SETTINGS.ENABLE_GHOST_AGENT:
            return (
                "❌ Ghost Agent jest wyłączony w konfiguracji. "
                "Ustaw ENABLE_GHOST_AGENT=True w .env aby go włączyć."
            )

        if self.is_running:
            return (
                "❌ Ghost Agent już działa. Poczekaj na zakończenie bieżącego zadania."
            )

        try:
            self.is_running = True
            self.emergency_stop = False
            self.action_history = []

            logger.info(f"Ghost Agent rozpoczyna zadanie: {input_text}")

            # Krok 1: Planowanie
            plan = await self._create_action_plan(input_text)

            if not plan:
                return "❌ Nie mogę stworzyć planu akcji dla tego zadania."

            # Krok 2: Wykonanie planu (OODA Loop)
            result = await self._execute_plan(plan)

            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas wykonywania zadania: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

        finally:
            self.is_running = False

    async def _create_action_plan(self, task: str) -> List[ActionStep]:
        """
        Tworzy plan akcji dla zadania używając LLM.

        Args:
            task: Opis zadania

        Returns:
            Lista kroków akcji
        """
        logger.info(f"Tworzenie planu dla: {task}")

        # Prompt dla LLM do generowania planu akcji
        planning_prompt = f"""Jesteś ekspertem od automatyzacji GUI. Stwórz szczegółowy plan akcji dla następującego zadania:

ZADANIE: {task}

Dostępne akcje:
1. "locate" - Znajdź element na ekranie po opisie (params: description)
2. "click" - Kliknij w element (params: x, y lub use_located: true)
3. "type" - Wpisz tekst (params: text)
4. "hotkey" - Użyj skrótu klawiszowego (params: keys, np. "win+r", "ctrl+s", "enter")
5. "wait" - Czekaj określony czas (params: duration w sekundach)
6. "screenshot" - Zrób screenshot ekranu (brak params)

ZASADY:
- Zawsze zaczynaj od screenshot jeśli potrzeba zlokalizować element
- Dodawaj opóźnienia (wait) między akcjami (min 1s dla dialogów, 2s dla aplikacji)
- Dla otwierania aplikacji używaj Win+R, potem type, potem Enter
- Dla lokalizacji elementów najpierw screenshot, potem locate, potem click
- Bądź konkretny w opisach elementów do locate

Zwróć plan jako JSON array w formacie:
[
  {{"action_type": "hotkey", "description": "Otwórz dialog Run", "params": {{"keys": "win+r"}}}},
  {{"action_type": "wait", "description": "Czekaj na otwarcie", "params": {{"duration": 1.0}}}}
]

ODPOWIEDŹ (tylko JSON, bez dodatkowych komentarzy):"""

        try:
            # Użyj LLM do wygenerowania planu
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=planning_prompt)
            )

            chat_service = self.kernel.get_service()
            settings = OpenAIChatPromptExecutionSettings()
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=settings,
                enable_functions=False,
            )

            response_text = str(response).strip()

            # Wyciągnij JSON z odpowiedzi (może być otoczony markdown)

            # Usuń markdown code blocks jeśli istnieją
            if "```json" in response_text:
                response_text = (
                    response_text.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            # Parsuj JSON
            plan_data = json.loads(response_text)

            # Walidacja typu
            if not isinstance(plan_data, list):
                logger.error(
                    f"LLM zwrócił niepoprawny format (oczekiwano listy): {type(plan_data)}"
                )
                raise ValueError("LLM nie zwrócił JSON array")

            # Konwertuj na ActionSteps
            plan = []
            for step_data in plan_data:
                if not isinstance(step_data, dict):
                    logger.warning(f"Pomijam niepoprawny krok: {step_data}")
                    continue
                step = ActionStep(
                    action_type=step_data.get("action_type"),
                    description=step_data.get("description", ""),
                    params=step_data.get("params", {}),
                )
                plan.append(step)

            logger.info(f"Plan utworzony przez LLM: {len(plan)} kroków")
            return plan

        except Exception as e:
            logger.error(f"Błąd podczas generowania planu przez LLM: {e}")
            logger.warning("Używam fallback planu heurystycznego")
            return self._build_fallback_plan(task)

    def _build_fallback_plan(self, task: str) -> List[ActionStep]:
        """Tworzy deterministyczny plan akcji gdy LLM nie jest dostępny."""

        task_lower = task.lower()
        steps: List[ActionStep] = []

        def extract_text_to_type() -> Optional[str]:
            matches = re.findall(r"['\"]([^'\"]+)['\"]", task)
            if matches:
                return matches[0]
            return None

        # Heurystyka dla Notatnika
        if "notatnik" in task_lower or "notepad" in task_lower:
            steps.append(
                ActionStep("hotkey", "Otwórz okno 'Uruchom'", {"keys": "win+r"})
            )
            steps.append(
                ActionStep("wait", "Czekaj na otwarcie okna", {"duration": 1.0})
            )
            steps.append(
                ActionStep("type", "Wpisz nazwę aplikacji", {"text": "notepad"})
            )
            steps.append(ActionStep("hotkey", "Potwierdź enter", {"keys": "enter"}))
            steps.append(
                ActionStep("wait", "Czekaj aż Notatnik się pojawi", {"duration": 2.0})
            )

            text_to_type = extract_text_to_type()
            if text_to_type:
                steps.append(
                    ActionStep(
                        "type",
                        f"Wpisz tekst '{text_to_type}'",
                        {"text": text_to_type},
                    )
                )
            else:
                steps.append(
                    ActionStep(
                        "type",
                        "Wpisz treść zadania",
                        {"text": "Hello Venom"},
                    )
                )

            steps.append(ActionStep("screenshot", "Zrób screenshot do weryfikacji", {}))
            return steps

        # Heurystyka dla Spotify / multimediów
        if "spotify" in task_lower:
            steps.append(
                ActionStep(
                    "screenshot",
                    "Zrób screenshot aby znaleźć okno Spotify",
                    {},
                )
            )
            steps.append(
                ActionStep(
                    "locate",
                    "Zlokalizuj okno Spotify",
                    {"description": "okno aplikacji Spotify"},
                )
            )
            steps.append(
                ActionStep("click", "Aktywuj okno Spotify", {"use_located": True})
            )
            steps.append(
                ActionStep(
                    "hotkey",
                    "Przejdź do następnej piosenki",
                    {"keys": "ctrl+right"},
                )
            )
            steps.append(
                ActionStep(
                    "wait",
                    "Czekaj aż utwór się zmieni",
                    {"duration": 1.5},
                )
            )
            steps.append(ActionStep("screenshot", "Zweryfikuj odtwarzanie", {}))
            return steps

        # Domyślny plan: screenshot + orientacja
        steps.append(ActionStep("screenshot", "Zrób screenshot ekranu", {}))
        steps.append(
            ActionStep(
                "locate",
                "Spróbuj znaleźć opisany element",
                {"description": task},
            )
        )
        steps.append(
            ActionStep("wait", "Czekaj na potwierdzenie zadania", {"duration": 1.0})
        )
        return steps

    async def _execute_plan(self, plan: List[ActionStep]) -> str:
        """
        Wykonuje plan akcji (OODA Loop).

        Args:
            plan: Lista kroków do wykonania

        Returns:
            Raport z wykonania
        """
        logger.info(f"Rozpoczynam wykonywanie planu ({len(plan)} kroków)")

        last_screenshot = None
        located_coords = None

        for i, step in enumerate(plan):
            if self.emergency_stop:
                logger.warning("Emergency stop aktywny - przerywam plan")
                return "🛑 Plan przerwany przez Emergency Stop"

            if i >= self.max_steps:
                logger.warning(f"Osiągnięto maksymalną liczbę kroków: {self.max_steps}")
                break

            step.status = "running"
            logger.info(f"Krok {i + 1}/{len(plan)}: {step.description}")

            try:
                # Wykonaj krok na podstawie typu
                if step.action_type == "screenshot":
                    last_screenshot = ImageGrab.grab()
                    step.result = f"Screenshot: {last_screenshot.size}"
                    step.status = "success"

                elif step.action_type == "locate":
                    if not last_screenshot:
                        last_screenshot = ImageGrab.grab()

                    description = step.params.get("description", "")
                    coords = await self.vision.locate_element(
                        last_screenshot, description
                    )

                    if coords:
                        located_coords = coords
                        step.result = f"Element znaleziony: {coords}"
                        step.status = "success"
                    else:
                        step.result = "Element nie znaleziony"
                        step.status = "failed"
                        logger.warning(f"Nie znaleziono elementu: {description}")
                        # Próbujemy kontynuować

                elif step.action_type == "click":
                    use_located = step.params.get("use_located", False)

                    if use_located and located_coords:
                        x, y = located_coords
                    else:
                        x = step.params.get("x", 0)
                        y = step.params.get("y", 0)

                    result = await self.input_skill.mouse_click(x, y)
                    step.result = result
                    step.status = "success" if "✅" in result else "failed"

                elif step.action_type == "type":
                    text = step.params.get("text", "")
                    result = await self.input_skill.keyboard_type(text)
                    step.result = result
                    step.status = "success" if "✅" in result else "failed"

                elif step.action_type == "hotkey":
                    keys = step.params.get("keys", "")
                    result = await self.input_skill.keyboard_hotkey(keys)
                    step.result = result
                    step.status = "success" if "✅" in result else "failed"

                elif step.action_type == "wait":
                    duration = step.params.get("duration", 1.0)
                    await asyncio.sleep(duration)
                    step.result = f"Oczekiwano {duration}s"
                    step.status = "success"

                else:
                    step.result = f"Nieznany typ akcji: {step.action_type}"
                    step.status = "failed"

                self.action_history.append(step)

                # Weryfikacja po każdym kroku jeśli włączona
                if self.verification_enabled and step.status == "success":
                    # Zrób screenshot po akcji i sprawdź czy akcja zakończyła się sukcesem
                    verification_result = await self._verify_step_result(
                        step, last_screenshot
                    )
                    if not verification_result:
                        logger.warning(f"Weryfikacja kroku {i + 1} nie powiodła się")
                        step.status = "failed"
                        step.result += " (weryfikacja nieudana)"

                # Czekaj między krokami
                if step.action_type != "wait":
                    await asyncio.sleep(self.step_delay)

            except Exception as e:
                step.status = "failed"
                step.result = f"Błąd: {e}"
                logger.error(f"Błąd w kroku {i + 1}: {e}", exc_info=True)
                self.action_history.append(step)

        # Generuj raport
        return self._generate_report()

    async def _verify_step_result(
        self, step: ActionStep, pre_action_screenshot
    ) -> bool:
        """
        Weryfikuje rezultat wykonania kroku porównując stan przed i po akcji.

        Args:
            step: Wykonany krok akcji
            pre_action_screenshot: Screenshot przed wykonaniem akcji

        Returns:
            True jeśli weryfikacja przebiegła pomyślnie, False w przeciwnym wypadku
        """
        try:
            # Zrób screenshot po akcji
            post_action_screenshot = ImageGrab.grab()

            # Dla różnych typów akcji stosujemy różne strategie weryfikacji
            if step.action_type == "type":
                # Dla wpisywania tekstu trudno zweryfikować wizualnie bez OCR
                # Zakładamy sukces jeśli akcja się wykonała
                logger.debug("Weryfikacja 'type': zakładam sukces (brak OCR)")
                return True

            elif step.action_type in ["hotkey", "click"]:
                # Dla kliknięć i skrótów sprawdzamy czy coś się zmieniło na ekranie
                # Konwertuj na numpy arrays dla porównania
                pre_array = (
                    np.array(pre_action_screenshot) if pre_action_screenshot else None
                )
                post_array = np.array(post_action_screenshot)

                if pre_array is None:
                    logger.debug("Brak pre-screenshot, zakładam sukces")
                    return True

                # Oblicz średnią różnicę między obrazami (stabilne numerycznie)
                diff = np.mean(
                    np.abs(post_array.astype(np.float32) - pre_array.astype(np.float32))
                )
                # diff to średnia różnica na piksel (0-255)

                # Jeśli różnica > 0.5% (średnia zmiana piksela), uznajemy że coś się zmieniło
                change_percent = (diff / 255.0) * 100  # Normalizuj do 0-100%
                logger.debug(f"Zmiana ekranu: {change_percent:.2f}%")

                if change_percent > 0.5:
                    logger.debug("Wykryto zmianę ekranu - weryfikacja OK")
                    return True
                else:
                    logger.warning("Brak znaczącej zmiany ekranu - możliwy problem")
                    return False

            elif step.action_type == "locate":
                # Dla locate sprawdzamy czy element został znaleziony
                if step.result and "znaleziony" in step.result:
                    return True
                return False

            elif step.action_type in ["wait", "screenshot"]:
                # Te akcje zawsze są OK
                return True

            else:
                # Nieznany typ akcji - zakładamy sukces
                logger.debug(f"Nieznany typ akcji {step.action_type}, zakładam sukces")
                return True

        except Exception as e:
            logger.error(f"Błąd podczas weryfikacji kroku: {e}")
            # W przypadku błędu weryfikacji zakładamy sukces (fail-open)
            return True

    def _generate_report(self) -> str:
        """
        Generuje raport z wykonania zadania.

        Returns:
            Tekstowy raport
        """
        total = len(self.action_history)
        success = sum(1 for step in self.action_history if step.status == "success")
        failed = sum(1 for step in self.action_history if step.status == "failed")

        report = f"""
📊 RAPORT GHOST AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wykonane kroki: {total}
Udane: {success} ✅
Nieudane: {failed} ❌

SZCZEGÓŁY:
"""

        for i, step in enumerate(self.action_history):
            status_icon = "✅" if step.status == "success" else "❌"
            report += f"{i + 1}. {status_icon} {step.description}\n"
            if step.result:
                report += f"   → {step.result}\n"

        if failed > 0:
            report += "\n⚠️ Niektóre kroki się nie powiodły. Sprawdź logi."

        return report

    def emergency_stop_trigger(self):
        """Aktywuje emergency stop."""
        logger.warning("🛑 EMERGENCY STOP AKTYWOWANY!")
        self.emergency_stop = True
        self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status agenta.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self.is_running,
            "emergency_stop": self.emergency_stop,
            "max_steps": self.max_steps,
            "step_delay": self.step_delay,
            "verification_enabled": self.verification_enabled,
            "action_history_length": len(self.action_history),
            "screen_size": self.input_skill.get_screen_size(),
        }
