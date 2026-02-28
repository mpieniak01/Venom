from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from venom_core.agents.coder import CoderAgent
from venom_core.agents.integrator import IntegratorAgent
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.agents.toolmaker import ToolmakerAgent


@pytest.mark.asyncio
async def test_release_manager_skill_manager_and_legacy_paths():
    release = ReleaseManagerAgent.__new__(ReleaseManagerAgent)
    release.skill_manager = None
    release.git_skill = SimpleNamespace(
        get_last_commit_log=AsyncMock(return_value="legacy")
    )
    release.file_skill = SimpleNamespace(write_file=AsyncMock(return_value=None))
    assert await release._invoke_git_tool("get_last_commit_log", {"n": 3}) == "legacy"
    await release._write_file("CHANGELOG.md", "x")

    release.skill_manager = SimpleNamespace(
        invoke_mcp_tool=AsyncMock(return_value="mcp")
    )
    assert await release._invoke_git_tool("get_last_commit_log", {"n": 2}) == "mcp"


@pytest.mark.asyncio
async def test_integrator_skill_manager_and_legacy_paths():
    integrator = IntegratorAgent.__new__(IntegratorAgent)
    integrator.skill_manager = SimpleNamespace(
        invoke_mcp_tool=AsyncMock(return_value="ok")
    )
    integrator.git_skill = SimpleNamespace(checkout=AsyncMock(return_value="legacy"))
    assert await integrator._invoke_git_tool("checkout", {"branch_name": "x"}) == "ok"
    integrator.skill_manager = None
    assert (
        await integrator._invoke_git_tool("checkout", {"branch_name": "y"}) == "legacy"
    )


@pytest.mark.asyncio
async def test_toolmaker_legacy_file_path():
    toolmaker = ToolmakerAgent.__new__(ToolmakerAgent)
    toolmaker.skill_manager = None
    toolmaker.file_skill = SimpleNamespace(write_file=AsyncMock(return_value=None))
    await toolmaker._write_file("custom/a.py", "print(1)")


@pytest.mark.asyncio
async def test_coder_legacy_file_path():
    coder = CoderAgent.__new__(CoderAgent)
    coder.skill_manager = None
    coder.file_skill = SimpleNamespace(read_file=AsyncMock(return_value="print(1)"))
    assert await coder._read_file("a.py") == "print(1)"
