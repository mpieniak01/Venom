from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from venom_core.core.streaming_handler import StreamingHandler


def test_should_emit_partial_logic():
    handler = StreamingHandler(state_manager=MagicMock(), partial_emit_interval=0.25)
    assert handler._should_emit_partial(False, 1.0, 1.0)
    assert not handler._should_emit_partial(True, 1.1, 1.0)
    assert handler._should_emit_partial(True, 1.3, 1.0)


def test_emit_partial_update_updates_state_manager():
    state = MagicMock()
    handler = StreamingHandler(state_manager=state)
    task_id = uuid4()

    handler._emit_partial_update(
        task_id, ["a", "b"], now=2.0, stream_start=1.0, chunk_count=2
    )

    state.update_partial_result.assert_called_once_with(task_id, "ab")
    state.update_context.assert_called_once()
    args = state.update_context.call_args[0]
    assert args[0] == task_id
    assert args[1]["streaming"]["chunk_count"] == 2


def test_create_stream_callback_handles_first_chunk_and_metrics(monkeypatch):
    state = MagicMock()
    state.get_task.return_value = SimpleNamespace(context_used=None)
    collector = MagicMock()
    monkeypatch.setattr(
        "venom_core.core.streaming_handler.metrics_module.metrics_collector", collector
    )
    monkeypatch.setattr(
        "venom_core.core.streaming_handler.get_utc_now_iso",
        lambda: "2026-01-01T00:00:00Z",
    )

    handler = StreamingHandler(state_manager=state, partial_emit_interval=0.0)
    task_id = uuid4()
    callback = handler.create_stream_callback(task_id)

    callback("hello")

    state.update_partial_result.assert_called()
    state.add_log.assert_called_once()
    assert state.update_context.call_count >= 2
    collector.add_llm_first_token_sample.assert_called_once()
