"""Tests for the scheduler module (BackgroundScheduler)."""

from unittest.mock import AsyncMock

import pytest

from venom_core.core.scheduler import BackgroundScheduler


@pytest.fixture
def scheduler():
    """Fixture for BackgroundScheduler."""
    return BackgroundScheduler()


def test_scheduler_initialization(scheduler):
    """Test scheduler initialization."""
    assert scheduler is not None
    assert not scheduler.is_running
    assert scheduler.scheduler is not None


@pytest.mark.asyncio
async def test_scheduler_start_stop(scheduler):
    """Test starting and stopping the scheduler."""
    await scheduler.start()
    assert scheduler.is_running

    await scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_add_interval_job(scheduler):
    """Test adding an interval job."""
    await scheduler.start()

    # Mock function
    mock_func = AsyncMock()

    # Add a job every 1 second
    job_id = scheduler.add_interval_job(
        func=mock_func, seconds=1, job_id="test_job", description="Test job"
    )

    assert job_id == "test_job"

    # Check if the job is registered
    jobs = scheduler.get_jobs()
    assert len(jobs) > 0
    assert any(job["id"] == "test_job" for job in jobs)

    # Remove the job
    removed = scheduler.remove_job("test_job")
    assert removed

    await scheduler.stop()


def test_get_status(scheduler):
    """Test getting scheduler status."""
    status = scheduler.get_status()

    assert "is_running" in status
    assert "paused" in status
    assert "jobs_count" in status
    assert "state" in status


@pytest.mark.asyncio
async def test_pause_resume_jobs(scheduler):
    """Test pausing and resuming jobs."""
    await scheduler.start()

    # Add a job
    mock_func = AsyncMock()
    scheduler.add_interval_job(
        func=mock_func, seconds=10, job_id="pausable_job", description="Pausable job"
    )

    # Pause
    await scheduler.pause_all_jobs()

    # Resume
    await scheduler.resume_all_jobs()

    # Remove the job
    scheduler.remove_job("pausable_job")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_get_job_status(scheduler):
    """Test getting status of a specific job."""
    await scheduler.start()

    # Add a job
    mock_func = AsyncMock()
    job_id = scheduler.add_interval_job(
        func=mock_func, seconds=10, job_id="status_test_job", description="Status test"
    )

    # Get status
    job_status = scheduler.get_job_status(job_id)
    assert job_status is not None
    assert job_status["id"] == job_id

    # Remove the job
    scheduler.remove_job(job_id)

    await scheduler.stop()


@pytest.mark.asyncio
async def test_add_cron_job(scheduler):
    """Test adding a cron job."""
    await scheduler.start()

    # Mock function
    mock_func = AsyncMock()

    # Add a cron job (every minute)
    job_id = scheduler.add_cron_job(
        func=mock_func,
        cron_expression="* * * * *",
        job_id="cron_test",
        description="Cron test",
    )

    assert job_id == "cron_test"

    # Check if the job is registered
    jobs = scheduler.get_jobs()
    assert any(job["id"] == "cron_test" for job in jobs)

    # Remove the job
    removed = scheduler.remove_job("cron_test")
    assert removed

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_start_when_already_running(scheduler):
    """Test starting when scheduler is already running."""
    await scheduler.start()
    assert scheduler.is_running

    # Attempt to start again
    await scheduler.start()
    # Should continue running without error
    assert scheduler.is_running

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_when_not_running(scheduler):
    """Test stopping when scheduler is not running."""
    assert not scheduler.is_running

    # Attempt to stop a non-running scheduler
    await scheduler.stop()
    # Should not raise an error
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_add_interval_job_without_time_params():
    """Test adding a job without time parameters."""
    scheduler = BackgroundScheduler()
    await scheduler.start()

    mock_func = AsyncMock()

    # Attempt to add job without minutes or seconds
    with pytest.raises(ValueError, match="minutes lub seconds"):
        scheduler.add_interval_job(func=mock_func, job_id="invalid_job")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_remove_nonexistent_job(scheduler):
    """Test removing a non-existent job."""
    await scheduler.start()

    # Attempt to remove a job that does not exist
    removed = scheduler.remove_job("nonexistent_job")
    assert removed is False

    await scheduler.stop()


@pytest.mark.asyncio
async def test_get_job_status_nonexistent(scheduler):
    """Test getting status of a non-existent job."""
    await scheduler.start()

    # Attempt to get status of a non-existent job
    status = scheduler.get_job_status("nonexistent_job")
    assert status is None

    await scheduler.stop()


def test_get_status_without_starting(scheduler):
    """Test getting status without starting the scheduler."""
    status = scheduler.get_status()

    assert isinstance(status, dict)
    assert "is_running" in status
    assert status["is_running"] is False


def test_get_jobs_empty(scheduler):
    """Test getting job list when it is empty."""
    jobs = scheduler.get_jobs()

    assert isinstance(jobs, list)
    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_add_interval_job_with_minutes(scheduler):
    """Test adding a job with minutes parameter."""
    await scheduler.start()

    mock_func = AsyncMock()
    job_id = scheduler.add_interval_job(
        func=mock_func, minutes=5, job_id="minute_job", description="Minute test"
    )

    assert job_id == "minute_job"

    # Check if the job is registered
    jobs = scheduler.get_jobs()
    assert any(job["id"] == "minute_job" for job in jobs)

    scheduler.remove_job(job_id)
    await scheduler.stop()


@pytest.mark.asyncio
async def test_add_interval_job_replace_existing(scheduler):
    """Test replacing an existing job."""
    await scheduler.start()

    mock_func1 = AsyncMock()
    mock_func2 = AsyncMock()

    # Add the first job
    job_id = scheduler.add_interval_job(
        func=mock_func1, seconds=10, job_id="replaceable_job"
    )

    # Add a job with the same ID (should replace)
    job_id2 = scheduler.add_interval_job(
        func=mock_func2, seconds=15, job_id="replaceable_job"
    )

    assert job_id == job_id2

    # There should be only one job with this ID
    jobs = scheduler.get_jobs()
    matching_jobs = [job for job in jobs if job["id"] == "replaceable_job"]
    assert len(matching_jobs) == 1

    scheduler.remove_job(job_id)
    await scheduler.stop()
