"""Build quality records from Academy's sealed evidence without loading weights."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import distributions
from pathlib import Path
from typing import Any

from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.services.remote_training.paths import operator_path

from .profiles import (
    MAX_JSON_BYTES,
    digest,
    load_profile,
    read_json,
    resolve_input,
    stable_hash,
)
from .quality import QualityStore, quality_record_view
from .quality_schema import QualityRecord

HISTORY_PREFIX = "history:"
_ENGINE_PACKAGES = ("torch", "transformers", "peft")
_DEFAULT_LOSS = "trainer_default"
_MANIFEST_NAME = "manifest.json"
_PROTOCOL_FIELDS = (
    "revision",
    "max_prompt_tokens",
    "max_new_tokens",
    "seed",
    "engine",
    "template",
    "generation_mode",
    "do_sample",
    "enable_thinking",
)


def _verified_bytes(path: Path, expected: str) -> bytes:
    with operator_path(path).open("rb") as stream:
        payload = stream.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("experiment_quality_evidence_changed")
    return payload


def _verified_json(path: Path, expected: str) -> Any:
    return json.loads(_verified_bytes(path, expected))


def _dev_categories(path: Path, expected: str) -> dict[str, str]:
    items = (
        json.loads(line)
        for line in _verified_bytes(path, expected).splitlines()
        if line.strip()
    )
    categories = {}
    for case in items:
        record_id = case["record_id"]
        if case["split"] != "dev" or record_id in categories:
            raise ValueError("experiment_quality_dev_invalid")
        categories[record_id] = case["task"]
    if not categories:
        raise ValueError("experiment_quality_dev_invalid")
    return categories


def _profile_runtime(venv: Path) -> dict:
    sites = [str(path) for path in venv.glob("lib/python*/site-packages")]
    engine = {}
    for name in _ENGINE_PACKAGES:
        candidates = list(distributions(name=name, path=sites))
        if len(candidates) != 1 or not candidates[0].version:
            raise ValueError("campaign_quality_runtime_unverified")
        engine[name] = candidates[0].version
    return {"evaluation_engine": engine, "loss": _DEFAULT_LOSS}


def profile_context(
    experiments: Any,
    profile_id: str,
    review_mode: str,
    *,
    include_runtime: bool = False,
) -> dict:
    profile, _ = load_profile(experiments.root, profile_id)
    categories = _dev_categories(
        resolve_input(experiments.root, profile.dev), profile.dev_sha256
    )
    context = {
        "identity": {
            "model": profile.model,
            "base_sha256": digest(SNAPSHOT_PIN),
            "dataset_sha256": profile.dev_sha256,
        },
        "case_categories": categories,
        "review_mode": review_mode,
        "train_sha256": profile.train_sha256,
    }
    if include_runtime:
        context["runtime"] = _profile_runtime(
            resolve_input(experiments.root, profile.training_venv)
        )
    return context


def evaluation_identity(generation: dict, calibration_sha256: str | None) -> dict:
    """Bind the scorer and actual inference protocol, including library versions."""
    return {
        "model": generation["model_repo"],
        "base_sha256": generation["snapshot_manifest_sha256"],
        "dataset_sha256": generation["data_sha256"],
        "protocol_sha256": stable_hash(
            {
                "scorer": "omni-rubric-v1",
                "calibration_sha256": calibration_sha256,
                **{key: generation[key] for key in _PROTOCOL_FIELDS},
            }
        ),
    }


def evaluated_cases(
    report: dict,
    categories: dict[str, str],
    grades: list[dict],
    mapping: dict,
) -> dict:
    checkpoint = f"checkpoint-{report['checkpoint']['step']}"
    critical = {}
    for grade in grades:
        record_id = grade["record_id"]
        variant = mapping[record_id][grade["label"]]
        critical[record_id, variant] = grade["critical_error"]
    verdicts = report["verdicts"]
    if any(set(verdicts[role]) != set(categories) for role in ("base", "candidate")):
        raise ValueError("experiment_quality_coverage_invalid")
    return {
        case_id: {
            "category": category,
            "base": {
                "usable": verdicts["base"][case_id]["usable"] == 1,
                "critical": critical[case_id, "base"],
            },
            "candidate": {
                "usable": verdicts["candidate"][case_id]["usable"] == 1,
                "critical": critical[case_id, checkpoint],
            },
        }
        for case_id, category in categories.items()
    }


def native_record(experiments: Any, run_id: str) -> dict:
    """Read a completed native run using its result seal and bound inputs."""
    directory = experiments.run_dir(run_id)
    result_sha = read_json(directory / "result-seal.json")["result_sha256"]
    report = _verified_json(directory / "result.json", result_sha)
    state = read_json(directory / "state.json")
    if (
        experiments._child_alive(state)
        or report["run_id"] != run_id
        or report.get("historical")
    ):
        raise ValueError("experiment_quality_result_incomplete")
    manifest = read_json(directory / _MANIFEST_NAME)
    if stable_hash(manifest) != report["manifest_sha256"]:
        raise ValueError("experiment_quality_evidence_changed")
    profile = manifest["profile"]
    generation = directory / f"evaluation-{state['attempt']}"
    seal = _verified_json(
        generation / "generation-seal.json", report["generation_sha256"]
    )
    generated = _verified_json(generation / _MANIFEST_NAME, seal[_MANIFEST_NAME])
    mapping = _verified_json(generation / "unblind.json", seal["unblind.json"])
    for name in ("blind.jsonl", "raw.jsonl"):
        if digest(generation / name) != seal[name]:
            raise ValueError("experiment_quality_evidence_changed")
    grades = _verified_json(generation / "judgments.json", report["judgment_sha256"])
    categories = _dev_categories(
        resolve_input(experiments.root, profile["dev"]), report["dev_sha256"]
    )
    calibration = (
        profile["calibration_sha256"] if manifest["calibration"] is not None else None
    )
    identity = evaluation_identity(generated, calibration)
    if (
        identity["dataset_sha256"] != profile["dev_sha256"]
        or identity["model"] != profile["model"]
    ):
        raise ValueError("experiment_quality_evidence_changed")
    record = QualityRecord.model_validate(
        {
            "record_id": run_id,
            "split": "dev",
            "identity": identity,
            "source": {"identity": run_id, "sha256": result_sha, "kind": "academy"},
            "cases": evaluated_cases(report, categories, grades, mapping),
            "train_sha256": profile["train_sha256"],
            "recipe": manifest["recipe"],
            "runtime": {
                "evaluation_engine": generated["engine"],
                "loss": _DEFAULT_LOSS,
            },
        }
    )
    return quality_record_view(record)


def get_record(experiments: Any, record_id: str) -> dict:
    if record_id.startswith(HISTORY_PREFIX):
        return QualityStore(experiments.root).get(
            record_id.removeprefix(HISTORY_PREFIX)
        )
    return native_record(experiments, record_id)
