"""Schemas for calendar API endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


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

    title: str = Field(
        ..., description="Tytuł wydarzenia (summary w terminologii Google Calendar)"
    )
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
