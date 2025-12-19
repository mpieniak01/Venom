"""Moduł: assistant_skill - Podstawowe umiejętności asystenta."""

import asyncio
from datetime import datetime
from typing import Annotated, Optional

import aiohttp
from semantic_kernel.functions import kernel_function

from venom_core.core.service_monitor import ServiceHealthMonitor, ServiceRegistry
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class AssistantSkill:
    """
    Skill z podstawowymi umiejętnościami asystenta.

    Zapewnia podstawowe funkcje, które powinny być zawsze dostępne:
    - Pobieranie aktualnego czasu
    - Sprawdzanie pogody
    - Sprawdzanie statusu usług systemowych
    """

    def __init__(
        self,
        service_registry: Optional[ServiceRegistry] = None,
        weather_api_key: Optional[str] = None,
    ):
        """
        Inicjalizacja AssistantSkill.

        Args:
            service_registry: Rejestr usług (utworzony automatycznie jeśli None)
            weather_api_key: Klucz API dla serwisu pogody (opcjonalny)
        """
        self.service_registry = service_registry or ServiceRegistry()
        self.service_monitor = ServiceHealthMonitor(self.service_registry)
        self.weather_api_key = weather_api_key
        logger.info("AssistantSkill zainicjalizowany")

    @kernel_function(
        name="get_current_time",
        description="Zwraca aktualny czas lokalny w formacie czytelnym dla człowieka.",
    )
    async def get_current_time(
        self,
        format_type: Annotated[
            str, "Format czasu: 'short' (HH:MM), 'full' (pełna data i czas)"
        ] = "full",
    ) -> str:
        """
        Zwraca aktualny czas lokalny.

        Args:
            format_type: Format odpowiedzi ('short' lub 'full')

        Returns:
            Sformatowany czas lokalny
        """
        try:
            now = datetime.now()

            if format_type == "short":
                time_str = now.strftime("%H:%M")
                return f"🕐 Aktualna godzina: {time_str}"
            else:
                # Pełny format z datą
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M:%S")
                day_name = now.strftime("%A")
                # Tłumaczenie nazw dni na polski
                day_names = {
                    "Monday": "Poniedziałek",
                    "Tuesday": "Wtorek",
                    "Wednesday": "Środa",
                    "Thursday": "Czwartek",
                    "Friday": "Piątek",
                    "Saturday": "Sobota",
                    "Sunday": "Niedziela",
                }
                day_name_pl = day_names.get(day_name, day_name)

                return (
                    f"📅 {day_name_pl}, {date_str}\n"
                    f"🕐 Godzina: {time_str}\n"
                    f"Strefa czasowa: {now.astimezone().tzname()}"
                )

        except Exception as e:
            logger.error(f"Błąd podczas pobierania czasu: {e}")
            return f"✗ Błąd podczas pobierania czasu: {e}"

    @kernel_function(
        name="get_weather",
        description="Zwraca aktualną pogodę dla podanej lokalizacji. Wymaga połączenia internetowego.",
    )
    async def get_weather(
        self,
        location: Annotated[
            str, "Nazwa miasta lub lokalizacji (np. 'Warszawa', 'London')"
        ],
        units: Annotated[
            str, "Jednostki: 'metric' (Celsjusz) lub 'imperial' (Fahrenheit)"
        ] = "metric",
    ) -> str:
        """
        Zwraca aktualną pogodę dla podanej lokalizacji.

        Używa darmowego API wttr.in, które nie wymaga klucza API.

        Args:
            location: Nazwa miasta
            units: System jednostek

        Returns:
            Informacje o pogodzie
        """
        try:
            # Używamy wttr.in - darmowe API bez wymagania klucza
            # Format: ?format=3 daje zwięzły output
            url = f"https://wttr.in/{location}?format=j1"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return f"✗ Nie udało się pobrać danych pogodowych dla '{location}'. Sprawdź nazwę lokalizacji."

                    data = await response.json()

                    # Parsowanie odpowiedzi z wttr.in
                    current = data.get("current_condition", [{}])[0]
                    nearest_area = data.get("nearest_area", [{}])[0]

                    temp_c = current.get("temp_C", "N/A")
                    temp_f = current.get("temp_F", "N/A")
                    feels_like_c = current.get("FeelsLikeC", "N/A")
                    humidity = current.get("humidity", "N/A")
                    weather_desc = current.get("weatherDesc", [{}])[0].get(
                        "value", "N/A"
                    )
                    wind_speed = current.get("windspeedKmph", "N/A")
                    wind_dir = current.get("winddir16Point", "N/A")

                    area_name = nearest_area.get("areaName", [{}])[0].get(
                        "value", location
                    )
                    country = nearest_area.get("country", [{}])[0].get("value", "")

                    if units == "metric":
                        temp_display = f"{temp_c}°C (odczuwalna: {feels_like_c}°C)"
                    else:
                        temp_display = f"{temp_f}°F"

                    return (
                        f"🌤️  Pogoda dla: {area_name}, {country}\n\n"
                        f"🌡️  Temperatura: {temp_display}\n"
                        f"☁️  Warunki: {weather_desc}\n"
                        f"💧 Wilgotność: {humidity}%\n"
                        f"💨 Wiatr: {wind_speed} km/h ({wind_dir})"
                    )

        except asyncio.TimeoutError:
            logger.error("Timeout podczas pobierania danych pogodowych")
            return "✗ Przekroczono limit czasu podczas pobierania danych pogodowych."
        except Exception as e:
            logger.error(f"Błąd podczas pobierania pogody: {e}")
            return f"✗ Błąd podczas pobierania pogody: {e}"

    @kernel_function(
        name="check_services",
        description="Sprawdza i zwraca status uruchomionych usług systemowych (LLM, Docker, itp.).",
    )
    async def check_services(
        self,
        detailed: Annotated[bool, "Czy pokazać szczegółowe informacje"] = False,
    ) -> str:
        """
        Sprawdza status usług systemowych.

        Args:
            detailed: Czy pokazać szczegółowe informacje o każdej usłudze

        Returns:
            Podsumowanie statusu usług
        """
        try:
            # Sprawdź wszystkie usługi
            await self.service_monitor.check_health()

            services = self.service_registry.get_all_services()

            if not services:
                return "⚠️  Brak zarejestrowanych usług do monitorowania."

            # Zlicz statusy
            online_count = sum(1 for s in services if s.status.value == "online")
            offline_count = sum(1 for s in services if s.status.value == "offline")
            degraded_count = sum(1 for s in services if s.status.value == "degraded")
            unknown_count = sum(1 for s in services if s.status.value == "unknown")

            total = len(services)

            # Podstawowe podsumowanie
            result = "🔍 Status usług systemowych\n\n"
            result += f"✅ Online: {online_count}/{total}\n"

            if offline_count > 0:
                result += f"❌ Offline: {offline_count}/{total}\n"
            if degraded_count > 0:
                result += f"⚠️  Degraded: {degraded_count}/{total}\n"
            if unknown_count > 0:
                result += f"❓ Unknown: {unknown_count}/{total}\n"

            # Sprawdź usługi krytyczne
            critical_services = self.service_registry.get_critical_services()
            critical_offline = [
                s for s in critical_services if s.status.value == "offline"
            ]

            if critical_offline:
                result += "\n⚠️  UWAGA: Krytyczne usługi offline:\n"
                for service in critical_offline:
                    result += f"  • {service.name}\n"

            # Szczegóły jeśli wymagane
            if detailed:
                result += "\n📋 Szczegóły usług:\n\n"
                for service in services:
                    status_icon = {
                        "online": "✅",
                        "offline": "❌",
                        "degraded": "⚠️",
                        "unknown": "❓",
                    }.get(service.status.value, "❓")

                    result += f"{status_icon} {service.name}\n"
                    result += f"   Typ: {service.service_type}\n"

                    if service.endpoint:
                        result += f"   Endpoint: {service.endpoint}\n"

                    if service.status.value == "online" and service.latency_ms > 0:
                        result += f"   Latencja: {service.latency_ms:.2f}ms\n"

                    if service.error_message:
                        result += f"   Błąd: {service.error_message}\n"

                    result += "\n"

            return result

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania usług: {e}")
            return f"✗ Błąd podczas sprawdzania usług: {e}"
