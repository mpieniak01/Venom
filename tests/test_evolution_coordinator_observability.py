import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.core.evolution_coordinator import EvolutionCoordinator
from venom_core.infrastructure.mirror_world import InstanceInfo


class _Engineer:
    def __init__(self, response: str):
        self._response = response

    async def process(self, _prompt: str) -> str:
        await asyncio.sleep(0)
        return self._response


class _Mirror:
    def __init__(self, instance_info: InstanceInfo):
        self.instance_info = instance_info

    def spawn_shadow_instance(
        self, branch_name: str, project_root: Path
    ) -> InstanceInfo:
        return self.instance_info

    async def verify_instance(self, _instance_id: str):
        await asyncio.sleep(0)
        return (True, "ok")

    async def destroy_instance(self, _instance_id: str, cleanup: bool = True):
        await asyncio.sleep(0)


class _Core:
    async def verify_syntax(self, _path: str) -> str:
        await asyncio.sleep(0)
        return "✅ OK"


class _Lessons:
    def __init__(self):
        self.saved = []

    def add_lesson(self, **kwargs):
        self.saved.append(kwargs)


class _Git:
    async def merge(self, _branch: str):
        await asyncio.sleep(0)
        return "✅ merged"

    def _get_repo(self):
        class _Branch:
            name = "main"

        class _Repo:
            active_branch = _Branch()

        return _Repo()


@pytest.mark.asyncio
async def test_evolution_audit_and_lesson_written_on_success(tmp_path, monkeypatch):
    (tmp_path / "ok.py").write_text("print('ok')", encoding="utf-8")
    captured = []
    monkeypatch.setattr(
        "venom_core.core.evolution_coordinator.append_learning_log_entry",
        lambda entry: captured.append(entry),
    )

    lessons = _Lessons()
    coordinator = EvolutionCoordinator(
        system_engineer=_Engineer("applied"),
        mirror_world=_Mirror(
            InstanceInfo(
                instance_id="shadow-obs",
                port=8011,
                branch_name="evolution/test",
                workspace_path=tmp_path,
                status="running",
            )
        ),
        core_skill=_Core(),
        git_skill=_Git(),
        lessons_store=lessons,
    )

    result = await coordinator.evolve(uuid4(), "dodaj endpoint health", tmp_path)

    assert result["success"] is True
    assert any(item.get("phase") == "start" for item in captured)
    assert any(item.get("phase") == "completed" for item in captured)
    assert lessons.saved
    assert lessons.saved[0]["result"] == "success"


@pytest.mark.asyncio
async def test_evolution_audit_written_on_analysis_failure(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(
        "venom_core.core.evolution_coordinator.append_learning_log_entry",
        lambda entry: captured.append(entry),
    )

    coordinator = EvolutionCoordinator(
        system_engineer=_Engineer("applied"),
        mirror_world=_Mirror(
            InstanceInfo(
                instance_id="shadow-obs-2",
                port=8012,
                branch_name="evolution/test",
                workspace_path=tmp_path,
                status="running",
            )
        ),
        core_skill=_Core(),
        git_skill=_Git(),
    )

    result = await coordinator.evolve(uuid4(), "hello", tmp_path)
    assert result["success"] is False
    assert any(
        item.get("phase") == "analysis" and item.get("status") == "failed"
        for item in captured
    )
