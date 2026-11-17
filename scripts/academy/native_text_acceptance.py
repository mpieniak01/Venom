"""Run local native-chat acceptance with explicit ownership and fresh restore proof.

This helper never starts services on import. The operator supplies canonical
launcher steps; all cleanup/restore steps run independently after a stop attempt.
It is used by the live acceptance driver, with CPU doubles in automated tests.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from venom_core.services.remote_training.lifecycle import atomic_json

_STEPS = (
    "preflight",
    "stop_main",
    "start_test",
    "accept",
    "stop_test",
    "restore_main",
    "verify_restore",
)
Action = Callable[[], dict[str, Any] | None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_restore(proof: dict[str, Any], started: str, main_root: Path) -> None:
    """Require a fresh, complete observation; a prior receipt is never sufficient."""
    observed = datetime.fromisoformat(proof["checked_at"])
    if observed.tzinfo is None or not (
        datetime.fromisoformat(started) <= observed <= datetime.now(timezone.utc)
    ):
        raise ValueError("native_acceptance_stale_restore_proof")
    owners = proof["owners"]
    expected = {
        "api": main_root,
        "web": main_root / "web-next",
        "supervisor": main_root,
    }
    if set(owners) != set(expected):
        raise ValueError("native_acceptance_restore_owner_missing")
    for kind, directory in expected.items():
        owner = owners[kind]
        if (
            type(owner["pid"]) is not int
            or owner["pid"] <= 0
            or Path(owner["cwd"]).resolve() != directory
        ):
            raise ValueError("native_acceptance_restore_owner_invalid")
    statuses = proof["http_statuses"]
    if len(statuses) != 9 or any(
        type(code) is not int or code != 200 for code in statuses
    ):
        raise ValueError("native_acceptance_restore_http_failed")
    if (
        proof["supervisor_active"] is not True
        or proof["test_ports_closed"] is not True
        or type(proof["leases"]) is not int
        or proof["leases"] != 0
        or type(proof["operations"]) is not int
        or proof["operations"] != 0
        or proof["active_experiments"] != []
        or proof["gpu_available"] is not True
        or proof["ollama_models"] != []
    ):
        raise ValueError("native_acceptance_restore_not_idle")


def run_acceptance(
    output: Path, main_root: Path, steps: dict[str, Action]
) -> dict[str, Any]:
    """Persist every phase and return PASS only after a fresh restored-state probe.

    The output must be a new attempt directory. A failure in stop_test cannot
    suppress restore_main or verify_restore. Callers must treat status=failed as
    an unsuccessful whole acceptance, even if generation itself passed.
    """
    if set(steps) != set(_STEPS):
        raise ValueError("native_acceptance_steps_incomplete")
    main_root = main_root.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "schema_version": 1,
        "started_at": _now(),
        "status": "failed",
        "main_root": str(main_root),
        "phases": [],
        "errors": [],
    }

    def persist(path: Path, payload: dict[str, Any], phase: dict | None = None) -> None:
        try:
            atomic_json(path, payload)
        except OSError as exc:
            result["status"] = "failed"
            result["errors"].append(
                {
                    "phase": phase["name"] if phase is not None else "lifecycle",
                    "operation": "write",
                    "file": path.name,
                    "type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            if phase is not None:
                phase["status"] = "failed"

    def call(name: str) -> bool:
        phase: dict[str, Any] = {"name": name, "started_at": _now()}
        try:
            value = steps[name]()
            phase["proof"] = value
            if name == "verify_restore":
                if not isinstance(value, dict):
                    raise ValueError("native_acceptance_restore_proof_missing")
                _validate_restore(value, phase["started_at"], main_root)
            phase["status"] = "passed"
        except BaseException as exc:
            phase["status"] = "failed"
            phase["error"] = {"type": type(exc).__name__, "reason": str(exc)}
            result["errors"].append({"phase": name, **phase["error"]})
        finally:
            phase["finished_at"] = _now()
            result["phases"].append(phase)
            persist(output / (name + ".json"), phase, phase)
            persist(output / "lifecycle.json", result, phase)
        return phase["status"] == "passed"

    if call("preflight"):
        try:
            if call("stop_main") and call("start_test"):
                call("accept")
        finally:
            call("stop_test")
            call("restore_main")
            call("verify_restore")
    result["status"] = "passed" if not result["errors"] else "failed"
    result["finished_at"] = _now()
    persist(output / "lifecycle.json", result)
    return result
