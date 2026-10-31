"""Session-owned, inert materials for chat turns."""

from typing import Literal

from pydantic import BaseModel


class ChatMaterial(BaseModel):
    id: str
    session_id: str
    name: str
    mime_type: str
    size_bytes: int
    kind: Literal["document", "image"]
    status: Literal["ready"] = "ready"
    created_at: str
    preview_url: str


class ChatMaterialList(BaseModel):
    materials: list[ChatMaterial]
