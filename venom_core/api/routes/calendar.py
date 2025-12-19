"""Moduł: routes/calendar - Endpointy API dla kalendarza i synchronizacji Google."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


# Modele
class CalendarEvent(BaseModel):
    """Model wydarzenia w kalendarzu."""

    id: Optional[str] = None
    summary: str = Field(..., description="Tytuł wydarzenia")
    description: Optional[str] = Field(None, description="Opis wydarzenia")
    start: str = Field(..., description="Data i czas rozpoczęcia (ISO format)")
    end: str = Field(..., description="Data i czas zakończenia (ISO format)")
    location: Optional[str] = None
    status: Optional[str] = None


class EventsResponse(BaseModel):
    """Model odpowiedzi z listą wydarzeń."""

    events: list[CalendarEvent]
    total: int
    time_min: str
    time_max: str


class CreateEventRequest(BaseModel):
    """Model żądania utworzenia wydarzenia."""

    title: str = Field(..., description="Tytuł wydarzenia")
    start_time: str = Field(
        ..., description="Czas startu w formacie ISO (np. '2024-01-15T16:00:00')"
    )
    duration_minutes: int = Field(60, description="Czas trwania w minutach")
    description: str = Field("", description="Opcjonalny opis wydarzenia")


class CreateEventResponse(BaseModel):
    """Model odpowiedzi po utworzeniu wydarzenia."""

    status: str
    message: str
    event_id: Optional[str] = None
    event_link: Optional[str] = None


# Dependency - będzie ustawione w main.py
_google_calendar_skill = None


def set_dependencies(google_calendar_skill):
    """Ustaw zależności dla routera."""
    global _google_calendar_skill
    _google_calendar_skill = google_calendar_skill


def _ensure_calendar_skill():
    """Sprawdź czy GoogleCalendarSkill jest dostępny."""
    global _google_calendar_skill
    if _google_calendar_skill is None or not _google_calendar_skill.credentials_available:
        raise HTTPException(
            status_code=503,
            detail="Google Calendar nie jest skonfigurowany. Sprawdź konfigurację ENABLE_GOOGLE_CALENDAR.",
        )
    return _google_calendar_skill


@router.get("/events", response_model=EventsResponse)
async def get_calendar_events(
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
    """
    try:
        skill = _ensure_calendar_skill()

        # Wywołaj skill do pobrania agendy
        result_text = skill.read_agenda(time_min=time_min, hours=hours)

        # Parse result (obecnie skill zwraca sformatowany string)
        # W przyszłości można rozszerzyć skill aby zwracał structured data
        logger.info(f"Pobrano wydarzenia z Google Calendar: {len(result_text)} znaków")

        # Dla uproszczenia zwracamy teraz pustą listę strukturalną
        # TODO: Rozszerzyć GoogleCalendarSkill aby zwracał structured data
        if "Brak wydarzeń" in result_text or "❌" in result_text:
            events = []
        else:
            # Tymczasowo zwracamy informację tekstową jako jedno "wydarzenie"
            events = [
                CalendarEvent(
                    id="summary",
                    summary="Wydarzenia z Google Calendar",
                    description=result_text,
                    start=datetime.now(timezone.utc).isoformat(),
                    end=datetime.now(timezone.utc).isoformat(),
                )
            ]

        # Oblicz czasy
        if time_min == "now":
            start_time = datetime.now(timezone.utc)
        else:
            start_time = datetime.fromisoformat(time_min.replace("Z", "+00:00"))

        from datetime import timedelta

        end_time = start_time + timedelta(hours=hours)

        return EventsResponse(
            events=events,
            total=len(events),
            time_min=start_time.isoformat(),
            time_max=end_time.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania wydarzeń: {e}")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas pobierania wydarzeń: {str(e)}"
        )


@router.post("/event", response_model=CreateEventResponse, status_code=201)
async def create_calendar_event(request: CreateEventRequest):
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

        # Wywołaj skill do utworzenia wydarzenia
        result_text = skill.schedule_task(
            title=request.title,
            start_time=request.start_time,
            duration_minutes=request.duration_minutes,
            description=request.description,
        )

        logger.info(f"Utworzono wydarzenie: {request.title}")

        # Parse result
        success = "✅" in result_text and "Zaplanowano" in result_text
        event_link = None

        # Wyciągnij link z wyniku
        if "🔗 Link:" in result_text:
            parts = result_text.split("🔗 Link:")
            if len(parts) > 1:
                link_line = parts[1].strip().split("\n")[0].strip()
                event_link = link_line

        return CreateEventResponse(
            status="success" if success else "error",
            message=result_text,
            event_link=event_link,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas tworzenia wydarzenia: {e}")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas tworzenia wydarzenia: {str(e)}"
        )
