"""Moduł: tracer - śledzenie przepływu zadań przez system."""

import asyncio
import json
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from venom_core.utils.helpers import get_utc_now
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TraceStatus(str, Enum):
    """Status śledzenia zadania."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    LOST = "LOST"


class TraceStep(BaseModel):
    """Pojedynczy krok w przepływie zadania."""

    component: str = Field(description="Nazwa komponentu (Agent, Skill, Router)")
    action: str = Field(description="Akcja wykonana przez komponent")
    timestamp: datetime = Field(default_factory=get_utc_now)
    status: str = Field(default="ok", description="Status kroku (ok, error)")
    details: Optional[str] = Field(
        default=None, description="Dodatkowe szczegóły (błąd, wynik)"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class RequestTrace(BaseModel):
    """Ślad przepływu pojedynczego zadania."""

    request_id: UUID
    status: TraceStatus = TraceStatus.PENDING
    prompt: str = Field(description="Treść polecenia użytkownika (skrócona)")
    session_id: Optional[str] = Field(
        default=None,
        description="Identyfikator sesji czatu (jeśli dostępny)",
    )
    created_at: datetime = Field(default_factory=get_utc_now)
    finished_at: Optional[datetime] = None
    steps: List[TraceStep] = Field(default_factory=list)
    last_activity: datetime = Field(default_factory=get_utc_now)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_config_hash: Optional[str] = None
    llm_runtime_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None
    forced_intent: Optional[str] = None
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    error_stage: Optional[str] = None
    error_retryable: Optional[bool] = None
    feedback: Optional[dict] = None

    @field_validator("created_at", "finished_at", "last_activity", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class RequestTracer:
    """
    Centralny rejestr śladów zadań z persystencją.

    Przechowuje informacje o przepływie każdego zadania przez system,
    od momentu utworzenia do zakończenia.
    """

    def __init__(
        self,
        watchdog_timeout_minutes: int = 5,
        trace_file_path: Optional[str] = None,
    ):
        """
        Inicjalizacja tracera.

        Args:
            watchdog_timeout_minutes: Czas w minutach po którym zadanie
                                     bez aktywności jest oznaczane jako LOST
            trace_file_path: Ścieżka do pliku z zapisem śladów (opcjonalna)
        """
        self._traces: Dict[UUID, RequestTrace] = {}
        self._traces_lock = Lock()  # Thread safety
        self._watchdog_timeout = timedelta(minutes=watchdog_timeout_minutes)
        self._watchdog_task: Optional[asyncio.Task] = None

        # Konfiguracja persystencji
        self._trace_file_path = Path(trace_file_path) if trace_file_path else None
        if self._trace_file_path:
            self._trace_file_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_traces()

        self._save_task: Optional[asyncio.Task] = None
        self._save_requested: bool = False

    def _load_traces(self) -> None:
        """Ładuje ślady z pliku JSON."""
        if not self._trace_file_path or not self._trace_file_path.exists():
            return

        try:
            content = self._trace_file_path.read_text(encoding="utf-8")
            if not content:
                return

            data = json.loads(content)
            loaded_count = self._load_traces_from_data(data)

            logger.info(f"Załadowano {loaded_count} śladów z {self._trace_file_path}")
            self._load_feedback_for_traces()
        except Exception as e:
            logger.error(f"Błąd podczas ładowania śladów: {e}")

    def _load_traces_from_data(self, data: list[dict[str, Any]]) -> int:
        loaded_count = 0
        with self._traces_lock:
            for trace_dict in data:
                try:
                    trace = RequestTrace.model_validate(trace_dict)
                    self._traces[trace.request_id] = trace
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Pominięto uszkodzony trace podczas ładowania: {e}")
        return loaded_count

    def _load_feedback_for_traces(self) -> None:
        feedback_path = Path("data/feedback/feedback.jsonl")
        if not feedback_path.exists():
            return
        try:
            feedback_map = self._read_feedback_map(feedback_path)
            if not feedback_map:
                return
            updated_count = self._apply_feedback_map(feedback_map)
            logger.info(f"Zaktualizowano feedback dla {updated_count} śladów")
        except Exception as e:
            logger.warning(f"Błąd podczas ładowania feedbacku: {e}")

    def _read_feedback_map(self, feedback_path: Path) -> dict[str, dict[str, Any]]:
        feedback_map: dict[str, dict[str, Any]] = {}
        with open(feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = self._parse_feedback_line(line)
                if entry:
                    feedback_map[entry["task_id"]] = entry["feedback"]
        return feedback_map

    def _parse_feedback_line(self, line: str) -> Optional[dict[str, Any]]:
        try:
            entry = json.loads(line)
            task_id = entry.get("task_id")
            if not task_id:
                return None
            return {
                "task_id": task_id,
                "feedback": {
                    "rating": entry.get("rating"),
                    "comment": entry.get("comment"),
                },
            }
        except Exception:
            return None

    def _apply_feedback_map(self, feedback_map: dict[str, dict[str, Any]]) -> int:
        updated_count = 0
        with self._traces_lock:
            for t_id_str, fb_data in feedback_map.items():
                try:
                    u_id = UUID(t_id_str)
                except Exception:
                    continue
                if u_id in self._traces:
                    self._traces[u_id].feedback = fb_data
                    updated_count += 1
        return updated_count

    async def _save_traces_async(self) -> None:
        """Zapisuje ślady do pliku JSON (asynchronicznie)."""
        if not self._trace_file_path:
            return

        try:
            # Tworzymy snapshot pod lockiem
            with self._traces_lock:
                traces_list = [t.model_dump(mode="json") for t in self._traces.values()]

            # Zapisz do pliku tymczasowego (w executorze aby nie blokować pętli)
            # Używamy run_in_executor dla operacji plikowych
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self._write_file, traces_list, self._trace_file_path
            )

        except Exception as e:
            logger.error(f"Błąd podczas zapisywania śladów: {e}")

    def _write_file(self, data: list, path: Path):
        """Synchroniczny zapis pliku (do uruchomienia w executorze)."""
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.replace(path)

    def _schedule_save(self) -> None:
        """Planuje zapis śladów z mechanizmem debouncingu."""
        self._save_requested = True

        try:
            # Sprawdź czy pętla zapisu już działa
            if self._save_task and not self._save_task.done():
                return

            # Spróbuj uzyskać aktywny event loop
            try:
                asyncio.get_running_loop()
                self._save_task = asyncio.create_task(self._process_save_queue())
            except RuntimeError:
                # Fallback dla braku loopa (np. testy synchroniczne) - wykonaj sync
                # self._save_traces_sync() # Opcjonalnie, ale może blokować
                pass
        except Exception as e:
            logger.error(f"Błąd podczas planowania zapisu trace: {e}")

    async def _process_save_queue(self) -> None:
        """Pętla przetwarzająca żądania zapisu."""
        await asyncio.sleep(1.0)  # Debounce 1s (dłuższy dla tracerów)

        while self._save_requested:
            self._save_requested = False
            await self._save_traces_async()

    async def shutdown(self) -> None:
        """Czeka na zakończenie pętli zapisu."""
        if self._save_task and not self._save_task.done():
            logger.info("Oczekiwanie na zakończenie zapisu śladów...")
            # Wymuś zapis, jeśli był żądany, i wyczyść flagę, aby uniknąć podwójnego zapisu
            if self._save_requested:
                self._save_requested = False
                await self._save_traces_async()

            with suppress(asyncio.CancelledError):
                await self._save_task
            self._save_task = None
            logger.info("Zapisy śladów zakończone")

    def _save_traces(self) -> None:
        """Kompatybilność wsteczna - przekierowuje do schedule."""
        self._schedule_save()

    async def start_watchdog(self):
        """Uruchamia watchdog do monitorowania zagubionych zadań."""
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            await asyncio.sleep(0)
            logger.info("RequestTracer watchdog uruchomiony")

    async def stop_watchdog(self):
        """Zatrzymuje watchdog."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None
            logger.info("RequestTracer watchdog zatrzymany")

    async def _watchdog_loop(self):
        """Pętla watchdog sprawdzająca zagubione zadania."""
        while True:
            try:
                await asyncio.sleep(60)  # Sprawdzaj co minutę
                self._check_lost_requests()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Błąd w watchdog loop: {e}", exc_info=True)

    def _check_lost_requests(self):
        """Sprawdza i oznacza zadania, które przekroczyły timeout."""
        now = get_utc_now()
        updated = False

        # Create a snapshot of traces to avoid holding lock during iteration
        with self._traces_lock:
            traces_snapshot = list(self._traces.items())

        for trace_id, trace in traces_snapshot:
            if trace.status == TraceStatus.PROCESSING:
                time_since_activity = now - trace.last_activity
                if time_since_activity > self._watchdog_timeout:
                    logger.warning(
                        f"Zadanie {trace_id} oznaczone jako LOST (brak aktywności przez {time_since_activity})"
                    )
                    # Re-acquire lock to safely modify trace
                    with self._traces_lock:
                        # Upewnij się, że trace nie został zmodyfikowany przez inny wątek
                        current_trace = self._traces.get(trace_id)
                        if (
                            current_trace
                            and current_trace.status == TraceStatus.PROCESSING
                        ):
                            current_trace.status = TraceStatus.LOST
                            current_trace.finished_at = now
                            current_trace.steps.append(
                                TraceStep(
                                    component="Watchdog",
                                    action="timeout",
                                    status="error",
                                    details=f"Brak aktywności przez {time_since_activity.total_seconds():.0f}s",
                                )
                            )
                            updated = True

        if updated:
            self._save_traces()

    def create_trace(
        self,
        request_id: UUID,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> RequestTrace:
        """
        Tworzy nowy ślad dla zadania.

        Args:
            request_id: UUID zadania
            prompt: Treść polecenia użytkownika
            session_id: ID sesji (opcjonalne)

        Returns:
            Utworzony ślad
        """
        # Skróć prompt do 500 znaków (zwiększono z 200)
        prompt_truncated = prompt[:500] + "..." if len(prompt) > 500 else prompt

        trace = RequestTrace(
            request_id=request_id,
            prompt=prompt_truncated,
            session_id=session_id,
            status=TraceStatus.PENDING,
        )
        with self._traces_lock:
            self._traces[request_id] = trace

        self._save_traces()
        logger.debug(f"Utworzono trace dla zadania {request_id}")
        return trace

    def add_step(
        self,
        request_id: UUID,
        component: str,
        action: str,
        status: str = "ok",
        details: Optional[str] = None,
    ):
        """
        Dodaje krok do śladu zadania.

        Args:
            request_id: UUID zadania
            component: Nazwa komponentu (np. "Orchestrator", "ResearcherAgent")
            action: Akcja (np. "dispatch", "classify_intent", "web_search")
            status: Status kroku ("ok" lub "error")
            details: Opcjonalne dodatkowe informacje
        """
        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba dodania kroku do nieistniejącego trace {request_id}"
                )
                return

            step = TraceStep(
                component=component, action=action, status=status, details=details
            )
            trace.steps.append(step)
            trace.last_activity = get_utc_now()

        # Zapisz asynchronicznie (tutaj uproszczenie do synchronicznego zapisu dla bezpieczeństwa danych)
        # W środowisku produkcyjnym o dużym obciążeniu warto rozważyć kolejkowanie zapisu
        self._save_traces()

        logger.debug(
            f"Dodano krok do trace {request_id}: {component}.{action} ({status})"
        )

    def update_status(self, request_id: UUID, status: TraceStatus):
        """
        Aktualizuje status zadania.

        Args:
            request_id: UUID zadania
            status: Nowy status
        """
        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba aktualizacji statusu nieistniejącego trace {request_id}"
                )
                return

            trace.status = status
            trace.last_activity = get_utc_now()

            # Ustaw finished_at dla stanów końcowych
            if status in (TraceStatus.COMPLETED, TraceStatus.FAILED, TraceStatus.LOST):
                trace.finished_at = get_utc_now()

        self._save_traces()
        logger.debug(f"Zaktualizowano status trace {request_id}: {status}")

    def set_forced_route(
        self,
        request_id: UUID,
        forced_tool: Optional[str],
        forced_provider: Optional[str],
        forced_intent: Optional[str] = None,
    ) -> None:
        """Zapisuje informacje o wymuszonej ścieżce."""
        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba ustawienia forced route dla nieistniejącego trace {request_id}"
                )
                return
            trace.forced_tool = forced_tool
            trace.forced_provider = forced_provider
            if forced_intent:
                trace.forced_intent = forced_intent
            trace.last_activity = get_utc_now()

        self._save_traces()

    def set_llm_metadata(
        self,
        request_id: UUID,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Ustawia informacje o LLM, które obsługuje zadanie."""

        metadata = metadata or {}
        provider = provider or metadata.get("provider")
        model = model or metadata.get("model")
        endpoint = endpoint or metadata.get("endpoint")
        config_hash = metadata.get("config_hash")
        runtime_id = metadata.get("runtime_id")

        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba ustawienia metadanych LLM dla nieistniejącego trace {request_id}"
                )
                return

            trace.llm_provider = provider
            trace.llm_model = model
            trace.llm_endpoint = endpoint
            trace.llm_config_hash = config_hash
            trace.llm_runtime_id = runtime_id

        self._save_traces()
        logger.debug(
            f"Zaktualizowano informacje o LLM dla trace {request_id}: {provider}/{model}"
        )

    def set_error_metadata(self, request_id: UUID, error: dict):
        """Ustawia ustandaryzowane informacje o błędzie dla trace."""
        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba ustawienia błędu dla nieistniejącego trace {request_id}"
                )
                return

            trace.error_code = error.get("error_code")
            trace.error_class = error.get("error_class")
            trace.error_message = error.get("error_message")
            trace.error_details = error.get("error_details")
            trace.error_stage = error.get("stage")
            trace.error_retryable = error.get("retryable")

        self._save_traces()
        logger.debug(
            "Zaktualizowano informacje o błędzie dla trace %s: %s",
            request_id,
            error.get("error_code"),
        )

    def set_feedback(self, request_id: UUID, feedback: dict):
        """Ustawia informacje o feedbacku użytkownika."""
        with self._traces_lock:
            trace = self._traces.get(request_id)
            if trace is None:
                logger.warning(
                    f"Próba ustawienia feedbacku dla nieistniejącego trace {request_id}"
                )
                return
            trace.feedback = feedback
            trace.last_activity = get_utc_now()

        self._save_traces()
        logger.debug(f"Zaktualizowano feedback dla trace {request_id}")

    def get_trace(self, request_id: UUID) -> Optional[RequestTrace]:
        """
        Pobiera ślad zadania.

        Args:
            request_id: UUID zadania

        Returns:
            Ślad zadania lub None jeśli nie istnieje
        """
        with self._traces_lock:
            return self._traces.get(request_id)

    def get_all_traces(
        self, limit: int = 50, offset: int = 0, status_filter: Optional[str] = None
    ) -> List[RequestTrace]:
        """
        Pobiera listę wszystkich śladów.

        Args:
            limit: Maksymalna liczba wyników
            offset: Offset dla paginacji
            status_filter: Opcjonalny filtr po statusie

        Returns:
            Lista śladów posortowana od najnowszych
        """
        with self._traces_lock:
            traces = list(self._traces.values())

        # Filtruj po statusie jeśli podano
        if status_filter:
            traces = [t for t in traces if t.status == status_filter]

        # Sortuj malejąco (najnowsze -> najstarsze)
        traces.sort(key=lambda t: t.created_at, reverse=True)

        # Zastosuj paginację
        return traces[offset : offset + limit]

    def get_trace_count(self) -> int:
        """
        Zwraca liczbę wszystkich śladów.

        Returns:
            Liczba śladów w systemie
        """
        with self._traces_lock:
            return len(self._traces)

    def clear_old_traces(self, days: int = 7):
        """
        Usuwa stare ślady starsze niż podana liczba dni.

        Args:
            days: Liczba dni - ślady starsze zostaną usunięte
        """
        cutoff = get_utc_now() - timedelta(days=days)
        updated = False

        with self._traces_lock:
            to_remove = []
            for trace_id, trace in self._traces.items():
                if trace.created_at < cutoff:
                    to_remove.append(trace_id)

            for trace_id in to_remove:
                del self._traces[trace_id]

            if to_remove:
                updated = True

        if updated:
            self._save_traces()
            logger.info(f"Usunięto {len(to_remove)} starych śladów")
