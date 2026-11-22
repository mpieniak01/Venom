"""Moduł: routes/calendar - Endpointy API dla kalendarza i synchronizacji Google."""

from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from venom_core.api.schemas.calendar import (
    CalendarEvent,
    CreateEventRequest,
    CreateEventResponse,
    EventsResponse,
)
from venom_core.services.calendar_execution import CalendarCreate
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


# Dependency - będzie ustawione w main.py
_google_calendar_skill = None


def set_dependencies(google_calendar_skill):
    """Ustaw zależności dla routera."""
    global _google_calendar_skill
    _google_calendar_skill = google_calendar_skill


def _ensure_calendar_skill():
    """Sprawdź czy GoogleCalendarSkill jest dostępny."""
    if (
        _google_calendar_skill is None
        or not _google_calendar_skill.credentials_available
    ):
        raise HTTPException(
            status_code=503,
            detail="Google Calendar nie jest skonfigurowany. Sprawdź konfigurację ENABLE_GOOGLE_CALENDAR.",
        )
    return _google_calendar_skill


@router.get(
    "/events",
    response_model=EventsResponse,
    responses={
        503: {"description": "Google Calendar nie jest skonfigurowany"},
        500: {"description": "Błąd wewnętrzny podczas pobierania wydarzeń"},
    },
)
def get_calendar_events(
    time_min: str = "now",
    hours: int = 24,
):
    """
    Pobiera listę wydarzeń z kalendarza Google.

    Args:
        time_min: Start okna czasowego (ISO format lub 'now')
        hours: Liczba godzin do przodu od time_min

    Returns:
        Lista wydarzeń z kalendarza

    Raises:
        HTTPException: 503 jeśli Google Calendar nie jest skonfigurowany

    Note:
        Obecnie GoogleCalendarSkill zwraca sformatowany tekst.
        W przyszłych wersjach skill zostanie rozszerzony o zwracanie structured data.
        Na razie zwracamy pustą listę lub informację tekstową jako opis.
    """
    try:
        skill = _ensure_calendar_skill()

        # Wywołaj skill do pobrania agendy
        result_text = skill.read_agenda(time_min=time_min, hours=hours)

        logger.info(f"Pobrano wydarzenia z Google Calendar: {len(result_text)} znaków")

        # Oblicz czasy
        if time_min == "now":
            start_time = datetime.now(timezone.utc)
        else:
            start_time = datetime.fromisoformat(time_min.replace("Z", "+00:00"))

        end_time = start_time + timedelta(hours=hours)

        # Parse result - obecnie skill zwraca sformatowany string
        events: List[CalendarEvent] = []
        if "Brak wydarzeń" not in result_text and "❌" not in result_text:
            # Zwróć informację tekstową - UI może wyświetlić jako opis
            # W przyszłości: skill zwróci strukturalne dane i parsujemy je tutaj
            logger.info(
                "GoogleCalendarSkill zwrócił tekst - zwracamy jako informację opisową"
            )

        return EventsResponse(
            events=events,
            total=len(events),
            time_min=start_time.isoformat(),
            time_max=end_time.isoformat(),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Błąd podczas pobierania wydarzeń")
        raise HTTPException(
            status_code=500,
            detail="Wystąpił błąd podczas pobierania wydarzeń z kalendarza.",
        )


def _create_verified_event(
    skill, request: CreateEventRequest, key: str | None
) -> CreateEventResponse:
    try:
        request_id = uuid4() if key is None else UUID(key)
    except ValueError as error:
        raise HTTPException(400, "Invalid Idempotency-Key UUID.") from error
    operation = CalendarCreate(
        request_id,
        request.title,
        request.start_time,
        request.duration_minutes,
        request.description,
        idempotent=key is not None,
    )
    result = skill.schedule_verified_task(operation)
    receipt = result.confirmed(operation)
    if receipt is not None:
        return CreateEventResponse(
            status="success",
            message=result.message,
            event_id=receipt.event_id,
            event_link=receipt.event_link,
        )
    if result.unconfirmed_event_id:
        return CreateEventResponse(
            status="unconfirmed",
            message=result.message,
            event_id=result.unconfirmed_event_id,
        )
    return CreateEventResponse(
        status="error",
        message="Wpis do kalendarza nie został potwierdzony.",
    )


@router.post(
    "/event",
    response_model=CreateEventResponse,
    status_code=201,
    responses={
        503: {"description": "Google Calendar nie jest skonfigurowany"},
        400: {"description": "Nieprawidłowe dane wejściowe"},
        500: {"description": "Błąd wewnętrzny podczas tworzenia wydarzenia"},
    },
)
def create_calendar_event(request: CreateEventRequest, http_request: Request):
    """
    Tworzy nowe wydarzenie w kalendarzu Venoma.

    Args:
        request: Dane nowego wydarzenia

    Returns:
        Potwierdzenie utworzenia wydarzenia

    Raises:
        HTTPException: 503 jeśli Google Calendar nie jest skonfigurowany,
                      400 przy błędnych danych
    """
    try:
        skill = _ensure_calendar_skill()

        # Walidacja danych
        if not request.title or not request.title.strip():
            raise HTTPException(status_code=400, detail="Tytuł nie może być pusty")

        if request.duration_minutes <= 0:
            raise HTTPException(
                status_code=400, detail="Czas trwania musi być większy od 0"
            )

        return _create_verified_event(
            skill, request, http_request.headers.get("Idempotency-Key")
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Błąd podczas tworzenia wydarzenia")
        raise HTTPException(
            status_code=500,
            detail="Wystąpił nieoczekiwany błąd podczas tworzenia wydarzenia.",
        )
