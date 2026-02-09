"""Testy dla modułu documenter (DocumenterAgent)."""

import asyncio
import tempfile
from pathlib import Path

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
    assert status["processing_files"] == 1
    assert str(test_file) in agent._last_processed_files
