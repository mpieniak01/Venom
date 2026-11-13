"""Resolve immutable, operator-installed Omni LoRA inputs by catalog ID."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.academy.omni_pl_chat_adapter import (
    ADAPTER_CONFIG,
    ADAPTER_WEIGHTS,
    HANDOFF_FIELDS,
    verify_initial_adapter,
)
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.services.remote_training.lifecycle import validate_run_id
from venom_core.services.remote_training.paths import operator_path

from .profiles import digest, read_json
from .quality_schema import Digest, EvidenceLabel, RecordId

_INVALID = "experiment_initial_adapter_invalid"
_MISSING = "experiment_initial_adapter_missing"
_CHANGED = "experiment_initial_adapter_changed"
_INCOMPATIBLE = "experiment_initial_adapter_incompatible"


class AdapterSource(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    identity: EvidenceLabel
    sha256: Digest


class AdapterEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal[1]
    adapter_id: RecordId
    label: EvidenceLabel
    model: EvidenceLabel
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    snapshot_sha256: Digest
    config_sha256: Digest
    weights_sha256: Digest
    source: AdapterSource


def _entry(root: Path, adapter_id: str) -> tuple[Path, dict]:
    try:
        validate_run_id(adapter_id)
        directory = operator_path(root / "adapters" / adapter_id)
        if not directory.exists():
            raise ValueError(_MISSING)
        if not directory.is_dir():
            raise ValueError(_INVALID)
        paths = {
            name: operator_path(directory / name)
            for name in ("adapter.json", "hashes.json", ADAPTER_CONFIG, ADAPTER_WEIGHTS)
        }
        if not all(path.is_file() for path in paths.values()):
            raise ValueError(_INVALID)
        entry = AdapterEntry.model_validate(read_json(paths["adapter.json"]))
    except ValueError as exc:
        if str(exc) == _MISSING:
            raise
        raise ValueError(_INVALID) from exc
    if entry.adapter_id != adapter_id:
        raise ValueError(_INVALID)
    expected = {
        ADAPTER_CONFIG: entry.config_sha256,
        ADAPTER_WEIGHTS: entry.weights_sha256,
    }
    try:
        unchanged = read_json(paths["hashes.json"]) == expected and all(
            digest(paths[name]) == checksum for name, checksum in expected.items()
        )
    except ValueError as exc:
        raise ValueError(_CHANGED) from exc
    if not unchanged:
        raise ValueError(_CHANGED)
    pin = read_json(SNAPSHOT_PIN)
    if (
        entry.model != pin["repo"]
        or entry.revision != pin["revision"]
        or entry.snapshot_sha256 != digest(SNAPSHOT_PIN)
    ):
        raise ValueError(_INCOMPATIBLE)
    return directory, entry.model_dump(mode="json")


def list_adapters(root: Path) -> list[dict]:
    result = []
    for directory in sorted(operator_path(root / "adapters").glob("*")):
        try:
            _, entry = _entry(root, directory.name)
        except (OSError, ValueError):
            continue
        result.append(entry)
    return result


def resolve_adapter(root: Path, adapter_id: str, recipe: dict) -> tuple[Path, dict]:
    directory, entry = _entry(root, adapter_id)
    try:
        verify_initial_adapter(directory, runner_identity(entry), recipe)
    except ValueError as exc:
        raise ValueError(_CHANGED if str(exc) == _CHANGED else _INCOMPATIBLE) from exc
    return directory, entry


def verify_adapter_entry(root: Path, expected: dict, recipe: dict) -> Path:
    directory, entry = resolve_adapter(root, expected["adapter_id"], recipe)
    if entry != expected:
        raise ValueError(_CHANGED)
    return directory


def runner_identity(entry: dict) -> dict:
    return {key: entry[key] for key in HANDOFF_FIELDS}
