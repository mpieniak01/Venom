"""Build explicit training input from admitted Granite splits only."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    load_dataset,
)

from .bundles import (
    _source,
    create_bundle,
    safe_relative,
    validate_identity,
    validate_run_id,
)
from .host import code_identity, dependencies_identity, tokenizer_identity
from .paths import operator_path

DATA_FILES = (
    "domain/train.jsonl",
    "domain/validation.jsonl",
    "hf/train.jsonl",
    "hf/validation.jsonl",
)


def _copy_inputs(source: Path, staging: Path) -> None:
    """Constrain both read and write paths before admitting fixed split files."""
    source_root = operator_path(source).resolve(strict=True)
    staging_root = operator_path(staging).resolve(strict=True)
    for name in DATA_FILES:
        relative = safe_relative(name)
        origin = _source(source_root, relative)
        target = operator_path(staging_root / relative)
        if not origin.resolve().is_relative_to(
            source_root
        ) or not target.is_relative_to(staging_root):
            raise ValueError("remote_training_split_path_escape")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)


def prepare(
    source: Path,
    manifest: Path,
    profile_path: Path,
    snapshot: Path,
    output: Path,
    *,
    run_id: str,
    dataset: str = "domain",
    updates: int = 100,
    max_seconds: int = 3600,
) -> dict:
    """No raw chats, model weights, test splits, Git histories or arbitrary files."""
    if (
        dataset not in {"domain", "hf", "mixed"}
        or type(updates) is not int
        or not 1 <= updates <= 256
    ):
        raise ValueError("remote_training_budget_invalid")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 86400:
        raise ValueError("remote_training_time_budget_invalid")
    validate_run_id(run_id)
    source = operator_path(source)
    manifest = operator_path(manifest)
    profile_path = operator_path(profile_path)
    snapshot = operator_path(snapshot, allow_symlinks=True)
    output = operator_path(output)
    document = json.loads(manifest.read_text())
    raw = json.loads(profile_path.read_text())
    raw.pop("schema_version", None)
    profile = TrainingProfile(**raw)
    profile.validate()
    if snapshot.name != profile.revision:
        raise ValueError("remote_training_snapshot_revision_mismatch")
    rows = []
    for family in ("domain", "hf"):
        train, val = load_dataset(source, document, family)
        rows.extend(train + val)
    # Deferred import: packaging can use the qualified tokenizer component, not CUDA.
    from transformers import AutoTokenizer

    from venom_core.services.granite_operator.engine import encoded_rows

    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    encoding_sha = digest(encoded_rows(rows, tokenizer, profile))
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    code_root = Path(__file__).resolve().parents[3]
    identity = {
        "model": profile.model,
        "revision": profile.revision,
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(document),
        "code_sha256": code_identity(code_root),
        "dependencies_sha256": dependencies_identity(code_root),
        "encoding_sha256": encoding_sha,
        "dataset": dataset,
        "limits": {"max_updates": updates, "max_seconds": max_seconds},
    }
    validate_identity(identity)
    with tempfile.TemporaryDirectory(prefix="venom-training-input-") as temporary:
        staging = Path(temporary)
        with (staging / "profile.json").open("w") as stream:
            json.dump(profile.identity(), stream)
        with (staging / "data-manifest.json").open("w") as stream:
            json.dump(document, stream)
        _copy_inputs(source, staging)
        return create_bundle(
            staging,
            ["profile.json", "data-manifest.json", *DATA_FILES],
            output,
            run_id=run_id,
            identity=identity,
        )
