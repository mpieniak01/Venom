"""Ordinary chat source routing without live provider calls."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services import chat_grounding, studio_normal_chat, verified_web
from venom_core.services.chat_public_sources import load_public_sources


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Jaka pogoda w Warszawie?", "weather"),
        ("Co to jest temperatura?", "wiki"),
        ("Kim jest obecny prezydent Polski?", "web"),
        ("Jakie są dziś wiadomości z Polski?", "web"),
        ("Kim była Maria Skłodowska-Curie?", "wiki"),
        ("Kto jest prezydentem Polski?", "web"),
        ("Ile kosztuje benzyna?", "web"),
        ("Napisz mi życzenia urodzinowe", None),
    ],
)
def test_routing(message, expected):
    assert chat_grounding.grounding_kind(message) == expected


def test_private_question_does_not_trigger_external_source():
    assert chat_grounding.grounding_kind("Aktualny status hasła do konta") is None
    assert chat_grounding.grounding_kind("Aktualne dane ola@example.org") is None
    assert chat_grounding.grounding_kind("Jakie mam wydarzenia dziś?") is None
    assert chat_grounding.grounding_kind("Co jest dziś w moim kalendarzu?") is None
    assert chat_grounding.grounding_kind("Pogoda w Poznaniu", use_notes=True) is None


@pytest.mark.asyncio
async def test_weather_includes_time_and_source(monkeypatch):
    fetch = AsyncMock(return_value="Pogoda w Warszawie: 12°C")
    monkeypatch.setattr(chat_grounding.AssistantSkill, "get_weather", fetch)
    result = await chat_grounding.current_chat_context("Jaka pogoda w Warszawie?")
    fetch.assert_awaited_once_with("Warszawa")
    assert "Retrieved at:" in result
    assert "https://wttr.in/Warszawa?format=j1" in result
    assert "12°C" in result


@pytest.mark.parametrize(
    ("question", "city"),
    [
        ("Jaka pogoda w Krakowie?", "Kraków"),
        ("Jaka pogoda we Wrocławiu?", "Wrocław"),
        ("Temperatura dla Gdańska", "Gdańsk"),
        ("Jaka pogoda w Katowicach?", "Katowice"),
        ("Jaka pogoda w Berlinie?", "Berlin"),
    ],
)
def test_weather_location_normalizes_known_polish_city_forms(question, city):
    assert chat_grounding._weather_location(question) == city


@pytest.mark.asyncio
async def test_operator_can_change_city_alias_and_news_source_without_code(
    tmp_path, monkeypatch
):
    original = (
        Path(chat_grounding.__file__).resolve().parents[2]
        / "config/chat_public_sources.json"
    )
    data = json.loads(original.read_text(encoding="utf-8"))
    data["weather"]["city_aliases"]["toruniu"] = "Toruń"
    world = data["news"]["regions"]["world"]
    world["search_domains"] = ["example.org"]
    world["article_hosts"] = ["example.org"]
    world["feeds"] = [
        {
            "name": "Example RSS",
            "url": "https://feeds.example.org/world.xml",
            "article_hosts": ["example.org"],
            "article_path_prefix": "/article/",
        }
    ]
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    sources = load_public_sources(path)
    monkeypatch.setattr(chat_grounding, "load_public_sources", lambda: sources)
    assert chat_grounding._weather_location("Jaka pogoda w Toruniu?") == "Toruń"
    assert sources.region_for("wiadomości ze świata").search_domains == ("example.org",)
    assert sources.region_for("wiadomości ze świata").feeds[0].name == "Example RSS"

    queries = []

    class NoSearchResults:
        tavily_client = None

        def search(self, query, max_results):
            queries.append(query)
            return "Nie znaleziono wyników"

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", NoSearchResults)
    feed = AsyncMock(
        return_value=[
            verified_web.NewsHeadline(
                url="https://example.org/article/latest",
                title="Configured source headline",
                published_at="2026-11-14",
            )
        ]
    )
    monkeypatch.setattr(chat_grounding.RSSReaderSkill, "read_feed", feed)
    context = await chat_grounding.current_chat_context("Wiadomości ze świata dziś")
    assert any(query.startswith("site:example.org ") for query in queries)
    assert "Example RSS https://feeds.example.org/world.xml" in context
    assert "Configured source headline" in context


def test_source_configuration_rejects_private_or_untrusted_endpoints(tmp_path):
    original = (
        Path(chat_grounding.__file__).resolve().parents[2]
        / "config/chat_public_sources.json"
    )
    data = json.loads(original.read_text(encoding="utf-8"))
    feed = data["news"]["regions"]["world"]["feeds"][0]
    for bad_url in (
        "http://feeds.example.org/rss",
        "https://127.0.0.1/rss",
        "https://user@feeds.example.org/rss",
    ):
        feed["url"] = bad_url
        path = tmp_path / "sources.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError):
            load_public_sources(path)


def test_current_sources_require_recent_publication(monkeypatch):
    monkeypatch.setattr(chat_grounding, "_today_utc", lambda: date(2026, 11, 14))
    assert chat_grounding._article_is_recent(
        "2026-11-12", "Kto jest prezydentem Polski?"
    )
    assert not chat_grounding._article_is_recent(
        "2026-10-01", "Kto jest prezydentem Polski?"
    )
    assert not chat_grounding._article_is_recent(
        "2026-11-11", "Jakie są dziś wiadomości?"
    )
    assert not chat_grounding._article_is_recent("2026-11-15", "Ile kosztuje benzyna?")


@pytest.mark.asyncio
async def test_search_uses_free_provider_and_requires_urls(monkeypatch):
    monkeypatch.setattr(chat_grounding, "_today_utc", lambda: date(2026, 11, 14))
    seen = []

    class FakeSearch:
        tavily_client = object()

        def search(self, query, max_results):
            seen.append((query, max_results, self.tavily_client))
            return (
                "[1] Invalid\nURL: https://[invalid/article\n"
                "[2] News\nURL: https://www.pap.pl/article\nOpis: story"
            )

        def scrape_text(self, url):
            raise AssertionError("Ordinary chat must not scrape search URLs")

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", FakeSearch)
    article = verified_web.VerifiedArticle(
        url="https://www.pap.pl/article",
        title="Wiadomość",
        published_at="2026-11-14",
        text="Sprawdzona treść z artykułu.",
    )
    fetch = AsyncMock(return_value=article)
    monkeypatch.setattr(chat_grounding, "fetch_verified_article", fetch)
    result = await chat_grounding.current_chat_context("Najnowsze wiadomości")
    assert seen[0] == ("Najnowsze wiadomości", 8, None)
    assert len(seen) == 2
    assert seen[1][0].startswith("site:pap.pl ")
    fetch.assert_awaited_once_with(
        "https://www.pap.pl/article", allowed_hosts=("pap.pl", "gov.pl")
    )
    assert "https://www.pap.pl/article" in result
    assert "Published: 2026-11-14" in result
    assert "Sprawdzona treść" in result

    class Missing(FakeSearch):
        def search(self, query, max_results):
            return "Wystąpił błąd podczas wyszukiwania"

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", Missing)
    result = await chat_grounding.current_chat_context("Najnowsze wiadomości")
    assert "could not be retrieved" in result

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", FakeSearch)
    fetch.return_value = None
    result = await chat_grounding.current_chat_context("Najnowsze wiadomości")
    assert "no dated article" in result


@pytest.mark.asyncio
async def test_targeted_second_search_finds_trusted_news(monkeypatch):
    monkeypatch.setattr(chat_grounding, "_today_utc", lambda: date(2026, 11, 14))
    queries = []

    class FakeSearch:
        tavily_client = object()

        def search(self, query, max_results):
            queries.append(query)
            if query.startswith("site:reuters.com "):
                return "URL: https://www.reuters.com/world/story"
            return "URL: https://untrusted.example/story"

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", FakeSearch)
    article = verified_web.VerifiedArticle(
        url="https://www.reuters.com/world/story",
        title="World news",
        published_at="2026-11-14",
        text="Verified world news content.",
    )
    fetch = AsyncMock(return_value=article)
    monkeypatch.setattr(chat_grounding, "fetch_verified_article", fetch)
    result = await chat_grounding.current_chat_context("Wiadomości ze świata dziś")
    assert len(queries) == 2
    assert queries[1].startswith("site:reuters.com ")
    fetch.assert_awaited_once_with(
        article.url,
        allowed_hosts=("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk"),
    )
    assert article.text in result


@pytest.mark.asyncio
async def test_news_skips_old_candidates_and_reads_next_dated_article(monkeypatch):
    monkeypatch.setattr(chat_grounding, "_today_utc", lambda: date(2026, 11, 14))

    class FakeSearch:
        tavily_client = None

        def search(self, query, max_results):
            if query.startswith("site:pap.pl "):
                return "URL: https://pap.pl/fresh"
            return "URL: https://pap.pl/old1\nURL: https://pap.pl/old2"

    async def fetch(url, *, allowed_hosts):
        fresh = url.endswith("fresh")
        return verified_web.VerifiedArticle(
            url=url,
            title="News",
            published_at="2026-11-14" if fresh else "2026-10-01",
            text="Nowy artykuł" if fresh else "Stary artykuł",
        )

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", FakeSearch)
    monkeypatch.setattr(chat_grounding, "fetch_verified_article", fetch)
    result = await chat_grounding.current_chat_context("Jakie są dziś wiadomości?")
    assert "Nowy artykuł" in result
    assert "Stary artykuł" not in result


@pytest.mark.asyncio
async def test_world_news_uses_labeled_bbc_headlines_when_articles_fail(monkeypatch):
    monkeypatch.setattr(chat_grounding, "_today_utc", lambda: date(2026, 11, 14))

    class NoSearchResults:
        tavily_client = None

        def search(self, query, max_results):
            return "Nie znaleziono wyników"

    monkeypatch.setattr(chat_grounding, "WebSearchSkill", NoSearchResults)
    article = AsyncMock()
    monkeypatch.setattr(chat_grounding, "fetch_verified_article", article)
    feed = AsyncMock(
        return_value=[
            verified_web.NewsHeadline(
                url="https://www.bbc.co.uk/news/articles/example",
                title="World headline",
                published_at="2026-11-14",
            )
        ]
    )
    monkeypatch.setattr(chat_grounding.RSSReaderSkill, "read_feed", feed)
    result = await chat_grounding.current_chat_context(
        "Jakie są dziś wiadomości ze świata?"
    )
    assert feed.await_count == 1
    assert feed.await_args.args[0].name == "BBC News RSS"
    article.assert_not_awaited()
    assert "Only the feed headlines were read" in result
    assert "World headline" in result
    assert "https://www.bbc.co.uk/news/articles/example" in result
    result = await chat_grounding.current_chat_context(
        "Jakie są dziś wiadomości z Polski?"
    )
    assert "could not be retrieved" in result
    feed.assert_awaited_once()


@pytest.mark.asyncio
async def test_bbc_feed_accepts_only_recent_official_article_links():
    feed = b"""<?xml version="1.0"?>
    <rss><channel>
      <item><title>Old</title><link>https://www.bbc.co.uk/news/old</link>
        <pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate></item>
      <item><title>Current headline</title>
        <link>https://www.bbc.co.uk/news/articles/current</link>
        <pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item>
      <item><title>Forged</title><link>https://bbc.co.uk.evil.test/news/article</link>
        <pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item>
    </channel></rss>"""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "application/rss+xml"}, content=feed
        )
    )
    headlines = await verified_web.fetch_rss_headlines(
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        article_hosts=("bbc.co.uk", "bbc.com"),
        article_path_prefix="/news/",
        today=date(2026, 11, 14),
        transport=transport,
    )
    assert len(headlines) == 1
    assert headlines[0].title == "Current headline"
    assert headlines[0].published_at == "2026-11-14"


@pytest.mark.asyncio
async def test_rss_reader_accepts_a_different_configured_source():
    feed = b"""<rss><channel>
      <item><title>Regional headline</title>
        <link>https://news.example.org/article/42</link>
        <pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item>
      <item><title>Wrong host</title>
        <link>https://other.example.org/article/42</link>
        <pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item>
    </channel></rss>"""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "application/rss+xml"}, content=feed
        )
    )
    headlines = await verified_web.fetch_rss_headlines(
        "https://feeds.example.org/region.xml",
        article_hosts=("news.example.org",),
        article_path_prefix="/article/",
        today=date(2026, 11, 14),
        transport=transport,
    )
    assert [item.title for item in headlines] == ["Regional headline"]


@pytest.mark.asyncio
async def test_bbc_feed_rejects_oversized_or_entity_payloads():
    for payload in (
        b"x" * (verified_web.MAX_FEED_BYTES + 1),
        b'<!DOCTYPE rss [<!ENTITY bogus "bad">]><rss/>',
    ):
        transport = httpx.MockTransport(
            lambda _, body=payload: httpx.Response(
                200, headers={"content-type": "application/rss+xml"}, content=body
            )
        )
        assert (
            await verified_web.fetch_rss_headlines(
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                article_hosts=("bbc.co.uk", "bbc.com"),
                article_path_prefix="/news/",
                today=date(2026, 11, 14),
                transport=transport,
            )
            == []
        )


@pytest.mark.asyncio
async def test_wiki_context_and_normal_chat_integration(monkeypatch):
    source = SimpleNamespace(
        title="Maria Skłodowska-Curie",
        url="https://pl.wikipedia.org/wiki/Maria_Sk%C5%82odowska-Curie",
        extract="Polska uczona.",
        retrieved_at="2026-11-14T12:00:00+00:00",
    )
    wiki = AsyncMock(return_value=[source])
    monkeypatch.setattr(chat_grounding, "search_polish_wikipedia", wiki)
    store = SimpleNamespace(get_history=lambda _session_id: [])
    vectors = AsyncMock()
    request = SimpleChatRequest(
        content="Kim była Maria Skłodowska-Curie?",
        session_id="test",
        studio_normal=True,
    )
    prepared, context = await studio_normal_chat.prepare_studio_normal(
        request, store, vectors
    )
    wiki.assert_awaited_once_with(request.content, limit=2)
    vectors.assert_not_awaited()
    assert source.url in context
    assert "Polska uczona" in context
    assert prepared.think is False


@pytest.mark.asyncio
async def test_note_question_never_leaves_normal_chat(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(chat_grounding, "search_polish_wikipedia", fetch)
    assert (
        await chat_grounding.current_chat_context(
            "Kim był autor według notatki?", use_notes=True
        )
        == ""
    )
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_wikipedia_is_reported(monkeypatch):
    monkeypatch.setattr(
        chat_grounding, "search_polish_wikipedia", AsyncMock(return_value=[])
    )
    result = await chat_grounding.current_chat_context("Co to jest biologia?")
    assert "could not be retrieved" in result


@pytest.mark.asyncio
async def test_source_too_large_never_falls_back_to_unguarded_answer(monkeypatch):
    monkeypatch.setattr(studio_normal_chat.SETTINGS, "OLLAMA_CONTEXT_LENGTH", 400)
    monkeypatch.setattr(
        studio_normal_chat,
        "current_chat_context",
        AsyncMock(return_value="source " * 1000),
    )
    request = SimpleChatRequest(
        content="Jakie są dziś wiadomości?", session_id="test", studio_normal=True
    )
    store = SimpleNamespace(get_history=lambda _session_id: [])
    _, context = await studio_normal_chat.prepare_studio_normal(
        request, store, AsyncMock()
    )
    assert "Fresh source context did not fit" in context


@pytest.mark.asyncio
async def test_verified_news_fetch_has_bounds_and_date(monkeypatch):
    monkeypatch.setattr(verified_web, "_host_has_only_public_addresses", lambda _: True)
    html = (
        '<html><head><meta property="article:published_time" '
        'content="2026-11-14T08:00:00Z"></head><body><article>'
        "<h1>Ważna informacja</h1><p>" + "Treść artykułu. " * 8 + "</p>"
        "</article></body></html>"
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": "text/html"}, text=html)
    )
    result = await verified_web.fetch_verified_article(
        "https://www.pap.pl/wiadomosc", allowed_hosts=("pap.pl",), transport=transport
    )
    assert result is not None
    assert result.published_at == "2026-11-14"
    assert "Treść artykułu" in result.text


@pytest.mark.asyncio
async def test_verified_news_rejects_redirect_large_body_and_private_target(
    monkeypatch,
):
    monkeypatch.setattr(verified_web, "_host_has_only_public_addresses", lambda _: True)
    assert not verified_web.trusted_news_url(
        "https://pap.pl.evil.test/story", ("pap.pl",)
    )
    assert not verified_web.trusted_news_url(
        "https://pap.pl@evil.test/story", ("pap.pl",)
    )
    assert not verified_web.trusted_news_url("http://pap.pl/story", ("pap.pl",))
    assert not verified_web.trusted_news_url("https://pap.pl:444/story", ("pap.pl",))
    redirect = httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1/"})
    )
    assert (
        await verified_web.fetch_verified_article(
            "https://pap.pl/story", allowed_hosts=("pap.pl",), transport=redirect
        )
        is None
    )
    huge = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 260_000
        )
    )
    assert (
        await verified_web.fetch_verified_article(
            "https://pap.pl/story", allowed_hosts=("pap.pl",), transport=huge
        )
        is None
    )
    undated = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<html><body><header><time datetime="2026-11-14">Today</time></header><article><h1>News</h1><p>'
            + "A" * 120
            + "</p></article></body></html>",
        )
    )
    assert (
        await verified_web.fetch_verified_article(
            "https://pap.pl/story", allowed_hosts=("pap.pl",), transport=undated
        )
        is None
    )
    monkeypatch.setattr(
        verified_web, "_host_has_only_public_addresses", lambda _: False
    )
    assert (
        await verified_web.fetch_verified_article(
            "https://pap.pl/story", allowed_hosts=("pap.pl",), transport=huge
        )
        is None
    )
