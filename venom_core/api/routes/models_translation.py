"""Endpointy tlumaczen powiazane z modelami."""

import importlib

from fastapi import APIRouter, HTTPException

from venom_core.api.model_schemas.model_requests import TranslationRequest
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _get_translation_service():
    models_module = importlib.import_module("venom_core.api.routes.models")
    return models_module.translation_service


router = APIRouter(prefix="/api/v1", tags=["models"])


@router.post("/translate")
async def translate_text_endpoint(request: TranslationRequest):
    """Uniwersalny endpoint do tlumaczenia tresci z uzyciem aktywnego modelu."""
    try:
        if request.target_lang not in ["pl", "en", "de"]:
            raise HTTPException(
                status_code=400, detail="Obsługiwane języki: pl, en, de"
            )
        translated = await _get_translation_service().translate_text(
            request.text,
            target_lang=request.target_lang,
            source_lang=request.source_lang,
            use_cache=request.use_cache,
            allow_fallback=False,
        )
        return {
            "success": True,
            "translated_text": translated,
            "target_lang": request.target_lang,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Błąd tłumaczenia: {exc}")
        raise HTTPException(status_code=500, detail="Błąd serwera podczas tłumaczenia")
