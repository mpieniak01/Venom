"""Moduł: work_ledger - system śledzenia zadań z metrykami operacyjnymi."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskComplexity(str, Enum):
    """Poziomy złożoności zadań."""

    TRIVIAL = "TRIVIAL"  # < 5 minut, 1 plik
    LOW = "LOW"  # 5-15 minut, 1-3 pliki
    MEDIUM = "MEDIUM"  # 15-60 minut, 3-10 plików
    HIGH = "HIGH"  # 1-4 godziny, 10-30 plików
    EPIC = "EPIC"  # > 4 godziny, >30 plików lub wymaga podziału


class TaskStatus(str, Enum):
    """Status zadania."""

    PLANNED = "PLANNED"  # Zaplanowane
    IN_PROGRESS = "IN_PROGRESS"  # W trakcie realizacji
    COMPLETED = "COMPLETED"  # Ukończone
    PAUSED = "PAUSED"  # Wstrzymane
    CANCELLED = "CANCELLED"  # Anulowane
    OVERRUN = "OVERRUN"  # Przekroczony czas/złożoność


@dataclass
class TaskRecord:
    """Rekord pojedynczego zadania w Work Ledger."""

    task_id: str
    name: str
    description: str
    estimated_minutes: float
    complexity: TaskComplexity
    status: TaskStatus = TaskStatus.PLANNED
    progress_percent: float = 0.0
    actual_minutes: float = 0.0
    files_touched: int = 0
    api_calls_made: int = 0
    tokens_used: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    risks: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    metadata: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Konwertuje rekord do słownika."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "estimated_minutes": self.estimated_minutes,
            "complexity": self.complexity.value,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "actual_minutes": self.actual_minutes,
            "files_touched": self.files_touched,
            "api_calls_made": self.api_calls_made,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "risks": self.risks,
            "subtasks": self.subtasks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        """Tworzy rekord ze słownika."""
        return cls(
            task_id=data["task_id"],
            name=data["name"],
            description=data["description"],
            estimated_minutes=data["estimated_minutes"],
            complexity=TaskComplexity(data["complexity"]),
            status=TaskStatus(data["status"]),
            progress_percent=data.get("progress_percent", 0.0),
            actual_minutes=data.get("actual_minutes", 0.0),
            files_touched=data.get("files_touched", 0),
            api_calls_made=data.get("api_calls_made", 0),
            tokens_used=data.get("tokens_used", 0),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            risks=data.get("risks", []),
            subtasks=data.get("subtasks", []),
            metadata=data.get("metadata", {}),
        )


class WorkLedger:
    """
    System śledzenia zadań z metrykami operacyjnymi.

    Work Ledger przechowuje informacje o zadaniach, ich złożoności,
    postępie i rzeczywistym czasie realizacji.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Inicjalizacja Work Ledger.

        Args:
            storage_path: Ścieżka do pliku z danymi (domyślnie workspace/work_ledger.json)
        """
        if storage_path is None:
            storage_path = "workspace/work_ledger.json"

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.tasks: Dict[str, TaskRecord] = {}
        self._load_tasks()
        logger.info(f"WorkLedger zainicjalizowany: {len(self.tasks)} zadań załadowanych")

    def log_task(
        self,
        task_id: str,
        name: str,
        description: str,
        estimated_minutes: float,
        complexity: TaskComplexity,
        metadata: Optional[Dict[str, any]] = None,
    ) -> TaskRecord:
        """
        Loguje nowe zadanie do Work Ledger.

        Args:
            task_id: Unikalny identyfikator zadania
            name: Nazwa zadania
            description: Opis zadania
            estimated_minutes: Szacowany czas w minutach
            complexity: Poziom złożoności
            metadata: Dodatkowe metadane

        Returns:
            Utworzony rekord zadania
        """
        if task_id in self.tasks:
            logger.warning(f"Zadanie {task_id} już istnieje - aktualizuję")
            task = self.tasks[task_id]
            task.name = name
            task.description = description
            task.estimated_minutes = estimated_minutes
            task.complexity = complexity
            if metadata:
                task.metadata.update(metadata)
        else:
            task = TaskRecord(
                task_id=task_id,
                name=name,
                description=description,
                estimated_minutes=estimated_minutes,
                complexity=complexity,
                metadata=metadata or {},
            )
            self.tasks[task_id] = task
            logger.info(f"Zadanie {task_id} zalogowane: {name} ({complexity.value}, {estimated_minutes}min)")

        self._save_tasks()
        return task

    def start_task(self, task_id: str) -> bool:
        """
        Oznacza zadanie jako rozpoczęte.

        Args:
            task_id: Identyfikator zadania

        Returns:
            True jeśli operacja się powiodła
        """
        if task_id not in self.tasks:
            logger.error(f"Zadanie {task_id} nie istnieje")
            return False

        task = self.tasks[task_id]
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(UTC).isoformat()
        self._save_tasks()
        logger.info(f"Zadanie {task_id} rozpoczęte")
        return True

    def update_progress(
        self,
        task_id: str,
        percent: float,
        actual_minutes: Optional[float] = None,
        files_touched: Optional[int] = None,
        api_calls: Optional[int] = None,
        tokens: Optional[int] = None,
    ) -> bool:
        """
        Aktualizuje postęp zadania.

        Args:
            task_id: Identyfikator zadania
            percent: Procent ukończenia (0-100)
            actual_minutes: Rzeczywisty czas spędzony
            files_touched: Liczba zmodyfikowanych plików
            api_calls: Liczba wywołań API
            tokens: Liczba użytych tokenów

        Returns:
            True jeśli operacja się powiodła
        """
        if task_id not in self.tasks:
            logger.error(f"Zadanie {task_id} nie istnieje")
            return False

        task = self.tasks[task_id]
        task.progress_percent = min(100.0, max(0.0, percent))

        if actual_minutes is not None:
            task.actual_minutes = actual_minutes

        if files_touched is not None:
            task.files_touched = files_touched

        if api_calls is not None:
            task.api_calls_made = api_calls

        if tokens is not None:
            task.tokens_used = tokens

        # Sprawdź czy zadanie jest w overrun
        if task.actual_minutes > task.estimated_minutes * 1.5:
            task.status = TaskStatus.OVERRUN
            logger.warning(
                f"Zadanie {task_id} przekroczyło estymację: "
                f"{task.actual_minutes:.1f}min vs {task.estimated_minutes:.1f}min"
            )

        self._save_tasks()
        return True

    def complete_task(self, task_id: str, actual_minutes: Optional[float] = None) -> bool:
        """
        Oznacza zadanie jako ukończone.

        Args:
            task_id: Identyfikator zadania
            actual_minutes: Rzeczywisty czas spędzony

        Returns:
            True jeśli operacja się powiodła
        """
        if task_id not in self.tasks:
            logger.error(f"Zadanie {task_id} nie istnieje")
            return False

        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.progress_percent = 100.0
        task.completed_at = datetime.now(UTC).isoformat()

        if actual_minutes is not None:
            task.actual_minutes = actual_minutes

        self._save_tasks()
        logger.info(
            f"Zadanie {task_id} ukończone: {task.actual_minutes:.1f}min "
            f"(estymacja: {task.estimated_minutes:.1f}min)"
        )
        return True

    def add_risk(self, task_id: str, risk_description: str) -> bool:
        """
        Dodaje ryzyko do zadania.

        Args:
            task_id: Identyfikator zadania
            risk_description: Opis ryzyka

        Returns:
            True jeśli operacja się powiodła
        """
        if task_id not in self.tasks:
            logger.error(f"Zadanie {task_id} nie istnieje")
            return False

        task = self.tasks[task_id]
        if risk_description not in task.risks:
            task.risks.append(risk_description)
            self._save_tasks()
            logger.warning(f"Ryzyko dodane do {task_id}: {risk_description}")

        return True

    def predict_overrun(self, task_id: str) -> Dict[str, any]:
        """
        Przewiduje czy zadanie przekroczy estymację.

        Args:
            task_id: Identyfikator zadania

        Returns:
            Słownik z prognozą przekroczenia
        """
        if task_id not in self.tasks:
            return {"error": f"Zadanie {task_id} nie istnieje"}

        task = self.tasks[task_id]

        # Jeśli zadanie nie jest w trakcie, nie ma co prognozować
        if task.status != TaskStatus.IN_PROGRESS:
            return {
                "task_id": task_id,
                "will_overrun": False,
                "reason": f"Zadanie w statusie {task.status.value}",
            }

        # Prognoza na podstawie postępu
        if task.progress_percent > 0:
            projected_total = (task.actual_minutes / task.progress_percent) * 100
            overrun_percent = ((projected_total - task.estimated_minutes) / task.estimated_minutes) * 100

            return {
                "task_id": task_id,
                "will_overrun": projected_total > task.estimated_minutes,
                "estimated_minutes": task.estimated_minutes,
                "actual_minutes": task.actual_minutes,
                "progress_percent": task.progress_percent,
                "projected_total_minutes": projected_total,
                "overrun_percent": overrun_percent,
                "recommendation": self._get_overrun_recommendation(overrun_percent),
            }

        return {
            "task_id": task_id,
            "will_overrun": False,
            "reason": "Brak wystarczających danych do prognozy",
        }

    def _get_overrun_recommendation(self, overrun_percent: float) -> str:
        """Zwraca rekomendację na podstawie przewidywanego overrun."""
        if overrun_percent < 10:
            return "Zadanie w normie - kontynuuj"
        elif overrun_percent < 30:
            return "Lekkie opóźnienie - rozważ optymalizację"
        elif overrun_percent < 50:
            return "Znaczące opóźnienie - rozważ podział zadania"
        else:
            return "KRYTYCZNE - wstrzymaj i przeplanuj zadanie"

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Zwraca rekord zadania."""
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        complexity: Optional[TaskComplexity] = None,
    ) -> List[TaskRecord]:
        """
        Zwraca listę zadań z opcjonalnym filtrowaniem.

        Args:
            status: Filtruj po statusie
            complexity: Filtruj po złożoności

        Returns:
            Lista rekordów zadań
        """
        tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        if complexity:
            tasks = [t for t in tasks if t.complexity == complexity]

        return tasks

    def summaries(self) -> Dict[str, any]:
        """
        Generuje podsumowanie stanu wszystkich zadań.

        Returns:
            Słownik z metrykami
        """
        total_tasks = len(self.tasks)
        if total_tasks == 0:
            return {"total_tasks": 0, "message": "Brak zadań w systemie"}

        completed = [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]
        in_progress = [t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS]
        overrun = [t for t in self.tasks.values() if t.status == TaskStatus.OVERRUN]

        # Statystyki czasowe
        total_estimated = sum(t.estimated_minutes for t in self.tasks.values())
        total_actual = sum(t.actual_minutes for t in self.tasks.values() if t.actual_minutes > 0)

        # Accuracy estymacji dla ukończonych zadań
        accuracy_data = []
        for task in completed:
            if task.actual_minutes > 0:
                accuracy = (task.estimated_minutes / task.actual_minutes) * 100
                accuracy_data.append(accuracy)

        avg_accuracy = sum(accuracy_data) / len(accuracy_data) if accuracy_data else 0

        # Breakdown po złożoności
        complexity_breakdown = {}
        for complexity in TaskComplexity:
            tasks = [t for t in self.tasks.values() if t.complexity == complexity]
            complexity_breakdown[complexity.value] = {
                "count": len(tasks),
                "completed": len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
                "avg_estimated_minutes": (
                    sum(t.estimated_minutes for t in tasks) / len(tasks) if tasks else 0
                ),
            }

        return {
            "total_tasks": total_tasks,
            "completed": len(completed),
            "in_progress": len(in_progress),
            "overrun": len(overrun),
            "total_estimated_minutes": total_estimated,
            "total_actual_minutes": total_actual,
            "estimation_accuracy_percent": avg_accuracy,
            "complexity_breakdown": complexity_breakdown,
            "total_files_touched": sum(t.files_touched for t in self.tasks.values()),
            "total_api_calls": sum(t.api_calls_made for t in self.tasks.values()),
            "total_tokens_used": sum(t.tokens_used for t in self.tasks.values()),
        }

    def record_api_usage(self, task_id: str, provider: str, tokens: int, ops: int = 1) -> bool:
        """
        Zapisuje wykorzystanie zewnętrznego API.

        Args:
            task_id: Identyfikator zadania
            provider: Nazwa providera API (np. "openai", "anthropic")
            tokens: Liczba użytych tokenów
            ops: Liczba operacji

        Returns:
            True jeśli operacja się powiodła
        """
        if task_id not in self.tasks:
            logger.error(f"Zadanie {task_id} nie istnieje")
            return False

        task = self.tasks[task_id]
        task.api_calls_made += ops
        task.tokens_used += tokens

        # Zapisz w metadata breakdown per provider
        if "api_usage" not in task.metadata:
            task.metadata["api_usage"] = {}

        if provider not in task.metadata["api_usage"]:
            task.metadata["api_usage"][provider] = {"calls": 0, "tokens": 0}

        task.metadata["api_usage"][provider]["calls"] += ops
        task.metadata["api_usage"][provider]["tokens"] += tokens

        self._save_tasks()
        logger.debug(f"API usage zapisane: {task_id} -> {provider}: {tokens} tokens, {ops} ops")
        return True

    def _load_tasks(self):
        """Wczytuje zadania z pliku."""
        if not self.storage_path.exists():
            logger.info("Brak pliku work_ledger - start z pustą bazą")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.tasks = {task_id: TaskRecord.from_dict(task_data) for task_id, task_data in data.items()}
            logger.info(f"Załadowano {len(self.tasks)} zadań z {self.storage_path}")
        except Exception as e:
            logger.error(f"Błąd wczytywania work_ledger: {e}")
            self.tasks = {}

    def _save_tasks(self):
        """Zapisuje zadania do pliku."""
        try:
            data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Błąd zapisywania work_ledger: {e}")
