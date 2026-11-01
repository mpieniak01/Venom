"""Read-only runtime observations, separate from installed filesystem payloads."""

from pathlib import Path


async def observe_runtime_models(provider: str, endpoint: str, client) -> dict:
    """Metadata GET only: never start, warm up or generate with a model."""
    from urllib.parse import urlsplit, urlunsplit

    import httpx

    result = {"status": "unverified", "models": None}
    parsed = urlsplit(endpoint)
    if parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    } or parsed.scheme not in {"http", "https"}:
        return result
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    try:
        if provider == "onnx":
            health = await client.get(origin + "/health")
            payload = health.json()
            if (
                health.status_code != 200
                or payload.get("engine") != "onnx-gpu"
                or payload.get("status") != "ok"
            ):
                return result
        response = await client.get(
            origin + ("/api/ps" if provider == "ollama" else "/v1/models")
        )
        if response.status_code != 200:
            return result
        payload = response.json()
        items = payload["models" if provider == "ollama" else "data"]
        if not isinstance(items, list):
            return result
        names = [item["name" if provider == "ollama" else "id"] for item in items]
        if not all(isinstance(name, str) and name for name in names):
            return result
        return {"status": "online", "models": names}
    except httpx.ConnectError:
        return {"status": "offline", "models": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return result


async def runtime_inventory(endpoints: dict[str, str]) -> dict:
    import asyncio
    from datetime import datetime, timezone

    import httpx

    async with httpx.AsyncClient(
        timeout=1.5, follow_redirects=False, trust_env=False
    ) as client:
        values = await asyncio.gather(
            *(
                observe_runtime_models(provider, url, client)
                for provider, url in endpoints.items()
            )
        )
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        provider: {**value, "checked_at": checked_at}
        for provider, value in zip(endpoints, values)
    }


def annotate_runtime_models(
    models: list[dict], observations: dict, selected_provider: str, selected_name: str
) -> None:
    for model in models:
        provider = model.get("provider")
        names = {model.get("name"), model.get("path")}
        names.update(Path(name).name for name in list(names) if isinstance(name, str))
        observation = observations.get(
            provider, {"status": "unverified", "models": None}
        )
        loaded_names = observation["models"]
        loaded = (
            None
            if loaded_names is None
            else any(name in names or Path(name).name in names for name in loaded_names)
        )
        model.update(
            installed=True,
            loaded=loaded,
            active=loaded is True,
            selected=provider == selected_provider
            and (selected_name in names or Path(selected_name).name in names),
            runtime_status=observation["status"],
        )
