"""Testy jednostkowe dla modułu RequestTracer."""

from datetime import timedelta
from uuid import uuid4

import pytest

from venom_core.core.tracer import RequestTracer, TraceStatus, get_utc_now


@pytest.fixture
def tracer():
    """Fixture dla RequestTracer."""
    return RequestTracer(watchdog_timeout_minutes=5)


@pytest.fixture
def sample_request_id():
    """Fixture dla przykładowego UUID requestu."""
    return uuid4()


# --- Testy tworzenia trace ---


def test_create_trace(tracer, sample_request_id):
    """Test tworzenia nowego trace."""
    prompt = "Test polecenie"
    trace = tracer.create_trace(sample_request_id, prompt)

    assert trace.request_id == sample_request_id
    assert trace.prompt == prompt
    assert trace.status == TraceStatus.PENDING
    assert trace.created_at is not None
    assert trace.finished_at is None
    assert len(trace.steps) == 0


def test_create_trace_truncates_long_prompt(tracer, sample_request_id):
    """Test skracania długiego promptu."""
    # 550 znaków, aby potwierdzić limit 500 + "..." dla skróconego promptu.
    long_prompt = "a" * 550
    trace = tracer.create_trace(sample_request_id, long_prompt)

    assert len(trace.prompt) == 503  # 500 + "..."
    assert trace.prompt.endswith("...")


def test_get_trace(tracer, sample_request_id):
    """Test pobierania trace po ID."""
    prompt = "Test polecenie"
    tracer.create_trace(sample_request_id, prompt)

    trace = tracer.get_trace(sample_request_id)
    assert trace is not None
    assert trace.request_id == sample_request_id


def test_get_nonexistent_trace(tracer):
    """Test pobierania nieistniejącego trace."""
    nonexistent_id = uuid4()
    trace = tracer.get_trace(nonexistent_id)
    assert trace is None


# --- Testy dodawania kroków ---


def test_add_step(tracer, sample_request_id):
    """Test dodawania kroku do trace."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.add_step(sample_request_id, "Orchestrator", "start_processing")

    trace = tracer.get_trace(sample_request_id)
    assert len(trace.steps) == 1
    assert trace.steps[0].component == "Orchestrator"
    assert trace.steps[0].action == "start_processing"
    assert trace.steps[0].status == "ok"


def test_add_step_with_details(tracer, sample_request_id):
    """Test dodawania kroku z szczegółami."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.add_step(
        sample_request_id,
        "ResearcherAgent",
        "web_search",
        status="ok",
        details="Found 5 results",
    )

    trace = tracer.get_trace(sample_request_id)
    assert len(trace.steps) == 1
    assert trace.steps[0].details == "Found 5 results"


def test_add_step_error(tracer, sample_request_id):
    """Test dodawania kroku z błędem."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.add_step(
        sample_request_id,
        "System",
        "error",
        status="error",
        details="Connection timeout",
    )

    trace = tracer.get_trace(sample_request_id)
    assert len(trace.steps) == 1
    assert trace.steps[0].status == "error"


def test_add_step_to_nonexistent_trace(tracer):
    """Test dodawania kroku do nieistniejącego trace (powinno być bezpieczne)."""
    nonexistent_id = uuid4()
    # Nie powinno rzucić wyjątku
    tracer.add_step(nonexistent_id, "Component", "action")


# --- Testy aktualizacji statusu ---


def test_update_status(tracer, sample_request_id):
    """Test aktualizacji statusu trace."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.update_status(sample_request_id, TraceStatus.PROCESSING)

    trace = tracer.get_trace(sample_request_id)
    assert trace.status == TraceStatus.PROCESSING


def test_update_status_to_completed_sets_finished_at(tracer, sample_request_id):
    """Test że zmiana statusu na COMPLETED ustawia finished_at."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.update_status(sample_request_id, TraceStatus.COMPLETED)

    trace = tracer.get_trace(sample_request_id)
    assert trace.finished_at is not None


def test_update_status_to_failed_sets_finished_at(tracer, sample_request_id):
    """Test że zmiana statusu na FAILED ustawia finished_at."""
    tracer.create_trace(sample_request_id, "Test")
    tracer.update_status(sample_request_id, TraceStatus.FAILED)

    trace = tracer.get_trace(sample_request_id)
    assert trace.finished_at is not None


# --- Testy pobierania wszystkich traces ---


def test_get_all_traces_empty(tracer):
    """Test pobierania listy traces gdy brak danych."""
    traces = tracer.get_all_traces()
    assert len(traces) == 0


def test_get_all_traces_returns_sorted(tracer):
    """Test że traces są sortowane rosnąco po created_at."""
    import time

    id1 = uuid4()
    id2 = uuid4()
    id3 = uuid4()

    tracer.create_trace(id1, "First")
    time.sleep(0.01)  # Mała przerwa aby mieć różne czasy
    tracer.create_trace(id2, "Second")
    time.sleep(0.01)
    tracer.create_trace(id3, "Third")

    traces = tracer.get_all_traces()
    assert len(traces) == 3
    # Najnowszy (Third) powinien być pierwszy
    assert traces[0].request_id == id3
    assert traces[2].request_id == id1


def test_get_all_traces_with_limit(tracer):
    """Test paginacji z limitem."""
    for i in range(10):
        tracer.create_trace(uuid4(), f"Request {i}")

    traces = tracer.get_all_traces(limit=5)
    assert len(traces) == 5


def test_get_all_traces_with_offset(tracer):
    """Test paginacji z offsetem."""
    ids = []
    for i in range(5):
        request_id = uuid4()
        ids.append(request_id)
        tracer.create_trace(request_id, f"Request {i}")

    traces = tracer.get_all_traces(offset=2)
    assert len(traces) == 3


def test_get_all_traces_with_status_filter(tracer):
    """Test filtrowania po statusie."""
    id1 = uuid4()
    id2 = uuid4()
    id3 = uuid4()

    tracer.create_trace(id1, "Pending request")
    tracer.create_trace(id2, "Processing request")
    tracer.create_trace(id3, "Completed request")

    tracer.update_status(id2, TraceStatus.PROCESSING)
    tracer.update_status(id3, TraceStatus.COMPLETED)

    completed_traces = tracer.get_all_traces(status_filter="COMPLETED")
    assert len(completed_traces) == 1
    assert completed_traces[0].request_id == id3


# --- Testy licznika ---


def test_get_trace_count(tracer):
    """Test zliczania traces."""
    assert tracer.get_trace_count() == 0

    tracer.create_trace(uuid4(), "First")
    assert tracer.get_trace_count() == 1

    tracer.create_trace(uuid4(), "Second")
    assert tracer.get_trace_count() == 2


# --- Testy czyszczenia starych traces ---


def test_clear_old_traces(tracer):
    """Test usuwania starych traces."""
    # Utwórz trace i "postarz" go
    old_id = uuid4()
    trace = tracer.create_trace(old_id, "Old request")
    trace.created_at = get_utc_now() - timedelta(days=8)

    # Utwórz świeży trace
    new_id = uuid4()
    tracer.create_trace(new_id, "New request")

    assert tracer.get_trace_count() == 2

    # Usuń stare (starsze niż 7 dni)
    tracer.clear_old_traces(days=7)

    assert tracer.get_trace_count() == 1
    assert tracer.get_trace(old_id) is None
    assert tracer.get_trace(new_id) is not None


# --- Testy watchdog ---


@pytest.mark.asyncio
async def test_watchdog_start_stop(tracer):
    """Test uruchamiania i zatrzymywania watchdog."""
    await tracer.start_watchdog()
    assert tracer._watchdog_task is not None

    await tracer.stop_watchdog()
    assert tracer._watchdog_task is None


def test_watchdog_marks_lost_requests(tracer):
    """Test że watchdog oznacza stare requesty jako LOST."""
    request_id = uuid4()
    tracer.create_trace(request_id, "Test request")
    tracer.update_status(request_id, TraceStatus.PROCESSING)

    # Postarz last_activity
    trace = tracer.get_trace(request_id)
    trace.last_activity = get_utc_now() - timedelta(minutes=6)

    # Uruchom watchdog check ręcznie
    tracer._check_lost_requests()

    # Sprawdź że został oznaczony jako LOST
    trace = tracer.get_trace(request_id)
    assert trace.status == TraceStatus.LOST
    assert trace.finished_at is not None
    assert any(step.action == "timeout" for step in trace.steps)


def test_watchdog_does_not_mark_fresh_requests(tracer):
    """Test że watchdog nie oznacza świeżych requestów."""
    request_id = uuid4()
    tracer.create_trace(request_id, "Test request")
    tracer.update_status(request_id, TraceStatus.PROCESSING)

    # Uruchom watchdog check
    tracer._check_lost_requests()

    # Sprawdź że nadal jest PROCESSING
    trace = tracer.get_trace(request_id)
    assert trace.status == TraceStatus.PROCESSING


def test_watchdog_does_not_mark_completed_requests(tracer):
    """Test że watchdog nie dotyka ukończonych requestów."""
    request_id = uuid4()
    tracer.create_trace(request_id, "Test request")
    tracer.update_status(request_id, TraceStatus.COMPLETED)

    # Postarz last_activity (ale status to COMPLETED)
    trace = tracer.get_trace(request_id)
    trace.last_activity = get_utc_now() - timedelta(minutes=6)

    # Uruchom watchdog check
    tracer._check_lost_requests()

    # Sprawdź że nadal jest COMPLETED
    trace = tracer.get_trace(request_id)
    assert trace.status == TraceStatus.COMPLETED
