import asyncio
from uuid import uuid4

import pytest

import venom_core.core.flows.forge as forge_mod


class DummyStateManager:
    def __init__(self):
        self.logs = []

    def add_log(self, task_id, message: str):
        self.logs.append((task_id, message))


class DummyToolmaker:
    def __init__(self, create_success=True):
        self.create_success = create_success

    async def create_tool(self, specification: str, tool_name: str, output_dir=None):
        await asyncio.sleep(0)
        if self.create_success:
            return True, f"# tool {tool_name}"
        return False, "tool error"

    async def create_test(self, tool_name: str, tool_code: str, output_dir=None):
        await asyncio.sleep(0)
        return True, "# test"


class DummySkillManager:
    def __init__(self, reload_success=True):
        self.reload_success = reload_success

    def reload_skill(self, _tool_name: str) -> bool:
        return self.reload_success


class DummyDispatcher:
    def __init__(self, create_success=True, reload_success=True):
        self.kernel = object()
        self.toolmaker_agent = DummyToolmaker(create_success=create_success)
        self.skill_manager = DummySkillManager(reload_success=reload_success)


class DummyGuardianAgent:
    def __init__(self, kernel=None):
        self.calls = []

    async def process(self, prompt: str) -> str:
        await asyncio.sleep(0)
        self.calls.append(prompt)
        return "APPROVED"


@pytest.mark.asyncio
async def test_forge_flow_success(monkeypatch):
    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(create_success=True, reload_success=True),
    )

    result = await flow.execute(uuid4(), "spec", "cool_tool")

    assert result["success"] is True
    assert result["tool_name"] == "cool_tool"


@pytest.mark.asyncio
async def test_forge_flow_toolmaker_failure(monkeypatch):
    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(create_success=False, reload_success=True),
    )

    result = await flow.execute(uuid4(), "spec", "broken_tool")

    assert result["success"] is False
    assert "Toolmaker" in result["message"]


@pytest.mark.asyncio
async def test_forge_flow_reload_failure(monkeypatch):
    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(create_success=True, reload_success=False),
    )

    result = await flow.execute(uuid4(), "spec", "tool_x")

    assert result["success"] is False
    assert "załadować" in result["message"]
