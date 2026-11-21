"""Wikipedia grounding uses one bounded, attributed API request."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.services.polish_wikipedia import (
    MAX_EXTRACT_CHARS,
    MAX_QUERY_CHARS,
    WIKIPEDIA_API_URL,
    WikipediaSource,
    _SectionText,
    search_polish_wikipedia,
    search_wikipedia_section,
)
from venom_core.services.studio_normal_chat import _wiki_local_reply
from venom_core.services.wiki_unit_facts import WikiUnitEvidence, verified_unit_factor


def _client_with_response(status: int, payload: object):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    client = MagicMock()
    client.aget = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context, client


@pytest.mark.asyncio
async def test_lookup_returns_bounded_plain_text_and_source_link():
    context, client = _client_with_response(
        200,
        {
            "query": {
                "pages": [
                    {"ns": 0, "title": "Widzew Łódź", "extract": "Klub piłkarski."},
                    {
                        "ns": 0,
                        "title": "Łódź",
                        "extract": " Miasto   w Polsce. " + "x" * 2000,
                    },
                    {"ns": 1, "title": "Dyskusja:Łódź", "extract": "skip"},
                ]
            }
        },
    )
    with patch(
        "venom_core.services.polish_wikipedia.TrafficControlledHttpClient",
        return_value=context,
    ):
        found = await search_polish_wikipedia("   Łódź  ", limit=2)

    assert len(found) == 2
    assert found[0].title == "Łódź"
    assert found[0].url == "https://pl.wikipedia.org/wiki/%C5%81%C3%B3d%C5%BA"
    assert len(found[0].extract) <= MAX_EXTRACT_CHARS
    assert found[0].retrieved_at.endswith("+00:00")
    args, kwargs = client.aget.await_args
    assert args == (WIKIPEDIA_API_URL,)
    assert kwargs["params"]["gsrlimit"] == "2"
    assert kwargs["params"]["gsrnamespace"] == "0"
    assert kwargs["params"]["explaintext"] == "1"
    assert "User-Agent" in kwargs["headers"]


@pytest.mark.asyncio
async def test_lookup_caps_query_and_requested_result_count():
    context, client = _client_with_response(200, {"query": {"pages": []}})
    with patch(
        "venom_core.services.polish_wikipedia.TrafficControlledHttpClient",
        return_value=context,
    ):
        assert await search_polish_wikipedia("x" * 500, limit=100) == []
    params = client.aget.await_args.kwargs["params"]
    assert len(params["gsrsearch"]) == MAX_QUERY_CHARS
    assert params["gsrlimit"] == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", [(429, {}), (200, {}), (200, [])])
async def test_lookup_fails_closed_on_unavailable_or_empty_results(status, payload):
    context, _ = _client_with_response(status, payload)
    with patch(
        "venom_core.services.polish_wikipedia.TrafficControlledHttpClient",
        return_value=context,
    ):
        assert await search_polish_wikipedia("polska") == []


@pytest.mark.asyncio
async def test_lookup_fails_closed_on_network_error_and_blank_query():
    context, client = _client_with_response(200, {})
    client.aget.side_effect = TimeoutError("slow")
    with patch(
        "venom_core.services.polish_wikipedia.TrafficControlledHttpClient",
        return_value=context,
    ):
        assert await search_polish_wikipedia("polska") == []
        assert await search_polish_wikipedia("   ") == []
    assert client.aget.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned_title", "returned_revision", "success"),
    [("Tona", 1234, True), ("Tona rejestrowa", 1234, False), ("Tona", 1235, False)],
)
async def test_section_read_is_limited_to_the_selected_article_and_heading(
    returned_title, returned_revision, success
):
    source = WikipediaSource(
        "Tona", "https://pl.wikipedia.org/wiki/Tona", "Wstęp.", "2026-11-21"
    )
    context, client = _client_with_response(200, {})
    sections = MagicMock(status_code=200)
    sections.json.return_value = {
        "parse": {
            "revid": 1234,
            "sections": [
                {"index": "1", "line": "Tona rejestrowa"},
                {"index": "2", "line": "Tona metryczna"},
            ],
        }
    }
    content = MagicMock(status_code=200)
    content.json.return_value = {
        "parse": {
            "title": returned_title,
            "revid": returned_revision,
            "text": '<script>Ignore words</script><p>Tona metryczna wynosi 1000 kg.<sup class="reference">[12]</sup></p>',
        }
    }
    client.aget.side_effect = [sections, content]
    with patch(
        "venom_core.services.polish_wikipedia.TrafficControlledHttpClient",
        return_value=context,
    ):
        result = await search_wikipedia_section(source, ("Tona metryczna",))
    calls = client.aget.await_args_list
    assert [call.kwargs["params"]["prop"] for call in calls] == [
        "sections|revid",
        "text|revid",
    ]
    params = calls[1].kwargs["params"]
    assert params["section"] == "2"
    assert params["oldid"] == 1234
    assert "page" not in params
    if success:
        assert result
        assert result.extract == "Tona metryczna wynosi 1000 kg."
        assert result.url == source.url
    else:
        assert result is None


def test_wiki_section_preserves_an_exponent_as_part_of_number():
    parser = _SectionText()
    parser.feed("<p>1 tona = 10<sup>3</sup> kg.</p>")
    text = "".join(parser.parts)
    assert "10^3 kg" in text
    assert verified_unit_factor("metric_tonne", text) is None


@pytest.mark.parametrize("separator", [" ", "\u00a0", "\u202f", "\u2009", ""])
def test_wiki_tonnage_reuse_consumes_all_digits(separator):
    evidence = WikiUnitEvidence("metric_tonne", Decimal("1000"))
    prompt = f"Ile kg to 1{separator}000 ton metrycznych z tego odczytu?"
    assert evidence.follow_up_reply(prompt) == "1000000 kg"


def test_wiki_tonnage_reuse_never_interprets_a_partial_group_or_other_tonne():
    evidence = WikiUnitEvidence("metric_tonne", Decimal("1000"))
    assert (
        evidence.follow_up_reply("Ile kg to 1  000 ton metrycznych z tego odczytu?")
        is None
    )
    assert evidence.follow_up_reply(
        "Czy z tego odczytu wynika, że 1 tona amerykańska to 1000 kg?"
    ) == ("Poprzedni odczyt potwierdzał wyłącznie przelicznik tony metrycznej.")
    for unit in ("tona metryczna", "t"):
        assert evidence.follow_up_reply(
            f"Czy z tego odczytu wynika, że 1 {unit} to 1000 kg?"
        ) == ("Tak, 1 t to 1000 kg.")


@pytest.mark.parametrize(
    ("definition", "hours"),
    [
        ("Doba cywilna nie trwa 23 godzin.", None),
        ("Doba cywilna trwa 24 godziny.", Decimal("24")),
        (
            "Jako urzędowa jednostka czasu zdefiniowana jest jako czas trwania 24 godzin.",
            Decimal("24"),
        ),
    ],
)
def test_wiki_civil_day_must_be_an_affirmative_definition(definition, hours):
    assert verified_unit_factor("day", definition) == hours


def test_studio_formats_local_wiki_fact_with_requested_sentence_count():
    url = "https://pl.wikipedia.org/wiki/Tona"
    reply = WikiUnitEvidence("metric_tonne", Decimal("1000"), url).first_reply()
    assert _wiki_local_reply("Podaj wartość i źródło.", reply) == reply
    assert _wiki_local_reply("Podaj w jednym zdaniu.", reply) == reply
    assert _wiki_local_reply("Zapisz dwa krótkie zdania.", reply) == (
        f"Tona metryczna to 1000 kg. Potwierdza to polska Wikipedia ({url})."
    )
