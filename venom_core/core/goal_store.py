"""Moduł: goal_store - Magazyn celów i roadmapy projektu (Executive Layer)."""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GoalType(str, Enum):
    """Typ celu w hierarchii."""

    VISION = "VISION"  # Nadrzędny cel długoterminowy
    MILESTONE = "MILESTONE"  # Kamień milowy (etap)
    TASK = "TASK"  # Konkretne zadanie


class GoalStatus(str, Enum):
    """Status celu."""

    PENDING = "PENDING"  # Oczekuje na realizację
    IN_PROGRESS = "IN_PROGRESS"  # W trakcie realizacji
    COMPLETED = "COMPLETED"  # Ukończone
    BLOCKED = "BLOCKED"  # Zablokowane
    CANCELLED = "CANCELLED"  # Anulowane


class KPI(BaseModel):
    """Wskaźnik sukcesu (Key Performance Indicator)."""

    name: str = Field(description="Nazwa wskaźnika")
    target_value: float = Field(gt=0, description="Wartość docelowa (musi być > 0)")
    current_value: float = Field(default=0.0, ge=0, description="Wartość bieżąca")
    unit: str = Field(default="%", description="Jednostka miary")

    def get_progress_percentage(self) -> float:
        """Zwraca postęp w procentach."""
        if self.target_value == 0:
            return 0.0
        return min(100.0, (self.current_value / self.target_value) * 100.0)


class Goal(BaseModel):
    """Cel w hierarchii Vision -> Milestone -> Task."""

    goal_id: UUID = Field(default_factory=uuid4, description="Unikalny identyfikator")
    type: GoalType = Field(description="Typ celu")
    title: str = Field(description="Tytuł celu")
    description: str = Field(default="", description="Szczegółowy opis")
    status: GoalStatus = Field(default=GoalStatus.PENDING, description="Status")
    priority: int = Field(default=1, ge=1, le=5, description="Priorytet (1=najwyższy)")
    parent_id: Optional[UUID] = Field(
        default=None, description="ID rodzica w hierarchii"
    )
    kpis: List[KPI] = Field(default_factory=list, description="Wskaźniki sukcesu")
    task_id: Optional[UUID] = Field(
        default=None, description="ID zadania w Orchestratorze (dla TASK)"
    )
    github_issue: Optional[int] = Field(
        default=None, description="Numer Issue w GitHub"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(default=None)

    def get_progress(self) -> float:
        """
        Zwraca postęp celu w procentach.

        Returns:
            Wartość 0-100
        """
        if not self.kpis:
            # Brak KPI - użyj statusu
            if self.status == GoalStatus.COMPLETED:
                return 100.0
            elif self.status == GoalStatus.IN_PROGRESS:
                return 50.0
            return 0.0

        # Oblicz średni postęp z KPI
        total_progress = sum(kpi.get_progress_percentage() for kpi in self.kpis)
        return total_progress / len(self.kpis)


class GoalStore:
    """
    Magazyn celów i roadmapy projektu.

    Przechowuje hierarchię Vision -> Milestone -> Task oraz zarządza
    postępem realizacji celów.
    """

    def __init__(self, storage_path: str = "data/memory/roadmap.json"):
        """
        Inicjalizacja magazynu celów.

        Args:
            storage_path: Ścieżka do pliku JSON z roadmapą
        """
        self.storage_path = Path(storage_path)
        self.goals: dict[UUID, Goal] = {}
        self._ensure_storage_exists()
        self._load_from_disk()

        logger.info(f"GoalStore zainicjalizowany z {len(self.goals)} celami")

    def _ensure_storage_exists(self) -> None:
        """Tworzy katalog dla storage jeśli nie istnieje."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> None:
        """Ładuje cele z dysku."""
        if not self.storage_path.exists():
            logger.debug("Brak pliku roadmap, tworzę nowy magazyn")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for goal_data in data.get("goals", []):
                    goal = Goal(**goal_data)
                    self.goals[goal.goal_id] = goal
            logger.info(f"Załadowano {len(self.goals)} celów z {self.storage_path}")
        except Exception as e:
            logger.error(f"Błąd podczas ładowania roadmapy: {e}")

    def _save_to_disk(self) -> None:
        """Zapisuje cele na dysk."""
        try:
            data = {
                "goals": [goal.model_dump(mode="json") for goal in self.goals.values()],
                "last_updated": datetime.now().isoformat(),
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.debug(f"Zapisano {len(self.goals)} celów do {self.storage_path}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania roadmapy: {e}")

    def add_goal(
        self,
        title: str,
        goal_type: GoalType,
        description: str = "",
        priority: int = 1,
        parent_id: Optional[UUID] = None,
        kpis: Optional[List[KPI]] = None,
        github_issue: Optional[int] = None,
    ) -> Goal:
        """
        Dodaje nowy cel do magazynu.

        Args:
            title: Tytuł celu
            goal_type: Typ celu (VISION/MILESTONE/TASK)
            description: Opis celu
            priority: Priorytet (1=najwyższy, 5=najniższy)
            parent_id: ID celu nadrzędnego
            kpis: Lista wskaźników sukcesu
            github_issue: Numer Issue w GitHub

        Returns:
            Utworzony cel
        """
        goal = Goal(
            type=goal_type,
            title=title,
            description=description,
            priority=priority,
            parent_id=parent_id,
            kpis=kpis or [],
            github_issue=github_issue,
        )

        self.goals[goal.goal_id] = goal
        self._save_to_disk()

        logger.info(f"Dodano nowy cel: {goal.title} [{goal.type}]")
        return goal

    def update_progress(
        self,
        goal_id: UUID,
        status: Optional[GoalStatus] = None,
        kpi_updates: Optional[dict[str, float]] = None,
        task_id: Optional[UUID] = None,
    ) -> Optional[Goal]:
        """
        Aktualizuje postęp celu.

        Args:
            goal_id: ID celu
            status: Nowy status (opcjonalnie)
            kpi_updates: Dict {kpi_name: new_value} (opcjonalnie)
            task_id: ID zadania w Orchestratorze (opcjonalnie)

        Returns:
            Zaktualizowany cel lub None jeśli nie znaleziono
        """
        goal = self.goals.get(goal_id)
        if not goal:
            logger.warning(f"Nie znaleziono celu {goal_id}")
            return None

        if status:
            goal.status = status
            if status == GoalStatus.COMPLETED:
                goal.completed_at = datetime.now()

        if kpi_updates:
            for kpi in goal.kpis:
                if kpi.name in kpi_updates:
                    kpi.current_value = kpi_updates[kpi.name]

        if task_id is not None:
            goal.task_id = task_id

        goal.updated_at = datetime.now()
        self._save_to_disk()

        logger.info(f"Zaktualizowano postęp: {goal.title} -> {goal.status}")
        return goal

    def get_goal(self, goal_id: UUID) -> Optional[Goal]:
        """
        Pobiera cel po ID.

        Args:
            goal_id: ID celu

        Returns:
            Cel lub None
        """
        return self.goals.get(goal_id)

    def get_vision(self) -> Optional[Goal]:
        """
        Zwraca główną wizję projektu.

        Returns:
            Goal typu VISION lub None
        """
        visions = [g for g in self.goals.values() if g.type == GoalType.VISION]
        if not visions:
            return None
        # Zwróć pierwszą wizję (powinna być jedna)
        return visions[0]

    def get_milestones(
        self, parent_id: Optional[UUID] = None, status: Optional[GoalStatus] = None
    ) -> List[Goal]:
        """
        Zwraca kamienie milowe.

        Args:
            parent_id: Filtruj po rodzicu (opcjonalnie)
            status: Filtruj po statusie (opcjonalnie)

        Returns:
            Lista kamieni milowych
        """
        milestones = [g for g in self.goals.values() if g.type == GoalType.MILESTONE]

        if parent_id:
            milestones = [m for m in milestones if m.parent_id == parent_id]

        if status:
            milestones = [m for m in milestones if m.status == status]

        # Sortuj po priorytecie
        return sorted(milestones, key=lambda m: (m.priority, m.created_at))

    def get_tasks(
        self, parent_id: Optional[UUID] = None, status: Optional[GoalStatus] = None
    ) -> List[Goal]:
        """
        Zwraca zadania.

        Args:
            parent_id: Filtruj po rodzicu (opcjonalnie)
            status: Filtruj po statusie (opcjonalnie)

        Returns:
            Lista zadań
        """
        tasks = [g for g in self.goals.values() if g.type == GoalType.TASK]

        if parent_id:
            tasks = [t for t in tasks if t.parent_id == parent_id]

        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sortuj po priorytecie
        return sorted(tasks, key=lambda t: (t.priority, t.created_at))

    def get_next_milestone(self) -> Optional[Goal]:
        """
        Zwraca kolejny kamień milowy do realizacji (najwyższy priorytet, PENDING).

        Returns:
            Goal lub None
        """
        pending_milestones = self.get_milestones(status=GoalStatus.PENDING)
        if not pending_milestones:
            # Sprawdź też IN_PROGRESS
            in_progress = self.get_milestones(status=GoalStatus.IN_PROGRESS)
            return in_progress[0] if in_progress else None

        return pending_milestones[0]

    def get_next_task(self, milestone_id: Optional[UUID] = None) -> Optional[Goal]:
        """
        Zwraca kolejne zadanie do realizacji.

        Args:
            milestone_id: Filtruj po kamieni milowym (opcjonalnie)

        Returns:
            Goal lub None
        """
        # Jeśli podano milestone, szukaj w nim
        if milestone_id:
            pending_tasks = self.get_tasks(
                parent_id=milestone_id, status=GoalStatus.PENDING
            )
        else:
            # Znajdź w aktualnym milestone
            current_milestone = self.get_next_milestone()
            if not current_milestone:
                return None
            pending_tasks = self.get_tasks(
                parent_id=current_milestone.goal_id, status=GoalStatus.PENDING
            )

        return pending_tasks[0] if pending_tasks else None

    def generate_roadmap_report(self) -> str:
        """
        Generuje raport tekstowy z roadmapy projektu.

        Returns:
            Sformatowany raport
        """
        report = ["=== ROADMAP PROJEKTU ===\n"]

        # Vision
        vision = self.get_vision()
        if vision:
            progress = vision.get_progress()
            report.extend(
                [
                    f"🎯 VISION: {vision.title}",
                    f"   Status: {vision.status.value}",
                    f"   Postęp: {progress:.1f}%",
                    f"   {vision.description}\n",
                ]
            )
        else:
            report.append("⚠️ Brak zdefiniowanej wizji\n")

        # Milestones
        milestones = self.get_milestones()
        if milestones:
            report.append(f"\n📋 KAMIENIE MILOWE ({len(milestones)}):\n")
            for i, milestone in enumerate(milestones, 1):
                progress = milestone.get_progress()
                status_emoji = {
                    GoalStatus.PENDING: "⏸️",
                    GoalStatus.IN_PROGRESS: "🔄",
                    GoalStatus.COMPLETED: "✅",
                    GoalStatus.BLOCKED: "🚫",
                    GoalStatus.CANCELLED: "❌",
                }.get(milestone.status, "❓")

                report.append(
                    f"  {i}. {status_emoji} [{milestone.priority}] {milestone.title}"
                )
                report.append(
                    f"      Postęp: {progress:.1f}% | {milestone.status.value}"
                )

                # Zadania w milestone
                tasks = self.get_tasks(parent_id=milestone.goal_id)
                if tasks:
                    completed = len(
                        [t for t in tasks if t.status == GoalStatus.COMPLETED]
                    )
                    report.append(
                        f"      Zadania: {completed}/{len(tasks)} ukończonych"
                    )
                report.append("")
        else:
            report.append("\n⚠️ Brak zdefiniowanych kamieni milowych\n")

        # Summary
        all_milestones = self.get_milestones()
        completed_milestones = [
            m for m in all_milestones if m.status == GoalStatus.COMPLETED
        ]
        if all_milestones:
            completion_rate = (len(completed_milestones) / len(all_milestones)) * 100
            report.append(
                f"\n📊 PODSUMOWANIE: {len(completed_milestones)}/{len(all_milestones)} "
                f"kamieni milowych ukończonych ({completion_rate:.1f}%)"
            )

        return "\n".join(report)

    def clear_all(self) -> None:
        """Usuwa wszystkie cele (użyj ostrożnie)."""
        self.goals.clear()
        self._save_to_disk()
        logger.warning("Wyczyszczono wszystkie cele z GoalStore")
