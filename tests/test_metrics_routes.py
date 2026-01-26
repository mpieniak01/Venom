"""Tests for metrics routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_metrics as metrics_routes
from venom_core.core import metrics as metrics_module


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(metrics_routes.router)
    return TestClient(app)


def test_get_token_metrics_requires_collector(monkeypatch, client):
    metrics_routes.set_dependencies(token_economist=None)
    monkeypatch.setattr(metrics_module, "metrics_collector", None)

    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 503


def test_get_token_metrics_basic_without_economist(monkeypatch, client):
    metrics_routes.set_dependencies(token_economist=None)

    class DummyCollector:
        def get_metrics(self):
            return {"tokens_used_session": 123}

    monkeypatch.setattr(metrics_module, "metrics_collector", DummyCollector())

    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 200
    data = response.json()
    assert data["session_total_tokens"] == 123
    assert data["session_cost_usd"] == 0.0


def test_get_token_metrics_with_economist(monkeypatch, client):
    class DummyCollector:
        def get_metrics(self):
            return {"tokens_used_session": 100}

    class DummyEconomist:
        def calculate_cost(self, usage, model_name):
            return {"total_cost_usd": 1.23}

    metrics_routes.set_dependencies(token_economist=DummyEconomist())
    monkeypatch.setattr(metrics_module, "metrics_collector", DummyCollector())

    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 200
    data = response.json()
    assert data["session_cost_usd"] == 1.23
    assert data["models_breakdown"]["estimated"]["tokens"] == 100


def test_get_system_metrics_error(monkeypatch, client):
    class FailingCollector:
        def get_metrics(self):
            raise RuntimeError("boom")

    metrics_routes.set_dependencies(token_economist=None)
    monkeypatch.setattr(metrics_module, "metrics_collector", FailingCollector())

    response = client.get("/api/v1/metrics/system")
    assert response.status_code == 500
