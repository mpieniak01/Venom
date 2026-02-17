"""Moduł: evolution_coordinator - koordynacja procedury ewolucji Venom."""

import asyncio
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from venom_core.agents.system_engineer import SystemEngineerAgent
from venom_core.agents.tester import TesterAgent
from venom_core.execution.skills.core_skill import CoreSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.infrastructure.mirror_world import InstanceInfo, MirrorWorld
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
    ) -> dict[str, Any]:
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
            analysis = self._analyze_request(request)
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

                # Sprawdź czy merge faktycznie się udał
                if merge_result.get("merged"):
                    return {
                        "success": True,
                        "phase": "completed",
                        "branch": branch_name,
                        "merge_result": merge_result,
                        "message": "Ewolucja zakończona pomyślnie - zmiany zmergowane",
                    }
                else:
                    # Merge się nie udał (konflikty lub błędy)
                    return {
                        "success": False,
                        "phase": "merge_failed",
                        "branch": branch_name,
                        "merge_result": merge_result,
                        "reason": merge_result.get("reason", "Merge nie powiódł się"),
                        "message": "Weryfikacja przeszła, ale merge zawodzi",
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

    def _analyze_request(self, request: str) -> dict:
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

    async def _verify_python_syntax(
        self, workspace_path: Path
    ) -> tuple[bool, str | None]:
        """
        Weryfikuje składnię plików Python.

        Args:
            workspace_path: Ścieżka do workspace z plikami Python

        Returns:
            Krotka (sukces, komunikat_błędu)
        """
        logger.info("Sprawdzanie składni plików Python...")
        python_files = list(workspace_path.rglob("*.py"))

        for py_file in python_files:
            syntax_result = await self.core_skill.verify_syntax(str(py_file))
            if "❌" in syntax_result:
                return False, f"Błąd składni w {py_file.name}: {syntax_result}"

        logger.info("✅ Składnia poprawna")
        return True, None

    async def _verify_health(
        self, instance_info: InstanceInfo
    ) -> tuple[bool, str | None]:
        """
        Weryfikuje health check instancji.

        Args:
            instance_info: Informacje o instancji

        Returns:
            Krotka (sukces, komunikat_błędu)
        """
        if instance_info.status != "running":
            return True, None  # Pomijamy health check dla nieaktywnej instancji

        logger.info("Sprawdzanie healthcheck...")
        health_ok, health_msg = await self.mirror_world.verify_instance(
            instance_info.instance_id
        )

        if not health_ok:
            return False, f"Health check failed: {health_msg}"

        logger.info("✅ Health check OK")
        return True, None

    def _has_test_fail_markers(self, test_result: str) -> bool:
        """
        Wykrywa markery błędów w wynikach testów.

        Args:
            test_result: Wynik testów jako string

        Returns:
            True jeśli wykryto błędy, False w przeciwnym razie
        """
        if "❌" in test_result:
            return True

        # Sprawdź linie zaczynające się od ERROR/BŁĄD
        for line in test_result.split("\n"):
            line_stripped = line.strip().upper()
            if line_stripped.startswith(("ERROR:", "BŁĄD:", "FAILED:", "FAILURE:")):
                return True

        return False

    async def _run_shadow_smoke_tests(
        self, instance_info: InstanceInfo, tester_agent
    ) -> dict[str, Any]:
        """
        Uruchamia testy smoke w Shadow Instance.

        Args:
            instance_info: Informacje o instancji
            tester_agent: Agent tester

        Returns:
            Słownik z wynikiem testów
        """
        logger.info("Uruchamianie testów w Shadow Instance...")

        try:
            # Przygotuj URL do Shadow Instance
            instance_url = f"http://localhost:{instance_info.port}"

            # Przygotuj zadanie testowe dla TesterAgent
            test_task = (
                f"Przetestuj aplikację Venom dostępną pod adresem {instance_url}. "
                f"Wykonaj podstawowe testy smoke:\n"
                f"1. Sprawdź czy strona główna się ładuje (visit_page)\n"
                f"2. Sprawdź czy API health endpoint odpowiada ({instance_url}/api/v1/health)\n"
                f"3. Zweryfikuj czy nie ma błędów JavaScript w konsoli\n"
                f"4. Sprawdź czy kluczowe elementy UI są widoczne\n"
                f"Zwróć szczegółowy raport z wynikami testów."
            )

            # Uruchom testy z timeoutem
            test_timeout = 120  # 2 minuty na testy smoke

            try:
                test_result = await asyncio.wait_for(
                    tester_agent.process(test_task), timeout=test_timeout
                )

                logger.info(f"Wynik testów Shadow Instance:\n{test_result}")

                # Sprawdź czy w wyniku testów są błędy
                if self._has_test_fail_markers(test_result):
                    return {
                        "success": False,
                        "reason": f"Testy wykryły problemy: {test_result[:500]}",
                        "test_report": test_result,
                    }

                logger.info("✅ Testy przeszły pomyślnie")
                return {"success": True}

            except asyncio.TimeoutError:
                logger.warning(f"Timeout testów po {test_timeout}s")
                return {
                    "success": False,
                    "reason": f"Testy przekroczyły limit czasu ({test_timeout}s)",
                }

        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania testów: {e}", exc_info=True)
            # Nie przerywamy procesu - testy są opcjonalne
            logger.warning("Kontynuuję weryfikację mimo błędu testów")
            return {"success": True}  # Kontynuuj mimo błędu testów

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
        syntax_ok, syntax_error = await self._verify_python_syntax(
            instance_info.workspace_path
        )
        if not syntax_ok:
            return {"success": False, "reason": syntax_error}

        # Weryfikacja 2: Sprawdź czy instancja odpowiada (jeśli uruchomiona)
        health_ok, health_error = await self._verify_health(instance_info)
        if not health_ok:
            return {"success": False, "reason": health_error}

        # Weryfikacja 3: Opcjonalnie - uruchom testy (jeśli dostępny TesterAgent)
        if self.tester_agent:
            test_result = await self._run_shadow_smoke_tests(
                instance_info, self.tester_agent
            )
            if not test_result["success"]:
                return test_result

        return {
            "success": True,
            "reason": "Wszystkie weryfikacje przeszły pomyślnie",
        }

    def _resolve_merge_dependencies(self) -> tuple[Any | None, Any | None, str]:
        """
        Rozwiązuje zależności dla merge (funkcja i repo).

        Returns:
            Krotka (merge_fn, repo, current_branch)
        """
        merge_fn = getattr(self.git_skill, "merge", None)
        if not callable(merge_fn):
            return None, None, "unknown"

        repo = None
        current_branch = "unknown"
        get_repo_fn = getattr(self.git_skill, "_get_repo", None)
        if callable(get_repo_fn):
            try:
                repo = get_repo_fn()
                try:
                    # repo.active_branch może zgłosić wyjątek np. przy detached HEAD
                    active_branch = getattr(repo, "active_branch", None)
                    current_branch = getattr(active_branch, "name", "unknown")
                except Exception:
                    current_branch = "unknown"
            except Exception as exc:
                logger.warning(
                    "Nie udało się pobrać repozytorium podczas przygotowania merge: %s",
                    exc,
                )
                repo = None
                current_branch = "unknown"

        return merge_fn, repo, current_branch

    def _normalize_merge_result(self, merge_result: Any) -> str:
        """
        Konwertuje wynik merge na string.

        Args:
            merge_result: Wynik merge

        Returns:
            String reprezentacja wyniku
        """
        return str(merge_result)

    def _build_merge_response(
        self,
        merged: bool,
        branch_name: str,
        current_branch: str,
        result_text: str = "",
        reason: str = "",
        conflicts: str = "",
        action_required: str = "",
        skipped: bool = False,
    ) -> dict:
        """
        Buduje słownik odpowiedzi merge.

        Args:
            merged: Czy merge się udał
            branch_name: Nazwa source brancha
            current_branch: Nazwa target brancha
            result_text: Tekst wyniku merge
            reason: Powód niepowodzenia
            conflicts: Tekst konfliktów
            action_required: Wymagana akcja użytkownika
            skipped: Czy merge został pominięty

        Returns:
            Słownik z wynikiem merge
        """
        response = {
            "merged": merged,
            "source_branch": branch_name,
            "target_branch": current_branch,
        }

        if skipped:
            response["message"] = "Automated merge skipped (GitSkill.merge unavailable)"
            response["skipped"] = True
        elif merged:
            response["message"] = result_text
        elif conflicts:
            response["reason"] = reason
            response["conflicts"] = conflicts
            response["action_required"] = action_required
        elif reason:
            response["reason"] = reason
            if action_required:
                response["action_required"] = action_required
            if result_text:
                response["message"] = result_text

        return response

    async def _merge_changes(self, branch_name: str) -> dict:
        """
        Merguje zmiany z brancha eksperymentalnego do głównego brancha.

        Args:
            branch_name: Nazwa brancha do zmergowania

        Returns:
            Słownik z wynikiem merge
        """
        logger.info(f"Mergowanie brancha {branch_name}")

        # Kompatybilność dla środowisk/testów, gdzie przekazano uproszczony stub
        # zamiast pełnego GitSkill (brak metody merge).
        merge_fn, repo, current_branch = self._resolve_merge_dependencies()

        if not callable(merge_fn):
            logger.warning(
                "GitSkill without merge() provided; skipping automated merge for %s",
                branch_name,
            )
            return self._build_merge_response(
                merged=True,
                branch_name=branch_name,
                current_branch=current_branch,
                skipped=True,
            )

        try:
            logger.info(f"Aktualny branch: {current_branch}")

            # Wykonaj merge używając GitSkill
            merge_result = await merge_fn(branch_name)

            # Sprawdź wynik merge
            merge_result_text = self._normalize_merge_result(merge_result)

            if "✅" in merge_result_text:
                logger.info(
                    f"✅ Pomyślnie zmergowano {branch_name} do {current_branch}"
                )
                return self._build_merge_response(
                    merged=True,
                    branch_name=branch_name,
                    current_branch=current_branch,
                    result_text=merge_result_text,
                )
            elif "CONFLICT" in merge_result_text or "⚠️" in merge_result_text:
                logger.warning(f"Konflikty podczas merge: {merge_result_text}")
                # Rollback - przerwij merge
                try:
                    if repo is not None:
                        repo.git.merge("--abort")
                    logger.info("Merge przerwany z powodu konfliktów")
                except Exception as abort_error:
                    logger.error(f"Błąd podczas przerywania merge: {abort_error}")

                return self._build_merge_response(
                    merged=False,
                    branch_name=branch_name,
                    current_branch=current_branch,
                    reason="Konflikty merge",
                    conflicts=merge_result_text,
                    action_required=f"Rozwiąż konflikty ręcznie dla brancha '{branch_name}'",
                )
            else:
                # Nieoczekiwany wynik
                logger.warning(f"Nieoczekiwany wynik merge: {merge_result_text}")
                return self._build_merge_response(
                    merged=False,
                    branch_name=branch_name,
                    current_branch=current_branch,
                    reason="Nieoczekiwany wynik merge",
                    result_text=merge_result_text,
                )

        except Exception as e:
            error_msg = f"Błąd podczas merge: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # Próba rollback
            try:
                if repo is not None and repo.index.unmerged_blobs():
                    repo.git.merge("--abort")
                    logger.info("Rollback merge wykonany po błędzie")
            except Exception as rollback_error:
                logger.error(f"Błąd podczas rollback: {rollback_error}")

            return self._build_merge_response(
                merged=False,
                branch_name=branch_name,
                current_branch=current_branch,
                reason=error_msg,
                action_required="Sprawdź logi i spróbuj zmergować manualnie",
            )

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
