"""Tests for optional model introspection analysis API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes
from venom_core.api.routes import models_dependencies, models_introspection


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(models_routes.router)
    return TestClient(app)


def test_model_introspection_analysis_endpoint_skips_by_default() -> None:
    models_dependencies.set_dependencies(model_manager=None)
    client = _client()
    response = client.post(
        "/api/v1/models/introspection/analyze",
        json={
            "prompt": "Co to jest slonce?",
            "live_analysis_enabled": False,
            "max_tokens": 32,
            "temperature": 0.2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["snapshot"]
    assert payload["success"] is True
    assert snapshot["status"] == "skipped"
    assert snapshot["skipped_reason"] == "live_analysis_disabled"
    assert snapshot["analysis"]["timeline"][0]["label"] == "Live analysis disabled"


def test_model_introspection_analysis_endpoint_exposes_timeline() -> None:
    models_dependencies.set_dependencies(model_manager=None)
    client = _client()
    response = client.post(
        "/api/v1/models/introspection/analyze",
        json={
            "prompt": "Co to jest slonce?",
            "live_analysis_enabled": False,
            "max_tokens": 32,
            "temperature": 0.2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    analysis = payload["snapshot"]["analysis"]
    assert analysis["timeline"][0]["label"] == "Live analysis disabled"
    assert analysis["timeline"][0]["status"] == "skipped"


def test_model_introspection_stream_endpoint_forwards_sse() -> None:
    models_dependencies.set_dependencies(model_manager=None)

    async def fake_stream_model_introspection_analysis(**kwargs):
        yield 'event: analysis_start\ndata: {"status":"running"}\n\n'
        yield 'event: analysis_done\ndata: {"status":"completed"}\n\n'

    original = models_introspection.stream_model_introspection_analysis
    models_introspection.stream_model_introspection_analysis = (
        fake_stream_model_introspection_analysis
    )
    try:
        client = _client()
        response = client.post(
            "/api/v1/models/introspection/analyze/stream",
            json={
                "prompt": "Co to jest slonce?",
                "live_analysis_enabled": True,
                "max_tokens": 32,
                "temperature": 0.2,
            },
        )
    finally:
        models_introspection.stream_model_introspection_analysis = original

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: analysis_start" in response.text
    assert "event: analysis_done" in response.text
