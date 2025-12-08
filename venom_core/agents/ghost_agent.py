"""
Moduł: ghost_agent - Ghost Agent (Upiór) - operator GUI (RPA).

Ghost Agent to specjalny agent zdolny do fizycznej interakcji z interfejsem
systemu operacyjnego. Używa vision grounding do lokalizacji elementów
i input skill do wykonywania akcji.
"""

import asyncio
from typing import Any, Dict, List, Optional

from PIL import ImageGrab
from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
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
        max_steps: int = 20,
        step_delay: float = 1.0,
        verification_enabled: bool = True,
    ):
        """
        Inicjalizacja Ghost Agent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            max_steps: Maksymalna liczba kroków do wykonania
            step_delay: Opóźnienie między krokami (sekundy)
            verification_enabled: Czy włączyć weryfikację po każdym kroku
        """
        super().__init__(kernel)
        self.max_steps = max_steps
        self.step_delay = step_delay
        self.verification_enabled = verification_enabled

        # Inicjalizuj komponenty
        self.vision = VisionGrounding()
        self.input_skill = InputSkill(safety_delay=step_delay)

        # Historia wykonanych kroków
        self.action_history: List[ActionStep] = []

        # Stan agenta
        self.is_running = False
        self.emergency_stop = False

        logger.info(
            f"GhostAgent zainicjalizowany (max_steps={max_steps}, "
            f"delay={step_delay}s, verification={verification_enabled})"
        )

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie i wykonuje sekwencję akcji GUI.

        Args:
            input_text: Opis zadania (np. "Otwórz Spotify i włącz następną piosenkę")

        Returns:
            Raport z wykonania zadania
        """
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
        Tworzy plan akcji dla zadania.

        Args:
            task: Opis zadania

        Returns:
            Lista kroków akcji
        """
        logger.info(f"Tworzenie planu dla: {task}")

        # W pełnej implementacji tutaj byłoby LLM które generuje plan
        # Na razie używamy prostej heurystyki dla przykładowych zadań

        plan = []

        # Przykład 1: "Otwórz notatnik i napisz 'Hello Venom'"
        if "notatnik" in task.lower() or "notepad" in task.lower():
            plan.append(
                ActionStep(
                    "hotkey",
                    "Otwórz dialog Run",
                    {"keys": "win+r"},
                )
            )
            plan.append(ActionStep("wait", "Czekaj na otwarcie", {"duration": 1.0}))
            plan.append(
                ActionStep(
                    "type",
                    "Wpisz 'notepad'",
                    {"text": "notepad"},
                )
            )
            plan.append(
                ActionStep(
                    "hotkey",
                    "Naciśnij Enter",
                    {"keys": "enter"},
                )
            )
            plan.append(ActionStep("wait", "Czekaj na notatnik", {"duration": 2.0}))

            # Wyciągnij tekst do wpisania
            if "napisz" in task.lower():
                # Prosta ekstrakcja tekstu z cudzysłowów lub po słowie "napisz"
                text_to_write = "Hello Venom"  # domyślny
                if "'" in task or '"' in task:
                    # Spróbuj wyciągnąć tekst z cudzysłowów
                    import re

                    match = re.search(r"['\"](.+?)['\"]", task)
                    if match:
                        text_to_write = match.group(1)

                plan.append(
                    ActionStep(
                        "type",
                        f"Wpisz tekst: {text_to_write}",
                        {"text": text_to_write},
                    )
                )

        # Przykład 2: "Włącz następną piosenkę w Spotify"
        elif "spotify" in task.lower() and "następn" in task.lower():
            plan.append(ActionStep("screenshot", "Zrób screenshot ekranu", {}))
            plan.append(
                ActionStep(
                    "locate",
                    "Znajdź przycisk Next w Spotify",
                    {"description": "next button spotify"},
                )
            )
            plan.append(
                ActionStep(
                    "click",
                    "Kliknij przycisk Next",
                    {"use_located": True},
                )
            )

        else:
            # Ogólny plan - zrób screenshot i spróbuj znaleźć opisany element
            plan.append(ActionStep("screenshot", "Zrób screenshot ekranu", {}))
            logger.warning(
                f"Nie rozpoznano konkretnego zadania: {task}. Używam ogólnego planu."
            )

        logger.info(f"Plan utworzony: {len(plan)} kroków")
        return plan

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
