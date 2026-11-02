"""Bounded idempotent RPC transfers into one prepared job's private directory."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .artifacts import create_result_bundle
from .bundles import MAX_BYTES, canonical, extract_bundle, sha256, verify_bundle
from .client import validate_run_id
from .lifecycle import TERMINAL, JobStore, atomic_json, file_lock, log_base

MAX_CHUNK_BYTES = 1024 * 1024


def _plain(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("remote_training_transfer_symlink")


def _upload_values(payload: dict[str, Any]) -> tuple[str, int, int, bytes, bool]:
    checksum = payload.get("sha256")
    total, offset, final = (
        payload.get("total_bytes"),
        payload.get("offset"),
        payload.get("final"),
    )
    if (
        not isinstance(checksum, str)
        or not re.fullmatch(r"[a-f0-9]{64}", checksum)
        or payload.get("upload_id") != checksum
    ):
        raise ValueError("remote_training_upload_digest_invalid")
    if (
        type(total) is not int
        or not 0 < total <= MAX_BYTES
        or type(offset) is not int
        or offset < 0
        or type(final) is not bool
    ):
        raise ValueError("remote_training_upload_range_invalid")
    encoded = payload.get("data_b64")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_CHUNK_BYTES + 2) // 3):
        raise ValueError("remote_training_upload_chunk_invalid")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("remote_training_upload_chunk_invalid") from None
    if (
        not data
        or len(data) > MAX_CHUNK_BYTES
        or offset + len(data) > total
        or final != (offset + len(data) == total)
    ):
        raise ValueError("remote_training_upload_range_invalid")
    return checksum, total, offset, data, final


def upload_chunk(store: JobStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Retries compare previously committed bytes; finalization verifies the ZIP manifest."""
    directory = store.directory(validate_run_id(payload.get("run_id")))
    manifest_path = directory / "manifest.json"
    _plain(manifest_path)
    if not manifest_path.is_file():
        raise ValueError("remote_training_run_not_prepared")
    manifest = json.loads(manifest_path.read_text())
    checksum, total, offset, data, final = _upload_values(payload)
    uploads = directory / "uploads"
    _plain(uploads)
    uploads.mkdir(exist_ok=True, mode=0o700)
    partial, complete = uploads / (checksum + ".part"), uploads / (checksum + ".zip")
    metadata = uploads / (checksum + ".json")
    wanted = {"sha256": checksum, "total_bytes": total}
    with file_lock(directory / ".transfer.lock"):
        for path in (partial, complete, metadata):
            _plain(path)
        if metadata.exists():
            if json.loads(metadata.read_text()) != wanted:
                raise ValueError("remote_training_upload_identity_changed")
        else:
            atomic_json(metadata, wanted)
        target = complete if complete.exists() else partial
        descriptor = os.open(target, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "r+b") as stream:
            stream.seek(0, os.SEEK_END)
            received = stream.tell()
            if offset > received or received > total:
                raise ValueError("remote_training_upload_offset_invalid")
            overlap = min(len(data), received - offset)
            stream.seek(offset)
            if overlap and stream.read(overlap) != data[:overlap]:
                raise ValueError("remote_training_upload_retry_changed")
            if offset + len(data) > received:
                if target == complete:
                    raise ValueError("remote_training_upload_completed_changed")
                stream.seek(received)
                stream.write(data[overlap:])
                stream.flush()
                os.fsync(stream.fileno())
        if final:
            if target.stat().st_size != total or sha256(target) != checksum:
                raise ValueError("remote_training_upload_checksum_mismatch")
            actual = verify_bundle(
                target,
                expected_run_id=manifest["run_id"],
                expected_identity=manifest["identity"],
            )
            if actual != manifest or actual["kind"] != "input":
                raise ValueError("remote_training_upload_manifest_changed")
            extract_bundle(
                target,
                directory / "input",
                expected_run_id=manifest["run_id"],
                expected_identity=manifest["identity"],
            )
            if target == partial:
                os.link(partial, complete)
                partial.unlink()
        return {"offset": offset + len(data), "ready": final}


def attempt_directory(
    store: JobStore, run_id: str, state: dict[str, Any]
) -> Path | None:
    """Accept only an attempt directory created by this job store, not an arbitrary path."""
    relative = state.get("attempt_root")
    if relative is None:
        return None
    pattern = r"runs/" + re.escape(run_id) + r"/attempts/[0-9]{4,}"
    if not isinstance(relative, str) or not re.fullmatch(pattern, relative):
        raise ValueError("remote_training_attempt_path_invalid")
    path = store.root
    for part in Path(relative).parts:
        path = path / part
        _plain(path)
    return path


def log_chunk(
    store: JobStore, run_id: str, offset: int, max_bytes: int
) -> dict[str, Any]:
    """Read a bounded byte range, without decoding private state or process environments."""
    if (
        type(offset) is not int
        or offset < 0
        or type(max_bytes) is not int
        or not 1 <= max_bytes <= MAX_CHUNK_BYTES
    ):
        raise ValueError("remote_training_log_range_invalid")
    attempt = attempt_directory(store, run_id, store.status(run_id))
    if attempt is None:
        return {"text": "", "offset": offset, "eof": True}
    path = attempt / "worker.log"
    _plain(path)
    if not path.exists():
        return {"text": "", "offset": offset, "eof": True}
    with file_lock(path.with_suffix(".log.lock")):
        base, reset = log_base(path)
        total = base + path.stat().st_size
        reset = reset or offset > total
        start = base if reset else max(base, offset)
        with path.open("rb") as stream:
            stream.seek(start - base)
            data = stream.read(max_bytes)
        end = start + len(data)
    return {
        "text": data.decode(errors="replace"),
        "offset": end,
        "eof": end >= total,
        "base_offset": base,
        "truncated": offset < base,
        "reset": reset,
    }


def _cache_stat(path: Path) -> list[int]:
    """Detect replaced or modified cached ZIPs without hashing every chunk."""
    value = path.stat()
    return [
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    ]


def collect_chunk(store: JobStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Cache immutable terminal-attempt bundles; active jobs cannot be collected."""
    run_id = validate_run_id(payload.get("run_id"))
    directory = store.directory(run_id)
    maximum, offset = payload.get("max_bytes"), payload.get("offset")
    checkpoint = payload.get("include_checkpoint", False)
    if (
        type(maximum) is not int
        or not 1 <= maximum <= MAX_CHUNK_BYTES
        or type(offset) is not int
        or offset < 0
        or type(checkpoint) is not bool
    ):
        raise ValueError("remote_training_collect_range_invalid")
    with file_lock(directory / ".collect.lock"):
        selected_attempt = payload.get("attempt")
        if "attempt" in payload and (
            type(selected_attempt) is not int or selected_attempt < 1
        ):
            raise ValueError("remote_training_attempt_selector_invalid")
        state = (
            store.status(run_id)
            if selected_attempt is None
            else store.attempt_status(run_id, selected_attempt)
        )
        if state["status"] not in TERMINAL:
            raise ValueError("remote_training_collect_requires_terminal")
        proof = {
            key: state[key] for key in ("run_id", "attempt", "status", "exit_code")
        }
        proof_hash = hashlib.sha256(canonical(proof)).hexdigest()
        collections = directory / "collections"
        _plain(collections)
        collections.mkdir(exist_ok=True, mode=0o700)
        name = f"v2-attempt-{state['attempt']:04d}-checkpoint-{int(checkpoint)}.zip"
        archive, metadata = collections / name, collections / (name + ".json")
        for path in (archive, metadata):
            _plain(path)
        if not archive.exists():
            _create_collection(store, directory, state, archive, checkpoint, proof)
        if not metadata.is_file():
            _publish_collection_metadata(
                directory, archive, metadata, proof, proof_hash
            )
        meta = json.loads(metadata.read_text())
        if meta.get("supervisor_sha256") != proof_hash or _cache_stat(
            archive
        ) != meta.get("archive_stat"):
            raise ValueError("remote_training_collect_cache_changed")
        if offset > meta["total_bytes"]:
            raise ValueError("remote_training_collect_range_invalid")
        with archive.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(maximum)
        return {
            "sha256": meta["sha256"],
            "total_bytes": meta["total_bytes"],
            "data_b64": base64.b64encode(data).decode("ascii"),
            "eof": offset + len(data) == meta["total_bytes"],
        }


def _create_collection(store, directory, state, archive, checkpoint, proof):
    from .milestones import read_attempt, verify_seal

    outcome = directory / "attempts" / f"{state['attempt']:04d}" / "outcome.json"
    if outcome.is_file():
        verify_seal(directory, read_attempt(directory, state["attempt"]))
    manifest = json.loads((directory / "manifest.json").read_text())
    attempt = attempt_directory(store, state["run_id"], state)
    result = attempt / "result" if attempt is not None else directory / "missing-result"
    _plain(result)
    create_result_bundle(
        result,
        archive,
        run_id=state["run_id"],
        identity=manifest["identity"],
        include_checkpoint=checkpoint,
        supervisor=proof,
        coordinator_log=attempt / "worker.log" if attempt is not None else None,
    )


def _publish_collection_metadata(directory, archive, metadata, proof, proof_hash):
    # Publication may have succeeded just before an SSH disconnect.
    manifest = json.loads((directory / "manifest.json").read_text())
    sealed = verify_bundle(
        archive, expected_run_id=proof["run_id"], expected_identity=manifest["identity"]
    )
    supervisor = sealed.get("receipt", {}).get("supervisor")
    if supervisor != proof:
        raise ValueError("remote_training_collect_supervisor_changed")
    atomic_json(
        metadata,
        {
            "sha256": sha256(archive),
            "total_bytes": archive.stat().st_size,
            "supervisor_sha256": proof_hash,
            "archive_stat": _cache_stat(archive),
        },
    )
