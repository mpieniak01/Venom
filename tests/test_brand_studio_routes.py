from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes.brand_studio import router
from venom_core.config import SETTINGS
from venom_core.services.brand_studio_loader import reset_brand_studio_provider_cache


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_brand_studio_feature_disabled_returns_404(monkeypatch):
    client = _client()
    monkeypatch.setattr(SETTINGS, "FEATURE_BRAND_STUDIO", False, raising=False)
    monkeypatch.setattr(SETTINGS, "BRAND_STUDIO_MODE", "stub", raising=False)
    reset_brand_studio_provider_cache()

    response = client.get("/api/v1/brand-studio/sources/candidates")
    assert response.status_code == 404


def test_brand_studio_user_allowlist(monkeypatch):
    client = _client()
    monkeypatch.setattr(SETTINGS, "FEATURE_BRAND_STUDIO", True, raising=False)
    monkeypatch.setattr(SETTINGS, "BRAND_STUDIO_MODE", "stub", raising=False)
    monkeypatch.setattr(SETTINGS, "BRAND_STUDIO_ALLOWED_USERS", "alice", raising=False)
    reset_brand_studio_provider_cache()

    response = client.get(
        "/api/v1/brand-studio/sources/candidates", headers={"X-User": "bob"}
    )
    assert response.status_code == 403


def test_brand_studio_stub_happy_path(monkeypatch):
    client = _client()
    monkeypatch.setattr(SETTINGS, "FEATURE_BRAND_STUDIO", True, raising=False)
    monkeypatch.setattr(SETTINGS, "BRAND_STUDIO_MODE", "stub", raising=False)
    monkeypatch.setattr(SETTINGS, "BRAND_STUDIO_ALLOWED_USERS", "", raising=False)
    reset_brand_studio_provider_cache()

    candidates = client.get(
        "/api/v1/brand-studio/sources/candidates", headers={"X-User": "alice"}
    )
    assert candidates.status_code == 200
    candidate_id = candidates.json()["items"][0]["id"]

    draft = client.post(
        "/api/v1/brand-studio/drafts/generate",
        headers={"X-User": "alice"},
        json={
            "candidate_id": candidate_id,
            "channels": ["x"],
            "languages": ["pl", "en"],
            "tone": "direct",
        },
    )
    assert draft.status_code == 200
    draft_id = draft.json()["id"]

    queue = client.post(
        f"/api/v1/brand-studio/drafts/{draft_id}/queue",
        headers={"X-User": "alice"},
        json={
            "target_channel": "x",
            "target_repo": "owner/repo",
            "target_path": "content/post.md",
        },
    )
    assert queue.status_code == 200
    item_id = queue.json()["id"]

    publish_without_confirm = client.post(
        f"/api/v1/brand-studio/queue/{item_id}/publish",
        headers={"X-User": "alice"},
        json={"confirm_publish": False},
    )
    assert publish_without_confirm.status_code == 400

    publish = client.post(
        f"/api/v1/brand-studio/queue/{item_id}/publish",
        headers={"X-User": "alice"},
        json={"confirm_publish": True},
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    queue_state = client.get("/api/v1/brand-studio/queue", headers={"X-User": "alice"})
    assert queue_state.status_code == 200
    assert queue_state.json()["items"][0]["status"] == "published"

    audit = client.get("/api/v1/brand-studio/audit", headers={"X-User": "alice"})
    assert audit.status_code == 200
    assert len(audit.json()["items"]) >= 2
