"""Testy jednostkowe dla History API - opcjonalne pola finished_at i duration_seconds."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure venom_core is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.api.routes.tasks import HistoryRequestDetail, HistoryRequestSummary


def test_history_request_summary_with_all_fields():
    """Test tworzenia HistoryRequestSummary ze wszystkimi polami."""
    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test prompt",
        status="COMPLETED",
        created_at="2024-12-17T10:00:00",
        finished_at="2024-12-17T10:05:00",
        duration_seconds=300.0,
        llm_provider="ollama",
        llm_model="llama3:latest",
        llm_endpoint="http://localhost:11434",
    )

    assert summary.request_id == request_id
    assert summary.prompt == "Test prompt"
    assert summary.status == "COMPLETED"
    assert summary.finished_at == "2024-12-17T10:05:00"
    assert summary.duration_seconds == 300.0


def test_history_request_summary_without_finished_at():
    """Test tworzenia HistoryRequestSummary bez finished_at (zadanie w toku)."""
    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test prompt",
        status="PROCESSING",
        created_at="2024-12-17T10:00:00",
        # finished_at=None - domyślnie
        # duration_seconds=None - domyślnie
    )

    assert summary.request_id == request_id
    assert summary.finished_at is None
    assert summary.duration_seconds is None


def test_history_request_summary_explicit_none():
    """Test tworzenia HistoryRequestSummary z jawnym None."""
    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test prompt",
        status="PENDING",
        created_at="2024-12-17T10:00:00",
        finished_at=None,
        duration_seconds=None,
    )

    assert summary.finished_at is None
    assert summary.duration_seconds is None


def test_history_request_summary_to_dict():
    """Test serializacji HistoryRequestSummary do dict."""
    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test prompt",
        status="COMPLETED",
        created_at="2024-12-17T10:00:00",
        finished_at="2024-12-17T10:05:00",
        duration_seconds=300.0,
    )

    data = summary.model_dump()

    assert data["request_id"] == request_id
    assert data["finished_at"] == "2024-12-17T10:05:00"
    assert data["duration_seconds"] == 300.0


def test_history_request_summary_to_dict_with_none():
    """Test serializacji HistoryRequestSummary z None do dict."""
    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test prompt",
        status="PROCESSING",
        created_at="2024-12-17T10:00:00",
    )

    data = summary.model_dump()

    assert data["finished_at"] is None
    assert data["duration_seconds"] is None


def test_history_request_detail_with_all_fields():
    """Test tworzenia HistoryRequestDetail ze wszystkimi polami."""
    request_id = uuid4()
    detail = HistoryRequestDetail(
        request_id=request_id,
        prompt="Test prompt",
        status="COMPLETED",
        created_at="2024-12-17T10:00:00",
        finished_at="2024-12-17T10:05:00",
        duration_seconds=300.0,
        steps=[
            {
                "component": "Orchestrator",
                "action": "start",
                "timestamp": "2024-12-17T10:00:00",
                "status": "OK",
                "details": None,
            }
        ],
        llm_provider="ollama",
        llm_model="llama3:latest",
        llm_endpoint="http://localhost:11434",
    )

    assert detail.request_id == request_id
    assert detail.finished_at == "2024-12-17T10:05:00"
    assert detail.duration_seconds == 300.0
    assert len(detail.steps) == 1


def test_history_request_detail_without_finished_at():
    """Test tworzenia HistoryRequestDetail bez finished_at."""
    request_id = uuid4()
    detail = HistoryRequestDetail(
        request_id=request_id,
        prompt="Test prompt",
        status="PROCESSING",
        created_at="2024-12-17T10:00:00",
        steps=[],
    )

    assert detail.finished_at is None
    assert detail.duration_seconds is None


def test_history_request_detail_to_dict():
    """Test serializacji HistoryRequestDetail do dict."""
    request_id = uuid4()
    detail = HistoryRequestDetail(
        request_id=request_id,
        prompt="Test prompt",
        status="COMPLETED",
        created_at="2024-12-17T10:00:00",
        finished_at="2024-12-17T10:05:00",
        duration_seconds=300.0,
        steps=[],
    )

    data = detail.model_dump()

    assert data["finished_at"] == "2024-12-17T10:05:00"
    assert data["duration_seconds"] == 300.0


def test_history_request_detail_to_dict_with_none():
    """Test serializacji HistoryRequestDetail z None do dict."""
    request_id = uuid4()
    detail = HistoryRequestDetail(
        request_id=request_id,
        prompt="Test prompt",
        status="PENDING",
        created_at="2024-12-17T10:00:00",
        steps=[],
    )

    data = detail.model_dump()

    assert data["finished_at"] is None
    assert data["duration_seconds"] is None


def test_history_models_json_serialization():
    """Test serializacji JSON (jak w FastAPI response)."""
    import json

    request_id = uuid4()
    summary = HistoryRequestSummary(
        request_id=request_id,
        prompt="Test",
        status="PROCESSING",
        created_at="2024-12-17T10:00:00",
    )

    # Pydantic v2 używa model_dump_json()
    json_str = summary.model_dump_json()
    parsed = json.loads(json_str)

    assert parsed["finished_at"] is None
    assert parsed["duration_seconds"] is None
