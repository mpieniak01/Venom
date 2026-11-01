"""Granite preflight and normalization; same encoder/worker as local G01."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    load_dataset,
    write_json,
)

from .host import code_identity, dependencies_identity, tokenizer_identity


def preflight(
    host: dict, input_root: Path, identity: dict
) -> tuple[TrainingProfile, dict]:
    from transformers import AutoTokenizer

    from venom_core.services.granite_operator.engine import encoded_rows

    if Path(__file__).resolve().parents[3] != Path(host["code_root"]).resolve():
        raise ValueError("remote_training_imported_code_mismatch")
    profile = TrainingProfile(**json.loads((input_root / "profile.json").read_text()))
    profile.validate()
    document = json.loads((input_root / "data-manifest.json").read_text())
    snapshot = Path(host["snapshot"])
    source = Path(host["code_root"])
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    actual = {
        "model": profile.model,
        "revision": profile.revision,
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(document),
        "code_sha256": code_identity(source),
        "dependencies_sha256": dependencies_identity(source),
    }
    if snapshot.name != profile.revision or any(
        identity.get(key) != value for key, value in actual.items()
    ):
        raise ValueError("remote_training_identity_mismatch")
    rows = []
    for family in ("domain", "hf"):
        train, validation = load_dataset(input_root, document, family)
        rows.extend(train + validation)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    if digest(encoded_rows(rows, tokenizer, profile)) != identity.get(
        "encoding_sha256"
    ):
        raise ValueError("remote_training_native_encoding_mismatch")
    return profile, document


def normalized(
    result: Path,
    stage: Path,
    identity: dict,
    profile: dict,
    document: dict,
    metrics: dict,
    environment: dict,
    *,
    run_id: str,
) -> None:
    """Expose portable inference artifacts separately from host-bound resume state."""
    checkpoint = stage / "checkpoint"
    for name in ("adapter_model.safetensors", "adapter_config.json"):
        shutil.copyfile(checkpoint / name, result / name)
    for name, value in [
        ("identity.json", identity),
        ("profile.json", profile),
        ("data-manifest.json", document),
        ("metrics.json", metrics),
        ("environment.json", environment),
        ("status.json", {"state": "succeeded", "run_id": run_id, "exit_code": 0}),
    ]:
        write_json(result / name, value)
    # Full resume state is explicit and optional at collection; no host fingerprint rewrite.
    shutil.copytree(checkpoint, result / "checkpoint")
