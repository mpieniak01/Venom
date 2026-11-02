"""Fixed JSON RPC entry point for an explicitly prepared remote training host."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .bundles import _manifest, canonical
from .client import validate_run_id
from .lifecycle import JobStore
from .remote_io import collect_chunk, log_chunk, upload_chunk
from .transport import ACTIONS, MAX_RPC_BYTES

_FIELDS = {
    "prepare": {"manifest"},
    "upload": {
        "run_id",
        "upload_id",
        "offset",
        "data_b64",
        "total_bytes",
        "sha256",
        "final",
    },
    "start": {"run_id", "stage", "timeout_seconds"},
    "status": {"run_id"},
    "logs": {"run_id", "offset", "max_bytes"},
    "stop": {"run_id"},
    "resume": {"run_id", "checkpoint", "stage", "timeout_seconds"},
    "retry": {"run_id", "from_attempt", "timeout_seconds"},
    "collect": {"run_id", "offset", "max_bytes", "include_checkpoint"},
}


def dispatch(store: JobStore, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch allowlisted operations; no executable or host path is accepted in input."""
    if (
        action not in ACTIONS
        or not isinstance(payload, dict)
        or not set(payload) <= _FIELDS[action]
    ):
        raise ValueError("remote_training_rpc_invalid")
    if action == "prepare":
        manifest = _manifest(payload.get("manifest"), 100 * 1024**3)
        if manifest["kind"] != "input":
            raise ValueError("remote_training_input_bundle_required")
        return store.prepare(manifest)
    run_id = validate_run_id(payload.get("run_id"))
    if action == "upload":
        return upload_chunk(store, payload)
    if action == "collect":
        return collect_chunk(store, payload)
    if action == "logs":
        return log_chunk(
            store, run_id, payload.get("offset", 0), payload.get("max_bytes", 65536)
        )
    if action == "status":
        return store.status(run_id)
    if action == "stop":
        return store.stop(run_id)
    if action == "retry":
        from_attempt = payload.get("from_attempt")
        if type(from_attempt) is not int or from_attempt < 1:
            raise ValueError("remote_training_retry_attempt_invalid")
        return store.retry(
            run_id,
            from_attempt,
            timeout_seconds=payload.get("timeout_seconds", 3600),
        )
    stage, timeout = payload.get("stage", "smoke"), payload.get("timeout_seconds", 3600)
    if stage not in {"smoke", "train"}:
        raise ValueError("remote_training_stage_invalid")
    if action == "start":
        return store.start(run_id, stage=stage, timeout_seconds=timeout)
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, str) or not checkpoint:
        raise ValueError("remote_training_checkpoint_path_invalid")
    # Resume retains its original stage unless the caller explicitly selected another.
    if "stage" not in payload:
        stage = store.status(run_id).get("stage") or "smoke"
    return store.resume(run_id, checkpoint, stage=stage, timeout_seconds=timeout)


def response(store: JobStore, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Expose only stable error codes, never exception text, locations or secrets."""
    try:
        return {"ok": True, "result": dispatch(store, action, payload)}
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        code = str(error).partition(":")[0]
        if not re.fullmatch(r"(?:remote_training|granite)_[a-z0-9_]{1,80}", code):
            code = "remote_training_operation_failed"
        return {"ok": False, "error": code}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("action", choices=sorted(ACTIONS))
    args = parser.parse_args(argv)
    raw = sys.stdin.buffer.read(MAX_RPC_BYTES + 1)
    if len(raw) > MAX_RPC_BYTES:
        result = {"ok": False, "error": "remote_training_rpc_too_large"}
    else:
        try:
            payload = json.loads(raw)
            result = response(JobStore(args.root), args.action, payload)
        except (ValueError, OSError):
            result = {"ok": False, "error": "remote_training_rpc_invalid"}
    encoded = canonical(result)
    if len(encoded) > MAX_RPC_BYTES:
        encoded = canonical({"ok": False, "error": "remote_training_rpc_too_large"})
    sys.stdout.buffer.write(encoded + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
