"""Model introspection snapshot endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.api.schemas.model_introspection import (
    ModelIntrospectionAnalyzeRequest,
    ModelIntrospectionProbeRequest,
)
from venom_core.services.model_introspection_analysis_service import (
    analyze_model_with_optional_live_run,
    stream_model_introspection_analysis,
)
from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)
from venom_core.services.model_introspection_service import (
    build_model_introspection_snapshot,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
_ERROR_INTERNAL_SERVER = "Internal server error"
_ERROR_INVALID_REQUEST_PARAMETERS = "Invalid request parameters"
_SSE_MEDIA_TYPE = "text/event-stream"

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
        raise HTTPException(status_code=500, detail=_ERROR_INTERNAL_SERVER) from exc


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
            top_p=request.top_p,
            model_manager=get_model_manager(),
        )
        return {"success": True, "snapshot": payload}
    except ValueError as exc:
        logger.warning(
            "Nieprawidłowe parametry analizy modelu",
            exc_info=True,
        )
        raise HTTPException(
            status_code=400,
            detail=_ERROR_INVALID_REQUEST_PARAMETERS,
        ) from exc
    except Exception as exc:
        logger.exception("Błąd podczas analizy modelu")
        raise HTTPException(status_code=500, detail=_ERROR_INTERNAL_SERVER) from exc


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
                top_p=request.top_p,
                model_manager=get_model_manager(),
            ),
            media_type=_SSE_MEDIA_TYPE,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except ValueError as exc:
        logger.warning(
            "Nieprawidłowe parametry streamowanej analizy modelu",
            exc_info=True,
        )
        raise HTTPException(
            status_code=400,
            detail=_ERROR_INVALID_REQUEST_PARAMETERS,
        ) from exc
    except Exception as exc:
        logger.exception("Błąd podczas streamowanej analizy modelu")
        raise HTTPException(status_code=500, detail=_ERROR_INTERNAL_SERVER) from exc


@router.post(
    "/introspection/probe",
    responses={
        400: {"description": "Nieprawidłowe parametry probe"},
        500: {"description": "Błąd wewnętrzny podczas wykonania probe"},
    },
)
async def probe_model_introspection(
    request: ModelIntrospectionProbeRequest,
) -> dict[str, object]:
    """Proxy probe request to active multi_runtime endpoint with safe fallback."""
    try:
        probe_payload = await run_model_introspection_probe(
            prompt=request.prompt,
            mode=request.mode,
            layer_selection=request.layer_selection,
            top_k=request.top_k,
        )
        return {
            "success": True,
            "probe": probe_payload,
        }
    except ValueError as exc:
        logger.warning(
            "Nieprawidłowe parametry probe model introspection",
            exc_info=True,
        )
        raise HTTPException(
            status_code=400,
            detail=_ERROR_INVALID_REQUEST_PARAMETERS,
        ) from exc
    except Exception as exc:
        logger.exception("Błąd podczas wykonania probe model introspection")
        raise HTTPException(status_code=500, detail=_ERROR_INTERNAL_SERVER) from exc
