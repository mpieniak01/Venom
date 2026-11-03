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
        try:
            proof.update(_checkpoint_evidence(attempt, directory))
            proof["artifact_hashes"] = _artifact_hashes(attempt)
        except (OSError, ValueError):
            proof.update(
                status="invalid_evidence",
                error="remote_training_attempt_evidence_invalid",
                completed_updates=None,
                result_checkpoint=None,
                artifact_hashes={},
            )
    atomic_json(path, proof)


def _checkpoint_evidence(attempt: Path, directory: Path) -> dict[str, Any]:
    receipt = attempt / "result/checkpoint/receipt.json"
    if not receipt.is_file():
        return {}
    if receipt.is_symlink() or receipt.stat().st_size > 8 * 1024**2:
        raise ValueError("remote_training_checkpoint_receipt_invalid")
    document = json.loads(receipt.read_text())
    if not isinstance(document, dict):
        raise ValueError("remote_training_checkpoint_receipt_invalid")
    step = document.get("step")
    maximum = (
        4096 if document.get("model") == "google/functiongemma-270m-it" else MAX_UPDATES
    )
    if type(step) is not int or not 1 <= step <= maximum:
        raise ValueError("remote_training_checkpoint_step_invalid")
    return {
        "completed_updates": step,
        "result_checkpoint": receipt.parent.relative_to(directory).as_posix(),
    }


def _artifact_hashes(attempt: Path) -> dict[str, str]:
    names = (
        "adapter_model.safetensors",
        "model.safetensors",
        "checkpoint/receipt.json",
        "identity.json",
        "metrics.json",
        "qualification.json",
    )
    return {
        name: sha256(attempt / "result" / name)
        for name in names
        if (attempt / "result" / name).exists()
    }


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
        or type(proof.get("attempt")) is not int
        or proof.get("attempt") != attempt
        or proof.get("status") not in tuple(TERMINAL)
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
                "model.safetensors",
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
