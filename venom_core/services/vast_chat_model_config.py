"""Generation settings and metadata scoped to the remote target, never local manifests."""

import math

from fastapi import HTTPException

from venom_core.services import vast_chat_runtime as remote


def scope(runtime: str | None) -> str | None:
    selected = remote.selection()
    requested = str(runtime or "").strip().lower()
    if requested != remote.SERVER and not (not requested and selected is not None):
        return None
    state = remote.connection().status(refresh=False)
    target = state.get("target_id")
    if not target:
        raise HTTPException(status_code=503, detail="vast_chat_target_unavailable")
    return remote.SERVER + "@" + target


def require_model(name: str) -> None:
    state = remote.connection().status(refresh=True)
    if not state.get("available"):
        raise HTTPException(status_code=503, detail="vast_chat_target_unavailable")
    if not any(row["name"] == name for row in state.get("models", [])):
        raise HTTPException(status_code=404, detail="vast_chat_model_unavailable")


def generation_schema(name: str):
    from venom_core.core.model_registry import create_default_generation_schema

    require_model(name)
    schema = create_default_generation_schema()
    parameters = remote.connection().model_details(name).get("parameters", "")
    if isinstance(parameters, str):
        mapping = {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "repeat_penalty": "repeat_penalty",
            "num_predict": "max_tokens",
        }
        for line in parameters.splitlines()[:64]:
            parts = line.split()
            if len(parts) != 2 or parts[0] not in mapping:
                continue
            spec = schema[mapping[parts[0]]]
            try:
                value = float(parts[1])
            except ValueError:
                continue
            if (
                not math.isfinite(value)
                or (spec.min is not None and value < spec.min)
                or (spec.max is not None and value > spec.max)
                or (spec.type == "int" and not value.is_integer())
            ):
                continue
            spec.default = int(value) if spec.type == "int" else value
    return schema


def capabilities(name: str) -> dict:
    from venom_core.core.ollama_runtime_capabilities import (
        normalize_ollama_show_payload,
    )

    require_model(name)
    state = remote.connection().status(refresh=False)
    details = remote.connection().model_details(name)
    result = normalize_ollama_show_payload(
        model_name=name,
        payload=details,
        endpoint=state["endpoint"],
        ollama_version=state.get("version"),
    )
    result.runtime_id = str(state["target_id"]) + ":" + str(state["generation"])
    return {
        "success": True,
        "model_name": name,
        "runtime_capabilities": result.to_dict(),
    }
