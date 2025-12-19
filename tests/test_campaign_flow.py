from dataclasses import dataclass
from uuid import uuid4

import pytest

from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.goal_store import GoalStatus
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus, VenomTask


@dataclass
class FakeGoalTask:
    goal_id: str
    title: str
    description: str


@dataclass
class FakeMilestone:
    goal_id: str
    title: str
    progress: int = 0

    def get_progress(self) -> int:
        return self.progress


class FakeGoalStore:
    def __init__(self, tasks, milestone) -> None:
        self.tasks = list(tasks)
        self.milestone = milestone
        self.updates = []

    def get_next_task(self):
        if self.tasks:
            return self.tasks.pop(0)
        return None

    def get_next_milestone(self):
        return self.milestone

    def update_progress(self, goal_id, status: GoalStatus, task_id=None):
        self.updates.append((goal_id, status, task_id))
        if status == GoalStatus.COMPLETED and self.milestone:
            self.milestone.progress = 100

    def generate_roadmap_report(self):
        return "OK"


class FakeStateManager:
    def __init__(self) -> None:
        self.tasks = {}
        self.logs = []

    def create_task(self, content: str) -> VenomTask:
        task = VenomTask(content=content)
        self.tasks[task.id] = task
        return task

    def add_log(self, task_id, message: str) -> None:
        self.logs.append((task_id, message))

    def get_task(self, task_id):
        return self.tasks[task_id]

    async def update_status(self, task_id, status: TaskStatus, result=None) -> None:
        task = self.tasks[task_id]
        task.status = status
        task.result = result


@pytest.mark.asyncio
async def test_campaign_flow_requires_goal_store():
    flow = CampaignFlow(
        state_manager=FakeStateManager(), orchestrator_submit_task=lambda _: None
    )

    result = await flow.execute(goal_store=None, max_iterations=1)

    assert result["success"] is False
    assert "GoalStore" in result["message"]


@pytest.mark.asyncio
async def test_campaign_flow_success_path():
    state_manager = FakeStateManager()
    task_queue = [
        FakeGoalTask(goal_id="goal-1", title="Task A", description="Do A"),
    ]
    milestone = FakeMilestone(goal_id="goal-1", title="Milestone A", progress=0)
    goal_store = FakeGoalStore(task_queue, milestone)

    async def orchestrator_submit_task(task_request: TaskRequest):
        sub_task = VenomTask(content=task_request.content, status=TaskStatus.COMPLETED)
        state_manager.tasks[sub_task.id] = sub_task
        return TaskResponse(task_id=sub_task.id, status=sub_task.status)

    flow = CampaignFlow(
        state_manager=state_manager, orchestrator_submit_task=orchestrator_submit_task
    )

    result = await flow.execute(goal_store=goal_store, max_iterations=2)

    assert result["success"] is True
    assert result["tasks_completed"] == 1
    assert milestone.progress == 100


@pytest.mark.asyncio
async def test_campaign_flow_finishes_when_no_tasks():
    state_manager = FakeStateManager()
    goal_store = FakeGoalStore(tasks=[], milestone=None)

    async def orchestrator_submit_task(_task_request: TaskRequest):
        return TaskResponse(task_id=uuid4(), status=TaskStatus.COMPLETED)

    flow = CampaignFlow(
        state_manager=state_manager, orchestrator_submit_task=orchestrator_submit_task
    )

    result = await flow.execute(goal_store=goal_store, max_iterations=1)

    assert result["success"] is True
