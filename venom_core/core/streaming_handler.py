"""Moduł: streaming_handler - obsługa streamingu odpowiedzi LLM."""

import time
from typing import Callable
from uuid import UUID

from venom_core.core import metrics as metrics_module
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class StreamingHandler:
    """Handler do zarządzania streamingiem odpowiedzi LLM."""

    def __init__(
        self,
        state_manager,
        partial_emit_interval: float = 0.25,
    ):
        """
        Inicjalizacja StreamingHandler.

        Args:
            state_manager: Menedżer stanu zadań
            partial_emit_interval: Interwał (w sekundach) między emitowaniem częściowych wyników
        """
        self.state_manager = state_manager
        self.partial_emit_interval = partial_emit_interval

    def create_stream_callback(self, task_id: UUID) -> Callable[[str], None]:
        """
        Tworzy callback do obsługi streamingu dla danego zadania.

        Args:
            task_id: ID zadania

        Returns:
            Funkcja callback przyjmująca tekst jako argument
        """
        stream_start = time.perf_counter()
        first_chunk_sent = False
        collector = metrics_module.metrics_collector
        stream_buffer: list[str] = []
        last_partial_emit = stream_start
        chunk_count = 0

        def _handle_stream_chunk(text: str) -> None:
            nonlocal first_chunk_sent, last_partial_emit, chunk_count

            if not text:
                return

            stream_buffer.append(text)
            chunk_count += 1
            now = time.perf_counter()

            # Emituj częściowe wyniki z określonym interwałem
            should_emit_partial = (
                not first_chunk_sent
                or (now - last_partial_emit) >= self.partial_emit_interval
            )

            if should_emit_partial:
                self.state_manager.update_partial_result(
                    task_id, "".join(stream_buffer)
                )
                last_partial_emit = now
                elapsed_ms = int((now - stream_start) * 1000)
                self.state_manager.update_context(
                    task_id,
                    {
                        "streaming": {
                            "chunk_count": chunk_count,
                            "last_emit_ms": elapsed_ms,
                        }
                    },
                )

            # Obsługa pierwszego fragmentu (first token latency)
            if first_chunk_sent:
                return

            preview = (text or "").strip()
            if not preview:
                return

            first_chunk_sent = True
            elapsed_ms = int((now - stream_start) * 1000)
            preview_trimmed = preview[:200] + "..." if len(preview) > 200 else preview

            # Zaloguj pierwszy fragment
            self.state_manager.add_log(
                task_id, f"Pierwszy fragment odpowiedzi: {preview_trimmed}"
            )

            # Zaktualizuj kontekst z informacją o pierwszym tokenie
            task = self.state_manager.get_task(task_id)
            context_used_dict = None
            if task:
                context_used_dict = getattr(task, "context_used", None)
                if context_used_dict:
                    context_used_dict = context_used_dict.model_dump()

            self.state_manager.update_context(
                task_id,
                {
                    "first_token": {
                        "at": get_utc_now_iso(),
                        "elapsed_ms": elapsed_ms,
                        "preview": preview_trimmed,
                    },
                    "context_used": context_used_dict,
                },
            )
            self.state_manager.update_context(
                task_id,
                {
                    "streaming": {
                        "chunk_count": chunk_count,
                        "first_chunk_ms": elapsed_ms,
                    }
                },
            )

            # Dodaj metrykę first token latency
            if collector:
                collector.add_llm_first_token_sample(elapsed_ms)

        return _handle_stream_chunk
