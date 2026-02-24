"""PR-172C-05 coverage gap tests for browser_skill, github_skill, and shell_skill.

Covers the remaining uncovered branches in browser_skill.py:
  - _validate_url_policy: no-host URL (lines 97-99)
  - _ensure_browser: success path — actual playwright launch mocked (lines 150-164)
  - _ensure_browser: browser already initialised, new page created (lines 158-164)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import venom_core.execution.skills.browser_skill as bmod
from venom_core.execution.skills.browser_skill import BrowserSkill


# ---------------------------------------------------------------------------
# _validate_url_policy — empty-host branch (lines 97-99)
# ---------------------------------------------------------------------------


def test_validate_url_policy_empty_host_returns_warning():
    """_validate_url_policy warns when URL has a valid scheme but no host."""
    skill = BrowserSkill()
    # "http://" parses to scheme="http", hostname=None → host="" → triggers warning
    warnings = skill._validate_url_policy("http://")
    assert warnings
    assert "Brak hosta" in warnings[0]


# ---------------------------------------------------------------------------
# _ensure_browser — full success path (lines 150-165)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_browser_full_success_path(monkeypatch):
    """_ensure_browser launches browser and creates page when playwright is available."""
    mock_page = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright_obj = AsyncMock()
    mock_playwright_obj.start = AsyncMock(return_value=mock_playwright_instance)

    mock_async_playwright_callable = MagicMock(return_value=mock_playwright_obj)

    mock_module = MagicMock()
    mock_module.async_playwright = mock_async_playwright_callable

    from importlib import import_module as _real_import_module

    def mock_import(name, *args, **kwargs):
        if name == "playwright.async_api":
            return mock_module
        return _real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(bmod, "import_module", mock_import)

    skill = BrowserSkill()
    assert skill._browser is None
    assert skill._page is None

    await skill._ensure_browser()

    assert skill._playwright is mock_playwright_instance
    assert skill._browser is mock_browser
    assert skill._page is mock_page
    mock_playwright_instance.chromium.launch.assert_awaited_once()
    mock_browser.new_context.assert_awaited_once()
    mock_context.new_page.assert_awaited_once()


# ---------------------------------------------------------------------------
# _ensure_browser — browser already set, new page created (lines 158-165)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_browser_reuses_browser_creates_new_page():
    """When _browser is already set but _page is None, _ensure_browser creates page."""
    mock_page = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    skill = BrowserSkill()
    # Simulate browser already initialised
    skill._browser = mock_browser
    skill._page = None

    await skill._ensure_browser()

    assert skill._page is mock_page
    mock_browser.new_context.assert_awaited_once()
    mock_context.new_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_browser_noop_when_both_browser_and_page_set():
    """_ensure_browser is a no-op when _browser and _page are already initialised."""
    mock_browser = MagicMock()
    mock_page = MagicMock()

    skill = BrowserSkill()
    skill._browser = mock_browser
    skill._page = mock_page

    # Should return immediately without creating new context or page
    await skill._ensure_browser()

    # Page and browser remain unchanged
    assert skill._page is mock_page
    assert skill._browser is mock_browser
