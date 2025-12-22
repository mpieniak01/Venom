"""Testy jednostkowe dla modułu streaming."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from venom_core.core.streaming import StreamingHandler


def test_streaming_handler_initialization():
    """Test inicjalizacji StreamingHandler."""
    state_manager = MagicMock()
    task_id = uuid4()
    metrics_collector = MagicMock()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
        metrics_collector=metrics_collector,
        partial_emit_interval=0.5,
    )

    assert handler.state_manager == state_manager
    assert handler.task_id == task_id
    assert handler.metrics_collector == metrics_collector
    assert handler.partial_emit_interval == 0.5
    assert handler.first_chunk_sent is False
    assert len(handler.stream_buffer) == 0


def test_handle_chunk_empty_text():
    """Test obsługi pustego fragmentu tekstu."""
    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
    )

    handler.handle_chunk("")

    # Pusty fragment nie powinien nic zrobić
    assert len(handler.stream_buffer) == 0
    state_manager.update_partial_result.assert_not_called()


def test_handle_chunk_first_token():
    """Test rejestracji pierwszego tokenu (TTFT)."""
    state_manager = MagicMock()
    task_id = uuid4()
    metrics_collector = MagicMock()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
        metrics_collector=metrics_collector,
    )

    handler.handle_chunk("Hello")

    # Pierwszy fragment powinien być zalogowany
    assert handler.first_chunk_sent is True
    assert len(handler.stream_buffer) == 1
    assert handler.stream_buffer[0] == "Hello"

    # Sprawdź czy dodano log i zaktualizowano kontekst
    state_manager.add_log.assert_called_once()
    state_manager.update_context.assert_called_once()
    state_manager.update_partial_result.assert_called_once_with(task_id, "Hello")

    # Sprawdź czy dodano metrykę TTFT
    metrics_collector.add_llm_first_token_sample.assert_called_once()


def test_handle_chunk_multiple_fragments():
    """Test obsługi wielu fragmentów tekstu."""
    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
        partial_emit_interval=0.1,
    )

    handler.handle_chunk("Hello")
    handler.handle_chunk(" world")
    handler.handle_chunk("!")

    # Sprawdź czy wszystkie fragmenty zostały zebrane
    assert len(handler.stream_buffer) == 3
    assert "".join(handler.stream_buffer) == "Hello world!"


def test_get_result():
    """Test zwracania pełnego wyniku."""
    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
    )

    handler.handle_chunk("Hello")
    handler.handle_chunk(" world")
    handler.handle_chunk("!")

    result = handler.get_result()

    assert result == "Hello world!"


def test_get_callback():
    """Test zwracania funkcji callback."""
    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
    )

    callback = handler.get_callback()

    # Callback powinien być funkcją
    assert callable(callback)

    # Wywołanie callback powinno działać jak handle_chunk
    callback("test")
    assert len(handler.stream_buffer) == 1
    assert handler.stream_buffer[0] == "test"


def test_partial_emit_interval():
    """Test interwału emisji częściowych wyników."""
    import time

    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
        partial_emit_interval=0.05,  # 50ms
    )

    # Pierwszy fragment - powinien wywołać partial update
    handler.handle_chunk("First")
    assert state_manager.update_partial_result.call_count == 1

    # Drugi fragment natychmiast - nie powinien wywołać partial update (za wcześnie)
    handler.handle_chunk(" Second")
    # Nadal 1, bo interval nie upłynął
    assert state_manager.update_partial_result.call_count == 1

    # Poczekaj na upłynięcie interwału
    time.sleep(0.06)

    # Trzeci fragment - powinien wywołać partial update
    handler.handle_chunk(" Third")
    assert state_manager.update_partial_result.call_count == 2


def test_long_preview_truncation():
    """Test skracania długich podglądów pierwszego tokenu."""
    state_manager = MagicMock()
    task_id = uuid4()

    handler = StreamingHandler(
        state_manager=state_manager,
        task_id=task_id,
    )

    # Fragment dłuższy niż 200 znaków
    long_text = "A" * 250

    handler.handle_chunk(long_text)

    # Sprawdź czy kontekst zawiera skrócony podgląd
    context_call = state_manager.update_context.call_args[0][1]
    preview = context_call["first_token"]["preview"]

    # Powinien być skrócony do 200 znaków + "..."
    assert len(preview) == 203  # 200 + "..."
    assert preview.endswith("...")
