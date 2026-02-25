"""Targeted unit coverage for browser_skill missing branches."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from venom_core.execution.skills.browser_skill import BrowserSkill


def test_is_local_or_private_host_link_local_true():
    """Cover link-local branch in host classifier."""
    assert BrowserSkill._is_local_or_private_host("169.254.10.20") is True


def test_sanitize_filename_dot_and_too_long():
    """Cover explicit invalid-dot and max-length branches."""
    with pytest.raises(ValueError, match="Niedozwolona nazwa pliku"):
        BrowserSkill._sanitize_screenshot_filename("..")

    with pytest.raises(ValueError, match="zbyt długa"):
        BrowserSkill._sanitize_screenshot_filename("a" * 200)


def test_ensure_url_scheme_empty_returns_empty():
    """Cover empty-input early return in URL normalizer."""
    assert BrowserSkill._ensure_url_scheme("") == ""


@pytest.mark.asyncio
async def test_close_browser_closes_browser_and_playwright_without_page():
    """Cover _close_browser branches when page is absent but browser/playwright exist."""
    skill = BrowserSkill()
    skill._page = None
    skill._browser = type("B", (), {"close": AsyncMock()})()
    skill._playwright = type("P", (), {"stop": AsyncMock()})()

    await skill._close_browser()

    assert skill._browser is None
    assert skill._playwright is None


@pytest.mark.asyncio
async def test_visit_page_returns_error_on_goto_exception():
    """Cover visit_page generic exception path."""

    class _FailingPage:
        async def goto(self, *_args, **_kwargs):
            raise RuntimeError("goto failed")

    skill = BrowserSkill()
    skill._ensure_browser = AsyncMock()
    skill._page = _FailingPage()

    result = await skill.visit_page("https://example.com")
    assert "❌" in result


@pytest.mark.asyncio
async def test_close_browser_returns_error_when_close_fails():
    """Cover close_browser exception wrapper."""
    skill = BrowserSkill()
    skill._close_browser = AsyncMock(side_effect=RuntimeError("close failed"))

    result = await skill.close_browser()
    assert "❌" in result
