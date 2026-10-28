"""Generation settings and metadata scoped to the remote target, never local manifests."""

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
    return create_default_generation_schema()


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
