"""Endpointy katalogu modeli (registry list/trending/news)."""

import asyncio
import importlib
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query

from venom_core.api.routes.models_dependencies import get_model_registry
from venom_core.config import SETTINGS
from venom_core.core.model_registry import ModelProvider
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _get_translation_service():
    models_module = importlib.import_module("venom_core.api.routes.models")
    return models_module.translation_service


SUPPORTED_NEWS_LANGS = {"pl", "en", "de"}


def _parse_provider(provider: str) -> ModelProvider:
    try:
        return ModelProvider(provider.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Nieprawidłowy provider: {provider}"
        ) from exc


def _parse_target_lang(lang: str) -> str:
    target_lang = (lang or "en").lower()
    if target_lang not in SUPPORTED_NEWS_LANGS:
        raise HTTPException(status_code=400, detail="Obsługiwane języki: pl, en, de")
    return target_lang


def _trim_papers_summaries(items: list[dict], item_type: str) -> None:
    if item_type != "papers" or not items:
        return
    max_summary_chars = SETTINGS.NEWS_SUMMARY_MAX_CHARS
    for item in items:
        summary = item.get("summary")
        if summary and len(summary) > max_summary_chars:
            trimmed = summary[:max_summary_chars].rstrip()
            item["summary"] = f"{trimmed}..."


async def _translate_news_field(
    translator, text: str, target_lang: str, timeout_per_call: float
) -> str:
    if not text:
        return text
    try:
        return await asyncio.wait_for(
            translator.translate_text(
                text,
                target_lang=target_lang,
                source_lang="en",
                allow_fallback=True,
            ),
            timeout=timeout_per_call,
        )
    except Exception:
        return text


async def _translate_news_item(
    translator, item: dict, target_lang: str, timeout_per_call: float
) -> dict:
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    translated_title, translated_summary = await asyncio.gather(
        _translate_news_field(translator, title, target_lang, timeout_per_call),
        _translate_news_field(translator, summary, target_lang, timeout_per_call),
    )
    translated_item = dict(item)
    translated_item["title"] = translated_title
    translated_item["summary"] = translated_summary
    return translated_item


async def _translate_news_items(
    items: list[dict], target_lang: str
) -> tuple[list[dict], str | None]:
    if target_lang == "en" or not items:
        return items, None

    translator = _get_translation_service()
    if translator is None:
        return items, "translator_unavailable"

    try:
        timeout_per_call = max(SETTINGS.TRANSLATION_TIMEOUT_NEWS, 0.5)
        translated_items = await asyncio.gather(
            *(
                _translate_news_item(translator, item, target_lang, timeout_per_call)
                for item in items
            )
        )
        return translated_items, None
    except Exception as exc:
        logger.warning(f"Nie udało się przetłumaczyć newsów: {exc}")
        return items, str(exc)


def _merge_news_errors(
    base_error: str | None, translation_error: str | None
) -> str | None:
    if not translation_error:
        return base_error
    if base_error:
        return f"{base_error}; translation: {translation_error}"
    return f"translation: {translation_error}"


router = APIRouter(prefix="/api/v1", tags=["models"])
MODEL_REGISTRY_UNAVAILABLE_DETAIL = "ModelRegistry nie jest dostępny"


@router.get(
    "/models/providers",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowy provider"},
        500: {"description": "Błąd serwera podczas pobierania listy modeli providerów"},
    },
)
async def list_model_providers(provider: Optional[str] = None, limit: int = 20):
    """
    Lista dostępnych modeli ze wszystkich providerów.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = None
        if provider:
            try:
                provider_enum = ModelProvider(provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Nieprawidłowy provider: {provider}"
                )

        providers_to_query = (
            [provider_enum]
            if provider_enum
            else [ModelProvider.OLLAMA, ModelProvider.HUGGINGFACE]
        )

        all_models: List[dict] = []
        stale = False
        errors: List[str] = []

        for prov in providers_to_query:
            result = await model_registry.list_catalog_models(prov, limit=limit)
            all_models.extend(result.get("models", []))
            stale = stale or bool(result.get("stale"))
            if result.get("error"):
                errors.append(result["error"])

        return {
            "success": True,
            "models": all_models,
            "count": len(all_models),
            "stale": stale,
            "error": "; ".join(errors) if errors else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas listowania providerów: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get(
    "/models/trending",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowy provider"},
        500: {"description": "Błąd serwera podczas pobierania trendujących modeli"},
    },
)
async def list_trending_models(provider: str, limit: int = 12):
    """
    Lista trendujących modeli z zewnętrznych providerów.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        try:
            provider_enum = ModelProvider(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Nieprawidłowy provider: {provider}"
            )

        result = await model_registry.list_trending_models(
            provider=provider_enum, limit=limit
        )
        models = result.get("models", [])

        return {
            "success": True,
            "provider": provider_enum.value,
            "models": models,
            "count": len(models),
            "stale": bool(result.get("stale")),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas listowania trendów: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get(
    "/models/search",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowy provider lub parametry wyszukiwania"},
        500: {"description": "Błąd serwera podczas wyszukiwania modeli"},
    },
)
async def search_models(
    query: Annotated[str, Query(min_length=2)],
    provider: str = "huggingface",
    limit: int = 10,
    page: int = 1,
):
    """
    Wyszukuje modele w zewnętrznych repozytoriach.
    Supports pagination via page parameter.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        try:
            provider_enum = ModelProvider(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Nieprawidłowy provider: {provider}"
            )

        result = await model_registry.search_external_models(
            provider=provider_enum, query=query, limit=limit * page
        )
        models = result.get("models", [])

        # Apply pagination in memory
        # Note: This fetches (limit * page) models to implement pagination
        # A future optimization would be to add native pagination support to model_registry
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_models = models[start_idx:end_idx]

        return {
            "success": True,
            "provider": provider_enum.value,
            "query": query,
            "models": paginated_models,
            "count": len(paginated_models),
            "total": len(models),
            "page": page,
            "limit": limit,
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas wyszukiwania modeli: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get(
    "/models/news",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowy provider lub język docelowy"},
        500: {"description": "Błąd serwera podczas pobierania newsów modeli"},
    },
)
async def list_model_news(
    provider: str = "huggingface",
    limit: int = 5,
    type: str = "blog",
    month: str = "",
    lang: str = "en",
):
    """
    Lista newsów dla providerów (obecnie tylko HuggingFace).
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        provider_enum = _parse_provider(provider)

        result = await model_registry.list_news(
            provider=provider_enum,
            limit=limit,
            kind=type,
            month=month or None,
        )
        items = result.get("items", [])
        target_lang = _parse_target_lang(lang)

        _trim_papers_summaries(items, item_type=type)
        items, translation_error = await _translate_news_items(items, target_lang)
        error_message = _merge_news_errors(result.get("error"), translation_error)

        return {
            "success": True,
            "provider": provider_enum.value,
            "items": items,
            "count": len(items),
            "stale": bool(result.get("stale")),
            "error": error_message,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas listowania newsów: {exc}")
        return {
            "success": False,
            "provider": provider,
            "items": [],
            "count": 0,
            "stale": True,
            "error": str(exc),
        }
