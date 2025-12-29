from unittest.mock import MagicMock

import pytest

from venom_core.agents.executive import ExecutiveAgent
from venom_core.core.goal_store import GoalStore, GoalType


@pytest.mark.asyncio
async def test_parse_and_create_roadmap_creates_goals(tmp_path):
    store = GoalStore(storage_path=str(tmp_path / "roadmap.json"))
    agent = ExecutiveAgent(kernel=MagicMock(), goal_store=store)

    llm_response = "\n".join(
        [
            "VISION: Nowy produkt",
            "Opis: Cel strategiczny",
            "KPI: adopcja - target: 100%",
            "MILESTONE 1: MVP",
            "Priorytet: 1",
            "Opis: Dostarczyć MVP",
            "TASK 1: Implementacja API",
            "Priorytet: 1",
            "Opis: Endpointy v1",
        ]
    )

    result = await agent._parse_and_create_roadmap(llm_response, "Wizja produktu")

    assert result["success"] is True
    assert result["milestones_count"] == 1
    assert result["tasks_count"] == 1
    goals = list(store.goals.values())
    assert any(goal.type == GoalType.VISION for goal in goals)
    assert any(goal.type == GoalType.MILESTONE for goal in goals)
    assert any(goal.type == GoalType.TASK for goal in goals)
