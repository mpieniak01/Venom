"""Testy integracyjne dla systemu zadań Venom Core Nervous System V1."""

import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.main import app, state_manager
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock dla get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint="http://mock",
        service_type="local",
        mode="LOCAL",
        config_hash="abc123456789",
        runtime_id="local@http://mock",
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=mock_runtime_info,
        ),
    ):
        with (
            patch("venom_core.config.SETTINGS") as mock_settings,
            patch(
                "venom_core.core.orchestrator.orchestrator_dispatch.SETTINGS",
                new=mock_settings,
            ),
        ):
            mock_settings.LLM_CONFIG_HASH = "abc123456789"
            yield


@pytest.fixture
def client():
    """Fixture dla klienta testowego FastAPI (odpala lifespan)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clear_state():
    """Fixture czyszczący stan przed testem."""
    state_manager._tasks.clear()
    yield
    state_manager._tasks.clear()


def test_healthz_endpoint(client):
    """Test endpointu health check."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "venom-core"}


def test_create_task(client, clear_state):
    """Test tworzenia zadania przez API."""
    response = client.post("/api/v1/tasks", json={"content": "Test zadania"})

    assert response.status_code == 201
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "PENDING"


def test_get_task(client, clear_state):
    """Test pobierania zadania po ID."""
    # Utwórz zadanie
    create_response = client.post("/api/v1/tasks", json={"content": "Test zadania"})
    task_id = create_response.json()["task_id"]

    # Pobierz zadanie
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == task_id
    assert data["content"] == "Test zadania"
    assert data["status"] in ["PENDING", "PROCESSING", "COMPLETED"]


def test_get_nonexistent_task(client, clear_state):
    """Test pobierania nieistniejącego zadania."""
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/tasks/{fake_id}")
    assert response.status_code == 404


def test_get_all_tasks(client, clear_state):
    """Test pobierania listy wszystkich zadań."""
    # Utwórz kilka zadań
    client.post("/api/v1/tasks", json={"content": "Zadanie 1"})
    client.post("/api/v1/tasks", json={"content": "Zadanie 2"})
    client.post("/api/v1/tasks", json={"content": "Zadanie 3"})

    # Pobierz wszystkie zadania
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3
    assert all("id" in task for task in data)
    assert all("content" in task for task in data)


def test_task_execution_lifecycle(client, clear_state):
    """Test pełnego cyklu życia zadania - integracyjny test synchroniczny."""
    # Utwórz zadanie
    create_response = client.post(
        "/api/v1/tasks", json={"content": "Zadanie do przetworzenia"}
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["task_id"]

    # Sprawdź status początkowy (PENDING lub już PROCESSING)
    get_response = client.get(f"/api/v1/tasks/{task_id}")
    task_data = get_response.json()
    assert task_data["status"] in ["PENDING", "PROCESSING"]

    # Poczekaj na zakończenie wykonania (MVP używa sleep(2))
    time.sleep(3)

    # Sprawdź status końcowy (COMPLETED)
    final_response = client.get(f"/api/v1/tasks/{task_id}")
    final_data = final_response.json()

    assert final_data["status"] == "COMPLETED"
    assert final_data["result"] is not None
    assert "Przetworzono" in final_data["result"]
    assert len(final_data["logs"]) > 0


def test_multiple_tasks_concurrent(client, clear_state):
    """Test równoczesnego przetwarzania wielu zadań."""
    # Utwórz kilka zadań jednocześnie
    task_ids = []
    for i in range(5):
        response = client.post(
            "/api/v1/tasks",
            json={
                "content": f"Pomoc {i}",
                "forced_intent": "HELP_REQUEST",
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert "task_id" in payload
        task_ids.append(payload["task_id"])

    # Poczekaj na zakończenie (polling, żeby uniknąć flakiness)
    timeout_s = 10.0
    deadline = time.monotonic() + timeout_s
    while True:
        all_completed = True
        for task_id in task_ids:
            response = client.get(f"/api/v1/tasks/{task_id}")
            data = response.json()
            if data["status"] != "COMPLETED":
                all_completed = False
                break
        if all_completed:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)

    # Sprawdź czy wszystkie zadania zostały przetworzone
    for task_id in task_ids:
        response = client.get(f"/api/v1/tasks/{task_id}")
        data = response.json()
        assert data["status"] == "COMPLETED"


def test_invalid_task_request(client, clear_state):
    """Test błędnego requestu tworzenia zadania."""
    # Request bez wymaganego pola 'content'
    response = client.post("/api/v1/tasks", json={})
    assert response.status_code == 422  # Unprocessable Entity


def test_task_logs(client, clear_state):
    """Test czy zadanie zapisuje logi podczas wykonania."""
    # Utwórz zadanie
    create_response = client.post("/api/v1/tasks", json={"content": "Zadanie z logami"})
    task_id = create_response.json()["task_id"]

    # Poczekaj na zakończenie
    time.sleep(3)

    # Sprawdź logi
    response = client.get(f"/api/v1/tasks/{task_id}")
    data = response.json()

    assert len(data["logs"]) >= 2  # Minimum: start i zakończenie
    assert any("uruchomione" in log.lower() for log in data["logs"])
    assert any(
        "zakończono" in log.lower() or "przetwarzanie" in log.lower()
        for log in data["logs"]
    )
