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

    @patch("venom_core.execution.skills.web_skill.httpx")
    @patch("venom_core.execution.skills.web_skill.trafilatura")
    def test_scrape_text_fallback_beautifulsoup(
        self, mock_trafilatura, mock_httpx, web_skill
    ):
        """Test fallbacku do BeautifulSoup gdy trafilatura zawodzi."""
        # Trafilatura zwraca None
        mock_trafilatura.fetch_url.return_value = None

        # Mock httpx
        mock_response = MagicMock()
        mock_response.content = b"<html><body><p>Test content</p></body></html>"
        mock_httpx.get.return_value = mock_response

        result = web_skill.scrape_text("https://example.com")

        assert "Test content" in result

    @patch("venom_core.execution.skills.web_skill.trafilatura")
    @patch("venom_core.execution.skills.web_skill.httpx")
    def test_scrape_text_timeout(self, mock_httpx, mock_trafilatura, web_skill):
        """Test obsługi timeoutu."""
        mock_trafilatura.fetch_url.return_value = None

        # Mock httpx.TimeoutException
        import httpx

        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_httpx.get.side_effect = httpx.TimeoutException("Timeout")

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
        mock_scrape.return_value = (
            "Treść ze strony https://example.com/1:\n\nScraped content"
        )

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

    @patch("venom_core.execution.skills.web_skill.SETTINGS")
    @patch("venom_core.execution.skills.web_skill.DDGS")
    def test_low_cost_routing_local_mode(self, mock_ddgs, mock_settings):
        """Test LOW-COST routing - tryb LOCAL wymusza DuckDuckGo nawet gdy Tavily jest dostępny."""
        # Skonfiguruj mock SETTINGS
        mock_settings.AI_MODE = "LOCAL"
        
        # Mock wyników DuckDuckGo
        mock_results = [
            {
                "title": "Test Result",
                "href": "https://example.com",
                "body": "Description",
            }
        ]
        
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = mock_results
        mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance
        
        # Utwórz WebSearchSkill z mock Tavily client (dostępny, ale nie powinien być użyty)
        with patch("venom_core.execution.skills.web_skill.extract_secret_value") as mock_extract:
            mock_extract.return_value = "fake-tavily-key"
            with patch("venom_core.execution.skills.web_skill.TavilyClient") as mock_tavily:
                mock_tavily_instance = MagicMock()
                mock_tavily.return_value = mock_tavily_instance
                
                skill = WebSearchSkill()
                
                # Upewnij się, że Tavily jest dostępny
                assert skill.tavily_client is not None
                
                # Wykonaj wyszukiwanie
                result = skill.search("test query")
                
                # Sprawdź że użyto DuckDuckGo (nie Tavily)
                assert "DuckDuckGo" in result
                mock_ddgs_instance.text.assert_called_once()
                # Tavily nie powinien być wywołany
                mock_tavily_instance.search.assert_not_called()
    
    @patch("venom_core.execution.skills.web_skill.SETTINGS")
    @patch("venom_core.execution.skills.web_skill.DDGS")
    def test_low_cost_routing_eco_mode(self, mock_ddgs, mock_settings):
        """Test LOW-COST routing - tryb ECO wymusza DuckDuckGo."""
        # Skonfiguruj mock SETTINGS
        mock_settings.AI_MODE = "ECO"
        
        # Mock wyników DuckDuckGo
        mock_results = [
            {
                "title": "Test Result",
                "href": "https://example.com",
                "body": "Description",
            }
        ]
        
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = mock_results
        mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance
        
        # Utwórz WebSearchSkill
        with patch("venom_core.execution.skills.web_skill.extract_secret_value") as mock_extract:
            mock_extract.return_value = "fake-tavily-key"
            with patch("venom_core.execution.skills.web_skill.TavilyClient") as mock_tavily:
                mock_tavily_instance = MagicMock()
                mock_tavily.return_value = mock_tavily_instance
                
                skill = WebSearchSkill()
                
                # Wykonaj wyszukiwanie
                result = skill.search("test query")
                
                # Sprawdź że użyto DuckDuckGo (nie Tavily)
                assert "DuckDuckGo" in result
                mock_ddgs_instance.text.assert_called_once()
                # Tavily nie powinien być wywołany
                mock_tavily_instance.search.assert_not_called()
