"""Quarantine remote adapters; register only after a fresh trusted local reload."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import inspect_artifacts, verify_result_bundle
from .bundles import (
    MANIFEST_NAME,
    canonical,
    extract_bundle,
    sha256,
    validate_identity,
    validate_run_id,
    verify_directory,
)
from .paths import operator_path

ReloadVerifier = Callable[[Path, dict[str, Any]], dict[str, Any]]


def _current(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = operator_path(root)
    marker = root / MANIFEST_NAME
    if root.is_symlink() or marker.is_symlink() or not marker.is_file():
        raise ValueError("remote_training_import_manifest_missing")
    manifest = json.loads(marker.read_text())
    if manifest.get("kind") != "result":
        raise ValueError("remote_training_import_kind_invalid")
    identity = validate_identity(manifest.get("identity"))
    verify_directory(root, manifest)
    checkpoint = any(
        name.startswith(("checkpoint/", "stages/")) for name in manifest["files"]
    )
    receipt = inspect_artifacts(
        root, identity, manifest["run_id"], include_checkpoint=checkpoint
    )
    if manifest.get("receipt") != receipt:
        raise ValueError("remote_training_import_receipt_mismatch")
    return manifest, receipt


def _register(registry: Path, record: dict[str, Any]) -> None:
    validate_run_id(record.get("run_id"))
    registry = operator_path(registry)
    if registry.is_symlink():
        raise ValueError("remote_training_registry_symlink")
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = operator_path(registry / (record["run_id"] + ".json"))
    if destination.parent != registry:
        raise ValueError("remote_training_registry_path_escape")
    with tempfile.TemporaryDirectory(prefix=".remote-import-", dir=registry) as folder:
        staged = Path(folder) / "metadata.json"
        staged.write_bytes(canonical(record))
        staged.chmod(0o600)
        try:
            os.link(staged, destination)
        except FileExistsError:
            if (
                destination.is_symlink()
                or json.loads(destination.read_text()) != record
            ):
                raise ValueError("remote_training_registry_conflict") from None


def _academy_register(
    root: Path, models: Path, manifest: dict[str, Any], proof: dict[str, Any]
) -> Path:
    """Publish the existing Academy directory/metadata contract, without signing chat."""
    validate_run_id(manifest.get("run_id"))
    root = operator_path(root)
    models = operator_path(models)
    from venom_core.services.academy.adapter_metadata_service import (
        AdapterMetadataContext,
        build_canonical_adapter_metadata,
        write_canonical_adapter_metadata,
    )

    if models.is_symlink():
        raise ValueError("remote_training_academy_symlink")
    models.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = operator_path(models / manifest["run_id"])
    if destination.parent != models:
        raise ValueError("remote_training_academy_path_escape")
    provenance = {
        "identity": manifest["identity"],
        "local_verification": proof,
        "manifest_sha256": manifest["manifest_sha256"],
        "local_resume_authorized": False,
    }
    payload = build_canonical_adapter_metadata(
        adapter_id=manifest["run_id"],
        base_model=manifest["identity"]["model"],
        created_at=datetime.now(timezone.utc).isoformat(),
        source_flow="remote_training",
        training_params=json.loads((root / "profile.json").read_text()),
        context=AdapterMetadataContext(run_id=manifest["run_id"]),
    )
    payload["remote_training"] = provenance
    payload["base_model_revision"] = manifest["identity"]["revision"]
    descriptor = os.open(
        models / ".remote-training-import.lock",
        os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink():
                raise ValueError("remote_training_academy_conflict")
            metadata = destination / "metadata.json"
            if metadata.is_symlink() or not metadata.is_file():
                raise ValueError("remote_training_academy_conflict")
            saved = json.loads(metadata.read_text())
            if (
                saved.get("remote_training") != provenance
                or saved.get("base_model") != payload["base_model"]
                or saved.get("metadata_version") != payload["metadata_version"]
                or saved.get("source_flow") != "remote_training"
                or "chat_signature" in saved
            ):
                raise ValueError("remote_training_academy_conflict")
            for name in ("adapter_model.safetensors", "adapter_config.json"):
                target = destination / "adapter" / name
                if (
                    target.is_symlink()
                    or (destination / "adapter").is_symlink()
                    or not target.is_file()
                ):
                    raise ValueError("remote_training_academy_conflict")
                if sha256(target) != manifest["files"][name]["sha256"]:
                    raise ValueError("remote_training_academy_conflict")
            return destination
        with tempfile.TemporaryDirectory(
            prefix=".remote-training-import-", dir=models.parent
        ) as temporary:
            staged = Path(temporary) / manifest["run_id"]
            (staged / "adapter").mkdir(parents=True, mode=0o700)
            for name in ("adapter_model.safetensors", "adapter_config.json"):
                target = staged / "adapter" / name
                shutil.copyfile(root / name, target)
                target.chmod(0o600)
                if sha256(target) != manifest["files"][name]["sha256"]:
                    raise ValueError("remote_training_academy_copy_changed")
            write_canonical_adapter_metadata(adapter_dir=staged, payload=payload)
            (staged / "metadata.json").chmod(0o600)
            staged.rename(destination)
    finally:
        os.close(descriptor)
    return destination


def finalize_import(
    root: Path,
    registry: Path,
    verifier: ReloadVerifier,
    *,
    academy_models: Path | None = None,
) -> dict[str, Any]:
    """Invoke a trusted function now; a receipt uploaded by the host is insufficient."""
    if not callable(verifier):
        raise ValueError("remote_training_local_reload_required")
    root, registry = operator_path(root), operator_path(registry)
    if academy_models is not None:
        academy_models = operator_path(academy_models)
    manifest, receipt = _current(root)
    if not receipt["complete"]:
        raise ValueError("remote_training_incomplete_import")
    identity = manifest["identity"]
    identity_checksum = hashlib.sha256(canonical(identity)).hexdigest()
    adapter_checksum = sha256(root / "adapter_model.safetensors")
    proof = verifier(root, identity)
    if (
        not isinstance(proof, dict)
        or proof.get("status") != "PASS"
        or proof.get("runtime_verified") is not True
        or proof.get("identity_sha256") != identity_checksum
        or proof.get("adapter_sha256") != adapter_checksum
    ):
        raise ValueError("remote_training_local_reload_failed")
    # A callback cannot replace bytes or amend the foreign checkpoint fingerprint.
    repeated, _ = _current(root)
    if repeated != manifest:
        raise ValueError("remote_training_import_changed_during_reload")
    verified = {
        "status": "PASS",
        "runtime_verified": True,
        "identity_sha256": identity_checksum,
        "adapter_sha256": adapter_checksum,
    }
    record = {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "model": identity["model"],
        "revision": identity["revision"],
        "identity": identity,
        "identity_sha256": identity_checksum,
        "adapter_sha256": adapter_checksum,
        "adapter_path": str(root.resolve()),
        "local_verification": verified,
        "activation_authorized": False,
        "local_resume_authorized": False,
    }
    academy_path = (
        _academy_register(root, Path(academy_models), manifest, verified)
        if academy_models is not None
        else None
    )
    _register(registry, record)
    return {
        **receipt,
        "import_status": "registered",
        "academy_registered": academy_path is not None,
        "academy_path": str(academy_path) if academy_path else None,
        "registered": True,
        "quarantine_path": str(root.resolve()),
        "local_verification": verified,
        "local_reload_required": False,
        "activation_authorized": False,
        "local_resume_authorized": False,
        "destroy_authorized": False,
    }


def import_result(
    archive: Path,
    quarantine: Path,
    registry: Path,
    expected_identity: dict[str, Any],
    run_id: str,
    reload_verifier: ReloadVerifier | None = None,
    *,
    academy_models: Path | None = None,
) -> dict[str, Any]:
    """Verify complete transfer even for failed runs; keep pending adapters inactive."""
    validate_run_id(run_id)
    archive = operator_path(archive)
    quarantine = operator_path(quarantine)
    registry = operator_path(registry)
    if academy_models is not None:
        academy_models = operator_path(academy_models)
    receipt = verify_result_bundle(
        archive, expected_identity=expected_identity, expected_run_id=run_id
    )
    # Keep every attempt immutable while deduplicating exact bundle retries.
    root = operator_path(quarantine / run_id / sha256(archive))
    if not root.is_relative_to(quarantine):
        raise ValueError("remote_training_quarantine_path_escape")
    extract_bundle(
        archive, root, expected_identity=expected_identity, expected_run_id=run_id
    )
    if not receipt["complete"]:
        return {
            **receipt,
            "import_status": "incomplete",
            "registered": False,
            "quarantine_path": str(root.resolve()),
        }
    if reload_verifier is None:
        return {
            **receipt,
            "import_status": "pending_local_reload",
            "registered": False,
            "quarantine_path": str(root.resolve()),
        }
    return finalize_import(
        root, registry, reload_verifier, academy_models=academy_models
    )
