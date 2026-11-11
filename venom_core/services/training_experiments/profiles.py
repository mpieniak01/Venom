"""Operator-installed profiles are the only source of model and data paths."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from venom_core.services.remote_training.lifecycle import validate_run_id
from venom_core.services.remote_training.paths import operator_path

MODEL = "LiquidAI/LFM3-Omni-2B"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_JSON_BYTES = 8 * 1024 * 1024


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int = 1
    label: str = Field(min_length=1, max_length=120)
    model: str = MODEL
    dataset: str = Field(min_length=1, max_length=120)
    snapshot: str
    training_venv: str
    train: str
    dev: str
    train_sha256: str = Field(pattern=SHA256_PATTERN)
    dev_sha256: str = Field(pattern=SHA256_PATTERN)
    recipe: dict[str, Any] = Field(default_factory=dict)
    max_seconds: int = Field(default=1800, ge=30, le=86400)
    min_free_bytes: int = Field(default=1073741824, ge=1)
    backing_volume: str | None = None
    calibration_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


def digest(path: Path) -> str:
    with operator_path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> Any:
    path = operator_path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("experiment_input_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    path = operator_path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("experiment_input_too_large")
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records or not all(isinstance(row, dict) for row in records):
        raise ValueError("experiment_invalid_records")
    return records


def stable_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def recipe_for(profile: Profile, overrides: dict | None) -> dict:
    # The worker checks the same recipe; it also binds the actual train hash.
    from scripts.academy.omni_pl_chat_recipe import validate_recipe

    parameters = dict(profile.recipe)
    if overrides:
        parameters.update(overrides)
    parameters["train_sha256"] = profile.train_sha256
    return validate_recipe(parameters)


def load_profile(root: Path, profile_id: str) -> tuple[Profile, str]:
    validate_run_id(profile_id)
    path = root / "profiles" / f"{profile_id}.json"
    raw = read_json(path)
    profile = Profile.model_validate(raw)
    if profile.schema_version != 1 or profile.model != MODEL:
        raise ValueError("experiment_profile_unsupported")
    return profile, stable_hash(raw)


def resolve_input(root: Path, value: str) -> Path:
    path = Path(value)
    return operator_path(path if path.is_absolute() else root / path)


def check_inputs(root: Path, profile: Profile) -> None:
    train = resolve_input(root, profile.train)
    dev = resolve_input(root, profile.dev)
    if train == dev or profile.train_sha256 == profile.dev_sha256:
        raise ValueError("experiment_overlapping_splits")
    if digest(train) != profile.train_sha256 or digest(dev) != profile.dev_sha256:
        raise ValueError("experiment_data_changed")
    training, development = rows(train), rows(dev)
    for data, split in ((training, "train"), (development, "dev")):
        keys = [row.get("record_id") for row in data]
        if any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("experiment_missing_record_id")
        if len(set(keys)) != len(data) or any(
            row.get("split") != split for row in data
        ):
            raise ValueError("experiment_invalid_split")
    for key in ("record_id", "group_id"):
        left = {item.get(key) for item in training}
        right = {item.get(key) for item in development}
        if not all(isinstance(value, str) and value for value in left | right):
            raise ValueError("experiment_missing_group")
        if left & right:
            raise ValueError("experiment_overlapping_splits")
    if not resolve_input(root, profile.snapshot).is_dir():
        raise ValueError("experiment_snapshot_missing")
    if not (resolve_input(root, profile.training_venv) / "bin/python").is_file():
        raise ValueError("experiment_training_python_missing")
