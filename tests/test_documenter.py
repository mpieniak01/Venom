"""Testy dla modułu documenter (DocumenterAgent)."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.agents.documenter import DocumenterAgent


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_documenter_initialization(temp_workspace):
    """Test inicjalizacji DocumenterAgent."""
    agent = DocumenterAgent(workspace_root=str(temp_workspace))

    assert agent.workspace_root == temp_workspace


def test_documenter_get_status(temp_workspace):
    """Test pobierania statusu agenta."""
    agent = DocumenterAgent(workspace_root=str(temp_workspace))

    status = agent.get_status()

    assert "enabled" in status
    assert "workspace_root" in status
    assert "processing_files" in status


@pytest.mark.asyncio
async def test_documenter_handles_code_change(temp_workspace):
    """Test obsługi zmiany pliku."""
    agent = DocumenterAgent(workspace_root=str(temp_workspace))

    # Utwórz plik Python
    test_file = temp_workspace / "test_module.py"
    test_file.write_text('''"""Test module."""

def hello():
    """Say hello."""
    return "hello"
''')

    # Wywołaj handle_code_change (bez GitSkill, nie będzie commitował)
    await agent.handle_code_change(str(test_file))

    status = agent.get_status()
    assert isinstance(status["enabled"], bool)
    assert status["workspace_root"] == str(temp_workspace.resolve())
    assert status["processing_files"] == 1


@pytest.mark.asyncio
async def test_documenter_ignores_non_python_files(temp_workspace):
    """Test ignorowania plików nie-Python."""
    agent = DocumenterAgent(workspace_root=str(temp_workspace))

    # Utwórz plik tekstowy
    test_file = temp_workspace / "test.txt"
    test_file.write_text("some text")

    # Wywołaj handle_code_change
    await agent.handle_code_change(str(test_file))

    status = agent.get_status()
    assert status["workspace_root"] == str(temp_workspace.resolve())
    assert isinstance(status["enabled"], bool)
    assert status["processing_files"] == 1


@pytest.mark.asyncio
async def test_documenter_prevents_infinite_loop(temp_workspace):
    """Test zapobiegania pętli nieskończonej."""
    agent = DocumenterAgent(workspace_root=str(temp_workspace))

    # Utwórz plik Python
    test_file = temp_workspace / "loop_test.py"
    test_file.write_text("def test(): pass")

    # Wywołaj dwukrotnie dla tego samego pliku
    task1 = asyncio.create_task(agent.handle_code_change(str(test_file)))
    task2 = asyncio.create_task(agent.handle_code_change(str(test_file)))

    # Poczekaj na zakończenie
    await task1
    await task2

    status = agent.get_status()
    assert status["workspace_root"] == str(temp_workspace.resolve())
    assert isinstance(status["enabled"], bool)
    assert status["processing_files"] == 1


@pytest.mark.asyncio
async def test_documenter_get_file_diff_uses_skill_manager(temp_workspace):
    skill_manager = MagicMock()
    skill_manager.invoke_mcp_tool = AsyncMock(
        return_value=SimpleNamespace(result="diff --git a/x b/x\n+def foo(): pass")
    )
    agent = DocumenterAgent(
        workspace_root=str(temp_workspace),
        skill_manager=skill_manager,
    )

    test_file = temp_workspace / "module.py"
    test_file.write_text("def foo():\n    pass\n")
    diff = await agent._get_file_diff(str(test_file))

    assert "diff --git" in diff
    skill_manager.invoke_mcp_tool.assert_awaited_once_with(
        "git",
        "get_diff",
        {"file_path": "module.py"},
    )


@pytest.mark.asyncio
async def test_documenter_invoke_git_tool_falls_back_to_legacy(temp_workspace):
    git_skill = MagicMock()
    git_skill.commit = AsyncMock(return_value={"status": "success"})
    agent = DocumenterAgent(
        workspace_root=str(temp_workspace),
        git_skill=git_skill,
        skill_manager=None,
    )

    result = await agent._invoke_git_tool(
        "commit",
        {"message": "docs: auto-update"},
    )

    assert result == {"status": "success"}
    git_skill.commit.assert_awaited_once_with(message="docs: auto-update")
