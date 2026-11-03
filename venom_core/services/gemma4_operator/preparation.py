"""Prepare bounded, immutable Gemma session packages without a host or GPU."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from venom_core.services.remote_training.bundles import (
    create_bundle,
    safe_relative,
    sha256,
    validate_identity,
    validate_run_id,
)
from venom_core.services.remote_training.host import (
    code_identity,
    dependencies_identity,
    tokenizer_identity,
)
from venom_core.services.remote_training.paths import operator_path

from .data_release import build_release
from .encoding import validate_encoded_release
from .identity import bind_ollama
from .material import digest, prepare_material
from .paths import checked_directory, checked_file
from .profile import GemmaProfile
from .training import GemmaTrainingRecipe

Json = dict[str, Any]
MAX_METADATA_BYTES = 64 * 1024 * 1024
INPUT_FILES = ("profile.json", "data-manifest.json", "ollama-binding.json")
INPUT_ARCHIVE = "input.zip"


def _read(path: Path) -> Json:
    target = checked_file(path)
    if target.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("gemma_preparation_metadata_too_large")
    with target.open("rb") as stream:
        data = stream.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError("gemma_preparation_metadata_too_large")
    document = json.loads(data)
    if not isinstance(document, dict):
        raise ValueError("gemma_preparation_document_required")
    return document


def _budget(run_id: str, max_updates: int, max_seconds: int) -> None:
    validate_run_id(run_id)
    if type(max_updates) is not int or not 1 <= max_updates <= 256:
        raise ValueError("gemma_preparation_update_budget_invalid")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 86400:
        raise ValueError("gemma_preparation_time_budget_invalid")


def _source(corpus_root: Path) -> tuple[Json, Json]:
    root = checked_directory(corpus_root)
    manifest = _read(root / "manifest.json")
    if manifest.get("material_version") != 5:
        raise ValueError("gemma_preparation_corpus_version_invalid")
    prepared_path = checked_file(root / "prepared.json")
    expected = manifest.get("files", {}).get("prepared.json", {}).get("sha256")
    if sha256(prepared_path) != expected:
        raise ValueError("gemma_preparation_canonical_hash_mismatch")
    prepared = _read(prepared_path)
    records = prepared.get("records")
    if not isinstance(records, dict):
        raise ValueError("gemma_preparation_canonical_records_required")
    if prepare_material(records) != prepared:
        raise ValueError("gemma_preparation_canonical_manifest_mismatch")
    if manifest.get("prepared_manifest") != prepared["manifest"]:
        raise ValueError("gemma_preparation_corpus_manifest_mismatch")
    return manifest, prepared


def _binding(document: Json, profile: GemmaProfile) -> Json:
    if document.get("kind") != "gemma4_training_runtime_binding":
        raise ValueError("gemma_preparation_binding_required")
    ollama, vendor = document.get("ollama"), document.get("vendor_source")
    if not isinstance(ollama, dict) or not isinstance(vendor, dict):
        raise ValueError("gemma_preparation_binding_metadata_invalid")
    architecture = ollama.get("architecture")
    if not isinstance(architecture, dict):
        raise ValueError("gemma_preparation_binding_metadata_invalid")
    observed = {
        "details": {
            "family": "gemma4",
            "format": ollama.get("format"),
            "quantization_level": ollama.get("quantization"),
        },
        "model_info": dict(architecture)
        | {"general.base_model.0.repo_url": vendor.get("base_repository")},
        "capabilities": ollama.get("capabilities"),
    }
    checked = bind_ollama(
        profile,
        {"name": ollama.get("tag"), "digest": ollama.get("digest")},
        observed,
    )
    if checked != document:
        raise ValueError("gemma_preparation_binding_identity_mismatch")
    return checked


def _encoded_source(document: Json, prepared: Json, profile: GemmaProfile) -> Json:
    encoded = validate_encoded_release(document, profile)
    release = build_release(prepared["records"], profile)
    if (
        document.get("source_release_sha256") != release["release_sha256"]
        or document.get("source_records_sha256")
        != release["training_payload"]["records_sha256"]
    ):
        raise ValueError("gemma_preparation_encoded_source_mismatch")
    for split, rows in encoded.items():
        original = release["training_payload"]["records"][split]
        if len(rows) != len(original):
            raise ValueError("gemma_preparation_encoded_count_mismatch")
        for row, source in zip(rows, original, strict=True):
            if row.get("source_record_sha256") != digest(source) or any(
                row.get(key) != source[key]
                for key in (
                    "record_id",
                    "problem_group",
                    "language",
                    "supervised_assistant_indices",
                )
            ):
                raise ValueError("gemma_preparation_encoded_record_mismatch")
    return release


def _publish(path: Path, document: Json) -> None:
    # Reuse the control CLI's atomic no-replacement JSON publisher, silently.
    from .cli import publish

    with contextlib.redirect_stdout(io.StringIO()):
        publish(path, document)


def _identity(
    profile: GemmaProfile,
    recipe: GemmaTrainingRecipe,
    encoded: Json,
    binding: Json,
    snapshot: Path,
    limits: Json,
) -> Json:
    root = Path(__file__).resolve().parents[3]
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    return validate_identity(
        {
            "model": profile.model,
            "revision": profile.revision,
            "tokenizer_sha256": tokenizer_sha,
            "template_sha256": template_sha,
            "profile_sha256": digest(recipe.identity()),
            "data_sha256": digest(encoded),
            "code_sha256": code_identity(root, model=profile.model),
            "dependencies_sha256": dependencies_identity(root, model=profile.model),
            "encoding_sha256": encoded["encoded_release_sha256"],
            "ollama_binding_sha256": binding["binding_sha256"],
            "dataset": "domain",
            "limits": limits,
        }
    )


def _evaluation_entry(root: Path, name: str, cases: str) -> Path:
    safe_relative(name)
    target = operator_path(root / name)
    if not target.is_file():
        raise ValueError("gemma_preparation_evaluation_file_missing")
    fixture = name.startswith("fixtures/") and (
        target.suffix == ".png" or target.name == ".keep"
    )
    if name != cases and not fixture:
        raise ValueError("gemma_preparation_evaluation_file_not_allowed")
    limit = 2 * 1024**2 if name == cases else 1024**2
    if target.stat().st_size > limit or (
        target.name == ".keep" and target.stat().st_size
    ):
        raise ValueError("gemma_preparation_evaluation_file_too_large")
    return target


def _evaluation_manifest(document: Json) -> tuple[Json, str]:
    files, cases = document.get("files"), document.get("cases")
    if (
        not isinstance(files, dict)
        or not 1 <= len(files) <= 2048
        or not isinstance(cases, str)
    ):
        raise ValueError("gemma_preparation_evaluation_manifest_invalid")
    safe_relative(cases)
    count = document.get("case_count")
    if type(count) is not int or not 1 <= count <= 512 or not cases.endswith(".jsonl"):
        raise ValueError("gemma_preparation_evaluation_cases_invalid")
    qualification = document.get("qualification")
    if not isinstance(qualification, dict) or qualification.get("status") != "PASS":
        raise ValueError("gemma_preparation_evaluation_not_qualified")
    return files, cases


def _evaluation_source(path: Path, run_id: str) -> tuple[Path, list[str], str, Json]:
    from scripts.granite_operator.comparison_support import load_frozen

    target = checked_file(path)
    root = checked_directory(target.parent)
    document = _read(target)
    files, cases = _evaluation_manifest(document)
    remote_run_id = run_id + "-eval"
    validate_run_id(remote_run_id)
    manifest_name = safe_relative(target.name)
    if manifest_name in files:
        raise ValueError("gemma_preparation_evaluation_manifest_self_reference")
    expected = {manifest_name: sha256(target)}
    total = target.stat().st_size
    for name, checksum in files.items():
        entry = _evaluation_entry(root, name, cases)
        total += entry.stat().st_size
        if total > MAX_METADATA_BYTES or sha256(entry) != checksum:
            raise ValueError("gemma_preparation_evaluation_changed_or_too_large")
        expected[name] = checksum
    frozen, selected_cases = load_frozen(target)
    for case in selected_cases:
        fixture = safe_relative(case["fixture"])
        if not fixture.startswith("fixtures/"):
            raise ValueError("gemma_preparation_evaluation_fixture_invalid")
    if frozen != document:
        raise ValueError("gemma_preparation_evaluation_changed")
    return (
        root,
        sorted(expected),
        remote_run_id,
        {"manifest_relative": manifest_name, "expected_files": expected},
    )


def _evaluation_bundle(
    source: tuple[Path, list[str], str, Json] | None, output: Path, identity: Json
) -> Json:
    if source is None:
        return {
            "prepared": False,
            "required_for_complete_workflow": True,
            "model_results_present": False,
        }
    root, files, run_id, metadata = source
    archive = output / "evaluation.zip"
    manifest = create_bundle(
        root,
        files,
        archive,
        run_id=run_id,
        identity=identity,
        max_bytes=MAX_METADATA_BYTES,
    )
    actual = {name: entry["sha256"] for name, entry in manifest["files"].items()}
    if actual != metadata["expected_files"]:
        raise ValueError("gemma_preparation_evaluation_changed_during_pack")
    return {
        "prepared": True,
        "transfer_archive": "evaluation.zip",
        "transfer_sha256": sha256(archive),
        "bundle_manifest_sha256": manifest["manifest_sha256"],
        "remote_run_id": run_id,
        "manifest_relative": metadata["manifest_relative"],
        "input_files": files,
        "source_manifest_sha256": metadata["expected_files"][
            metadata["manifest_relative"]
        ],
        "hidden_oracles_present": True,
        "model_results_present": False,
        "comparison_results_collected": False,
    }


def prepare_session(
    corpus_root: Path,
    encoded_path: Path,
    binding_path: Path,
    recipe: GemmaTrainingRecipe,
    destination: Path,
    *,
    snapshot: Path,
    run_id: str,
    max_updates: int,
    max_seconds: int,
    evaluation_cases: Path | None = None,
) -> Json:
    """Package validated inputs; remote GPU admission and smoke stay mandatory.

    Source data and metadata are local only. The explicit transfer allowlist has
    native train/validation tensors and the observed variant binding, never the
    canonical holdout, capability answers, raw chats, credentials or weights.
    An optional separate evaluation archive contains the hidden frozen oracles and
    their image fixtures; it never changes the three-file training input archive.
    """
    _budget(run_id, max_updates, max_seconds)
    recipe.validate()
    parent = checked_directory(destination.parent)
    output = parent / destination.name
    if output.exists() or output.is_symlink():
        raise FileExistsError("gemma_preparation_output_exists")
    manifest, prepared = _source(corpus_root)
    encoded = _read(encoded_path)
    profile_data = encoded.get("model_profile")
    if not isinstance(profile_data, dict):
        raise ValueError("gemma_preparation_profile_required")
    try:
        profile = GemmaProfile(**profile_data)
    except TypeError as error:
        raise ValueError("gemma_preparation_profile_invalid") from error
    recipe.validate_profile(profile)
    snapshot = checked_directory(snapshot)
    profile.validate_snapshot(snapshot)
    release = _encoded_source(encoded, prepared, profile)
    binding = _binding(_read(binding_path), profile)
    evaluation_source = (
        _evaluation_source(evaluation_cases, run_id)
        if evaluation_cases is not None
        else None
    )
    identity = _identity(
        profile,
        recipe,
        encoded,
        binding,
        snapshot,
        {"max_updates": max_updates, "max_seconds": max_seconds},
    )
    # Reserve the immutable destination only after all input checks have passed.
    # If disk publication fails, leave this incomplete directory for diagnosis.
    output.mkdir(mode=0o700)
    staging = output / "input"
    staging.mkdir(mode=0o700)
    for name, document in zip(
        INPUT_FILES, (recipe.identity(), encoded, binding), strict=True
    ):
        _publish(staging / name, document)
    bundle = create_bundle(
        staging,
        INPUT_FILES,
        output / INPUT_ARCHIVE,
        run_id=run_id,
        identity=identity,
        max_bytes=MAX_METADATA_BYTES,
    )
    evaluation = _evaluation_bundle(evaluation_source, output, identity)
    report = {
        "schema_version": 1,
        "kind": "gemma4_training_session_package",
        "status": "SESSION_PACKAGE_PREPARED",
        "run_id": run_id,
        "identity": identity,
        "source_corpus_manifest_sha256": digest(manifest),
        "source_release_sha256": release["release_sha256"],
        "source_training_records_sha256": release["training_payload"]["records_sha256"],
        "split_summary": encoded["split_summary"],
        "input_files": list(INPUT_FILES),
        "transfer_archive": INPUT_ARCHIVE,
        "transfer_sha256": sha256(output / INPUT_ARCHIVE),
        "bundle_manifest_sha256": bundle["manifest_sha256"],
        "ready_for_remote_session": True,
        "ready_for_complete_remote_workflow": evaluation["prepared"],
        "evaluation_package_prepared": evaluation["prepared"],
        "evaluation": evaluation,
        "model_execution_policy": {"gpu_required": True, "cpu_fallback": False},
        "qualification": "integrity_only_remote_gpu_smoke_required",
        "remote_steps_required": [
            "download_and_verify_exact_weight_snapshot",
            "provision_locked_interpreter",
            "host_runtime_admission",
            "native_loader_meta_preflight",
            "smoke",
            "smoke_resume_and_seal_qualification",
            "explicit_budget_training",
            "variant_matched_base_adapter_and_capability_evaluation",
        ],
        "canonical_holdout_in_bundle": False,
        "capability_answers_in_bundle": False,
        "weights_in_bundle": False,
        "host_created": False,
        "model_loaded": False,
        "gpu_qualified": False,
        "training_started": False,
        "activation_authorized": False,
    }
    _publish(output / "preflight.json", report)
    return report
