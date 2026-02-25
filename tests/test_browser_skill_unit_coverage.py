"""Focused unit coverage tests for browser_skill without integration dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.execution.skills.browser_skill as bmod
from venom_core.execution.skills.browser_skill import BrowserSkill


def test_validate_url_policy_cases(monkeypatch):
    skill = BrowserSkill()
    assert "Niedozwolony schemat URL" in skill._validate_url_policy("file:///tmp/x")[0]
    assert "Brak hosta" in skill._validate_url_policy("http://")[0]
    assert skill._validate_url_policy("http://localhost:3000") == []
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "example.com")
    assert skill._validate_url_policy("https://example.com/x") == []
    assert skill._validate_url_policy("https://not-allowed.example")


def test_sanitize_filename_valid_and_invalid():
    assert BrowserSkill._sanitize_screenshot_filename("home") == "home.png"
    assert BrowserSkill._sanitize_screenshot_filename("ok.png") == "ok.png"
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("")
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("../evil.png")
    with pytest.raises(ValueError):
        BrowserSkill._sanitize_screenshot_filename("bad name.png")


def test_ensure_url_scheme_and_require_page(monkeypatch):
    assert (
        BrowserSkill._ensure_url_scheme("https://example.com") == "https://example.com"
    )
    monkeypatch.setattr(
        "venom_core.utils.url_policy.SETTINGS.URL_SCHEME_POLICY",
        "force_http",
        raising=False,
    )
    assert BrowserSkill._ensure_url_scheme("localhost/path") == "http://localhost/path"
    with pytest.raises(RuntimeError):
        BrowserSkill()._require_page()


@pytest.mark.asyncio
async def test_ensure_browser_full_success_path(monkeypatch):
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright_obj = AsyncMock()
    mock_playwright_obj.start = AsyncMock(return_value=mock_playwright_instance)
    mock_module = MagicMock()
    mock_module.async_playwright = MagicMock(return_value=mock_playwright_obj)

    def _import(name, *args, **kwargs):
        if name == "playwright.async_api":
            return mock_module
        return __import__(name, fromlist=["*"])

    monkeypatch.setattr(bmod, "import_module", _import)
    skill = BrowserSkill()
    await skill._ensure_browser()
    assert skill._browser is mock_browser
    assert skill._page is mock_page


@pytest.mark.asyncio
async def test_ensure_browser_raises_when_playwright_missing(monkeypatch):
    skill = BrowserSkill()

    def _import(*_args, **_kwargs):
        raise ImportError("missing")

    monkeypatch.setattr(bmod, "import_module", _import)
    with pytest.raises(RuntimeError, match="Playwright is not installed"):
        await skill._ensure_browser()


@pytest.mark.asyncio
async def test_visit_page_success_and_block(monkeypatch):
    page = MagicMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Example")
    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = page

    monkeypatch.setenv("VENOM_BROWSER_URL_POLICY_MODE", "warn")
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "example.com")
    ok = await skill.visit_page("https://example.com")
    assert "✅" in ok

    monkeypatch.setenv("VENOM_BROWSER_URL_POLICY_MODE", "block")
    monkeypatch.setenv("VENOM_BROWSER_ALLOWED_HOSTS", "")
    blocked = await skill.visit_page("https://example.com")
    assert "zablokowany przez politykę" in blocked


@pytest.mark.asyncio
async def test_take_screenshot_success_and_error():
    page = MagicMock()
    page.screenshot = AsyncMock()
    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = page
    ok = await skill.take_screenshot("shot", full_page=True)
    assert "✅" in ok

    class _FailingPage:
        async def screenshot(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    skill._page = _FailingPage()
    err = await skill.take_screenshot("x")
    assert "❌" in err


@pytest.mark.asyncio
async def test_html_click_fill_text_wait_and_close_paths():
    class _Page:
        async def content(self):
            return "<html>ok</html>"

        async def click(self, *_args, **_kwargs):
            return None

        async def fill(self, *_args, **_kwargs):
            return None

        async def text_content(self, *_args, **_kwargs):
            return "txt"

        async def wait_for_selector(self, *_args, **_kwargs):
            return None

        async def wait_for_timeout(self, *_args, **_kwargs):
            return None

        async def screenshot(self, *_args, **_kwargs):
            return None

        async def close(self):
            return None

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = _Page()
    assert "<html>" in await skill.get_html_content()
    assert "✅" in await skill.click_element("#a")
    assert "✅" in await skill.fill_form("#b", "v")
    assert "txt" == await skill.get_text_content("#c")
    assert "✅" in await skill.wait_for_element("#d")

    skill._browser = SimpleNamespace(close=AsyncMock())
    skill._playwright = SimpleNamespace(stop=AsyncMock())
    assert "✅" in await skill.close_browser()


@pytest.mark.asyncio
async def test_error_paths_for_methods():
    class _Fail:
        async def content(self):
            raise RuntimeError("content")

        async def click(self, *_args, **_kwargs):
            raise RuntimeError("click")

        async def fill(self, *_args, **_kwargs):
            raise RuntimeError("fill")

        async def text_content(self, *_args, **_kwargs):
            raise RuntimeError("text")

        async def wait_for_selector(self, *_args, **_kwargs):
            raise RuntimeError("wait")

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = _Fail()
    assert "❌" in await skill.get_html_content()
    assert "❌" in await skill.click_element("#x")
    assert "❌" in await skill.fill_form("#x", "v")
    assert "❌" in await skill.get_text_content("#x")
    assert "❌" in await skill.wait_for_element("#x")
