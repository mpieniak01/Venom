from unittest.mock import MagicMock
from uuid import uuid4

from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import Orchestrator


def build_orchestrator_with_state(state_manager: MagicMock) -> Orchestrator:
    # Orchestrator akceptuje dowolny obiekt z wymaganymi metodami state_manager
    return Orchestrator(state_manager=state_manager)


def test_persist_session_context_skips_when_empty():
    state = MagicMock()
    state.update_context = MagicMock()
    state.add_log = MagicMock()

    orch = build_orchestrator_with_state(state)
    orch._persist_session_context(uuid4(), TaskRequest(content="test"))

    state.update_context.assert_not_called()
    state.add_log.assert_not_called()


def test_persist_session_context_saves_filtered_fields():
    state = MagicMock()
    state.update_context = MagicMock()
    state.add_log = MagicMock()

    orch = build_orchestrator_with_state(state)
    task_id = uuid4()
    request = TaskRequest(
        content="test",
        session_id="sess-1",
        preference_scope="global",
        tone="concise",
        style_notes=None,
        preferred_language="pl",
    )

    orch._persist_session_context(task_id, request)

    state.update_context.assert_called_once()
    args, kwargs = state.update_context.call_args
    assert args[0] == task_id
    assert "session" in args[1]
    saved = args[1]["session"]
    assert saved["session_id"] == "sess-1"
    assert saved["preference_scope"] == "global"
    assert saved["tone"] == "concise"
    assert saved["preferred_language"] == "pl"
    # style_notes było None, nie powinno się pojawić
    assert "style_notes" not in saved

    state.add_log.assert_called_once()
