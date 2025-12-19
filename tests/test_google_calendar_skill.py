"""Testy jednostkowe dla GoogleCalendarSkill."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from venom_core.execution.skills.google_calendar_skill import GoogleCalendarSkill


@pytest.fixture
def mock_google_service():
    """Fixture dla zmockowanego Google Calendar API service."""
    mock_service = MagicMock()
    return mock_service


@pytest.fixture
def mock_credentials():
    """Fixture dla zmockowanych credentials."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    return mock_creds


@pytest.fixture
def calendar_skill_no_credentials():
    """Fixture dla GoogleCalendarSkill bez credentials (graceful degradation)."""
    with patch("venom_core.execution.skills.google_calendar_skill.Path") as mock_path:
        # Symuluj brak pliku credentials
        mock_path.return_value.exists.return_value = False
        skill = GoogleCalendarSkill()
        return skill


@pytest.fixture
def calendar_skill_with_mock_service(mock_google_service, mock_credentials):
    """Fixture dla GoogleCalendarSkill z mockowanym serwisem."""
    with (
        patch("venom_core.execution.skills.google_calendar_skill.Path") as mock_path,
        patch("venom_core.execution.skills.google_calendar_skill.build") as mock_build,
        patch(
            "venom_core.execution.skills.google_calendar_skill.pickle"
        ) as mock_pickle,
    ):
        # Symuluj że credentials istnieją
        mock_path.return_value.exists.return_value = True

        # Mock pickle.load zwraca credentials
        mock_pickle.load.return_value = mock_credentials

        # Mock build zwraca mock service
        mock_build.return_value = mock_google_service

        # Utwórz skill z dedykowanym kalendarzem Venoma (nie primary)
        skill = GoogleCalendarSkill(venom_calendar_id="venom_work_calendar")
        skill.service = mock_google_service
        skill.credentials_available = True

        return skill


def test_calendar_skill_initialization_without_credentials(
    calendar_skill_no_credentials,
):
    """Test inicjalizacji GoogleCalendarSkill bez credentials - graceful degradation."""
    assert calendar_skill_no_credentials.service is None
    assert calendar_skill_no_credentials.credentials_available is False


def test_calendar_skill_initialization_with_credentials(
    calendar_skill_with_mock_service,
):
    """Test inicjalizacji GoogleCalendarSkill z credentials."""
    assert calendar_skill_with_mock_service.service is not None
    assert calendar_skill_with_mock_service.credentials_available is True


def test_read_agenda_without_credentials(calendar_skill_no_credentials):
    """Test read_agenda bez credentials - powinna zwrócić komunikat o błędzie."""
    result = calendar_skill_no_credentials.read_agenda()
    assert "nie jest skonfigurowany" in result.lower()


def test_read_agenda_success(calendar_skill_with_mock_service):
    """Test read_agenda - sukces z mockowanymi wydarzeniami."""
    # Mock wydarzeń
    now = datetime.now(timezone.utc)
    event1 = {
        "summary": "Spotkanie 1",
        "start": {"dateTime": now.isoformat() + "Z"},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat() + "Z"},
    }
    event2 = {
        "summary": "Spotkanie 2",
        "start": {"dateTime": (now + timedelta(hours=2)).isoformat() + "Z"},
        "end": {"dateTime": (now + timedelta(hours=3)).isoformat() + "Z"},
    }

    # Konfiguruj mock API
    mock_events = Mock()
    mock_events.list.return_value.execute.return_value = {"items": [event1, event2]}
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    # Wywołaj read_agenda
    result = calendar_skill_with_mock_service.read_agenda(time_min="now", hours=24)

    # Asercje
    assert "Agenda" in result
    assert "Spotkanie 1" in result
    assert "Spotkanie 2" in result
    mock_events.list.assert_called_once()

    # Sprawdź że używa primary calendar (READ-ONLY)
    call_args = mock_events.list.call_args
    assert call_args[1]["calendarId"] == "primary"


def test_read_agenda_no_events(calendar_skill_with_mock_service):
    """Test read_agenda - brak wydarzeń."""
    # Mock pustej listy
    mock_events = Mock()
    mock_events.list.return_value.execute.return_value = {"items": []}
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    result = calendar_skill_with_mock_service.read_agenda()

    assert "Brak wydarzeń" in result


def test_schedule_task_without_credentials(calendar_skill_no_credentials):
    """Test schedule_task bez credentials - powinna zwrócić komunikat o błędzie."""
    result = calendar_skill_no_credentials.schedule_task(
        title="Test Task", start_time="2024-01-15T16:00:00", duration_minutes=60
    )
    assert "nie jest skonfigurowany" in result.lower()


def test_schedule_task_success(calendar_skill_with_mock_service):
    """Test schedule_task - sukces."""
    # Mock utworzonego wydarzenia
    created_event = {
        "id": "test_event_123",
        "htmlLink": "https://calendar.google.com/event?id=test_event_123",
        "summary": "Test Task",
    }

    mock_events = Mock()
    mock_events.insert.return_value.execute.return_value = created_event
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    # Wywołaj schedule_task
    start_time = "2024-01-15T16:00:00"
    result = calendar_skill_with_mock_service.schedule_task(
        title="Test Task",
        start_time=start_time,
        duration_minutes=90,
        description="Test description",
    )

    # Asercje
    assert "Zaplanowano zadanie" in result
    assert "Test Task" in result
    assert "90 minut" in result
    assert "kalendarzu Venoma" in result
    assert created_event["htmlLink"] in result

    # Sprawdź że używa venom calendar ID (WRITE-ONLY)
    call_args = mock_events.insert.call_args
    assert (
        call_args[1]["calendarId"] == calendar_skill_with_mock_service.venom_calendar_id
    )

    # Sprawdź strukturę wydarzenia
    event_body = call_args[1]["body"]
    assert event_body["summary"] == "Test Task"
    assert event_body["description"] == "Test description"
    assert "reminders" in event_body


def test_schedule_task_invalid_time_format(calendar_skill_with_mock_service):
    """Test schedule_task z nieprawidłowym formatem czasu."""
    result = calendar_skill_with_mock_service.schedule_task(
        title="Test Task", start_time="invalid-time-format", duration_minutes=60
    )

    assert "Nieprawidłowy format czasu" in result or "błąd" in result.lower()


def test_read_agenda_api_error(calendar_skill_with_mock_service):
    """Test read_agenda z błędem API."""
    from googleapiclient.errors import HttpError

    # Mock błędu API
    mock_events = Mock()
    mock_error = HttpError(Mock(status=403), b"Forbidden")
    mock_events.list.return_value.execute.side_effect = mock_error
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    result = calendar_skill_with_mock_service.read_agenda()

    assert "Błąd" in result or "błąd" in result.lower()


def test_schedule_task_api_error(calendar_skill_with_mock_service):
    """Test schedule_task z błędem API."""
    from googleapiclient.errors import HttpError

    # Mock błędu API
    mock_events = Mock()
    mock_error = HttpError(Mock(status=403), b"Forbidden")
    mock_events.insert.return_value.execute.side_effect = mock_error
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    result = calendar_skill_with_mock_service.schedule_task(
        title="Test Task", start_time="2024-01-15T16:00:00", duration_minutes=60
    )

    assert "Błąd" in result or "błąd" in result.lower()


def test_safe_layering_read_only_primary(calendar_skill_with_mock_service):
    """Test Safe Layering: read_agenda używa primary calendar (READ-ONLY)."""
    mock_events = Mock()
    mock_events.list.return_value.execute.return_value = {"items": []}
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    calendar_skill_with_mock_service.read_agenda()

    # Sprawdź że używa primary calendar
    call_args = mock_events.list.call_args
    assert call_args[1]["calendarId"] == "primary"


def test_safe_layering_write_only_venom(calendar_skill_with_mock_service):
    """Test Safe Layering: schedule_task używa venom calendar (WRITE-ONLY)."""
    mock_events = Mock()
    mock_events.insert.return_value.execute.return_value = {
        "id": "test_id",
        "htmlLink": "https://test.link",
    }
    calendar_skill_with_mock_service.service.events.return_value = mock_events

    calendar_skill_with_mock_service.schedule_task(
        title="Test", start_time="2024-01-15T16:00:00", duration_minutes=60
    )

    # Sprawdź że NIE używa primary calendar
    call_args = mock_events.insert.call_args
    assert call_args[1]["calendarId"] != "primary"
    assert (
        call_args[1]["calendarId"] == calendar_skill_with_mock_service.venom_calendar_id
    )


def test_primary_calendar_warning(mock_google_service, mock_credentials):
    """Test że ostrzeżenie jest emitowane gdy venom_calendar_id='primary'."""
    with (
        patch("venom_core.execution.skills.google_calendar_skill.Path") as mock_path,
        patch("venom_core.execution.skills.google_calendar_skill.build") as mock_build,
        patch(
            "venom_core.execution.skills.google_calendar_skill.pickle"
        ) as mock_pickle,
        patch(
            "venom_core.execution.skills.google_calendar_skill.logger"
        ) as mock_logger,
    ):
        # Symuluj że credentials istnieją
        mock_path.return_value.exists.return_value = True

        # Mock pickle.load zwraca credentials
        mock_pickle.load.return_value = mock_credentials

        # Mock build zwraca mock service
        mock_build.return_value = mock_google_service

        # Utwórz skill z venom_calendar_id='primary' (naruszenie Safe Layering)
        GoogleCalendarSkill(venom_calendar_id="primary")

        # Sprawdź że ostrzeżenie zostało wywołane
        mock_logger.warning.assert_called()
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any(
            "VENOM_CALENDAR_ID is set to 'primary'" in str(call)
            and "violates Safe Layering" in str(call)
            for call in warning_calls
        )
