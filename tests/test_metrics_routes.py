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
    assert data["session_cost_usd"] == pytest.approx(0.0)


def test_get_token_metrics_with_economist(monkeypatch, client):
    class DummyCollector:
        def get_metrics(self):
            return {"tokens_used_session": 100}

    class DummyEconomist:
        def get_model_breakdown(self):
            # Return empty breakdown to trigger fallback to estimation
            return {
                "models_breakdown": {},
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }
        
        def calculate_cost(self, usage, model_name):
            return {"total_cost_usd": 1.23}

    metrics_routes.set_dependencies(token_economist=DummyEconomist())
    monkeypatch.setattr(metrics_module, "metrics_collector", DummyCollector())

    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 200
    data = response.json()
    assert data["session_cost_usd"] == pytest.approx(1.23)
    assert data["models_breakdown"]["estimated"]["tokens"] == 100


def test_get_system_metrics_error(monkeypatch, client):
    class FailingCollector:
        def get_metrics(self):
            raise RuntimeError("boom")

    metrics_routes.set_dependencies(token_economist=None)
    monkeypatch.setattr(metrics_module, "metrics_collector", FailingCollector())

    response = client.get("/api/v1/metrics/system")
    assert response.status_code == 500


def test_get_token_metrics_with_per_model_breakdown(monkeypatch, client):
    """Test metrics endpoint zwraca per-model breakdown gdy TokenEconomist ma dane (PR-132A)."""
    
    class DummyCollector:
        def get_metrics(self):
            return {"tokens_used_session": 500}
    
    class DummyEconomistWithTracking:
        def get_model_breakdown(self):
            return {
                "models_breakdown": {
                    "gpt-4o": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                        "cost_usd": 0.00225,
                    },
                    "local": {
                        "input_tokens": 200,
                        "output_tokens": 150,
                        "total_tokens": 350,
                        "cost_usd": 0.0,
                    }
                },
                "total_tokens": 500,
                "total_cost_usd": 0.00225,
            }
    
    metrics_routes.set_dependencies(token_economist=DummyEconomistWithTracking())
    monkeypatch.setattr(metrics_module, "metrics_collector", DummyCollector())
    
    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 200
    data = response.json()
    
    # Sprawdź czy zwrócono rzeczywiste dane per-model
    assert data["total_tokens"] == 500
    assert data["session_total_tokens"] == 500
    assert data["session_cost_usd"] == pytest.approx(0.00225)
    
    # Sprawdź breakdown per-model
    assert "gpt-4o" in data["models_breakdown"]
    assert "local" in data["models_breakdown"]
    assert data["models_breakdown"]["gpt-4o"]["total_tokens"] == 150
    assert data["models_breakdown"]["local"]["total_tokens"] == 350
    assert data["models_breakdown"]["gpt-4o"]["cost_usd"] == pytest.approx(0.00225)
    assert data["models_breakdown"]["local"]["cost_usd"] == 0.0
    
    # Nie powinno być komunikatu "note" o braku danych
    assert "note" not in data or "brak zarejestrowanego użycia" not in data.get("note", "").lower()


def test_get_token_metrics_economist_no_data_fallback(monkeypatch, client):
    """Test fallback do estymacji gdy TokenEconomist nie ma danych per-model (PR-132A)."""
    
    class DummyCollector:
        def get_metrics(self):
            return {"tokens_used_session": 200}
    
    class DummyEconomistWithoutData:
        def get_model_breakdown(self):
            # Brak danych per-model
            return {
                "models_breakdown": {},
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }
        
        def calculate_cost(self, usage, model_name):
            return {"total_cost_usd": 0.0003}
    
    metrics_routes.set_dependencies(token_economist=DummyEconomistWithoutData())
    monkeypatch.setattr(metrics_module, "metrics_collector", DummyCollector())
    
    response = client.get("/api/v1/metrics/tokens")
    assert response.status_code == 200
    data = response.json()
    
    # Sprawdź czy zwrócono estymację
    assert data["total_tokens"] == 200
    assert "estimated" in data["models_breakdown"]
    assert "note" in data
    assert "szacunkowe" in data["note"].lower() or "estimated" in data["note"].lower()
