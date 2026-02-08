"""Testy jednostkowe dla StackManager."""

import tempfile
from pathlib import Path

import pytest

from venom_core.infrastructure.stack_manager import StackManager

pytestmark = pytest.mark.requires_docker_compose


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def stack_manager(temp_workspace):
    """Fixture dla StackManager."""
    return StackManager(workspace_root=temp_workspace)


def test_stack_manager_initialization(stack_manager, temp_workspace):
    """Test inicjalizacji StackManager."""
    assert stack_manager.workspace_root == Path(temp_workspace).resolve()
    assert stack_manager.stacks_dir.exists()
    assert stack_manager.stacks_dir.name == "stacks"


def test_stack_manager_check_docker_compose():
    """Test sprawdzania dostępności docker-compose."""
    # StackManager powinien zostać zainicjalizowany bez błędów
    # jeśli docker-compose jest dostępny
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = StackManager(workspace_root=tmpdir)
            assert manager.workspace_root == Path(tmpdir).resolve()
    except RuntimeError:
        pytest.skip("Docker Compose nie jest dostępny w środowisku testowym")


def test_deploy_stack_simple(stack_manager):
    """Test wdrożenia prostego stacka."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 10
"""
    stack_name = "test-stack"

    success, message = stack_manager.deploy_stack(compose_content, stack_name)

    # Sprawdź czy plik został utworzony
    compose_file = stack_manager.stacks_dir / stack_name / "docker-compose.yml"
    assert compose_file.exists()

    # Posprzątaj
    if success:
        stack_manager.destroy_stack(stack_name)


def test_deploy_stack_creates_directory(stack_manager):
    """Test czy deploy_stack tworzy katalog stacka."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 5
"""
    stack_name = "dir-test-stack"

    stack_manager.deploy_stack(compose_content, stack_name)

    stack_dir = stack_manager.stacks_dir / stack_name
    assert stack_dir.exists()
    assert stack_dir.is_dir()

    # Posprzątaj
    stack_manager.destroy_stack(stack_name)


def test_deploy_stack_saves_compose_file(stack_manager):
    """Test czy deploy_stack zapisuje plik docker-compose.yml."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 5
"""
    stack_name = "file-test-stack"

    stack_manager.deploy_stack(compose_content, stack_name)

    compose_file = stack_manager.stacks_dir / stack_name / "docker-compose.yml"
    assert compose_file.exists()
    assert compose_content in compose_file.read_text()

    # Posprzątaj
    stack_manager.destroy_stack(stack_name)


def test_destroy_stack_nonexistent(stack_manager):
    """Test usuwania nieistniejącego stacka."""
    success, message = stack_manager.destroy_stack("nonexistent-stack")
    assert not success
    assert "nie istnieje" in message.lower()


def test_get_running_stacks_empty(stack_manager):
    """Test pobierania listy stacków gdy nie ma aktywnych."""
    stacks = stack_manager.get_running_stacks()
    assert isinstance(stacks, list)
    # Lista może być pusta lub zawierać stacki z innych testów


def test_get_stack_status_nonexistent(stack_manager):
    """Test pobierania statusu nieistniejącego stacka."""
    success, status = stack_manager.get_stack_status("nonexistent-stack")
    assert not success
    assert "error" in status


def test_get_service_logs_nonexistent_stack(stack_manager):
    """Test pobierania logów z nieistniejącego stacka."""
    success, logs = stack_manager.get_service_logs(
        "nonexistent-stack", "nonexistent-service"
    )
    assert not success


def test_stack_manager_workspace_isolation(temp_workspace):
    """Test izolacji workspace między różnymi instancjami."""
    manager1 = StackManager(workspace_root=temp_workspace)
    manager2 = StackManager(workspace_root=temp_workspace)

    # Oba managery powinny wskazywać na ten sam katalog stacków
    assert manager1.stacks_dir == manager2.stacks_dir


def test_deploy_stack_with_custom_project_name(stack_manager):
    """Test wdrożenia stacka z niestandardową nazwą projektu."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 5
"""
    stack_name = "custom-stack"
    project_name = "custom-project"

    success, message = stack_manager.deploy_stack(
        compose_content, stack_name, project_name=project_name
    )

    # Sprawdź czy plik został utworzony
    compose_file = stack_manager.stacks_dir / stack_name / "docker-compose.yml"
    assert compose_file.exists()

    # Posprzątaj z tą samą nazwą projektu
    if success:
        stack_manager.destroy_stack(stack_name, project_name=project_name)


def test_deploy_stack_invalid_yaml(stack_manager):
    """Test wdrożenia stacka z nieprawidłowym YAML."""
    compose_content = "invalid: yaml: content: [[[{"
    stack_name = "invalid-stack"

    success, message = stack_manager.deploy_stack(compose_content, stack_name)

    # Deployment powinien się nie powieść
    assert not success
    assert "błąd" in message.lower() or "error" in message.lower()

    # Plik powinien zostać utworzony mimo błędu
    compose_file = stack_manager.stacks_dir / stack_name / "docker-compose.yml"
    assert compose_file.exists()
