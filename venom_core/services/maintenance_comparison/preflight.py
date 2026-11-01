"""Read-only local LLM preflight under a host-issued exclusive lease."""

import httpx

from venom_core.services.model_resources import resource_snapshot
from venom_core.services.runtime_release_service import _listening


async def require_local_llms_empty(controller) -> None:
    if controller is None:
        raise ValueError("maintenance_controller_unavailable")
    if any(
        resource["category"] in {"llm", "local_llm"} for resource in resource_snapshot()
    ):
        raise ValueError("maintenance_local_llm_still_loaded")
    for server in controller.list_servers():
        name = server["name"]
        if name not in {"ollama", "multi_runtime", "vllm", "onnx"}:
            continue
        endpoint = server["endpoint"]
        if not endpoint:
            continue  # An unconfigured optional engine has no worker endpoint.
        try:
            listening = await _listening(endpoint)
        except (ValueError, OSError, TimeoutError) as exc:
            raise ValueError("maintenance_local_llm_runtime_unverified") from exc
        if not listening:
            continue
        if name != "ollama":
            raise ValueError("maintenance_local_llm_runtime_running")
        await _require_ollama_empty(endpoint)


async def _require_ollama_empty(endpoint: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(
                endpoint.rstrip("/").removesuffix("/v1") + "/api/ps"
            )
            response.raise_for_status()
            models = response.json()["models"]
            if not isinstance(models, list):
                raise ValueError("runtime_models_not_list")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("maintenance_local_llm_runtime_unverified") from exc
    if models:
        raise ValueError("maintenance_local_llm_still_loaded")
