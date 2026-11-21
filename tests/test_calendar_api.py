"""Testy jednostkowe dla Calendar API."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import calendar as calendar_routes


@pytest.fixture
def mock_calendar_skill():
    """Fixture dla zmockowanego GoogleCalendarSkill."""
    mock_skill = MagicMock()
    mock_skill.credentials_available = True
    return mock_skill


@pytest.fixture
def mock_calendar_skill_no_credentials():
    """Fixture dla GoogleCalendarSkill bez credentials."""
    mock_skill = MagicMock()
    mock_skill.credentials_available = False
    return mock_skill


@pytest.fixture
def app_with_calendar(mock_calendar_skill):
    """Fixture dla FastAPI app z calendar routerem."""
    app = FastAPI()
    calendar_routes.set_dependencies(mock_calendar_skill)
    app.include_router(calendar_routes.router)
    return app


@pytest.fixture
def app_without_credentials(mock_calendar_skill_no_credentials):
    """Fixture dla FastAPI app bez credentials."""
    app = FastAPI()
    calendar_routes.set_dependencies(mock_calendar_skill_no_credentials)
    app.include_router(calendar_routes.router)
    return app


@pytest.fixture
def client(app_with_calendar):
    """Fixture dla test clienta."""
    return TestClient(app_with_calendar)


@pytest.fixture
def client_no_credentials(app_without_credentials):
    """Fixture dla test clienta bez credentials."""
    return TestClient(app_without_credentials)


def test_get_events_success(client, mock_calendar_skill):
    """Test pobierania wydarzeń - sukces."""
    # Mock odpowiedzi z skill
    mock_calendar_skill.read_agenda.return_value = (
        "📅 Agenda: 2024-01-15 09:00 - 2024-01-16 09:00\n\n"
        "🕒 09:00 - 10:00\n   Spotkanie 1\n\n"
        "🕒 14:00 - 15:00\n   Spotkanie 2"
    )

    response = client.get("/api/v1/calendar/events?time_min=now&hours=24")

    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "total" in data
    assert "time_min" in data
    assert "time_max" in data
    assert isinstance(data["events"], list)
    # Currently returns empty list as skill returns text format
    assert data["total"] == 0
    mock_calendar_skill.read_agenda.assert_called_once_with(time_min="now", hours=24)


def test_get_events_no_events(client, mock_calendar_skill):
    """Test pobierania wydarzeń - brak wydarzeń."""
    mock_calendar_skill.read_agenda.return_value = (
        "📅 Brak wydarzeń w kalendarzu od 2024-01-15 09:00 przez następne 24h"
    )

    response = client.get("/api/v1/calendar/events")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["events"]) == 0


def test_get_events_without_credentials(client_no_credentials):
    """Test pobierania wydarzeń bez credentials."""
    response = client_no_credentials.get("/api/v1/calendar/events")

    assert response.status_code == 503
    assert "Google Calendar nie jest skonfigurowany" in response.json()["detail"]


def test_get_events_with_custom_params(client, mock_calendar_skill):
    """Test pobierania wydarzeń z niestandardowymi parametrami."""
    mock_calendar_skill.read_agenda.return_value = "📅 Agenda..."

    response = client.get(
        "/api/v1/calendar/events?time_min=2024-01-15T09:00:00Z&hours=48"
    )

    assert response.status_code == 200
    mock_calendar_skill.read_agenda.assert_called_once_with(
        time_min="2024-01-15T09:00:00Z", hours=48
    )


def test_create_event_success(client, mock_calendar_skill):
    """Test tworzenia wydarzenia - sukces."""
    mock_calendar_skill.schedule_task.return_value = (
        "✅ Zaplanowano zadanie w kalendarzu Venoma:\n"
        "📌 Tytuł: Test Event\n"
        "🕒 Czas: 2024-01-15 16:00 - 17:00\n"
        "⏱️  Czas trwania: 60 minut\n"
        "🔗 Link: https://calendar.google.com/event?eid=test123\n"
    )

    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 60,
        "description": "Test description",
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "Test Event" in data["message"]
    assert data["event_link"] == "https://calendar.google.com/event?eid=test123"

    mock_calendar_skill.schedule_task.assert_called_once_with(
        title="Test Event",
        start_time="2024-01-15T16:00:00",
        duration_minutes=60,
        description="Test description",
    )


def test_create_event_without_credentials(client_no_credentials):
    """Test tworzenia wydarzenia bez credentials."""
    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 60,
    }

    response = client_no_credentials.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 503
    assert "Google Calendar nie jest skonfigurowany" in response.json()["detail"]


def test_create_event_empty_title(client):
    """Test tworzenia wydarzenia z pustym tytułem."""
    event_data = {
        "title": "   ",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 60,
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 400
    assert "Tytuł nie może być pusty" in response.json()["detail"]


def test_create_event_invalid_duration(client):
    """Test tworzenia wydarzenia z nieprawidłowym czasem trwania."""
    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 0,
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 400
    assert "Czas trwania musi być większy od 0" in response.json()["detail"]


def test_create_event_skill_error(client, mock_calendar_skill):
    """Test tworzenia wydarzenia - błąd skill."""
    mock_calendar_skill.schedule_task.return_value = (
        "❌ Błąd Google Calendar API: 403 Forbidden"
    )

    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 60,
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    # Skill zwraca komunikat o błędzie, ale nie rzuca wyjątku
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "error"
    assert "❌" in data["message"]


def test_create_event_with_default_duration(client, mock_calendar_skill):
    """Test tworzenia wydarzenia z domyślnym czasem trwania."""
    mock_calendar_skill.schedule_task.return_value = "✅ Zaplanowano zadanie..."

    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        # duration_minutes nie podany - użyje domyślnego 60
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 201
    mock_calendar_skill.schedule_task.assert_called_once()
    call_args = mock_calendar_skill.schedule_task.call_args
    assert call_args[1]["duration_minutes"] == 60


def test_create_event_exception_handling(client, mock_calendar_skill):
    """Test obsługi wyjątków podczas tworzenia wydarzenia."""
    mock_calendar_skill.schedule_task.side_effect = Exception("Unexpected error")

    event_data = {
        "title": "Test Event",
        "start_time": "2024-01-15T16:00:00",
        "duration_minutes": 60,
    }

    response = client.post("/api/v1/calendar/event", json=event_data)

    assert response.status_code == 500
    assert (
        "Wystąpił nieoczekiwany błąd podczas tworzenia wydarzenia"
        in response.json()["detail"]
    )


def test_get_events_exception_handling(client, mock_calendar_skill):
    """Test obsługi wyjątków podczas pobierania wydarzeń."""
    mock_calendar_skill.read_agenda.side_effect = Exception("Unexpected error")

    response = client.get("/api/v1/calendar/events")

    assert response.status_code == 500
    assert (
        "Wystąpił błąd podczas pobierania wydarzeń z kalendarza"
        in response.json()["detail"]
    )


@pytest.mark.parametrize(
    "case", ["success", "stale", "wrong_title", "pending", "empty_id", "failure"]
)
def test_calendar_api_requires_a_receipt_bound_to_current_execution(
    client, mock_calendar_skill, monkeypatch, case
):
    from dataclasses import replace
    from uuid import uuid4

    from venom_core.services.calendar_execution import (
        CalendarExecution,
        CalendarReceipt,
    )

    monkeypatch.setattr(
        calendar_routes.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", True
    )
    observed = []

    def execute(operation):
        observed.append(operation)
        receipt = CalendarReceipt(operation, "event-42", None)
        if case == "stale":
            receipt = replace(receipt, request=replace(operation, request_id=uuid4()))
        if case == "wrong_title":
            receipt = replace(receipt, request=replace(operation, title="Inne"))
        if case == "pending":
            receipt = replace(receipt, status="pending")
        if case == "empty_id":
            receipt = replace(receipt, event_id="")
        return CalendarExecution(
            "✅ Zaplanowano", receipt if case != "failure" else None
        )

    mock_calendar_skill.schedule_verified_task.side_effect = execute
    request = {
        "title": "Odprawa",
        "start_time": "2026-11-20T15:00:00+01:00",
        "duration_minutes": 30,
        "description": "Zespół",
    }
    for _ in range(2):
        response = client.post("/api/v1/calendar/event", json=request)
        assert response.status_code == 201
        result = response.json()
        if case == "success":
            assert result["status"] == "success"
            assert result["event_id"] == "event-42"
        else:
            assert result["status"] == "error"
            assert result["event_id"] is None
            assert "✅" not in result["message"]
    assert observed[0].request_id != observed[1].request_id
    assert (observed[0].title, observed[0].duration_minutes) == ("Odprawa", 30)
    mock_calendar_skill.schedule_task.assert_not_called()


def test_calendar_api_reuses_the_submission_key_for_an_unconfirmed_write(
    client, mock_calendar_skill, monkeypatch
):
    from uuid import uuid4

    from venom_core.services.calendar_execution import CalendarExecution

    monkeypatch.setattr(
        calendar_routes.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", True
    )
    mock_calendar_skill.schedule_verified_task.return_value = CalendarExecution(
        "Parametry niepotwierdzone", unconfirmed_event_id="provider-event"
    )
    key = uuid4()
    request = {"title": "Odprawa", "start_time": "2026-11-20T15:00:00+01:00"}
    for _ in range(2):
        response = client.post(
            "/api/v1/calendar/event",
            json=request,
            headers={"Idempotency-Key": str(key)},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "unconfirmed"
        assert response.json()["event_id"] == "provider-event"
    calls = mock_calendar_skill.schedule_verified_task.call_args_list
    assert len(calls) == 2
    assert all(
        call.args[0].request_id == key and call.args[0].idempotent for call in calls
    )
