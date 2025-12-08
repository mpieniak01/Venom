"""Testy jednostkowe dla GoalStore (Executive Layer)."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.goal_store import (
    Goal,
    GoalStatus,
    GoalStore,
    GoalType,
    KPI,
)


@pytest.fixture
def temp_storage():
    """Fixture dla tymczasowego pliku storage."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


def test_goal_store_initialization(temp_storage):
    """Test inicjalizacji GoalStore."""
    store = GoalStore(storage_path=temp_storage)
    assert store.goals == {}
    assert store.storage_path.exists() or not Path(temp_storage).exists()


def test_add_vision(temp_storage):
    """Test dodawania wizji."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Stworzyć najlepszy framework AI",
        goal_type=GoalType.VISION,
        description="Długoterminowy cel projektu",
        priority=1,
    )

    assert vision.title == "Stworzyć najlepszy framework AI"
    assert vision.type == GoalType.VISION
    assert vision.status == GoalStatus.PENDING
    assert vision.goal_id in store.goals


def test_add_milestone_with_parent(temp_storage):
    """Test dodawania milestone z rodzicem."""
    store = GoalStore(storage_path=temp_storage)

    # Dodaj vision
    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    # Dodaj milestone
    milestone = store.add_goal(
        title="Milestone 1",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=1,
    )

    assert milestone.type == GoalType.MILESTONE
    assert milestone.parent_id == vision.goal_id


def test_add_task_with_kpi(temp_storage):
    """Test dodawania zadania z KPI."""
    store = GoalStore(storage_path=temp_storage)

    kpi = KPI(name="Pokrycie testami", target_value=90.0, unit="%")

    task = store.add_goal(
        title="Napisać testy",
        goal_type=GoalType.TASK,
        priority=2,
        kpis=[kpi],
    )

    assert len(task.kpis) == 1
    assert task.kpis[0].name == "Pokrycie testami"
    assert task.kpis[0].target_value == 90.0


def test_update_progress(temp_storage):
    """Test aktualizacji postępu."""
    store = GoalStore(storage_path=temp_storage)

    task = store.add_goal(
        title="Zadanie", goal_type=GoalType.TASK, priority=1
    )

    # Aktualizuj status
    updated = store.update_progress(task.goal_id, status=GoalStatus.IN_PROGRESS)

    assert updated is not None
    assert updated.status == GoalStatus.IN_PROGRESS


def test_update_progress_with_kpi(temp_storage):
    """Test aktualizacji KPI."""
    store = GoalStore(storage_path=temp_storage)

    kpi = KPI(name="Test", target_value=100.0)
    task = store.add_goal(
        title="Zadanie", goal_type=GoalType.TASK, priority=1, kpis=[kpi]
    )

    # Aktualizuj KPI
    updated = store.update_progress(
        task.goal_id, kpi_updates={"Test": 50.0}
    )

    assert updated.kpis[0].current_value == 50.0
    assert updated.get_progress() == 50.0


def test_get_vision(temp_storage):
    """Test pobierania wizji."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    retrieved = store.get_vision()

    assert retrieved is not None
    assert retrieved.goal_id == vision.goal_id


def test_get_milestones(temp_storage):
    """Test pobierania kamieni milowych."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    # Dodaj 3 milestone
    m1 = store.add_goal(
        title="M1",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=1,
    )
    m2 = store.add_goal(
        title="M2",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=2,
    )
    m3 = store.add_goal(
        title="M3",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=3,
    )

    milestones = store.get_milestones()

    assert len(milestones) == 3
    # Powinny być posortowane po priorytecie
    assert milestones[0].title == "M1"
    assert milestones[1].title == "M2"
    assert milestones[2].title == "M3"


def test_get_next_milestone(temp_storage):
    """Test pobierania kolejnego milestone."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    # Dodaj milestone z różnymi statusami
    m1 = store.add_goal(
        title="M1",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=1,
    )
    store.update_progress(m1.goal_id, status=GoalStatus.COMPLETED)

    m2 = store.add_goal(
        title="M2",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=2,
    )

    next_milestone = store.get_next_milestone()

    assert next_milestone is not None
    assert next_milestone.title == "M2"


def test_get_next_task(temp_storage):
    """Test pobierania kolejnego zadania."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    milestone = store.add_goal(
        title="M1",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=1,
    )

    # Dodaj zadania
    t1 = store.add_goal(
        title="T1",
        goal_type=GoalType.TASK,
        parent_id=milestone.goal_id,
        priority=1,
    )

    t2 = store.add_goal(
        title="T2",
        goal_type=GoalType.TASK,
        parent_id=milestone.goal_id,
        priority=2,
    )

    next_task = store.get_next_task()

    assert next_task is not None
    assert next_task.title == "T1"


def test_generate_roadmap_report(temp_storage):
    """Test generowania raportu roadmapy."""
    store = GoalStore(storage_path=temp_storage)

    vision = store.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    milestone = store.add_goal(
        title="Milestone 1",
        goal_type=GoalType.MILESTONE,
        parent_id=vision.goal_id,
        priority=1,
    )

    report = store.generate_roadmap_report()

    assert "ROADMAP PROJEKTU" in report
    assert "Vision" in report
    assert "Milestone 1" in report


def test_persistence(temp_storage):
    """Test zapisu i odczytu z dysku."""
    # Utwórz store i dodaj cele
    store1 = GoalStore(storage_path=temp_storage)
    vision = store1.add_goal(
        title="Vision", goal_type=GoalType.VISION, priority=1
    )

    # Utwórz nową instancję - powinna załadować dane
    store2 = GoalStore(storage_path=temp_storage)

    assert len(store2.goals) == 1
    retrieved = store2.get_vision()
    assert retrieved is not None
    assert retrieved.title == "Vision"


def test_kpi_progress():
    """Test obliczania postępu KPI."""
    kpi = KPI(name="Test", target_value=100.0, current_value=50.0)

    assert kpi.get_progress_percentage() == 50.0

    kpi.current_value = 100.0
    assert kpi.get_progress_percentage() == 100.0

    kpi.current_value = 150.0
    assert kpi.get_progress_percentage() == 100.0  # Max 100%


def test_goal_progress_with_status():
    """Test postępu celu na podstawie statusu (bez KPI)."""
    goal = Goal(
        type=GoalType.TASK,
        title="Task",
        status=GoalStatus.PENDING,
        priority=1,
    )

    assert goal.get_progress() == 0.0

    goal.status = GoalStatus.IN_PROGRESS
    assert goal.get_progress() == 50.0

    goal.status = GoalStatus.COMPLETED
    assert goal.get_progress() == 100.0


def test_goal_progress_with_kpis():
    """Test postępu celu na podstawie KPI."""
    kpi1 = KPI(name="KPI1", target_value=100.0, current_value=50.0)
    kpi2 = KPI(name="KPI2", target_value=100.0, current_value=100.0)

    goal = Goal(
        type=GoalType.MILESTONE,
        title="Milestone",
        priority=1,
        kpis=[kpi1, kpi2],
    )

    # Średnia z 50% i 100% = 75%
    assert goal.get_progress() == 75.0
