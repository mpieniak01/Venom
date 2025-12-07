"""Moduł: evolution_coordinator - koordynacja procedury ewolucji Venom."""

import asyncio
from pathlib import Path
from typing import Optional
from uuid import UUID

from venom_core.agents.system_engineer import SystemEngineerAgent
from venom_core.agents.tester import TesterAgent
from venom_core.execution.skills.core_skill import CoreSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.infrastructure.mirror_world import MirrorWorld, InstanceInfo
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class EvolutionCoordinator:
    """
    Koordynator procedury ewolucji - zarządza procesem bezpiecznej modyfikacji kodu źródłowego.

    Proces ewolucji:
    1. SystemEngineer tworzy branch eksperymentalny i wprowadza zmiany
    2. MirrorWorld uruchamia Shadow Instance z nowymi zmianami
    3. TesterAgent weryfikuje czy Shadow Instance działa poprawnie
    4. Jeśli testy przechodzą - zmiany są aplikowane (merge)
    5. Jeśli testy nie przechodzą - zmiany są odrzucane (rollback)
    """

    def __init__(
        self,
        system_engineer: SystemEngineerAgent,
        mirror_world: MirrorWorld,
        core_skill: CoreSkill,
        git_skill: GitSkill,
        tester_agent: Optional[TesterAgent] = None,
        graph_store: Optional[CodeGraphStore] = None,
    ):
        """
        Inicjalizacja EvolutionCoordinator.

        Args:
            system_engineer: Agent inżynier systemowy
            mirror_world: Zarządca instancji lustrzanych
            core_skill: Skill operacji chirurgicznych
            git_skill: Skill operacji Git
            tester_agent: Opcjonalny agent tester (do weryfikacji)
            graph_store: Opcjonalny graf kodu
        """
        self.system_engineer = system_engineer
        self.mirror_world = mirror_world
        self.core_skill = core_skill
        self.git_skill = git_skill
        self.tester_agent = tester_agent
        self.graph_store = graph_store

        logger.info("EvolutionCoordinator zainicjalizowany")

    async def evolve(
        self, task_id: UUID, request: str, project_root: Path
    ) -> dict[str, any]:
        """
        Wykonuje pełną procedurę ewolucji.

        Args:
            task_id: ID zadania (dla logowania)
            request: Opis żądanej zmiany
            project_root: Katalog główny projektu Venom

        Returns:
            Słownik z wynikiem ewolucji
        """
        logger.info(f"Rozpoczynam procedurę ewolucji dla zadania {task_id}")
        logger.info(f"Żądanie: {request[:100]}...")

        try:
            # Faza 1: Analiza i planowanie
            logger.info("=== FAZA 1: ANALIZA ===")
            analysis = await self._analyze_request(request)
            if not analysis["feasible"]:
                return {
                    "success": False,
                    "phase": "analysis",
                    "reason": analysis["reason"],
                }

            # Faza 2: Tworzenie brancha i wprowadzenie zmian
            logger.info("=== FAZA 2: MODYFIKACJA KODU ===")
            branch_name = analysis.get("branch_name", "evolution/auto-generated")
            modification_result = await self.system_engineer.process(
                f"Utwórz branch '{branch_name}' i wprowadź następujące zmiany:\n{request}"
            )

            if "❌" in modification_result:
                return {
                    "success": False,
                    "phase": "modification",
                    "reason": modification_result,
                }

            # Faza 3: Tworzenie instancji lustrzanej
            logger.info("=== FAZA 3: MIRROR WORLD ===")
            instance_info = self._create_shadow_instance(branch_name, project_root)

            # Faza 4: Weryfikacja w Mirror World
            logger.info("=== FAZA 4: WERYFIKACJA ===")
            verification_result = await self._verify_shadow_instance(instance_info)

            # Faza 5: Decyzja - Merge lub Rollback
            logger.info("=== FAZA 5: DECYZJA ===")
            if verification_result["success"]:
                logger.info("✅ Weryfikacja pomyślna - mergowanie zmian")
                merge_result = await self._merge_changes(branch_name)

                # Cleanup
                await self.mirror_world.destroy_instance(
                    instance_info.instance_id, cleanup=True
                )

                return {
                    "success": True,
                    "phase": "completed",
                    "branch": branch_name,
                    "merge_result": merge_result,
                    "message": "Ewolucja zakończona pomyślnie",
                }
            else:
                logger.warning(
                    f"❌ Weryfikacja niepomyślna: {verification_result['reason']}"
                )
                # Rollback - nie merguj zmian
                await self.mirror_world.destroy_instance(
                    instance_info.instance_id, cleanup=True
                )

                return {
                    "success": False,
                    "phase": "verification_failed",
                    "branch": branch_name,
                    "reason": verification_result["reason"],
                    "message": "Zmiany nie zostały zastosowane - weryfikacja niepomyślna",
                }

        except Exception as e:
            logger.error(f"Błąd podczas procedury ewolucji: {e}", exc_info=True)
            return {
                "success": False,
                "phase": "error",
                "reason": str(e),
            }

    async def _analyze_request(self, request: str) -> dict:
        """
        Analizuje żądanie i sprawdza czy jest możliwe do wykonania.

        Args:
            request: Opis żądanej zmiany

        Returns:
            Słownik z wynikiem analizy
        """
        # Proste sprawdzenie - w przyszłości można użyć LLM
        keywords = ["dodaj", "zmień", "usuń", "zmodyfikuj", "uaktualnij", "popraw"]
        is_modification_request = any(kw in request.lower() for kw in keywords)

        if not is_modification_request:
            return {
                "feasible": False,
                "reason": "Żądanie nie wygląda na prośbę o modyfikację kodu",
            }

        # Wygeneruj nazwę brancha
        words = request.split()[:3]
        branch_name = f"evolution/{'-'.join(w.lower() for w in words if w.isalnum())}"

        return {
            "feasible": True,
            "branch_name": branch_name,
            "estimated_risk": "medium",
        }

    def _create_shadow_instance(
        self, branch_name: str, project_root: Path
    ) -> InstanceInfo:
        """
        Tworzy instancję lustrzaną dla testowania.

        Args:
            branch_name: Nazwa brancha do przetestowania
            project_root: Katalog główny projektu

        Returns:
            Informacje o instancji
        """
        logger.info(f"Tworzenie instancji lustrzanej dla brancha: {branch_name}")

        instance_info = self.mirror_world.spawn_shadow_instance(
            branch_name=branch_name,
            project_root=project_root,
        )

        logger.info(
            f"Instancja lustrzana {instance_info.instance_id} utworzona na porcie {instance_info.port}"
        )
        return instance_info

    async def _verify_shadow_instance(self, instance_info: InstanceInfo) -> dict:
        """
        Weryfikuje czy instancja lustrzana działa poprawnie.

        Args:
            instance_info: Informacje o instancji

        Returns:
            Słownik z wynikiem weryfikacji
        """
        logger.info(f"Weryfikacja instancji {instance_info.instance_id}")

        # Weryfikacja 1: Sprawdź składnię plików Python
        logger.info("Sprawdzanie składni plików Python...")
        python_files = list(instance_info.workspace_path.rglob("*.py"))[:10]  # Próbka

        for py_file in python_files:
            syntax_result = await self.core_skill.verify_syntax(str(py_file))
            if "❌" in syntax_result:
                return {
                    "success": False,
                    "reason": f"Błąd składni w {py_file.name}: {syntax_result}",
                }

        logger.info("✅ Składnia poprawna")

        # Weryfikacja 2: Sprawdź czy instancja odpowiada (jeśli uruchomiona)
        if instance_info.status == "running":
            logger.info("Sprawdzanie healthcheck...")
            health_ok, health_msg = await self.mirror_world.verify_instance(
                instance_info.instance_id
            )

            if not health_ok:
                return {
                    "success": False,
                    "reason": f"Health check failed: {health_msg}",
                }

            logger.info("✅ Health check OK")

        # Weryfikacja 3: Opcjonalnie - uruchom testy (jeśli dostępny TesterAgent)
        if self.tester_agent:
            logger.info("Uruchamianie testów...")
            # TODO: Implementacja uruchamiania testów w Shadow Instance
            # Na razie placeholder
            logger.info("⚠️ Uruchamianie testów nie jest jeszcze w pełni zaimplementowane")

        return {
            "success": True,
            "reason": "Wszystkie weryfikacje przeszły pomyślnie",
        }

    async def _merge_changes(self, branch_name: str) -> dict:
        """
        Merguje zmiany z brancha eksperymentalnego do głównego brancha.

        Args:
            branch_name: Nazwa brancha do zmergowania

        Returns:
            Słownik z wynikiem merge
        """
        logger.info(f"Mergowanie brancha {branch_name}")

        try:
            # TODO: Implementacja merge (wymaga dodatkowych metod w GitSkill)
            # Na razie placeholder - zakładamy że zmiana jest już w branchu
            # i użytkownik może zmergować manualnie lub przez GitHub PR

            logger.info(
                f"⚠️ Automatyczny merge nie jest jeszcze zaimplementowany. "
                f"Proszę zmergować branch '{branch_name}' manualnie."
            )

            return {
                "merged": False,
                "reason": "Automatyczny merge nie jest zaimplementowany",
                "action_required": f"Zmerguj branch '{branch_name}' manualnie",
            }

        except Exception as e:
            logger.error(f"Błąd podczas merge: {e}")
            return {
                "merged": False,
                "reason": str(e),
            }

    async def trigger_restart(self, confirm: bool = False) -> str:
        """
        Wyzwala restart procesu Venom po pomyślnej ewolucji.

        UWAGA: To jest destrukcyjna operacja!

        Args:
            confirm: Potwierdzenie restartu

        Returns:
            Komunikat o wyniku
        """
        if not confirm:
            return "❌ Restart wymaga potwierdzenia"

        logger.warning("🔄 Restartowanie Venom po ewolucji...")
        return await self.core_skill.restart_service(confirm=True)
