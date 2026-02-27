from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.coder import CoderAgent


@pytest.fixture
def mock_kernel():
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()
    kernel.get_service = MagicMock(return_value=MagicMock())
    return kernel


@pytest.mark.asyncio
async def test_coder_read_file_uses_skill_manager_when_available(mock_kernel):
    skill_manager = MagicMock()
    skill_manager.invoke_mcp_tool = AsyncMock(return_value="print('ok')")

    with (
        patch("venom_core.agents.coder.FileSkill"),
        patch("venom_core.agents.coder.ShellSkill"),
        patch("venom_core.agents.coder.ComposeSkill"),
    ):
        agent = CoderAgent(mock_kernel, skill_manager=skill_manager)

    content = await agent._read_file("script.py")
    assert content == "print('ok')"
    skill_manager.invoke_mcp_tool.assert_awaited_once_with(
        "file",
        "read_file",
        {"file_path": "script.py"},
        is_external=False,
    )


@pytest.mark.asyncio
async def test_coder_read_file_falls_back_to_file_skill(mock_kernel):
    with (
        patch("venom_core.agents.coder.ShellSkill"),
        patch("venom_core.agents.coder.ComposeSkill"),
    ):
        agent = CoderAgent(mock_kernel)

    agent.file_skill.read_file = AsyncMock(return_value="fallback-content")
    content = await agent._read_file("fallback.py")
    assert content == "fallback-content"
    agent.file_skill.read_file.assert_awaited_once_with("fallback.py")
