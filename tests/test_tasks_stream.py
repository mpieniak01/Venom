"""Testy integracyjne dla strumienia `/api/v1/tasks/{id}/stream`."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.api import dependencies as api_deps
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

    api_deps.set_state_manager(state_manager)
    client = TestClient(app)

    try:
        yield client, task_id
    finally:
        api_deps.set_state_manager(DummyStateManager({}))


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


@pytest.mark.parametrize("forced_intent", [None, "COMPLEX_PLANNING"])
def test_onnx_task_submission_preserves_orchestrator_contract(
    monkeypatch, forced_intent
):
    """Normal/Complex must not enter a provider-specific native generation pool."""
    from unittest.mock import AsyncMock

    from fastapi import FastAPI

    from venom_core.api.routes import tasks as routes
    from venom_core.api.schemas.tasks import TaskResponse
    from venom_core.config import SETTINGS
    from venom_core.utils.llm_runtime import get_active_llm_runtime

    monkeypatch.setattr(SETTINGS, "LLM_SERVICE_TYPE", "onnx")
    monkeypatch.setattr(SETTINGS, "ACTIVE_LLM_SERVER", "onnx")
    monkeypatch.setattr(SETTINGS, "ONNX_LLM_ENABLED", True)
    monkeypatch.setattr(SETTINGS, "ONNX_LLM_ENDPOINT", "http://127.0.0.1:8068/v1")
    assert get_active_llm_runtime().provider == "onnx"
    expected = TaskResponse(task_id=uuid4(), status=TaskStatus.PENDING.value)
    orchestrator = type("OrchestratorFixture", (), {})()
    orchestrator.submit_task = AsyncMock(return_value=expected)
    isolated_app = FastAPI()
    isolated_app.include_router(routes.router)
    isolated_app.dependency_overrides[api_deps.get_orchestrator] = lambda: orchestrator
    payload = {
        "content": "Explain one byte",
        "session_id": "onnx-session",
        "store_knowledge": False,
    }
    if forced_intent:
        payload["forced_intent"] = forced_intent
    with TestClient(isolated_app) as client:
        response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["task_id"] == str(expected.task_id)
    orchestrator.submit_task.assert_awaited_once()
    submitted = orchestrator.submit_task.await_args.args[0]
    assert submitted.forced_intent == forced_intent
    assert submitted.session_id == "onnx-session"
    assert submitted.store_knowledge is False
