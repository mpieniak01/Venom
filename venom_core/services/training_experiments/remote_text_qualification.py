"""Evaluate the frozen remote finalist once on a controller-held text holdout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from socket import create_connection
from typing import Annotated, TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from scripts.academy.omni_pl_chat_adapter import verify_initial_adapter
from scripts.academy.omni_pl_chat_data import validate_splits
from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    group_alive,
    process_identity,
)
from venom_core.services.remote_training.paths import data_directory, operator_path
from venom_core.services.remote_training.supervisor import _drain, _terminate
from venom_core.services.runtime_admission import (
    ACADEMY_TRAINING_OWNER,
    RuntimeAdmission,
    get_runtime_admission,
)

from .adapters import AdapterEntry, resolve_adapter, runner_identity
from .campaign_schema import CampaignId
from .checkpoint_evaluation import read_generation, seal_generation
from .evidence import (
    ADAPTER_FILES,
    WEIGHTS,
    calibrated_judgments,
    review_data,
    sealed_report,
)
from .profiles import digest, read_json, rows, stable_hash
from .quality_native import evaluation_identity
from .remote_text_evidence import _metrics, _receipt_matches, _sha, stage_candidate
from .service import REPO
from .worker import Worker

_TARGET_RUNTIME = "omni-native-peft-text"
_ENTRY = "final-qualification"
_INPUTS = "remote-text-final-inputs"
_MAX_PENDING_RETRIES = 3
_Bound = TypeVar("_Bound", list, dict)
_CAMPAIGN_ID = TypeAdapter(CampaignId)


class QualificationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train: Path
    dev: Path
    final_test: Path
    calibration: Path
    snapshot: Path
    training_venv: Path
    max_seconds: Annotated[int, Field(strict=True, ge=30, le=86400)]


def _binding(
    remote: dict, receipts: Mapping[str, dict], test_sha: str, calibration_sha: str
) -> dict:
    if remote.get("status") not in {"succeeded", "timed_out", "stopped"}:
        raise ValueError("remote_text_final_campaign_not_finished")
    if any(
        variant.get("initial_adapter") for variant in remote["plan"].get("variants", [])
    ):
        raise ValueError("remote_text_final_parent_comparison_required")
    run_id = remote.get("selected_run_id")
    receipt = receipts.get(run_id) if isinstance(run_id, str) else None
    trial = next((row for row in remote["trials"] if row["run_id"] == run_id), None)
    if receipt is None or trial is None or not _receipt_matches(receipt, remote, trial):
        raise ValueError("remote_text_final_candidate_missing")
    step = remote.get("selected_checkpoint_step")
    items = receipt["checkpoints"]
    if step is None and len(items) == 1:
        step = items[0]["step"]
    candidate = next((row for row in items if row["step"] == step), None)
    if candidate is None or candidate["adapter_available"] is not True:
        raise ValueError("remote_text_final_candidate_missing")
    return {
        "campaign_id": receipt["campaign_id"],
        "run_id": receipt["run_id"],
        "plan_sha256": receipt["plan_sha256"],
        "profile_identity": receipt["profile_identity"],
        "archive_sha256": receipt["archive_sha256"],
        "result_sha256": receipt["result_sha256"],
        "step": step,
        "checkpoint_sha256": candidate["sha256"],
        "development_identity": candidate["identity"],
        "development_protocol": stable_hash(remote["plan"]["selection"]),
        "final_test_sha256": _sha(test_sha),
        "final_calibration_sha256": _sha(calibration_sha),
    }


def _load_bound(path: Path, checksum: str, parser: Callable[[Path], _Bound]) -> _Bound:
    path = operator_path(path)
    if digest(path) != checksum:
        raise ValueError("remote_text_final_input_changed")
    value = parser(path)
    if digest(path) != checksum:
        raise ValueError("remote_text_final_input_changed")
    return value


def _stage_data(
    spec: QualificationInputs, binding: dict, manifest: dict, target: Path
) -> dict:
    profile = manifest["profile"]
    train = _load_bound(spec.train, profile["train_sha256"], rows)
    dev = _load_bound(spec.dev, profile["dev_sha256"], rows)
    holdout_sha = binding["final_test_sha256"]
    holdout = _load_bound(spec.final_test, holdout_sha, rows)
    if (
        any(row.get("split") != "train" for row in train)
        or any(row.get("split") != "dev" for row in dev)
        or any(row.get("split") != "pilot" for row in holdout)
    ):
        raise ValueError("remote_text_final_split_invalid")
    validate_splits(train, dev, holdout)
    # The isolated evaluator uses its dev-shaped input protocol. The original
    # sealed pilot split remains separate and bound in the final receipt.
    evaluator_rows = [{**row, "split": "dev"} for row in holdout]
    validate_dev_cases(evaluator_rows)
    with target.open("x", encoding="utf-8") as stream:
        for row in evaluator_rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    calibration = _load_bound(
        spec.calibration, binding["final_calibration_sha256"], read_json
    )
    if (
        not isinstance(calibration, dict)
        or calibration.get("schema_version") != 1
        or calibration.get("judge") != "exact-v1"
        or calibration.get("dev_sha256") != holdout_sha
        or not isinstance(calibration.get("reviewer"), str)
        or not calibration["reviewer"].strip()
        or not isinstance(calibration.get("cases"), dict)
        or calibration["cases"].keys() != {row["record_id"] for row in holdout}
    ):
        raise ValueError("remote_text_final_calibration_invalid")
    return calibration


def _execute(
    command: list[str], log: Path, timeout: int, gpu_fd: int, group: list[int]
) -> None:
    deadline = time.monotonic() + timeout
    child = subprocess.Popen(
        command,
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        pass_fds=(gpu_fd,),
    )
    group.append(child.pid)
    identity = process_identity(child.pid)
    try:
        if identity is None or child.stdout is None:
            raise RuntimeError("remote_text_final_child_not_confirmed")
        os.set_blocking(child.stdout.fileno(), False)
        while child.poll() is None:
            _drain(child, log)
            if time.monotonic() >= deadline:
                raise TimeoutError("remote_text_final_inference_timed_out")
            time.sleep(0.1)
        _drain(child, log)
        if child.returncode != 0:
            raise ValueError("remote_text_final_inference_failed")
        if group_alive(identity["process_group"]):
            raise RuntimeError("remote_text_final_child_group_active")
    finally:
        if identity is not None and group_alive(identity["process_group"]):
            _terminate(child, identity, log)
        if child.stdout is not None:
            child.stdout.close()


def _evaluate(
    command: list[str], log: Path, timeout: int, run_id: str, model: str
) -> None:
    host = get_runtime_admission()
    if not host.enabled or not host.claim_offline_host():
        raise ValueError("remote_text_final_dedicated_gpu_required")
    try:
        listener = create_connection(("127.0.0.1", Worker._local_api_port()), timeout=1)
    except ConnectionRefusedError:
        pass
    else:
        listener.close()
        raise ValueError("remote_text_final_dedicated_gpu_required")
    lock = host.database.parent / "academy-experiments.gpu.lock"
    admission = RuntimeAdmission.for_training_worker(host.database)
    with file_lock(lock, blocking=False) as gpu_fd:
        lease = admission.acquire(
            owner=ACADEMY_TRAINING_OWNER,
            run_id=run_id,
            engine=_TARGET_RUNTIME,
            model=model,
        )
        group: list[int] = []

        def quiescent() -> bool:
            return not group or not group_alive(group[0])

        try:
            # Any failure with unconfirmed process state quarantines the lease.
            with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
                _execute(command, log, timeout, gpu_fd, group)
        finally:
            if quiescent() and not lease.release():
                raise RuntimeError("remote_text_final_gpu_recovery_required")


def _adapter_identity(checkpoint: Path, binding: dict, manifest: dict) -> dict:
    pin = read_json(SNAPSHOT_PIN)
    if (
        manifest["profile"]["model"] != pin["repo"]
        or binding["development_identity"]["base_sha256"] != digest(SNAPSHOT_PIN)
        or digest(checkpoint / WEIGHTS) != binding["checkpoint_sha256"]
    ):
        raise ValueError("remote_text_final_adapter_identity_mismatch")
    adapter = {
        "schema_version": 1,
        "adapter_id": f"text-{binding['campaign_id']}-{binding['checkpoint_sha256'][:12]}",
        "label": f"Remote text {binding['campaign_id']} step {binding['step']}",
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_sha256": digest(SNAPSHOT_PIN),
        "config_sha256": digest(checkpoint / ADAPTER_FILES[0]),
        "weights_sha256": binding["checkpoint_sha256"],
    }
    handoff = {
        **adapter,
        "source": {"identity": binding["run_id"], "sha256": binding["result_sha256"]},
    }
    entry = AdapterEntry.model_validate(handoff).model_dump(mode="json")
    verify_initial_adapter(checkpoint, runner_identity(entry), manifest["recipe"])
    return entry


def _known_outputs(calibration: dict, review: dict) -> bool:
    return all(
        result.get("error") is None
        and result["text"].strip()
        in calibration["cases"][row["case"]["record_id"]]["outputs"]
        for row in review["answers"]
        for result in row["answers"].values()
    )


def _measure(
    generation: Path,
    data: Path,
    calibration: dict,
    adapter: dict,
    binding: dict,
    selection: dict,
) -> dict:
    seal_generation(generation)
    generated, _ = read_generation(generation)
    tag = f"checkpoint-{binding['step']}"
    if (
        generated["data_sha256"] != digest(data)
        or generated["snapshot_manifest_sha256"] != adapter["snapshot_sha256"]
        or generated["model_repo"] != adapter["model"]
        or generated["revision"] != adapter["revision"]
        or generated["generation_mode"] != "text"
        or generated["resumed_generations"] != 0
        or generated["models"]
        != {
            "base": {"base": True},
            tag: {
                ADAPTER_FILES[0]: adapter["config_sha256"],
                WEIGHTS: adapter["weights_sha256"],
            },
        }
    ):
        raise ValueError("remote_text_final_generation_identity_mismatch")
    review = review_data(generation, data)
    identity = evaluation_identity(generated, binding["final_calibration_sha256"])
    result = {
        "binding": binding,
        "runtime": _TARGET_RUNTIME,
        "runtime_reloaded": True,
        "holdout_identity": identity,
        "generation_seal_sha256": digest(generation / "generation-seal.json"),
    }
    if not _known_outputs(calibration, review):
        return {**result, "status": "incomplete_calibration", "qualified": None}
    judgments = calibrated_judgments(calibration, review)
    scores = sealed_report(
        generation,
        data,
        judgments,
        {"step": binding["step"], "sha256": binding["checkpoint_sha256"]},
    )
    usable, critical = _metrics(scores["summaries"])
    critical_regression = any(
        candidate["critical"] > scores["summaries"]["base"][name]["critical"]
        for name, candidate in scores["summaries"]["candidate"].items()
    )
    passed = (
        usable > 0
        and usable >= selection["min_usable_delta"]
        and critical <= selection["max_critical_delta"]
        and not critical_regression
    )
    atomic_json(generation / "judgments.json", judgments)
    return {
        **result,
        "status": "passed" if passed else "failed_quality",
        "judgments_sha256": digest(generation / "judgments.json"),
        "summaries": scores["summaries"],
        "usable_delta": usable,
        "critical_delta": critical,
        "qualified": {
            "run_id": binding["run_id"],
            "step": binding["step"],
            "sha256": binding["checkpoint_sha256"],
            "adapter_id": adapter["adapter_id"],
            "runtime": _TARGET_RUNTIME,
        }
        if passed
        else None,
    }


def _publish_adapter(
    academy_root: Path, checkpoint: Path, adapter: dict, recipe: dict
) -> None:
    catalog = operator_path(academy_root / "adapters")
    catalog.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = catalog / adapter["adapter_id"]
    with file_lock(catalog / ".remote-text.lock"):
        if not destination.exists():
            with tempfile.TemporaryDirectory(
                prefix=".remote-text-", dir=catalog
            ) as staging:
                entry = Path(staging) / "entry"
                entry.mkdir(mode=0o700)
                for name in ADAPTER_FILES:
                    destination_file = entry / name
                    shutil.copyfile(checkpoint / name, destination_file)
                    with destination_file.open("rb") as stream:
                        os.fsync(stream.fileno())
                atomic_json(entry / "adapter.json", adapter)
                atomic_json(
                    entry / "hashes.json",
                    {
                        ADAPTER_FILES[0]: adapter["config_sha256"],
                        WEIGHTS: adapter["weights_sha256"],
                    },
                )
                verify_initial_adapter(entry, runner_identity(adapter), recipe)
                entry.rename(destination)
                with data_directory(catalog) as directory:
                    os.fsync(directory)
        _, existing = resolve_adapter(academy_root, adapter["adapter_id"], recipe)
        if existing != adapter:
            raise ValueError("remote_text_final_catalog_conflict")


def _read_result(directory: Path, binding: dict) -> dict | None:
    if not (directory / "result-seal.json").exists():
        return None
    path = directory / "result.json"
    if digest(path) != read_json(directory / "result-seal.json")["sha256"]:
        raise ValueError("remote_text_final_result_changed")
    result = read_json(path)
    if result["binding"] != binding:
        raise ValueError("remote_text_final_result_identity_mismatch")
    return result


def _catalog_published(directory: Path) -> bool:
    receipt = operator_path(directory / "catalog.json")
    return receipt.is_file() and read_json(receipt)["result_sha256"] == digest(
        directory / "result.json"
    )


def read_qualification(
    evidence_root: Path,
    remote: dict,
    receipts: Mapping[str, dict],
    *,
    final_test_sha256: str,
    final_calibration_sha256: str,
) -> dict | None:
    """Read the sealed controller decision without rehashing remote weight archives."""
    directory = operator_path(evidence_root / _ENTRY)
    if not (directory / "result-seal.json").exists():
        return None
    binding = _binding(remote, receipts, final_test_sha256, final_calibration_sha256)
    result = _read_result(directory, binding)
    if (
        result is not None
        and result["qualified"] is not None
        and not _catalog_published(directory)
    ):
        return {**result, "status": "catalog_pending", "qualified": None}
    return result


def qualify(
    evidence_root: Path,
    remote: dict,
    receipts: Mapping[str, dict],
    academy_root: Path,
    spec: QualificationInputs,
    *,
    final_test_sha256: str,
    final_calibration_sha256: str,
    evaluator: Callable[[list[str], Path, int, str, str], None] = _evaluate,
) -> dict:
    ensure_data_mutation_allowed("academy_remote_text_qualification")
    binding = _binding(remote, receipts, final_test_sha256, final_calibration_sha256)
    directory = operator_path(evidence_root / _ENTRY)
    directory.mkdir(mode=0o700, exist_ok=True)
    return _qualify_locked(
        directory, evidence_root, remote, academy_root, spec, binding, evaluator
    )


def _qualify_locked(
    directory: Path,
    evidence_root: Path,
    remote: dict,
    academy_root: Path,
    spec: QualificationInputs,
    binding: dict,
    evaluator: Callable[[list[str], Path, int, str, str], None],
) -> dict:
    with file_lock(directory / ".lock"):
        intent = directory / "intent.json"
        if intent.exists() and read_json(intent) != binding:
            raise ValueError("remote_text_final_already_bound")
        result = _read_result(directory, binding)
        if result is not None and (
            result["qualified"] is None or _catalog_published(directory)
        ):
            return result
        with tempfile.TemporaryDirectory(prefix=".final-", dir=directory) as staging:
            workspace = Path(staging)
            checkpoint = workspace / f"checkpoint-{binding['step']}"
            manifest = stage_candidate(
                evidence_root,
                binding["run_id"],
                binding["step"],
                checkpoint,
                expected_archive_sha256=binding["archive_sha256"],
            )
            adapter = _adapter_identity(checkpoint, binding, manifest)
            if result is None:
                result = _run_final(
                    directory,
                    workspace,
                    checkpoint,
                    spec,
                    binding,
                    manifest,
                    adapter,
                    remote["plan"]["selection"],
                    evaluator,
                )
            if result["qualified"] is not None:
                _publish_adapter(academy_root, checkpoint, adapter, manifest["recipe"])
                atomic_json(
                    directory / "catalog.json",
                    {"result_sha256": digest(directory / "result.json")},
                )
            return result


def _run_final(
    directory: Path,
    workspace: Path,
    checkpoint: Path,
    spec: QualificationInputs,
    binding: dict,
    manifest: dict,
    adapter: dict,
    selection: dict,
    evaluator: Callable[[list[str], Path, int, str, str], None],
) -> dict:
    data = workspace / "holdout.jsonl"
    calibration = _stage_data(spec, binding, manifest, data)
    snapshot = operator_path(spec.snapshot)
    venv = operator_path(spec.training_venv)
    if not snapshot.is_dir() or not (venv / "bin/python").is_file():
        raise ValueError("remote_text_final_runtime_missing")
    atomic_json(directory / "intent.json", binding)
    generation = workspace / "generation"
    command = [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        "bash",
        str(REPO / "scripts/academy/omni_pl_chat_evaluate.sh"),
        str(snapshot),
        str(data),
        str(generation),
        str(venv),
        "base",
        f"{checkpoint.name}={checkpoint}",
    ]
    data_sha = digest(data)
    log = workspace / "evaluation.log"
    evaluator(command, log, spec.max_seconds, binding["run_id"], adapter["model"])
    if digest(data) != data_sha:
        raise ValueError("remote_text_final_input_changed")
    result = _measure(generation, data, calibration, adapter, binding, selection)
    # The case definitions, outputs and judgments stay on the independent host.
    run_dir = Path(tempfile.mkdtemp(prefix="verified-", dir=directory))
    data.rename(run_dir / "holdout.jsonl")
    if log.is_file():
        log.rename(run_dir / "evaluation.log")
    generation.rename(run_dir / "generation")
    result["evidence_name"] = run_dir.name
    atomic_json(directory / "result.json", result)
    atomic_json(
        directory / "result-seal.json", {"sha256": digest(directory / "result.json")}
    )
    return result


def _controller_state(academy_root: Path, campaign_id: str) -> tuple[Path, dict]:
    _CAMPAIGN_ID.validate_python(campaign_id)
    directory = operator_path(academy_root / "remote-text" / campaign_id)
    state = read_json(directory / "state.json")
    if state["campaign_id"] != campaign_id or state["status"] != "completed":
        raise ValueError("remote_text_final_campaign_not_finished")
    remote = state["remote"]
    plan = state["plan"]
    if (
        remote["campaign_id"] != campaign_id
        or remote["plan"]["plan_sha256"] != plan["remote_plan_sha256"]
        or remote["plan"]["profile_identity"] != plan["profile_identity"]
    ):
        raise ValueError("remote_text_final_controller_binding_invalid")
    return directory, state


def _pins(state: dict) -> dict[str, str]:
    request = state["plan"]["request"]
    return {
        name: _sha(request.get(name))
        for name in ("final_test_sha256", "final_calibration_sha256")
    }


def _dispatch(
    academy_root: Path,
    directory: Path,
    state: dict,
    inputs: Path,
    evaluator: Callable[[list[str], Path, int, str, str], None],
) -> dict:
    return qualify(
        directory / "evidence",
        state["remote"],
        state["evidence"],
        academy_root,
        QualificationInputs.model_validate(read_json(inputs)),
        evaluator=evaluator,
        **_pins(state),
    )


def qualify_pending(
    academy_root: Path,
    *,
    evaluator: Callable[[list[str], Path, int, str, str], None] = _evaluate,
) -> dict:
    """Attempt one prepared, completed campaign per independent evaluator tick."""
    ensure_data_mutation_allowed("academy_remote_text_qualification")
    academy_root = operator_path(academy_root)
    queue = operator_path(academy_root / _INPUTS)
    if not queue.is_dir():
        return {"status": "idle"}
    if queue.stat().st_mode & 0o077:
        raise ValueError("remote_text_final_queue_not_private")
    with file_lock(queue / ".pending.lock", blocking=False):
        for item in sorted(queue.glob("*.json")):
            campaign_id = item.stem
            try:
                directory, state = _controller_state(academy_root, campaign_id)
                current = read_qualification(
                    directory / "evidence",
                    state["remote"],
                    state["evidence"],
                    **_pins(state),
                )
            except (OSError, RuntimeError, TypeError, ValueError, KeyError):
                continue
            if current is not None and current["status"] != "catalog_pending":
                continue
            retry = operator_path(directory / "qualification-attempts.json")
            previous = read_json(retry) if retry.exists() else {"attempts": 0}
            if previous["attempts"] >= _MAX_PENDING_RETRIES:
                continue
            attempts = previous["attempts"] + 1
            atomic_json(retry, {"attempts": attempts})
            try:
                result = _dispatch(academy_root, directory, state, item, evaluator)
            except (OSError, RuntimeError, TypeError, ValueError, KeyError):
                return {
                    "status": "retry" if attempts < _MAX_PENDING_RETRIES else "failed",
                    "campaign_id": campaign_id,
                    "attempts": attempts,
                }
            return {"status": result["status"], "campaign_id": campaign_id}
    return {"status": "idle"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("academy_root", type=Path)
    parser.add_argument("campaign_id", nargs="?")
    parser.add_argument("inputs", nargs="?", type=Path)
    parser.add_argument("--pending", action="store_true")
    args = parser.parse_args()
    academy_root = operator_path(args.academy_root)
    if args.pending:
        if args.campaign_id is not None or args.inputs is not None:
            parser.error("--pending takes only the Academy root")
        result = qualify_pending(academy_root)
    else:
        if args.campaign_id is None or args.inputs is None:
            parser.error("provide campaign_id and inputs or use --pending")
        directory, state = _controller_state(academy_root, args.campaign_id)
        result = _dispatch(academy_root, directory, state, args.inputs, _evaluate)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
