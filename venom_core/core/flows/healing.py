"""Moduł: healing - Logika pętli samonaprawy (Healing Cycle)."""

from typing import Optional
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.flows.base import BaseFlow, EventBroadcaster
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maksymalna liczba prób naprawy przed końcową weryfikacją
MAX_HEALING_ITERATIONS = 3


class HealingFlow(BaseFlow):
    """Logika pętli samonaprawy - Test-Diagnose-Fix-Apply."""

    def __init__(
        self,
        state_manager: StateManager,
        task_dispatcher: TaskDispatcher,
        event_broadcaster: Optional[EventBroadcaster] = None,
    ):
        """
        Inicjalizacja HealingFlow.

        Args:
            state_manager: Menedżer stanu zadań
            task_dispatcher: Dispatcher zadań (dostęp do agentów)
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        super().__init__(event_broadcaster)
        self.state_manager = state_manager
        self.task_dispatcher = task_dispatcher

    async def execute(self, task_id: UUID, test_path: str = ".") -> dict:
        """
        Pętla samonaprawy (Test-Diagnose-Fix-Apply).

        Algorytm:
        1. CHECK: Uruchom testy
        2. DIAGNOSE: Przeanalizuj błędy (Guardian)
        3. FIX: Wygeneruj poprawkę (Coder)
        4. APPLY: Zapisz poprawkę (FileSkill)
        5. LOOP: Sprawdź wynik po każdej próbie naprawy (max 3 naprawy)

        Args:
            task_id: ID zadania
            test_path: Ścieżka do testów

        Returns:
            Słownik z wynikami:
            - success: bool - czy testy przeszły
            - iterations: int - liczba uruchomień testów
            - exit_code: int | None - kod wyjścia ostatniego uruchomienia
            - final_report: str - ostatni raport z testów
        """
        from venom_core.agents.guardian import GuardianAgent
        from venom_core.execution.skills.test_skill import TestSkill
        from venom_core.infrastructure.docker_habitat import DockerHabitat

        try:
            # Inicjalizuj komponenty
            habitat = DockerHabitat()
            test_skill = TestSkill(habitat=habitat)

            # Pobierz agentów
            guardian = GuardianAgent(
                kernel=self.task_dispatcher.kernel, test_skill=test_skill
            )
            coder = self.task_dispatcher.coder_agent

            self.state_manager.add_log(
                task_id,
                f"🔄 Rozpoczynam pętlę samonaprawy (max {MAX_HEALING_ITERATIONS} prób naprawy)",
            )

            await self._broadcast_event(
                event_type="HEALING_STARTED",
                message="Rozpoczynam automatyczne testy i naprawy",
                data={
                    "task_id": str(task_id),
                    "max_iterations": MAX_HEALING_ITERATIONS,
                },
            )

            # Przygotuj środowisko - zainstaluj zależności
            self.state_manager.add_log(task_id, "📦 Przygotowuję środowisko testowe...")
            habitat.execute(
                "pip install -r requirements.txt 2>&1 || echo 'No requirements.txt'",
                timeout=120,
            )

            max_checks = MAX_HEALING_ITERATIONS + 1
            for iteration in range(1, max_checks + 1):
                self.state_manager.add_log(
                    task_id,
                    f"🔍 Weryfikacja {iteration}/{max_checks} - uruchamiam testy",
                )

                await self._broadcast_event(
                    event_type="TEST_RUNNING",
                    message=f"Weryfikacja {iteration}/{max_checks}: Uruchamiam testy",
                    agent="Guardian",
                    data={"task_id": str(task_id), "iteration": iteration},
                )

                exit_code, test_report = await test_skill.run_pytest_with_evidence(
                    test_path=test_path
                )

                if exit_code == 0:
                    self.state_manager.add_log(
                        task_id,
                        f"✅ Testy przeszły pomyślnie po {iteration} uruchomieniach!",
                    )

                    await self._broadcast_event(
                        event_type="TEST_RESULT",
                        message="✅ Testy przeszły pomyślnie!",
                        agent="Guardian",
                        data={
                            "task_id": str(task_id),
                            "success": True,
                            "iterations": iteration,
                            "exit_code": exit_code,
                        },
                    )

                    return {
                        "success": True,
                        "iterations": iteration,
                        "final_report": test_report,
                        "exit_code": exit_code,
                    }

                if exit_code is None or iteration == max_checks:
                    break

                # Testy nie przeszły - diagnozuj
                self.state_manager.add_log(
                    task_id, "❌ Testy nie przeszły. Rozpoczynam diagnostykę..."
                )

                await self._broadcast_event(
                    event_type="TEST_RESULT",
                    message="❌ Testy nie przeszły - analizuję błędy",
                    agent="Guardian",
                    data={
                        "task_id": str(task_id),
                        "success": False,
                        "iteration": iteration,
                        "exit_code": exit_code,
                    },
                )

                # PHASE 2: DIAGNOSE - Guardian analizuje błędy
                self.state_manager.add_log(
                    task_id,
                    "🔬 PHASE 2: Guardian analizuje błędy (traceback)",
                )

                diagnosis_prompt = f"""Przeanalizuj wyniki testów i stwórz precyzyjny ticket naprawczy.

WYNIKI TESTÓW:
{test_report}

Zidentyfikuj:
1. Który plik wymaga naprawy
2. Jaka jest przyczyna błędu
3. Co dokładnie trzeba poprawić

Odpowiedz w formacie ticketu naprawczego.
"""

                repair_ticket = await guardian.process(diagnosis_prompt)

                self.state_manager.add_log(
                    task_id,
                    f"📋 Ticket naprawczy:\n{repair_ticket[:300]}...",
                )

                await self._broadcast_event(
                    event_type="AGENT_THOUGHT",
                    message="Zdiagnozowałem problem - tworzę ticket naprawczy",
                    agent="Guardian",
                    data={
                        "task_id": str(task_id),
                        "ticket_preview": repair_ticket[:100],
                    },
                )

                # PHASE 3: FIX - Coder generuje poprawkę
                self.state_manager.add_log(
                    task_id,
                    "🛠️ PHASE 3: Coder generuje poprawkę",
                )

                fix_prompt = f"""TICKET NAPRAWCZY OD GUARDIANA:
{repair_ticket}

WYNIKI TESTÓW:
{test_report[:500]}

Twoim zadaniem jest naprawić kod zgodnie z ticketem.
WAŻNE: Użyj funkcji write_file aby zapisać poprawiony kod do pliku.
"""

                await self._broadcast_event(
                    event_type="AGENT_ACTION",
                    message="Coder naprawia kod",
                    agent="Coder",
                    data={"task_id": str(task_id), "iteration": iteration},
                )

                await coder.process(fix_prompt)
                self.state_manager.add_log(
                    task_id,
                    "✏️ Coder zakończył próbę naprawy. Sprawdzam testy.",
                )

            message = (
                "Brak kodu wyjścia pytest. Nie można zweryfikować naprawy."
                if exit_code is None
                else (
                    f"Testy nadal nie przechodzą po {MAX_HEALING_ITERATIONS} "
                    "próbach naprawy. Wymagana interwencja ręczna."
                )
            )
            self.state_manager.add_log(task_id, message)
            await self._broadcast_event(
                event_type="HEALING_FAILED",
                message=message,
                data={
                    "task_id": str(task_id),
                    "iterations": iteration,
                    "exit_code": exit_code,
                    "final_report": test_report[:500],
                },
            )
            return {
                "success": False,
                "iterations": iteration,
                "final_report": test_report,
                "exit_code": exit_code,
                "message": message,
            }

        except Exception as e:
            error_msg = f"❌ Błąd podczas pętli samonaprawy: {str(e)}"
            logger.error(error_msg)
            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="HEALING_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            return {
                "success": False,
                "iterations": 0,
                "exit_code": None,
                "final_report": "",
                "message": error_msg,
            }
