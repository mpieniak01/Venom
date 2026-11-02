"""Bounded read-only progress observations; never start or stop training."""

from __future__ import annotations

import json
import math
import time
from typing import Any

from .lifecycle import LOG_LIMIT, TERMINAL, file_lock
from .transport import TransportError


def _metrics(event, total):
    """Reject malformed/nonfinite values rather than synthesizing progress."""
    step = event.get("step")
    if type(step) is not int or type(total) is not int or not 0 <= step <= total:
        return None
    keys = ("loss", "gradient_norm", "elapsed_seconds", "target_tokens")
    if not all(
        type(event.get(key)) in {int, float}
        and abs(event[key]) < 1e30
        and math.isfinite(event[key])
        and event[key] >= 0
        for key in keys
    ):
        return None
    return {
        "completed_updates": step,
        "percent": round(100 * step / total, 1) if total else None,
        "phase": "optimizing",
        **{key: event[key] for key in ("loss", "gradient_norm", "target_tokens")},
    }


def _events(lines, progress, total):
    """Accept only complete native metric records and explicit known phases."""
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "remote_training_stage":
            if event.get("phase") in {"loading", "finalizing", "stage_complete"}:
                progress["phase"] = event["phase"]
            continue
        metrics = _metrics(event, total)
        if metrics is not None:
            progress.update(metrics)
    return progress


def observe(store, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Read only the current attempt; retries cannot inherit stale progress."""
    from .remote_io import attempt_directory

    manifest = json.loads((store.directory(run_id) / "manifest.json").read_text())
    total = (
        20
        if state.get("stage") == "smoke"
        else state.get("until_update")
        or manifest["identity"].get("limits", {}).get("max_updates")
    )
    progress: dict[str, Any] = {
        "completed_updates": None,
        "total_updates": total,
        "planned_max_updates": manifest["identity"]
        .get("limits", {})
        .get("max_updates"),
        "percent": None,
        "phase": state["status"]
        if state.get("status") in TERMINAL
        else "waiting_for_worker",
        "scope": "optimizer_updates",
    }
    attempt = attempt_directory(store, run_id, state)
    if attempt is None:
        return progress
    path = attempt / "worker.log"
    if path.is_symlink():
        raise ValueError("remote_training_log_symlink")
    with file_lock(path.with_suffix(".log.lock")):
        if not path.exists():
            return progress
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - LOG_LIMIT))
            lines = stream.read(LOG_LIMIT).splitlines()
        progress["log_updated_at"] = path.stat().st_mtime
        progress["last_log_age_seconds"] = round(
            max(0, time.time() - progress["log_updated_at"]), 1
        )
    _events(lines, progress, total)
    if state.get("status") in TERMINAL:
        progress["phase"] = state["status"]
    return progress


def format_status(state: dict[str, Any]) -> str:
    """One readable snapshot; never label optimizer completion as job success."""
    progress = state.get("progress", {})
    completed, total = progress.get("completed_updates"), progress.get("total_updates")
    updates = "--" if completed is None else str(completed)
    percent = "--" if progress.get("percent") is None else str(progress["percent"])
    loss = progress.get("loss", "--")
    age = progress.get("last_log_age_seconds", "--")
    error = f" error={state['error']}" if state.get("error") else ""
    return (
        f"{state.get('run_id', '--')} attempt={state.get('attempt', 0)} "
        f"{state.get('stage') or '--'}/{state['status']} "
        f"phase={progress.get('phase', '--')} updates={updates}/{total or '--'} "
        f"({percent}%) loss={loss} last_log={age}s{error}"
    )


def watch(
    client,
    run_id: str,
    *,
    interval: float,
    max_seconds: float,
    json_lines: bool = False,
    emit=print,
):
    """Poll state; interruption or SSH loss only disconnects the viewer."""
    if not 1 <= interval <= 60 or not 1 <= max_seconds <= 86400:
        raise ValueError("remote_training_watch_limits_invalid")
    deadline = time.monotonic() + max_seconds
    errors = 0
    try:
        while True:
            try:
                state = client.status(run_id)
                errors = 0
                message = (
                    json.dumps({"connection": "connected", **state}, allow_nan=False)
                    if json_lines
                    else format_status(state)
                )
                emit(message, flush=True)
                if state["status"] in TERMINAL:
                    return {"watch": "finished", "status": state["status"]}
            except TransportError as error:
                errors += 1
                message = (
                    json.dumps({"connection": "unavailable", "failures": errors})
                    if json_lines
                    else f"SSH unavailable ({errors}/3); training has not been stopped"
                )
                emit(message, flush=True)
                if not error.retryable or errors >= 3:
                    return {"watch": "disconnected", "training_stopped": False}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"watch": "time_limit", "training_stopped": False}
            time.sleep(min(interval, remaining))
    except KeyboardInterrupt:
        return {"watch": "interrupted", "training_stopped": False}
