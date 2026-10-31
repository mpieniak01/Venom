"""Bounded, environment/session-scoped storage; materials are never executed."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, NoReturn
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import HTTPException

from venom_core.api.schemas.chat_materials import ChatMaterial
from venom_core.utils.logger import get_logger
from venom_core.utils.runtime_state import runtime_state_root

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 64000
MAX_SESSION_BYTES = 64 * 1024 * 1024
MAX_SESSION_FILES = 32
DOCUMENT_TYPES = frozenset(
    {"text/plain", "text/markdown", "text/csv", "application/json"}
)
IMAGE_TYPES = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
_LOCK = threading.RLock()
logger = get_logger(__name__)


def _invalid(reason: str, status: int = 400) -> NoReturn:
    raise HTTPException(status, {"reason_code": reason})


def validate_session(session_id: str) -> str:
    if not session_id or len(session_id) > 256 or any(ord(c) < 32 for c in session_id):
        _invalid("material_session_required")
    return session_id


def validate_content(
    name: str, mime_type: str, data: bytes
) -> tuple[str, Literal["document", "image"]]:
    if not name or len(name) > 180 or any(ord(c) < 32 for c in name):
        _invalid("material_name_invalid")
    if not data:
        _invalid("material_empty")
    if len(data) > MAX_BYTES:
        _invalid("material_too_large", 413)
    mime = mime_type.split(";", 1)[0].strip().lower()
    if mime in DOCUMENT_TYPES:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            _invalid("material_utf8_required")
        if len(text) > MAX_TEXT_CHARS or "\x00" in text:
            _invalid("material_text_limit", 413)
        return mime, "document"
    if mime not in IMAGE_TYPES:
        _invalid("material_type_unsupported", 415)
    # Decode structure, not just a forgeable MIME/header. Avoid huge image buffers.
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            if (
                image.format != IMAGE_TYPES[mime]
                or image.width * image.height > 20000000
            ):
                _invalid("material_image_invalid")
            image.verify()
    except (
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(400, {"reason_code": "material_image_invalid"}) from exc
    return mime, "image"


class MaterialStore:
    def __init__(self, root: Path | None = None):
        self.root = (
            root if root is not None else runtime_state_root() / "chat-materials"
        )

    def _folder(self, session_id: str) -> Path:
        value = validate_session(session_id)
        return self.root / hashlib.sha256(value.encode()).hexdigest()

    def _paths(self, session_id: str, material_id: str) -> tuple[Path, Path]:
        try:
            if str(UUID(material_id)) != material_id:
                raise ValueError("noncanonical id")
        except ValueError as exc:
            raise HTTPException(404, {"reason_code": "material_not_found"}) from exc
        folder = self._folder(session_id)
        return folder / (material_id + ".json"), folder / (material_id + ".bin")

    def list(self, session_id: str) -> list[ChatMaterial]:
        """Return readable session records without letting one damaged entry block uploads."""
        folder = self._folder(session_id)
        with _LOCK:
            materials = []
            for item in sorted(folder.glob("*.json")):
                try:
                    materials.append(self.get(session_id, item.stem))
                except HTTPException:
                    logger.warning("Skipping unreadable chat material {}", item.stem)
            return materials

    def get(self, session_id: str, material_id: str) -> ChatMaterial:
        meta, binary = self._paths(session_id, material_id)
        try:
            material = ChatMaterial.model_validate_json(meta.read_bytes())
            if material.session_id != session_id or not binary.is_file():
                raise ValueError("owner or content unavailable")
            return material
        except (OSError, ValueError) as exc:
            raise HTTPException(404, {"reason_code": "material_not_found"}) from exc

    def read(self, session_id: str, material_id: str) -> tuple[ChatMaterial, bytes]:
        with _LOCK:
            material = self.get(session_id, material_id)
            _, binary = self._paths(session_id, material_id)
            try:
                data = binary.read_bytes()
            except OSError as exc:
                raise HTTPException(404, {"reason_code": "material_not_found"}) from exc
            if len(data) != material.size_bytes or len(data) > MAX_BYTES:
                _invalid("material_content_invalid")
            return material, data

    def save(
        self, session_id: str, name: str, mime_type: str, data: bytes
    ) -> ChatMaterial:
        folder = self._folder(session_id)
        mime, kind = validate_content(name, mime_type, data)
        with _LOCK:
            records = self.list(session_id)
            digest = hashlib.sha256(data).hexdigest()
            for record in records:
                meta, _ = self._paths(session_id, record.id)
                stored = json.loads(meta.read_text())
                if (
                    record.name == name
                    and record.mime_type == mime
                    and stored.get("sha256") == digest
                ):
                    return record
            if (
                len(records) >= MAX_SESSION_FILES
                or sum(r.size_bytes for r in records) + len(data) > MAX_SESSION_BYTES
            ):
                _invalid("material_session_limit", 413)
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            material_id = str(uuid4())
            material = ChatMaterial(
                id=material_id,
                session_id=session_id,
                name=name,
                mime_type=mime,
                size_bytes=len(data),
                kind=kind,
                created_at=datetime.now(timezone.utc).isoformat(),
                preview_url=f"/api/v1/chat/materials/{material_id}/content?session_id={quote(session_id, safe='')}",
            )
            meta, binary = self._paths(session_id, material_id)
            # A completed metadata write is the publication boundary. An aborted
            # upload never reaches this method; incomplete content is not listed.
            self._write(binary, data)
            try:
                self._write(
                    meta,
                    json.dumps({**material.model_dump(), "sha256": digest}).encode(),
                )
            except OSError:
                binary.unlink(missing_ok=True)
                raise
            return material

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".material-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def delete(self, session_id: str, material_id: str) -> None:
        with _LOCK:
            self.get(session_id, material_id)
            meta, binary = self._paths(session_id, material_id)
            meta.unlink()
            binary.unlink(missing_ok=True)
