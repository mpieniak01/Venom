"""API contract tests for history ordering."""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.core.tracer import RequestTracer
from venom_core.main import app


@pytest.fixture
def tracer():
    return RequestTracer(watchdog_timeout_minutes=5)


@pytest.fixture
def client(tracer):
    from venom_core.api.routes import tasks as tasks_routes

    tasks_routes.set_dependencies(None, None, tracer)
    return TestClient(app)


def _seed_trace(tracer: RequestTracer, created_at: datetime) -> str:
    trace_id = uuid4()
    tracer.create_trace(trace_id, "Test prompt")
    trace = tracer.get_trace(trace_id)
    assert trace is not None
    trace.created_at = created_at
    return str(trace_id)


def test_history_requests_sorted_descending_by_created_at(client, tracer):
    t1 = datetime(2026, 2, 2, 10, 0, 0)
    t2 = datetime(2026, 2, 2, 10, 1, 0)
    t3 = datetime(2026, 2, 2, 10, 2, 0)

    _seed_trace(tracer, t2)
    _seed_trace(tracer, t3)
    _seed_trace(tracer, t1)

    response = client.get("/api/v1/history/requests?limit=50")
    assert response.status_code == 200

    data = response.json()
    created = [item["created_at"] for item in data]

    assert created == sorted(created, reverse=True)
