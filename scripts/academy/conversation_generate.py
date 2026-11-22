"""Generate the complete 0A DEV panel with the native Academy evaluator."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases, verify_adapter
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.training_experiments.checkpoint_evaluation import (
    GENERATION_SEAL,
    _raw_rows,
    publish_pairs,
    seal_generation,
    step_directory,
    verify_generation_pair,
)
from venom_core.services.training_experiments.conversation_blind import _case_index
from venom_core.services.training_experiments.conversation_review import (
    _validate_panel,
    payload_sha,
)
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    rows,
    stable_hash,
)
from venom_core.services.training_experiments.remote_text_qualification import _evaluate
from venom_core.services.training_experiments.worker import EVALUATOR

Evaluator = Callable[..., None]


def _adapter_identity(step: int, path: Path, base: dict) -> dict:
    hashes = verify_adapter(operator_path(path))
    return {
        "step": step,
        "path": f"checkpoint-evaluations/{step}",
        "identity": {
            **base,
            "config_sha256": hashes["adapter_config.json"],
            "weights_sha256": hashes["adapter_model.safetensors"],
        },
    }


def _model_hashes(entry: dict) -> dict:
    identity = entry["identity"]
    return {
        "adapter_config.json": identity["config_sha256"],
        "adapter_model.safetensors": identity["weights_sha256"],
    }


def _generation_manifest(
    generation: Path, cases: list[dict], intent: dict, inputs: dict
) -> dict:
    manifest, _ = verify_generation_pair(
        generation, cases, {"base": {"base": True}, **inputs}
    )
    if (
        manifest["data_sha256"] != intent["dataset_sha256"]
        or manifest["model_repo"] != intent["base"]["model"]
        or manifest["snapshot_manifest_sha256"] != intent["base"]["snapshot_sha256"]
        or manifest.get("dialogue_protocol") != "own-history-v1"
    ):
        raise ValueError("conversation_generation_identity_mismatch")
    return manifest


def _finish_counts(generation: Path, manifest: dict, intent: dict) -> dict:
    counts: dict[str, Counter[str]] = {tag: Counter() for tag in manifest["models"]}
    for (_, tag), row in _raw_rows(generation, manifest).items():
        response = row["response"]
        finish = response.get("finish")
        has_error = response.get("error") is not None
        counts[tag][
            finish if not has_error and finish in ("stop", "length") else "error"
        ] += 1
        text = response.get("text")
        counts[tag]["nonempty"] += bool(isinstance(text, str) and text.strip())
        counts[tag]["turns"] += 1
    tags = {
        "base": "base",
        **{arm: f"checkpoint-{intent[arm]['step']}" for arm in ("parent", "candidate")},
    }
    fields = ("turns", "stop", "length", "error", "nonempty")
    return {arm: {key: counts[tag][key] for key in fields} for arm, tag in tags.items()}


def generate_panel(
    args: argparse.Namespace, *, evaluator: Evaluator = _evaluate
) -> dict:
    """Generate paired evidence in a separate diagnostic store without promotion."""
    steps = (args.parent_step, args.candidate_step)
    if len(set(steps)) != 2 or any(not 1 <= step <= 10000 for step in steps):
        raise ValueError("conversation_generation_steps_invalid")
    if not 1 <= args.max_seconds <= 86400:
        raise ValueError("conversation_generation_timeout_invalid")
    output = operator_path(args.output)
    dataset = operator_path(args.dataset)
    snapshot = operator_path(args.snapshot)
    venv = operator_path(args.venv, allow_symlinks=True)
    if not snapshot.is_dir() or not (venv / "bin/python").is_file():
        raise ValueError("conversation_generation_runtime_missing")
    panel = read_json(args.panel)
    conversations, _, _, _, turns = _validate_panel("dev", panel)
    dataset_hash = digest(dataset)
    cases = rows(dataset)
    validate_dev_cases(cases)
    _case_index(cases, panel)
    if digest(dataset) != dataset_hash:
        raise ValueError("conversation_generation_dataset_changed")
    base = {
        "model": read_json(SNAPSHOT_PIN)["repo"],
        "snapshot_sha256": digest(SNAPSHOT_PIN),
    }
    parent = _adapter_identity(args.parent_step, args.parent, base)
    candidate = _adapter_identity(args.candidate_step, args.candidate, base)
    if parent["identity"]["weights_sha256"] == candidate["identity"]["weights_sha256"]:
        raise ValueError("conversation_generation_same_weights")
    intent = {
        "schema_version": 1,
        "panel_sha256": payload_sha(panel),
        "dataset_sha256": dataset_hash,
        "conversations": conversations,
        "turns": turns,
        "base": base,
        "parent": parent,
        "candidate": candidate,
    }
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    with file_lock(output / ".generation.lock", blocking=False):
        return _generate_locked(args, output, cases, intent, evaluator)


def _generate_locked(
    args: argparse.Namespace,
    output: Path,
    cases: list[dict],
    intent: dict,
    evaluator: Evaluator,
) -> dict:
    intent_path = output / "generation-intent.json"
    if intent_path.exists():
        if read_json(intent_path) != intent:
            raise ValueError("conversation_generation_intent_changed")
    else:
        atomic_json(intent_path, intent)
    parent, candidate = intent["parent"], intent["candidate"]
    steps = (parent["step"], candidate["step"])
    inputs = {
        f"checkpoint-{entry['step']}": _model_hashes(entry)
        for entry in (parent, candidate)
    }
    generation = output / "generation"
    if not generation.exists():
        stage = output / f"attempt-{uuid4().hex}"
        _run_evaluator(args, output, stage, evaluator, intent)
        seal_generation(stage)
        _generation_manifest(stage, cases, intent, inputs)
        stage.rename(generation)
    manifest = _generation_manifest(generation, cases, intent, inputs)
    if digest(args.dataset) != intent["dataset_sha256"]:
        raise ValueError("conversation_generation_dataset_changed")
    publish_pairs(output, generation, cases, inputs, list(steps))
    counts = _finish_counts(generation, manifest, intent)
    result = {
        **intent,
        "status": "complete",
        "generation_counts": counts,
        "input_sha256": stable_hash(intent),
        "generation_path": generation.name,
        "generation_seal_sha256": digest(generation / GENERATION_SEAL),
        "resumed_generations": manifest.get("resumed_generations", 0),
        **{
            arm: {
                **entry,
                "generation_seal_sha256": digest(
                    step_directory(output, entry["step"]) / GENERATION_SEAL
                ),
            }
            for arm, entry in (("parent", parent), ("candidate", candidate))
        },
    }
    acceptance = output / "generation-acceptance.json"
    if acceptance.exists():
        if read_json(acceptance) != result:
            raise ValueError("conversation_generation_acceptance_changed")
    else:
        atomic_json(acceptance, result)
    return result


def _run_evaluator(
    args: argparse.Namespace,
    output: Path,
    stage: Path,
    evaluator: Evaluator,
    intent: dict,
) -> None:
    command = [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        "bash",
        str(EVALUATOR),
        str(operator_path(args.snapshot)),
        str(operator_path(args.dataset)),
        str(stage),
        str(operator_path(args.venv, allow_symlinks=True)),
        "--resume-partial",
        "base",
        f"checkpoint-{args.parent_step}={operator_path(args.parent)}",
        f"checkpoint-{args.candidate_step}={operator_path(args.candidate)}",
    ]
    run_id = f"review-{stable_hash(intent)[:20]}"
    evaluator(
        command,
        output / f"{stage.name}.log",
        args.max_seconds,
        run_id,
        intent["base"]["model"],
        shared_runtime=not args.dedicated_runtime,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in (
        "panel",
        "dataset",
        "snapshot",
        "venv",
        "parent",
        "candidate",
        "output",
    ):
        parser.add_argument("--" + argument, required=True, type=Path)
    for argument in ("parent-step", "candidate-step"):
        parser.add_argument("--" + argument, required=True, type=int)
    parser.add_argument("--max-seconds", type=int, default=7200)
    parser.add_argument(
        "--dedicated-runtime",
        action="store_true",
        help="Require the API to be absent and keep the existing GPU lease checks.",
    )
    args = parser.parse_args(argv)
    try:
        result = generate_panel(args)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Conversation generation failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
