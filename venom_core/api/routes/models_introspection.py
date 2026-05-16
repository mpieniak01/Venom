"""Model introspection snapshot endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.api.schemas.model_introspection import ModelIntrospectionAnalyzeRequest
from venom_core.services.model_introspection_analysis_service import (
    analyze_model_with_optional_live_run,
    stream_model_introspection_analysis,
)
from venom_core.services.model_introspection_service import (
    build_model_introspection_snapshot,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get(
    "/introspection",
    responses={
        500: {"description": "Błąd wewnętrzny podczas budowania snapshotu modelu"},
    },
)
async def get_model_introspection() -> dict[str, object]:
    """Return a read-only introspection snapshot for the active model/runtime."""
    try:
        snapshot = await build_model_introspection_snapshot(
            model_manager=get_model_manager()
        )
        return {"success": True, "snapshot": snapshot}
    except Exception as exc:
        logger.exception("Błąd podczas budowania snapshotu modelu")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post(
    "/introspection/analyze",
    responses={
        400: {"description": "Nieprawidłowy prompt lub opcje analizy"},
        500: {"description": "Błąd wewnętrzny podczas analizy modelu"},
    },
)
async def analyze_model_introspection(
    request: ModelIntrospectionAnalyzeRequest,
) -> dict[str, object]:
    """Optionally run the active model on a prompt and return the result."""
    try:
        payload = await analyze_model_with_optional_live_run(
            prompt=request.prompt,
            live_analysis_enabled=request.live_analysis_enabled,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            model_manager=get_model_manager(),
        )
        return {"success": True, "snapshot": payload}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Błąd podczas analizy modelu")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post(
    "/introspection/analyze/stream",
    responses={
        400: {"description": "Nieprawidłowy prompt lub opcje analizy"},
        500: {"description": "Błąd wewnętrzny podczas analizy modelu"},
    },
)
async def stream_model_introspection_analysis_endpoint(
    request: ModelIntrospectionAnalyzeRequest,
) -> StreamingResponse:
    """Stream model introspection analysis as SSE for live UI updates."""
    try:
        if not request.prompt.strip():
            raise ValueError("prompt cannot be empty")
        return StreamingResponse(
            stream_model_introspection_analysis(
                prompt=request.prompt,
                live_analysis_enabled=request.live_analysis_enabled,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                model_manager=get_model_manager(),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Błąd podczas streamowanej analizy modelu")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
