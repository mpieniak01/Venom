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
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: analysis_start" in response.text
    assert "event: analysis_done" in response.text


def test_model_introspection_snapshot_endpoint_returns_500_without_internal_detail() -> (
    None
):
    async def _boom_snapshot(**_kwargs):
        raise RuntimeError("secret backend detail")

    original = models_introspection.build_model_introspection_snapshot
    models_introspection.build_model_introspection_snapshot = _boom_snapshot
    try:
        client = _client()
        response = client.get("/api/v1/models/introspection")
    finally:
        models_introspection.build_model_introspection_snapshot = original

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"


def test_model_introspection_analyze_endpoint_returns_500_without_internal_detail() -> (
    None
):
    async def _boom_analyze(**_kwargs):
        raise RuntimeError("sensitive trace")

    original = models_introspection.analyze_model_with_optional_live_run
    models_introspection.analyze_model_with_optional_live_run = _boom_analyze
    try:
        client = _client()
        response = client.post(
            "/api/v1/models/introspection/analyze",
            json={
                "prompt": "Co to jest slonce?",
                "live_analysis_enabled": True,
                "max_tokens": 32,
                "temperature": 0.2,
            },
        )
    finally:
        models_introspection.analyze_model_with_optional_live_run = original

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"


def test_model_introspection_stream_endpoint_returns_500_without_internal_detail() -> (
    None
):
    def _boom_stream(**_kwargs):
        raise RuntimeError("stream failure")

    original = models_introspection.stream_model_introspection_analysis
    models_introspection.stream_model_introspection_analysis = _boom_stream
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

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"


def test_model_introspection_analyze_endpoint_maps_value_error_to_safe_400() -> None:
    async def _bad_request(**_kwargs):
        raise ValueError("internal validation detail")

    original = models_introspection.analyze_model_with_optional_live_run
    models_introspection.analyze_model_with_optional_live_run = _bad_request
    try:
        client = _client()
        response = client.post(
            "/api/v1/models/introspection/analyze",
            json={
                "prompt": "Co to jest slonce?",
                "live_analysis_enabled": True,
                "max_tokens": 32,
                "temperature": 0.2,
            },
        )
    finally:
        models_introspection.analyze_model_with_optional_live_run = original

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request parameters"


def test_model_introspection_stream_endpoint_maps_value_error_to_safe_400() -> None:
    client = _client()
    response = client.post(
        "/api/v1/models/introspection/analyze/stream",
        json={
            "prompt": "   ",
            "live_analysis_enabled": True,
            "max_tokens": 32,
            "temperature": 0.2,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request parameters"
