"""Moduł: tracer - śledzenie przepływu zadań przez system."""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

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
    timestamp: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="ok", description="Status kroku (ok, error)")
    details: Optional[str] = Field(
        default=None, description="Dodatkowe szczegóły (błąd, wynik)"
    )


class RequestTrace(BaseModel):
    """Ślad przepływu pojedynczego zadania."""

    request_id: UUID
    status: TraceStatus = TraceStatus.PENDING
    prompt: str = Field(description="Treść polecenia użytkownika (skrócona)")
    created_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    steps: List[TraceStep] = Field(default_factory=list)
    last_activity: datetime = Field(default_factory=datetime.now)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None


class RequestTracer:
    """
    Centralny rejestr śladów zadań.

    Przechowuje informacje o przepływie każdego zadania przez system,
    od momentu utworzenia do zakończenia.
    """

    def __init__(self, watchdog_timeout_minutes: int = 5):
        """
        Inicjalizacja tracera.

        Args:
            watchdog_timeout_minutes: Czas w minutach po którym zadanie
                                     bez aktywności jest oznaczane jako LOST
        """
        self._traces: Dict[UUID, RequestTrace] = {}
        self._traces_lock = Lock()  # Thread safety
        self._watchdog_timeout = timedelta(minutes=watchdog_timeout_minutes)
        self._watchdog_task: Optional[asyncio.Task] = None

    async def start_watchdog(self):
        """Uruchamia watchdog do monitorowania zagubionych zadań."""
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            logger.info("RequestTracer watchdog uruchomiony")

    async def stop_watchdog(self):
        """Zatrzymuje watchdog."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                # Oczekiwane anulowanie zadania watchdog przy zatrzymywaniu
                pass
            self._watchdog_task = None
            logger.info("RequestTracer watchdog zatrzymany")

    async def _watchdog_loop(self):
        """Pętla watchdog sprawdzająca zagubione zadania."""
        while True:
            try:
                await asyncio.sleep(60)  # Sprawdzaj co minutę
                await self._check_lost_requests()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Błąd w watchdog loop: {e}", exc_info=True)

    async def _check_lost_requests(self):
        """Sprawdza i oznacza zadania, które przekroczyły timeout."""
        now = datetime.now()
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

    def create_trace(self, request_id: UUID, prompt: str) -> RequestTrace:
        """
        Tworzy nowy ślad dla zadania.

        Args:
            request_id: UUID zadania
            prompt: Treść polecenia użytkownika

        Returns:
            Utworzony ślad
        """
        # Skróć prompt do 200 znaków
        prompt_truncated = prompt[:200] + "..." if len(prompt) > 200 else prompt

        trace = RequestTrace(
            request_id=request_id,
            prompt=prompt_truncated,
            status=TraceStatus.PENDING,
        )
        with self._traces_lock:
            self._traces[request_id] = trace
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
            trace.last_activity = datetime.now()

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
            trace.last_activity = datetime.now()

            # Ustaw finished_at dla stanów końcowych
            if status in (TraceStatus.COMPLETED, TraceStatus.FAILED, TraceStatus.LOST):
                trace.finished_at = datetime.now()

        logger.debug(f"Zaktualizowano status trace {request_id}: {status}")

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

        logger.debug(
            f"Zaktualizowano informacje o LLM dla trace {request_id}: {provider}/{model}"
        )

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

        # Sortuj od najnowszych
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
        cutoff = datetime.now() - timedelta(days=days)

        with self._traces_lock:
            to_remove = []
            for trace_id, trace in self._traces.items():
                if trace.created_at < cutoff:
                    to_remove.append(trace_id)

            for trace_id in to_remove:
                del self._traces[trace_id]

        if to_remove:
            logger.info(f"Usunięto {len(to_remove)} starych śladów")
