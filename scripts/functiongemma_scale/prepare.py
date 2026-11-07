"""Build the private, CPU-qualified three-arm FunctionGemma experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from venom_core.services.functiongemma.dataset import validate_release
from venom_core.services.functiongemma.encoding import encode_release
from venom_core.services.functiongemma.execution import pack, preflight
from venom_core.services.functiongemma.profile import REVISION, Recipe
from venom_core.services.functiongemma.protocol import render_messages
from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training.bundles import extract_bundle

from .cases import corrected_rows, counterfactuals, distribution, make_suite, pilot
from .legacy import adapt
from .score import score_suite
from .weights import expand

ROOT = Path(__file__).resolve().parents[2]
SEEDS = (42, 43)
TRAINING_STEPS = 128
SUITE = "fg-scale"
EVALUATOR = ("run_evaluation.py", "native_worker.py", "score_results.py")
LEGACY = ("development-128", "repair-diagnostic-64")
HISTORICAL_ACCEPTANCE = ("acceptance-256", "operator-scenarios-64")
QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')
SPACES = re.compile(r"\s+")


def read(path):
    """Read one JSON document from the selected local archive."""
    return json.loads(path.read_text(encoding="utf-8"))


def release_for(train, validation):
    """Build a split release with digests tied to its ordered decisions."""
    records = {"train": train, "validation": validation}
    release = {
        "schema_version": 1,
        "kind": "functiongemma_decision_release",
        "records": records,
        "records_sha256": digest(records),
        "source_records_sha256": digest(records),
        "manifest": {
            "counts": {name: len(rows) for name, rows in records.items()},
            "skipped": {},
            "split_policy": "problem_group_before_decision_expansion",
            "sources_modified": False,
        },
    }
    release["release_sha256"] = digest(release)
    return release


def signature(row, *, template):
    """Normalize the last user prompt for exact or template overlap detection."""
    prompt = next(
        m["content"] for m in reversed(row["messages"][:-1]) if m["role"] == "user"
    )
    if template:
        prompt = re.sub(r"\d+", "#", QUOTED.sub("<value>", prompt))
    return SPACES.sub(" ", unicodedata.normalize("NFC", prompt).casefold()).strip()


def disjoint(left, right, *, templates):
    """Reject shared IDs, problem groups, or prompts between evaluation and training."""
    sets = (
        [{row["record_id"] for row in rows} for rows in (left, right)],
        [{row["problem_group"] for row in rows} for rows in (left, right)],
        [
            {signature(row, template=templates) for row in rows}
            for rows in (left, right)
        ],
    )
    overlap = dict(
        zip(
            ("ids", "groups", "prompt_templates" if templates else "exact_prompts"),
            (len(a & b) for a, b in sets),
            strict=True,
        )
    )
    if any(overlap.values()):
        raise ValueError(f"evaluation overlaps training or another split: {overlap}")
    return overlap


def archived_cases(history, historical_acceptance):
    """Verify the prior acceptance and retention suites against their recorded digests."""
    execution = history / "execution"
    specs = read(execution / "evaluation-plan.json")["suites"]
    preserved = {}
    with ZipFile(historical_acceptance) as archive:
        frozen_rows = []
        for name in HISTORICAL_ACCEPTANCE:
            body = archive.read(f"evaluation/{name}.json")
            actual = hashlib.sha256(body).hexdigest()
            if actual != specs[name]["sha256"]:
                raise ValueError(f"historical acceptance changed: {name}")
            frozen_rows.extend(c["record"] for c in json.loads(body)["cases"])
            preserved[name] = specs[name]
    retained = []
    for name in LEGACY:
        path = execution / "scoring-cases" / (name + ".json")
        if file_digest(path) != specs[name]["sha256"]:
            raise ValueError(f"historical retention changed: {name}")
        retained.extend(read(path)["cases"])
        preserved[name] = specs[name]
    return retained, frozen_rows, preserved


async def evaluation(history, output, tokenizer, suites):
    """Build and verify the reference fixtures for sealed development and acceptance bundles."""
    development = output / "evaluation"
    acceptance = output / "acceptance"
    development.mkdir()
    acceptance.mkdir()
    specs, references = {}, {}
    phases = {
        "pilot": ["pilot-16"],
        "development": [
            "scale-development-128",
            "scale-counterfactual-24",
            "scale-retention-192",
        ],
        "acceptance": ["scale-acceptance-256"],
    }
    for name, cases in suites.items():
        directory = acceptance if name in phases["acceptance"] else development
        path = directory / (name + ".json")
        write_json(path, {"cases": cases})
        specs[name] = {"sha256": file_digest(path), "count": len(cases)}
        maximum = max(
            len(
                tokenizer(
                    render_messages(
                        tokenizer,
                        case["record"]["messages"][:-1],
                        case["record"]["tools"],
                        add_generation_prompt=True,
                    ),
                    add_special_tokens=False,
                )["input_ids"]
            )
            for case in cases
        )
        if maximum + 256 > 2048:
            raise ValueError(f"generation context exceeds 2048: {name}")
        report = await score_suite(cases)
        if report["total"]["correct"] != len(cases):
            fails = [
                row["record_id"] for row in report["verdicts"] if not row["correct"]
            ]
            raise ValueError(f"fixture oracle mismatch: {fails[:6]}")
        references[name] = {**report["total"], "max_prompt_tokens": maximum}
    plan = {"phases": phases, "suites": specs}
    write_json(output / "evaluation-plan.json", plan)
    with (
        ZipFile(history / "execution/evaluation-precision.zip") as old,
        ZipFile(output / "evaluation.zip", "x", ZIP_DEFLATED) as bundle,
    ):
        for name in EVALUATOR:
            bundle.writestr(name, old.read(name))
        bundle.write(output / "evaluation-plan.json", "evaluation-plan.json")
        for name in phases["pilot"] + phases["development"]:
            bundle.write(development / (name + ".json"), f"evaluation/{name}.json")
    with ZipFile(output / "acceptance.zip", "x", ZIP_DEFLATED) as bundle:
        for name in phases["acceptance"]:
            bundle.write(acceptance / (name + ".json"), name + ".json")
    return specs, references


def prepare_run(
    output, label, seed, weights, snapshot, encoded, data, checkpoint_hashes
):
    """Round-trip one training plan through the same validation used by the remote worker."""
    run_id = f"{SUITE}-{label}-{seed}"
    run_dir = output / "runs" / run_id
    run_dir.mkdir(parents=True)
    recipe = Recipe(
        context=2048,
        epochs=1,
        learning_rate=2e-6,
        seed=seed,
        checkpoint_interval=32,
        parameter_dtype="fp32",
        initial_weights=checkpoint_hashes,
    )
    bundle = run_dir / "input.zip"
    manifest = pack(
        encoded,
        recipe.identity(),
        snapshot,
        bundle,
        run_id=run_id,
        updates=TRAINING_STEPS,
        max_seconds=900,
    )
    budget = recipe.budget(len(data["records"]["train"]))
    with TemporaryDirectory(dir=run_dir) as temporary:
        scratch = Path(temporary)
        warm = scratch / "warm-start"
        warm.mkdir()
        for name in checkpoint_hashes:
            os.link(weights / name, warm / name)
        extract_bundle(
            bundle,
            scratch / "input",
            expected_run_id=run_id,
            expected_identity=manifest["identity"],
        )
        actual_recipe, actual_data = preflight(
            {"code_root": str(ROOT), "snapshot": str(snapshot)},
            scratch / "input",
            manifest["identity"],
        )
        if (actual_recipe, actual_data) != (recipe, data):
            raise ValueError("training bundle did not round trip")
    plan = {
        "status": "CPU_PREFLIGHT_PASS",
        "run_id": run_id,
        "arm": label,
        "seed": seed,
        "identity": manifest["identity"],
        "recipe": recipe.identity(),
        "budget": budget,
        "bundle_sha256": file_digest(bundle),
        "source_encoded_sha256": file_digest(encoded),
        "warm_start": weights.name,
        "training_checkpoints": [32, 64, 96, 128],
        "evaluated_checkpoints": [32, 64, 128],
        "gpu_authorized": False,
    }
    write_json(run_dir / "launch-plan.json", plan)
    print(run_id, "CPU_PREFLIGHT_PASS", flush=True)
    return plan


async def prepare(history, snapshot, output, *, start_weights, historical_acceptance):
    """Prepare six matched training runs and sealed evaluations without starting training."""
    from loguru import logger
    from transformers import AutoTokenizer

    logger.disable("venom_core")
    if snapshot.name != REVISION:
        raise ValueError("expected pinned tokenizer snapshot")
    source = history / "narrow-experiment"
    source_release = source / "narrow/release.json"
    legacy_train = validate_release(read(source_release))["train"]
    corrected = corrected_rows(legacy_train)
    if distribution(legacy_train) != distribution(corrected):
        raise ValueError("training action or language distribution changed")
    development = make_suite(legacy_train)
    frozen = make_suite(legacy_train, acceptance=True)
    archived, old_frozen, archived_specs = archived_cases(
        history, historical_acceptance
    )
    dev_rows = [c["record"] for c in development]
    frozen_rows = [c["record"] for c in frozen]
    legacy_rows = [c["record"] for c in archived]
    separation = {
        "development/acceptance": disjoint(dev_rows, frozen_rows, templates=True)
    }
    for label, rows in (("original", legacy_train), ("corrected", corrected)):
        for suite, held, templates in (
            ("development", dev_rows, True),
            ("acceptance", frozen_rows, True),
            ("historical-retention", legacy_rows, False),
            ("historical-acceptance", old_frozen, False),
        ):
            separation[f"{label}/{suite}"] = disjoint(rows, held, templates=templates)
    suites = {
        "pilot-16": pilot(development),
        "scale-development-128": development,
        "scale-counterfactual-24": counterfactuals(development),
        "scale-retention-192": [
            adapt(c, legacy_train[0]["messages"][0]["content"]) for c in archived
        ],
        "scale-acceptance-256": frozen,
    }
    output.mkdir(mode=0o700, parents=True)
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    specs, references = await evaluation(history, output, tokenizer, suites)
    print("Reference sandbox and split audit PASS", flush=True)
    encodings = {}
    for key, train in (("original", legacy_train), ("corrected", corrected)):
        directory = output / key
        directory.mkdir()
        release = release_for(train, dev_rows)
        write_json(directory / "release.json", release)
        document = encode_release(release, tokenizer, context=2048)
        encoded = directory / "encoded.json"
        write_json(encoded, document)
        encodings[key] = (encoded, document)
    original_encoded = read(source / "narrow/encoded.json")["records"]["train"]
    if encodings["original"][1]["records"]["train"] != original_encoded:
        raise ValueError("legacy control tokens differ from the original corpus")
    print("Native tokenization and unchanged control tokens PASS", flush=True)
    weight_store = output / "weights"
    weight_store.mkdir()
    expanded = weight_store / "299m"
    expansion = expand(start_weights, start_weights / "export-receipt.json", expanded)
    original = weight_store / "268m"
    original.mkdir()
    for name in expansion["original"]:
        shutil.copyfile(start_weights / name, original / name)
    write_json(output / "widening.json", expansion)
    print("Warm starts sealed", flush=True)
    plans = [
        prepare_run(
            output,
            arm,
            seed,
            weights,
            snapshot,
            *encodings[data],
            expansion[width],
        )
        for seed in SEEDS
        for arm, weights, data, width in (
            ("a", original, "original", "original"),
            ("b", original, "corrected", "original"),
            ("c", expanded, "corrected", "expanded"),
        )
    ]
    training_suite = read(source / "vast-offers/suite.json")
    write_json(output / "host-suite.json", training_suite)
    write_json(
        output / "readiness.json",
        {
            "status": "CPU_PACKAGES_PREPARED",
            "rented_host": False,
            "training_started": False,
            "code_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "experiment_code": {
                p.name: file_digest(p)
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
            "tokenizer_snapshot": str(snapshot),
            "source_release_sha256": file_digest(source_release),
            "language_and_action_distribution": distribution(legacy_train),
            "replaced_rows": sum(
                a != b for a, b in zip(legacy_train, corrected, strict=True)
            ),
            "separation": separation,
            "historical_seals": archived_specs,
            "suites": specs,
            "references": references,
            "runs": plans,
            "transfer_files": {
                name: file_digest(output / name)
                for name in (
                    "evaluation.zip",
                    "acceptance.zip",
                    "widening.json",
                    "host-suite.json",
                )
            },
        },
    )


def main():
    """Read explicit checkpoint and acceptance paths before preparing the experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("history", "snapshot", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--start-weights",
        type=Path,
        required=True,
        help="Directory of the source checkpoint with its export receipt.",
    )
    parser.add_argument(
        "--historical-acceptance",
        type=Path,
        required=True,
        help="Sealed evaluation archive referenced by the prior evaluation plan.",
    )
    args = parser.parse_args()
    asyncio.run(
        prepare(
            args.history.resolve(),
            args.snapshot.resolve(),
            args.output.resolve(),
            start_weights=args.start_weights.resolve(strict=True),
            historical_acceptance=args.historical_acceptance.resolve(strict=True),
        )
    )


if __name__ == "__main__":
    main()
