from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from venom_core.api.routes import feedback as feedback_routes


def _make_step(component: str, action: str, details: str | None = None):
    return SimpleNamespace(component=component, action=action, details=details)


def test_validate_feedback_payload_errors_and_success():
    task_id = uuid4()
    with pytest.raises(HTTPException) as exc_rating:
        feedback_routes._validate_feedback_payload(
            feedback_routes.FeedbackRequest(task_id=task_id, rating="meh")
        )
    assert exc_rating.value.status_code == 400

    with pytest.raises(HTTPException) as exc_comment:
        feedback_routes._validate_feedback_payload(
            feedback_routes.FeedbackRequest(
                task_id=task_id, rating="down", comment="  "
            )
        )
    assert exc_comment.value.status_code == 400

    assert (
        feedback_routes._validate_feedback_payload(
            feedback_routes.FeedbackRequest(task_id=task_id, rating="up", comment=None)
        )
        == ""
    )


def test_extract_result_from_trace_parses_last_simple_mode_response():
    trace = SimpleNamespace(
        steps=[
            _make_step("Other", "response", details='{"response":"ignored"}'),
            _make_step("SimpleMode", "response", details="{bad json"),
            _make_step(
                "SimpleMode", "response", details=json.dumps({"response": "final"})
            ),
        ]
    )

    assert feedback_routes._extract_result_from_trace(trace) == "final"
    assert feedback_routes._extract_result_from_trace(None) == ""


def test_resolve_feedback_context_from_task():
    task_id = uuid4()
    task = SimpleNamespace(
        content="prompt",
        result="result",
        context_history={
            "intent_debug": {"intent": "CHAT"},
            "tool_requirement": {"required": True},
        },
    )
    state = SimpleNamespace(get_task=lambda _task_id: task)

    prompt, result, intent, tool_required = feedback_routes._resolve_feedback_context(
        task_id, state
    )
    assert prompt == "prompt"
    assert result == "result"
    assert intent == "CHAT"
    assert tool_required is True


def test_resolve_feedback_context_from_trace_and_404(monkeypatch):
    task_id = uuid4()
    state = SimpleNamespace(get_task=lambda _task_id: None)

    trace = SimpleNamespace(prompt="trace prompt", steps=[])
    tracer = SimpleNamespace(get_trace=lambda _task_id: trace)
    monkeypatch.setattr(feedback_routes, "_request_tracer", tracer)

    prompt, result, intent, tool_required = feedback_routes._resolve_feedback_context(
        task_id, state
    )
    assert prompt == "trace prompt"
    assert result == ""
    assert intent is None
    assert tool_required is None

    monkeypatch.setattr(feedback_routes, "_request_tracer", None)
    with pytest.raises(HTTPException) as exc:
        feedback_routes._resolve_feedback_context(task_id, state)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_feedback_state_manager_missing():
    feedback_routes.set_dependencies(orchestrator=None, state_manager=None)
    payload = feedback_routes.FeedbackRequest(task_id=uuid4(), rating="up")

    with pytest.raises(HTTPException) as exc:
        await feedback_routes.submit_feedback(payload)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_submit_feedback_save_error_returns_500(monkeypatch):
    task_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        content="prompt",
        result="result",
        context_history={},
    )
    state = SimpleNamespace(get_task=lambda _task_id: task)
    feedback_routes.set_dependencies(orchestrator=None, state_manager=state)

    async def failing_save(*_args, **_kwargs):
        raise RuntimeError("disk error")

    monkeypatch.setattr(feedback_routes, "_save_jsonl_entry", failing_save)

    payload = feedback_routes.FeedbackRequest(task_id=task_id, rating="up")
    with pytest.raises(HTTPException) as exc:
        await feedback_routes.submit_feedback(payload)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_feedback_logs_limits_and_invalid_lines(tmp_path, monkeypatch):
    feedback_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(feedback_routes, "FEEDBACK_LOG_PATH", feedback_path)

    feedback_path.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "1", "rating": "up"}),
                "{invalid",
                json.dumps({"task_id": "2", "rating": "down"}),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc:
        await feedback_routes.get_feedback_logs(limit=5, rating="bad")
    assert exc.value.status_code == 400

    up_only = await feedback_routes.get_feedback_logs(limit=999, rating="up")
    assert up_only["count"] == 1
    assert up_only["items"][0]["rating"] == "up"

    none = await feedback_routes.get_feedback_logs(limit=0)
    assert "count" in none
