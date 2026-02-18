"""Module Example API (modular, extension-ready)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from venom_core.api.schemas.module_example import (
    AuditResponse,
    CandidatesResponse,
    DraftBundle,
    GenerateDraftsRequest,
    PublishQueueItem,
    PublishQueueRequest,
    PublishResult,
    QueueDraftRequest,
    QueueResponse,
)
from venom_core.config import SETTINGS
from venom_core.services.module_example_loader import (
    ModuleExampleProvider,
    get_module_example_provider,
)

router = APIRouter(prefix="/api/v1/module-example", tags=["module-example"])


def _extract_actor(
    x_authenticated_user: str | None,
    x_user: str | None,
    x_admin_user: str | None,
) -> str:
    for candidate in (x_authenticated_user, x_user, x_admin_user):
        if candidate:
            return candidate
    return "unknown"


def _assert_allowed(actor: str) -> None:
    raw = (SETTINGS.MODULE_EXAMPLE_ALLOWED_USERS or "").strip()
    if not raw:
        return
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    if actor not in allowed:
        raise HTTPException(status_code=403, detail="Access denied for this user")


def _resolve_provider(
    actor: str,
) -> ModuleExampleProvider:
    if not SETTINGS.FEATURE_MODULE_EXAMPLE:
        raise HTTPException(status_code=404, detail="Module Example feature disabled")
    _assert_allowed(actor)
    provider = get_module_example_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="Module Example mode is disabled")
    return provider


def get_actor(
    x_authenticated_user: str | None = Header(default=None),
    x_user: str | None = Header(default=None),
    x_admin_user: str | None = Header(default=None),
) -> str:
    return _extract_actor(x_authenticated_user, x_user, x_admin_user)


def get_provider(actor: str = Depends(get_actor)) -> ModuleExampleProvider:
    return _resolve_provider(actor)


@router.get("/sources/candidates", response_model=CandidatesResponse)
async def list_candidates(
    channel: str | None = Query(default=None),
    lang: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    provider: ModuleExampleProvider = Depends(get_provider),
) -> CandidatesResponse:
    items = provider.list_candidates(
        channel=channel,
        language=lang,
        limit=limit,
        min_score=min_score,
    )
    return CandidatesResponse(items=items)


@router.post("/drafts/generate", response_model=DraftBundle)
async def generate_drafts(
    payload: GenerateDraftsRequest,
    provider: ModuleExampleProvider = Depends(get_provider),
) -> DraftBundle:
    return provider.generate_drafts(
        candidate_id=payload.candidate_id,
        channels=payload.channels,
        languages=payload.languages,
        tone=payload.tone,
    )


@router.post("/drafts/{draft_id}/queue", response_model=PublishQueueItem)
async def queue_draft(
    draft_id: str,
    payload: QueueDraftRequest,
    provider: ModuleExampleProvider = Depends(get_provider),
) -> PublishQueueItem:
    try:
        return provider.queue_draft(
            draft_id=draft_id,
            target_channel=payload.target_channel,
            target_repo=payload.target_repo,
            target_path=payload.target_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/queue/{item_id}/publish", response_model=PublishResult)
async def publish_queue_item(
    item_id: str,
    payload: PublishQueueRequest,
    actor: str = Depends(get_actor),
    provider: ModuleExampleProvider = Depends(get_provider),
) -> PublishResult:
    try:
        return provider.publish(
            item_id=item_id,
            actor=actor,
            confirm_publish=payload.confirm_publish,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/queue", response_model=QueueResponse)
async def list_queue(
    provider: ModuleExampleProvider = Depends(get_provider),
) -> QueueResponse:
    return QueueResponse(items=provider.list_queue())


@router.get("/audit", response_model=AuditResponse)
async def list_audit(
    provider: ModuleExampleProvider = Depends(get_provider),
) -> AuditResponse:
    return AuditResponse(items=provider.list_audit())
