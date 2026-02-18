"""Testy dla feedbacku i hidden prompts (PR 064/067)."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from venom_core.api.routes import feedback as feedback_routes
from venom_core.core import hidden_prompts


class DummyStateManager:
    def __init__(self, task):
        self._task = task

    def get_task(self, task_id):
        return self._task if str(task_id) == str(self._task.id) else None


class DummyOrchestrator:
    def __init__(self, task_id):
        self._task_id = task_id

    async def submit_task(self, request):
        await asyncio.sleep(0)
        return SimpleNamespace(task_id=self._task_id)


def _write_jsonl(path: Path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


@pytest.mark.asyncio
async def test_feedback_endpoint_saves_and_triggers_followup(tmp_path, monkeypatch):
    feedback_path = tmp_path / "feedback.jsonl"
    hidden_path = tmp_path / "hidden.jsonl"
    monkeypatch.setattr(feedback_routes, "FEEDBACK_LOG_PATH", feedback_path)
    monkeypatch.setattr(feedback_routes, "HIDDEN_PROMPT_LOG_PATH", hidden_path)

    task_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        content="Test prompt",
        result="Test result",
        context_history={
            "intent_debug": {"intent": "GENERAL_CHAT"},
            "tool_requirement": {"intent": "GENERAL_CHAT", "required": False},
        },
    )
    feedback_routes.set_dependencies(
        DummyOrchestrator(uuid4()),
        DummyStateManager(task),
    )

    payload = feedback_routes.FeedbackRequest(
        task_id=task_id, rating="down", comment="Brakuje szczegolow"
    )
    response = await feedback_routes.submit_feedback(payload)
    assert response.status == "ok"
    assert response.follow_up_task_id
    assert feedback_path.exists()

    payload_up = feedback_routes.FeedbackRequest(task_id=task_id, rating="up")
    response_up = await feedback_routes.submit_feedback(payload_up)
    assert response_up.status == "ok"
    assert hidden_path.exists()


@pytest.mark.asyncio
async def test_feedback_logs_filtering(tmp_path, monkeypatch):
    feedback_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(feedback_routes, "FEEDBACK_LOG_PATH", feedback_path)

    _write_jsonl(
        feedback_path,
        [
            {"task_id": "1", "rating": "up", "timestamp": "2024-01-01T10:00:00"},
            {"task_id": "2", "rating": "down", "timestamp": "2024-01-01T10:01:00"},
        ],
    )

    data = await feedback_routes.get_feedback_logs(limit=10, rating="up")
    assert data.count == 1
    assert data.items[0]["rating"] == "up"


def test_hidden_prompts_aggregation_dedup(tmp_path, monkeypatch):
    hidden_path = tmp_path / "hidden.jsonl"
    monkeypatch.setattr(hidden_prompts, "HIDDEN_PROMPTS_PATH", hidden_path)
    hidden_prompts._cache_mtime = None
    hidden_prompts._cache_entries = []

    _write_jsonl(
        hidden_path,
        [
            {
                "intent": "GENERAL_CHAT",
                "prompt": "Hello",
                "approved_response": "A",
                "prompt_hash": "hash1",
                "timestamp": "2024-01-01T10:00:00",
            },
            {
                "intent": "GENERAL_CHAT",
                "prompt": "Hello",
                "approved_response": "B",
                "prompt_hash": "hash1",
                "timestamp": "2024-01-02T10:00:00",
            },
        ],
    )

    items = hidden_prompts.aggregate_hidden_prompts(limit=5)
    assert len(items) == 1
    assert items[0]["score"] == 2
    assert items[0]["approved_response"] == "B"


def test_active_hidden_prompts_priority(tmp_path, monkeypatch):
    hidden_path = tmp_path / "hidden.jsonl"
    active_path = tmp_path / "active.json"
    monkeypatch.setattr(hidden_prompts, "HIDDEN_PROMPTS_PATH", hidden_path)
    monkeypatch.setattr(hidden_prompts, "ACTIVE_HIDDEN_PROMPTS_PATH", active_path)
    hidden_prompts._cache_mtime = None
    hidden_prompts._cache_entries = []

    _write_jsonl(
        hidden_path,
        [
            {
                "intent": "GENERAL_CHAT",
                "prompt": "P1",
                "approved_response": "R1",
                "prompt_hash": "h1",
                "timestamp": "2024-01-01T10:00:00",
            },
            {
                "intent": "GENERAL_CHAT",
                "prompt": "P2",
                "approved_response": "R2",
                "prompt_hash": "h2",
                "timestamp": "2024-01-01T10:01:00",
            },
        ],
    )

    hidden_prompts.set_active_hidden_prompt(
        {
            "intent": "GENERAL_CHAT",
            "prompt": "P2",
            "approved_response": "R2",
            "prompt_hash": "h2",
        },
        active=True,
        actor="test",
    )

    context = hidden_prompts.build_hidden_prompts_context("GENERAL_CHAT", limit=2)
    assert "P2" in context
    assert context.index("P2") < context.index("P1")


def test_hidden_prompt_prepare_entry_filters():
    assert hidden_prompts._prepare_hidden_prompt_entry({"prompt": "   "}, None) is None
    assert (
        hidden_prompts._prepare_hidden_prompt_entry({"prompt": "x", "intent": "A"}, "B")
        is None
    )
    prepared = hidden_prompts._prepare_hidden_prompt_entry(
        {
            "prompt": "x",
            "intent": "A",
            "approved_response": "R",
            "timestamp": "2024-01-01T10:00:00",
        },
        None,
    )
    assert prepared is not None


def test_hidden_prompt_upsert_updates_newer_response():
    aggregated = {}
    payload = {
        "intent": "GENERAL_CHAT",
        "prompt": "P",
        "approved_response": "R1",
        "prompt_hash": "h1",
        "timestamp": "2024-01-01T10:00:00",
    }
    hidden_prompts._upsert_aggregated_prompt(aggregated, "h1", payload)
    assert aggregated["h1"]["score"] == 1

    payload_newer = dict(payload)
    payload_newer["approved_response"] = "R2"
    payload_newer["timestamp"] = "2024-01-02T10:00:00"
    hidden_prompts._upsert_aggregated_prompt(aggregated, "h1", payload_newer)
    assert aggregated["h1"]["score"] == 2
    assert aggregated["h1"]["approved_response"] == "R2"


def test_find_exact_cached_response_prefers_active(monkeypatch):
    monkeypatch.setattr(
        hidden_prompts,
        "get_active_hidden_prompts",
        lambda intent=None: [{"prompt": "Hello", "approved_response": "Active"}],
    )
    monkeypatch.setattr(
        hidden_prompts,
        "aggregate_hidden_prompts",
        lambda **_kwargs: [{"prompt": "Hello", "approved_response": "Aggregated"}],
    )

    value = hidden_prompts._find_exact_cached_response(
        hidden_prompts._normalize("hello"), intent=None, min_score=1
    )
    assert value == "Active"


def test_find_semantic_cached_response_handles_store_error(monkeypatch):
    class BrokenStore:
        def __init__(self, **_kwargs):
            pass

        def search(self, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "venom_core.memory.vector_store",
        SimpleNamespace(VectorStore=BrokenStore),
    )
    assert hidden_prompts._find_semantic_cached_response("hello", intent=None) is None
