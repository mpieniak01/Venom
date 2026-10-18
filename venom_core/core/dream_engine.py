"""Moduł: dream_engine - Silnik Aktywnego Śnienia (Synthetic Experience Replay)."""

import asyncio
import json
import secrets
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.agents.coder import CoderAgent
from venom_core.agents.guardian import GuardianAgent
from venom_core.config import SETTINGS
from venom_core.core.chronos import ChronosEngine
from venom_core.core.energy_manager import EnergyManager
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.lessons_store import LessonsStore
from venom_core.simulation.scenario_weaver import ScenarioSpec, ScenarioWeaver
from venom_core.utils.logger import get_logger
from venom_core.utils.markdown_blocks import extract_fenced_block

logger = get_logger(__name__)
secure_random = secrets.SystemRandom()

# Stałe konfiguracyjne
MAX_CODE_PREVIEW_LENGTH = 500  # Maksymalna długość podglądu kodu w zapisach


def _write_dream_artifacts(
    dream_file: Path,
    meta_file: Path,
    scenario: ScenarioSpec,
    code: str,
    metadata: dict[str, Any],
) -> None:
    """Zapisuje artefakty snu do plików na dysku."""
    with open(dream_file, "w", encoding="utf-8") as f:
        f.write(f"# Dream: {scenario.title}\n")
        f.write(f"# Description: {scenario.description}\n")
        f.write(f"# Libraries: {', '.join(scenario.libraries)}\n")
        f.write(f"# Difficulty: {scenario.difficulty}\n\n")
        f.write(code)

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


class DreamState:
    """Stan sesji śnienia."""

    IDLE = "idle"
    DREAMING = "dreaming"
    VALIDATING = "validating"
    SAVING = "saving"
    INTERRUPTED = "interrupted"


class DreamEngine:
    """
    Silnik Snów - mózg operacji "aktywnego śnienia".

    Workflow:
    1. Wykrywa bezczynność (Idle) lub nocne godziny
    2. Pobiera "Klastr Wiedzy" z GraphRAG (dokumentacja)
    3. Zleca ScenarioWeaver wygenerowanie zadania
    4. Uruchamia Coder w trybie "Silent" (izolowany Docker)
    5. Waliduje przez Guardian (ultra-surowy)
    6. Zapisuje jako syntetyczny przykład treningowy

    Może być przerwany w każdej chwili przez EnergyManager.
    """

    def __init__(
        self,
        kernel: Kernel,
        graph_rag: GraphRAGService,
        lessons_store: LessonsStore,
        energy_manager: EnergyManager,
        scenario_weaver: Optional[ScenarioWeaver] = None,
        coder_agent: Optional[CoderAgent] = None,
        guardian_agent: Optional[GuardianAgent] = None,
        chronos_engine: Optional[ChronosEngine] = None,
    ):
        """
        Inicjalizacja DreamEngine.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            graph_rag: Serwis GraphRAG do pobierania wiedzy
            lessons_store: Magazyn lekcji do zapisywania syntetycznych doświadczeń
            energy_manager: Zarządca energii do monitorowania zasobów
            scenario_weaver: Tkacz scenariuszy (opcjonalny, utworzy nowy)
            coder_agent: Agent programujący (opcjonalny, utworzy nowy)
            guardian_agent: Agent walidujący (opcjonalny, utworzy nowy)
            chronos_engine: Silnik zarządzania czasem (opcjonalny, utworzy nowy)
        """
        self.kernel = kernel
        self.graph_rag = graph_rag
        self.lessons_store = lessons_store
        self.energy_manager = energy_manager

        # Komponenty
        self.scenario_weaver = scenario_weaver or ScenarioWeaver(kernel)
        self.coder_agent = coder_agent or CoderAgent(kernel)
        self.guardian_agent = guardian_agent or GuardianAgent(kernel)
        self.chronos = chronos_engine or ChronosEngine()

        # Stan
        self.state = DreamState.IDLE
        self.current_session_id: Optional[str] = None
        self.current_checkpoint_id: Optional[str] = None  # Checkpoint dla sesji śnienia
        self.dreams_count = 0
        self.successful_dreams = 0
        self._state_lock = asyncio.Lock()  # Lock dla ochrony przed race conditions

        # Katalog wyjściowy
        self.output_dir = Path(SETTINGS.DREAMING_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Rejestruj callback w EnergyManager
        self.energy_manager.register_alert_callback(self._handle_wake_up)

        logger.info(
            f"DreamEngine zainicjalizowany (output_dir={self.output_dir}, "
            f"max_scenarios={SETTINGS.DREAMING_MAX_SCENARIOS})"
        )

    async def enter_rem_phase(
        self, max_scenarios: Optional[int] = None, difficulty: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Rozpoczyna fazę REM (Rapid Eye Movement) - intensywne śnienie.

        Args:
            max_scenarios: Maksymalna liczba scenariuszy (domyślnie z SETTINGS)
            difficulty: Poziom trudności scenariuszy (opcjonalny)

        Returns:
            Raport z sesji śnienia
        """
        if not await self._start_rem_session():
            return {"error": "Dream engine not idle", "state": self.state}

        session_start = datetime.now()
        short_session_id = (self.current_session_id or "unknown")[:8]
        logger.info(f"🌙 Rozpoczynam fazę REM (session_id={short_session_id})")
        timeline_name = self._create_dream_timeline(short_session_id)
        max_scenarios, difficulty = self._resolve_dream_parameters(
            max_scenarios, difficulty
        )
        self.energy_manager.set_low_priority()

        try:
            return await self._run_rem_cycle(
                timeline_name, session_start, max_scenarios, difficulty
            )
        finally:
            self.state = DreamState.IDLE
            self.current_checkpoint_id = None
            self.current_session_id = None

    async def _start_rem_session(self) -> bool:
        async with self._state_lock:
            if self.state != DreamState.IDLE:
                logger.warning(
                    f"Nie można rozpocząć śnienia - aktualny stan: {self.state}"
                )
                return False
            self.current_session_id = str(uuid.uuid4())
            self.state = DreamState.DREAMING
            return True

    def _create_dream_timeline(self, short_session_id: str) -> str:
        timeline_name = f"dream_{short_session_id}"
        timeline_created = False
        try:
            self.chronos.create_timeline(timeline_name)
            timeline_created = True
            self.current_checkpoint_id = self.chronos.create_checkpoint(
                name=f"dream_start_{short_session_id}",
                description="Punkt startowy sesji śnienia - na wypadek błędów",
                timeline=timeline_name,
            )
            logger.info(
                f"🛡️ Checkpoint bezpieczeństwa utworzony: {self.current_checkpoint_id} (timeline: {timeline_name})"
            )
        except Exception as e:
            logger.warning(f"Nie udało się utworzyć checkpointu dla śnienia: {e}")
            self.current_checkpoint_id = None
            if timeline_created:
                self._cleanup_partial_timeline(timeline_name)
        return timeline_name

    def _cleanup_partial_timeline(self, timeline_name: str) -> None:
        try:
            timeline_path = self.chronos.timelines_dir / timeline_name
            if timeline_path.exists() and not list(timeline_path.iterdir()):
                timeline_path.rmdir()
                logger.debug(f"Usunięto pustą timeline: {timeline_name}")
        except Exception as cleanup_error:
            logger.debug(f"Nie udało się wyczyścić timeline: {cleanup_error}")

    def _resolve_dream_parameters(
        self, max_scenarios: Optional[int], difficulty: Optional[str]
    ) -> tuple[int, str]:
        resolved_max = max_scenarios or SETTINGS.DREAMING_MAX_SCENARIOS
        resolved_difficulty = difficulty or SETTINGS.DREAMING_SCENARIO_COMPLEXITY
        return resolved_max, resolved_difficulty

    async def _run_rem_cycle(
        self,
        timeline_name: str,
        session_start: datetime,
        max_scenarios: int,
        difficulty: str,
    ) -> Dict[str, Any]:
        try:
            knowledge_fragments = await self._get_knowledge_clusters(max_scenarios)
            if not knowledge_fragments:
                logger.warning(
                    "Brak klastrów wiedzy w GraphRAG - nie można śnić bez wiedzy"
                )
                self._cleanup_empty_timeline(timeline_name, self.current_checkpoint_id)
                return {
                    "session_id": self.current_session_id,
                    "status": "no_knowledge",
                    "dreams_attempted": 0,
                    "dreams_successful": 0,
                }

            logger.info(
                f"Pobrano {len(knowledge_fragments)} klastrów wiedzy z GraphRAG"
            )
            scenarios = await self.scenario_weaver.weave_multiple_scenarios(
                knowledge_fragments, count=max_scenarios, difficulty=difficulty
            )
            logger.info(f"Wygenerowano {len(scenarios)} scenariuszy do realizacji")
            results = await self._run_scenarios(scenarios)
            report = self._build_rem_report(results, session_start)
            self._attach_checkpoint_context(report, timeline_name)
            return report
        except Exception as e:
            logger.error(f"Błąd krytyczny w enter_rem_phase: {e}")
            self._cleanup_empty_timeline(timeline_name, self.current_checkpoint_id)
            return {
                "session_id": self.current_session_id,
                "status": "error",
                "error": str(e),
            }

    async def _run_scenarios(
        self, scenarios: List[ScenarioSpec]
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i, scenario in enumerate(scenarios, 1):
            if self.state == DreamState.INTERRUPTED:
                logger.warning("Śnienie przerwane przez użytkownika")
                break
            logger.info(f"💭 Sen {i}/{len(scenarios)}: {scenario.title}")
            try:
                result = await self._dream_scenario(scenario)
                results.append(result)
                if result.get("success"):
                    self.successful_dreams += 1
                self.dreams_count += 1
            except Exception as e:
                logger.error(f"Błąd podczas śnienia scenariusza {i}: {e}")
                results.append(
                    {"success": False, "error": str(e), "scenario": scenario.title}
                )
        return results

    def _build_rem_report(
        self, results: List[Dict[str, Any]], session_start: datetime
    ) -> Dict[str, Any]:
        session_end = datetime.now()
        duration = (session_end - session_start).total_seconds()
        success_count = sum(1 for r in results if r.get("success"))
        success_rate = success_count / len(results) if results else 0.0
        report = {
            "session_id": self.current_session_id,
            "status": "completed"
            if self.state != DreamState.INTERRUPTED
            else "interrupted",
            "duration_seconds": duration,
            "dreams_attempted": len(results),
            "dreams_successful": success_count,
            "scenarios": [r.get("scenario", "unknown") for r in results],
            "success_rate": success_rate,
        }
        logger.info(
            f"✨ Sesja śnienia zakończona: "
            f"{report['dreams_successful']}/{report['dreams_attempted']} sukcesów"
        )
        return report

    def _attach_checkpoint_context(
        self, report: Dict[str, Any], timeline_name: str
    ) -> None:
        if not self.current_checkpoint_id:
            return
        if report["success_rate"] > 0.5:
            logger.info(
                "✅ Sesja śnienia pomyślna - wiedza zostanie zachowana w głównej linii"
            )
            return
        logger.info("⚠️ Sesja śnienia niepomyślna - rozważ przywrócenie checkpointu")
        report["checkpoint_id"] = self.current_checkpoint_id
        report["timeline"] = timeline_name

    async def _get_knowledge_clusters(self, count: int) -> List[str]:
        """
        Pobiera losowe klastry wiedzy z GraphRAG.

        Args:
            count: Liczba klastrów do pobrania

        Returns:
            Lista fragmentów dokumentacji/wiedzy
        """
        try:
            # Pobierz statystyki grafu
            stats = await asyncio.to_thread(self.graph_rag.get_stats)

            if stats["total_nodes"] == 0:
                logger.warning("Graf wiedzy jest pusty")
                return []

            # Pobierz losowe węzły z grafu (communities/entities)
            # Preferujemy węzły z dużą liczbą połączeń (ważne koncepty)
            graph_store = getattr(self.graph_rag, "graph_store", None)
            graph = graph_store.graph if graph_store else self.graph_rag.graph

            # Sortuj węzły po degree (liczba połączeń)
            nodes_by_degree = sorted(graph.degree(), key=lambda x: x[1], reverse=True)

            # Weź top węzły (najbardziej powiązane) + trochę losowych
            top_nodes = [node for node, degree in nodes_by_degree[: count * 2]]

            # Losuj z top nodes
            selected_nodes = secure_random.sample(top_nodes, min(count, len(top_nodes)))

            # Pobierz dane z węzłów
            fragments = []
            for node in selected_nodes:
                node_data = graph.nodes.get(node, {})

                # Skonstruuj fragment tekstowy z węzła
                fragment = f"Entity: {node}\n"
                fragment += f"Type: {node_data.get('type', 'unknown')}\n"

                # Dodaj opis jeśli jest
                if "description" in node_data:
                    fragment += f"Description: {node_data['description']}\n"

                # Dodaj powiązane węzły (relacje)
                neighbors = list(graph.neighbors(node))
                if neighbors:
                    fragment += f"Related to: {', '.join(neighbors[:5])}\n"

                fragments.append(fragment)

            logger.debug(f"Wydobyto {len(fragments)} fragmentów wiedzy z grafu")
            return fragments

        except Exception as e:
            logger.error(f"Błąd podczas pobierania klastrów wiedzy: {e}")
            return []

    async def _dream_scenario(self, scenario: ScenarioSpec) -> Dict[str, Any]:
        """
        "Śni" pojedynczy scenariusz - próbuje go rozwiązać i zwalidować.

        Args:
            scenario: Specyfikacja scenariusza

        Returns:
            Słownik z wynikiem (success, code, validation, etc.)
        """
        dream_id = str(uuid.uuid4())[:8]
        logger.info(f"💭 [Dream {dream_id}] Rozpoczynam sen: {scenario.title}")

        try:
            # Faza 1: Generowanie kodu (Coder)
            logger.debug(f"[Dream {dream_id}] Faza 1: Generowanie kodu...")

            coder_result = await self.coder_agent.process(scenario.task_prompt)

            # Wyciągnij kod z odpowiedzi (coder zwraca tekst z code blockami)
            code = self._extract_code_from_response(coder_result)

            if not code:
                logger.warning(f"[Dream {dream_id}] Brak kodu w odpowiedzi Codera")
                return {
                    "success": False,
                    "scenario": scenario.title,
                    "error": "No code generated",
                }

            logger.debug(f"[Dream {dream_id}] Wygenerowano {len(code)} znaków kodu")

            # Faza 2: Ultra-surowa walidacja (Guardian)
            if SETTINGS.DREAMING_VALIDATION_STRICT:
                self.state = DreamState.VALIDATING
                logger.debug(f"[Dream {dream_id}] Faza 2: Walidacja Guardian...")

                validation_prompt = (
                    f"Przeanalizuj poniższy kod w trybie ULTRA-SUROWYM.\n\n"
                    f"SCENARIUSZ: {scenario.title}\n"
                    f"ZADANIE: {scenario.description}\n\n"
                    f"TEST CASES (wszystkie muszą być spełnione):\n"
                    f"{chr(10).join(f'- {tc}' for tc in scenario.test_cases)}\n\n"
                    f"KOD:\n"
                    f"```python\n{code}\n```\n\n"
                    f"WYMAGANIA ULTRA-SUROWE:\n"
                    f"- Kod musi się kompilować (brak SyntaxError)\n"
                    f"- Musi spełniać WSZYSTKIE test cases\n"
                    f"- Brak błędów bezpieczeństwa\n"
                    f"- Brak hardcoded credentials/paths\n"
                    f"- Proper error handling\n"
                    f"- Code quality (nie hacki, czytelny)\n\n"
                    f"Odpowiedz w formacie:\n"
                    f"PASS: yes/no\n"
                    f"REASON: <dlaczego pass lub fail>\n"
                )

                validation_result = await self.guardian_agent.process(validation_prompt)

                # Parsuj wynik walidacji
                is_valid = "PASS: yes" in validation_result.upper()

                if not is_valid:
                    logger.warning(
                        f"[Dream {dream_id}] Walidacja FAILED:\n{validation_result}"
                    )
                    return {
                        "success": False,
                        "scenario": scenario.title,
                        "code": code[:200] + "...",
                        "validation": validation_result,
                        "error": "Validation failed",
                    }

                logger.info(f"[Dream {dream_id}] ✅ Walidacja PASSED")

            # Faza 3: Zapis jako syntetyczne doświadczenie
            self.state = DreamState.SAVING
            logger.debug(f"[Dream {dream_id}] Faza 3: Zapisywanie do LessonsStore...")

            # Dodaj do LessonsStore
            code_preview = code[:MAX_CODE_PREVIEW_LENGTH]
            self.lessons_store.add_lesson(
                situation=f"[SYNTHETIC DREAM] {scenario.title}\n{scenario.description}",
                action=f"Wygenerowano kod:\n```python\n{code_preview}...\n```",
                result="✅ Sukces - kod przeszedł walidację Guardian",
                feedback=f"Nauczyłem się: {', '.join(scenario.libraries)}",
                tags=["synthetic", "dream", *scenario.libraries],
                metadata={
                    "dream_id": dream_id,
                    "session_id": self.current_session_id,
                    "difficulty": scenario.difficulty,
                    "test_cases": scenario.test_cases,
                    "synthetic": True,
                },
            )

            # Zapisz też jako plik w synthetic_training/
            dream_file = self.output_dir / f"dream_{dream_id}.py"
            meta_file = self.output_dir / f"dream_{dream_id}.json"

            try:
                await asyncio.to_thread(
                    _write_dream_artifacts,
                    dream_file,
                    meta_file,
                    scenario,
                    code,
                    {
                        "dream_id": dream_id,
                        "session_id": self.current_session_id,
                        "scenario": {
                            "title": scenario.title,
                            "description": scenario.description,
                            "difficulty": scenario.difficulty,
                            "libraries": scenario.libraries,
                            "test_cases": scenario.test_cases,
                        },
                        "code_file": f"dream_{dream_id}.py",
                        "timestamp": datetime.now().isoformat(),
                        "synthetic": True,
                    },
                )

                logger.info(f"[Dream {dream_id}] 💾 Zapisano jako {dream_file.name}")
            except Exception as io_err:
                logger.warning(
                    f"[Dream {dream_id}] ⚠️ Nie udało się zapisać plików snu: {io_err}. "
                    f"Lekcja została dodana do LessonsStore, ale pliki nie zostały zapisane."
                )

            return {
                "success": True,
                "scenario": scenario.title,
                "dream_id": dream_id,
                "code_length": len(code),
                "libraries": scenario.libraries,
            }

        except Exception as e:
            logger.error(f"[Dream {dream_id}] Błąd podczas śnienia: {e}")
            return {
                "success": False,
                "scenario": scenario.title,
                "error": str(e),
            }

    def _extract_code_from_response(self, response: str) -> str:
        """
        Wyciąga kod Python z odpowiedzi LLM (usuwa markdown code blocks).

        Args:
            response: Surowa odpowiedź od LLM

        Returns:
            Czysty kod Python
        """
        # Szukaj bloków kodu ```python ... ```
        python_block = extract_fenced_block(response, language="python")
        if python_block:
            return python_block

        # Szukaj bloków ``` ... ``` (bez języka lub z dowolnym nagłówkiem)
        generic_block = extract_fenced_block(response)
        if generic_block:
            return generic_block

        # Jeśli brak code blocków, zwróć całość (może to być czysty kod)
        return response.strip()

    def _handle_wake_up(self) -> None:
        """Callback wywoływany przez EnergyManager gdy system staje się zajęty."""
        if self.state in [
            DreamState.DREAMING,
            DreamState.VALIDATING,
            DreamState.SAVING,
        ]:
            logger.warning(f"⏰ WAKE UP! Przerywanie śnienia (state={self.state})")
            self.state = DreamState.INTERRUPTED

            # Tu można dodać logikę zatrzymania kontenerów Docker
            # docker stop venom-dream-worker-*

            logger.info("Śnienie przerwane, zasoby zwolnione")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Zwraca statystyki DreamEngine.

        Returns:
            Słownik ze statystykami
        """
        # Policz pliki w output_dir
        dream_files = list(self.output_dir.glob("dream_*.py"))

        return {
            "state": self.state,
            "current_session_id": self.current_session_id,
            "total_dreams": self.dreams_count,
            "successful_dreams": self.successful_dreams,
            "success_rate": (
                self.successful_dreams / self.dreams_count
                if self.dreams_count > 0
                else 0.0
            ),
            "saved_dreams_count": len(dream_files),
            "output_directory": str(self.output_dir),
        }

    def _cleanup_empty_timeline(
        self, timeline_name: str, checkpoint_id: Optional[str] = None
    ) -> None:
        """
        Usuwa pustą lub nieużywaną timeline po nieudanej sesji śnienia.

        Args:
            timeline_name: Nazwa timeline do wyczyszczenia
            checkpoint_id: ID checkpointu do sprawdzenia (opcjonalny)
        """
        try:
            timeline_path = self.chronos.timelines_dir / timeline_name
            if not timeline_path.exists():
                return

            # Sprawdź czy timeline jest pusta lub ma tylko checkpoint startowy
            checkpoints = list(timeline_path.iterdir())

            if len(checkpoints) == 0:
                # Pusta timeline - usuń
                self._remove_timeline_directory(timeline_path, timeline_name, "pustą")
            elif len(checkpoints) == 1 and checkpoint_id:
                # Tylko checkpoint startowy - sprawdź czy to jedyny
                checkpoint_dir = checkpoints[0]
                if checkpoint_dir.name == checkpoint_id:
                    # Usuń checkpoint i timeline
                    shutil.rmtree(checkpoint_dir)
                    self._remove_timeline_directory(
                        timeline_path, timeline_name, "nieużywaną"
                    )
        except Exception as e:
            logger.debug(f"Nie udało się wyczyścić timeline {timeline_name}: {e}")

    def _remove_timeline_directory(
        self, timeline_path: Path, timeline_name: str, description: str
    ) -> None:
        """
        Usuwa katalog timeline i loguje akcję.

        Args:
            timeline_path: Ścieżka do katalogu timeline
            timeline_name: Nazwa timeline
            description: Opis typu timeline (np. "pustą", "nieużywaną")
        """
        try:
            timeline_path.rmdir()
            logger.info(f"🗑️ Usunięto {description} timeline: {timeline_name}")
        except Exception as e:
            logger.debug(f"Nie udało się usunąć timeline {timeline_name}: {e}")
