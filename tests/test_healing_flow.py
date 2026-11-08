import asyncio
from uuid import uuid4

import pytest

from venom_core.core.flows.healing import HealingFlow


class DummyDockerHabitat:
    def execute(self, _cmd: str, timeout: int = 120):
        return "ok"


class DummyTestSkill:
    def __init__(self, reports):
        self.reports = iter(reports)
        self.calls = 0

    async def run_pytest(self, test_path: str = ".", timeout: int = 60):
        _, report = await self.run_pytest_with_evidence(test_path)
        return report

    async def run_pytest_with_evidence(self, test_path: str = "."):
        await asyncio.sleep(0)
        self.calls += 1
        return next(self.reports)


class DummyGuardianAgent:
    def __init__(self, kernel=None, test_skill=None):
        self.calls = []

    async def process(self, prompt: str) -> str:
        await asyncio.sleep(0)
        self.calls.append(prompt)
        return "ticket"


class DummyCoderAgent:
    calls = 0

    async def process(self, prompt: str) -> str:
        await asyncio.sleep(0)
        self.calls += 1
        return "All tests PASSED and fix applied"


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
        lambda habitat=None: DummyTestSkill([(0, "PASSED")]),
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
        lambda habitat=None: DummyTestSkill([(1, "FAILED: 1"), (0, "PASSED")]),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reports", "success", "attempts"),
    [
        (
            [(1, "Exit Code: 1\nPassed: 4\nFailed: 1")] * 3
            + [(1, "Final test still FAILED")],
            False,
            3,
        ),
        ([(1, "FAILED: 1")] * 3 + [(0, "PASSED")], True, 3),
        ([(None, "Test runner unavailable")], False, 0),
    ],
    ids=["false-green", "verify-last-fix", "runner-unavailable"],
)
async def test_healing_flow_uses_last_pytest_exit_code(
    monkeypatch, reports, success, attempts
):
    monkeypatch.setattr(
        "venom_core.infrastructure.docker_habitat.DockerHabitat", DummyDockerHabitat
    )
    test_skill = DummyTestSkill(reports)
    monkeypatch.setattr(
        "venom_core.execution.skills.test_skill.TestSkill",
        lambda habitat=None: test_skill,
    )
    monkeypatch.setattr("venom_core.agents.guardian.GuardianAgent", DummyGuardianAgent)

    dispatcher = DummyDispatcher()
    state = DummyStateManager()
    flow = HealingFlow(state_manager=state, task_dispatcher=dispatcher)
    result = await flow.execute(task_id=uuid4(), test_path=".")

    assert result["success"] is success
    assert result["iterations"] == test_skill.calls == len(reports)
    assert result["final_report"] == reports[-1][1]
    assert result["exit_code"] == reports[-1][0]
    assert dispatcher.coder_agent.calls == attempts
    assert all("poprawka zastosowana" not in log.lower() for _, log in state.logs)
