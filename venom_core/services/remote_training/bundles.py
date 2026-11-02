"""Bounded, explicit-file ZIP transfer with canonical portable identities."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import operator_path

MAX_BYTES = 100 * 1024**3
MAX_FILES = 10000
MANIFEST_NAME = ".bundle-manifest.json"
_HASH_FIELDS = (
    "tokenizer_sha256",
    "template_sha256",
    "profile_sha256",
    "data_sha256",
    "code_sha256",
    "dependencies_sha256",
)
_SECRET_PARTS = {".git", ".ssh", ".codex", "secrets", "credentials", "__pycache__"}


def canonical(value: Any) -> bytes:
    """Produce deterministic JSON; reject NaN and non-JSON identity values."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sha256(path: Path) -> str:
    """Hash large artifacts without reading them entirely into memory."""
    path = operator_path(path)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_run_id(run_id: object) -> None:
    """Keep job names portable and prevent access to adjacent sessions."""
    if (
        not isinstance(run_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id) is None
    ):
        raise ValueError("remote_training_run_id_invalid")


def validate_identity(identity: object) -> dict[str, Any]:
    """Keep portable model/data/code identity separate from host credentials."""
    if (
        not isinstance(identity, Mapping)
        or not isinstance(identity.get("model"), str)
        or not identity["model"]
    ):
        raise ValueError("remote_training_identity_invalid")
    if re.fullmatch(r"[a-f0-9]{40}", str(identity.get("revision", ""))) is None:
        raise ValueError("remote_training_revision_invalid")
    for field in _HASH_FIELDS:
        if re.fullmatch(r"[a-f0-9]{64}", str(identity.get(field, ""))) is None:
            raise ValueError("remote_training_identity_hash_invalid:" + field)

    def inspect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if (
                    not isinstance(key, str)
                    or key.lower()
                    in {
                        "token",
                        "hf_token",
                        "access_token",
                        "authorization",
                        "private_key",
                        "ssh_key",
                    }
                    or any(
                        word in key.lower()
                        for word in (
                            "password",
                            "api_key",
                            "token_secret",
                            "credential",
                            "identity_file",
                            "known_hosts",
                            "hostname",
                        )
                    )
                ):
                    raise ValueError("remote_training_identity_secret_field")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
        elif isinstance(value, str) and (
            value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value)
        ):
            raise ValueError("remote_training_identity_host_path")

    inspect(identity)
    return json.loads(canonical(dict(identity)))


def safe_relative(name: str) -> str:
    """Accept one canonical POSIX relative name on Windows and Linux."""
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or ":" in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("remote_training_path_invalid")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or str(path) != name
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("remote_training_path_invalid")
    if any(
        part.lower() in _SECRET_PARTS or part.lower().startswith(".env")
        for part in path.parts
    ):
        raise ValueError("remote_training_sensitive_path")
    if name == MANIFEST_NAME:
        raise ValueError("remote_training_reserved_path")
    return name


def _source(root: Path, name: str) -> Path:
    root = operator_path(root)
    relative = safe_relative(name)
    target = root
    for part in PurePosixPath(relative).parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("remote_training_symlink_forbidden")
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("remote_training_source_invalid")
    return target


def _names(names: Sequence[str]) -> list[str]:
    result = [safe_relative(name) for name in names]
    if (
        not result
        or len(result) > MAX_FILES
        or len({name.casefold() for name in result}) != len(result)
    ):
        raise ValueError("remote_training_file_list_invalid")
    selected = set(result)
    if any(
        str(parent) in selected
        for name in result
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    ):
        raise ValueError("remote_training_path_collision")
    return sorted(result)


def _manifest(raw: Any, max_bytes: int) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != 1
        or raw.get("kind") not in {"input", "result"}
    ):
        raise ValueError("remote_training_manifest_invalid")
    validate_run_id(raw.get("run_id"))
    validate_identity(raw.get("identity"))
    files = raw.get("files")
    if not isinstance(files, dict):
        raise ValueError("remote_training_manifest_files_invalid")
    _names(list(files))
    total = 0
    for entry in files.values():
        if not isinstance(entry, dict) or set(entry) != {"sha256", "size"}:
            raise ValueError("remote_training_manifest_entry_invalid")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError("remote_training_manifest_size_invalid")
        if re.fullmatch(r"[a-f0-9]{64}", str(entry["sha256"])) is None:
            raise ValueError("remote_training_manifest_checksum_invalid")
        total += entry["size"]
    if total > max_bytes or raw.get("total_bytes") != total:
        raise ValueError("remote_training_bundle_size_exceeded")
    checksum = hashlib.sha256(
        canonical({k: v for k, v in raw.items() if k != "manifest_sha256"})
    ).hexdigest()
    if raw.get("manifest_sha256") != checksum:
        raise ValueError("remote_training_manifest_checksum_mismatch")
    return raw


def _reuse_archive(destination: Path, manifest: dict[str, Any], max_bytes: int) -> bool:
    if not destination.exists() and not destination.is_symlink():
        return False
    if destination.is_symlink():
        raise FileExistsError("remote_training_archive_conflict")
    try:
        existing = verify_bundle(destination, max_bytes=max_bytes)
    except (OSError, ValueError, zipfile.BadZipFile):
        raise FileExistsError("remote_training_archive_conflict") from None
    if existing != manifest:
        raise FileExistsError("remote_training_archive_conflict")
    return True


def create_bundle(
    source_root: Path,
    files: Sequence[str],
    destination: Path,
    *,
    run_id: str,
    identity: Mapping[str, Any],
    kind: str = "input",
    max_bytes: int = MAX_BYTES,
    receipt: dict | None = None,
) -> dict[str, Any]:
    """Pack only selected regular files; do not overwrite an existing archive."""
    validate_run_id(run_id)
    source_root = operator_path(source_root)
    destination = operator_path(destination)
    entries = {}
    total = 0
    for name in _names(files):
        path = _source(source_root, name)
        size = path.stat().st_size
        total += size
        if total > max_bytes:
            raise ValueError("remote_training_bundle_size_exceeded")
        entries[name] = {"sha256": sha256(path), "size": size}
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "kind": kind,
        "identity": validate_identity(identity),
        "files": entries,
        "total_bytes": total,
    }
    if receipt is not None:
        manifest["receipt"] = receipt
    manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    _manifest(manifest, max_bytes)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".bundle-pack-", dir=destination.parent
    ) as temporary:
        archive_path = Path(temporary) / "bundle.zip"
        archive_path.touch(mode=0o600, exist_ok=False)
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            archive.writestr("manifest.json", canonical(manifest))
            for name in entries:
                archive.write(_source(source_root, name), "payload/" + name)
        verify_bundle(
            archive_path,
            expected_identity=identity,
            expected_run_id=run_id,
            max_bytes=max_bytes,
        )
        # Hard-link publication is atomic and cannot replace a previous archive.
        try:
            os.link(archive_path, destination)
        except FileExistsError:
            if not _reuse_archive(destination, manifest, max_bytes):
                raise
    return manifest


def _open_manifest(archive: zipfile.ZipFile, max_bytes: int) -> dict[str, Any]:
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1 or len({entry.filename for entry in infos}) != len(
        infos
    ):
        raise ValueError("remote_training_archive_duplicate_or_limit")
    names = {entry.filename for entry in infos}
    if "manifest.json" not in names:
        raise ValueError("remote_training_manifest_missing")
    header = archive.getinfo("manifest.json")
    if header.file_size > 1024**2:
        raise ValueError("remote_training_manifest_too_large")
    manifest = _manifest(json.loads(archive.read(header)), max_bytes)
    if names != {"manifest.json", *("payload/" + name for name in manifest["files"])}:
        raise ValueError("remote_training_archive_unlisted_entry")
    for info in infos:
        mode = info.external_attr >> 16
        if (
            info.is_dir()
            or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
            or info.flag_bits & 1
        ):
            raise ValueError("remote_training_archive_special_entry")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ValueError("remote_training_archive_compression_invalid")
        if info.file_size > max_bytes or info.file_size > max(
            1024**2, info.compress_size * 1000
        ):
            raise ValueError("remote_training_archive_expansion_exceeded")
    return manifest


def _copy_verified(
    archive: zipfile.ZipFile, name: str, expected: dict, output=None
) -> None:
    info = archive.getinfo("payload/" + name)
    if info.file_size != expected["size"]:
        raise ValueError("remote_training_archive_size_mismatch")
    checksum = hashlib.sha256()
    total = 0
    with archive.open(info) as source:
        while data := source.read(1024**2):
            total += len(data)
            if total > expected["size"]:
                raise ValueError("remote_training_archive_size_mismatch")
            checksum.update(data)
            if output is not None:
                output.write(data)
    if total != expected["size"] or checksum.hexdigest() != expected["sha256"]:
        raise ValueError("remote_training_payload_checksum_mismatch")


def _expected(
    manifest: dict, identity: Mapping[str, Any] | None, run_id: str | None
) -> None:
    if identity is not None and manifest["identity"] != validate_identity(identity):
        raise ValueError("remote_training_identity_mismatch")
    if run_id is not None and manifest["run_id"] != run_id:
        raise ValueError("remote_training_run_id_mismatch")


def verify_bundle(
    archive_path: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    expected_run_id: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> dict[str, Any]:
    """Read and authenticate every declared payload byte without extraction."""
    archive_path = operator_path(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = _open_manifest(archive, max_bytes)
        _expected(manifest, expected_identity, expected_run_id)
        for name, expected in manifest["files"].items():
            _copy_verified(archive, name, expected)
    return manifest


def verify_directory(destination: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """An upload retry accepts only an unchanged extracted input tree."""
    destination = operator_path(destination)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("remote_training_existing_destination_invalid")
    marker = destination / MANIFEST_NAME
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("remote_training_existing_manifest_missing")
    saved = json.loads(marker.read_text())
    if saved != manifest:
        raise ValueError("remote_training_existing_manifest_mismatch")
    actual = set()
    for item in destination.rglob("*"):
        if item.is_symlink():
            raise ValueError("remote_training_symlink_forbidden")
        if item.is_file() and item != marker:
            actual.add(item.relative_to(destination).as_posix())
    if actual != set(manifest["files"]):
        raise ValueError("remote_training_existing_files_mismatch")
    for name, entry in manifest["files"].items():
        source = _source(destination, name)
        if source.stat().st_size != entry["size"] or sha256(source) != entry["sha256"]:
            raise ValueError("remote_training_existing_payload_changed")
    return manifest


def extract_bundle(
    archive_path: Path,
    destination: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    expected_run_id: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> dict[str, Any]:
    """Verify before publishing a quarantine tree; never replace prior results."""
    destination = operator_path(destination)
    manifest = verify_bundle(
        archive_path,
        expected_identity=expected_identity,
        expected_run_id=expected_run_id,
        max_bytes=max_bytes,
    )
    if destination.exists() or destination.is_symlink():
        verify_directory(destination, manifest)
        return manifest
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".bundle-quarantine-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "payload"
        staged.mkdir(mode=0o700)
        with zipfile.ZipFile(archive_path) as archive:
            repeated = _open_manifest(archive, max_bytes)
            if repeated != manifest:
                raise ValueError("remote_training_archive_changed")
            for name, entry in manifest["files"].items():
                path = staged / name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with path.open("xb") as output:
                    _copy_verified(archive, name, entry, output)
                path.chmod(0o600)
        (staged / MANIFEST_NAME).write_bytes(canonical(manifest))
        # Serialize our publishers; never let rename replace another completed tree.
        lock_name = (
            ".bundle-" + hashlib.sha256(destination.name.encode()).hexdigest() + ".lock"
        )
        descriptor = os.open(
            destination.parent / lock_name,
            os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if destination.exists() or destination.is_symlink():
                verify_directory(destination, manifest)
            else:
                staged.rename(destination)
        finally:
            os.close(descriptor)
    return manifest
