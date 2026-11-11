"""Ollama runtime policy helpers.

Enforces the invariant: at most one loaded Ollama model at a time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from venom_core.services.runtime_admission import admitted_operation

_UNLOAD_VERIFY_TIMEOUT_SECONDS = 5.0
_UNLOAD_VERIFY_INTERVAL_SECONDS = 0.1


def _resolve_ollama_base_url(endpoint: str | None) -> str:
    value = str(endpoint or "").strip()
    if not value:
        return "http://localhost:11434"
    value = value.rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3].rstrip("/")
    return value or "http://localhost:11434"


def _extract_loaded_model_names(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    loaded: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            loaded.append(name)
    return loaded


@admitted_operation("ollama_unload", mutation=True)
async def enforce_single_loaded_ollama_model(
    *, endpoint: str | None, selected_model: str | None
) -> dict[str, Any]:
    """Unload all loaded Ollama models except selected_model.

    Returns summary payload for diagnostics/testing.
    Raises RuntimeError if Ollama API calls fail.
    """

    base = _resolve_ollama_base_url(endpoint)
    keep_model = str(selected_model or "").strip()
    async with httpx.AsyncClient(timeout=10.0) as client:
        ps_response = await client.get(f"{base}/api/ps")
        if ps_response.status_code >= 400:
            raise RuntimeError(f"ollama /api/ps failed with {ps_response.status_code}")
        before = _extract_loaded_model_names(
            ps_response.json() if ps_response.content else {}
        )
        to_unload = [name for name in before if name != keep_model]
        for model_name in to_unload:
            response = await client.post(
                f"{base}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0,
                },
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ollama unload failed for {model_name} with {response.status_code}"
                )
        # Ollama can acknowledge unload before the runner disappears from /api/ps.
        after = before
        try:
            async with asyncio.timeout(_UNLOAD_VERIFY_TIMEOUT_SECONDS):
                while True:
                    verify_response = await client.get(f"{base}/api/ps")
                    if verify_response.status_code >= 400:
                        raise RuntimeError(
                            f"ollama /api/ps verify failed with {verify_response.status_code}"
                        )
                    after = _extract_loaded_model_names(
                        verify_response.json() if verify_response.content else {}
                    )
                    if all(name == keep_model for name in after):
                        break
                    await asyncio.sleep(_UNLOAD_VERIFY_INTERVAL_SECONDS)
        except TimeoutError as exc:
            raise RuntimeError(
                "ollama single-model policy verification timed out: "
                f"keep={keep_model or 'none'} loaded={after}"
            ) from exc
    return {
        "base_url": base,
        "keep_model": keep_model,
        "before": before,
        "unloaded": to_unload,
        "after": after,
    }
