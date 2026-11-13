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


def verify(bundle: Path) -> dict:
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
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--profile", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--code-root", type=Path, default=Path.cwd())
    check = sub.add_parser("verify")
    check.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    result = (
        prepare(args.profile, args.output, args.code_root)
        if args.command == "prepare"
        else verify(args.bundle)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
