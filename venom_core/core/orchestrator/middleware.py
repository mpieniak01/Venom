"""Middleware dla obsługi błędów, zdarzeń i logowania."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.state_manager import StateManager
    from venom_core.core.tracer import RequestTracer

logger = get_logger(__name__)


class Middleware:
    """Obsługuje błędy, zdarzenia i logowanie w Orchestrator."""

    def __init__(
        self,
        state_manager: "StateManager",
        event_broadcaster=None,
        request_tracer: Optional["RequestTracer"] = None,
    ):
        """
        Inicjalizacja Middleware.

        Args:
            state_manager: Menedżer stanu zadań
            event_broadcaster: Opcjonalny broadcaster zdarzeń do WebSocket
            request_tracer: Opcjonalny tracer do śledzenia przepływu
        """
        self.state_manager = state_manager
        self.event_broadcaster = event_broadcaster
        self.request_tracer = request_tracer

    async def broadcast_event(
        self, event_type: str, message: str, agent: str = None, data: dict = None
    ):
        """
        Wysyła zdarzenie do WebSocket (jeśli broadcaster jest dostępny).

        Args:
            event_type: Typ zdarzenia
            message: Treść wiadomości
            agent: Opcjonalna nazwa agenta
            data: Opcjonalne dodatkowe dane
        """
        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=event_type, message=message, agent=agent, data=data
            )

    def build_error_envelope(
        self,
        *,
        error_code: str,
        error_message: str,
        error_details: Optional[dict] = None,
        stage: Optional[str] = None,
        retryable: bool = False,
        error_class: Optional[str] = None,
    ) -> dict:
        """
        Tworzy standardową strukturę błędu.

        Args:
            error_code: Kod błędu
            error_message: Opis błędu
            error_details: Dodatkowe szczegóły błędu
            stage: Etap w którym wystąpił błąd
            retryable: Czy błąd można powtórzyć
            error_class: Klasa błędu

        Returns:
            Słownik z danymi błędu
        """
        return {
            "error_code": error_code,
            "error_class": error_class or error_code,
            "error_message": error_message,
            "error_details": error_details or {},
            "stage": stage,
            "retryable": retryable,
        }

    def set_runtime_error(self, task_id: UUID, envelope: dict) -> None:
        """
        Zapisuje błąd runtime w kontekście zadania.

        Args:
            task_id: ID zadania
            envelope: Struktura błędu z build_error_envelope
        """
        self.state_manager.update_context(
            task_id,
            {
                "llm_runtime": {
                    "status": "error",
                    "error": envelope,
                    "last_error_at": datetime.now().isoformat(),
                }
            },
        )
        if self.request_tracer:
            self.request_tracer.set_error_metadata(task_id, envelope)
