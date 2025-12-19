"""Moduł: google_calendar_skill - Skill do integracji z Google Calendar (Safe Layering)."""

import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# OAuth2 scopes - minimal required permissions
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", 
          "https://www.googleapis.com/auth/calendar.events"]

# Limity dla bezpieczeństwa
MAX_EVENTS_RESULTS = 20


class GoogleCalendarSkill:
    """
    Skill do integracji z Google Calendar - Safe Layering Model.
    
    Architektura:
    - READ-ONLY z głównego kalendarza (primary) - sprawdzanie dostępności
    - WRITE-ONLY do kalendarza Venoma - planowanie zadań i bloków pracy
    - Graceful degradation - brak credentials nie powoduje crashu
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
        venom_calendar_id: Optional[str] = None,
    ):
        """
        Inicjalizacja GoogleCalendarSkill.

        Args:
            credentials_path: Ścieżka do pliku OAuth2 credentials (opcjonalnie)
            token_path: Ścieżka do pliku token (opcjonalnie)
            venom_calendar_id: ID kalendarza Venoma (opcjonalnie)
        """
        self.credentials_path = credentials_path or SETTINGS.GOOGLE_CALENDAR_CREDENTIALS_PATH
        self.token_path = token_path or SETTINGS.GOOGLE_CALENDAR_TOKEN_PATH
        self.venom_calendar_id = venom_calendar_id or SETTINGS.VENOM_CALENDAR_ID
        
        self.service = None
        self.credentials_available = False
        
        # Próba inicjalizacji - graceful degradation
        try:
            self._initialize_service()
            self.credentials_available = True
            logger.info("GoogleCalendarSkill zainicjalizowany pomyślnie")
        except FileNotFoundError:
            logger.warning(
                f"GoogleCalendarSkill: Brak pliku credentials ({self.credentials_path}). "
                "Skill nie jest aktywny - graceful degradation."
            )
        except Exception as e:
            logger.warning(
                f"GoogleCalendarSkill: Nie udało się zainicjalizować: {e}. "
                "Skill nie jest aktywny - graceful degradation."
            )

    def _initialize_service(self):
        """
        Inicjalizuje połączenie z Google Calendar API przez OAuth2.
        
        Raises:
            FileNotFoundError: Jeśli plik credentials nie istnieje
            Exception: Inne błędy inicjalizacji
        """
        # Sprawdź czy plik credentials istnieje
        if not Path(self.credentials_path).exists():
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
        
        creds = None
        
        # Załaduj token jeśli istnieje
        if Path(self.token_path).exists():
            try:
                with open(self.token_path, "rb") as token_file:
                    creds = pickle.load(token_file)
                logger.info("Załadowano istniejący token OAuth2")
            except Exception as e:
                logger.warning(f"Nie udało się załadować tokenu: {e}")
        
        # Jeśli brak ważnych credentials, wykonaj OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Odświeżono token OAuth2")
                except Exception as e:
                    logger.warning(f"Nie udało się odświeżyć tokenu: {e}")
                    creds = None
            
            if not creds:
                # Rozpocznij OAuth flow
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Przeprowadzono autoryzację OAuth2")
            
            # Zapisz token dla następnych uruchomień
            try:
                # Upewnij się że katalog istnieje
                Path(self.token_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, "wb") as token_file:
                    pickle.dump(creds, token_file)
                logger.info(f"Zapisano token OAuth2 do {self.token_path}")
            except Exception as e:
                logger.warning(f"Nie udało się zapisać tokenu: {e}")
        
        # Stwórz serwis Google Calendar API
        self.service = build("calendar", "v3", credentials=creds)
        logger.info("Połączono z Google Calendar API")

    @kernel_function(
        name="read_agenda",
        description="Odczytuje agendę/dostępność z głównego kalendarza użytkownika (READ-ONLY). Zwraca listę wydarzeń w określonym oknie czasowym. Użyj gdy użytkownik pyta o plan dnia lub dostępność.",
    )
    def read_agenda(
        self,
        time_min: Annotated[
            str, "Start okna czasowego (ISO format lub 'now', np. '2024-01-15T09:00:00Z')"
        ] = "now",
        hours: Annotated[int, "Liczba godzin do przodu od time_min"] = 24,
    ) -> str:
        """
        Odczytuje wydarzenia z głównego kalendarza (primary).
        
        READ-ONLY operation - nie modyfikuje kalendarza użytkownika.
        
        Args:
            time_min: Start okna czasowego (ISO format lub 'now')
            hours: Liczba godzin do przodu
            
        Returns:
            Sformatowana lista wydarzeń lub komunikat o błędzie
        """
        if not self.credentials_available:
            return "❌ Google Calendar nie jest skonfigurowany. Brak dostępu do kalendarza."
        
        logger.info(f"GoogleCalendarSkill: read_agenda (time_min={time_min}, hours={hours})")
        
        try:
            # Oblicz okno czasowe
            if time_min == "now":
                start_time = datetime.utcnow()
            else:
                start_time = datetime.fromisoformat(time_min.replace("Z", "+00:00"))
            
            end_time = start_time + timedelta(hours=hours)
            
            # Pobierz wydarzenia z primary calendar (READ-ONLY)
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_time.isoformat() + "Z",
                    timeMax=end_time.isoformat() + "Z",
                    maxResults=MAX_EVENTS_RESULTS,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            
            events = events_result.get("items", [])
            
            if not events:
                return f"📅 Brak wydarzeń w kalendarzu od {start_time.strftime('%Y-%m-%d %H:%M')} przez następne {hours}h"
            
            # Formatuj wyniki
            output = f"📅 Agenda: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}\n\n"
            
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                summary = event.get("summary", "(Brak tytułu)")
                
                # Parsuj czas
                try:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    time_str = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                except:
                    time_str = start
                
                output += f"🕒 {time_str}\n"
                output += f"   {summary}\n\n"
            
            logger.info(f"GoogleCalendarSkill: zwrócono {len(events)} wydarzeń")
            return output.strip()
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            return f"❌ Błąd Google Calendar API: {str(e)}"
        except Exception as e:
            logger.error(f"Błąd podczas odczytywania agendy: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    @kernel_function(
        name="schedule_task",
        description="Planuje zadanie/blok pracy w kalendarzu Venoma (WRITE-ONLY do Venom Work). Tworzy wydarzenie tylko w dedykowanym kalendarzu roboczym, NIE w głównym kalendarzu użytkownika. Użyj gdy użytkownik chce zaplanować zadanie, time-blocking lub przypomnienie.",
    )
    def schedule_task(
        self,
        title: Annotated[str, "Tytuł zadania/wydarzenia"],
        start_time: Annotated[
            str, "Czas startu w formacie ISO (np. '2024-01-15T16:00:00')"
        ],
        duration_minutes: Annotated[int, "Czas trwania w minutach"] = 60,
        description: Annotated[str, "Opcjonalny opis zadania"] = "",
    ) -> str:
        """
        Tworzy wydarzenie w kalendarzu Venoma.
        
        WRITE-ONLY operation - zapisuje TYLKO do kalendarza Venoma, NIE do primary.
        Safe Layering: użytkownik zachowuje kontrolę - może ukryć kalendarz Venoma.
        
        Args:
            title: Tytuł wydarzenia
            start_time: Czas startu (ISO format)
            duration_minutes: Czas trwania w minutach
            description: Opcjonalny opis
            
        Returns:
            Potwierdzenie utworzenia lub komunikat o błędzie
        """
        if not self.credentials_available:
            return "❌ Google Calendar nie jest skonfigurowany. Nie można zaplanować zadania."
        
        logger.info(
            f"GoogleCalendarSkill: schedule_task (title='{title}', start={start_time}, duration={duration_minutes}min)"
        )
        
        try:
            # Parsuj czas startu
            start_dt = datetime.fromisoformat(start_time)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            # Przygotuj wydarzenie
            event = {
                "summary": title,
                "description": description,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": "UTC",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 10},
                    ],
                },
            }
            
            # WRITE-ONLY do kalendarza Venoma (NIE do primary)
            created_event = (
                self.service.events()
                .insert(calendarId=self.venom_calendar_id, body=event)
                .execute()
            )
            
            event_link = created_event.get("htmlLink")
            
            output = f"✅ Zaplanowano zadanie w kalendarzu Venoma:\n"
            output += f"📌 Tytuł: {title}\n"
            output += f"🕒 Czas: {start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}\n"
            output += f"⏱️  Czas trwania: {duration_minutes} minut\n"
            if description:
                output += f"📝 Opis: {description}\n"
            output += f"🔗 Link: {event_link}\n"
            output += f"\n💡 Wydarzenie zostało utworzone w kalendarzu Venoma (nie w głównym kalendarzu)"
            
            logger.info(f"GoogleCalendarSkill: utworzono wydarzenie: {created_event.get('id')}")
            return output
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            return f"❌ Błąd Google Calendar API: {str(e)}"
        except ValueError as e:
            logger.error(f"Nieprawidłowy format czasu: {e}")
            return f"❌ Nieprawidłowy format czasu. Użyj formatu ISO: YYYY-MM-DDTHH:MM:SS"
        except Exception as e:
            logger.error(f"Błąd podczas planowania zadania: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    def close(self):
        """Zamknięcie połączenia (cleanup)."""
        if self.service:
            self.service.close()
            logger.info("GoogleCalendarSkill: zamknięto połączenie")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
