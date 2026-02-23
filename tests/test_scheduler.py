"""Testy dla modułu scheduler (BackgroundScheduler)."""

from unittest.mock import AsyncMock

import pytest

from venom_core.core.scheduler import BackgroundScheduler


@pytest.fixture
def scheduler():
    """Fixture dla BackgroundScheduler."""
    return BackgroundScheduler()


def test_scheduler_initialization(scheduler):
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


def test_get_status(scheduler):
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


@pytest.mark.asyncio
async def test_scheduler_start_when_already_running(scheduler):
    """Test uruchomienia gdy scheduler już działa."""
    await scheduler.start()
    assert scheduler.is_running

    # Próba ponownego uruchomienia
    await scheduler.start()
    # Powinien nadal działać bez błędu
    assert scheduler.is_running

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_when_not_running(scheduler):
    """Test zatrzymania gdy scheduler nie działa."""
    assert not scheduler.is_running

    # Próba zatrzymania nie działającego schedulera
    await scheduler.stop()
    # Nie powinien wywołać błędu
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_add_interval_job_without_time_params():
    """Test dodawania zadania bez parametrów czasu."""
    scheduler = BackgroundScheduler()
    await scheduler.start()

    mock_func = AsyncMock()

    # Próba dodania zadania bez minutes ani seconds
    with pytest.raises(ValueError, match="minutes lub seconds"):
        scheduler.add_interval_job(func=mock_func, job_id="invalid_job")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_remove_nonexistent_job(scheduler):
    """Test usuwania nieistniejącego zadania."""
    await scheduler.start()

    # Próba usunięcia zadania które nie istnieje
    removed = scheduler.remove_job("nonexistent_job")
    assert removed is False

    await scheduler.stop()


@pytest.mark.asyncio
async def test_get_job_status_nonexistent(scheduler):
    """Test pobierania statusu nieistniejącego zadania."""
    await scheduler.start()

    # Próba pobrania statusu nieistniejącego zadania
    status = scheduler.get_job_status("nonexistent_job")
    assert status is None

    await scheduler.stop()


def test_get_status_without_starting(scheduler):
    """Test pobierania statusu bez uruchomienia schedulera."""
    status = scheduler.get_status()

    assert isinstance(status, dict)
    assert "is_running" in status
    assert status["is_running"] is False


def test_get_jobs_empty(scheduler):
    """Test pobierania listy zadań gdy jest pusta."""
    jobs = scheduler.get_jobs()

    assert isinstance(jobs, list)
    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_add_interval_job_with_minutes(scheduler):
    """Test dodawania zadania z parametrem minutes."""
    await scheduler.start()

    mock_func = AsyncMock()
    job_id = scheduler.add_interval_job(
        func=mock_func, minutes=5, job_id="minute_job", description="Minute test"
    )

    assert job_id == "minute_job"

    # Sprawdź czy zadanie jest w rejestrze
    jobs = scheduler.get_jobs()
    assert any(job["id"] == "minute_job" for job in jobs)

    scheduler.remove_job(job_id)
    await scheduler.stop()


@pytest.mark.asyncio
async def test_add_interval_job_replace_existing(scheduler):
    """Test zastępowania istniejącego zadania."""
    await scheduler.start()

    mock_func1 = AsyncMock()
    mock_func2 = AsyncMock()

    # Dodaj pierwsze zadanie
    job_id = scheduler.add_interval_job(
        func=mock_func1, seconds=10, job_id="replaceable_job"
    )

    # Dodaj zadanie o tym samym ID (powinno zastąpić)
    job_id2 = scheduler.add_interval_job(
        func=mock_func2, seconds=15, job_id="replaceable_job"
    )

    assert job_id == job_id2

    # Powinno być tylko jedno zadanie o tym ID
    jobs = scheduler.get_jobs()
    matching_jobs = [job for job in jobs if job["id"] == "replaceable_job"]
    assert len(matching_jobs) == 1

    scheduler.remove_job(job_id)
    await scheduler.stop()
