"""Testy dla BrowserSkill."""

import pytest

from venom_core.execution.skills.browser_skill import BrowserSkill


@pytest.fixture
def browser_skill():
    """Fixture dla BrowserSkill."""
    return BrowserSkill()


@pytest.mark.asyncio
async def test_browser_skill_initialization(browser_skill):
    """Test inicjalizacji BrowserSkill."""
    assert browser_skill is not None
    assert browser_skill.screenshots_dir.exists()
    assert browser_skill._browser is None  # Nie uruchomiona jeszcze


@pytest.mark.asyncio
async def test_visit_page_invalid_url(browser_skill):
    """Test odwiedzania nieprawidłowego URL."""
    result = await browser_skill.visit_page("invalid-url")
    assert "❌" in result or "Błąd" in result


@pytest.mark.asyncio
async def test_close_browser(browser_skill):
    """Test zamykania przeglądarki."""
    result = await browser_skill.close_browser()
    assert "✅" in result or "zamknięta" in result.lower()


@pytest.mark.asyncio
async def test_take_screenshot_without_page(browser_skill):
    """Test wykonywania screenshotu bez załadowanej strony."""
    # Powinno uruchomić przeglądarkę i zrobić screenshot pustej strony
    result = await browser_skill.take_screenshot("test.png")
    # Może się powieść lub zwrócić błąd - zależnie od implementacji
    assert isinstance(result, str)
    await browser_skill.close_browser()


# Testy integracyjne (wymagają działającego serwera web)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_visit_real_page(browser_skill):
    """Test odwiedzania prawdziwej strony (wymaga internetu)."""
    result = await browser_skill.visit_page("https://example.com")
    assert "✅" in result
    assert "Example Domain" in result or "example" in result.lower()
    await browser_skill.close_browser()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_html_content(browser_skill):
    """Test pobierania zawartości HTML."""
    await browser_skill.visit_page("https://example.com")
    html = await browser_skill.get_html_content()
    assert "<html" in html.lower()
    assert "</html>" in html.lower()
    await browser_skill.close_browser()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_screenshot_workflow(browser_skill):
    """Test pełnego workflow ze screenshotem."""
    # Odwiedź stronę
    await browser_skill.visit_page("https://example.com")

    # Zrób screenshot
    result = await browser_skill.take_screenshot("example_test.png", full_page=True)
    assert "✅" in result

    # Sprawdź czy plik istnieje
    screenshot_path = browser_skill.screenshots_dir / "example_test.png"
    assert screenshot_path.exists()

    # Zamknij
    await browser_skill.close_browser()
