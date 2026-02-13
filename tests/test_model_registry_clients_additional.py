"""Additional coverage tests for model_registry_clients helpers and clients."""

from __future__ import annotations

import html
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core import model_registry_clients as mrc


def test_normalize_hf_papers_month_invalid_falls_back_current():
    value = mrc._normalize_hf_papers_month("2024-99")
    assert len(value) == 7
    assert value[4] == "-"


def test_parse_hf_blog_feed_strips_html_and_limits_items():
    payload = """<?xml version="1.0"?>
    <rss><channel>
      <item><title>A</title><link>https://a</link><description><![CDATA[<b>x</b>]]></description><pubDate>now</pubDate></item>
      <item><title>B</title><link>https://b</link><description>plain</description><pubDate>later</pubDate></item>
    </channel></rss>"""
    parsed = mrc._parse_hf_blog_feed(payload, limit=1)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "A"
    assert parsed[0]["summary"] == "x"


def test_parse_hf_papers_html_invalid_and_valid_paths():
    assert mrc._parse_hf_papers_html("<html></html>", limit=3) == []

    props = {
        "dailyPapers": [
            {
                "title": "Paper 1",
                "summary": "S1",
                "publishedAt": "2026-01-01",
                "paper": {"id": "p1", "authors": [{"name": "A1"}]},
            }
        ]
    }
    raw = html.escape(__import__("json").dumps(props))
    payload = f'<div data-target="DailyPapers" data-props="{raw}"></div>'
    parsed = mrc._parse_hf_papers_html(payload, limit=5)
    assert len(parsed) == 1
    assert parsed[0]["url"] == "https://huggingface.co/papers/p1"
    assert parsed[0]["authors"] == ["A1"]


def test_extract_ollama_helpers():
    assert mrc._extract_ollama_model_name("/library/llama3.1") == "llama3.1"
    assert mrc._extract_ollama_model_name("/other/x") is None

    anchor = MagicMock()
    anchor.find.return_value = None
    anchor.get_text.return_value = "llama3.1 compact model"
    assert mrc._extract_ollama_description(anchor, "llama3.1") == "compact model"


def test_parse_ollama_search_html_with_fake_bs4(monkeypatch):
    class _Anchor:
        def __init__(self, href: str, text: str):
            self._href = href
            self._text = text

        def get(self, key):
            return self._href if key == "href" else None

        def find(self, _name):
            return None

        def get_text(self, *_args, **_kwargs):
            return self._text

    class _Soup:
        def __init__(self, _payload, _parser):
            pass

        def find_all(self, _tag, href=True):
            _ = href
            return [
                _Anchor("/library/phi4-mini", "phi4-mini compact"),
                _Anchor("/library/phi4-mini", "duplicate"),
                _Anchor("/library/qwen2.5", "qwen2.5 coder"),
            ]

    fake_bs4 = SimpleNamespace(BeautifulSoup=_Soup)
    monkeypatch.setitem(__import__("sys").modules, "bs4", fake_bs4)

    parsed = mrc._parse_ollama_search_html("<html></html>", limit=5)
    assert [item["name"] for item in parsed] == ["phi4-mini", "qwen2.5"]


@pytest.mark.asyncio
async def test_ollama_client_remove_model_paths():
    client = mrc.OllamaClient()

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(return_value=SimpleNamespace(returncode=0, stderr="", stdout="")),
    ):
        assert await client.remove_model("ok-model") is True

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(
            return_value=SimpleNamespace(returncode=1, stderr="err", stdout="")
        ),
    ):
        assert await client.remove_model("bad-model") is False

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(
            side_effect=subprocess.TimeoutExpired(cmd="ollama rm", timeout=30)
        ),
    ):
        assert await client.remove_model("timeout-model") is False

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=FileNotFoundError())):
        assert await client.remove_model("missing-bin") is False


@pytest.mark.asyncio
async def test_ollama_client_pull_model_without_streams_returns_false():
    client = mrc.OllamaClient()

    process = SimpleNamespace(
        stdout=None,
        stderr=None,
        returncode=0,
        kill=lambda: None,
        wait=AsyncMock(return_value=0),
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
        assert await client.pull_model("m1") is False


@pytest.mark.asyncio
async def test_hf_fetch_papers_month_handles_redirect():
    client = mrc.HuggingFaceClient()

    first = MagicMock()
    first.is_redirect = True
    first.headers = {"location": "/papers/month/2026-01"}
    first.raise_for_status = MagicMock()
    first.text = ""

    second = MagicMock()
    second.is_redirect = False
    second.headers = {}
    second.raise_for_status = MagicMock()
    second.text = '<div data-target="DailyPapers" data-props="{&quot;dailyPapers&quot;: []}"></div>'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=[first, second])
        mock_client_class.return_value = mock_client

        parsed = await client.fetch_papers_month(limit=3, month="2026-01")
        assert parsed == []
        assert mock_client.get.await_count == 2
