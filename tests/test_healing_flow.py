from uuid import uuid4

import pytest

from venom_core.core.flows.healing import HealingFlow


class DummyDockerHabitat:
    def execute(self, _cmd: str, timeout: int = 120):
        return "ok"


class DummyTestSkill:
    def __init__(self, reports):
        self.reports = list(reports)

    async def run_pytest(self, test_path: str = ".", timeout: int = 60):
        return self.reports.pop(0)


class DummyGuardianAgent:
    def __init__(self, kernel=None, test_skill=None):
        self.calls = []

    async def process(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "ticket"


class DummyCoderAgent:
    async def process(self, prompt: str) -> str:
        return "fix applied"


class DummyStateManager:
    def __init__(self):
        self.logs = []

    def add_log(self, task_id, message: str):
        self.logs.append((task_id, message))


class DummyDispatcher:
    def __init__(self):
        self.kernel = object()
        self.coder_agent = DummyCoderAgent()


@pytest.mark.asyncio
async def test_healing_flow_success_first_pass(monkeypatch):
    monkeypatch.setattr(
        "venom_core.infrastructure.docker_habitat.DockerHabitat",
        DummyDockerHabitat,
    )
    monkeypatch.setattr(
        "venom_core.execution.skills.test_skill.TestSkill",
        lambda habitat=None: DummyTestSkill(["PASSED"]),
    )
    monkeypatch.setattr(
        "venom_core.agents.guardian.GuardianAgent",
        DummyGuardianAgent,
    )

    flow = HealingFlow(
        state_manager=DummyStateManager(), task_dispatcher=DummyDispatcher()
    )
    result = await flow.execute(task_id=uuid4(), test_path=".")

    assert result["success"] is True
    assert result["iterations"] == 1


@pytest.mark.asyncio
async def test_healing_flow_recovers_after_fix(monkeypatch):
    monkeypatch.setattr(
        "venom_core.infrastructure.docker_habitat.DockerHabitat",
        DummyDockerHabitat,
    )
    monkeypatch.setattr(
        "venom_core.execution.skills.test_skill.TestSkill",
        lambda habitat=None: DummyTestSkill(["FAILED: 1", "PASSED"]),
    )
    monkeypatch.setattr(
        "venom_core.agents.guardian.GuardianAgent",
        DummyGuardianAgent,
    )

    flow = HealingFlow(
        state_manager=DummyStateManager(), task_dispatcher=DummyDispatcher()
    )
    result = await flow.execute(task_id=uuid4(), test_path=".")

    assert result["success"] is True
    assert result["iterations"] == 2
