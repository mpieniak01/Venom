"""Moduł: base - Bazowa klasa dla wszystkich Flow."""

from typing import Callable, Optional


class BaseFlow:
    """Bazowa klasa dla wszystkich Flow - zawiera wspólną logikę."""

    def __init__(self, event_broadcaster: Optional[Callable] = None):
        """
        Inicjalizacja BaseFlow.

        Args:
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        self.event_broadcaster = event_broadcaster

    async def _broadcast_event(
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
