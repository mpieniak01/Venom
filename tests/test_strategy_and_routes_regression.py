"""Hotfix tests for low-coverage strategy/session/config/workflow routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from venom_core.api.routes import strategy as strategy_routes
from venom_core.api.routes import system_config as system_config_routes
from venom_core.api.routes import workflow_operations as workflow_ops_routes
from venom_core.api.schemas.system import ConfigUpdateRequest, RestoreBackupRequest
from venom_core.api.schemas.workflow_control import (
    WorkflowOperation,
    WorkflowOperationRequest,
)
from venom_core.memory.embedding_service import EmbeddingService
from venom_core.services.session_store import SessionStore


def _request_with_host(
    host: str = "127.0.0.1", headers: dict[str, str] | None = None
) -> Request:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": encoded_headers,
        "client": (host, 1234),
    }
    return Request(scope)


def _goal(title: str, status: str, description: str = "desc", priority: int = 1):
    return SimpleNamespace(
        goal_id=f"{title}-id",
        title=title,
        description=description,
        priority=priority,
        status=SimpleNamespace(value=status),
        get_progress=lambda: 50.0,
    )


def test_session_store_handles_save_error_and_empty_clear(tmp_path):
    store = SessionStore(store_path=str(tmp_path / "store.json"))
    with patch(
        "venom_core.services.session_store.json.dump", side_effect=OSError("disk")
    ):
        store.append_message("s1", {"role": "user", "content": "x"})
    assert store.clear_session("") is False


def test_embedding_service_raises_for_unknown_type():
    service = EmbeddingService(service_type="unknown")
    with pytest.raises(ValueError):
        service.get_embedding("abc")


def test_embedding_service_openai_batch_requires_client(monkeypatch):
    service = EmbeddingService(service_type="openai")
    monkeypatch.setattr(service, "_ensure_model_loaded", lambda: None)
    service._client = None
    with pytest.raises(RuntimeError):
        service.get_embeddings_batch(["abc"])


def test_get_roadmap_returns_503_when_orchestrator_missing():
    strategy_routes.set_dependencies(None)
    with pytest.raises(HTTPException) as exc:
        strategy_routes.get_roadmap()
    assert exc.value.status_code == 503


def test_get_roadmap_success_with_goal_data():
    vision = _goal("Vision", "RUNNING", description="Vision text")
    milestone = _goal("Milestone", "COMPLETED")
    task = _goal("Task", "COMPLETED", priority=2)

    goal_store = SimpleNamespace(
        get_vision=lambda: vision,
        get_milestones=lambda: [milestone],
        get_tasks=lambda parent_id=None: [task]
        if parent_id == milestone.goal_id
        else [],
        generate_roadmap_report=lambda: "report",
    )
    orchestrator = SimpleNamespace(
        task_dispatcher=SimpleNamespace(goal_store=goal_store)
    )
    strategy_routes.set_dependencies(orchestrator)

    result = strategy_routes.get_roadmap()
    assert result["status"] == "success"
    assert result["vision"]["title"] == "Vision"
    assert result["kpis"]["milestones_completed"] == 1
    assert result["kpis"]["tasks_completed"] == 1


@pytest.mark.asyncio
async def test_strategy_async_endpoints_success_and_error_paths():
    executive = SimpleNamespace(
        create_roadmap=AsyncMock(return_value={"items": 1}),
        generate_status_report=AsyncMock(return_value={"ok": True}),
    )
    orchestrator = SimpleNamespace(
        task_dispatcher=SimpleNamespace(executive_agent=executive, goal_store=object()),
        execute_campaign_mode=AsyncMock(return_value={"started": True}),
    )
    strategy_routes.set_dependencies(orchestrator)

    create_result = await strategy_routes.create_roadmap(
        SimpleNamespace(vision="build x")
    )
    assert create_result["status"] == "success"
    status_result = await strategy_routes.get_roadmap_status()
    assert status_result["report"]["ok"] is True
    campaign_result = await strategy_routes.start_campaign()
    assert campaign_result["result"]["started"] is True

    executive.create_roadmap.side_effect = RuntimeError("boom")
    with pytest.raises(HTTPException) as exc:
        await strategy_routes.create_roadmap(SimpleNamespace(vision="x"))
    assert exc.value.status_code == 500


def test_system_config_update_non_dict_and_http_exception_passthrough():
    req = _request_with_host("127.0.0.1")
    payload = ConfigUpdateRequest(updates={"A": "1"})

    direct = system_config_routes.ConfigUpdateResponse(
        status="success",
        message="ok",
        updated_keys=["A"],
    )
    with patch.object(
        system_config_routes.config_manager, "update_config", return_value=direct
    ):
        result = system_config_routes.update_runtime_config(payload, req)
    assert result is direct

    with patch.object(
        system_config_routes.config_manager,
        "update_config",
        side_effect=HTTPException(status_code=403, detail="denied"),
    ):
        with pytest.raises(HTTPException) as exc:
            system_config_routes.update_runtime_config(payload, req)
    assert exc.value.status_code == 403


def test_system_config_restore_non_dict_result():
    req = _request_with_host("127.0.0.1")
    restore_request = RestoreBackupRequest(backup_filename="backup.env")
    direct = system_config_routes.RestoreBackupResponse(
        status="success",
        message="restored",
        restored_file="backup.env",
    )
    with patch.object(
        system_config_routes.config_manager, "restore_backup", return_value=direct
    ):
        result = system_config_routes.restore_config_backup(restore_request, req)
    assert result is direct


def test_workflow_ops_extract_user_paths():
    req_with_state = _request_with_host(headers={"x-user": "header-user"})
    req_with_state.state.user = "state-user"
    assert (
        workflow_ops_routes._extract_user_from_request(req_with_state) == "state-user"
    )

    class BrokenRequest:
        state = object()

        @property
        def headers(self):
            raise RuntimeError("broken")

    assert workflow_ops_routes._extract_user_from_request(BrokenRequest()) == "unknown"


@pytest.mark.asyncio
async def test_workflow_ops_pause_resume_cancel_retry_and_dry_run():
    req = _request_with_host(headers={"x-authenticated-user": "tester"})
    operation_request = WorkflowOperationRequest(
        workflow_id=uuid4(),
        operation=WorkflowOperation.PAUSE,
        metadata={"k": "v"},
    )
    response_obj = SimpleNamespace(status="ok")
    service = SimpleNamespace(
        pause_workflow=MagicMock(return_value=response_obj),
        resume_workflow=MagicMock(return_value=response_obj),
        cancel_workflow=MagicMock(return_value=response_obj),
        retry_workflow=MagicMock(return_value=response_obj),
        dry_run=MagicMock(return_value=response_obj),
    )

    with patch(
        "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
        return_value=service,
    ):
        assert (
            await workflow_ops_routes.pause_workflow(req, operation_request)
            is response_obj
        )
        assert (
            await workflow_ops_routes.resume_workflow(req, operation_request)
            is response_obj
        )
        assert (
            await workflow_ops_routes.cancel_workflow(req, operation_request)
            is response_obj
        )
        assert (
            await workflow_ops_routes.retry_workflow(req, operation_request)
            is response_obj
        )
        assert (
            await workflow_ops_routes.dry_run_workflow(req, operation_request)
            is response_obj
        )
