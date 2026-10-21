"""Small durable transport identity, independent of boot/process sessions."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path

from venom_core.config import SETTINGS

_PEER_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}", re.ASCII)


def _read_peer_id(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
            raise ValueError("Invalid transport identity file")
        payload = json.loads(handle.read(1025))
    peer_id = payload.get("peer_id") if isinstance(payload, dict) else None
    if not isinstance(peer_id, str) or not _PEER_ID.fullmatch(peer_id):
        raise ValueError("Invalid transport peer identity")
    return peer_id


def read_transport_identity() -> dict[str, str | int]:
    """Create once atomically, or fail closed without replacing corrupt identity."""
    path = Path(SETTINGS.VENOM_TRANSPORT_IDENTITY_FILE)
    try:
        peer_id = _read_peer_id(path)
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(json.dumps({"peer_id": uuid.uuid4().hex}).encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass  # A concurrent worker won; read the same durable identity.
            finally:
                temporary.unlink()
        peer_id = _read_peer_id(path)
    return {
        "protocol_version": 1,
        "peer_id": peer_id,
        "service_role": "venom",
        "operator_access": SETTINGS.VENOM_OPERATOR_ACCESS,
    }
