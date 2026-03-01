from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from venom_core.agents.coder import CoderAgent


@pytest.mark.asyncio
async def test_read_file_prefers_skill_manager_path() -> None:
    agent = object.__new__(CoderAgent)
    invoke = AsyncMock(return_value="mcp-content")
    agent.skill_manager = SimpleNamespace(invoke_mcp_tool=invoke)
    agent.file_skill = SimpleNamespace(
        read_file=AsyncMock(return_value="legacy-content")
    )

    result = await CoderAgent._read_file(agent, "demo.py")

    assert result == "mcp-content"
    invoke.assert_awaited_once_with(
        "file",
        "read_file",
        {"file_path": "demo.py"},
        is_external=False,
    )


@pytest.mark.asyncio
async def test_read_file_uses_legacy_file_skill_without_skill_manager() -> None:
    agent = object.__new__(CoderAgent)
    read_file = AsyncMock(return_value="legacy-content")
    agent.skill_manager = None
    agent.file_skill = SimpleNamespace(read_file=read_file)

    result = await CoderAgent._read_file(agent, "legacy.py")

    assert result == "legacy-content"
    read_file.assert_awaited_once_with("legacy.py")
