"""Testy jednostkowe dla WebSearchSkill."""

from unittest.mock import MagicMock, patch

import pytest

from venom_core.execution.skills.web_skill import WebSearchSkill


@pytest.fixture
def web_skill():
    """Fixture dla WebSearchSkill."""
    return WebSearchSkill()


class TestWebSearchSkill:
    """Testy dla WebSearchSkill."""

    @patch("venom_core.execution.skills.web_skill.DDGS")
    def test_search_success(self, mock_ddgs, web_skill):
        """Test udanego wyszukiwania."""
        # Mock wyników wyszukiwania
        mock_results = [
            {
                "title": "Test Result 1",
                "href": "https://example.com/1",
                "body": "Description 1",
            },
            {
                "title": "Test Result 2",
                "href": "https://example.com/2",
                "body": "Description 2",
            },
        ]

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = mock_results
        mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance

        # Wykonaj wyszukiwanie
        result = web_skill.search("test query")

        # Sprawdź wynik
        assert "Test Result 1" in result
        assert "https://example.com/1" in result
        assert "Description 1" in result
        assert "Test Result 2" in result
        assert "2 wyników" in result

    @patch("venom_core.execution.skills.web_skill.DDGS")
    def test_search_no_results(self, mock_ddgs, web_skill):
        """Test wyszukiwania bez wyników."""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance

        result = web_skill.search("nonexistent query")

        assert "Nie znaleziono wyników" in result

    @patch("venom_core.execution.skills.web_skill.DDGS")
    def test_search_exception(self, mock_ddgs, web_skill):
        """Test obsługi błędu podczas wyszukiwania."""
        mock_ddgs.return_value.__enter__.side_effect = Exception("Network error")

        result = web_skill.search("test query")

        assert "Wystąpił błąd" in result
        assert "Network error" in result

    @patch("venom_core.execution.skills.web_skill.trafilatura")
    def test_scrape_text_success_trafilatura(self, mock_trafilatura, web_skill):
        """Test udanego scrapowania przez trafilatura."""
        mock_trafilatura.fetch_url.return_value = "<html>content</html>"
        mock_trafilatura.extract.return_value = "Extracted clean text content"

        result = web_skill.scrape_text("https://example.com")

        assert "Extracted clean text content" in result
        assert "https://example.com" in result

    @patch("venom_core.execution.skills.web_skill.requests")
    @patch("venom_core.execution.skills.web_skill.trafilatura")
    def test_scrape_text_fallback_beautifulsoup(
        self, mock_trafilatura, mock_requests, web_skill
    ):
        """Test fallbacku do BeautifulSoup gdy trafilatura zawodzi."""
        # Trafilatura zwraca None
        mock_trafilatura.fetch_url.return_value = None

        # Mock requests
        mock_response = MagicMock()
        mock_response.content = b"<html><body><p>Test content</p></body></html>"
        mock_requests.get.return_value = mock_response

        result = web_skill.scrape_text("https://example.com")

        assert "Test content" in result

    @patch("venom_core.execution.skills.web_skill.trafilatura")
    def test_scrape_text_timeout(self, mock_trafilatura, web_skill):
        """Test obsługi timeoutu."""
        mock_trafilatura.fetch_url.return_value = None

        with patch(
            "venom_core.execution.skills.web_skill.requests.get"
        ) as mock_get:
            from requests.exceptions import Timeout

            mock_get.side_effect = Timeout("Timeout")

            result = web_skill.scrape_text("https://example.com")

            assert "Przekroczono limit czasu" in result

    @patch("venom_core.execution.skills.web_skill.DDGS")
    @patch.object(WebSearchSkill, "scrape_text")
    def test_search_and_scrape(self, mock_scrape, mock_ddgs, web_skill):
        """Test wyszukiwania i scrapowania."""
        # Mock wyników wyszukiwania
        mock_results = [
            {
                "title": "Result 1",
                "href": "https://example.com/1",
                "body": "Description 1",
            },
            {
                "title": "Result 2",
                "href": "https://example.com/2",
                "body": "Description 2",
            },
        ]

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = mock_results
        mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance

        # Mock scrapowania
        mock_scrape.return_value = "Treść ze strony https://example.com/1:\n\nScraped content"

        result = web_skill.search_and_scrape("test query", num_sources=2)

        assert "Result 1" in result
        assert "https://example.com/1" in result
        assert "Scraped content" in result
        assert mock_scrape.call_count == 2  # Powinno wywołać dla obu wyników

    @patch("venom_core.execution.skills.web_skill.trafilatura")
    def test_scrape_text_max_length(self, mock_trafilatura, web_skill):
        """Test ograniczenia długości tekstu."""
        # Wygeneruj długi tekst
        long_text = "A" * 10000

        mock_trafilatura.fetch_url.return_value = "<html>content</html>"
        mock_trafilatura.extract.return_value = long_text

        result = web_skill.scrape_text("https://example.com")

        # Sprawdź czy tekst został obcięty
        assert "tekst obcięty" in result
        assert len(result) < len(long_text) + 1000  # +1000 dla metadanych
