from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.core.evolution_coordinator import EvolutionCoordinator
from venom_core.infrastructure.mirror_world import InstanceInfo


class DummySystemEngineer:
    def __init__(self, response: str) -> None:
        self.response = response

    async def process(self, _prompt: str) -> str:
        return self.response


class DummyMirrorWorld:
    def __init__(self, instance_info: InstanceInfo, verify_result=(True, "ok")) -> None:
        self.instance_info = instance_info
        self.verify_result = verify_result
        self.destroy_calls = []

    def spawn_shadow_instance(
        self, branch_name: str, project_root: Path
    ) -> InstanceInfo:
        return self.instance_info

    async def verify_instance(self, _instance_id: str):
        return self.verify_result

    async def destroy_instance(self, instance_id: str, cleanup: bool = True):
        self.destroy_calls.append((instance_id, cleanup))


class DummyCoreSkill:
    def __init__(
        self, syntax_result: str = "✅ OK", restart_result: str = "restarted"
    ) -> None:
        self.syntax_result = syntax_result
        self.restart_result = restart_result
        self.restart_called = False

    async def verify_syntax(self, _path: str) -> str:
        return self.syntax_result

    async def restart_service(self, confirm: bool = True) -> str:
        self.restart_called = True
        return self.restart_result


@pytest.mark.asyncio
async def test_evolve_analysis_rejected(tmp_path):
    instance_info = InstanceInfo(
        instance_id="shadow-1",
        port=8001,
        branch_name="evolution/test",
        workspace_path=tmp_path,
        status="running",
    )
    coordinator = EvolutionCoordinator(
        system_engineer=DummySystemEngineer("OK"),
        mirror_world=DummyMirrorWorld(instance_info),
        core_skill=DummyCoreSkill(),
        git_skill=object(),
    )

    result = await coordinator.evolve(uuid4(), "tylko zapytanie", tmp_path)

    assert result["success"] is False
    assert result["phase"] == "analysis"


@pytest.mark.asyncio
async def test_evolve_modification_failure(tmp_path):
    instance_info = InstanceInfo(
        instance_id="shadow-1",
        port=8001,
        branch_name="evolution/test",
        workspace_path=tmp_path,
        status="running",
    )
    coordinator = EvolutionCoordinator(
        system_engineer=DummySystemEngineer("❌ brak zmian"),
        mirror_world=DummyMirrorWorld(instance_info),
        core_skill=DummyCoreSkill(),
        git_skill=object(),
    )

    result = await coordinator.evolve(uuid4(), "dodaj nowa funkcje", tmp_path)

    assert result["success"] is False
    assert result["phase"] == "modification"


@pytest.mark.asyncio
async def test_evolve_success_path(tmp_path):
    (tmp_path / "module.py").write_text("print('ok')", encoding="utf-8")
    instance_info = InstanceInfo(
        instance_id="shadow-1",
        port=8001,
        branch_name="evolution/test",
        workspace_path=tmp_path,
        status="running",
    )
    mirror_world = DummyMirrorWorld(instance_info, verify_result=(True, "healthy"))
    coordinator = EvolutionCoordinator(
        system_engineer=DummySystemEngineer("Zmieniono kod"),
        mirror_world=mirror_world,
        core_skill=DummyCoreSkill(),
        git_skill=object(),
    )

    result = await coordinator.evolve(uuid4(), "dodaj nowa funkcje", tmp_path)

    assert result["success"] is True
    assert result["phase"] == "completed"
    assert mirror_world.destroy_calls == [("shadow-1", True)]


@pytest.mark.asyncio
async def test_evolve_verification_syntax_failure(tmp_path):
    (tmp_path / "bad.py").write_text("print('oops')", encoding="utf-8")
    instance_info = InstanceInfo(
        instance_id="shadow-2",
        port=8002,
        branch_name="evolution/test",
        workspace_path=tmp_path,
        status="running",
    )
    mirror_world = DummyMirrorWorld(instance_info, verify_result=(True, "healthy"))
    coordinator = EvolutionCoordinator(
        system_engineer=DummySystemEngineer("OK"),
        mirror_world=mirror_world,
        core_skill=DummyCoreSkill(syntax_result="❌ Syntax error"),
        git_skill=object(),
    )

    result = await coordinator.evolve(uuid4(), "popraw bledy", tmp_path)

    assert result["success"] is False
    assert result["phase"] == "verification_failed"
    assert mirror_world.destroy_calls == [("shadow-2", True)]


@pytest.mark.asyncio
async def test_trigger_restart_requires_confirmation(tmp_path):
    coordinator = EvolutionCoordinator(
        system_engineer=DummySystemEngineer("OK"),
        mirror_world=DummyMirrorWorld(
            InstanceInfo(
                instance_id="shadow-3",
                port=8003,
                branch_name="evolution/test",
                workspace_path=tmp_path,
                status="running",
            )
        ),
        core_skill=DummyCoreSkill(restart_result="restart-ok"),
        git_skill=object(),
    )

    assert (
        await coordinator.trigger_restart(confirm=False)
        == "❌ Restart wymaga potwierdzenia"
    )
    assert await coordinator.trigger_restart(confirm=True) == "restart-ok"
