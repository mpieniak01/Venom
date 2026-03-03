"""Testy jednostkowe dla CodingBenchmarkService."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from venom_core.services.benchmark_coding import (
    CodingBenchmarkService,
    _is_valid_run_id,
    _parse_scheduler_state,
    _safe_float,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path):
    """Fixture: CodingBenchmarkService z tymczasowym katalogiem."""
    return CodingBenchmarkService(storage_dir=str(tmp_path / "coding_benchmarks"))


@pytest.fixture
def scheduler_state_file(tmp_path):
    """Fixture: przykładowy scheduler_state.json."""
    state = {
        "meta": {"models": ["llama3:latest"], "tasks": ["python_sanity"]},
        "jobs": [
            {
                "id": "job-0001",
                "model": "llama3:latest",
                "mode": "single",
                "task": "python_sanity",
                "role": "main",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00+00:00",
                "started_at": "2024-01-01T00:00:01+00:00",
                "finished_at": "2024-01-01T00:01:00+00:00",
                "rc": 0,
                "artifact": None,
                "output": None,
            },
            {
                "id": "job-0002",
                "model": "llama3:latest",
                "mode": "loop",
                "task": "python_complex_bugfix",
                "role": "main",
                "status": "failed",
                "created_at": "2024-01-01T00:01:00+00:00",
                "started_at": "2024-01-01T00:01:01+00:00",
                "finished_at": "2024-01-01T00:02:30+00:00",
                "rc": 2,
                "artifact": None,
                "output": None,
            },
        ],
    }
    path = tmp_path / "scheduler_state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Testy pomocnicze
# ---------------------------------------------------------------------------


def test_is_valid_run_id_valid():
    """Test walidacji poprawnego UUID run_id."""
    import uuid

    valid_id = str(uuid.uuid4())
    assert _is_valid_run_id(valid_id) is True


def test_is_valid_run_id_invalid():
    """Test walidacji niepoprawnego run_id."""
    assert _is_valid_run_id("../../etc/passwd") is False
    assert _is_valid_run_id("not-a-uuid") is False
    assert _is_valid_run_id("") is False


def test_safe_float():
    """Test konwersji wartości na float."""
    assert _safe_float(1.5) == pytest.approx(1.5)
    assert _safe_float(3) == pytest.approx(3.0)
    assert _safe_float(None) is None
    assert _safe_float("bad") is None


def test_parse_scheduler_state(scheduler_state_file):
    """Test parsowania pliku scheduler_state.json."""
    jobs = _parse_scheduler_state(scheduler_state_file)
    assert len(jobs) == 2
    assert jobs[0].id == "job-0001"
    assert jobs[0].status == "completed"
    assert jobs[0].rc == 0
    assert jobs[1].id == "job-0002"
    assert jobs[1].status == "failed"


def test_parse_scheduler_state_missing_file(tmp_path):
    """Test parsowania brakującego pliku - zwraca pustą listę."""
    jobs = _parse_scheduler_state(tmp_path / "nonexistent.json")
    assert jobs == []


# ---------------------------------------------------------------------------
# Testy CodingBenchmarkService
# ---------------------------------------------------------------------------


def test_service_initialization(service):
    """Test inicjalizacji serwisu."""
    assert service is not None
    assert service.storage_dir.exists()
    assert service._runs == {}


def test_start_run_creates_entry(service):
    """Test uruchomienia benchmarku - tworzy wpis w _runs."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(
            models=["llama3:latest"],
            tasks=["python_sanity"],
        )
    assert run_id in service._runs
    run = service._runs[run_id]
    assert run.config.models == ["llama3:latest"]
    assert run.config.tasks == ["python_sanity"]
    assert run.status == "pending"


def test_start_run_persists_meta(service):
    """Test uruchomienia - metadane są zapisywane na dysk."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(
            models=["llama3:latest"],
            tasks=["python_sanity"],
        )
    meta_file = service._meta_file(run_id)
    assert meta_file.exists()
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id


def test_start_run_empty_models_raises(service):
    """Test walidacji: pusta lista modeli."""
    with pytest.raises(ValueError, match="Lista modeli nie może być pusta"):
        service.start_run(models=[], tasks=["python_sanity"])


def test_start_run_invalid_task_raises(service):
    """Test walidacji: nieznane zadanie."""
    with pytest.raises(ValueError, match="Nieznane zadania"):
        service.start_run(models=["llama3:latest"], tasks=["invalid_task"])


def test_get_run_status_returns_dict(service):
    """Test pobierania statusu istniejącego run."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(
            models=["llama3:latest"],
            tasks=["python_sanity"],
        )
    status = service.get_run_status(run_id)
    assert status is not None
    assert status["run_id"] == run_id
    assert "config" in status
    assert "summary" in status


def test_get_run_status_not_found(service):
    """Test pobierania statusu nieistniejącego run."""
    import uuid

    result = service.get_run_status(str(uuid.uuid4()))
    assert result is None


def test_get_run_status_invalid_id(service):
    """Test pobierania statusu z path traversal ID."""
    result = service.get_run_status("../../etc/passwd")
    assert result is None


def test_list_runs(service):
    """Test listowania run."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id1 = service.start_run(models=["m1"], tasks=["python_sanity"])
        run_id2 = service.start_run(models=["m2"], tasks=["python_simple"])
    runs = service.list_runs(limit=10)
    assert len(runs) == 2
    ids = [r["run_id"] for r in runs]
    assert run_id1 in ids
    assert run_id2 in ids


def test_list_runs_limit(service):
    """Test limitu na liście run."""
    with patch.object(service, "_run_scheduler_thread"):
        for _ in range(5):
            service.start_run(models=["m1"], tasks=["python_sanity"])
    runs = service.list_runs(limit=3)
    assert len(runs) == 3


def test_delete_run(service):
    """Test usuwania run."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(models=["m1"], tasks=["python_sanity"])
    assert service.delete_run(run_id) is True
    assert service.get_run_status(run_id) is None


def test_delete_run_not_found(service):
    """Test usuwania nieistniejącego run."""
    import uuid

    assert service.delete_run(str(uuid.uuid4())) is False


def test_delete_run_invalid_id(service):
    """Test usuwania z path traversal ID - odrzucone."""
    assert service.delete_run("../../etc/passwd") is False


def test_clear_all_runs(service):
    """Test czyszczenia wszystkich run."""
    with patch.object(service, "_run_scheduler_thread"):
        service.start_run(models=["m1"], tasks=["python_sanity"])
        service.start_run(models=["m2"], tasks=["python_sanity"])
    count = service.clear_all_runs()
    assert count == 2
    assert service.list_runs() == []


def test_to_summary_dict(service):
    """Test generowania podsumowania run."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(models=["m1"], tasks=["python_sanity"])
    status = service.get_run_status(run_id)
    summary = status["summary"]
    assert "total_jobs" in summary
    assert "completed" in summary
    assert "failed" in summary
    assert "success_rate" in summary


def test_build_scheduler_command(service):
    """Test budowania komendy schedulera."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(
            models=["llama3:latest"],
            tasks=["python_sanity", "python_simple"],
            loop_task="python_complex_bugfix",
            timeout=120,
            stop_on_failure=True,
        )
    run = service._runs[run_id]
    cmd = service._build_scheduler_command(run)
    assert "--models" in cmd
    assert "llama3:latest" in cmd
    assert "--tasks" in cmd
    assert "python_sanity,python_simple" in cmd
    assert "--stop-on-failure" in cmd
    assert "--timeout" in cmd
    assert "120" in cmd


def test_scheduler_thread_success(service, tmp_path):
    """Test wątku schedulera - sukces."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(models=["m1"], tasks=["python_sanity"])

    # Zasymuluj sukces schedulera
    run = service._runs[run_id]
    run.status = "running"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        service._run_scheduler_thread(run_id)

    assert run.status == "completed"
    assert run.finished_at is not None


def test_scheduler_thread_failure(service):
    """Test wątku schedulera - niepowodzenie."""
    with patch.object(service, "_run_scheduler_thread"):
        run_id = service.start_run(models=["m1"], tasks=["python_sanity"])

    run = service._runs[run_id]

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Error message"

    with patch("subprocess.run", return_value=mock_proc):
        service._run_scheduler_thread(run_id)

    assert run.status == "failed"
    assert run.error_message is not None


def test_load_persisted_runs(tmp_path):
    """Test wczytywania run z dysku przy starcie serwisu."""
    storage = tmp_path / "storage"
    # Najpierw stwórz run i zapisz metadane
    svc = CodingBenchmarkService(storage_dir=str(storage))
    with patch.object(svc, "_run_scheduler_thread"):
        run_id = svc.start_run(models=["m1"], tasks=["python_sanity"])
    # Oznacz jako completed
    svc._runs[run_id].status = "completed"
    svc._persist_meta(svc._runs[run_id])

    # Stwórz nowy serwis - powinien załadować z dysku
    svc2 = CodingBenchmarkService(storage_dir=str(storage))
    assert run_id in svc2._runs
    assert svc2._runs[run_id].status == "completed"
