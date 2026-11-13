"""Prepare and verify a portable, qualification-only Omni GPU session input.

The archive contains train/dev text and a bounded smoke recipe. Model weights,
credentials, held-out cases and historical set B are never copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from scripts.academy.omni_pl_chat_data import read_jsonl, validate_splits
from scripts.academy.omni_pl_chat_recipe import validate_recipe

FILES = ("train.jsonl", "dev.jsonl", "recipe.json", "smoke-recipe.json")
FORBIDDEN_SOURCE_PARTS = {"holdout", "set-b", "set_b", "benchmark", "pl-assistant-v1"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _commit(code_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=code_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(result) != 40 or any(c not in "0123456789abcdef" for c in result):
        raise ValueError("source commit must be a full SHA-1")
    return result


def _clean_checkout(code_root: Path) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=code_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise ValueError("remote checkout has uncommitted tracked changes")


def prepare(profile_path: Path, output: Path, code_root: Path) -> dict:
    profile = _json(profile_path)
    train = Path(profile["train"]).resolve(strict=True)
    dev = Path(profile["dev"]).resolve(strict=True)
    if train.is_symlink() or dev.is_symlink():
        raise ValueError("training inputs must be regular files")
    for path in (train, dev):
        if any(part.lower() in FORBIDDEN_SOURCE_PARTS for part in path.parts):
            raise ValueError("reserved evaluation data cannot enter the session")
    if digest(train) != profile["train_sha256"] or digest(dev) != profile["dev_sha256"]:
        raise ValueError("profile data hashes differ from files")
    training = read_jsonl(train)
    validation = read_jsonl(dev)
    validate_splits(training, validation)
    if any(row["split"] != "train" for row in training) or any(
        row["split"] != "dev" for row in validation
    ):
        raise ValueError("expected train and dev splits")
    recipe = validate_recipe(profile["recipe"])
    recipe["train_sha256"] = digest(train)
    pin = _json(code_root / "scripts/llm/omni_native_snapshot.json")
    if profile["model"] != pin["repo"]:
        raise ValueError("profile model differs from pinned Omni")
    source_commit = _commit(code_root)
    smoke = {
        **recipe,
        "steps": 16,
        "save_every": 8,
        "warmup_steps": min(recipe["warmup_steps"], 7),
    }
    validate_recipe(smoke)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(train, output / "train.jsonl")
    shutil.copyfile(dev, output / "dev.jsonl")
    _write(output / "recipe.json", recipe)
    _write(output / "smoke-recipe.json", smoke)
    manifest = {
        "schema_version": 1,
        "purpose": "remote_technical_qualification_only",
        "source_commit": source_commit,
        "model": profile["model"],
        "revision": pin["revision"],
        "train_records": len(training),
        "dev_records": len(validation),
        "files": {name: digest(output / name) for name in FILES},
        "stages": [
            "preflight",
            "smoke_initial_8",
            "smoke_resume_16",
            "evaluate_base_adapter",
        ],
        "excluded": ["model_weights", "credentials", "holdout", "historical_set_B"],
    }
    _write(output / "manifest.json", manifest)
    return manifest


def verify(bundle: Path, code_root: Path | None = None) -> dict:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("session bundle must be a real directory")
    manifest = _json(bundle / "manifest.json")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("purpose") != "remote_technical_qualification_only"
        or set(manifest.get("files", {})) != set(FILES)
        or set(path.name for path in bundle.iterdir()) != {*FILES, "manifest.json"}
    ):
        raise ValueError("unexpected session bundle structure")
    for name in FILES:
        path = bundle / name
        if (
            path.is_symlink()
            or not path.is_file()
            or digest(path) != manifest["files"][name]
        ):
            raise ValueError(f"session input differs: {name}")
    recipe = validate_recipe(_json(bundle / "recipe.json"))
    smoke = validate_recipe(_json(bundle / "smoke-recipe.json"))
    if recipe["train_sha256"] != digest(bundle / "train.jsonl") or (
        smoke["train_sha256"] != recipe["train_sha256"]
        or smoke["steps"] != 16
        or smoke["save_every"] != 8
    ):
        raise ValueError("session recipes differ from frozen inputs")
    training = read_jsonl(bundle / "train.jsonl")
    validation = read_jsonl(bundle / "dev.jsonl")
    validate_splits(training, validation)
    if (
        len(training) != manifest["train_records"]
        or len(validation) != manifest["dev_records"]
    ):
        raise ValueError("session record counts differ")
    if code_root is not None:
        pin = _json(code_root / "scripts/llm/omni_native_snapshot.json")
        if (
            manifest["source_commit"] != _commit(code_root)
            or manifest["model"] != pin["repo"]
            or manifest["revision"] != pin["revision"]
        ):
            raise ValueError("session differs from the reviewed checkout")
    return manifest


def run_stage(
    bundle: Path,
    code_root: Path,
    snapshot: Path,
    venv: Path,
    output: Path,
    stage: str,
) -> None:
    """Execute one explicit stage on an already prepared GPU host."""
    verify(bundle, code_root)
    _clean_checkout(code_root)
    if output.is_symlink() or snapshot.is_symlink() or venv.is_symlink():
        raise ValueError("session paths must be real directories")
    if not snapshot.is_dir() or not (venv / "bin/python").is_file():
        raise ValueError("snapshot or training interpreter is unavailable")
    if not output.is_dir():
        output.mkdir(parents=True)
    script = code_root / "scripts/academy/omni_pl_chat_p1.sh"
    common = ["bash", str(script), str(snapshot), str(bundle / "train.jsonl")]
    smoke = output / "smoke"
    if stage == "preflight":
        receipt = output / "preflight/preflight.json"
        if receipt.exists():
            result = _json(receipt)
            if result.get("recipe") != _json(
                bundle / "smoke-recipe.json"
            ) or result.get("train_sha256") != digest(bundle / "train.jsonl"):
                raise ValueError("preflight receipt differs from frozen inputs")
            return
        argv = [
            *common,
            str(output / "preflight"),
            str(venv),
            "preflight",
            str(bundle / "smoke-recipe.json"),
        ]
    elif stage == "smoke":
        receipt = output / "preflight/preflight.json"
        if not receipt.is_file():
            raise ValueError("preflight must pass before GPU smoke")
        if _json(receipt).get("recipe") != _json(bundle / "smoke-recipe.json") or _json(
            receipt
        ).get("train_sha256") != digest(bundle / "train.jsonl"):
            raise ValueError("preflight receipt differs from frozen inputs")
        if (smoke / "resume.json").exists():
            from scripts.academy.omni_pl_chat_p1 import verify_checkpoint

            verify_checkpoint(smoke / "checkpoint-16")
            return
        if smoke.exists():
            from scripts.academy.omni_pl_chat_p1 import verify_checkpoint

            verify_checkpoint(smoke / "checkpoint-8")
            mode = "resume"
        else:
            mode = "initial"
        argv = [
            *common,
            str(smoke),
            str(venv),
            mode,
            str(bundle / "smoke-recipe.json"),
        ]
    elif stage == "evaluate":
        from scripts.academy.omni_pl_chat_p1 import verify_checkpoint

        if not (smoke / "resume.json").is_file():
            raise ValueError("completed smoke is required for evaluation")
        checkpoint = smoke / "checkpoint-16"
        verify_checkpoint(checkpoint)
        if (output / "evaluation").exists():
            raise ValueError("evaluation output already exists; use a new run")
        argv = [
            "bash",
            str(script),
            str(snapshot),
            str(bundle / "dev.jsonl"),
            str(output / "evaluation"),
            str(venv),
            "evaluate",
            "base",
            f"checkpoint-16={checkpoint}",
        ]
    else:
        raise ValueError("unknown remote qualification stage")
    subprocess.run(argv, cwd=code_root, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--profile", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--code-root", type=Path, default=Path.cwd())
    check = sub.add_parser("verify")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--code-root", type=Path)
    run = sub.add_parser("run-stage")
    run.add_argument("--bundle", type=Path, required=True)
    run.add_argument("--code-root", type=Path, required=True)
    run.add_argument("--snapshot", type=Path, required=True)
    run.add_argument("--venv", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--stage", choices=["preflight", "smoke", "evaluate"], required=True
    )
    args = parser.parse_args()
    if args.command == "run-stage":
        run_stage(
            args.bundle,
            args.code_root,
            args.snapshot,
            args.venv,
            args.output,
            args.stage,
        )
        return
    result = (
        prepare(args.profile, args.output, args.code_root)
        if args.command == "prepare"
        else verify(args.bundle, args.code_root)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
