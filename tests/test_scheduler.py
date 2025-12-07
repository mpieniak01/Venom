"""Testy dla modułu scheduler (BackgroundScheduler)."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from venom_core.core.scheduler import BackgroundScheduler


@pytest.fixture
def scheduler():
    """Fixture dla BackgroundScheduler."""
    return BackgroundScheduler()


@pytest.mark.asyncio
async def test_scheduler_initialization(scheduler):
    """Test inicjalizacji schedulera."""
    assert scheduler is not None
    assert not scheduler.is_running
    assert scheduler.scheduler is not None


@pytest.mark.asyncio
async def test_scheduler_start_stop(scheduler):
    """Test uruchamiania i zatrzymywania schedulera."""
    await scheduler.start()
    assert scheduler.is_running

    await scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_add_interval_job(scheduler):
    """Test dodawania zadania interwałowego."""
    await scheduler.start()

    # Mock function
    mock_func = AsyncMock()

    # Dodaj zadanie co 1 sekundę
    job_id = scheduler.add_interval_job(
        func=mock_func, seconds=1, job_id="test_job", description="Test job"
    )

    assert job_id == "test_job"

    # Sprawdź czy zadanie jest w rejestrze
    jobs = scheduler.get_jobs()
    assert len(jobs) > 0
    assert any(job["id"] == "test_job" for job in jobs)

    # Usuń zadanie
    removed = scheduler.remove_job("test_job")
    assert removed

    await scheduler.stop()


@pytest.mark.asyncio
async def test_get_status(scheduler):
    """Test pobierania statusu schedulera."""
    status = scheduler.get_status()

    assert "is_running" in status
    assert "paused" in status
    assert "jobs_count" in status
    assert "state" in status


@pytest.mark.asyncio
async def test_pause_resume_jobs(scheduler):
    """Test wstrzymywania i wznawiania zadań."""
    await scheduler.start()

    # Dodaj zadanie
    mock_func = AsyncMock()
    scheduler.add_interval_job(
        func=mock_func, seconds=10, job_id="pausable_job", description="Pausable job"
    )

    # Wstrzymaj
    await scheduler.pause_all_jobs()

    # Wznów
    await scheduler.resume_all_jobs()

    # Usuń zadanie
    scheduler.remove_job("pausable_job")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_get_job_status(scheduler):
    """Test pobierania statusu konkretnego zadania."""
    await scheduler.start()

    # Dodaj zadanie
    mock_func = AsyncMock()
    job_id = scheduler.add_interval_job(
        func=mock_func, seconds=10, job_id="status_test_job", description="Status test"
    )

    # Pobierz status
    job_status = scheduler.get_job_status(job_id)
    assert job_status is not None
    assert job_status["id"] == job_id

    # Usuń zadanie
    scheduler.remove_job(job_id)

    await scheduler.stop()


@pytest.mark.asyncio
async def test_add_cron_job(scheduler):
    """Test dodawania zadania cron."""
    await scheduler.start()

    # Mock function
    mock_func = AsyncMock()

    # Dodaj zadanie cron (co minutę)
    job_id = scheduler.add_cron_job(
        func=mock_func,
        cron_expression="* * * * *",
        job_id="cron_test",
        description="Cron test",
    )

    assert job_id == "cron_test"

    # Sprawdź czy zadanie jest w rejestrze
    jobs = scheduler.get_jobs()
    assert any(job["id"] == "cron_test" for job in jobs)

    # Usuń zadanie
    removed = scheduler.remove_job("cron_test")
    assert removed

    await scheduler.stop()
