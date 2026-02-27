"""Logika katalogu/trending/news/search dla ModelRegistry."""

import time
from typing import Any, Dict, List, Optional

from venom_core.core.model_registry_types import ModelProvider
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def list_trending_models(
    registry: Any, provider: ModelProvider, limit: int = 12
) -> Dict[str, Any]:
    """Lista trendujących modeli z zewnętrznych źródeł."""
    return await _list_external_models(registry, provider, limit, mode="trending")


async def list_catalog_models(
    registry: Any, provider: ModelProvider, limit: int = 20
) -> Dict[str, Any]:
    """Lista dostępnych modeli z zewnętrznych źródeł."""
    return await _list_external_models(registry, provider, limit, mode="catalog")


async def list_news(
    registry: Any,
    provider: ModelProvider,
    limit: int = 5,
    kind: str = "blog",
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """Lista newsów dla danego providera."""
    if provider != ModelProvider.HUGGINGFACE:
        return {"items": [], "stale": False, "error": None}
    try:
        if kind == "papers":
            items = await _fetch_hf_papers_month(registry, limit=limit, month=month)
        else:
            items = await _fetch_hf_blog_feed(registry, limit=limit)
        return {"items": items, "stale": False, "error": None}
    except Exception as e:
        logger.warning(f"Nie udało się pobrać newsów HF: {e}")
        return {"items": [], "stale": True, "error": str(e)}


async def search_external_models(
    registry: Any, provider: ModelProvider, query: str, limit: int = 20
) -> Dict[str, Any]:
    """Przeszukuje modele u zewnętrznego providera."""
    try:
        if not query or len(query) < 2:
            return {"models": [], "count": 0}

        if provider == ModelProvider.HUGGINGFACE:
            models = await registry.hf_client.search_models(query, limit)
            formatted = []
            for item in models:
                model_id = item.get("modelId") or item.get("id")
                if not model_id:
                    continue
                entry = _format_catalog_entry(
                    provider=ModelProvider.HUGGINGFACE,
                    model_name=model_id,
                    display_name=model_id.split("/")[-1],
                    runtime="vllm",
                    size_gb=None,
                    tags=item.get("tags"),
                    downloads=item.get("downloads"),
                    likes=item.get("likes"),
                )
                entry["description"] = None
                formatted.append(entry)
            return {"models": formatted, "count": len(formatted)}

        if provider == ModelProvider.OLLAMA:
            raw_models = await registry.ollama_catalog_client.search_models(
                query, limit
            )
            formatted = []
            for item in raw_models:
                entry = _format_catalog_entry(
                    provider=ModelProvider.OLLAMA,
                    model_name=item["name"],
                    display_name=item["name"],
                    runtime="ollama",
                    size_gb=None,
                    tags=[],
                    downloads=None,
                    likes=None,
                )
                entry["description"] = item.get("description")
                formatted.append(entry)
            return {"models": formatted, "count": len(formatted)}

        return {"models": [], "count": 0}
    except Exception as e:
        logger.error(f"Search failed for {provider}: {e}")
        return {"models": [], "count": 0, "error": str(e)}


async def _list_external_models(
    registry: Any, provider: ModelProvider, limit: int, mode: str
) -> Dict[str, Any]:
    cache_key = f"{provider.value}:{mode}:{limit}"
    cached = registry._external_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["timestamp"] < registry._external_cache_ttl_seconds:
        return {"models": cached["data"], "stale": False, "error": None}

    try:
        if provider == ModelProvider.HUGGINGFACE:
            sort = "trendingScore" if mode == "trending" else "downloads"
            models = await _fetch_huggingface_models(registry, sort=sort, limit=limit)
        elif provider == ModelProvider.OLLAMA:
            models = await _fetch_ollama_models(registry, limit=limit)
        else:
            models = []
        registry._external_cache[cache_key] = {
            "timestamp": now,
            "data": models,
        }
        return {"models": models, "stale": False, "error": None}
    except Exception as e:
        logger.warning(f"Nie udało się pobrać listy {mode} dla {provider}: {e}")
        if cached:
            return {"models": cached["data"], "stale": True, "error": str(e)}
        return {"models": [], "stale": True, "error": str(e)}


async def _fetch_huggingface_models(
    registry: Any, sort: str, limit: int
) -> List[Dict[str, Any]]:
    payload = await registry.hf_client.list_models(sort=sort, limit=limit)
    if not isinstance(payload, list):
        return []

    models: List[Dict[str, Any]] = []
    for item in payload:
        model_id = item.get("modelId") or item.get("id")
        if not model_id:
            continue
        display = model_id.split("/")[-1]
        models.append(
            _format_catalog_entry(
                provider=ModelProvider.HUGGINGFACE,
                model_name=model_id,
                display_name=display,
                runtime="vllm",
                size_gb=None,
                tags=item.get("tags") or [],
                downloads=item.get("downloads"),
                likes=item.get("likes"),
            )
        )
    return models


async def _fetch_ollama_models(registry: Any, limit: int) -> List[Dict[str, Any]]:
    payload = await registry.ollama_catalog_client.list_tags()
    models: List[Dict[str, Any]] = []
    for item in payload.get("models", [])[:limit]:
        name = item.get("name")
        if not name:
            continue
        details = item.get("details") or {}
        tags = [
            value
            for value in [
                details.get("family"),
                details.get("parameter_size"),
                details.get("quantization_level"),
                details.get("format"),
            ]
            if value
        ]
        size_bytes = item.get("size")
        if isinstance(size_bytes, (int, float)):
            size_gb = round(size_bytes / (1024**3), 2)
        else:
            size_gb = None
        models.append(
            _format_catalog_entry(
                provider=ModelProvider.OLLAMA,
                model_name=name,
                display_name=name,
                runtime="ollama",
                size_gb=size_gb,
                tags=tags,
                downloads=None,
                likes=None,
            )
        )
    return models


async def _fetch_hf_blog_feed(registry: Any, limit: int) -> List[Dict[str, Any]]:
    return await registry.hf_client.fetch_blog_feed(limit=limit)


async def _fetch_hf_papers_month(
    registry: Any, limit: int, month: Optional[str] = None
) -> List[Dict[str, Any]]:
    return await registry.hf_client.fetch_papers_month(limit=limit, month=month)


def _format_catalog_entry(
    provider: ModelProvider,
    model_name: str,
    display_name: str,
    runtime: str,
    size_gb: Optional[float] = None,
    tags: Optional[List[str]] = None,
    downloads: Optional[int] = None,
    likes: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "provider": provider.value,
        "model_name": model_name,
        "display_name": display_name,
        "size_gb": size_gb,
        "runtime": runtime,
        "tags": tags or [],
        "downloads": downloads,
        "likes": likes,
    }
