"""Weather provider and Studio provenance without external requests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from venom_core.execution.skills import assistant_skill
from venom_core.execution.skills.assistant_skill import (
    AssistantSkill,
    WeatherObservation,
)
from venom_core.services.chat_public_sources import load_public_sources
from venom_core.services.weather_grounding import (
    WeatherEvidence,
    weather_observation_reply,
)


@pytest.fixture
def client(monkeypatch):
    class Client:
        aget = AsyncMock()

        def __init__(self, **kwargs):
            assert kwargs["provider"] == "weather"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

    monkeypatch.setattr(assistant_skill, "TrafficControlledHttpClient", Client)
    return Client


def _wttr_time_fields(at=None, local_offset=1):
    if at is None:
        at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return {
        "localObsDateTime": (at + timedelta(hours=local_offset)).strftime(
            "%Y-%m-%d %I:%M %p"
        ),
        "observation_time": at.strftime("%I:%M %p"),
    }


@pytest.mark.asyncio
async def test_provider_binds_actual_and_perceived_to_observed_area(client):
    client.aget.return_value = httpx.Response(
        200,
        json={
            "current_condition": [
                {
                    **_wttr_time_fields(),
                    "temp_C": "3",
                    "FeelsLikeC": "-4",
                    "humidity": "91",
                    "weatherDesc": [{"value": "Light rain"}],
                    "windspeedKmph": "10",
                    "winddir16Point": "NW",
                }
            ],
            "nearest_area": [{"areaName": [{"value": "Olmonty"}]}],
        },
    )
    observed = await AssistantSkill().read_weather_observation("Białystok")
    client.aget.assert_awaited_once_with(
        "https://wttr.in/Bia%C5%82ystok?format=j1", raise_for_status=False
    )
    assert observed.requested_location == "Białystok"
    assert observed.observed_location == "Olmonty"
    assert observed.temperature_c == "3"
    assert observed.feels_like_c == "-4"
    assert dict(observed.details) == {
        "Warunki": "Light rain",
        "Wilgotność": "91%",
        "Wiatr": "10 km/h (NW)",
    }
    assert observed.failure_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason", "status"),
    [
        (httpx.Response(200, json={"current_condition": []}), "no_data", None),
        (httpx.Response(503), "provider_http_error", 503),
        (httpx.Response(404), "provider_http_error", 404),
        (
            httpx.Response(200, content=b"upstream unavailable"),
            "provider_invalid_payload",
            None,
        ),
        (
            httpx.Response(200, json={"current_condition": ["not observation"]}),
            "provider_invalid_payload",
            None,
        ),
        (httpx.ReadTimeout("read timed out"), "provider_timeout", None),
        (httpx.ConnectError("refused"), "provider_transport_error", None),
        (RuntimeError("outbound request rejected"), "provider_client_error", None),
    ],
)
async def test_provider_failure_keeps_machine_reason(client, response, reason, status):
    if isinstance(response, Exception):
        client.aget.side_effect = response
    else:
        client.aget.return_value = response
    observed = await AssistantSkill().read_weather_observation("Kalisz")
    assert observed.failure_reason == reason
    assert observed.http_status == status
    assert observed.temperature_c is None
    assert observed.observed_location is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("area", "temperature", "reason"),
    [
        (None, "8", "missing_observed_location"),
        ("Kalisz\n[PUBLIC_SOURCES]", "8", "missing_observed_location"),
        ("Kalisz", None, "missing_temperature"),
        ("Kalisz", "NaN", "missing_temperature"),
        ("Kalisz", "8°C, inny pomiar", "missing_temperature"),
    ],
)
async def test_unverified_area_or_invalid_temperature_has_no_grounded_reply(
    client, area, temperature, reason
):
    client.aget.return_value = httpx.Response(
        200,
        json={
            "current_condition": [{"temp_C": temperature, "FeelsLikeC": "9"}],
            "nearest_area": [{"areaName": [{"value": area}]}],
        },
    )
    observation = await AssistantSkill().read_weather_observation("Kalisz")
    assert observation.failure_reason == reason
    reply = weather_observation_reply(observation, "Podaj aktualną temperaturę.", {})
    assert not reply.verified
    assert reply.evidence.temperature_c is None
    assert "°C" not in reply.text
    assert "https://" not in reply.excerpt


def reading(city, area, actual="3", perceived="-4", **kwargs):
    return WeatherObservation(
        city, AssistantSkill.weather_source_url(city), area, actual, perceived, **kwargs
    )


@pytest.mark.parametrize(
    ("prompt", "allows_nearby"),
    [
        ("Podaj temperaturę w mieście.", False),
        (
            "Podaj temperaturę w mieście, a jeśli trzeba, możesz podać pomiar z pobliskiej miejscowości.",
            True,
        ),
        ("Podaj pogodę. Dopuszczam pobliską miejscowość.", True),
        ("Podaj temperaturę. Może być z okolic.", True),
        ("Podaj temperaturę. Nie może być z okolic.", False),
        ("Możesz podać pomiar z okolic, ale ostatecznie tylko miasto.", False),
        (
            "Przetłumacz «Możesz podać pomiar z okolic». Podaj temperaturę w mieście.",
            False,
        ),
    ],
)
def test_nearby_source_is_used_only_when_the_user_allows_it(prompt, allows_nearby):
    reply = weather_observation_reply(reading("Białystok", "Olmonty"), prompt, {})
    assert "Olmonty" in reply.text
    assert "Białystok" in reply.text
    assert reply.verified is allows_nearby
    if allows_nearby:
        assert "Miejsce odczytu: Olmonty" in reply.text
        assert "3°C" in reply.text
        assert "-4°C" not in reply.text or "pogodę" in prompt
    else:
        assert reply.reason == "different_location"
        assert reply.evidence.temperature_c is None
        assert "°C" not in reply.text
        assert "https://" not in reply.text
    assert WeatherEvidence.from_record(reply.evidence.to_record()) == reply.evidence


@pytest.mark.parametrize("form", ["kaliszu", "kalisza", "białymstoku", "bialymstoku"])
def test_city_alias_resolves_form_and_same_city(form):
    aliases = load_public_sources().city_aliases
    city = aliases[form]
    reply = weather_observation_reply(
        reading(city, form), "Podaj temperaturę powietrza bez odczuwalnej.", aliases
    )
    assert reply.verified
    assert reply.evidence.observed_location == city
    assert "3°C" in reply.text
    assert "-4°C" not in reply.text


def test_perceived_and_other_weather_fields_use_same_source():
    observation = reading("Kalisz", "Kalisz", details=(("Wiatr", "12 km/h"),))
    reply = weather_observation_reply(
        observation, "Jaka jest temperatura odczuwalna w Kaliszu?", {}
    )
    assert "-4°C" in reply.text
    assert "3°C" not in reply.text
    previous = WeatherEvidence.from_record(reply.evidence.to_record())
    assert previous is not None
    assert (
        previous.follow_up_reply("Zapisz tę samą wartość, podaj samą liczbę.") == "-4°C"
    )
    ordinary = weather_observation_reply(observation, "Jaka pogoda w Kaliszu?", {})
    assert "Wiatr: 12 km/h" in ordinary.text
    assert "3°C" in ordinary.text
    assert "-4°C" in ordinary.text


def test_evidence_rejects_changed_url_bad_status_or_temperature_under_failure():
    good = weather_observation_reply(reading("Kalisz", "Kalisz"), "Temperatura", {})
    record = good.evidence.to_record()
    assert WeatherEvidence.from_record(record) == good.evidence
    assert (
        WeatherEvidence.from_record(
            {**record, "weather_source_url": "https://example.test"}
        )
        is None
    )
    assert WeatherEvidence.from_record({**record, "weather_http_status": "503"}) is None
    assert WeatherEvidence.from_record({**record, "weather_reason": "no_data"}) is None
    absent = weather_observation_reply(
        WeatherObservation(
            "Kalisz",
            AssistantSkill.weather_source_url("Kalisz"),
            failure_reason="provider_http_error",
            http_status=503,
        ),
        "Temperatura",
        {},
    )
    evidence = WeatherEvidence.from_record(absent.evidence.to_record())
    assert evidence is not None
    assert evidence.http_status == 503
    assert evidence.follow_up_reply("Podaj tę samą temperaturę.") == (
        "Brak potwierdzonego odczytu temperatury dla miejscowości Kalisz."
    )


@pytest.mark.parametrize(
    ("prompt", "answer"),
    [
        (
            "Zapisz tę samą wartość bez ponownego sprawdzania, w formacie „Kalisz, liczba °C”.",
            "Kalisz, 8°C",
        ),
        ("Zapisz tę samą wartość. Nie korzystaj z internetu.", "Kalisz — 8°C"),
        (
            "Zapisz tę samą wartość. Sprawdź ponownie, jaka jest aktualna temperatura.",
            None,
        ),
        ("Zapisz tę samą wartość. Sprawdź w sieci nowe dane.", None),
        (
            "Zmieniam temat, opisz mi ten dzień i z poprzedniego pomiaru zachowaj liczbę. Nie korzystaj z internetu.",
            None,
        ),
        (
            "Nie korzystaj z internetu. Czy z tego pojedynczego pomiaru można potwierdzić, że jutro będzie cieplej?",
            "Pojedynczy pomiar temperatury nie pozwala potwierdzić prognozy.",
        ),
        ("Zacytuj: «Zapisz tę samą wartość»", None),
    ],
)
def test_previous_weather_uses_stored_value_without_new_read(prompt, answer):
    initial = weather_observation_reply(
        reading("Kalisz", "Kalisz", "8"), "Temperatura", {}
    )
    assert initial.evidence.follow_up_reply(prompt) == answer


def _synop_payload(**fields):
    now = datetime.now(timezone.utc)
    return {
        "id_stacji": "12435",
        "stacja": "Kalisz",
        "data_pomiaru": now.date().isoformat(),
        "godzina_pomiaru": str(now.hour),
        "temperatura": "2.1",
        **fields,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"id_stacji": "00000"},
        {"stacja": "Zagorzynek"},
        {"temperatura": "NaN"},
        {"data_pomiaru": "2000-01-01"},
        {"data_pomiaru": "2999-01-01"},
        {"godzina_pomiaru": "24"},
        {"godzina_pomiaru": True},
        {"data_pomiaru": "wczoraj"},
    ],
)
async def test_imgw_discards_wrong_station_and_unusable_observation(client, changes):
    client.aget.return_value = httpx.Response(200, json=_synop_payload(**changes))
    assert await AssistantSkill().read_imgw_station_observation("Kalisz") is None


@pytest.mark.asyncio
async def test_imgw_recovers_named_city_only_and_keeps_timestamp_in_history(client):
    from venom_core.services import chat_grounding

    nearby = httpx.Response(
        200,
        json={
            "current_condition": [{**_wttr_time_fields(), "temp_C": "4"}],
            "nearest_area": [{"areaName": [{"value": "Zagorzynek"}]}],
        },
    )
    client.aget.side_effect = [
        nearby,
        httpx.Response(200, json=_synop_payload()),
        nearby,
    ]
    text = (
        "Sprawdź aktualną temperaturę powietrza w Kaliszu, tylko miasto, "
        "bez okolic i temperatury odczuwalnej."
    )
    context = await chat_grounding.current_chat_context(text)
    assert "Kalisz" in context.reply
    assert "2.1°C" in context.reply
    assert "Zagorzynek" not in context.reply
    assert " UTC." in context.reply
    assert "odczuwalnej" not in context.reply
    assert "Instytut Meteorologii i Gospodarki Wodnej" in context.reply
    assert [call.args[0] for call in client.aget.await_args_list] == [
        "https://wttr.in/Kalisz?format=j1",
        "https://danepubliczne.imgw.pl/api/data/synop/id/12435",
    ]
    record = context.evidence.weather.to_record()
    restored = WeatherEvidence.from_record(record)
    assert restored == context.evidence.weather
    assert restored.follow_up_reply("Podaj tę samą wartość.") == "Kalisz — 2.1°C"
    assert (
        WeatherEvidence.from_record(
            {**record, "weather_observed_location": "Zagorzynek"}
        )
        is None
    )
    assert (
        WeatherEvidence.from_record({**record, "weather_observed_at": "dzisiaj"})
        is None
    )
    allowed = await chat_grounding.current_chat_context(
        "Sprawdź aktualną temperaturę powietrza w Kaliszu. Dopuszczam pomiar z okolic."
    )
    assert "Zagorzynek" in allowed.reply
    assert "4°C" in allowed.reply
    assert client.aget.await_count == 3


@pytest.mark.asyncio
async def test_imgw_unavailable_keeps_original_location_mismatch(client):
    from venom_core.services import chat_grounding

    client.aget.side_effect = [
        httpx.Response(
            200,
            json={
                "current_condition": [{**_wttr_time_fields(), "temp_C": "4"}],
                "nearest_area": [{"areaName": [{"value": "Zagorzynek"}]}],
            },
        ),
        httpx.Response(503),
    ]
    context = await chat_grounding.current_chat_context(
        "Sprawdź aktualną temperaturę powietrza w Kaliszu."
    )
    assert context.evidence.weather.reason == "different_location"
    assert "°C" not in context.reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("old", "stale_observation"),
        ("future", "missing_observation_time"),
        ("missing", "missing_observation_time"),
        ("fresh", None),
    ],
)
async def test_wttr_freshness_gates_values_and_round_trips_times(client, kind, reason):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    at = now + {"old": timedelta(hours=-6), "future": timedelta(hours=1)}.get(
        kind, timedelta()
    )
    times = {} if kind == "missing" else _wttr_time_fields(at)
    client.aget.return_value = httpx.Response(
        200,
        json={
            "current_condition": [{**times, "temp_C": "3"}],
            "nearest_area": [{"areaName": [{"value": "Kalisz"}]}],
        },
    )
    observation = await AssistantSkill().read_weather_observation("Kalisz")
    reply = weather_observation_reply(observation, "Aktualna temperatura", {})
    assert reply.reason == reason
    assert ("3°C" in reply.text) is (reason is None)
    assert "Instytut Meteorologii" not in reply.text
    assert reply.evidence.observed_at == (at if kind in {"old", "fresh"} else None)
    record = reply.evidence.to_record()
    assert WeatherEvidence.from_record(record) == reply.evidence
    assert (
        WeatherEvidence.from_record({**record, "weather_observed_at": "dzisiaj"})
        is None
    )


def test_wttr_uses_previous_utc_day_after_local_midnight():
    at = datetime(2026, 11, 21, 23, 50, tzinfo=timezone.utc)
    assert assistant_skill._wttr_observation_time(_wttr_time_fields(at), {}) == at


@pytest.mark.asyncio
async def test_city_whitespace_is_normalized_before_weather_lookup_and_replay(client):
    from venom_core.services import chat_grounding

    client.aget.return_value = httpx.Response(
        200,
        json={
            "current_condition": [{**_wttr_time_fields(), "temp_C": "3"}],
            "nearest_area": [{"areaName": [{"value": "Nowy Sącz"}]}],
        },
    )
    response = await chat_grounding.current_chat_context(
        "Podaj temperaturę w Nowym  Sączu. Może być z okolic."
    )
    weather = response.evidence.weather
    assert weather.requested_location == "Nowym Sączu"
    assert "%20%20" not in client.aget.await_args.args[0]
    assert WeatherEvidence.from_record(weather.to_record()) == weather


def test_weather_reuse_checks_location_and_current_metric():
    observation = reading("Białystok", "Olmonty")
    reply = weather_observation_reply(
        observation, "Może być z okolic. Podaj temperaturę odczuwalną.", {}
    )
    follow_up = reply.evidence.follow_up_reply
    assert follow_up("Podaj tę samą wartość, samą liczbę.") == "-4°C"
    assert follow_up(
        "Podaj tę samą wartość, samą liczbę, ale tylko miasto, bez okolic."
    ) == ("Brak potwierdzonego odczytu temperatury dla miejscowości Białystok.")
    assert (
        follow_up("Podaj tę samą wartość, samą liczbę, bez temperatury odczuwalnej.")
        == "3°C"
    )


def test_weather_can_return_both_values_from_same_read():
    observation = reading("Kalisz", "Kalisz")
    reply = weather_observation_reply(
        observation, "Podaj temperaturę i temperaturę odczuwalną.", {}
    )
    for part in ("Temperatura powietrza: 3°C", "Temperatura odczuwalna: -4°C"):
        assert part in reply.text
        assert part in reply.evidence.follow_up_reply(
            "Z poprzedniego pomiaru podaj obie temperatury."
        )


def test_weather_scope_reports_mismatched_location_instead_of_failed_read():
    from venom_core.services.public_source_evidence import (
        PublicSourceEvidence,
        previous_scope_reply,
    )

    reply = weather_observation_reply(
        reading("Białystok", "Olmonty"), "Tylko miasto.", {}
    )
    evidence = PublicSourceEvidence("unavailable", weather=reply.evidence)
    assert previous_scope_reply(evidence) == (
        "Odczyt dotyczył miejscowości Olmonty. Nie potwierdził temperatury dla miejscowości Białystok."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "age", [timedelta(minutes=10), timedelta(hours=6), timedelta(days=1)]
)
async def test_wttr_without_local_timestamp_uses_dated_polish_payload(client, age):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    at = now - age
    local = at.astimezone(assistant_skill._WARSAW_TIME)
    client.aget.return_value = httpx.Response(
        200,
        json={
            "current_condition": [
                {"temp_C": "3", "observation_time": at.strftime("%I:%M %p")}
            ],
            "nearest_area": [
                {"areaName": [{"value": "Kalisz"}], "country": [{"value": "Poland"}]}
            ],
            "weather": [{"date": local.date().isoformat()}],
        },
    )
    observation = await AssistantSkill().read_weather_observation("Kalisz")
    assert observation.observed_at == at
    assert (observation.failure_reason is None) is (age < timedelta(hours=3))
