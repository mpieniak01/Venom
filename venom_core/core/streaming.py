"""
Moduł: streaming - Obsługa streamingu odpowiedzi LLM i częściowych aktualizacji.

Wydzielony z orchestrator.py dla lepszej organizacji kodu i testowalności.
"""

import time
from datetime import datetime
from typing import Callable, List
from uuid import UUID

from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class StreamingHandler:
    """Handler dla streamingu odpowiedzi LLM z częściowymi aktualizacjami."""

    def __init__(
        self,
        state_manager: StateManager,
        task_id: UUID,
        metrics_collector=None,
        partial_emit_interval: float = 0.25,
    ):
        """
        Inicjalizacja handlera streamingu.

        Args:
            state_manager: Menedżer stanu zadań
            task_id: ID zadania
            metrics_collector: Opcjonalny kolektor metryk
            partial_emit_interval: Interwał emisji częściowych aktualizacji (sekundy)
        """
        self.state_manager = state_manager
        self.task_id = task_id
        self.metrics_collector = metrics_collector
        self.partial_emit_interval = partial_emit_interval

        # Stan streamingu
        self.stream_start = time.perf_counter()
        self.first_chunk_sent = False
        self.stream_buffer: List[str] = []
        self.last_partial_emit = self.stream_start

    def handle_chunk(self, text: str) -> None:
        """
        Obsługuje fragment odpowiedzi ze streamingu LLM.

        Args:
            text: Fragment tekstu z LLM
        """
        if not text:
            return

        self.stream_buffer.append(text)
        now = time.perf_counter()

        # Emit partial result at intervals
        should_emit_partial = (
            not self.first_chunk_sent
            or (now - self.last_partial_emit) >= self.partial_emit_interval
        )

        if should_emit_partial:
            self.state_manager.update_partial_result(
                self.task_id, "".join(self.stream_buffer)
            )
            self.last_partial_emit = now

        # Handle first chunk specially for metrics
        if self.first_chunk_sent:
            return

        preview = (text or "").strip()
        if not preview:
            return

        self.first_chunk_sent = True
        self._record_first_token(preview, now)

    def _record_first_token(self, preview: str, now: float) -> None:
        """
        Rejestruje pierwszy token (TTFT - Time To First Token).

        Args:
            preview: Fragment tekstu
            now: Timestamp perf_counter
        """
        elapsed_ms = int((now - self.stream_start) * 1000)
        preview_trimmed = preview[:200] + "..." if len(preview) > 200 else preview

        self.state_manager.add_log(
            self.task_id, f"Pierwszy fragment odpowiedzi: {preview_trimmed}"
        )

        self.state_manager.update_context(
            self.task_id,
            {
                "first_token": {
                    "at": datetime.now().isoformat(),
                    "elapsed_ms": elapsed_ms,
                    "preview": preview_trimmed,
                }
            },
        )

        if self.metrics_collector:
            self.metrics_collector.add_llm_first_token_sample(elapsed_ms)

    def get_result(self) -> str:
        """
        Zwraca zebrane fragmenty jako pełny tekst.

        Returns:
            Połączony tekst ze wszystkich fragmentów
        """
        return "".join(self.stream_buffer)

    def get_callback(self) -> Callable[[str], None]:
        """
        Zwraca funkcję callback do użycia z set_llm_stream_callback.

        Returns:
            Callback function
        """
        return self.handle_chunk
