"""Sealed paired evidence for a fixed set of checkpoints in one training run."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from scripts.academy.omni_pl_chat_dialogue import (
    DialogueHistory,
    blind_answer,
    validate_dialogues,
)
from scripts.academy.omni_pl_chat_evaluate import blind_mapping
from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.remote_training.paths import operator_path

from .evidence import ADAPTER_FILES, inspect_checkpoint
from .profiles import MAX_JSON_BYTES, digest, read_json, rows, stable_hash

GENERATION_SEAL = "generation-seal.json"
RAW_ANSWERS = "raw.jsonl"
BLIND_MAPPING = "unblind.json"
EVALUATION_MANIFEST = "manifest.json"
_BLIND = "blind.jsonl"
GENERATION_OUTPUTS = (RAW_ANSWERS, _BLIND, BLIND_MAPPING)
RESULT_SEAL = "result-seal.json"
_JUDGMENTS = "judgments.json"


def validate_steps(steps: list[int], recipe: dict) -> None:
    if (
        not 1 <= len(steps) <= 4
        or steps != sorted(set(steps))
        or any(
            type(step) is not int
            or not 1 <= step <= recipe["steps"]
            or (step != recipe["steps"] and step % recipe["save_every"] != 0)
            for step in steps
        )
    ):
        raise ValueError("campaign_checkpoint_steps_invalid")


def step_directory(directory: Path, step: int) -> Path:
    return operator_path(directory / "checkpoint-evaluations" / str(step))


def inspect_steps(training: Path, steps: list[int]) -> dict:
    """Read the exact hashed inputs before and after generation."""
    inputs = {}
    for step in steps:
        tag = f"checkpoint-{step}"
        folder = training / tag
        inspect_checkpoint(folder)
        inputs[tag] = {name: digest(folder / name) for name in ADAPTER_FILES}
    return inputs


def bind_steps(directory: Path, steps: list[int]) -> dict:
    observed = inspect_steps(directory / "training", steps)
    path = directory / "checkpoint-inputs.json"
    if path.exists():
        if read_json(path) != observed:
            raise ValueError("experiment_checkpoint_changed")
    else:
        atomic_json(path, observed)
    return observed


def read_generation(directory: Path) -> tuple[dict, dict]:
    seal = read_json(directory / GENERATION_SEAL)
    manifest = read_json(directory / EVALUATION_MANIFEST)
    if any(
        digest(directory / name) != seal[name]
        for name in (*GENERATION_OUTPUTS, EVALUATION_MANIFEST)
    ) or manifest["outputs"] != {name: seal[name] for name in GENERATION_OUTPUTS}:
        raise ValueError("experiment_evidence_changed")
    return manifest, seal


def seal_generation(directory: Path) -> None:
    atomic_json(
        directory / GENERATION_SEAL,
        {
            name: digest(directory / name)
            for name in (*GENERATION_OUTPUTS, EVALUATION_MANIFEST)
        },
    )


def _raw_rows(directory: Path, manifest: dict) -> dict:
    # This matrix can contain 5 × 512 generations. Do not materialize its text twice.
    rows = {}
    expected = {
        (case_id, variant)
        for case_id in manifest["evaluated_ids"]
        for variant in manifest["models"]
    }
    with operator_path(directory / RAW_ANSWERS).open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            key = (row["case"], row["model"])
            if key not in expected or key in rows:
                raise ValueError("experiment_evidence_changed")
            rows[key] = row
    if rows.keys() != expected:
        raise ValueError("experiment_evidence_changed")
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    target = operator_path(path)
    temporary = operator_path(path.with_suffix(".jsonl.tmp"))
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)


def _publish_pair(
    folder: Path, cases: list[dict], manifest: dict, rows: dict, step: int
) -> None:
    tag = f"checkpoint-{step}"
    mapping = blind_mapping(cases, ["base", tag])
    pair = {
        **manifest,
        "models": {key: manifest["models"][key] for key in ("base", tag)},
    }
    if (folder / GENERATION_SEAL).exists():
        previous, _ = read_generation(folder)
        keys = (
            "models",
            "data_sha256",
            "snapshot_manifest_sha256",
            "generation_identity_sha256",
        )
        if any(previous[key] != pair[key] for key in keys):
            raise ValueError("experiment_evidence_changed")
        return
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = []
    blind = []
    for case in cases:
        answers = {}
        for label, variant in mapping[case["record_id"]].items():
            row = rows[case["record_id"], variant]
            raw.append({**row, "label": label})
            answers[label] = blind_answer(row)
        blind.append({"case": case, "answers": dict(sorted(answers.items()))})
    _write_rows(folder / RAW_ANSWERS, raw)
    _write_rows(folder / _BLIND, blind)
    atomic_json(folder / BLIND_MAPPING, mapping)
    atomic_json(
        folder / EVALUATION_MANIFEST,
        {
            **pair,
            "outputs": {name: digest(folder / name) for name in GENERATION_OUTPUTS},
        },
    )
    seal_generation(folder)


def publish_pairs(
    directory: Path, generation: Path, cases: list[dict], inputs: dict, steps: list[int]
) -> None:
    manifest, _ = read_generation(generation)
    if manifest["models"] != {"base": {"base": True}, **inputs} or manifest[
        "evaluated_ids"
    ] != [case["record_id"] for case in cases]:
        raise ValueError("experiment_evidence_changed")
    matrix = _raw_rows(generation, manifest)
    for step in steps:
        _publish_pair(step_directory(directory, step), cases, manifest, matrix, step)


def sealed_step(folder: Path) -> tuple[dict, str]:
    expected = read_json(folder / RESULT_SEAL)["result_sha256"]
    path = operator_path(folder / "result.json")
    with path.open("rb") as stream:
        payload = stream.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("experiment_result_changed")
    return json.loads(payload), expected


def review_step(directory: Path, steps: list[int]) -> int:
    for step in steps:
        if not (step_directory(directory, step) / RESULT_SEAL).is_file():
            return step
    # Recover final publication if the process crashed after writing the last step seal.
    return steps[-1]


def step_statuses(directory: Path, steps: list[int], status: str) -> list[dict]:
    values = []
    for step in steps:
        folder = step_directory(directory, step)
        entry = {"step": step, "status": "pending"}
        if (folder / RESULT_SEAL).is_file():
            result, sha = sealed_step(folder)
            entry.update(
                status="succeeded", summaries=result["summaries"], result_sha256=sha
            )
        elif status == "awaiting_review":
            entry["status"] = "awaiting_review"
        values.append(entry)
    return values


def baseline_judgments(folder: Path, judgments: list[dict]) -> dict:
    mapping = read_json(folder / BLIND_MAPPING)
    return {
        grade["record_id"]: {
            key: grade[key]
            for key in ("criteria", "polish_ok", "natural_ok", "critical_error")
        }
        for grade in judgments
        if mapping[grade["record_id"]][grade["label"]] == "base"
    }


def verify_baseline(
    directory: Path, steps: list[int], checkpoint_step: int, judgments: list[dict]
) -> None:
    if checkpoint_step == steps[0]:
        return
    reference = step_directory(directory, steps[0])
    report, _ = sealed_step(reference)
    prior_path = reference / _JUDGMENTS
    if (
        digest(prior_path) != report["judgment_sha256"]
        or digest(reference / GENERATION_SEAL) != report["generation_sha256"]
    ):
        raise ValueError("experiment_evidence_changed")
    read_generation(reference)
    current = step_directory(directory, checkpoint_step)
    if baseline_judgments(current, judgments) != baseline_judgments(
        reference, read_json(prior_path)
    ):
        raise ValueError("experiment_checkpoint_baseline_changed")


def _baseline_inputs(
    folder: Path, manifest: dict, cases: list[dict], *, variant: str = "base"
) -> dict:
    """Check the sealed raw/anonymous views and the requested arm's own history."""
    if manifest["evaluated_ids"] != [case["record_id"] for case in cases]:
        raise ValueError("experiment_checkpoint_baseline_generation_changed")
    raw = _raw_rows(folder, manifest)
    mapping = read_json(folder / BLIND_MAPPING)
    blind = rows(folder / _BLIND)
    if [row["case"] for row in blind] != cases or set(mapping) != {
        case["record_id"] for case in cases
    }:
        raise ValueError("experiment_checkpoint_baseline_generation_changed")
    validate_dialogues(cases)
    history = DialogueHistory()
    result = {}
    for case, anonymous in zip(cases, blind, strict=True):
        ident = case["record_id"]
        labels = [label for label, tag in mapping[ident].items() if tag == variant]
        if len(labels) != 1:
            raise ValueError("experiment_checkpoint_baseline_generation_changed")
        row = raw[ident, variant]
        answer = blind_answer(row)
        if anonymous["answers"].get(labels[0]) != answer:
            raise ValueError("experiment_checkpoint_baseline_generation_changed")
        history.remember(case, row, history.context(case))
        result[ident] = {
            "raw": {key: value for key, value in row.items() if key != "label"},
            "answer": answer,
            "label": labels[0],
        }
    return result


def verify_generation_pair(
    directory: Path, cases: list[dict], models: dict
) -> tuple[dict, dict]:
    """Bind an existing paired evaluation to exact model inputs and own histories."""
    manifest, seal = read_generation(directory)
    if manifest["models"] != models:
        raise ValueError("campaign_quality_parent_adapter_changed")
    if manifest.get("case_max_new_tokens") != {
        case["record_id"]: case.get("max_new_tokens", manifest["max_new_tokens"])
        for case in cases
    }:
        raise ValueError("campaign_quality_identity_changed")
    for name in models:
        _baseline_inputs(directory, manifest, cases, variant=name)
    return manifest, seal


def _baseline_source(
    directory: Path, first_step: int, calibration: dict, manifest_sha256: str
) -> tuple[Path, dict, dict, list[dict]]:
    source = step_directory(directory, first_step)
    report, result_sha = sealed_step(source)
    manifest = read_json(directory / EVALUATION_MANIFEST)
    generated, _ = read_generation(source)
    if (
        stable_hash(manifest) != manifest_sha256
        or report["manifest_sha256"] != manifest_sha256
        or report["run_id"] != directory.name
        or report["checkpoint"]["step"] != first_step
        or manifest["calibration"] != calibration
        or report["calibration_judge"] != calibration["judge"]
        or digest(source / GENERATION_SEAL) != report["generation_sha256"]
        or digest(source / _JUDGMENTS) != report["judgment_sha256"]
        or generated["data_sha256"] != report["dev_sha256"]
        or generated["data_sha256"] != manifest["profile"]["dev_sha256"]
    ):
        raise ValueError("experiment_checkpoint_baseline_receipt_changed")
    from .calibration import scorer_protocol

    receipt = {
        "run_id": report["run_id"],
        "checkpoint_step": first_step,
        "result_sha256": result_sha,
        "generation_sha256": report["generation_sha256"],
        "judgment_sha256": report["judgment_sha256"],
        "calibration_sha256": manifest["profile"]["calibration_sha256"],
        "scorer_protocol": scorer_protocol(calibration),
    }
    return source, generated, receipt, read_json(source / _JUDGMENTS)


def reuse_baseline_reviews(
    directory: Path,
    step: int,
    bundle: dict,
    calibration: dict,
    *,
    steps: list[int],
    manifest_sha256: str,
) -> tuple[dict, list[dict]]:
    """Reuse only the first fully sealed M0 receipt within this generation matrix."""
    if step == steps[0]:
        return bundle, []
    from scripts.academy.omni_pl_chat_scoring import aggregate

    from . import semantic_judge_dispatch

    try:
        source, previous, receipt, grades = _baseline_source(
            directory, steps[0], calibration, manifest_sha256
        )
        current = step_directory(directory, step)
        generated, _ = read_generation(current)
        # Per-step models/output digests differ; all inference identity fields,
        # including evaluator file hashes and own-history protocol, must agree.
        ignored = {"models", "outputs", "resumed_generations"}
        if previous["models"].get("base") != {"base": True} or generated["models"].get(
            "base"
        ) != {"base": True}:
            raise ValueError("experiment_checkpoint_baseline_protocol_changed")
        if {k: v for k, v in previous.items() if k not in ignored} != {
            k: v for k, v in generated.items() if k not in ignored
        }:
            raise ValueError("experiment_checkpoint_baseline_protocol_changed")
        cases = bundle["cases"]
        original = _baseline_inputs(source, previous, cases)
        target = _baseline_inputs(current, generated, cases)
        if bundle["answers"] != rows(current / _BLIND):
            raise ValueError("experiment_checkpoint_baseline_generation_changed")
        aggregate(cases, rows(source / _BLIND), grades)
        source_grades = {
            grade["record_id"]: grade
            for grade in grades
            if grade["label"] == original[grade["record_id"]]["label"]
        }
        pin = semantic_judge_dispatch.qualification(calibration)
        reused = []
        for case in cases:
            ident = case["record_id"]
            if original[ident]["raw"] != target[ident]["raw"]:
                raise ValueError("experiment_checkpoint_baseline_generation_changed")
            grade = source_grades[ident]
            if "review_reused_from" in grade:
                raise ValueError("experiment_checkpoint_baseline_receipt_changed")
            semantic_judge_dispatch.verify_review_receipt(
                pin, calibration["cases"][ident], case, target[ident]["answer"], grade
            )
            # The original call and response remain byte-equivalent JSON values.
            # Explicit provenance distinguishes replay from a new model call.
            reused.append(
                {
                    **grade,
                    "label": target[ident]["label"],
                    "review_reused_from": receipt,
                }
            )
        pending = {
            **bundle,
            "answers": [
                {
                    **row,
                    "answers": {
                        label: answer
                        for label, answer in row["answers"].items()
                        if label != target[row["case"]["record_id"]]["label"]
                    },
                }
                for row in bundle["answers"]
            ],
        }
        return pending, reused
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("experiment_checkpoint_baseline_receipt_invalid") from exc
