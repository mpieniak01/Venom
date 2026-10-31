"""Expand owned references only at send/quote, with truthful adapter capabilities."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from venom_core.api.schemas.llm_simple import HistoryMessage, SimpleChatRequest
from venom_core.core.model_registry_clients import OllamaClient
from venom_core.services.chat_materials import MaterialStore
from venom_core.services.vast_chat_runtime import is_remote

MAX_CONTEXT_BYTES = 16 * 1024 * 1024
MAX_CONTEXT_TEXT = 64000


def has_materials(request: SimpleChatRequest) -> bool:
    return bool(
        request.material_ids or any(turn.material_ids for turn in request.history)
    )


def _expand_turn_materials(
    store: MaterialStore,
    session_id: str,
    turn: HistoryMessage | SimpleChatRequest,
    *,
    allow_images: bool,
    total_bytes: int,
) -> tuple[str, list[dict[str, Any]], int]:
    text = turn.content
    images: list[dict[str, Any]] = []
    for material_id in turn.material_ids:
        material, data = store.read(session_id, material_id)
        total_bytes += len(data)
        if total_bytes > MAX_CONTEXT_BYTES:
            raise HTTPException(413, {"reason_code": "material_context_limit"})
        if material.kind == "document":
            text += f"\n\n[Reference material: {material.name}]\n" + data.decode(
                "utf-8-sig"
            )
        elif allow_images:
            images.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:"
                        + material.mime_type
                        + ";base64,"
                        + base64.b64encode(data).decode("ascii")
                    },
                }
            )
        else:
            raise HTTPException(
                400, {"reason_code": "material_image_adapter_unsupported"}
            )
    return text, images, total_bytes


def material_messages(
    request: SimpleChatRequest, *, allow_images: bool
) -> list[dict[str, Any]]:
    """Resolve references, not paths; an unavailable material fails before inference."""
    if not has_materials(request):
        return [
            *[turn.model_dump(exclude={"material_ids"}) for turn in request.history],
            {"role": "user", "content": request.content},
        ]
    if not request.session_id:
        raise HTTPException(400, {"reason_code": "material_session_required"})
    store = MaterialStore()
    messages = []
    total_bytes, text_chars = 0, 0
    turns: list[HistoryMessage | SimpleChatRequest] = [*request.history, request]
    for turn in turns:
        text, images, total_bytes = _expand_turn_materials(
            store,
            request.session_id,
            turn,
            allow_images=allow_images,
            total_bytes=total_bytes,
        )
        text_chars += len(text)
        if text_chars > MAX_CONTEXT_TEXT or len(text) > 50000:
            raise HTTPException(413, {"reason_code": "material_context_limit"})
        messages.append(
            {
                "role": getattr(turn, "role", "user"),
                "content": [{"type": "text", "text": text}, *images]
                if images
                else text,
            }
        )
    return messages


def text_material_request(request: SimpleChatRequest) -> SimpleChatRequest:
    """Cloud quotes and sends expand the identical bounded text before accounting."""
    if not has_materials(request):
        return request
    messages = material_messages(request, allow_images=False)
    return request.model_copy(
        update={
            "content": messages[-1]["content"],
            "material_ids": [],
            "history": [HistoryMessage.model_validate(turn) for turn in messages[:-1]],
        }
    )


async def image_capability(runtime: Any, model: str) -> bool:
    # Only this adapter has a verified image transport. A model name, an
    # advertised provider family, or cloud text support never grants capability.
    if (
        runtime.provider != "ollama"
        or is_remote(runtime)
        or urlsplit(str(runtime.endpoint)).hostname
        not in {"localhost", "127.0.0.1", "::1"}
    ):
        return False
    payload = await OllamaClient(endpoint=runtime.endpoint).get_model_show(model)
    if payload.get("remote_model") or payload.get("remote_host"):
        return False
    capabilities = payload.get("capabilities")
    return isinstance(capabilities, list) and "vision" in capabilities


async def direct_material_messages(
    request: SimpleChatRequest, runtime: Any, model: str
) -> list[dict[str, Any]]:
    # Keep provider metadata I/O separate from material parsing; unsupported
    # adapters reject an image without sending any content to a provider.
    messages = material_messages(request, allow_images=True)
    if any(isinstance(message["content"], list) for message in messages):
        if not await image_capability(runtime, model):
            raise HTTPException(
                400, {"reason_code": "material_image_adapter_unsupported"}
            )
    return messages
