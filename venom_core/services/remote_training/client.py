"""Resumable, hash-verified transfers and explicit operations on a prepared host."""

from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .bundles import verify_bundle
from .transport import Transport, TransportError

MAX_BUNDLE_BYTES = 100 * 1024**3


def validate_run_id(value: object) -> str:
    """Use the same non-path session identifier as bundle and host contracts."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value
    ):
        raise ValueError("remote_run_id_invalid")
    return value


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class RemoteClient:
    """No provider lifecycle, environment changes or adapter activation authority."""

    def __init__(
        self,
        transport: Transport,
        *,
        chunk_bytes: int = 256 * 1024,
        attempts: int = 3,
        max_bytes: int = MAX_BUNDLE_BYTES,
    ):
        if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 1024 * 1024:
            raise ValueError("remote_chunk_size_invalid")
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError("remote_attempts_invalid")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BUNDLE_BYTES:
            raise ValueError("remote_bundle_limit_invalid")
        self.transport = transport
        self.chunk_bytes = chunk_bytes
        self.attempts = attempts
        self.max_bytes = max_bytes

    def _request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.attempts):
            try:
                return self.transport.request(action, payload)
            except TransportError as error:
                if not error.retryable or attempt + 1 == self.attempts:
                    raise
        raise AssertionError("unreachable")

    def prepare(self, manifest: dict[str, Any]) -> dict[str, Any]:
        validate_run_id(manifest.get("run_id"))
        return self._request("prepare", {"manifest": manifest})

    def start(self, run_id: str, *, stage: str = "smoke") -> dict[str, Any]:
        if stage not in {"smoke", "train"}:
            raise ValueError("remote_stage_invalid")
        return self._request(
            "start", {"run_id": validate_run_id(run_id), "stage": stage}
        )

    def status(self, run_id: str) -> dict[str, Any]:
        return self._request("status", {"run_id": validate_run_id(run_id)})

    def logs(
        self, run_id: str, *, offset: int = 0, max_bytes: int = 65536
    ) -> dict[str, Any]:
        if (
            type(offset) is not int
            or offset < 0
            or type(max_bytes) is not int
            or not 1 <= max_bytes <= 1024 * 1024
        ):
            raise ValueError("remote_log_range_invalid")
        return self._request(
            "logs",
            {
                "run_id": validate_run_id(run_id),
                "offset": offset,
                "max_bytes": max_bytes,
            },
        )

    def stop(self, run_id: str) -> dict[str, Any]:
        return self._request("stop", {"run_id": validate_run_id(run_id)})

    def retry(self, run_id: str, *, from_attempt: int) -> dict[str, Any]:
        if type(from_attempt) is not int or from_attempt < 1:
            raise ValueError("remote_retry_attempt_invalid")
        return self._request(
            "retry", {"run_id": validate_run_id(run_id), "from_attempt": from_attempt}
        )

    def resume(self, run_id: str, checkpoint: str) -> dict[str, Any]:
        # The host validates the checkpoint inside this run; never a host pathname.
        if (
            not isinstance(checkpoint, str)
            or not checkpoint
            or len(checkpoint) > 256
            or "\x00" in checkpoint
        ):
            raise ValueError("remote_checkpoint_invalid")
        return self._request(
            "resume", {"run_id": validate_run_id(run_id), "checkpoint": checkpoint}
        )

    def upload(self, run_id: str, bundle: Path) -> dict[str, Any]:
        """Retry each idempotent chunk using identical offsets and whole-file digest."""
        validate_run_id(run_id)
        if bundle.is_symlink() or not bundle.is_file():
            raise ValueError("remote_bundle_path_invalid")
        size = bundle.stat().st_size
        if not 0 < size <= self.max_bytes:
            raise ValueError("remote_bundle_size_invalid")
        manifest = verify_bundle(
            bundle, expected_run_id=run_id, max_bytes=self.max_bytes
        )
        if manifest["kind"] != "input":
            raise ValueError("remote_input_bundle_required")
        checksum = _sha(bundle)
        offset = 0
        result: dict[str, Any] = {}
        with bundle.open("rb") as stream:
            while chunk := stream.read(self.chunk_bytes):
                final = offset + len(chunk) == size
                payload = {
                    "run_id": run_id,
                    "upload_id": checksum,
                    "offset": offset,
                    "data_b64": base64.b64encode(chunk).decode("ascii"),
                    "total_bytes": size,
                    "sha256": checksum,
                    "final": final,
                }
                result = self._request("upload", payload)
                offset += len(chunk)
                if type(result.get("offset")) is not int or result["offset"] != offset:
                    raise TransportError("remote_upload_offset_invalid")
        if offset != size:
            raise ValueError("remote_bundle_changed")
        return result

    def _download_chunk(
        self, run_id: str, offset: int, include_checkpoint: bool
    ) -> tuple[dict[str, Any], bytes]:
        result = self._request(
            "collect",
            {
                "run_id": run_id,
                "offset": offset,
                "max_bytes": self.chunk_bytes,
                "include_checkpoint": include_checkpoint,
            },
        )
        total = result.get("total_bytes")
        checksum = result.get("sha256")
        if (
            type(total) is not int
            or not 0 < total <= self.max_bytes
            or not isinstance(checksum, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or type(result.get("eof")) is not bool
            or not isinstance(result.get("data_b64"), str)
        ):
            raise TransportError("remote_collect_metadata_invalid")
        try:
            data = base64.b64decode(result["data_b64"], validate=True)
        except (ValueError, binascii.Error):
            raise TransportError("remote_collect_chunk_invalid") from None
        if (
            len(data) > self.chunk_bytes
            or offset + len(data) > total
            or result["eof"] != (offset + len(data) == total)
            or (not data and not result["eof"])
        ):
            raise TransportError("remote_collect_chunk_invalid")
        return result, data

    def collect(
        self, run_id: str, destination: Path, *, include_checkpoint: bool = False
    ) -> dict[str, Any]:
        """Keep interrupted bytes; atomically publish only verified result archives."""
        validate_run_id(run_id)
        if type(include_checkpoint) is not bool or destination.is_symlink():
            raise ValueError("remote_collect_destination_invalid")
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock_path = destination.with_name(destination.name + ".download.lock")
        if lock_path.is_symlink():
            raise ValueError("remote_collect_destination_invalid")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("remote_collect_busy") from None
            return self._collect_locked(run_id, destination, include_checkpoint)

    def _collect_locked(
        self, run_id: str, destination: Path, include_checkpoint: bool
    ) -> dict[str, Any]:
        first, data = self._download_chunk(run_id, 0, include_checkpoint)
        meta = {key: first[key] for key in ("sha256", "total_bytes")}
        meta.update(run_id=run_id, include_checkpoint=include_checkpoint)
        if destination.exists():
            if not destination.is_file() or _sha(destination) != meta["sha256"]:
                raise ValueError("remote_collect_destination_exists")
            manifest = verify_bundle(
                destination, expected_run_id=run_id, max_bytes=self.max_bytes
            )
            destination.chmod(0o600)
            return {
                "path": str(destination),
                "sha256": meta["sha256"],
                "manifest": manifest,
            }
        partial = destination.with_name(destination.name + ".part")
        metadata = destination.with_name(destination.name + ".part.json")
        if partial.is_symlink() or metadata.is_symlink():
            raise ValueError("remote_collect_destination_invalid")
        if partial.exists() or metadata.exists():
            if (
                not partial.is_file()
                or not metadata.is_file()
                or json.loads(metadata.read_text()) != meta
            ):
                raise ValueError("remote_collect_partial_mismatch")
        else:
            descriptor = os.open(
                partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            os.close(descriptor)
            descriptor = os.open(
                metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "w") as stream:
                json.dump(meta, stream, sort_keys=True)
        offset = partial.stat().st_size
        if offset > meta["total_bytes"]:
            raise ValueError("remote_collect_partial_mismatch")
        descriptor = os.open(partial, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            while offset < meta["total_bytes"]:
                result, chunk = (
                    (first, data)
                    if offset == 0
                    else self._download_chunk(run_id, offset, include_checkpoint)
                )
                if any(result[key] != meta[key] for key in ("sha256", "total_bytes")):
                    raise TransportError("remote_collect_changed")
                stream.write(chunk)
                stream.flush()
                offset += len(chunk)
            os.fsync(stream.fileno())
        if _sha(partial) != meta["sha256"]:
            raise ValueError("remote_collect_hash_mismatch")
        manifest = verify_bundle(
            partial, expected_run_id=run_id, max_bytes=self.max_bytes
        )
        if manifest["kind"] != "result":
            raise ValueError("remote_result_bundle_required")
        os.link(partial, destination)
        partial.unlink()
        metadata.unlink()
        return {
            "path": str(destination),
            "sha256": meta["sha256"],
            "manifest": manifest,
        }
