"""Testy integracyjne dla CoderAgent z pętlą samonaprawy."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.config import SETTINGS
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.shell_skill import ShellSkill

pytestmark = pytest.mark.requires_docker


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_workspace = SETTINGS.WORKSPACE_ROOT
        SETTINGS.WORKSPACE_ROOT = tmpdir
        Path(tmpdir).mkdir(parents=True, exist_ok=True)
        yield tmpdir
        SETTINGS.WORKSPACE_ROOT = original_workspace


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Semantic Kernel."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()

    # Mock chat service
    chat_service = MagicMock()
    chat_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=chat_service)

    return kernel


def test_coder_agent_initialization(mock_kernel):
    """Test inicjalizacji CoderAgent z ShellSkill."""
    from venom_core.agents.coder import CoderAgent

    agent = CoderAgent(mock_kernel, enable_self_repair=True)

    assert agent.enable_self_repair
    # Sprawdź czy oba skille zostały dodane
    assert mock_kernel.add_plugin.call_count >= 2


def test_coder_agent_initialization_without_self_repair(mock_kernel):
    """Test inicjalizacji CoderAgent bez samonaprawy."""
    from venom_core.agents.coder import CoderAgent

    agent = CoderAgent(mock_kernel, enable_self_repair=False)

    assert not agent.enable_self_repair


@pytest.mark.asyncio
async def test_coder_agent_process_basic(mock_kernel):
    """Test podstawowej metody process."""
    from venom_core.agents.coder import CoderAgent

    agent = CoderAgent(mock_kernel)

    # Mock odpowiedzi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Generated code")
    mock_kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Write a hello world function")

    assert result == "Generated code"


@pytest.mark.asyncio
async def test_coder_agent_process_with_verification_disabled(
    mock_kernel, temp_workspace
):
    """Test process_with_verification gdy self_repair jest wyłączony."""
    from venom_core.agents.coder import CoderAgent

    agent = CoderAgent(mock_kernel, enable_self_repair=False)

    # Mock odpowiedzi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Generated code")
    mock_kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process_with_verification("Write a hello world function")

    assert result["success"]
    assert result["attempts"] == 1
    assert result["output"] == "Generated code"


@pytest.mark.asyncio
async def test_file_and_shell_skill_integration(temp_workspace):
    """Test integracji FileSkill i ShellSkill."""
    file_skill = FileSkill(workspace_root=temp_workspace)
    shell_skill = ShellSkill(use_sandbox=False)  # Użyj lokalnego dla prostoty

    # Utwórz prosty skrypt Python
    script_content = "print('Integration test')"
    await file_skill.write_file("integration_test.py", script_content)

    # Sprawdź czy plik istnieje
    exists = file_skill.file_exists("integration_test.py")
    assert exists == "True"

    # Wykonaj skrypt
    result = shell_skill.run_shell("python integration_test.py")

    assert "Integration test" in result


@pytest.mark.asyncio
async def test_shell_skill_error_detection(temp_workspace):
    """Test wykrywania błędów przez ShellSkill."""
    file_skill = FileSkill(workspace_root=temp_workspace)
    shell_skill = ShellSkill(use_sandbox=False)

    # Utwórz skrypt z błędem
    error_script = """
print("Before error")
raise ValueError("Test error")
print("After error")
"""
    await file_skill.write_file("error_test.py", error_script)

    # Wykonaj skrypt
    result = shell_skill.run_shell("python error_test.py")
    exit_code = shell_skill.get_exit_code_from_output(result)

    # Powinien wykryć błąd
    assert exit_code != 0
    assert "ValueError" in result or "Test error" in result


@pytest.mark.asyncio
async def test_shell_skill_success_detection(temp_workspace):
    """Test wykrywania sukcesu przez ShellSkill."""
    file_skill = FileSkill(workspace_root=temp_workspace)
    shell_skill = ShellSkill(use_sandbox=False)

    # Utwórz prawidłowy skrypt
    success_script = """
print("Script executed successfully")
result = 2 + 2
print(f"Result: {result}")
"""
    await file_skill.write_file("success_test.py", success_script)

    # Wykonaj skrypt
    result = shell_skill.run_shell("python success_test.py")
    exit_code = shell_skill.get_exit_code_from_output(result)

    # Powinien wykryć sukces
    assert exit_code == 0
    assert "Script executed successfully" in result
    assert "Result: 4" in result


@pytest.mark.asyncio
async def test_sandbox_file_visibility():
    """Test czy pliki utworzone w workspace są widoczne w sandbox."""
    # Pomiń jeśli Docker nie jest dostępny
    try:
        shell_skill = ShellSkill(use_sandbox=True)
        if not shell_skill.use_sandbox:
            pytest.skip("Docker Sandbox nie jest dostępny")
    except Exception:
        pytest.skip("Docker Sandbox nie jest dostępny")

    file_skill = FileSkill()  # Użyj domyślnego workspace

    # Utwórz plik na hoście
    await file_skill.write_file("sandbox_test.txt", "Content from host")

    # Sprawdź czy plik jest widoczny w sandbox
    result = shell_skill.run_shell("cat sandbox_test.txt")

    assert "Content from host" in result


@pytest.mark.skipif(True, reason="SSL issues in CI environment")
def test_sandbox_pip_isolation():
    """Test czy instalacja pip w sandbox nie wpływa na hosta."""
    # Pomiń jeśli Docker nie jest dostępny
    try:
        shell_skill = ShellSkill(use_sandbox=True)
        if not shell_skill.use_sandbox:
            pytest.skip("Docker Sandbox nie jest dostępny")
    except Exception:
        pytest.skip("Docker Sandbox nie jest dostępny")

    # Zainstaluj pakiet w sandbox
    result = shell_skill.run_shell("pip install --quiet requests")
    exit_code = shell_skill.get_exit_code_from_output(result)

    # Instalacja powinna się udać
    assert (
        exit_code == 0
        or "Successfully installed" in result
        or "Requirement already satisfied" in result
    )

    # Sprawdź czy pakiet jest dostępny w sandbox
    result = shell_skill.run_shell(
        "python -c \"import requests; print('requests imported')\""
    )
    assert "requests imported" in result
