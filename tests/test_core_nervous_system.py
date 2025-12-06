"""Testy integracyjne dla systemu zadań Venom Core Nervous System V1."""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from venom_core.main import app, state_manager


@pytest.fixture
def client():
    """Fixture dla klienta testowego FastAPI."""
    return TestClient(app)


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


@pytest.mark.asyncio
async def test_task_execution_lifecycle(clear_state):
    """Test pełnego cyklu życia zadania - integracyjny test asynchroniczny."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Utwórz zadanie
        create_response = await ac.post(
            "/api/v1/tasks", json={"content": "Zadanie do przetworzenia"}
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["task_id"]

        # Sprawdź status początkowy (PENDING lub już PROCESSING)
        get_response = await ac.get(f"/api/v1/tasks/{task_id}")
        task_data = get_response.json()
        assert task_data["status"] in ["PENDING", "PROCESSING"]

        # Poczekaj na zakończenie wykonania (MVP używa sleep(2))
        await asyncio.sleep(3)

        # Sprawdź status końcowy (COMPLETED)
        final_response = await ac.get(f"/api/v1/tasks/{task_id}")
        final_data = final_response.json()

        assert final_data["status"] == "COMPLETED"
        assert final_data["result"] is not None
        assert "Przetworzono" in final_data["result"]
        assert len(final_data["logs"]) > 0


@pytest.mark.asyncio
async def test_multiple_tasks_concurrent(clear_state):
    """Test równoczesnego przetwarzania wielu zadań."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Utwórz kilka zadań jednocześnie
        task_ids = []
        for i in range(5):
            response = await ac.post("/api/v1/tasks", json={"content": f"Zadanie {i}"})
            task_ids.append(response.json()["task_id"])

        # Poczekaj na zakończenie
        await asyncio.sleep(3)

        # Sprawdź czy wszystkie zadania zostały przetworzone
        for task_id in task_ids:
            response = await ac.get(f"/api/v1/tasks/{task_id}")
            data = response.json()
            assert data["status"] == "COMPLETED"


def test_invalid_task_request(client, clear_state):
    """Test błędnego requestu tworzenia zadania."""
    # Request bez wymaganego pola 'content'
    response = client.post("/api/v1/tasks", json={})
    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.asyncio
async def test_task_logs(clear_state):
    """Test czy zadanie zapisuje logi podczas wykonania."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Utwórz zadanie
        create_response = await ac.post(
            "/api/v1/tasks", json={"content": "Zadanie z logami"}
        )
        task_id = create_response.json()["task_id"]

        # Poczekaj na zakończenie
        await asyncio.sleep(3)

        # Sprawdź logi
        response = await ac.get(f"/api/v1/tasks/{task_id}")
        data = response.json()

        assert len(data["logs"]) >= 2  # Minimum: start i zakończenie
        assert any("uruchomione" in log.lower() for log in data["logs"])
        assert any(
            "zakończono" in log.lower() or "przetwarzanie" in log.lower()
            for log in data["logs"]
        )
