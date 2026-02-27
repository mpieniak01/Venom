from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.agents.system_engineer as se_mod
from venom_core.agents.system_engineer import SystemEngineerAgent


class _DummySkill:
    pass


@pytest.fixture
def patched_system_engineer_deps(monkeypatch):
    git_skill = MagicMock()
    git_skill.checkout = AsyncMock(return_value="legacy-ok")

    monkeypatch.setattr(se_mod, "FileSkill", lambda *args, **kwargs: _DummySkill())
    monkeypatch.setattr(se_mod, "GitSkill", lambda *args, **kwargs: git_skill)
    monkeypatch.setattr(se_mod, "GitHubSkill", lambda *args, **kwargs: _DummySkill())
    monkeypatch.setattr(
        se_mod, "HuggingFaceSkill", lambda *args, **kwargs: _DummySkill()
    )
    return git_skill


@pytest.mark.asyncio
async def test_system_engineer_create_branch_uses_skill_manager(
    patched_system_engineer_deps,
):
    kernel = MagicMock()
    skill_manager = MagicMock()
    skill_manager.invoke_mcp_tool = AsyncMock(
        return_value=SimpleNamespace(result="mcp-ok")
    )
    agent = SystemEngineerAgent(kernel=kernel, skill_manager=skill_manager)

    result = await agent.create_evolution_branch("new-feature")

    assert result == "mcp-ok"
    skill_manager.invoke_mcp_tool.assert_awaited_once_with(
        "git",
        "checkout",
        {"branch_name": "evolution/new-feature", "create_new": True},
    )


@pytest.mark.asyncio
async def test_system_engineer_create_branch_falls_back_to_legacy(
    patched_system_engineer_deps,
):
    git_skill = patched_system_engineer_deps
    kernel = MagicMock()
    agent = SystemEngineerAgent(kernel=kernel, skill_manager=None)

    result = await agent.create_evolution_branch("evolution/hotfix")

    assert result == "legacy-ok"
    git_skill.checkout.assert_awaited_once_with(
        branch_name="evolution/hotfix",
        create_new=True,
    )
