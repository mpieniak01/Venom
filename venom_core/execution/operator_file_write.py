"""Trusted operator path for one reviewed file write. Never register as a tool."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from threading import Lock

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.core.permission_guard import permission_guard
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

MAX_CONTENT_BYTES = 128 * 1024
_APPROVAL_SECONDS = 120
_SIGNATURE = tuple[int, int, int, int, int]
logger = get_logger(__name__)


def _parts(path: str) -> list[str]:
    """Reject noncanonical or absolute paths before opening workspace directories."""
    parts = path.split("/")
    if (
        any(c in path for c in ("\\", ":", "\0"))
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(c) < 32 for c in path)
    ):
        raise ValueError("file_write_relative_path_required")
    return parts


def _content_digest(content: bytes | None) -> str:
    """Validate explicit UTF-8 content and bind the approval to its SHA-256."""
    if content is None:
        raise ValueError("file_write_content_required")
    if len(content) > MAX_CONTENT_BYTES:
        raise ValueError("file_write_content_too_large")
    content.decode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _state(directory: int, name: str) -> _SIGNATURE | None:
    """Capture the identity of a regular file without following symlinks."""
    try:
        result = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(result.st_mode):
        raise PermissionError("file_write_regular_target_required")
    return (
        result.st_dev,
        result.st_ino,
        result.st_ctime_ns,
        result.st_size,
        result.st_mode,
    )


def _directory_identity(directory: int) -> tuple[int, int]:
    """Identify the opened parent by device and inode."""
    current = os.fstat(directory)
    return current.st_dev, current.st_ino


@contextmanager
def _parent(workspace: Path, parts: list[str]) -> Iterator[int]:
    """Open each parent relative to a verified directory without following symlinks."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PermissionError("file_write_secure_directory_handles_required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        directory = os.open(workspace, flags)
        stack.callback(os.close, directory)
        for part in parts[:-1]:
            directory = os.open(part, flags, dir_fd=directory)
            stack.callback(os.close, directory)
        yield directory


def _publish(
    directory: int, name: str, content: bytes, expected: _SIGNATURE | None
) -> None:
    """Write through a private temporary file and publish only after rechecking the target."""
    tmp = f".venom-write-{token_urlsafe(18)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(tmp, flags, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            if expected is not None:
                os.fchmod(stream.fileno(), expected[-1] & 0o777)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if _state(directory, name) != expected:
            raise PermissionError("file_write_target_changed")
        if expected is None:
            # Atomic create. A concurrently created target must not be overwritten.
            os.link(tmp, name, src_dir_fd=directory, dst_dir_fd=directory)
        else:
            os.replace(tmp, name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(tmp, dir_fd=directory)


@dataclass(frozen=True)
class _Approval:
    token: str
    session: str
    path: str
    content_sha256: str
    overwrite: bool
    expires: float
    parent: tuple[int, int]
    target: _SIGNATURE | None


class OperatorFileWrites:
    """One pending approval scoped to this workspace and trusted operator flow."""

    def __init__(self, workspace: Path):
        """Initialize one approval slot for the selected workspace."""
        self._workspace = workspace.resolve(strict=True)
        self._approval: _Approval | None = None
        self._lock = Lock()

    def prepare(
        self, session: str, path: str, content: bytes | None, *, overwrite: bool = False
    ) -> str:
        """Bind a reviewed payload from operator input, never from model output."""
        if not session.strip():
            raise ValueError("file_write_session_required")
        parts = _parts(path)
        digest = _content_digest(content)
        with _parent(self._workspace, parts) as directory:
            parent = _directory_identity(directory)
            target = _state(directory, parts[-1])
        if target is not None and not overwrite:
            raise FileExistsError("file_write_overwrite_confirmation_required")
        token = token_urlsafe(32)
        approval = _Approval(
            token,
            session,
            path,
            digest,
            overwrite,
            time.monotonic() + _APPROVAL_SECONDS,
            parent,
            target,
        )
        with self._lock:
            self._approval = approval
        return token

    def execute(
        self,
        token: str,
        session: str,
        path: str,
        content: bytes | None,
        *,
        overwrite: bool = False,
    ) -> None:
        """Check and consume the approval before any filesystem mutation."""
        parts = _parts(path)
        digest = _content_digest(content)
        with self._lock:
            approval = self._approval
            if (
                approval is None
                or approval.session != session
                or not compare_digest(token, approval.token)
                or time.monotonic() >= approval.expires
            ):
                raise PermissionError("file_write_approval_required")
            self._approval = None
        if (path, digest, overwrite) != (
            approval.path,
            approval.content_sha256,
            approval.overwrite,
        ):
            raise PermissionError("file_write_approval_mismatch")
        ensure_data_mutation_allowed("operator_file_write")
        if not permission_guard.can_write_files():
            raise PermissionError("file_write_permission_required")
        assert content is not None  # enforced by _content_digest
        with _parent(self._workspace, parts) as directory:
            if (
                _directory_identity(directory) != approval.parent
                or _state(directory, parts[-1]) != approval.target
            ):
                raise PermissionError("file_write_target_changed")
            _publish(directory, parts[-1], content, approval.target)
        entry = get_audit_stream().publish(
            source="execution.operator_file_write",
            action="operator_file_write",
            actor="local_operator",
            status="succeeded",
            context=session,
            details={"path": path, "content_sha256": digest, "overwrite": overwrite},
        )
        logger.info(
            "Operator file write: {}",
            json.dumps(
                {
                    "id": entry.id,
                    "timestamp": entry.timestamp.isoformat(),
                    "actor": entry.actor,
                    "status": entry.status,
                    "session": entry.context,
                    **entry.details,
                }
            ),
        )
