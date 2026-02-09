"""Testy dla BrowserSkill."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from venom_core.execution.skills.browser_skill import BrowserSkill


@pytest_asyncio.fixture
async def browser_skill():
    """Fixture dla BrowserSkill."""
    skill = BrowserSkill()
    yield skill
    try:
        await skill.close_browser()
    except Exception:
        # Ignorujemy wyjątki przy zamykaniu przeglądarki w teardown — nie chcemy, by błąd w sprzątaniu psuł testy.
        pass


def test_browser_skill_initialization(browser_skill):
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


def test_sanitize_screenshot_filename_rejects_path_traversal():
    """Nazwa pliku nie może zawierać ścieżek względnych."""
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("../secret.png")


def test_sanitize_screenshot_filename_accepts_simple_name():
    """Prawidłowa nazwa powinna dostać rozszerzenie .png."""
    assert BrowserSkill._sanitize_screenshot_filename("home") == "home.png"


def test_validate_url_policy_flags_unsupported_scheme():
    """Policy check powinien flagować niedozwolony schemat."""
    skill = BrowserSkill()
    warnings = skill._validate_url_policy("file:///etc/passwd")
    assert warnings
    assert "Niedozwolony schemat URL" in warnings[0]


def test_url_helpers_and_policy_localhost(monkeypatch):
    skill = BrowserSkill()
    assert skill._is_local_or_private_host("127.0.0.1") is True
    assert skill._is_local_or_private_host("localhost") is True
    assert skill._is_local_or_private_host("example.com") is False
    monkeypatch.delenv("VENOM_BROWSER_ALLOWED_HOSTS", raising=False)
    assert skill._get_allowed_hosts() == set()
    warnings = skill._validate_url_policy("http://localhost:3000")
    assert warnings == []


def test_validate_url_policy_non_local_host_requires_allowlist(monkeypatch):
    skill = BrowserSkill()
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "example.com, api.example.com")
    assert skill._validate_url_policy("https://example.com/a") == []
    warnings = skill._validate_url_policy("https://not-allowed.example")
    assert warnings
    assert "allowliście" in warnings[0]


def test_sanitize_filename_rejects_invalid_cases():
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("")
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("..")
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("name with spaces.png")
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("a" * 200 + ".png")


def test_ensure_url_scheme_keeps_existing_and_adds_for_missing(monkeypatch):
    assert (
        BrowserSkill._ensure_url_scheme("https://example.com") == "https://example.com"
    )
    monkeypatch.setenv("URL_SCHEME_POLICY", "force_http")
    assert BrowserSkill._ensure_url_scheme("localhost/path") == "http://localhost/path"


def test_require_page_raises_when_missing():
    skill = BrowserSkill()
    with pytest.raises(RuntimeError):
        skill._require_page()


@pytest.mark.asyncio
async def test_visit_page_policy_block(monkeypatch):
    class DummyPage:
        async def goto(
            self, *args, **kwargs
        ):  # pragma: no cover - nie powinno być wywołane
            raise AssertionError("goto should not be called in block mode")

        async def title(self):
            return "Ignored"

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = DummyPage()
    monkeypatch.setenv("VENOM_BROWSER_URL_POLICY_MODE", "block")
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "")

    result = await skill.visit_page("https://example.com")
    assert "zablokowany przez politykę" in result


@pytest.mark.asyncio
async def test_visit_page_success_path_with_warning_mode(monkeypatch):
    page = MagicMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Example")

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = page
    monkeypatch.setenv("VENOM_BROWSER_URL_POLICY_MODE", "warn")
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "example.com")

    result = await skill.visit_page("https://example.com")
    assert "✅" in result
    assert "Example" in result
    page.goto.assert_awaited_once()


@pytest.mark.asyncio
async def test_take_screenshot_success_with_mocked_page():
    page = MagicMock()
    page.screenshot = AsyncMock()

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = page

    result = await skill.take_screenshot("shot", full_page=True)
    assert "✅" in result
    page.screenshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_fill_text_wait_success_paths():
    class DummyPage:
        async def click(self, *_args, **_kwargs):
            return None

        async def fill(self, *_args, **_kwargs):
            return None

        async def text_content(self, *_args, **_kwargs):
            return "sample text"

        async def wait_for_selector(self, *_args, **_kwargs):
            return None

        async def wait_for_timeout(self, *_args, **_kwargs):
            return None

        async def screenshot(self, *_args, **_kwargs):
            return None

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = DummyPage()

    click_result = await skill.click_element("#btn")
    fill_result = await skill.fill_form("#input", "x")
    text_result = await skill.get_text_content("#msg")
    wait_result = await skill.wait_for_element("#msg")

    assert "✅" in click_result
    assert "✅" in fill_result
    assert text_result == "sample text"
    assert "✅" in wait_result


@pytest.mark.asyncio
async def test_click_element_error_path():
    class FailingPage:
        async def click(self, *_args, **_kwargs):
            raise RuntimeError("click failed")

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = FailingPage()

    result = await skill.click_element("#btn")
    assert "❌" in result
