from unittest.mock import MagicMock
from uuid import uuid4

from venom_core.core.models import TaskRequest, TaskStatus, VenomTask
from venom_core.core.orchestrator import SESSION_HISTORY_LIMIT, Orchestrator
from venom_core.services.session_store import SessionStore


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


def test_session_history_shared_across_tasks(tmp_path):
    store_path = tmp_path / "session_store.json"
    session_store = SessionStore(store_path=str(store_path))
    task_id_1 = uuid4()
    task_id_2 = uuid4()
    task_1 = VenomTask(id=task_id_1, content="foo", status=TaskStatus.PENDING)
    task_2 = VenomTask(id=task_id_2, content="bar", status=TaskStatus.PENDING)
    for task in (task_1, task_2):
        task.context_history = {"session": {"session_id": "s1"}}

    state = MagicMock()
    state.get_task.side_effect = lambda tid: task_1 if tid == task_id_1 else task_2
    state.update_context = MagicMock()

    orch = Orchestrator(state_manager=state, session_store=session_store)
    orch._append_session_history(task_id_1, "user", "hello", session_id="s1")
    orch._append_session_history(task_id_1, "assistant", "hi", session_id="s1")

    context = orch._build_session_context_block(
        TaskRequest(content="test", session_id="s1"), task_id_2
    )

    assert "HISTORIA SESJI" in context
    assert "user: hello" in context
