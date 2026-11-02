"""CPU-only experiment preparation and one selected adapter; no provider calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    MODEL,
    REVISION,
    TrainingProfile,
    write_json,
)

from .artifacts import inspect_artifacts, verify_result_bundle
from .bundles import _source, sha256, validate_run_id, verify_bundle
from .job import prepare
from .lifecycle import file_lock
from .milestones import plan
from .paths import operator_path

REPO = Path(__file__).resolve().parents[3]
METHODS = {"qlora": "nf4", "lora": "bf16"}
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


def _read(path: Path) -> dict:
    path = operator_path(path)
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError("experiment_metadata_too_large")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("experiment_metadata_invalid")
    return value


def _publish(path: Path, value: dict) -> None:
    """Idempotent publication; existing prepared evidence is never amended."""
    path = operator_path(path)
    if path.exists():
        if _read(path) != value:
            raise ValueError("experiment_prepared_output_changed")
        return
    write_json(path, value)


def select_result(
    archive: Path, adapter_root: Path, expected_sha256: str, step: int
) -> dict:
    """Select intact result bytes without importing, activating or granting resume."""
    if type(step) is not int or step < 1 or sha256(archive) != expected_sha256:
        raise ValueError("experiment_selected_archive_or_step_invalid")
    manifest = verify_bundle(archive)
    receipt = verify_result_bundle(
        archive,
        expected_identity=manifest["identity"],
        expected_run_id=manifest["run_id"],
    )
    if not receipt["complete"] or manifest["identity"]["model"] != MODEL:
        raise ValueError("experiment_selected_result_incomplete")
    if manifest["identity"]["revision"] != REVISION:
        raise ValueError("experiment_selected_base_revision_invalid")
    root = operator_path(adapter_root).resolve(strict=True)
    for name, entry in manifest["files"].items():
        path = _source(root, name)
        if path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            raise ValueError("experiment_selected_payload_changed")
    if (
        _read(root / "checkpoint/receipt.json").get("step") != step
        or _read(root / "metrics.json").get("global_step") != step
        or sha256(archive) != expected_sha256
    ):
        raise ValueError("experiment_selected_checkpoint_mismatch")
    return {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "step": step,
        "archive": str(operator_path(archive).resolve()),
        "archive_sha256": expected_sha256,
        "adapter_root": str(root),
        "adapter_sha256": manifest["files"]["adapter_model.safetensors"]["sha256"],
        "identity": manifest["identity"],
        "activation_state": "selected_pending_local_reload",
        "verification_scope": "CPU_integrity_only",
        "local_reload_verified": False,
        "local_resume_authorized": False,
    }


def selected(path: Path) -> dict:
    value = _read(path)
    current = select_result(
        Path(value["archive"]),
        Path(value["adapter_root"]),
        value["archive_sha256"],
        value["step"],
    )
    if current != value:
        raise ValueError("experiment_selection_changed")
    return current


def profiles(config: Path) -> dict[str, TrainingProfile]:
    result = {}
    for method, precision in METHODS.items():
        raw = _read(config / f"granite_operator_{method}.json")
        raw.pop("schema_version", None)
        profile = TrainingProfile(**raw)
        profile.validate()
        if profile.quantization != precision:
            raise ValueError("experiment_method_precision_mismatch")
        result[method] = profile
    controls = []
    for profile in result.values():
        control = profile.identity()
        control.pop("quantization")
        controls.append(control)
    if controls[0] != controls[1]:
        raise ValueError("experiment_controls_mismatch")
    return result


def operator_commands(run_id: str, bundle: Path, output: Path, updates: int) -> dict:
    """Separate explicit actions on an existing SSH alias, never a chained run."""
    prefix = [
        "python",
        "scripts/remote_training.py",
        "--host",
        "gpu-training",
        "--remote-python",
        "/workspace/data/remote-training/rpc-python",
    ]
    return {
        "upload": prefix + ["upload", "--bundle", str(bundle)],
        "smoke": prefix + ["start", "--run-id", run_id, "--stage", "smoke"],
        "status": prefix + ["status", "--run-id", run_id],
        "watch": prefix + ["watch", "--run-id", run_id, "--json-lines"],
        "train": prefix
        + [
            "start",
            "--run-id",
            run_id,
            "--stage",
            "train",
            "--until-update",
            str(updates),
        ],
        "collect": prefix
        + [
            "collect",
            "--run-id",
            run_id,
            "--include-checkpoint",
            "--output",
            str(output / "result.zip"),
        ],
        "inspect": [
            "python",
            "scripts/remote_training.py",
            "inspect-result",
            "--bundle",
            str(output / "result.zip"),
            "--input-bundle",
            str(bundle),
        ],
    }


def prepare_pair(
    source: Path,
    manifest: Path,
    snapshot: Path,
    output: Path,
    selection: Path,
    run_prefix: str,
    *,
    config: Path = REPO / "config",
    updates: int = 250,
    max_seconds: int = 7200,
) -> dict:
    """Publish each job independently; publish suite only after both are intact."""
    baseline = selected(selection)
    pair = profiles(config)
    runs = {method: run_prefix + "-" + method for method in METHODS}
    for run_id in runs.values():
        validate_run_id(run_id)
        plan(run_id, [updates], max_seconds)
    output = operator_path(output).absolute()
    output.mkdir(parents=True, exist_ok=True)
    document = _read(manifest)
    count = document["datasets"]["domain/train.jsonl"]["rows"]
    if type(count) is not int or count < 1:
        raise ValueError("experiment_dataset_count_invalid")
    jobs = {}
    with file_lock(output / ".prepare.lock", blocking=False):
        for method, profile in pair.items():
            folder = output / method
            folder.mkdir(exist_ok=True)
            _publish(folder / "profile.json", profile.identity())
            packed = prepare(
                source,
                manifest,
                folder / "profile.json",
                snapshot,
                folder / "input.zip",
                run_id=runs[method],
                dataset="domain",
                updates=updates,
                max_seconds=max_seconds,
            )
            _publish(folder / "input-manifest.json", packed)
            _publish(folder / "plan.json", plan(runs[method], [updates], max_seconds))
            _publish(
                folder / "operator-commands.json",
                operator_commands(
                    runs[method],
                    folder / "input.zip",
                    folder,
                    updates,
                ),
            )
            job = {
                "run_id": runs[method],
                "precision": profile.quantization,
                "input": str(folder / "input.zip"),
                "input_sha256": sha256(folder / "input.zip"),
                "identity": packed["identity"],
                "target_update": updates,
                "initialization": "pinned_original_base_no_adapter_resume",
                "gpu_qualification": "fresh_smoke_required",
            }
            _publish(folder / "READY.json", job)
            jobs[method] = job
        # Same data/token order and sample exposure; profiles differ only in precision.
        for key in (
            "data_sha256",
            "encoding_sha256",
            "code_sha256",
            "dependencies_sha256",
            "tokenizer_sha256",
            "template_sha256",
        ):
            if jobs["qlora"]["identity"][key] != jobs["lora"]["identity"][key]:
                raise ValueError("experiment_input_controls_mismatch")
        suite = {
            "schema_version": 1,
            "status": "CPU_PREPARED_GPU_SMOKE_REQUIRED",
            "selected_adapter": baseline,
            "selection_sha256": sha256(selection),
            "jobs": jobs,
            "training_execution": "sequential_on_one_host",
            "targets": TARGETS,
            "rows_per_epoch": count,
            "samples_seen": updates * pair["qlora"].accumulation,
            "epochs": updates * pair["qlora"].accumulation / count,
            "milestones": [updates],
            "publish_intermediate_adapters": False,
            "common_host_requirements": {
                "gpu_vram_gb": 24,
                "ram_gb": 64,
                "disk_gb": 100,
                "vm_required": True,
            },
            "primary_inference_precision": "nf4",
            "secondary_optional_precision": "bf16",
            "evaluation": {
                "remote_sessions": 4,
                "max_sessions": 8,
                "adaptive": True,
                "local_sessions": 1,
            },
            "host_retention": "retain_on_success_and_failure",
            "model_loaded": False,
            "training_started": False,
            "paid_host_created": False,
        }
        _publish(output / "suite.json", suite)
    return suite


def evaluation_commands(
    result: Path,
    host: Path,
    cases: list[Path],
    output: Path,
    *,
    precision: str = "nf4",
    placement: str = "remote",
    expected_step: int = 250,
) -> dict:
    """Prepare commands after collection; never load models or alter result bytes."""
    from scripts.granite_operator.comparison_support import load_frozen

    if (
        precision not in ("nf4", "bf16")
        or placement not in ("local", "remote")
        or not cases
    ):
        raise ValueError("experiment_evaluation_options_invalid")
    result, host, output = map(operator_path, (result, host, output))
    cases = [operator_path(path) for path in cases]
    identity = _read(result / "identity.json")
    run_id = _read(result / "status.json")["run_id"]
    receipt = inspect_artifacts(result, identity, run_id)
    if not receipt["complete"]:
        raise ValueError("experiment_evaluation_result_incomplete")
    if (
        type(expected_step) is not int
        or expected_step < 1
        or _read(result / "metrics.json").get("global_step") != expected_step
    ):
        raise ValueError("experiment_evaluation_checkpoint_mismatch")
    commands = []
    for index, path in enumerate(cases, 1):
        manifest, _ = load_frozen(path)
        if manifest.get("qualification", {}).get("status") != "PASS":
            raise ValueError("experiment_evaluation_cases_unqualified")
        concurrency = "4" if placement == "remote" else "1"
        commands.append(
            [
                "python",
                "-m",
                "scripts.granite_operator.comparison",
                "--adapter-root",
                str(result),
                "--host-root",
                str(host),
                "--cases",
                str(path),
                "--output",
                str(output / precision / f"benchmark-{index:02d}"),
                "--expected-adapter-sha256",
                sha256(result / "adapter_model.safetensors"),
                "--inference-precision",
                precision,
                "--execution-host",
                placement,
                "--concurrency",
                concurrency,
                "--batch-size",
                concurrency,
                "--adaptive" if placement == "remote" else "--no-adaptive",
                "--max-concurrency",
                "8" if placement == "remote" else "2",
            ]
        )
    return {
        "commands": commands,
        "inference_precision": precision,
        "execution": "explicit_one_at_a_time",
    }


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    sub = value.add_subparsers(dest="action", required=True)
    select = sub.add_parser("select")
    for name in ("archive", "adapter-root", "output"):
        select.add_argument("--" + name, type=Path, required=True)
    select.add_argument("--sha256", required=True)
    select.add_argument("--step", type=int, required=True)
    pair = sub.add_parser("prepare")
    for name in ("source", "manifest", "snapshot", "output", "selection"):
        pair.add_argument("--" + name, type=Path, required=True)
    pair.add_argument("--run-prefix", required=True)
    pair.add_argument("--config", type=Path, default=REPO / "config")
    pair.add_argument("--updates", type=int, default=250)
    pair.add_argument("--max-seconds", type=int, default=7200)
    evaluate = sub.add_parser("evaluation-commands")
    for name in ("result", "host", "output"):
        evaluate.add_argument("--" + name, type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, action="append", required=True)
    evaluate.add_argument("--expected-step", type=int, default=250)
    evaluate.add_argument("--precision", choices=("nf4", "bf16"), default="nf4")
    evaluate.add_argument("--placement", choices=("local", "remote"), default="remote")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == "select":
        result = select_result(args.archive, args.adapter_root, args.sha256, args.step)
        destination = operator_path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(destination.with_suffix(".lock"), blocking=False):
            _publish(destination, result)
    elif args.action == "prepare":
        result = prepare_pair(
            args.source,
            args.manifest,
            args.snapshot,
            args.output,
            args.selection,
            args.run_prefix,
            config=args.config,
            updates=args.updates,
            max_seconds=args.max_seconds,
        )
    else:
        result = evaluation_commands(
            args.result,
            args.host,
            args.cases,
            args.output,
            precision=args.precision,
            placement=args.placement,
            expected_step=args.expected_step,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
