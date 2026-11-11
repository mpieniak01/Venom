"""Verified checkpoints and sealed, portable evaluation evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
from scripts.academy.omni_pl_chat_scoring import aggregate
from venom_core.services.remote_training.paths import operator_path

from .profiles import digest, read_json, rows

WEIGHTS = "adapter_model.safetensors"
ADAPTER_FILES = ("adapter_config.json", WEIGHTS)
CHECKPOINT_PATTERN = re.compile(r"checkpoint-([1-9][0-9]*)")


def inspect_checkpoint(directory: Path, *, resume: bool = False) -> dict:
    match = CHECKPOINT_PATTERN.fullmatch(directory.name)
    if match is None:
        raise ValueError("experiment_checkpoint_invalid")
    directory = operator_path(directory)
    hashes = read_json(directory / "hashes.json")
    if not isinstance(hashes, dict) or set(hashes) != set(CHECKPOINT_FILES):
        raise ValueError("experiment_checkpoint_receipt_invalid")
    names = CHECKPOINT_FILES if resume else ADAPTER_FILES
    if any(digest(directory / name) != hashes[name] for name in names):
        raise ValueError("experiment_checkpoint_changed")
    if resume:
        state = read_json(directory / "trainer_state.json")
        if state.get("global_step") != int(match[1]):
            raise ValueError("experiment_checkpoint_step_mismatch")
    return {
        "step": int(match[1]),
        "sha256": hashes[WEIGHTS],
        "bytes": sum((directory / name).stat().st_size for name in names),
    }


def latest_checkpoint(
    training: Path, *, resume: bool = False
) -> tuple[Path, dict] | None:
    if not training.is_dir():
        return None
    checkpoints = [
        (int(match[1]), path)
        for path in training.iterdir()
        if (match := CHECKPOINT_PATTERN.fullmatch(path.name))
    ]
    for _, path in sorted(checkpoints, reverse=True):
        try:
            return path, inspect_checkpoint(path, resume=resume)
        except (OSError, ValueError, TypeError, KeyError):
            if resume and (path / "hashes.json").exists():
                return None
            continue
    return None


def review_data(generation: Path, dev: Path) -> dict:
    return {"cases": rows(dev), "answers": rows(generation / "blind.jsonl")}


def sealed_report(
    generation: Path,
    dev: Path,
    judgments: list[dict[str, Any]],
    checkpoint: dict,
) -> dict:
    bundle = review_data(generation, dev)
    cases, answers = bundle["cases"], bundle["answers"]
    # Validate before reading variant identities. Map labels to variants per case.
    aggregate(cases, answers, judgments)
    mapping = read_json(generation / "unblind.json")
    candidate = f"checkpoint-{checkpoint['step']}"
    if set(mapping) != {case["record_id"] for case in cases}:
        raise ValueError("experiment_unblind_incomplete")
    grades = {(row["record_id"], row["label"]): row for row in judgments}
    identified = []
    identified_grades = []
    details = []
    for row in answers:
        case = row["case"]
        case_id = case["record_id"]
        names = mapping[case_id]
        if set(names) != set(row["answers"]) or sorted(names.values()) != [
            "base",
            candidate,
        ]:
            raise ValueError("experiment_unblind_invalid")
        variants = {}
        for label, value in row["answers"].items():
            role = "base" if names[label] == "base" else "candidate"
            grade = grades[case_id, label]
            identified_grades.append({**grade, "label": role})
            variants[role] = {**value, "reason": grade["reason"]}
        identified.append({"case": case, "answers": variants})
        details.append({"case_id": case_id, "messages": case["messages"], **variants})
    scores = aggregate(cases, identified, identified_grades)
    return {
        **scores,
        "cases": details,
        "checkpoint": checkpoint,
        "artifacts": [{"kind": "adapter", **checkpoint, "available": True}],
    }


def calibrated_judgments(calibration: dict, bundle: dict) -> list[dict]:
    """Apply operator-qualified explicit output/grade pairs and fallbacks."""
    grades = []
    rules = calibration["cases"]
    if set(rules) != {case["record_id"] for case in bundle["cases"]}:
        raise ValueError("experiment_calibration_coverage")
    for row in bundle["answers"]:
        case_id = row["case"]["record_id"]
        rule = rules[case_id]
        for label, answer in row["answers"].items():
            text = answer["text"].strip()
            grade = rule["outputs"].get(text, rule["fallback"])
            grades.append({**grade, "record_id": case_id, "label": label})
    return grades


def historical_report(source: dict, source_sha256: str) -> dict:
    """Import prior scorer output without treating a receipt as existing weights."""
    selected = source["selected"]
    match = CHECKPOINT_PATTERN.fullmatch(selected)
    if match is None:
        raise ValueError("experiment_historical_checkpoint_invalid")
    summaries = {}
    verdicts = {}
    for role, name in (("base", "base"), ("candidate", selected)):
        summaries[role] = source["summaries"][name]
        verdicts[role] = source["verdicts"][name]
        total = summaries[role]["total"]
        n = total["n"]
        if (
            type(n) is not int
            or n < 1
            or any(
                type(value) is not int or not 0 <= value <= n
                for value in total.values()
            )
        ):
            raise ValueError("experiment_historical_metrics_invalid")
    if summaries["base"]["total"]["n"] != summaries["candidate"]["total"]["n"]:
        raise ValueError("experiment_historical_coverage_invalid")
    checkpoint = {"step": int(match[1])}
    return {
        "source_sha256": source_sha256,
        "historical": True,
        "summaries": summaries,
        "verdicts": verdicts,
        "cases": [],
        "checkpoint": checkpoint,
        "artifacts": [{"kind": "adapter", **checkpoint, "available": False}],
    }
