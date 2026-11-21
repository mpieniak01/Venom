"""Moduł: assistant_skill - Podstawowe umiejętności asystenta."""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Literal, Optional
from urllib.parse import quote

import httpx

from venom_core.core.service_monitor import ServiceHealthMonitor, ServiceRegistry
from venom_core.execution.agent_contracts import tool_function as kernel_function
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Słownik tłumaczeń nazw dni tygodnia (na poziomie modułu dla wydajności)
DAY_NAMES_PL = {
    "Monday": "Poniedziałek",
    "Tuesday": "Wtorek",
    "Wednesday": "Środa",
    "Thursday": "Czwartek",
    "Friday": "Piątek",
    "Saturday": "Sobota",
    "Sunday": "Niedziela",
}


WeatherFailureReason = Literal[
    "empty_location",
    "no_data",
    "missing_temperature",
    "missing_observed_location",
    "provider_http_error",
    "provider_timeout",
    "provider_transport_error",
    "provider_client_error",
    "provider_invalid_payload",
]

# IMGW's public synoptic station catalogue. Match both station identity and name.
_IMGW_STATIONS = {"kalisz": "12435"}
_IMGW_MAX_AGE = timedelta(hours=3)
_WEATHER_TEMPERATURE = re.compile(r"-?[0-9]{1,3}(?:[.,][0-9]{1,2})?")


@dataclass(frozen=True)
class WeatherObservation:
    requested_location: str
    source_url: str
    observed_location: str | None = None
    temperature_c: str | None = None
    feels_like_c: str | None = None
    failure_reason: WeatherFailureReason | None = None
    http_status: int | None = None
    details: tuple[tuple[str, str], ...] = ()
    observed_at: datetime | None = None


def imgw_station_url(location: str) -> str | None:
    station = _IMGW_STATIONS.get(location.casefold())
    return (
        f"https://danepubliczne.imgw.pl/api/data/synop/id/{station}"
        if station
        else None
    )


def imgw_observation_time(day: object, hour: object) -> datetime | None:
    if not isinstance(day, str) or type(hour) not in (int, str):
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) or not re.fullmatch(
        r"[0-9]{1,2}", str(hour)
    ):
        return None
    try:
        return datetime.fromisoformat(f"{day}T{int(hour):02}:00:00+00:00")
    except ValueError:
        return None


@dataclass(frozen=True)
class _WeatherProviderFailure:
    reason: WeatherFailureReason
    status: int | None = None

    def legacy_message(self, location: str) -> str:
        if self.reason == "provider_timeout":
            return "✗ Przekroczono limit czasu podczas pobierania danych pogodowych."
        if self.reason == "provider_transport_error":
            return "✗ Błąd połączenia z serwisem pogodowym."
        if self.reason == "provider_http_error":
            return (
                f"✗ Nie udało się pobrać danych pogodowych dla '{location}'. "
                "Sprawdź nazwę lokalizacji."
            )
        return "✗ Błąd podczas pobierania pogody."


def weather_temperature(value: object) -> str | None:
    if type(value) not in (str, int, float):
        return None
    raw = str(value).strip()
    return raw.replace(",", ".") if _WEATHER_TEMPERATURE.fullmatch(raw) else None


def _weather_area(payload: dict[str, Any]) -> str | None:
    areas = payload.get("nearest_area")
    if not isinstance(areas, list) or not areas or not isinstance(areas[0], dict):
        return None
    names = areas[0].get("areaName")
    if not isinstance(names, list) or not names or not isinstance(names[0], dict):
        return None
    return weather_area_name(names[0].get("value"))


def weather_area_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = " ".join(value.split())
    if (
        not name
        or len(name) > 120
        or not all(char.isalpha() or char in " .-'’–" for char in name)
    ):
        return None
    return name


def _weather_details(current: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    details = []
    desc = current.get("weatherDesc")
    if isinstance(desc, list) and desc and isinstance(desc[0], dict):
        if condition := weather_area_name(desc[0].get("value")):
            details.append(("Warunki", condition))
    if humidity := weather_temperature(current.get("humidity")):
        details.append(("Wilgotność", f"{humidity}%"))
    if speed := weather_temperature(current.get("windspeedKmph")):
        direction = weather_area_name(current.get("winddir16Point"))
        suffix = f" ({direction})" if direction else ""
        details.append(("Wiatr", f"{speed} km/h{suffix}"))
    return tuple(details)


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
    ):
        """
        Inicjalizacja AssistantSkill.

        Args:
            service_registry: Rejestr usług (utworzony automatycznie jeśli None)
        """
        self.service_registry = service_registry or ServiceRegistry()
        self.service_monitor = ServiceHealthMonitor(self.service_registry)
        logger.info("AssistantSkill zainicjalizowany")

    @staticmethod
    def weather_source_url(location: str) -> str:
        """Return the exact public endpoint used by this weather skill."""
        return f"https://wttr.in/{quote(location)}?format=j1"

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
                # Tłumaczenie nazwy dnia na polski
                day_name_pl = DAY_NAMES_PL.get(day_name, day_name)

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
            units = self._normalize_units(units)
            location_safe = (location or "").strip()
            if not location_safe:
                return "✗ Nazwa lokalizacji nie może być pusta."

            url = self.weather_source_url(location_safe)
            data = await self._fetch_weather_payload(url)
            if isinstance(data, _WeatherProviderFailure):
                return data.legacy_message(location_safe)

            parsed = self._parse_weather_payload(data, location_safe)
            if isinstance(parsed, str):
                return parsed
            return self._format_weather_response(parsed, units)

        except asyncio.TimeoutError:
            logger.error("Timeout podczas pobierania danych pogodowych")
            return "✗ Przekroczono limit czasu podczas pobierania danych pogodowych."
        except httpx.HTTPError as e:
            logger.error(f"Błąd połączenia podczas pobierania pogody: {e}")
            return f"✗ Błąd połączenia z serwisem pogodowym: {e}"
        except Exception as e:
            logger.error(f"Błąd podczas pobierania pogody: {e}")
            return f"✗ Błąd podczas pobierania pogody: {e}"

    @staticmethod
    def _normalize_units(units: str) -> str:
        if units in ("metric", "imperial"):
            return units
        logger.warning(f"Nieprawidłowa wartość units: '{units}'. Używam 'metric'.")
        return "metric"

    async def read_weather_observation(self, location: str) -> WeatherObservation:
        """Bind a measured temperature to the area named by the provider."""
        requested = location.strip()
        if not requested:
            return WeatherObservation(requested, "", failure_reason="empty_location")
        url = self.weather_source_url(requested)
        data = await self._fetch_weather_payload(url)
        if isinstance(data, _WeatherProviderFailure):
            return WeatherObservation(
                requested, url, failure_reason=data.reason, http_status=data.status
            )
        conditions = data.get("current_condition")
        if conditions is None or conditions == []:
            return WeatherObservation(requested, url, failure_reason="no_data")
        if not isinstance(conditions, list) or not isinstance(conditions[0], dict):
            return WeatherObservation(
                requested, url, failure_reason="provider_invalid_payload"
            )
        current = conditions[0]
        observed = _weather_area(data)
        temperature = weather_temperature(current.get("temp_C"))
        failure: WeatherFailureReason | None = None
        if observed is None:
            failure = "missing_observed_location"
        elif temperature is None:
            failure = "missing_temperature"
        return WeatherObservation(
            requested_location=requested,
            source_url=url,
            observed_location=observed,
            temperature_c=temperature,
            feels_like_c=weather_temperature(current.get("FeelsLikeC")),
            failure_reason=failure,
            details=_weather_details(current),
        )

    async def read_imgw_station_observation(
        self, location: str
    ) -> WeatherObservation | None:
        url = imgw_station_url(location)
        if url is None:
            return None
        data = await self._fetch_weather_payload(url, timeout=4.0)
        if isinstance(data, _WeatherProviderFailure):
            return None
        observed = weather_area_name(data.get("stacja"))
        value = weather_temperature(data.get("temperatura"))
        at = imgw_observation_time(
            data.get("data_pomiaru"), data.get("godzina_pomiaru")
        )
        now = datetime.now(timezone.utc)
        if (
            observed is None
            or observed.casefold() != location.casefold()
            or str(data.get("id_stacji")) != _IMGW_STATIONS[location.casefold()]
            or value is None
            or at is None
            or not timedelta() <= now - at <= _IMGW_MAX_AGE
        ):
            return None
        return WeatherObservation(location, url, observed, value, observed_at=at)

    async def _fetch_weather_payload(
        self, url: str, *, timeout: float = 10.0
    ) -> dict[str, Any] | _WeatherProviderFailure:
        try:
            async with TrafficControlledHttpClient(
                provider="weather", timeout=timeout
            ) as client:
                response = await client.aget(url, raise_for_status=False)
            if response.status_code != 200:
                return _WeatherProviderFailure(
                    "provider_http_error", response.status_code
                )
            data = response.json()
        except (TimeoutError, httpx.TimeoutException):
            return _WeatherProviderFailure("provider_timeout")
        except httpx.HTTPError:
            return _WeatherProviderFailure("provider_transport_error")
        except RuntimeError:
            return _WeatherProviderFailure("provider_client_error")
        except ValueError:
            return _WeatherProviderFailure("provider_invalid_payload")
        if not isinstance(data, dict):
            return _WeatherProviderFailure("provider_invalid_payload")
        return data

    @staticmethod
    def _first_nested_value(items: Any, field: str, default: str) -> str:
        if not items:
            return default
        first = items[0] or {}
        return first.get(field, default)

    def _parse_weather_payload(
        self, data: Dict[str, Any], location: str
    ) -> Dict[str, str] | str:
        current_list = data.get("current_condition") or []
        if not current_list:
            return f"✗ Brak danych pogodowych dla '{location}'."

        current = current_list[0]
        nearest_area = (data.get("nearest_area") or [{}])[0] or {}

        return {
            "temp_c": current.get("temp_C", "N/A"),
            "temp_f": current.get("temp_F", "N/A"),
            "feels_like_c": current.get("FeelsLikeC", "N/A"),
            "feels_like_f": current.get("FeelsLikeF", "N/A"),
            "humidity": current.get("humidity", "N/A"),
            "weather_desc": self._first_nested_value(
                current.get("weatherDesc"), "value", "N/A"
            ),
            "wind_speed": current.get("windspeedKmph", "N/A"),
            "wind_dir": current.get("winddir16Point", "N/A"),
            "area_name": self._first_nested_value(
                nearest_area.get("areaName"), "value", location
            ),
            "country": self._first_nested_value(
                nearest_area.get("country"), "value", ""
            ),
        }

    @staticmethod
    def _format_weather_response(parsed: Dict[str, str], units: str) -> str:
        if units == "metric":
            temp_display = (
                f"{parsed['temp_c']}°C (odczuwalna: {parsed['feels_like_c']}°C)"
            )
        else:
            temp_display = (
                f"{parsed['temp_f']}°F (odczuwalna: {parsed['feels_like_f']}°F)"
            )

        return (
            f"🌤️  Pogoda dla: {parsed['area_name']}, {parsed['country']}\n\n"
            f"🌡️  Temperatura: {temp_display}\n"
            f"☁️  Warunki: {parsed['weather_desc']}\n"
            f"💧 Wilgotność: {parsed['humidity']}%\n"
            f"💨 Wiatr: {parsed['wind_speed']} km/h ({parsed['wind_dir']})"
        )

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

            status_counts = self._count_service_statuses(services)
            result = self._build_services_summary(services, status_counts)

            critical_offline = self._get_critical_offline_services()
            if critical_offline:
                result += "\n⚠️  UWAGA: Krytyczne usługi offline:\n"
                result += "".join(
                    f"  • {service.name}\n" for service in critical_offline
                )

            if detailed:
                result += self._build_detailed_services_section(services)

            return result

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania usług: {e}")
            return f"✗ Błąd podczas sprawdzania usług: {e}"

    @staticmethod
    def _count_service_statuses(services) -> dict[str, int]:
        return {
            "online": sum(
                1 for service in services if service.status.value == "online"
            ),
            "offline": sum(
                1 for service in services if service.status.value == "offline"
            ),
            "degraded": sum(
                1 for service in services if service.status.value == "degraded"
            ),
            "unknown": sum(
                1 for service in services if service.status.value == "unknown"
            ),
        }

    def _build_services_summary(self, services, status_counts: dict[str, int]) -> str:
        total = len(services)
        result = "🔍 Status usług systemowych\n\n"
        result += f"✅ Online: {status_counts['online']}/{total}\n"

        if status_counts["offline"] > 0:
            result += f"❌ Offline: {status_counts['offline']}/{total}\n"
        if status_counts["degraded"] > 0:
            result += f"⚠️  Degraded: {status_counts['degraded']}/{total}\n"
        if status_counts["unknown"] > 0:
            result += f"❓ Unknown: {status_counts['unknown']}/{total}\n"
        return result

    def _get_critical_offline_services(self):
        critical_services = self.service_registry.get_critical_services()
        return [
            service
            for service in critical_services
            if service.status.value == "offline"
        ]

    @staticmethod
    def _service_status_icon(status_value: str) -> str:
        return {
            "online": "✅",
            "offline": "❌",
            "degraded": "⚠️",
            "unknown": "❓",
        }.get(status_value, "❓")

    def _build_detailed_services_section(self, services) -> str:
        details = "\n📋 Szczegóły usług:\n\n"
        for service in services:
            details += (
                f"{self._service_status_icon(service.status.value)} {service.name}\n"
            )
            details += f"   Typ: {service.service_type}\n"

            if service.endpoint:
                details += f"   Endpoint: {service.endpoint}\n"

            if service.status.value == "online" and service.latency_ms > 0:
                details += f"   Latencja: {service.latency_ms:.2f}ms\n"

            if service.error_message:
                details += f"   Błąd: {service.error_message}\n"

            details += "\n"
        return details
