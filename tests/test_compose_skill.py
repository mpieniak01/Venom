"""Testy jednostkowe dla ComposeSkill."""

import tempfile

import pytest

from venom_core.execution.skills.compose_skill import ComposeSkill


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def compose_skill(temp_workspace):
    """Fixture dla ComposeSkill."""
    return ComposeSkill(workspace_root=temp_workspace)


def test_compose_skill_initialization(compose_skill):
    """Test inicjalizacji ComposeSkill."""
    assert compose_skill.stack_manager is not None


@pytest.mark.asyncio
async def test_create_environment_simple(compose_skill):
    """Test tworzenia prostego środowiska."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 10
"""
    stack_name = "test-env"

    result = await compose_skill.create_environment(compose_content, stack_name)

    assert "✅" in result or "utworzone" in result.lower()

    # Posprzątaj
    await compose_skill.destroy_environment(stack_name)


@pytest.mark.asyncio
async def test_create_environment_invalid_name(compose_skill):
    """Test tworzenia środowiska z nieprawidłową nazwą."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
"""
    # Nazwa z wielkimi literami i spacjami - nieprawidłowa
    stack_name = "Invalid Stack Name!"

    result = await compose_skill.create_environment(compose_content, stack_name)

    assert "Błąd" in result or "Nieprawidłowa" in result


@pytest.mark.asyncio
async def test_destroy_environment(compose_skill):
    """Test usuwania środowiska."""
    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 5
"""
    stack_name = "destroy-test"

    # Najpierw utwórz środowisko
    await compose_skill.create_environment(compose_content, stack_name)

    # Następnie usuń
    result = await compose_skill.destroy_environment(stack_name)

    assert "✅" in result or "usunięte" in result.lower()


@pytest.mark.asyncio
async def test_destroy_environment_nonexistent(compose_skill):
    """Test usuwania nieistniejącego środowiska."""
    result = await compose_skill.destroy_environment("nonexistent-env")

    assert "❌" in result or "nie istnieje" in result.lower()


@pytest.mark.asyncio
async def test_list_environments_empty(compose_skill):
    """Test listowania środowisk gdy nie ma aktywnych."""
    result = await compose_skill.list_environments()

    assert "Brak aktywnych środowisk" in result or "📦" in result


@pytest.mark.asyncio
async def test_get_environment_status_nonexistent(compose_skill):
    """Test pobierania statusu nieistniejącego środowiska."""
    result = await compose_skill.get_environment_status("nonexistent-env")

    assert "❌" in result or "nie istnieje" in result.lower()


@pytest.mark.asyncio
async def test_check_service_health_nonexistent(compose_skill):
    """Test sprawdzania zdrowia nieistniejącego serwisu."""
    result = await compose_skill.check_service_health("nonexistent-env", "nonexistent")

    assert "❌" in result or "nie można" in result.lower()


@pytest.mark.asyncio
async def test_process_port_placeholders_no_placeholders(compose_skill):
    """Test przetwarzania zawartości bez placeholderów."""
    content = """
version: '3.8'
services:
  app:
    image: nginx
    ports:
      - "8080:80"
"""
    result = await compose_skill._process_port_placeholders(content)
    assert result == content


@pytest.mark.asyncio
async def test_process_port_placeholders_simple(compose_skill):
    """Test przetwarzania prostego placeholdera portu."""
    content = """
version: '3.8'
services:
  app:
    image: nginx
    ports:
      - "{{PORT}}:80"
"""
    result = await compose_skill._process_port_placeholders(content)

    # Placeholder powinien zostać zastąpiony liczbą
    assert "{{PORT}}" not in result
    assert ":" in result
    # Sprawdź czy zastąpiono prawidłowym portem (liczba)
    import re

    matches = re.findall(r"(\d+):80", result)
    assert len(matches) > 0
    port = int(matches[0])
    assert 8000 <= port <= 9000


@pytest.mark.asyncio
async def test_process_port_placeholders_with_preferred(compose_skill):
    """Test przetwarzania placeholdera z preferowanym portem."""
    content = """
version: '3.8'
services:
  app:
    image: nginx
    ports:
      - "{{PORT:8888}}:80"
"""
    result = await compose_skill._process_port_placeholders(content)

    # Placeholder powinien zostać zastąpiony
    assert "{{PORT" not in result
    # Preferowany port może być użyty jeśli jest wolny
    assert ":80" in result


def test_extract_port_info_simple(compose_skill):
    """Test wyciągania informacji o portach."""
    content = """
version: '3.8'
services:
  app:
    ports:
      - "8080:80"
      - "8443:443"
"""
    result = compose_skill._extract_port_info(content)

    assert "8080" in result
    assert "80" in result
    assert "8443" in result
    assert "443" in result


def test_extract_port_info_no_ports(compose_skill):
    """Test wyciągania informacji gdy nie ma portów."""
    content = """
version: '3.8'
services:
  app:
    image: nginx
"""
    result = compose_skill._extract_port_info(content)

    assert result == ""


@pytest.mark.asyncio
async def test_create_environment_with_port_placeholder(compose_skill):
    """Test integracyjny: tworzenie środowiska z placeholderem portu."""
    compose_content = """
version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "{{PORT}}:80"
    command: sleep 5
"""
    stack_name = "port-test"

    result = await compose_skill.create_environment(compose_content, stack_name)

    # Sprawdź czy środowisko zostało utworzone
    assert "✅" in result or "utworzone" in result.lower()

    # Posprzątaj
    await compose_skill.destroy_environment(stack_name)


def test_compose_skill_has_kernel_functions(compose_skill):
    """Test czy ComposeSkill ma wymagane @kernel_function dekoratory."""
    # Sprawdź czy metody mają odpowiednie atrybuty
    assert hasattr(compose_skill.create_environment, "__kernel_function__") or hasattr(
        compose_skill.create_environment, "__kernel_function_name__"
    )
    assert hasattr(compose_skill.destroy_environment, "__kernel_function__") or hasattr(
        compose_skill.destroy_environment, "__kernel_function_name__"
    )
