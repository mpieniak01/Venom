from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import governance as governance_routes
from venom_core.api.routes import knowledge as knowledge_routes
from venom_core.api.routes import memory as memory_routes


def _blocked(_operation_name: str) -> None:
    raise PermissionError("blocked")


def test_memory_mutation_endpoints_blocked(monkeypatch):
    app = FastAPI()
    app.include_router(memory_routes.router)
    client = TestClient(app)

    vector_store = MagicMock()
    vector_store.delete_by_metadata.return_value = 0
    vector_store.wipe_collection.return_value = 0
    memory_routes.set_dependencies(vector_store=vector_store)

    monkeypatch.setattr(memory_routes, "ensure_data_mutation_allowed", _blocked)

    resp = client.delete("/api/v1/memory/global")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["decision"] == "block"
    assert detail["reason_code"] == "PERMISSION_DENIED"
    assert detail["technical_context"]["operation"] == "memory.clear_global"

    resp = client.delete("/api/v1/memory/session/sess-1")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["decision"] == "block"
    assert detail["reason_code"] == "PERMISSION_DENIED"
    assert detail["technical_context"]["operation"] == "memory.clear_session"


def test_knowledge_mutation_endpoints_blocked(monkeypatch):
    app = FastAPI()
    app.include_router(knowledge_routes.router)
    client = TestClient(app)

    lessons_store = MagicMock()
    knowledge_routes.set_dependencies(lessons_store=lessons_store)
    monkeypatch.setattr(knowledge_routes, "ensure_data_mutation_allowed", _blocked)

    resp = client.delete("/api/v1/lessons/prune/latest?count=1")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["decision"] == "block"
    assert detail["reason_code"] == "PERMISSION_DENIED"
    assert detail["technical_context"]["operation"] == "knowledge.lessons.prune_latest"

    resp = client.delete("/api/v1/lessons/prune/ttl?days=3")
    assert resp.status_code == 403

    resp = client.post("/api/v1/lessons/dedupe")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["decision"] == "block"
    assert detail["reason_code"] == "PERMISSION_DENIED"
    assert detail["technical_context"]["operation"] == "knowledge.lessons.dedupe"


def test_knowledge_mutation_success_publishes_audit(monkeypatch):
    app = FastAPI()
    app.include_router(knowledge_routes.router)
    client = TestClient(app)

    lessons_store = MagicMock()
    lessons_store.delete_last_n.return_value = 2
    knowledge_routes.set_dependencies(lessons_store=lessons_store)
    monkeypatch.setattr(
        knowledge_routes, "ensure_data_mutation_allowed", lambda _op: None
    )

    audit_stream = MagicMock()
    monkeypatch.setattr(knowledge_routes, "get_audit_stream", lambda: audit_stream)

    resp = client.delete("/api/v1/lessons/prune/latest?count=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mutation"]["action"] == "prune_latest"

    audit_stream.publish.assert_called_once()
    call = audit_stream.publish.call_args.kwargs
    assert call["source"] == "knowledge.lessons"
    assert call["action"] == "mutation.applied"
    assert call["status"] == "success"
    assert call["context"] == "knowledge.lessons.prune_latest"
    assert call["details"]["mutation"]["action"] == "prune_latest"
    assert call["details"]["mutation"]["source"] == "lesson"
    assert call["details"]["deleted"] == 2


def test_governance_reset_usage_blocked(monkeypatch):
    app = FastAPI()
    app.include_router(governance_routes.router)
    client = TestClient(app)

    monkeypatch.setattr(governance_routes, "ensure_data_mutation_allowed", _blocked)
    resp = client.post("/api/v1/governance/reset-usage")
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["decision"] == "block"
    assert detail["reason_code"] == "PERMISSION_DENIED"
    assert detail["technical_context"]["operation"] == "governance.reset_usage"
