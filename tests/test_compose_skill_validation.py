"""Testy walidacji i policy guardów dla ComposeSkill (bez Dockera)."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.execution.skills.compose_skill import ComposeSkill


class _FakeStackManager:
    def __init__(self, workspace_root=None):
        self.workspace_root = workspace_root or "."

    def deploy_stack(self, compose_content: str, stack_name: str):
        return True, f"stack {stack_name} deployed"

    def destroy_stack(self, stack_name: str, remove_volumes: bool = True):
        return True, f"stack {stack_name} destroyed"

    def get_service_logs(self, stack_name: str, service: str, tail: int = 50):
        return True, f"logs for {stack_name}/{service}"

    def get_stack_status(self, stack_name: str):
        return True, {"status": "running", "details": ""}

    def get_running_stacks(self):
        return []


@pytest.fixture
def compose_skill(monkeypatch):
    monkeypatch.setattr(
        "venom_core.execution.skills.compose_skill.StackManager", _FakeStackManager
    )
    workspace_root = (
        Path(__file__).resolve().parent
        / ".compose_skill_test_workspace"
        / f"run_{uuid4().hex}"
    )
    workspace_root.mkdir(parents=True, exist_ok=True)
    try:
        yield ComposeSkill(workspace_root=str(workspace_root))
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_destroy_environment_validates_stack_name(compose_skill):
    result = await compose_skill.destroy_environment("../escape")
    assert "Nieprawidłowa nazwa stacka" in result


@pytest.mark.asyncio
async def test_check_service_health_validates_service_name(compose_skill):
    result = await compose_skill.check_service_health("ok-stack", "../bad-service")
    assert "Nieprawidłowa nazwa serwisu" in result


@pytest.mark.asyncio
async def test_compose_policy_warn_mode_allows_with_warning(compose_skill, monkeypatch):
    monkeypatch.setenv("VENOM_COMPOSE_POLICY_MODE", "warn")
    compose_content = """
version: '3.8'
services:
  app:
    image: alpine:latest
    privileged: true
"""
    result = await compose_skill.create_environment(compose_content, "safe-stack")
    assert "✅" in result
    assert "Ostrzeżenia polityki bezpieczeństwa" in result


@pytest.mark.asyncio
async def test_compose_policy_block_mode_blocks(compose_skill, monkeypatch):
    monkeypatch.setenv("VENOM_COMPOSE_POLICY_MODE", "block")
    compose_content = """
version: '3.8'
services:
  app:
    image: alpine:latest
    network_mode: host
"""
    result = await compose_skill.create_environment(compose_content, "safe-stack")
    assert "zablokowany przez politykę bezpieczeństwa" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host_mount",
    [
        "/:/container_data",
        "C:/:/container_data",
    ],
)
async def test_compose_policy_blocks_host_root_mounts(
    compose_skill, monkeypatch, host_mount
):
    monkeypatch.setenv("VENOM_COMPOSE_POLICY_MODE", "block")
    compose_content = f"""
version: '3.8'
services:
  app:
    image: alpine:latest
    volumes:
      - {host_mount}
"""
    result = await compose_skill.create_environment(compose_content, "safe-stack")
    assert "zablokowany przez politykę bezpieczeństwa" in result
