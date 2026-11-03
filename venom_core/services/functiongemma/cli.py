"""CPU preparation by default; GPU execution requires an explicit request."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from venom_core.services.granite_operator.contract import file_digest, write_json
from venom_core.services.remote_training.paths import operator_path

from .profile import Recipe


def read(path: str | Path):
    return json.loads(operator_path(path).read_text(encoding="utf-8-sig"))


def export(args) -> dict:
    from .dataset import export_decisions

    output = operator_path(args.output)
    if output.exists():
        raise FileExistsError("functiongemma_output_exists")
    records = {}
    for split in ("train", "validation"):
        path = operator_path(getattr(args, split))
        records[split] = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
    release = export_decisions(records)
    write_json(output, release)
    return {
        "status": "DECISIONS_EXPORTED",
        "manifest": release["manifest"],
        "release_sha256": release["release_sha256"],
        "activation_allowed": False,
    }


def prepare(args) -> dict:
    from transformers import AutoTokenizer

    from .dataset import export_decisions
    from .encoding import encode_release, validate_encoded_release

    recipe = Recipe()
    snapshot = operator_path(args.snapshot, allow_symlinks=True)
    if snapshot.name != recipe.revision:
        raise ValueError("functiongemma_pinned_snapshot_required")
    output = operator_path(args.output)
    if output.exists():
        raise FileExistsError("functiongemma_output_exists")
    records = {}
    sources = {}
    for split in ("train", "validation"):
        path = operator_path(getattr(args, split))
        records[split] = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
        sources[split] = {"sha256": file_digest(path), "records": len(records[split])}
    release = export_decisions(records)
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    encoded = encode_release(release, tokenizer, context=recipe.context)
    checked = validate_encoded_release(encoded, context=recipe.context)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "release.json", release)
    write_json(output / "encoded.json", encoded)
    for method in ("full", "lora"):
        write_json(
            output / (method + "-recipe.json"),
            replace(recipe, method=method).identity(),
        )
    report = {
        "status": "CPU_PREPARED",
        "sources": sources,
        "budget": recipe.budget(len(checked["train"])),
        "training_qualified": False,
        "activation_allowed": False,
        "model_loaded": False,
    }
    write_json(output / "preparation.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--samples", type=int, required=True)
    exported = sub.add_parser("export")
    for key in ("train", "validation", "output"):
        exported.add_argument("--" + key, required=True)
    prep = sub.add_parser("prepare")
    for key in ("train", "validation", "snapshot", "output"):
        prep.add_argument("--" + key, required=True)
    run = sub.add_parser("run")
    run.add_argument("request")
    compare = sub.add_parser("compare")
    compare.add_argument("trials")
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = {
            "recipe": Recipe().identity(),
            "budget": Recipe().budget(args.samples),
            "activation_allowed": False,
        }
    elif args.command == "export":
        result = export(args)
    elif args.command == "prepare":
        result = prepare(args)
    elif args.command == "run":
        from .worker import run

        result = run(read(args.request))
    else:
        from .evaluation import compare

        result = compare(read(args.trials))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0
