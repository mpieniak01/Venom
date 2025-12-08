"""Testy dla WorkLedger."""

import json
from pathlib import Path

import pytest

from venom_core.ops.work_ledger import TaskComplexity, TaskRecord, TaskStatus, WorkLedger


class TestWorkLedger:
    """Testy dla klasy WorkLedger."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Tymczasowy plik storage."""
        return str(tmp_path / "test_work_ledger.json")

    @pytest.fixture
    def ledger(self, temp_storage):
        """Instancja WorkLedger z tymczasowym storage."""
        return WorkLedger(storage_path=temp_storage)

    def test_initialization(self, ledger):
        """Test inicjalizacji Work Ledger."""
        assert ledger is not None
        assert len(ledger.tasks) == 0

    def test_log_task(self, ledger):
        """Test logowania zadania."""
        task = ledger.log_task(
            task_id="test_001",
            name="Test Task",
            description="Test description",
            estimated_minutes=30,
            complexity=TaskComplexity.LOW,
        )

        assert task.task_id == "test_001"
        assert task.name == "Test Task"
        assert task.estimated_minutes == 30
        assert task.complexity == TaskComplexity.LOW
        assert task.status == TaskStatus.PLANNED
        assert "test_001" in ledger.tasks

    def test_start_task(self, ledger):
        """Test rozpoczęcia zadania."""
        ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)
        success = ledger.start_task("test_001")

        assert success is True
        task = ledger.get_task("test_001")
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None

    def test_update_progress(self, ledger):
        """Test aktualizacji postępu."""
        ledger.log_task("test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_001")

        success = ledger.update_progress(
            "test_001", percent=50, actual_minutes=30, files_touched=5, tokens=1000
        )

        assert success is True
        task = ledger.get_task("test_001")
        assert task.progress_percent == 50
        assert task.actual_minutes == 30
        assert task.files_touched == 5
        assert task.tokens_used == 1000

    def test_update_progress_overrun_detection(self, ledger):
        """Test wykrywania overrun przy aktualizacji postępu."""
        ledger.log_task("test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_001")

        # Spędzono 100 minut na 60-minutowym zadaniu
        ledger.update_progress("test_001", percent=50, actual_minutes=100)

        task = ledger.get_task("test_001")
        assert task.status == TaskStatus.OVERRUN

    def test_complete_task(self, ledger):
        """Test ukończenia zadania."""
        ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)
        ledger.start_task("test_001")

        success = ledger.complete_task("test_001", actual_minutes=28)

        assert success is True
        task = ledger.get_task("test_001")
        assert task.status == TaskStatus.COMPLETED
        assert task.progress_percent == 100.0
        assert task.actual_minutes == 28
        assert task.completed_at is not None

    def test_add_risk(self, ledger):
        """Test dodawania ryzyka."""
        ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)
        success = ledger.add_risk("test_001", "Zewnętrzne API może nie działać")

        assert success is True
        task = ledger.get_task("test_001")
        assert len(task.risks) == 1
        assert "Zewnętrzne API" in task.risks[0]

    def test_predict_overrun_no_data(self, ledger):
        """Test prognozy overrun bez danych."""
        ledger.log_task("test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM)

        prediction = ledger.predict_overrun("test_001")

        assert "will_overrun" in prediction
        assert prediction["will_overrun"] is False

    def test_predict_overrun_on_track(self, ledger):
        """Test prognozy overrun - zadanie na dobrej drodze."""
        ledger.log_task("test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_001")
        ledger.update_progress("test_001", percent=50, actual_minutes=30)

        prediction = ledger.predict_overrun("test_001")

        assert prediction["will_overrun"] is False
        assert prediction["projected_total_minutes"] == 60

    def test_predict_overrun_delayed(self, ledger):
        """Test prognozy overrun - zadanie opóźnione."""
        ledger.log_task("test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_001")
        # 50% postępu po 50 minutach = prognoza 100 minut całkowitych
        ledger.update_progress("test_001", percent=50, actual_minutes=50)

        prediction = ledger.predict_overrun("test_001")

        assert prediction["will_overrun"] is True
        assert prediction["projected_total_minutes"] == 100
        assert prediction["overrun_percent"] > 0

    def test_list_tasks_no_filter(self, ledger):
        """Test listowania zadań bez filtra."""
        ledger.log_task("test_001", "Task 1", "Desc", 30, TaskComplexity.LOW)
        ledger.log_task("test_002", "Task 2", "Desc", 60, TaskComplexity.MEDIUM)

        tasks = ledger.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_filter_by_status(self, ledger):
        """Test listowania zadań z filtrem po statusie."""
        ledger.log_task("test_001", "Task 1", "Desc", 30, TaskComplexity.LOW)
        ledger.log_task("test_002", "Task 2", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_001")

        in_progress = ledger.list_tasks(status=TaskStatus.IN_PROGRESS)
        assert len(in_progress) == 1
        assert in_progress[0].task_id == "test_001"

    def test_summaries_empty(self, ledger):
        """Test podsumowania przy pustym ledgerze."""
        summary = ledger.summaries()
        assert summary["total_tasks"] == 0

    def test_summaries_with_tasks(self, ledger):
        """Test podsumowania z zadaniami."""
        ledger.log_task("test_001", "Task 1", "Desc", 30, TaskComplexity.LOW)
        ledger.start_task("test_001")
        ledger.complete_task("test_001", actual_minutes=28)

        ledger.log_task("test_002", "Task 2", "Desc", 60, TaskComplexity.MEDIUM)
        ledger.start_task("test_002")

        summary = ledger.summaries()

        assert summary["total_tasks"] == 2
        assert summary["completed"] == 1
        assert summary["in_progress"] == 1
        assert summary["total_estimated_minutes"] == 90

    def test_record_api_usage(self, ledger):
        """Test zapisywania użycia API."""
        ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)

        success = ledger.record_api_usage("test_001", "openai", tokens=500, ops=1)

        assert success is True
        task = ledger.get_task("test_001")
        assert task.api_calls_made == 1
        assert task.tokens_used == 500
        assert "api_usage" in task.metadata
        assert "openai" in task.metadata["api_usage"]

    def test_persistence(self, temp_storage):
        """Test zachowania danych między sesjami."""
        # Sesja 1: Dodaj zadanie
        ledger1 = WorkLedger(storage_path=temp_storage)
        ledger1.log_task("test_001", "Persistent Task", "Desc", 30, TaskComplexity.LOW)

        # Sesja 2: Wczytaj z pliku
        ledger2 = WorkLedger(storage_path=temp_storage)
        task = ledger2.get_task("test_001")

        assert task is not None
        assert task.name == "Persistent Task"


class TestTaskRecord:
    """Testy dla klasy TaskRecord."""

    def test_to_dict(self):
        """Test konwersji do słownika."""
        record = TaskRecord(
            task_id="test_001",
            name="Test",
            description="Desc",
            estimated_minutes=30,
            complexity=TaskComplexity.LOW,
        )

        data = record.to_dict()

        assert data["task_id"] == "test_001"
        assert data["complexity"] == "LOW"
        assert data["status"] == "PLANNED"

    def test_from_dict(self):
        """Test utworzenia z słownika."""
        data = {
            "task_id": "test_001",
            "name": "Test",
            "description": "Desc",
            "estimated_minutes": 30,
            "complexity": "LOW",
            "status": "PLANNED",
            "created_at": "2024-01-01T00:00:00",
        }

        record = TaskRecord.from_dict(data)

        assert record.task_id == "test_001"
        assert record.complexity == TaskComplexity.LOW
        assert record.status == TaskStatus.PLANNED
