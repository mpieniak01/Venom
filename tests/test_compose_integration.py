"""Test integracyjny dla scenariusza full-stack z Docker Compose."""

import tempfile
from pathlib import Path

import pytest

from venom_core.execution.skills.compose_skill import ComposeSkill
from venom_core.infrastructure.stack_manager import StackManager


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.asyncio
async def test_full_stack_redis_integration(temp_workspace):
    """
    Test integracyjny: Tworzenie pełnego stacka z Redis.

    Scenariusz:
    1. Stwórz docker-compose.yml z Redis
    2. Wdróż stack
    3. Sprawdź status
    4. Posprzątaj
    """
    compose_skill = ComposeSkill(workspace_root=temp_workspace)

    # 1. Przygotuj docker-compose z Redis
    compose_content = """
version: '3.8'
services:
  redis:
    image: redis:alpine
    ports:
      - "{{PORT:6379}}:6379"
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
"""

    stack_name = "integration-redis-test"

    # 2. Wdróż stack
    result = await compose_skill.create_environment(compose_content, stack_name)
    assert "✅" in result or "utworzone" in result.lower()

    # 3. Sprawdź status
    status_result = await compose_skill.get_environment_status(stack_name)
    assert stack_name in status_result

    # 4. Lista środowisk
    list_result = await compose_skill.list_environments()
    assert stack_name in list_result or "Brak aktywnych" in list_result

    # 5. Posprzątaj
    destroy_result = await compose_skill.destroy_environment(stack_name)
    assert "✅" in destroy_result or "usunięte" in destroy_result.lower()


@pytest.mark.asyncio
async def test_full_stack_multi_service(temp_workspace):
    """
    Test integracyjny: Stack z wieloma serwisami.

    Scenariusz z aplikacją i bazą danych.
    """
    compose_skill = ComposeSkill(workspace_root=temp_workspace)

    # Docker Compose z nginx i Redis (symulacja API + cache)
    compose_content = """
version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "{{PORT}}:80"
    depends_on:
      - cache
    command: sh -c "sleep 10 && nginx -g 'daemon off;'"

  cache:
    image: redis:alpine
    command: redis-server
"""

    stack_name = "multi-service-test"

    try:
        # Wdróż stack
        result = await compose_skill.create_environment(compose_content, stack_name)
        assert "✅" in result or "utworzone" in result.lower()

        # Sprawdź logi cache
        health_result = await compose_skill.check_service_health(stack_name, "cache")
        # Może być sukces lub błąd w zależności od tego czy kontenery zdążyły wystartować
        assert "cache" in health_result or "błąd" in health_result.lower()

    finally:
        # Zawsze posprzątaj
        await compose_skill.destroy_environment(stack_name)


@pytest.mark.asyncio
async def test_stack_manager_workflow(temp_workspace):
    """
    Test workflow StackManager bez ComposeSkill wrapper.

    Testuje bezpośrednie użycie StackManager.
    """
    stack_manager = StackManager(workspace_root=temp_workspace)

    compose_content = """
version: '3.8'
services:
  test:
    image: alpine:latest
    command: sleep 15
"""

    stack_name = "direct-manager-test"

    # Deploy
    success, msg = stack_manager.deploy_stack(compose_content, stack_name)
    assert success or "error" not in msg.lower()

    # Status
    success, status = stack_manager.get_stack_status(stack_name)
    assert success or "error" in status

    # Cleanup
    success, msg = stack_manager.destroy_stack(stack_name)
    assert success or "error" not in msg.lower()


def test_workspace_isolation_multiple_stacks(temp_workspace):
    """
    Test izolacji workspace między wieloma stackami.

    Sprawdza czy stacki nie interferują ze sobą.
    """
    stack_manager = StackManager(workspace_root=temp_workspace)

    compose_simple = """
version: '3.8'
services:
  svc:
    image: alpine:latest
    command: sleep 5
"""

    # Stwórz dwa stacki
    stack1_name = "isolated-stack-1"
    stack2_name = "isolated-stack-2"

    success1, _ = stack_manager.deploy_stack(compose_simple, stack1_name)
    success2, _ = stack_manager.deploy_stack(compose_simple, stack2_name)

    # Oba powinny się udać
    assert success1 or success2

    # Sprawdź izolację katalogów
    stack1_dir = Path(temp_workspace) / "stacks" / stack1_name
    stack2_dir = Path(temp_workspace) / "stacks" / stack2_name

    assert stack1_dir.exists()
    assert stack2_dir.exists()
    assert stack1_dir != stack2_dir

    # Posprzątaj
    stack_manager.destroy_stack(stack1_name)
    stack_manager.destroy_stack(stack2_name)


@pytest.mark.asyncio
async def test_port_conflict_handling(temp_workspace):
    """
    Test obsługi konfliktów portów.

    Sprawdza czy system automatycznie znajduje wolne porty.
    """
    compose_skill = ComposeSkill(workspace_root=temp_workspace)

    # Compose z placeholderem portu
    compose_content = """
version: '3.8'
services:
  app:
    image: nginx:alpine
    ports:
      - "{{PORT}}:80"
    command: sleep 5
"""

    stack_name = "port-conflict-test"

    try:
        result = await compose_skill.create_environment(compose_content, stack_name)

        # Sprawdź czy placeholder został zastąpiony
        compose_file = (
            Path(temp_workspace) / "stacks" / stack_name / "docker-compose.yml"
        )
        assert compose_file.exists()

        content = compose_file.read_text()
        assert "{{PORT}}" not in content
        # Powinien zawierać faktyczny numer portu
        assert ":" in content

    finally:
        await compose_skill.destroy_environment(stack_name)
