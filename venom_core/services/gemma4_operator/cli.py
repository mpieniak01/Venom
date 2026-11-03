"""Explicit CPU preparation commands, with immutable local evidence outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .errors import EvidenceMismatch
from .paths import checked_directory, checked_file

DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[3] / "config/gemma4_operator_profile.json"
)
MAX_INPUT_BYTES = 32 * 1024 * 1024


def read_document(path: Path) -> Any:
    """Read bounded local JSON as data; never execute material or observations."""
    path = checked_file(path)
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("gemma_input_missing_or_too_large")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def result_code(document: Any) -> int:
    """Keep command receipts consistent with mismatched or incomplete evidence."""
    if isinstance(document, dict):
        if document.get("status") == "MISMATCH":
            return 2
        if (
            document.get("comparison_complete") is False
            or document.get("status") == "REFERENCE_FAIL"
        ):
            return 3
        if document.get("status") == "REJECTED":
            return 4
    return 0


def publish(path: Path | None, document: Any) -> None:
    """Refuse to replace previous preparation or qualification evidence."""
    if path is None:
        print(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False))
        return
    path = checked_file(path, output=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix="." + path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if a concurrent writer
        # already created the target; rename/replace would overwrite it.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
            "freeze-material",
            "qualify-cases",
            "export-experience",
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


def _command_parser(sub, name, *, profile=False, output=False, inputs=()):
    item = sub.add_parser(name)
    if profile:
        item.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    item.add_argument("--output", type=Path, required=output)
    for option, required in inputs:
        item.add_argument("--" + option, type=Path, required=required)
    return item


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    _command_parser(sub, "plan", profile=True)
    _command_parser(sub, "verify-snapshot", profile=True, inputs=(("snapshot", True),))
    _command_parser(sub, "prepare-material", output=True, inputs=(("input", True),))
    _command_parser(
        sub, "readiness", profile=True, inputs=(("request", True), ("observed", False))
    )
    _command_parser(sub, "compare", inputs=(("input", True),))
    _command_parser(
        sub, "freeze-material", profile=True, output=True, inputs=(("input", True),)
    )
    _command_parser(sub, "qualify-cases", inputs=(("manifest", True),))
    _command_parser(
        sub,
        "export-experience",
        output=True,
        inputs=(("task", True), ("receipt", False), ("evidence", False)),
    )
    return root


def _export_experience(args):
    from .experience import build_experience

    evidence = checked_file(args.evidence) if args.evidence else None
    if evidence is not None and evidence.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("gemma_evidence_too_large")
    return build_experience(
        read_document(args.task),
        read_document(args.receipt) if args.receipt else None,
        evidence.read_bytes() if evidence else None,
    )


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "qualify-cases":
        from .benchmark import qualify_cases

        return qualify_cases(checked_file(args.manifest, profile=True))
    if args.command == "export-experience":
        return _export_experience(args)
    return _dispatch_material_or_runtime(args)


def _dispatch_material_or_runtime(args: argparse.Namespace) -> Any:
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
    if args.command == "freeze-material":
        from .data_release import build_release

        return build_release(read_document(args.input), profile)
    if args.command == "verify-snapshot":
        return {
            "status": "METADATA_VERIFIED",
            "files": profile.validate_snapshot(checked_directory(args.snapshot)),
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
    except EvidenceMismatch as exc:
        print(json.dumps({"ok": False, "status": "MISMATCH", "error": str(exc)}))
        return 2
    except RecursionError:
        print(json.dumps({"ok": False, "error": "gemma_input_nesting_exceeded"}))
        return 1
    except (ValueError, TypeError, OSError, KeyError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0
