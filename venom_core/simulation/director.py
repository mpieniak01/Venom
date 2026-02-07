"""Moduł: director - reżyser koordynujący symulacje użytkowników."""

import asyncio
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from semantic_kernel import Kernel

from venom_core.agents.simulated_user import SimulatedUserAgent
from venom_core.config import SETTINGS
from venom_core.infrastructure.stack_manager import StackManager
from venom_core.simulation.persona_factory import Persona, PersonaFactory
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
secure_random = secrets.SystemRandom()


class SimulationDirector:
    """Reżyser koordynujący symulacje użytkowników.

    Odpowiada za:
    - Uruchamianie stacków aplikacji
    - Spawning symulowanych użytkowników
    - Koordynację równoległych sesji
    - Elementy Chaos Engineering
    """

    def __init__(
        self,
        kernel: Kernel,
        workspace_root: Optional[str] = None,
        enable_chaos: bool = False,
    ):
        """
        Inicjalizacja SimulationDirector.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            workspace_root: Katalog roboczy
            enable_chaos: Czy włączyć Chaos Engineering
        """
        self.kernel = kernel
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.enable_chaos = enable_chaos

        # Komponenty
        self.stack_manager = StackManager(workspace_root=str(self.workspace_root))
        self.persona_factory = PersonaFactory(kernel=kernel)

        # Tracking aktywnych symulacji
        self.active_simulations: dict[str, SimulatedUserAgent] = {}
        self.simulation_results: list[dict[str, Any]] = []

        logger.info(f"SimulationDirector zainicjalizowany (chaos={enable_chaos})")

    async def run_scenario(
        self,
        stack_name: str,
        target_url: str,
        scenario_desc: str,
        user_count: int = 5,
        personas: Optional[list[Persona]] = None,
        max_steps_per_user: int = 10,
        deploy_stack: bool = False,
        compose_content: Optional[str] = None,
    ) -> dict:
        """
        Uruchamia scenariusz symulacji.

        Args:
            stack_name: Nazwa stacka aplikacji (jeśli deploy_stack=True)
            target_url: URL aplikacji do testowania
            scenario_desc: Opis scenariusza / cel użytkowników
            user_count: Liczba symulowanych użytkowników
            personas: Opcjonalna lista person (None = wygeneruj automatycznie)
            max_steps_per_user: Maksymalna liczba kroków na użytkownika
            deploy_stack: Czy wdrożyć stack przed testem
            compose_content: Zawartość docker-compose.yml (jeśli deploy_stack=True)

        Returns:
            Słownik z wynikami symulacji
        """
        scenario_id = str(uuid.uuid4())[:8]
        logger.info(
            f"🎬 Rozpoczynam scenariusz symulacji: {scenario_desc} "
            f"(ID: {scenario_id}, użytkowników: {user_count})"
        )

        start_time = datetime.now(timezone.utc)

        # Krok 1: Wdróż stack jeśli wymagane
        if deploy_stack:
            if not compose_content:
                logger.error("deploy_stack=True ale brak compose_content")
                return {
                    "error": "Brak zawartości docker-compose.yml",
                    "scenario_id": scenario_id,
                }

            logger.info(f"Wdrażam stack: {stack_name}")
            success, msg = self.stack_manager.deploy_stack(
                compose_content=compose_content,
                stack_name=stack_name,
            )

            if not success:
                logger.error(f"Nie udało się wdrożyć stacka: {msg}")
                return {
                    "error": f"Błąd wdrażania stacka: {msg}",
                    "scenario_id": scenario_id,
                }

            logger.info("Stack wdrożony, czekam 5s na inicjalizację...")
            await asyncio.sleep(5)

        # Krok 2: Przygotuj persony
        if not personas:
            logger.info(f"Generuję {user_count} zróżnicowanych person")
            personas = self.persona_factory.generate_diverse_personas(
                goal=scenario_desc,
                count=user_count,
                use_llm=False,  # Dla MVP bez LLM
            )

        # Krok 3: Spawn użytkowników równolegle
        logger.info(f"Spawning {len(personas)} symulowanych użytkowników...")

        # Stwórz zadania dla każdego użytkownika
        tasks = []
        for i, persona in enumerate(personas):
            session_id = f"{scenario_id}_{i}"
            task = self._run_user_session(
                persona=persona,
                target_url=target_url,
                session_id=session_id,
                max_steps=max_steps_per_user,
            )
            tasks.append(task)

        # Krok 4: Opcjonalnie wprowadź chaos
        if self.enable_chaos and deploy_stack:
            chaos_task = self._run_chaos_monkey(
                stack_name=stack_name,
                duration_seconds=max_steps_per_user * 5,  # Szacunkowy czas
            )
            tasks.append(chaos_task)

        # Uruchom wszystkie sesje równolegle
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Krok 5: Zbierz wyniki (pomiń wynik chaos_monkey jeśli był)
        if self.enable_chaos and deploy_stack:
            user_results = results[:-1]  # Usuń ostatni (chaos monkey)
        else:
            user_results = results

        # Filtruj błędy
        successful_results = [
            r for r in user_results if isinstance(r, dict) and "error" not in r
        ]
        failed_results = [
            r for r in user_results if not isinstance(r, dict) or "error" in r
        ]

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Statystyki
        total_users = len(personas)
        successful_users = sum(1 for r in successful_results if r.get("goal_achieved"))
        rage_quits = sum(1 for r in successful_results if r.get("rage_quit"))

        scenario_report = {
            "scenario_id": scenario_id,
            "scenario_desc": scenario_desc,
            "target_url": target_url,
            "stack_name": stack_name if deploy_stack else None,
            "total_users": total_users,
            "successful_users": successful_users,
            "rage_quits": rage_quits,
            "failed_sessions": len(failed_results),
            "success_rate": (
                round(successful_users / total_users * 100, 1) if total_users > 0 else 0
            ),
            "duration_seconds": round(duration, 2),
            "chaos_enabled": self.enable_chaos,
            "user_results": successful_results,
            "errors": failed_results if failed_results else None,
        }

        logger.info(
            f"✅ Scenariusz zakończony: {successful_users}/{total_users} sukces "
            f"({scenario_report['success_rate']}%), {rage_quits} rage quits"
        )

        self.simulation_results.append(scenario_report)
        return scenario_report

    async def _run_user_session(
        self,
        persona: Persona,
        target_url: str,
        session_id: str,
        max_steps: int,
    ) -> dict:
        """
        Uruchamia sesję pojedynczego użytkownika.

        Args:
            persona: Persona użytkownika
            target_url: URL aplikacji
            session_id: ID sesji
            max_steps: Maksymalna liczba kroków

        Returns:
            Raport z sesji
        """
        try:
            logger.info(f"[{persona.name}] Rozpoczynam sesję {session_id}")

            # Stwórz agenta symulowanego użytkownika
            user_agent = SimulatedUserAgent(
                kernel=self.kernel,
                persona=persona,
                target_url=target_url,
                session_id=session_id,
                workspace_root=str(self.workspace_root),
            )

            # Dodaj do trackingu
            self.active_simulations[session_id] = user_agent

            # Uruchom pętlę behawioralną
            report = await user_agent.run_behavioral_loop(max_steps=max_steps)

            # Usuń z trackingu
            del self.active_simulations[session_id]

            logger.info(f"[{persona.name}] Sesja zakończona: {session_id}")
            return report

        except Exception as e:
            logger.error(f"Błąd podczas sesji {session_id}: {e}")
            return {
                "session_id": session_id,
                "persona_name": persona.name,
                "error": str(e),
            }

    async def _run_chaos_monkey(self, stack_name: str, duration_seconds: int):
        """
        Chaos Engineering - losowo wprowadza problemy w stacku.

        Args:
            stack_name: Nazwa stacka
            duration_seconds: Czas trwania chaosu
        """
        logger.warning(f"🐵 Chaos Monkey aktywowany na {duration_seconds}s")

        start_time = time.monotonic()
        chaos_events = []

        while (time.monotonic() - start_time) < duration_seconds:
            # Czekaj losowy czas (10-30s)
            await asyncio.sleep(secure_random.randint(10, 30))

            # Losuj akcję chaosu
            chaos_action = secure_random.choice(
                [
                    "restart_service",
                    # "kill_service",  # Zbyt agresywne dla MVP
                    # "network_delay",  # Wymaga dodatkowych narzędzi
                ]
            )

            if chaos_action == "restart_service":
                # Restart losowego serwisu (TODO: wymagałoby parsowania compose)
                logger.warning("🐵 Chaos: Restart serwisu (placeholder)")
                chaos_events.append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "restart_service",
                        "stack": stack_name,
                    }
                )

        logger.info(f"🐵 Chaos Monkey zakończył (wydarzenia: {len(chaos_events)})")
        return {"chaos_events": chaos_events}

    def get_active_simulations(self) -> dict:
        """
        Zwraca informacje o aktywnych symulacjach.

        Returns:
            Słownik z aktywnymi symulacjami
        """
        active = {}
        for session_id, agent in self.active_simulations.items():
            active[session_id] = {
                "persona_name": agent.persona.name,
                "goal": agent.persona.goal,
                "emotional_state": agent.emotional_state.value,
                "frustration_level": agent.frustration_level,
                "actions_taken": agent.actions_taken,
                "rage_quit": agent.rage_quit,
                "goal_achieved": agent.goal_achieved,
            }
        return active

    def get_simulation_results(self) -> list[dict]:
        """
        Zwraca wyniki wszystkich przeprowadzonych symulacji.

        Returns:
            Lista raportów ze scenariuszy
        """
        return self.simulation_results

    async def cleanup(self, stack_name: Optional[str] = None):
        """
        Czyszczenie zasobów po symulacji.

        Args:
            stack_name: Opcjonalna nazwa stacka do usunięcia
        """
        logger.info("Czyszczenie zasobów symulacji")

        # Zamknij aktywne sesje
        for session_id, agent in list(self.active_simulations.items()):
            try:
                await agent.browser_skill.close_browser()
                logger.debug(f"Zamknięto przeglądarkę dla sesji: {session_id}")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania przeglądarki {session_id}: {e}")

        self.active_simulations.clear()

        # Opcjonalnie usuń stack
        if stack_name:
            logger.info(f"Usuwam stack: {stack_name}")
            success, msg = self.stack_manager.destroy_stack(
                stack_name=stack_name,
                remove_volumes=True,
                cleanup_directory=False,
            )
            if success:
                logger.info("Stack usunięty")
            else:
                logger.warning(f"Problem z usuwaniem stacka: {msg}")

        logger.info("Czyszczenie zakończone")
