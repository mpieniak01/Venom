import pytest

from venom_core.core.orchestrator.constants import SESSION_FULL_HISTORY_LIMIT
from venom_core.core.orchestrator.session_handler import SessionHandler
from venom_core.core.state_manager import StateManager


class MockMemorySkill:
    def __init__(self):
        self.vector_store = None


@pytest.mark.asyncio
async def test_state_manager_pruning():
    # Inicjalizacja StateManager z tymczasowym plikiem
    sm = StateManager(state_file_path="data/test_state_pruning.json")

    # Tworzymy 1050 zadań (limit to 1000)
    for i in range(1050):
        sm.create_task(f"Task {i}")

    # Sprawdzamy czy liczba zadań jest ograniczona do 1000
    tasks = sm.get_all_tasks()
    assert len(tasks) == 1000

    # Sprawdzamy czy najstarsze zadania zostały usunięte (powinny zostać od 50 do 1049)
    contents = [t.content for t in tasks]
    assert "Task 0" not in contents
    assert "Task 1049" in contents

    await sm.shutdown()


@pytest.mark.asyncio
async def test_session_handler_full_history_limit():
    sm = StateManager(state_file_path="data/test_session_handler.json")
    memory = MockMemorySkill()
    sh = SessionHandler(state_manager=sm, memory_skill=memory)

    task = sm.create_task("Main Task")
    session_id = "test_session_123"

    # Dodajemy 600 wiadomości (limit to 500)
    for i in range(600):
        sh.append_session_history(task.id, "user", f"Msg {i}", session_id)

    # Pobieramy zadanie ponownie ze stanu
    updated_task = sm.get_task(task.id)
    full_history = updated_task.context_history.get("session_history_full", [])

    assert len(full_history) == SESSION_FULL_HISTORY_LIMIT
    assert full_history[-1]["content"] == "Msg 599"
    assert full_history[0]["content"] == "Msg 100"  # 600 - 500 = 100

    await sm.shutdown()
