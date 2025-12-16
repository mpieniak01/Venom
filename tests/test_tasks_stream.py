"""Testy integracyjne dla strumienia `/api/v1/tasks/{id}/stream`."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.api.routes import tasks as tasks_routes
from venom_core.core.models import TaskStatus, VenomTask
from venom_core.main import app


class DummyStateManager:
    """Minimalny StateManager na potrzeby testów SSE."""

    def __init__(self, tasks):
        self._tasks = tasks

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def get_all_tasks(self):
        return list(self._tasks.values())


@pytest.fixture
def streaming_client():
    """Konfiguruje FastAPI TestClient z podstawionym StateManagerem."""

    task_id = uuid4()
    task = VenomTask(
        id=task_id,
        content="Diagnostyka SSE",
        status=TaskStatus.COMPLETED,
        logs=["Plan wykonany", "Raport wygenerowany"],
        result="Gotowe",
    )
    state_manager = DummyStateManager({task_id: task})

    tasks_routes.set_dependencies(
        orchestrator=None, state_manager=state_manager, request_tracer=None
    )
    client = TestClient(app)

    try:
        yield client, task_id
    finally:
        tasks_routes.set_dependencies(None, None, None)


def test_task_stream_emits_update_and_finished(streaming_client):
    client, task_id = streaming_client

    with client.stream("GET", f"/api/v1/tasks/{task_id}/stream") as response:
        assert response.status_code == 200
        payload = "".join(list(response.iter_text()))

    lines = [line for line in payload.splitlines() if line.strip()]
    assert lines[0] == "event:task_update"
    update_payload = json.loads(lines[1].removeprefix("data:"))
    assert update_payload["status"] == TaskStatus.COMPLETED.value
    assert update_payload["logs"] == ["Plan wykonany", "Raport wygenerowany"]
    assert update_payload["result"] == "Gotowe"

    assert lines[2] == "event:task_finished"
    finished_payload = json.loads(lines[3].removeprefix("data:"))
    assert finished_payload["status"] == TaskStatus.COMPLETED.value
    assert finished_payload["result"] == "Gotowe"
