from unittest.mock import MagicMock
from uuid import uuid4

from venom_core.core.models import TaskStatus, VenomTask
from venom_core.core.orchestrator import SESSION_HISTORY_LIMIT, Orchestrator


def make_state_with_task() -> MagicMock:
    state = MagicMock()
    task_id = uuid4()
    task = VenomTask(id=task_id, content="foo", status=TaskStatus.PENDING)
    state.get_task.return_value = task
    state.update_context = MagicMock()
    return state, task_id, task


def test_append_session_history_adds_entries():
    state, task_id, task = make_state_with_task()
    orch = Orchestrator(state_manager=state)

    orch._append_session_history(task_id, "user", "hello", session_id="s1")
    orch._append_session_history(task_id, "assistant", "hi", session_id="s1")

    # ostatnie wywołanie update_context powinno zawierać oba wpisy
    args, kwargs = state.update_context.call_args
    assert args[0] == task_id
    history = args[1]["session_history"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_append_session_history_trims_to_limit():
    state, task_id, task = make_state_with_task()
    orch = Orchestrator(state_manager=state)

    for i in range(SESSION_HISTORY_LIMIT + 5):
        orch._append_session_history(task_id, "user", f"msg-{i}", session_id="s1")

    args, kwargs = state.update_context.call_args
    history = args[1]["session_history"]
    assert len(history) == SESSION_HISTORY_LIMIT
    assert history[0]["content"] == f"msg-{5}"  # najstarsze obcięte
