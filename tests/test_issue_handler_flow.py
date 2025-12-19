from dataclasses import dataclass
from uuid import uuid4

import pytest

from venom_core.core.flows.issue_handler import IssueHandlerFlow


@dataclass
class FakeTask:
    id: str


class FakeStateManager:
    def __init__(self) -> None:
        self.logs = []
        self.status_updates = []

    def create_task(self, content: str):
        return FakeTask(id=str(uuid4()))

    def add_log(self, task_id, message: str) -> None:
        self.logs.append((task_id, message))

    async def update_status(self, task_id, status, result=None) -> None:
        self.status_updates.append((task_id, status, result))


class FakeAgent:
    def __init__(self, response: str) -> None:
        self.response = response
        self.handled = []

    async def process(self, prompt: str) -> str:
        self.handled.append(prompt)
        return self.response

    async def handle_issue(self, issue_number: int) -> str:
        self.handled.append(str(issue_number))
        return self.response

    async def finalize_issue(
        self, issue_number: int, branch_name: str, pr_title: str, pr_body: str
    ) -> str:
        self.handled.append(f"finalize:{issue_number}:{branch_name}")
        return "PR created"


class FakeDispatcher:
    def __init__(self, agent_map):
        self.agent_map = agent_map


@pytest.mark.asyncio
async def test_issue_handler_missing_integrator():
    dispatcher = FakeDispatcher(agent_map={})
    flow = IssueHandlerFlow(
        state_manager=FakeStateManager(), task_dispatcher=dispatcher
    )

    result = await flow.execute(issue_number=123)

    assert result["success"] is False
    assert "IntegratorAgent" in result["message"]


@pytest.mark.asyncio
async def test_issue_handler_success_path():
    integrator = FakeAgent("Issue details")
    architect = FakeAgent("Plan")
    coder = FakeAgent("Fix implemented")

    dispatcher = FakeDispatcher(
        agent_map={
            "GIT_OPERATIONS": integrator,
            "COMPLEX_PLANNING": architect,
            "CODE_GENERATION": coder,
        }
    )
    flow = IssueHandlerFlow(
        state_manager=FakeStateManager(), task_dispatcher=dispatcher
    )

    result = await flow.execute(issue_number=42)

    assert result["success"] is True
    assert result["issue_number"] == 42


@pytest.mark.asyncio
async def test_issue_handler_missing_architect():
    integrator = FakeAgent("Issue details")
    dispatcher = FakeDispatcher(agent_map={"GIT_OPERATIONS": integrator})
    flow = IssueHandlerFlow(
        state_manager=FakeStateManager(), task_dispatcher=dispatcher
    )

    result = await flow.execute(issue_number=77)

    assert result["success"] is False
    assert "ArchitectAgent" in result["message"]


@pytest.mark.asyncio
async def test_issue_handler_missing_coder():
    integrator = FakeAgent("Issue details")
    architect = FakeAgent("Plan")
    dispatcher = FakeDispatcher(
        agent_map={
            "GIT_OPERATIONS": integrator,
            "COMPLEX_PLANNING": architect,
        }
    )
    flow = IssueHandlerFlow(
        state_manager=FakeStateManager(), task_dispatcher=dispatcher
    )

    result = await flow.execute(issue_number=88)

    assert result["success"] is False
    assert "CoderAgent" in result["message"]
