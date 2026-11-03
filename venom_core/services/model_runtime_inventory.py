"""Read-only runtime observations, separate from installed filesystem payloads."""

from pathlib import Path


async def observe_runtime_models(provider: str, endpoint: str, client) -> dict:
    """Metadata GET only: never start, warm up or generate with a model."""
    from urllib.parse import urlsplit, urlunsplit

    import httpx

    result = {"status": "unverified", "models": None}
    try:
        parsed = urlsplit(endpoint)
        if parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        } or parsed.scheme not in {"http", "https"}:
            return result
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
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
    """Observe configured local runtimes through metadata GET requests without generating text."""
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


def _matching_model_indexes(models: list[dict], name: str) -> set[int]:
    """Prefer exact IDs and paths, accepting short aliases only when unambiguous per engine."""
    if not isinstance(name, str) or not name:
        return set()

    def identifiers(model: dict) -> set[str]:
        """Collect installation names and real paths, excluding registry URI pseudo-paths."""
        values = {model.get("name")}
        if model.get("provider") == "ollama":
            values.update(model.get("aliases", []))
        path = model.get("path")
        if isinstance(path, str) and not path.startswith("ollama://"):
            values.add(path)
        return {value for value in values if isinstance(value, str) and value}

    exact = {i for i, model in enumerate(models) if name in identifiers(model)}
    if exact or "/" in name or "\\" in name:
        return exact
    return {
        i
        for i, model in enumerate(models)
        if any(Path(value).name == name for value in identifiers(model))
    }


def _loaded_states(models: list[dict], names: list[str] | None) -> list[bool | None]:
    """Map observed names to loaded states, preserving ambiguity as unknown."""
    if names is None:
        return [None] * len(models)
    confirmed: set[int] = set()
    ambiguous: set[int] = set()
    for name in names:
        matches = _matching_model_indexes(models, name)
        if len(matches) == 1:
            confirmed.update(matches)
        else:
            ambiguous.update(matches)
    states: list[bool | None] = [False] * len(models)
    for i in ambiguous:
        states[i] = None
    for i in confirmed:
        states[i] = True
    return states


def annotate_runtime_models(
    models: list[dict], observations: dict, selected_provider: str, selected_name: str
) -> None:
    """Annotate installation, selection and observed loading independently for each engine."""
    providers = {model.get("provider") for model in models}
    for provider in providers:
        entries = [model for model in models if model.get("provider") == provider]
        observation = observations.get(
            provider, {"status": "unverified", "models": None}
        )
        selected = (
            _matching_model_indexes(entries, selected_name)
            if provider == selected_provider
            else set()
        )
        for i, (model, loaded) in enumerate(
            zip(entries, _loaded_states(entries, observation["models"]))
        ):
            model.update(
                installed=True,
                loaded=loaded,
                active=loaded is True,
                selected=len(selected) == 1 and i in selected,
                runtime_status=observation["status"],
            )
