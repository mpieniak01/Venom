"""Explicit CPU preparation commands, with immutable local evidence outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[3] / "config/gemma4_operator_profile.json"
)
MAX_INPUT_BYTES = 32 * 1024 * 1024


def read_document(path: Path) -> Any:
    """Read bounded local JSON as data; never execute material or observations."""
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("gemma_input_missing_or_too_large")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def result_code(document: Any) -> int:
    """Keep command receipts consistent with mismatched or incomplete evidence."""
    if isinstance(document, dict):
        if document.get("status") == "MISMATCH":
            return 2
        if document.get("comparison_complete") is False:
            return 3
    return 0


def publish(path: Path | None, document: Any) -> None:
    """Refuse to replace previous preparation or qualification evidence."""
    if path is None:
        print(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False))
        return
    payload = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")
    print(
        json.dumps(
            {
                "ok": result_code(document) == 0,
                "output": str(path),
                "exit_code": result_code(document),
            },
            ensure_ascii=False,
        )
    )


def preparation_plan(profile) -> dict:
    """Describe available CPU commands and separate remote qualification gates."""
    return {
        "schema_version": 1,
        "status": "PREPARED",
        "profile": profile.identity(),
        "execution_location": "cpu_control",
        "model_loaded": False,
        "training_started": False,
        "activation_authorized": False,
        "available_commands": [
            "plan",
            "verify-snapshot",
            "prepare-material",
            "readiness",
            "compare",
        ],
        "remote_gates": [
            {"stage": stage, "status": "DEFERRED_REMOTE"}
            for stage in (
                "tokenization_and_masks",
                "loader_and_tool_cycle",
                "baseline_gpu",
                "sft_qlora_or_lora",
                "checkpoint_reload",
                "candidate_evaluation",
            )
        ],
        "optional_experiments": ["dpo", "grpo", "full_sft", "multimodal_tuning"],
        "qualification": "cpu_preparation_is_not_model_or_training_qualification",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for command in (
        "plan",
        "verify-snapshot",
        "prepare-material",
        "readiness",
        "compare",
    ):
        item = sub.add_parser(command)
        if command in {"plan", "verify-snapshot", "readiness"}:
            item.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
        item.add_argument("--output", type=Path, required=command == "prepare-material")
        if command == "verify-snapshot":
            item.add_argument("--snapshot", type=Path, required=True)
        if command in {"prepare-material", "compare"}:
            item.add_argument("--input", type=Path, required=True)
        if command == "readiness":
            item.add_argument("--request", type=Path, required=True)
            item.add_argument("--observed", type=Path)
    return root


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "prepare-material":
        from .material import prepare_material

        return prepare_material(read_document(args.input))
    if args.command == "compare":
        from .evaluation import compare_trials

        data = read_document(args.input)
        if not isinstance(data, dict) or set(data) != {"identities", "trials"}:
            raise ValueError("gemma_comparison_input_invalid")
        return compare_trials(data["trials"], identities=data["identities"])
    from .profile import GemmaProfile

    profile = GemmaProfile.load(args.profile)
    if args.command == "plan":
        return preparation_plan(profile)
    if args.command == "verify-snapshot":
        return {
            "status": "METADATA_VERIFIED",
            "files": profile.validate_snapshot(args.snapshot),
            "weights_verified": False,
            "gpu_qualified": False,
        }
    from .runtime import readiness_report

    return readiness_report(
        profile,
        read_document(args.request),
        read_document(args.observed) if args.observed else None,
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        publish(args.output, result)
        return result_code(result)
    except RecursionError:
        print(json.dumps({"ok": False, "error": "gemma_input_nesting_exceeded"}))
        return 1
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0
