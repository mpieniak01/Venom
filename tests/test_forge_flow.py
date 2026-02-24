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


# ---------------------------------------------------------------------------
# Core workflow paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forge_flow_success(monkeypatch):
    """Happy path: tool created and loaded successfully."""
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
    """Toolmaker failure results in success=False with Toolmaker mention."""
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
    """Skill reload failure results in success=False."""
    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(create_success=True, reload_success=False),
    )

    result = await flow.execute(uuid4(), "spec", "tool_x")

    assert result["success"] is False
    assert "załadować" in result["message"]


# ---------------------------------------------------------------------------
# _broadcast_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_event_without_broadcaster():
    """_broadcast_event is a no-op when no broadcaster is configured."""
    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(),
        event_broadcaster=None,
    )
    # Must not raise
    await flow._broadcast_event(
        event_type="FORGE_STARTED",
        message="test message",
        agent="Toolmaker",
        data={"key": "value"},
    )


@pytest.mark.asyncio
async def test_broadcast_event_with_broadcaster():
    """_broadcast_event calls broadcaster.broadcast_event when provided."""
    broadcast_calls = []

    class FakeBroadcaster:
        async def broadcast_event(self, *, event_type, message, agent=None, data=None):
            broadcast_calls.append(
                {"event_type": event_type, "message": message, "agent": agent}
            )

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=DummyDispatcher(),
        event_broadcaster=FakeBroadcaster(),
    )

    await flow._broadcast_event(
        event_type="TEST_EVENT",
        message="hello",
        agent="AgentX",
        data={},
    )

    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["event_type"] == "TEST_EVENT"
    assert broadcast_calls[0]["agent"] == "AgentX"


# ---------------------------------------------------------------------------
# Exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forge_flow_handles_unexpected_exception(monkeypatch):
    """Unexpected exception in execute is caught and reported in result."""

    class BrokenDispatcher:
        kernel = object()
        toolmaker_agent = None  # Will cause AttributeError

        @property
        def skill_manager(self):
            raise RuntimeError("dispatcher broken")

    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    flow = forge_mod.ForgeFlow(
        state_manager=DummyStateManager(),
        task_dispatcher=BrokenDispatcher(),
    )

    result = await flow.execute(uuid4(), "spec", "bad_tool")

    assert result["success"] is False
    assert "bad_tool" == result["tool_name"]


# ---------------------------------------------------------------------------
# State manager receives logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forge_flow_logs_to_state_manager(monkeypatch):
    """Successful forge flow writes multiple log entries to state_manager."""
    monkeypatch.setattr(forge_mod, "GuardianAgent", DummyGuardianAgent)

    sm = DummyStateManager()
    await forge_mod.ForgeFlow(
        state_manager=sm,
        task_dispatcher=DummyDispatcher(create_success=True, reload_success=True),
    ).execute(uuid4(), "spec", "logged_tool")

    # At least the initial FORGE log should be present
    assert len(sm.logs) >= 1
    messages = [msg for _, msg in sm.logs]
    assert any("logged_tool" in m for m in messages)
