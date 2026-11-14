"""Wikipedia grounding uses one bounded, attributed API request."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.services.polish_wikipedia import (
    MAX_EXTRACT_CHARS,
    MAX_QUERY_CHARS,
    WIKIPEDIA_API_URL,
    search_polish_wikipedia,
)


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
