"""Result collection receipts: verified transport never implies model acceptance."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .bundles import (
    MAX_BYTES,
    _source,
    canonical,
    create_bundle,
    extract_bundle,
    sha256,
    validate_identity,
    validate_run_id,
)

DATA_MANIFEST = "data-manifest.json"
ADAPTER_CONFIG = "adapter_config.json"
MODEL_WEIGHTS = "model.safetensors"
MODEL_CONFIG = "config.json"


REQUIRED_FILES = (
    "adapter_model.safetensors",
    ADAPTER_CONFIG,
    "identity.json",
    "profile.json",
    DATA_MANIFEST,
    "metrics.json",
    "environment.json",
    "qualification.json",
    "status.json",
    "supervisor.json",
    "logs/training.log",
)
_EXTRA_FILES = (
    MODEL_WEIGHTS,
    MODEL_CONFIG,
    "generation_config.json",
    "error.json",
    "metrics.jsonl",
    "logs/stdout.log",
    "logs/stderr.log",
    "logs/coordinator.log",
)
_CHECKPOINT_SUFFIXES = {
    ".safetensors",
    ".json",
    ".pt",
    ".pth",
    ".jinja",
    ".txt",
    ".model",
}


def _files(root: Path, include_checkpoint: bool) -> list[str]:
    selected = []
    for name in REQUIRED_FILES + _EXTRA_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError("remote_training_artifact_symlink")
        if path.is_file():
            _source(root, name)
            selected.append(name)
    if include_checkpoint:
        checkpoint = root / "checkpoint"
        if checkpoint.is_symlink():
            raise ValueError("remote_training_artifact_symlink")
        if not (checkpoint / "receipt.json").is_file():
            for stage in ("train-resume", "train-first", "smoke-resume", "smoke-first"):
                candidate = root / "stages" / stage / "checkpoint"
                receipt = candidate / "receipt.json"
                if candidate.is_symlink() or receipt.is_symlink():
                    raise ValueError("remote_training_artifact_symlink")
                if receipt.is_file():
                    _source(root, receipt.relative_to(root).as_posix())
                    checkpoint = candidate
                    break
        if checkpoint.exists():
            for path in sorted(checkpoint.rglob("*")):
                if path.is_symlink():
                    raise ValueError("remote_training_artifact_symlink")
                allowed = (
                    path.suffix in _CHECKPOINT_SUFFIXES
                    or path == checkpoint / "README.md"
                )
                if path.is_file() and allowed:
                    name = path.relative_to(root).as_posix()
                    _source(root, name)
                    selected.append(name)
    return selected


def _document(root: Path, name: str, errors: list[str]) -> dict[str, Any]:
    path = root / name
    if not path.exists():
        return {}
    try:
        limit = 256 * 1024**2 if name == DATA_MANIFEST else 8 * 1024**2
        if path.stat().st_size > limit:
            raise ValueError("metadata_size")
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("metadata_type")
        canonical(value)
        return value
    except (OSError, UnicodeError, ValueError):
        errors.append("invalid_metadata:" + name)
        return {}


def required_files(identity):
    if (
        identity.get("model") == "google/functiongemma-270m-it"
        and identity.get("training_method") == "full"
    ):
        return tuple(
            name
            for name in REQUIRED_FILES
            if name not in {"adapter_model.safetensors", ADAPTER_CONFIG}
        ) + (MODEL_WEIGHTS, MODEL_CONFIG)
    return REQUIRED_FILES


def inspect_artifacts(
    root: Path,
    identity: dict[str, Any],
    run_id: str,
    *,
    include_checkpoint: bool = False,
) -> dict[str, Any]:
    """Inventory evidence, preserving failed/incomplete outcomes and reload gate."""
    root = Path(root)
    portable = validate_identity(identity)
    validate_run_id(run_id)
    selected = _files(root, include_checkpoint)
    required = required_files(portable)
    missing = sorted(set(required) - set(selected))
    errors: list[str] = []
    documents = {
        name: _document(root, name, errors)
        for name in required
        if name.endswith(".json")
    }
    actual_identity = documents["identity.json"]
    if "identity.json" not in missing and actual_identity != portable:
        errors.append("identity_mismatch")
    status = documents["status.json"]
    state = status.get("state", "unknown")
    if state not in {"succeeded", "failed", "stopped"}:
        errors.append("status_invalid")
    if status and status.get("run_id") != run_id:
        errors.append("run_id_mismatch")
    if type(status.get("exit_code")) is not int:
        errors.append("exit_code_missing")
    qualification = documents["qualification.json"]
    if "qualification.json" not in missing and qualification.get("status") != "PASS":
        errors.append("qualification_not_passed")
    if (
        "adapter_model.safetensors" in selected
        and (root / "adapter_model.safetensors").stat().st_size == 0
    ):
        errors.append("adapter_empty")
    if MODEL_WEIGHTS in selected and (root / MODEL_WEIGHTS).stat().st_size == 0:
        errors.append("model_empty")
    for name in (
        MODEL_CONFIG,
        ADAPTER_CONFIG,
        "metrics.json",
        "environment.json",
        "profile.json",
        DATA_MANIFEST,
    ):
        if name in required and name not in missing and not documents[name]:
            errors.append("metadata_empty:" + name)
    supervisor = documents["supervisor.json"]
    if supervisor and (
        supervisor.get("run_id") != run_id
        or type(supervisor.get("attempt")) is not int
        or supervisor["attempt"] < 1
        or supervisor.get("status")
        not in {"succeeded", "failed", "stopped", "timed_out"}
        or type(supervisor.get("exit_code")) is not int
    ):
        errors.append("supervisor_invalid")
    complete = (
        not missing
        and not errors
        and supervisor.get("status") == "succeeded"
        and supervisor.get("exit_code") == 0
        and state == "succeeded"
        and status.get("exit_code") == 0
    )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "identity": portable,
        "status": state,
        "supervisor": supervisor,
        "complete": complete,
        "missing": missing,
        "errors": sorted(errors),
        "files": {
            name: {"sha256": sha256(root / name), "size": (root / name).stat().st_size}
            for name in selected
        },
        "local_reload_required": True,
        "activation_authorized": False,
        "destroy_authorized": False,
    }


def create_result_bundle(
    root: Path,
    destination: Path,
    *,
    run_id: str,
    identity: dict[str, Any],
    include_checkpoint: bool = False,
    max_bytes: int = MAX_BYTES,
    supervisor: dict | None = None,
    coordinator_log: Path | None = None,
) -> dict[str, Any]:
    """Snapshot worker evidence together with the final supervisor outcome."""
    root, destination = Path(root), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".result-evidence-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary)
        for name in _files(root, include_checkpoint):
            if name == "supervisor.json" and supervisor is not None:
                continue
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.link(_source(root, name), target)
        if supervisor is not None:
            proof = {
                key: supervisor.get(key)
                for key in ("run_id", "attempt", "status", "exit_code")
            }
            (staged / "supervisor.json").write_bytes(canonical(proof))
        if coordinator_log is not None and coordinator_log.exists():
            if coordinator_log.is_symlink():
                raise ValueError("remote_training_artifact_symlink")
            target = staged / "logs/coordinator.log"
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Never truncate an existing source hard link.
            target.unlink(missing_ok=True)
            with coordinator_log.open("rb") as source:
                source.seek(max(0, coordinator_log.stat().st_size - 1024**2))
                target.write_bytes(source.read(1024**2))
        receipt = inspect_artifacts(
            staged, identity, run_id, include_checkpoint=include_checkpoint
        )
        return create_bundle(
            staged,
            list(receipt["files"]),
            destination,
            run_id=run_id,
            identity=identity,
            kind="result",
            max_bytes=max_bytes,
            receipt=receipt,
        )


def verify_result_bundle(
    archive: Path,
    *,
    expected_identity: dict[str, Any],
    expected_run_id: str,
    max_bytes: int = MAX_BYTES,
) -> dict[str, Any]:
    """Recompute completeness after quarantine; trust no remote success flag alone."""
    with tempfile.TemporaryDirectory(prefix="remote-training-result-") as temporary:
        destination = Path(temporary) / "verified"
        manifest = extract_bundle(
            archive,
            destination,
            expected_identity=expected_identity,
            expected_run_id=expected_run_id,
            max_bytes=max_bytes,
        )
        if manifest["kind"] != "result":
            raise ValueError("remote_training_result_kind_invalid")
        checkpoint = any(
            name.startswith(("checkpoint/", "stages/")) for name in manifest["files"]
        )
        receipt = inspect_artifacts(
            destination,
            expected_identity,
            expected_run_id,
            include_checkpoint=checkpoint,
        )
        if manifest.get("receipt") != receipt:
            raise ValueError("remote_training_result_receipt_mismatch")
        return receipt
