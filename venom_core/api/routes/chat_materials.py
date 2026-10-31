"""Inert material upload/preview API; no prefetch reaches a model provider."""

import asyncio
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from venom_core.api.schemas.chat_materials import ChatMaterial, ChatMaterialList
from venom_core.api.transport_access import require_operator_request
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.chat_materials import MAX_BYTES, MaterialStore

router = APIRouter(
    prefix="/api/v1/chat/materials",
    tags=["chat-materials"],
    dependencies=[Depends(require_operator_request)],
)


def _same_origin(request: Request) -> None:
    try:
        ensure_data_mutation_allowed("chat_materials")
    except PermissionError as exc:
        raise HTTPException(
            403, {"reason_code": "material_environment_read_only"}
        ) from exc
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {
            "http",
            "https",
        } or parsed.netloc != request.headers.get("host"):
            # Next's same-origin proxy retains the browser Origin but has a
            # loopback API Host. Both origins must remain explicitly loopback.
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname
                not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }
                or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
            ):
                raise HTTPException(403, {"reason_code": "material_origin_denied"})


@router.post("", response_model=ChatMaterial, dependencies=[Depends(_same_origin)])
async def upload_material(
    request: Request,
    session_id: str = Query(min_length=1, max_length=256),
    name: str = Query(min_length=1, max_length=180),
):
    declared = request.headers.get("content-length", "")
    if declared.isdecimal() and int(declared) > MAX_BYTES:
        raise HTTPException(413, {"reason_code": "material_too_large"})
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, {"reason_code": "material_too_large"})
        chunks.extend(chunk)
    return await asyncio.to_thread(
        MaterialStore().save,
        session_id,
        name,
        request.headers.get("content-type", ""),
        bytes(chunks),
    )


@router.get("", response_model=ChatMaterialList)
async def list_materials(session_id: str = Query(min_length=1, max_length=256)):
    return ChatMaterialList(
        materials=await asyncio.to_thread(MaterialStore().list, session_id)
    )


@router.get("/capabilities")
async def material_capabilities(
    model: str | None = Query(default=None, max_length=1024),
):
    from venom_core.services.chat_material_payload import image_capability
    from venom_core.utils.llm_runtime import get_active_llm_runtime

    runtime = get_active_llm_runtime()
    selected = model or runtime.model_name or ""
    return {
        "document": True,
        "image": await image_capability(runtime, selected),
        "audio": False,
        "video": False,
        "max_bytes": MAX_BYTES,
        "max_document_chars": 64000,
        "runtime_id": runtime.runtime_id,
        "config_hash": runtime.config_hash,
        "model": selected,
    }


@router.get("/{material_id}", response_model=ChatMaterial)
async def get_material(
    material_id: str, session_id: str = Query(min_length=1, max_length=256)
):
    return await asyncio.to_thread(MaterialStore().get, session_id, material_id)


@router.get("/{material_id}/content")
async def preview_material(
    material_id: str, session_id: str = Query(min_length=1, max_length=256)
):
    material, content = await asyncio.to_thread(
        MaterialStore().read, session_id, material_id
    )
    return Response(
        content,
        media_type=material.mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{material_id}", status_code=204, dependencies=[Depends(_same_origin)])
async def delete_material(
    material_id: str, session_id: str = Query(min_length=1, max_length=256)
):
    await asyncio.to_thread(MaterialStore().delete, session_id, material_id)
    return Response(status_code=204)
