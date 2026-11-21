"""Weather evidence and deterministic Studio replies owned by one source read."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Self, get_args
from unicodedata import normalize

from venom_core.execution.skills.assistant_skill import (
    AssistantSkill,
    WeatherFailureReason,
    WeatherObservation,
    imgw_observation_time,
    imgw_station_url,
    weather_area_name,
    weather_temperature,
)
from venom_core.services.academy.qualified_chat_quote import without_quotes
from venom_core.services.academy.qualified_chat_revisions import (
    explicit_lookup_allowed,
    lookup_forbidden,
)

_NEARBY_ALLOWED = re.compile(
    r"\b(?:dopuszczam|możesz (?:użyć|podać)|może być|mogą być|"
    r"podaj|uwzględnij)(?: też| także| mi| odczyt| pomiar| dane| wynik)*"
    r" (?:z )?(?:okolic\w*|poblisk\w* (?:miejscowoś\w*|pomiar\w*))\b",
    re.I,
)
_NEARBY_DENIED = re.compile(
    r"\b(?:(?:tylko|wyłącznie) (?:samo |w granicach )?miast\w*|"
    r"bez okolic\w*|nie (?:podawaj|uwzględniaj) (?:danych z )?okolic\w*)\b",
    re.I,
)
_PREVIOUS_VALUE = re.compile(
    r"\b(?:tę samą (?:wartość|temperaturę)|(?:z|według) poprzedniego "
    r"(?:pomiaru|odczytu)|poprzedni(?:ą|e) (?:temperaturę|wartość))\b",
    re.I,
)
_FORECAST_FROM_READING = re.compile(
    r"\b(?:z (?:tego )?(?:jednego |pojedynczego )?pomiaru|"
    r"na podstawie (?:tego )?(?:jednego |pojedynczego )?(?:odczytu|pomiaru))\b"
    r"[^?!.]{0,120}\b(?:jutro|prognoz\w*)\b",
    re.I,
)
_CHANGE_TOPIC = re.compile(r"\b(?:zmieniam temat|inny temat|nowe pytanie)\b", re.I)
_NEW_READ = re.compile(
    r"\b(?:sprawdź|odczytaj|pobierz|zmierz) (?:jeszcze raz|ponownie|teraz|znowu)\b",
    re.I,
)
_VALUE_ONLY = re.compile(
    r"\b(?:samą liczbę|bez nazwy miasta)\b|(?<!tę )\bsamą wartość\b", re.I
)
_COMMA_FORMAT = re.compile(r"\bw formacie\b[^.!?]{0,60},\s*liczba\s*°?C\b", re.I)
_TEMPERATURE_REQUEST = re.compile(r"\btemperatur\w*\b|°C", re.I)
_FEELS_LIKE = re.compile(r"\bodczuwaln\w*\b", re.I)
_ACTUAL = re.compile(r"\b(?:rzeczywist|zmierzon|powietrz)\w*\b", re.I)
_NO_FEELS_LIKE = re.compile(
    r"\b(?:bez|pomiń|nie podawaj) (?:okolic\w* (?:i|ani|oraz) )?"
    r"(?:(?:temperatur|pogod)\w* )?odczuwaln\w*\b",
    re.I,
)
_OTHER_METRICS = re.compile(
    r"\b(?:wilgotn\w*|wiatr\w*|opad\w*|zachmurzeni\w*|ciśnieni\w*)\b", re.I
)
_FAILURES = frozenset((*get_args(WeatherFailureReason), "different_location"))


@dataclass(frozen=True)
class WeatherEvidence:
    requested_location: str
    observed_location: str | None = None
    temperature_c: str | None = None
    source_url: str | None = None
    reason: str | None = None
    http_status: int | None = None
    feels_like_c: str | None = None
    preferred_metric: str | None = None
    observed_at: datetime | None = None

    def to_record(self) -> dict[str, str]:
        data = {"weather_requested_location": self.requested_location}
        for name in (
            "observed_location",
            "temperature_c",
            "source_url",
            "reason",
            "http_status",
            "feels_like_c",
            "preferred_metric",
        ):
            value = getattr(self, name)
            if value is not None:
                data["weather_" + name] = str(value)
        if self.observed_at is not None:
            data["weather_observed_at"] = self.observed_at.isoformat()
        return data

    @classmethod
    def from_record(cls, record: dict[str, str]) -> Self | None:
        if any(
            not isinstance(value, str)
            for key, value in record.items()
            if key.startswith("weather_")
        ):
            return None
        requested = weather_area_name(record.get("weather_requested_location"))
        if requested is None:
            return None
        observed = weather_area_name(record.get("weather_observed_location"))
        temperature = weather_temperature(record.get("weather_temperature_c"))
        source = record.get("weather_source_url")
        reason = record.get("weather_reason")
        status_text = record.get("weather_http_status")
        feels = weather_temperature(record.get("weather_feels_like_c"))
        metric = record.get("weather_preferred_metric")
        if metric not in {None, "feels_like"} or (
            metric is not None and reason is not None
        ):
            return None
        if reason is None:
            if observed is None or temperature is None:
                return None
        elif reason not in _FAILURES or record.get("weather_temperature_c") is not None:
            return None
        at = record.get("weather_observed_at")
        observed_at = None
        if source != AssistantSkill.weather_source_url(requested):
            if (
                source is None
                or source != imgw_station_url(requested)
                or observed is None
                or observed.casefold() != requested.casefold()
                or reason is not None
                or not at
            ):
                return None
            observed_at = imgw_observation_time(at[:10], at[11:13])
            if observed_at is None or observed_at.isoformat() != at:
                return None
        elif at is not None:
            return None
        if status_text is not None and (
            reason != "provider_http_error"
            or not re.fullmatch(r"[1-5]\d{2}", status_text)
        ):
            return None
        return cls(
            requested,
            observed,
            temperature,
            source,
            reason,
            int(status_text) if status_text is not None else None,
            feels,
            metric,
            observed_at,
        )

    def follow_up_reply(self, message: str) -> str | None:
        visible = without_quotes(message)
        if (
            _CHANGE_TOPIC.search(visible)
            or explicit_lookup_allowed(message)
            or (_NEW_READ.search(visible) and not lookup_forbidden(message))
        ):
            return None
        if _FORECAST_FROM_READING.search(visible):
            return "Pojedynczy pomiar temperatury nie pozwala potwierdzić prognozy."
        if not _PREVIOUS_VALUE.search(visible):
            return None
        temperature = self.temperature_c
        if _only_feels_like(visible) or (
            self.preferred_metric == "feels_like" and not _ACTUAL.search(visible)
        ):
            temperature = self.feels_like_c
        if temperature is None or self.observed_location is None:
            return f"Brak potwierdzonego odczytu temperatury dla miejscowości {self.requested_location}."
        value = f"{temperature}°C"
        if _VALUE_ONLY.search(visible):
            return value
        separator = ", " if _COMMA_FORMAT.search(message) else " — "
        return f"{self.observed_location}{separator}{value}"


@dataclass(frozen=True)
class WeatherGroundingReply:
    text: str
    evidence: WeatherEvidence

    @property
    def verified(self) -> bool:
        return self.evidence.reason is None

    @property
    def reason(self) -> str | None:
        return self.evidence.reason

    @property
    def excerpt(self) -> str:
        return (
            f"Requested location: {self.evidence.requested_location}\n"
            + (f"Source: {self.evidence.source_url}\n" if self.verified else "")
            + f"{self.text}\n"
        )


def _canonical(place: str, aliases: Mapping[str, str]) -> str:
    key = normalize("NFC", place).casefold()
    return aliases.get(key, place)


def _only_feels_like(visible: str) -> bool:
    return bool(
        _FEELS_LIKE.search(visible)
        and not _NO_FEELS_LIKE.search(visible)
        and not _ACTUAL.search(visible)
    )


def weather_observation_reply(
    observation: WeatherObservation,
    message: str,
    aliases: Mapping[str, str],
) -> WeatherGroundingReply:
    """Publish only the real temperature and the location bound to it."""
    requested = observation.requested_location
    observed = observation.observed_location
    reason = observation.failure_reason
    if reason is None:
        if observed is None:
            reason = "missing_observed_location"
        elif observation.temperature_c is None:
            reason = "missing_temperature"
    if reason is not None:
        text = (
            f"Dostawca nie zwrócił potwierdzonej temperatury dla miejscowości {requested}."
            if reason in {"no_data", "missing_temperature", "missing_observed_location"}
            else f"Nie udało się pobrać danych pogodowych dla miejscowości {requested}."
        )
        return WeatherGroundingReply(
            text,
            WeatherEvidence(
                requested,
                observed,
                source_url=observation.source_url,
                reason=reason,
                http_status=observation.http_status,
            ),
        )
    assert observed is not None and observation.temperature_c is not None
    canonical_observed = _canonical(observed, aliases)
    same_place = (
        normalize("NFC", _canonical(requested, aliases)).casefold()
        == normalize("NFC", canonical_observed).casefold()
    )
    visible = without_quotes(message)
    nearby = bool(
        _NEARBY_ALLOWED.search(visible) and not _NEARBY_DENIED.search(visible)
    )
    if not same_place and not nearby:
        return WeatherGroundingReply(
            f"Dostawca wskazał miejscowość {observed}. "
            f"Brak potwierdzonej temperatury dla miejscowości {requested}.",
            WeatherEvidence(
                requested,
                observed,
                source_url=observation.source_url,
                reason="different_location",
            ),
        )
    context = (
        ""
        if same_place
        else f"Dostawca podał pomiar z innego miejsca niż {requested}. "
    )
    only_feels = _only_feels_like(visible)
    include_feels = _FEELS_LIKE.search(visible) and not _NO_FEELS_LIKE.search(visible)
    lines = []
    if not only_feels:
        lines.append(f"Temperatura powietrza: {observation.temperature_c}°C.")
    if include_feels:
        if observation.feels_like_c is None:
            lines.append("Brak potwierdzonej temperatury odczuwalnej.")
        else:
            lines.append(f"Temperatura odczuwalna: {observation.feels_like_c}°C.")
    temperature = " ".join(lines)
    if _TEMPERATURE_REQUEST.search(visible) is None or _OTHER_METRICS.search(visible):
        details = [f"{name}: {value}." for name, value in observation.details]
        if (
            observation.feels_like_c
            and not include_feels
            and not _NO_FEELS_LIKE.search(visible)
        ):
            details.insert(0, f"Temperatura odczuwalna: {observation.feels_like_c}°C.")
        temperature = " ".join([temperature, *details])
    when = ""
    if observation.observed_at is not None:
        when = (
            f" Pomiar z {observation.observed_at:%Y-%m-%d, %H:%M} UTC. "
            "Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki "
            "Wodnej – Państwowy Instytut Badawczy."
        )
    return WeatherGroundingReply(
        f"{context}Miejsce odczytu: {observed}. {temperature}{when} Źródło: {observation.source_url}",
        WeatherEvidence(
            requested,
            canonical_observed,
            observation.temperature_c,
            observation.source_url,
            feels_like_c=observation.feels_like_c,
            preferred_metric="feels_like" if only_feels else None,
            observed_at=observation.observed_at,
        ),
    )
