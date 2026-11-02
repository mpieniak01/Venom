"""Bound CPU evidence I/O to operator-owned material and configuration roots."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT_ENV = "GEMMA_OPERATOR_DATA_ROOT"


def _roots(*, profile: bool = False) -> list[Path]:
    roots = [ROOT / "data/training", ROOT / ".venom_runtime/gemma4"]
    approved = os.environ.get(DATA_ROOT_ENV)
    if approved:
        extra = Path(approved)
        if not extra.is_absolute():
            raise ValueError("gemma_operator_data_root_must_be_absolute")
        roots.append(extra)
    if profile:
        roots.append(ROOT / "config")
    return [root.resolve() for root in roots]


def _approved(path: Path, *, profile: bool = False) -> Path:
    lexical = path.absolute()
    if any(part.is_symlink() for part in (lexical, *lexical.parents)):
        raise ValueError("gemma_path_symlink_not_allowed")
    resolved = lexical.resolve()
    if not any(resolved.is_relative_to(root) for root in _roots(profile=profile)):
        raise ValueError("gemma_path_outside_approved_roots")
    return resolved


def checked_file(path: Path, *, profile: bool = False, output: bool = False) -> Path:
    """Reject traversal, symlinks and unsupported file types before file I/O."""
    target = _approved(path, profile=profile)
    if target.suffix != ".json":
        raise ValueError("gemma_json_path_required")
    if output:
        if target.exists():
            raise FileExistsError("gemma_evidence_output_exists")
    elif not target.is_file():
        raise ValueError("gemma_input_file_required")
    return target


def checked_directory(path: Path) -> Path:
    """Constrain materialized snapshot roots as well as the files below them."""
    target = _approved(path)
    if not target.is_dir():
        raise ValueError("gemma_snapshot_directory_required")
    return target
