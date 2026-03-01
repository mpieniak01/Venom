"""Global data-isolation contract for optional modules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from venom_core.config import SETTINGS
from venom_core.core.environment_policy import ensure_data_mutation_allowed

ALLOWED_STORAGE_MODES = {"core_prefixed"}
ALLOWED_MUTATION_GUARDS = {"core_environment_policy"}
MODULE_ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")


@dataclass(frozen=True)
class ModuleDataPolicy:
    storage_mode: str
    mutation_guard: str
    state_files: tuple[str, ...]


def _normalize_module_id(module_id: str) -> str:
    safe_module_id = module_id.strip().lower().replace(" ", "_")
    if not safe_module_id:
        raise ValueError("module_id must be non-empty")
    if not MODULE_ID_PATTERN.fullmatch(safe_module_id):
        raise ValueError("module_id contains invalid characters")
    return safe_module_id


def _storage_scope(settings: object) -> str:
    prefix = str(getattr(settings, "STORAGE_PREFIX", "") or "").strip().strip("/")
    if prefix:
        return prefix
    role = str(getattr(settings, "ENVIRONMENT_ROLE", "dev") or "").strip().lower()
    return "preprod" if role == "preprod" else "dev"


def _validate_data_policy_flags(
    *,
    module_id: str,
    storage_mode: str,
    mutation_guard: str,
) -> list[str]:
    errors: list[str] = []
    if storage_mode not in ALLOWED_STORAGE_MODES:
        errors.append(
            f"{module_id}: backend.data_policy.storage_mode must be one of "
            f"{sorted(ALLOWED_STORAGE_MODES)}"
        )
    if mutation_guard not in ALLOWED_MUTATION_GUARDS:
        errors.append(
            f"{module_id}: backend.data_policy.mutation_guard must be one of "
            f"{sorted(ALLOWED_MUTATION_GUARDS)}"
        )
    return errors


def _parse_state_files(
    *, module_id: str, raw_state_files: Any
) -> tuple[list[str], list[str]]:
    if not isinstance(raw_state_files, list):
        return [], [f"{module_id}: backend.data_policy.state_files must be a list"]

    errors: list[str] = []
    state_files: list[str] = []
    for idx, item in enumerate(raw_state_files):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                f"{module_id}: backend.data_policy.state_files[{idx}] "
                "must be non-empty string"
            )
            continue

        file_name = item.strip()
        file_path = Path(file_name)
        if file_path.is_absolute() or ".." in file_path.parts:
            errors.append(
                f"{module_id}: backend.data_policy.state_files[{idx}] "
                "must be relative filename without parent traversal"
            )
            continue
        state_files.append(file_name)
    return state_files, errors


def parse_module_data_policy_payload(
    *, module_id: str, payload: Any
) -> tuple[ModuleDataPolicy | None, list[str]]:
    if not isinstance(payload, Mapping):
        return None, [f"{module_id}: backend.data_policy must be an object"]

    storage_mode = str(payload.get("storage_mode", "") or "").strip()
    mutation_guard = str(payload.get("mutation_guard", "") or "").strip()
    raw_state_files = payload.get("state_files")

    errors = _validate_data_policy_flags(
        module_id=module_id,
        storage_mode=storage_mode,
        mutation_guard=mutation_guard,
    )
    state_files, state_file_errors = _parse_state_files(
        module_id=module_id,
        raw_state_files=raw_state_files,
    )
    errors.extend(state_file_errors)

    if errors:
        return None, errors

    return (
        ModuleDataPolicy(
            storage_mode=storage_mode,
            mutation_guard=mutation_guard,
            state_files=tuple(state_files),
        ),
        [],
    )


def resolve_module_data_root(
    *, module_id: str, settings: object = SETTINGS, base_dir: Path | None = None
) -> Path:
    safe_module_id = _normalize_module_id(module_id)
    root = (base_dir or Path("./data/modules")).resolve()
    return root / _storage_scope(settings) / safe_module_id


def resolve_module_state_path(
    *,
    module_id: str,
    file_name: str,
    settings: object = SETTINGS,
    base_dir: Path | None = None,
) -> Path:
    cleaned = file_name.strip()
    if not cleaned:
        raise ValueError("file_name must be non-empty")
    file_path = Path(cleaned)
    if file_path.is_absolute() or ".." in file_path.parts:
        raise ValueError("file_name must be a safe relative path")
    return (
        resolve_module_data_root(
            module_id=module_id,
            settings=settings,
            base_dir=base_dir,
        )
        / file_path
    )


def ensure_module_mutation_allowed(
    *,
    module_id: str,
    operation_name: str,
) -> None:
    safe_module_id = _normalize_module_id(module_id)
    ensure_data_mutation_allowed(f"module.{safe_module_id}.{operation_name}")
