"""Testy jednostkowe dla ShellSkill z obsługą Docker Sandbox."""

import sys
import tempfile
from pathlib import Path

import pytest

from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.shell_skill import ShellSkill

pytestmark = pytest.mark.requires_docker


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Zapisz oryginalną wartość
        original_workspace = SETTINGS.WORKSPACE_ROOT
        SETTINGS.WORKSPACE_ROOT = tmpdir

        # Upewnij się że katalog istnieje
        Path(tmpdir).mkdir(parents=True, exist_ok=True)

        yield tmpdir

        # Przywróć oryginalną wartość
        SETTINGS.WORKSPACE_ROOT = original_workspace


@pytest.fixture(autouse=True)
def _allow_shell_for_tests():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


def test_shell_skill_initialization_sandbox():
    """Test inicjalizacji ShellSkill z sandbox."""
    skill = ShellSkill(use_sandbox=True)
    # Sprawdź czy use_sandbox jest boolean
    assert isinstance(skill.use_sandbox, bool)
    if skill.use_sandbox:
        assert skill.habitat is not None


def test_shell_skill_initialization_local():
    """Test inicjalizacji ShellSkill bez sandbox."""
    skill = ShellSkill(use_sandbox=False)
    assert not skill.use_sandbox
    assert skill.habitat is None


def test_shell_skill_run_simple_command_sandbox(temp_workspace):
    """Test wykonania prostej komendy w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    result = skill.run_shell("echo 'Hello World'")

    assert "Hello World" in result
    assert "pomyślnie" in result or "exit_code=0" in result


def test_shell_skill_run_simple_command_local(temp_workspace):
    """Test wykonania prostej komendy lokalnie."""
    skill = ShellSkill(use_sandbox=False)

    result = skill.run_shell("echo 'Hello Local'")

    assert "Hello Local" in result
    assert "pomyślnie" in result or "exit_code=0" in result


def test_shell_skill_run_python_command_sandbox(temp_workspace):
    """Test wykonania komendy Python w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    result = skill.run_shell("python -c \"print('Python in sandbox')\"")

    assert "Python in sandbox" in result
    assert "pomyślnie" in result.lower()


def test_shell_skill_run_failed_command_sandbox(temp_workspace):
    """Test wykonania komendy która się nie powiedzie w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    result = skill.run_shell('python -c "import nonexistent_module"')

    assert "błęd" in result.lower() or "exit_code=" in result
    assert "ModuleNotFoundError" in result or "ImportError" in result


def test_shell_skill_run_failed_command_local(temp_workspace):
    """Test wykonania komendy która się nie powiedzie lokalnie."""
    skill = ShellSkill(use_sandbox=False)

    result = skill.run_shell(f"{sys.executable} -c \"raise ValueError('Test error')\"")

    assert "błąd" in result.lower() or "exit_code=" in result
    assert "ValueError" in result or "Test error" in result


def test_shell_skill_get_exit_code_success():
    """Test parsowania exit_code z udanego wykonania."""
    skill = ShellSkill(use_sandbox=False)

    output = "Komenda wykonana pomyślnie.\n\nOutput:\nHello"
    exit_code = skill.get_exit_code_from_output(output)

    assert exit_code == 0


def test_shell_skill_get_exit_code_failure():
    """Test parsowania exit_code z nieudanego wykonania."""
    skill = ShellSkill(use_sandbox=False)

    output = "Komenda zakończona z błędem (exit_code=1).\n\nOutput:\nError message"
    exit_code = skill.get_exit_code_from_output(output)

    assert exit_code == 1


def test_shell_skill_get_exit_code_from_error():
    """Test parsowania exit_code z błędu."""
    skill = ShellSkill(use_sandbox=False)

    output = (
        "Komenda zakończona z błędem (exit_code=127).\n\nOutput:\nCommand not found"
    )
    exit_code = skill.get_exit_code_from_output(output)

    assert exit_code == 127


def test_shell_skill_python_script_execution_sandbox():
    """Test wykonania skryptu Python w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    # Utwórz skrypt w głównym workspace
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    script_path = workspace_path / "test.py"
    script_path.write_text("print('Script executed')")

    result = skill.run_shell("python test.py")

    assert "Script executed" in result
    assert "pomyślnie" in result.lower() or "exit_code=0" in result


def test_shell_skill_python_script_execution_local(temp_workspace):
    """Test wykonania skryptu Python lokalnie."""
    skill = ShellSkill(use_sandbox=False)

    # Utwórz skrypt
    script_path = Path(temp_workspace) / "test_local.py"
    script_path.write_text("print('Local script executed')")

    result = skill.run_shell(f"{sys.executable} test_local.py")

    assert "Local script executed" in result
    assert "pomyślnie" in result.lower() or "exit_code=0" in result


def test_shell_skill_working_directory_sandbox():
    """Test czy working directory jest ustawiony poprawnie w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    # Utwórz plik w głównym workspace
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    test_file = workspace_path / "test_dir.txt"
    test_file.write_text("Directory test")

    result = skill.run_shell("ls test_dir.txt")

    assert "test_dir.txt" in result
    assert "pomyślnie" in result.lower() or "exit_code=0" in result


def test_shell_skill_working_directory_local(temp_workspace):
    """Test czy working directory jest ustawiony poprawnie lokalnie."""
    skill = ShellSkill(use_sandbox=False)

    # Utwórz plik w workspace
    test_file = Path(temp_workspace) / "test_dir_local.txt"
    test_file.write_text("Directory test local")

    result = skill.run_shell("ls test_dir_local.txt")

    assert "test_dir_local.txt" in result or "pomyślnie" in result.lower()


def test_shell_skill_timeout_sandbox(temp_workspace):
    """Test timeout w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    # Komenda która szybko się wykona
    result = skill.run_shell("sleep 0.1", timeout=5)
    assert "pomyślnie" in result.lower() or "exit_code=0" in result


def test_shell_skill_config_enable_sandbox_false(temp_workspace):
    """Test czy ENABLE_SANDBOX=False wyłącza sandbox."""
    original_enable = SETTINGS.ENABLE_SANDBOX
    SETTINGS.ENABLE_SANDBOX = False

    skill = ShellSkill(use_sandbox=True)  # Prosi o sandbox

    # Ale sandbox powinien być wyłączony przez config
    assert not skill.use_sandbox

    SETTINGS.ENABLE_SANDBOX = original_enable


def test_shell_skill_stderr_capture_sandbox(temp_workspace):
    """Test czy stderr jest przechwytywany w sandbox."""
    skill = ShellSkill(use_sandbox=True)

    if not skill.use_sandbox:
        pytest.skip("Docker Sandbox nie jest dostępny")

    result = skill.run_shell(
        "python -c \"import sys; sys.stderr.write('Error output\\n')\""
    )

    assert "Error output" in result


def test_shell_skill_stderr_capture_local(temp_workspace):
    """Test czy stderr jest przechwytywany lokalnie."""
    skill = ShellSkill(use_sandbox=False)

    result = skill.run_shell(
        f"{sys.executable} -c \"import sys; sys.stderr.write('Local error\\n')\""
    )

    assert "Local error" in result
