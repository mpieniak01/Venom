import html
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from venom_core.core.model_registry_clients import (
    HuggingFaceClient,
    OllamaClient,
    _normalize_hf_papers_month,
    _parse_hf_papers_html,
)
from venom_core.main import app


@pytest.fixture
def mock_hf_response():
    return [
        {
            "id": "meta-llama/Meta-Llama-3-8B",
            "modelId": "meta-llama/Meta-Llama-3-8B",
            "likes": 1234,
            "downloads": 5678,
            "tags": ["llama", "text-generation"],
            "pipeline_tag": "text-generation",
        }
    ]


@pytest.fixture
def mock_ollama_html():
    return """
    <html>
        <body>
            <div id="search-results">
                <li class="flex items-baseline border-b border-neutral-200 py-6">
                    <div class="flex-1 overflow-hidden min-w-0">
                        <a href="/library/llama3" class="group">
                            <h2 class="flex items-center mb-3">
                                <span class="text-lg font-bold">llama3</span>
                                <span class="bg-[#ddf4ff] text-[#0d74ce] text-xs py-0.5 px-2 rounded-full ml-2">8B</span>
                            </h2>
                            <p class="max-w-xl text-neutral-500 mb-4">The most capable open/weight models.</p>
                        </a>
                        <div class="flex items-center space-x-5 text-xs font-medium text-neutral-500">
                           <span><span x-test-pulls>100K</span> pulls</span>
                           <span><span x-test-updated>2 days ago</span></span>
                        </div>
                    </div>
                </li>
            </div>
        </body>
    </html>
    """


@pytest.mark.asyncio
async def test_hf_search_success(mock_hf_response):
    client = HuggingFaceClient()
    # Mock return object for client.get
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_hf_response
    mock_response.raise_for_status.return_value = None

    # Patch AsyncClient class to support context manager
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        results = await client.search_models("llama3", limit=1)

        assert len(results) == 1
        assert results[0]["modelId"] == "meta-llama/Meta-Llama-3-8B"
        # HF Client returns raw API response, provider is added later by Registry
        assert results[0]["likes"] == 1234
        assert results[0]["downloads"] == 5678


@pytest.mark.asyncio
async def test_ollama_search_scraping_success(mock_ollama_html):
    client = OllamaClient()
    # Mock return object for client.get
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_ollama_html
    mock_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        results = await client.search_models("llama3", limit=1)

        assert len(results) >= 1
        model = results[0]
        # Result is a dict, not object. Key is 'name' as per _parse_ollama_search_html
        assert model["name"] == "llama3"
        assert model["provider"] == "ollama"
        assert "Meta-Llama-3-8B" not in model["name"]
        assert model["description"].startswith("The most capable")


@pytest.mark.asyncio
async def test_hf_fetch_papers_month_uses_validated_month_in_url():
    client = HuggingFaceClient()
    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.headers = {}
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html></html>"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with patch(
            "venom_core.core.model_registry_clients._parse_hf_papers_html",
            return_value=[{"title": "ok"}],
        ) as mock_parser:
            results = await client.fetch_papers_month(limit=10, month="2025-01")

    first_url = mock_client.get.await_args_list[0].args[0]
    assert first_url == "https://huggingface.co/papers/month/2025-01"
    assert results == [{"title": "ok"}]
    mock_parser.assert_called_once_with("<html></html>", 10)


@pytest.mark.asyncio
async def test_hf_fetch_papers_month_rejects_invalid_month_for_url_path():
    client = HuggingFaceClient()
    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.headers = {}
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html></html>"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with patch(
            "venom_core.core.model_registry_clients._parse_hf_papers_html",
            return_value=[],
        ):
            await client.fetch_papers_month(limit=5, month="../../etc/passwd")

    first_url = mock_client.get.await_args_list[0].args[0]
    assert re.fullmatch(
        r"https://huggingface\.co/papers/month/\d{4}-\d{2}",
        first_url,
    )


def test_parse_hf_papers_html_returns_empty_when_section_missing():
    assert _parse_hf_papers_html("<html></html>", limit=3) == []


def test_normalize_hf_papers_month_rejects_invalid_calendar_month():
    normalized = _normalize_hf_papers_month("2025-13")
    assert re.fullmatch(r"\d{4}-\d{2}", normalized)
    assert normalized != "2025-13"


def test_parse_hf_papers_html_returns_empty_when_props_json_invalid():
    payload = (
        '<div data-target="DailyPapers" data-props="'
        + html.escape("{bad-json", quote=True)
        + '"></div>'
    )
    assert _parse_hf_papers_html(payload, limit=3) == []


def test_parse_hf_papers_html_returns_empty_when_data_not_dict():
    payload = (
        '<div data-target="DailyPapers" data-props="'
        + html.escape('["x"]', quote=True)
        + '"></div>'
    )
    assert _parse_hf_papers_html(payload, limit=3) == []


def test_parse_hf_papers_html_returns_empty_when_daily_papers_not_list():
    payload = (
        '<div data-target="DailyPapers" data-props="'
        + html.escape(json.dumps({"dailyPapers": {"paper": {}}}), quote=True)
        + '"></div>'
    )
    assert _parse_hf_papers_html(payload, limit=3) == []


def test_parse_hf_papers_html_parses_expected_fields():
    raw = json.dumps(
        {
            "dailyPapers": [
                {
                    "title": "Entry title",
                    "summary": "Entry summary",
                    "publishedAt": "2025-01-02",
                    "paper": {
                        "id": "paper-1",
                        "authors": [{"name": "Alice"}, {"name": ""}, {}],
                    },
                }
            ]
        }
    )
    payload = (
        '<div data-target="DailyPapers" data-props="'
        + html.escape(raw, quote=True)
        + '"></div>'
    )
    parsed = _parse_hf_papers_html(payload, limit=1)
    assert len(parsed) == 1
    assert parsed[0]["url"] == "https://huggingface.co/papers/paper-1"
    assert parsed[0]["authors"] == ["Alice"]
    assert parsed[0]["title"] == "Entry title"


def test_api_search_endpoint():
    mock_registry_results = {
        "models": [
            {
                "model_name": "test-model",
                "provider": "ollama",
                "description": "Test description",
                "likes": 10,
                "downloads": 50,
                "tags": [],
            }
        ],
        "count": 1,
        "error": None,
    }

    # Patch get_model_registry to return a mock registry
    with patch(
        "venom_core.api.routes.models_registry.get_model_registry"
    ) as mock_get_registry:
        mock_registry = AsyncMock()
        mock_registry.search_external_models.return_value = mock_registry_results
        mock_get_registry.return_value = mock_registry

        client = TestClient(app)
        response = client.get("/api/v1/models/search?query=test&provider=ollama")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["models"]) == 1
        assert data["models"][0]["model_name"] == "test-model"


def test_api_search_validation():
    # Test min_length validation
    client = TestClient(app)
    response = client.get("/api/v1/models/search?query=a&provider=huggingface")
    assert response.status_code == 422
