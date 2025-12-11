"""Testy jednostkowe dla ulepszeń skills (FileSkill, BrowserSkill, PlatformSkill, WebSkill)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venom_core.execution.skills.browser_skill import BrowserSkill
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.platform_skill import PlatformSkill
from venom_core.execution.skills.web_skill import WebSearchSkill


# ===== FileSkill: Test recursive listing =====


@pytest.fixture
def temp_workspace_with_structure():
    """Fixture dla workspace z zagnieżdżoną strukturą katalogów."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        
        # Utwórz strukturę:
        # root/
        #   file1.txt
        #   dir1/
        #     file2.txt
        #     dir2/
        #       file3.txt
        #       dir3/
        #         file4.txt (poziom 3)
        #         dir4/
        #           file5.txt (poziom 4 - nie powinien być widoczny)
        
        (base / "file1.txt").write_text("content1")
        (base / "dir1").mkdir()
        (base / "dir1" / "file2.txt").write_text("content2")
        (base / "dir1" / "dir2").mkdir()
        (base / "dir1" / "dir2" / "file3.txt").write_text("content3")
        (base / "dir1" / "dir2" / "dir3").mkdir()
        (base / "dir1" / "dir2" / "dir3" / "file4.txt").write_text("content4")
        (base / "dir1" / "dir2" / "dir3" / "dir4").mkdir()
        (base / "dir1" / "dir2" / "dir3" / "dir4" / "file5.txt").write_text("content5")
        
        yield tmpdir


def test_file_skill_list_files_recursive_false(temp_workspace_with_structure):
    """Test listowania nierekurencyjnego (domyślne zachowanie)."""
    skill = FileSkill(workspace_root=temp_workspace_with_structure)
    result = skill.list_files(".", recursive=False)
    
    # Powinien pokazać tylko elementy w root
    assert "file1.txt" in result
    assert "dir1" in result
    # Nie powinien pokazywać zagnieżdżonych elementów
    assert "file2.txt" not in result
    assert "dir2" not in result


def test_file_skill_list_files_recursive_true(temp_workspace_with_structure):
    """Test listowania rekurencyjnego."""
    skill = FileSkill(workspace_root=temp_workspace_with_structure)
    result = skill.list_files(".", recursive=True)
    
    # Powinien pokazać wszystkie elementy do poziomu 3
    assert "file1.txt" in result
    assert "dir1" in result
    assert "file2.txt" in result
    assert "dir2" in result
    assert "file3.txt" in result
    assert "dir3" in result
    assert "file4.txt" in result  # Poziom 3
    
    # Nie powinien pokazywać poziomu 4+
    assert "dir4" not in result
    assert "file5.txt" not in result


def test_file_skill_list_files_recursive_depth_limit(temp_workspace_with_structure):
    """Test limitu głębokości rekurencyjnego listowania."""
    skill = FileSkill(workspace_root=temp_workspace_with_structure)
    result = skill.list_files(".", recursive=True)
    
    # Sprawdź że nagłówek zawiera informację o max głębokości
    assert "max 3 poziomy" in result
    
    # Sprawdź że poziom 3 jest widoczny, ale nie 4
    assert "file4.txt" in result
    assert "file5.txt" not in result


# ===== BrowserSkill: Test automatic screenshots =====


@pytest.mark.asyncio
async def test_browser_click_element_creates_screenshot():
    """Test czy click_element tworzy automatyczny screenshot."""
    from unittest.mock import AsyncMock
    
    skill = BrowserSkill()
    
    # Mock _ensure_browser aby nie uruchamiała prawdziwej przeglądarki
    skill._ensure_browser = AsyncMock()
    
    # Mock przeglądarki z async methods
    skill._page = MagicMock()
    skill._page.click = AsyncMock()
    skill._page.wait_for_timeout = AsyncMock()
    skill._page.screenshot = AsyncMock()
    skill._browser = MagicMock()  # Mark as initialized
    
    result = await skill.click_element("#test-button")
    
    # Sprawdź czy wywołano screenshot
    skill._page.screenshot.assert_called_once()
    
    # Sprawdź komunikat zwrotny
    assert "✅" in result
    assert "Zrzut ekranu weryfikacyjny:" in result
    assert "click_verification_" in result


@pytest.mark.asyncio
async def test_browser_fill_form_creates_screenshot():
    """Test czy fill_form tworzy automatyczny screenshot."""
    from unittest.mock import AsyncMock
    
    skill = BrowserSkill()
    
    # Mock _ensure_browser aby nie uruchamiała prawdziwej przeglądarki
    skill._ensure_browser = AsyncMock()
    
    # Mock przeglądarki z async methods
    skill._page = MagicMock()
    skill._page.fill = AsyncMock()
    skill._page.wait_for_timeout = AsyncMock()
    skill._page.screenshot = AsyncMock()
    skill._browser = MagicMock()  # Mark as initialized
    
    result = await skill.fill_form("#username", "test_user")
    
    # Sprawdź czy wywołano screenshot
    skill._page.screenshot.assert_called_once()
    
    # Sprawdź komunikat zwrotny
    assert "✅" in result
    assert "Zrzut ekranu weryfikacyjny:" in result
    assert "fill_verification_" in result


@pytest.mark.asyncio
async def test_browser_screenshot_path_format():
    """Test formatu ścieżki screenshota."""
    from unittest.mock import AsyncMock
    
    skill = BrowserSkill()
    
    # Mock _ensure_browser aby nie uruchamiała prawdziwej przeglądarki
    skill._ensure_browser = AsyncMock()
    
    # Mock przeglądarki z async methods
    skill._page = MagicMock()
    skill._page.click = AsyncMock()
    skill._page.wait_for_timeout = AsyncMock()
    skill._page.screenshot = AsyncMock()
    skill._browser = MagicMock()  # Mark as initialized
    
    result = await skill.click_element("#test")
    
    # Sprawdź czy ścieżka zawiera timestamp
    assert "click_verification_" in result
    assert ".png" in result
    assert str(skill.screenshots_dir) in result


# ===== PlatformSkill: Test configuration status =====


def test_platform_skill_get_configuration_status_all_configured():
    """Test raportu konfiguracji gdy wszystko jest skonfigurowane."""
    with patch("venom_core.execution.skills.platform_skill.SETTINGS") as mock_settings:
        # Mock wszystkich konfiguracji
        mock_settings.GITHUB_TOKEN.get_secret_value.return_value = "test_token"
        mock_settings.GITHUB_REPO_NAME = "test/repo"
        mock_settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = "https://slack.com/webhook"
        mock_settings.DISCORD_WEBHOOK_URL.get_secret_value.return_value = "https://discord.com/webhook"
        
        skill = PlatformSkill()
        
        # Mock GitHub client
        skill.github_client = MagicMock()
        skill.github_client.get_user.return_value.login = "test_user"
        
        result = skill.get_configuration_status()
        
        # Sprawdź raport
        assert "[Konfiguracja PlatformSkill]" in result
        assert "GitHub: ✅ AKTYWNY" in result
        assert "Slack: ✅ AKTYWNY" in result
        assert "Discord: ✅ AKTYWNY" in result


def test_platform_skill_get_configuration_status_none_configured():
    """Test raportu konfiguracji gdy nic nie jest skonfigurowane."""
    with patch("venom_core.execution.skills.platform_skill.SETTINGS") as mock_settings:
        # Mock brak konfiguracji
        mock_settings.GITHUB_TOKEN.get_secret_value.return_value = ""
        mock_settings.GITHUB_REPO_NAME = ""
        mock_settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = ""
        mock_settings.DISCORD_WEBHOOK_URL.get_secret_value.return_value = ""
        
        skill = PlatformSkill()
        result = skill.get_configuration_status()
        
        # Sprawdź raport
        assert "GitHub: ❌ BRAK KONFIGURACJI" in result
        assert "GITHUB_TOKEN" in result
        assert "Slack: ❌ BRAK KLUCZA" in result
        assert "Discord: ❌ BRAK KLUCZA" in result


def test_platform_skill_get_configuration_status_partial():
    """Test raportu konfiguracji z częściową konfiguracją."""
    with patch("venom_core.execution.skills.platform_skill.SETTINGS") as mock_settings:
        # Mock częściowej konfiguracji - tylko GitHub
        mock_settings.GITHUB_TOKEN.get_secret_value.return_value = "test_token"
        mock_settings.GITHUB_REPO_NAME = "test/repo"
        mock_settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = ""
        mock_settings.DISCORD_WEBHOOK_URL.get_secret_value.return_value = ""
        
        skill = PlatformSkill()
        
        # Mock GitHub client
        skill.github_client = MagicMock()
        skill.github_client.get_user.return_value.login = "test_user"
        
        result = skill.get_configuration_status()
        
        # Sprawdź raport
        assert "GitHub: ✅ AKTYWNY" in result or "GitHub: ⚠️" in result
        assert "Slack: ❌ BRAK KLUCZA" in result
        assert "Discord: ❌ BRAK KLUCZA" in result


# ===== WebSkill: Test Tavily integration =====


def test_web_skill_initialization_without_tavily():
    """Test inicjalizacji WebSkill bez Tavily API Key."""
    with patch("venom_core.execution.skills.web_skill.SETTINGS") as mock_settings:
        mock_settings.TAVILY_API_KEY.get_secret_value.return_value = ""
        
        skill = WebSearchSkill()
        
        # Powinien użyć DuckDuckGo jako fallback
        assert skill.tavily_client is None


def test_web_skill_initialization_with_tavily():
    """Test inicjalizacji WebSkill z Tavily API Key."""
    import sys
    
    with patch("venom_core.execution.skills.web_skill.SETTINGS") as mock_settings:
        with patch("venom_core.execution.skills.web_skill.extract_secret_value") as mock_extract:
            mock_extract.return_value = "test_api_key"
            
            # Patch tavily import before it's imported
            with patch.dict('sys.modules', {'tavily': MagicMock()}):
                mock_tavily_module = sys.modules['tavily']
                mock_tavily_client = MagicMock()
                mock_tavily_module.TavilyClient = mock_tavily_client
                
                skill = WebSearchSkill()
                
                # Powinien zainicjalizować klienta Tavily
                mock_tavily_client.assert_called_once_with(api_key="test_api_key")


def test_web_skill_search_uses_tavily_when_available():
    """Test czy search używa Tavily gdy jest dostępny."""
    import sys
    
    with patch("venom_core.execution.skills.web_skill.extract_secret_value") as mock_extract:
        mock_extract.return_value = "test_api_key"
        
        # Patch tavily import before it's imported
        with patch.dict('sys.modules', {'tavily': MagicMock()}):
            mock_tavily_module = sys.modules['tavily']
            
            # Mock odpowiedzi Tavily
            mock_client = MagicMock()
            mock_client.search.return_value = {
                "answer": "Test AI answer",
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "content": "Test content",
                    }
                ],
            }
            mock_tavily_module.TavilyClient.return_value = mock_client
            
            skill = WebSearchSkill()
            result = skill.search("test query", max_results=5)
            
            # Sprawdź czy użyto Tavily
            mock_client.search.assert_called_once()
            assert "Tavily AI Search" in result
            assert "Test AI answer" in result
            assert "Test Result" in result


@patch("venom_core.execution.skills.web_skill.DDGS")
@patch("venom_core.execution.skills.web_skill.SETTINGS")
def test_web_skill_search_fallback_to_duckduckgo(mock_settings, mock_ddgs):
    """Test czy search używa DuckDuckGo jako fallback."""
    mock_settings.TAVILY_API_KEY.get_secret_value.return_value = ""
    
    # Mock odpowiedzi DuckDuckGo
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {
            "title": "DDG Result",
            "href": "https://example.com",
            "body": "DDG content",
        }
    ]
    mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance
    
    skill = WebSearchSkill()
    result = skill.search("test query", max_results=5)
    
    # Sprawdź czy użyto DuckDuckGo
    mock_ddgs_instance.text.assert_called_once()
    assert "DuckDuckGo" in result
    assert "DDG Result" in result


def test_web_skill_tavily_fallback_on_error():
    """Test czy następuje fallback do DuckDuckGo gdy Tavily zwraca błąd."""
    import sys
    
    with patch("venom_core.execution.skills.web_skill.extract_secret_value") as mock_extract:
        mock_extract.return_value = "test_api_key"
        
        # Patch tavily import
        with patch.dict('sys.modules', {'tavily': MagicMock()}):
            mock_tavily_module = sys.modules['tavily']
            
            with patch("venom_core.execution.skills.web_skill.DDGS") as mock_ddgs:
                # Mock Tavily rzucającego błąd
                mock_client = MagicMock()
                mock_client.search.side_effect = Exception("Tavily API error")
                mock_tavily_module.TavilyClient.return_value = mock_client
                
                # Mock DuckDuckGo jako fallback
                mock_ddgs_instance = MagicMock()
                mock_ddgs_instance.text.return_value = [
                    {
                        "title": "Fallback Result",
                        "href": "https://example.com",
                        "body": "Fallback content",
                    }
                ]
                mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance
                
                skill = WebSearchSkill()
                result = skill.search("test query", max_results=5)
                
                # Sprawdź czy użyto DuckDuckGo jako fallback
                mock_ddgs_instance.text.assert_called_once()
                assert "DuckDuckGo" in result
                assert "Fallback Result" in result
