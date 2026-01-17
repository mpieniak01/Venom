from uuid import UUID

from venom_core.core.state_manager import StateManager


def test_clear_session_context_resets_only_matching_session():
    state_manager = StateManager()

    task_a = state_manager.create_task("foo")
    task_b = state_manager.create_task("bar")

    task_a.context_history = {
        "session": {"session_id": "s1"},
        "session_history": ["u1", "a1"],
        "session_history_full": ["u1", "a1"],
        "session_summary": "sum-1",
    }
    task_b.context_history = {
        "session": {"session_id": "s2"},
        "session_history": ["u2"],
        "session_history_full": ["u2"],
        "session_summary": "sum-2",
    }

    updated = state_manager.clear_session_context("s1")
    assert updated == 1

    ctx_a = state_manager.get_task(UUID(str(task_a.id))).context_history
    assert ctx_a["session"] == {"session_id": "s1"}
    assert ctx_a["session_history"] == []
    assert ctx_a["session_history_full"] == []
    assert ctx_a["session_summary"] is None

    ctx_b = state_manager.get_task(UUID(str(task_b.id))).context_history
    assert ctx_b["session_history"] == ["u2"]
    assert ctx_b["session_summary"] == "sum-2"
