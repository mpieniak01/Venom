"""Testy jednostkowe dla DockerHabitat."""

import tempfile
from pathlib import Path

import pytest

from venom_core.config import SETTINGS
from venom_core.infrastructure.docker_habitat import DockerHabitat

pytestmark = pytest.mark.requires_docker


@pytest.fixture(scope="module")
def docker_habitat():
    """Fixture dla DockerHabitat - jeden kontener dla wszystkich testów."""
    habitat = DockerHabitat()
    yield habitat
    # Cleanup po wszystkich testach
    habitat.cleanup()


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Zapisz oryginalną wartość
        original_workspace = SETTINGS.WORKSPACE_ROOT
        SETTINGS.WORKSPACE_ROOT = tmpdir
        yield tmpdir
        # Przywróć oryginalną wartość
        SETTINGS.WORKSPACE_ROOT = original_workspace


def test_docker_habitat_initialization():
    """Test inicjalizacji DockerHabitat."""
    habitat = DockerHabitat()
    assert habitat.container is not None
    assert habitat.container.status == "running"
    assert habitat.container.name == "venom-sandbox"


def test_docker_habitat_execute_simple_command(docker_habitat):
    """Test wykonania prostej komendy."""
    exit_code, output = docker_habitat.execute("echo 'Hello from Docker'")

    assert exit_code == 0
    assert "Hello from Docker" in output


def test_docker_habitat_execute_python_command(docker_habitat):
    """Test wykonania komendy Python."""
    exit_code, output = docker_habitat.execute("python -c \"print('Test Python')\"")

    assert exit_code == 0
    assert "Test Python" in output


def test_docker_habitat_execute_failed_command(docker_habitat):
    """Test wykonania komendy która się nie powiedzie."""
    exit_code, output = docker_habitat.execute("sh -c 'exit 1'")

    assert exit_code == 1


def test_docker_habitat_execute_python_error(docker_habitat):
    """Test wykonania kodu Python z błędem."""
    exit_code, output = docker_habitat.execute('python -c "import nonexistent_module"')

    assert exit_code != 0
    assert "ModuleNotFoundError" in output or "ImportError" in output


def test_docker_habitat_working_directory(docker_habitat):
    """Test czy working directory jest ustawiony poprawnie."""
    exit_code, output = docker_habitat.execute("pwd")

    assert exit_code == 0
    assert "/workspace" in output


def test_docker_habitat_volume_mount(docker_habitat):
    """Test czy volume jest zamontowany poprawnie."""
    # Utwórz plik w workspace (główny workspace, nie temp)
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    test_file = workspace_path / "test_volume.txt"
    test_content = "Test volume mount"
    test_file.write_text(test_content)

    # Sprawdź czy plik jest widoczny w kontenerze
    exit_code, output = docker_habitat.execute("cat /workspace/test_volume.txt")

    assert exit_code == 0
    assert test_content in output


def test_docker_habitat_file_creation_in_container(docker_habitat):
    """Test tworzenia pliku w kontenerze i jego widoczności na hoście."""
    # Utwórz plik w kontenerze używając sh -c
    exit_code, output = docker_habitat.execute(
        "sh -c \"echo 'Created in container' > /workspace/container_file.txt\""
    )
    assert exit_code == 0

    # Sprawdź czy plik jest widoczny na hoście
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    created_file = workspace_path / "container_file.txt"

    assert created_file.exists()
    assert "Created in container" in created_file.read_text()


def test_docker_habitat_execute_with_stderr(docker_habitat):
    """Test czy stderr jest łączony z stdout."""
    exit_code, output = docker_habitat.execute(
        "python -c \"import sys; sys.stderr.write('Error message\\n')\""
    )

    assert exit_code == 0
    assert "Error message" in output


def test_docker_habitat_multiple_commands(docker_habitat):
    """Test wykonania wielu komend w sekwencji."""
    commands = [
        "echo 'First command'",
        "echo 'Second command'",
        "python -c \"print('Third command')\"",
    ]

    for cmd in commands:
        exit_code, output = docker_habitat.execute(cmd)
        assert exit_code == 0


def test_docker_habitat_python_script_execution(docker_habitat):
    """Test wykonania skryptu Python z pliku."""
    # Utwórz skrypt Python w głównym workspace
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    script_path = workspace_path / "test_script.py"
    script_content = """
print("Hello from script")
result = 2 + 2
print(f"Result: {result}")
"""
    script_path.write_text(script_content)

    # Wykonaj skrypt
    exit_code, output = docker_habitat.execute("python test_script.py")

    assert exit_code == 0
    assert "Hello from script" in output
    assert "Result: 4" in output


def test_docker_habitat_python_script_with_error(docker_habitat):
    """Test wykonania skryptu Python z błędem."""
    # Utwórz skrypt Python z błędem w głównym workspace
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
    script_path = workspace_path / "error_script.py"
    script_content = """
print("Before error")
raise ValueError("Intentional error")
print("After error")
"""
    script_path.write_text(script_content)

    # Wykonaj skrypt
    exit_code, output = docker_habitat.execute("python error_script.py")

    assert exit_code != 0
    assert "ValueError" in output
    assert "Intentional error" in output


@pytest.mark.skipif(
    not Path("/usr/bin/docker").exists(), reason="Docker nie jest dostępny"
)
def test_docker_habitat_container_reuse():
    """Test czy kontener jest ponownie używany zamiast tworzenia nowego."""
    # Utwórz pierwszą instancję
    habitat1 = DockerHabitat()
    container_id1 = habitat1.container.id

    # Utwórz drugą instancję
    habitat2 = DockerHabitat()
    container_id2 = habitat2.container.id

    # Powinny używać tego samego kontenera
    assert container_id1 == container_id2


def test_docker_habitat_pip_install(docker_habitat):
    """Test instalacji pakietu pip w kontenerze (nie na hoście)."""
    # Zainstaluj prosty pakiet
    exit_code, output = docker_habitat.execute(
        "pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org six"
    )

    # Sprawdź czy instalacja się powiodła lub pakiet już istnieje
    assert exit_code == 0 or "already satisfied" in output.lower()

    # Sprawdź czy pakiet jest dostępny w kontenerze
    exit_code, output = docker_habitat.execute(
        "python -c \"import six; print('six imported')\""
    )
    assert exit_code == 0
    assert "six imported" in output
