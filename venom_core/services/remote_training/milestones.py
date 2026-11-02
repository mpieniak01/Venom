"""Explicit milestone targets and sealed terminal-attempt evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .bundles import sha256

MAX_UPDATES = 256


def target_update(manifest: dict, stage: str, value: int | None) -> int | None:
    if value is None:
        return None
    maximum = manifest.get("identity", {}).get("limits", {}).get("max_updates")
    if (
        stage != "train"
        or type(value) is not int
        or type(maximum) is not int
        or not 1 <= value <= maximum <= MAX_UPDATES
    ):
        raise ValueError("remote_training_update_target_invalid")
    return value


def seal_attempt(directory: Path, state: dict[str, Any]) -> None:
    from .lifecycle import TERMINAL, atomic_json

    if (
        state["status"] not in TERMINAL
        or state["attempt"] < 1
        or state.get("attempt_root") is None
    ):
        return
    attempt = directory / "attempts" / f"{state['attempt']:04d}"
    if attempt.is_symlink() or not attempt.is_dir():
        raise ValueError("remote_training_attempt_path_invalid")
    path = attempt / "outcome.json"
    if path.is_symlink():
        raise ValueError("remote_training_attempt_outcome_invalid")
    if path.exists():
        return
    proof: dict[str, Any] = {
        key: state.get(key)
        for key in (
            "run_id",
            "attempt",
            "status",
            "stage",
            "exit_code",
            "until_update",
            "attempt_root",
            "elapsed_seconds",
            "finished_at",
        )
    }
    proof["completed_updates"] = None
    proof["result_checkpoint"] = None
    proof["artifact_hashes"] = {}
    if state["status"] == "succeeded":
        receipt = attempt / "result/checkpoint/receipt.json"
        if receipt.is_file():
            if receipt.is_symlink() or receipt.stat().st_size > 8 * 1024**2:
                raise ValueError("remote_training_checkpoint_receipt_invalid")
            step = json.loads(receipt.read_text()).get("step")
            if type(step) is not int or not 1 <= step <= MAX_UPDATES:
                raise ValueError("remote_training_checkpoint_step_invalid")
            proof["completed_updates"] = step
            proof["result_checkpoint"] = receipt.parent.relative_to(
                directory
            ).as_posix()
        for name in (
            "adapter_model.safetensors",
            "checkpoint/receipt.json",
            "identity.json",
            "metrics.json",
            "qualification.json",
        ):
            file = attempt / "result" / name
            if file.exists():
                proof["artifact_hashes"][name] = sha256(file)
    atomic_json(path, proof)


def read_attempt(directory: Path, attempt: int) -> dict[str, Any]:
    from .lifecycle import TERMINAL

    if type(attempt) is not int or attempt < 1:
        raise ValueError("remote_training_attempt_selector_invalid")
    path = directory / "attempts" / f"{attempt:04d}" / "outcome.json"
    if (
        path.parent.is_symlink()
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 8 * 1024**2
    ):
        raise ValueError("remote_training_attempt_outcome_missing")
    proof = json.loads(path.read_text())
    if (
        not isinstance(proof, dict)
        or not isinstance(proof.get("artifact_hashes"), dict)
        or proof.get("run_id") != directory.name
        or proof.get("attempt") != attempt
        or proof.get("status") not in TERMINAL
        or proof.get("attempt_root") != f"runs/{directory.name}/attempts/{attempt:04d}"
    ):
        raise ValueError("remote_training_attempt_outcome_invalid")
    elapsed = proof.get("elapsed_seconds", 0.0)
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("remote_training_attempt_outcome_invalid")
    return proof


def verify_seal(directory: Path, proof: dict[str, Any]) -> None:
    result = directory / "attempts" / f"{proof['attempt']:04d}" / "result"
    for name, checksum in proof.get("artifact_hashes", {}).items():
        if (
            name
            not in (
                "adapter_model.safetensors",
                "checkpoint/receipt.json",
                "identity.json",
                "metrics.json",
                "qualification.json",
            )
            or sha256(result / name) != checksum
        ):
            raise ValueError("remote_training_sealed_artifact_changed")


def plan(run_id: str, steps: list[int], max_seconds: int) -> dict:
    from .bundles import validate_run_id

    validate_run_id(run_id)
    if (
        not steps
        or len(steps) > 16
        or any(type(s) is not int or not 1 <= s <= MAX_UPDATES for s in steps)
        or steps != sorted(set(steps))
        or type(max_seconds) is not int
        or not 1 <= max_seconds <= 86400
    ):
        raise ValueError("remote_training_milestone_plan_invalid")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "milestones": steps,
        "max_updates": steps[-1],
        "max_seconds": max_seconds,
        "execution": "explicit_one_step_at_a_time",
        "host_retention": "retain_on_success_and_failure",
        "steps": [
            {
                "target_update": step,
                "action": "start" if i == 0 else "resume",
                "stage": "train",
                "requires": "qualified_smoke"
                if i == 0
                else f"completed_checkpoint_{steps[i - 1]}",
                "independent_actions": [
                    "status",
                    "collect",
                    "inspect-result",
                    "import-result",
                    "evaluate",
                ],
                "auto_advance": False,
            }
            for i, step in enumerate(steps)
        ],
    }
