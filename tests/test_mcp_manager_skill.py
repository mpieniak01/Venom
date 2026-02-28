from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from venom_core.skills.mcp_manager_skill import McpManagerSkill


def test_sanitize_env_for_mcp_adds_pythonunbuffered() -> None:
    skill = McpManagerSkill()
    env = {"PATH": "/usr/bin", "HOME": "/tmp", "SECRET_TOKEN": "x"}

    sanitized = skill._sanitize_env_for_mcp(env)

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/tmp"
    assert sanitized["PYTHONUNBUFFERED"] == "1"
    assert "SECRET_TOKEN" not in sanitized


@pytest.mark.asyncio
async def test_import_mcp_tool_stops_when_no_tools(monkeypatch: pytest.MonkeyPatch):
    skill = McpManagerSkill()
    monkeypatch.setattr(
        "venom_core.skills.mcp_manager_skill.require_shell_permission", lambda: None
    )
    skill._run_shell = AsyncMock()
    skill._introspect_tools = AsyncMock(return_value=[])

    result = await skill.import_mcp_tool(
        repo_url="https://example.com/repo.git",
        tool_name="demo",
    )

    assert "Nie wykryto żadnych narzędzi" in result
