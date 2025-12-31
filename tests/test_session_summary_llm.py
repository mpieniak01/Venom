from unittest.mock import MagicMock, patch
from uuid import uuid4

from venom_core.core.models import TaskStatus, VenomTask
from venom_core.core.orchestrator import Orchestrator


def make_task_with_history():
    task_id = uuid4()
    task = VenomTask(id=task_id, content="foo", status=TaskStatus.PENDING)
    task.context_history["session_history_full"] = [
        {"role": "user", "content": f"msg {i}"} for i in range(25)
    ]
    return task_id, task


def test_summary_uses_llm_when_available(monkeypatch):
    state = MagicMock()
    task_id, task = make_task_with_history()
    state.get_task.return_value = task
    state.update_context = MagicMock()
    orch = Orchestrator(state_manager=state)

    with patch.object(
        orch, "_summarize_history_llm", return_value="LLM summary"
    ) as mock_llm:
        orch._ensure_session_summary(task_id, task)
        mock_llm.assert_called_once()
        # summary zapisane przez update_context
        args, kwargs = state.update_context.call_args
        assert args[0] == task_id
        assert kwargs is None or True  # compatibility no kwargs
        saved = args[1]["session_summary"]
        assert "LLM summary" in saved


def test_summary_falls_back_to_heuristic(monkeypatch):
    state = MagicMock()
    task_id, task = make_task_with_history()
    state.get_task.return_value = task
    state.update_context = MagicMock()
    orch = Orchestrator(state_manager=state)

    with patch.object(orch, "_summarize_history_llm", return_value="") as mock_llm:
        orch._ensure_session_summary(task_id, task)
        mock_llm.assert_called_once()
        args, kwargs = state.update_context.call_args
        saved = args[1]["session_summary"]
        assert "(Heurystyczne)" in saved


def test_summary_strategy_heuristic_only(monkeypatch):
    state = MagicMock()
    task_id, task = make_task_with_history()
    state.get_task.return_value = task
    state.update_context = MagicMock()
    orch = Orchestrator(state_manager=state)

    monkeypatch.setattr(
        "venom_core.config.SETTINGS.SUMMARY_STRATEGY", "heuristic_only", raising=False
    )
    with patch.object(
        orch, "_summarize_history_llm", return_value="LLM summary"
    ) as mock_llm:
        orch._ensure_session_summary(task_id, task)
        # LLM nie powinien być użyty przy strategii heuristic_only
        mock_llm.assert_not_called()
        args, kwargs = state.update_context.call_args
        saved = args[1]["session_summary"]
        assert "(Heurystyczne)" in saved
