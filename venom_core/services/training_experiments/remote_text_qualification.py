"""Evaluate the frozen remote finalist once on a controller-held text holdout."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from functools import partial
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
    RuntimeAdmissionError,
    RuntimeLease,
    get_runtime_admission,
)

from . import local_semantic_judge
from .adapters import (
    AdapterEntry,
    resolve_adapter,
    runner_identity,
    verify_adapter_entry,
)
from .calibration import validate_calibration
from .campaign_schema import CampaignId
from .checkpoint_evaluation import read_generation, seal_generation
from .evidence import (
    ADAPTER_FILES,
    WEIGHTS,
    calibrated_judgments,
    review_data,
    sealed_report,
)
from .grounded_claims import UNCERTAIN
from .profiles import digest, read_json, rows, stable_hash
from .quality_native import evaluation_identity
from .remote_text_evidence import (
    _metrics,
    _receipt_matches,
    _sha,
    read_run,
    reverify_run,
    stage_candidate,
)
from .remote_text_local import collect_local, pin_local
from .service import REPO
from .worker import Worker

_TARGET_RUNTIME = "omni-native-peft-text"
_ENTRY = "final-qualification"
_INPUTS = "remote-text-final-inputs"
_GPU_RELEASE_RECEIPT = "gpu-release.json"
_HOLDOUT = "holdout.jsonl"
_JUDGMENTS = "judgments.json"
_MAX_PENDING_RETRIES = 3
_Bound = TypeVar("_Bound", list, dict)
_CAMPAIGN_ID = TypeAdapter(CampaignId)


class _QualificationDeferred(RuntimeError):
    """The evaluator could not reserve the dedicated GPU."""


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
    remote: dict,
    receipts: Mapping[str, dict],
    test_sha: str,
    calibration_sha: str,
    *,
    source: str = "remote",
) -> dict:
    if remote.get("status") not in {"succeeded", "timed_out", "stopped"}:
        raise ValueError("remote_text_final_campaign_not_finished")
    run_id = remote.get("selected_run_id")
    if not isinstance(run_id, str):
        raise ValueError("remote_text_final_candidate_missing")
    receipt = receipts.get(run_id)
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
    parent = _planned_parent(remote["plan"], run_id)
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
        **({"parent": parent} if parent is not None else {}),
        **({"source": source} if source == "local" else {}),
    }


def _planned_parent(plan: dict, run_id: str) -> dict | None:
    variants = plan.get("variants", [])
    parents = [row.get("initial_adapter") for row in variants]
    if not parents or all(parent is None for parent in parents):
        return None
    selected = [row for row in variants if row.get("run_id") == run_id]
    if (
        plan.get("strategy", "fixed") != "fixed"
        or parents[0] is None
        or any(parent != parents[0] for parent in parents)
        or len(selected) != 1
        or not isinstance(selected[0].get("recipe"), dict)
    ):
        raise ValueError("remote_text_final_parent_plan_invalid")
    entry = AdapterEntry.model_validate(parents[0]).model_dump(mode="json")
    return {"entry": entry, "recipe": selected[0]["recipe"]}


def _parent_tag(step: int) -> str:
    return "checkpoint-99998" if step == 99999 else "checkpoint-99999"


def _verify_parent(binding: dict, academy_root: Path | None) -> Path | None:
    parent = binding.get("parent")
    if parent is None:
        return None
    if academy_root is None:
        raise ValueError("remote_text_final_parent_catalog_required")
    return verify_adapter_entry(academy_root, parent["entry"], parent["recipe"])


def _stage_parent(
    binding: dict, manifest: dict, academy_root: Path, workspace: Path
) -> Path | None:
    parent = binding.get("parent")
    expected = parent["entry"] if parent is not None else None
    if manifest.get("initial_adapter") != expected or (
        parent is not None and manifest["recipe"] != parent["recipe"]
    ):
        raise ValueError("remote_text_final_parent_manifest_mismatch")
    source = _verify_parent(binding, academy_root)
    if source is None:
        return None
    target = workspace / _parent_tag(binding["step"])
    target.mkdir(mode=0o700)
    for name in (*ADAPTER_FILES, "hashes.json"):
        shutil.copyfile(operator_path(source / name), target / name)
    assert parent is not None
    verify_initial_adapter(target, runner_identity(parent["entry"]), parent["recipe"])
    return target


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
    validate_calibration(calibration, holdout_sha, holdout)
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


def _require_dedicated_runtime(offline: bool) -> None:
    if not offline:
        raise _QualificationDeferred("remote_text_final_dedicated_gpu_required")
    try:
        listener = create_connection(("127.0.0.1", Worker._local_api_port()), timeout=1)
    except ConnectionRefusedError:
        return
    listener.close()
    raise _QualificationDeferred("remote_text_final_dedicated_gpu_required")


def _evaluate(
    command: list[str],
    log: Path,
    timeout: int,
    run_id: str,
    model: str,
    *,
    shared_runtime: bool = False,
) -> None:
    host = get_runtime_admission()
    if not host.enabled:
        raise ValueError("remote_text_final_dedicated_gpu_required")
    offline = host.claim_offline_host()
    if not shared_runtime:
        _require_dedicated_runtime(offline)
    lock = host.database.parent / "academy-experiments.gpu.lock"
    admission = RuntimeAdmission.for_training_worker(host.database)
    with ExitStack() as resources:
        try:
            gpu_fd = resources.enter_context(file_lock(lock, blocking=False))
            lease = admission.acquire(
                owner=ACADEMY_TRAINING_OWNER,
                run_id=run_id,
                engine="omni-training" if shared_runtime else _TARGET_RUNTIME,
                model=model,
            )
        except BlockingIOError as exc:
            raise _QualificationDeferred("remote_text_final_gpu_busy") from exc
        except RuntimeAdmissionError as exc:
            if exc.code == "runtime_busy":
                raise _QualificationDeferred("remote_text_final_gpu_busy") from exc
            raise
        _evaluate_with_lease(
            command,
            log,
            timeout,
            gpu_fd,
            lease,
            shared_runtime=shared_runtime,
            offline=offline,
        )


def _evaluate_with_lease(
    command: list[str],
    log: Path,
    timeout: int,
    gpu_fd: int,
    lease: RuntimeLease,
    *,
    shared_runtime: bool,
    offline: bool,
) -> None:
    group: list[int] = []

    def quiescent() -> bool:
        return not group or not group_alive(group[0])

    try:
        if shared_runtime:
            if timeout <= 0:
                raise TimeoutError("remote_text_final_inference_timed_out")
            started = time.monotonic()
            receipt = Worker.release_gpu(lease, offline=offline, timeout=timeout)
            atomic_json(log.with_name(_GPU_RELEASE_RECEIPT), receipt)
            timeout -= math.ceil(time.monotonic() - started)
            if timeout <= 0:
                raise TimeoutError("remote_text_final_inference_timed_out")
        # Any failure with unconfirmed process state quarantines the lease.
        with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
            _execute(command, log, timeout, gpu_fd, group)
    finally:
        if quiescent() and not lease.release():
            if shared_runtime and not group:
                lease.defer_training_release()
            else:
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


def _new_m0_critical_cases(scores: dict) -> list[str]:
    critical = scores["critical_case_ids"]
    return sorted(set(critical["candidate"]) - set(critical["base"]))


def _parent_comparison(scores: dict) -> dict:
    summaries, verdicts = scores["summaries"], scores["verdicts"]
    m0_usable, m0_critical = _metrics(summaries)
    parent_usable, parent_critical = _metrics(
        {"base": summaries["parent"], "candidate": summaries["candidate"]}
    )
    critical = scores["critical_case_ids"]
    return {
        "parent_usable_delta": parent_usable,
        "parent_critical_delta": parent_critical,
        "m0_usable_delta": m0_usable,
        "m0_critical_delta": m0_critical,
        "lost_parent_usable_case_ids": sorted(
            case_id
            for case_id, verdict in verdicts["parent"].items()
            if verdict["usable"] and not verdicts["candidate"][case_id]["usable"]
        ),
        "new_parent_critical_case_ids": sorted(
            set(critical["candidate"]) - set(critical["parent"])
        ),
        "new_m0_critical_case_ids": _new_m0_critical_cases(scores),
    }


def _model_hashes(adapter: dict) -> dict[str, str]:
    return {
        ADAPTER_FILES[0]: adapter["config_sha256"],
        WEIGHTS: adapter["weights_sha256"],
    }


def _verified_generation(
    generation: Path,
    data: Path,
    adapter: dict,
    binding: dict,
    parent_tag: str | None,
) -> dict:
    seal_generation(generation)
    generated, _ = read_generation(generation)
    tag = f"checkpoint-{binding['step']}"
    models: dict[str, dict] = {"base": {"base": True}, tag: _model_hashes(adapter)}
    if parent_tag is not None:
        models[parent_tag] = _model_hashes(binding["parent"]["entry"])
    if (
        generated["data_sha256"] != digest(data)
        or generated["snapshot_manifest_sha256"] != adapter["snapshot_sha256"]
        or generated["model_repo"] != adapter["model"]
        or generated["revision"] != adapter["revision"]
        or generated["generation_mode"] != "text"
        or generated["resumed_generations"] != 0
        or generated["models"] != models
    ):
        raise ValueError("remote_text_final_generation_identity_mismatch")
    return generated


def _selection_metrics(
    scores: dict, result: dict, *, has_parent: bool
) -> tuple[float, float, bool]:
    if not has_parent:
        usable, critical = _metrics(scores["summaries"])
        new_cases = _new_m0_critical_cases(scores)
        result["new_m0_critical_case_ids"] = new_cases
        regression = bool(new_cases) or any(
            candidate["critical"] > scores["summaries"]["base"][name]["critical"]
            for name, candidate in scores["summaries"]["candidate"].items()
        )
        return usable, critical, regression
    comparison = _parent_comparison(scores)
    result["parent_comparison"] = comparison
    regression = any(
        comparison[key]
        for key in (
            "lost_parent_usable_case_ids",
            "new_parent_critical_case_ids",
            "new_m0_critical_case_ids",
        )
    )
    return (
        comparison["parent_usable_delta"],
        comparison["parent_critical_delta"],
        regression,
    )


def _measure(
    generation: Path,
    data: Path,
    calibration: dict,
    adapter: dict,
    binding: dict,
    selection: dict,
    *,
    seconds: float = 0.0,
) -> dict:
    has_parent = binding.get("parent") is not None
    parent_tag = _parent_tag(binding["step"]) if has_parent else None
    generated = _verified_generation(generation, data, adapter, binding, parent_tag)
    review = review_data(generation, data)
    identity = evaluation_identity(
        generated,
        binding["final_calibration_sha256"],
        calibration=calibration,
    )
    result = {
        "binding": binding,
        "runtime": _TARGET_RUNTIME,
        "runtime_reloaded": True,
        "holdout_identity": identity,
        "generation_seal_sha256": digest(generation / "generation-seal.json"),
    }
    if has_parent:
        result["adapter_config_sha256"] = adapter["config_sha256"]
    legacy = calibration["judge"] == "exact-v1"
    if legacy and not _known_outputs(calibration, review):
        return {**result, "status": "incomplete_calibration", "qualified": None}
    if calibration["judge"] == local_semantic_judge.JUDGE:
        judgments = local_semantic_judge.review_bundle(
            calibration,
            review,
            binding["run_id"],
            seconds,
        )
    else:
        judgments = calibrated_judgments(calibration, review)
    scores = sealed_report(
        generation,
        data,
        judgments,
        {"step": binding["step"], "sha256": binding["checkpoint_sha256"]},
        parent_tag=parent_tag,
        include_critical_case_ids=True,
    )
    usable, critical, critical_regression = _selection_metrics(
        scores, result, has_parent=has_parent
    )
    passed = (
        usable > 0
        and usable >= selection["min_usable_delta"]
        and critical <= selection["max_critical_delta"]
        and not critical_regression
    )
    status = "passed" if passed else "failed_quality"
    if not legacy:
        result["calibration_protocol"] = {
            name: calibration[name]
            for name in ("judge", "schema_version", "judge_qualification")
            if name in calibration
        }
        uncertain = sum(grade["reason"] == UNCERTAIN for grade in judgments)
        result["unverifiable_answers"] = uncertain
        if uncertain:
            status, passed = "incomplete_calibration", False
            result["qualification_reason"] = UNCERTAIN
    atomic_json(generation / _JUDGMENTS, judgments)
    return {
        **result,
        "status": status,
        "judgments_sha256": digest(generation / _JUDGMENTS),
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
                    _model_hashes(adapter),
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
    no_parent_pass = "parent" not in binding and result["qualified"] is not None
    semantic = (
        result.get("calibration_protocol", {}).get("judge")
        == local_semantic_judge.JUDGE
    )
    if "parent" in binding or semantic or no_parent_pass:
        evidence = _verify_final_evidence(directory, result)
        if no_parent_pass:
            _verify_m0_pass(evidence, result)
    return result


def _verify_final_evidence(directory: Path, result: dict) -> Path:
    name = result["evidence_name"]
    if not re.fullmatch(r"verified-\w{8}", name, re.ASCII):
        raise ValueError("remote_text_final_evidence_invalid")
    evidence = operator_path(directory / name)
    generation = evidence / "generation"
    manifest, _ = read_generation(generation)
    judgments = result.get("judgments_sha256")
    if (
        digest(generation / "generation-seal.json") != result["generation_seal_sha256"]
        or digest(evidence / _HOLDOUT) != result["holdout_identity"]["dataset_sha256"]
        or evaluation_identity(
            manifest,
            result["binding"]["final_calibration_sha256"],
            calibration=result.get("calibration_protocol"),
        )
        != result["holdout_identity"]
        or (judgments is not None and digest(generation / _JUDGMENTS) != judgments)
    ):
        raise ValueError("remote_text_final_evidence_changed")
    return evidence


def _verify_m0_pass(evidence: Path, result: dict) -> None:
    generation = evidence / "generation"
    if result.get("judgments_sha256") is None:
        raise ValueError("remote_text_final_critical_evidence_missing")
    binding = result["binding"]
    scores = sealed_report(
        generation,
        evidence / _HOLDOUT,
        read_json(generation / _JUDGMENTS),
        {"step": binding["step"], "sha256": binding["checkpoint_sha256"]},
        include_critical_case_ids=True,
    )
    if _new_m0_critical_cases(scores):
        raise ValueError("remote_text_final_m0_critical_regression")


def _catalog_published(
    directory: Path, result: dict, academy_root: Path | None
) -> bool:
    receipt = operator_path(directory / "catalog.json")
    if not receipt.is_file() or read_json(receipt)["result_sha256"] != digest(
        directory / "result.json"
    ):
        return False
    binding = result["binding"]
    if "parent" in binding:
        if academy_root is None:
            raise ValueError("remote_text_final_parent_catalog_required")
        qualified = result["qualified"]
        _, adapter = resolve_adapter(
            academy_root, qualified["adapter_id"], binding["parent"]["recipe"]
        )
        if (
            adapter["config_sha256"] != result["adapter_config_sha256"]
            or adapter["weights_sha256"] != binding["checkpoint_sha256"]
            or adapter["source"]
            != {"identity": binding["run_id"], "sha256": binding["result_sha256"]}
        ):
            raise ValueError("remote_text_final_catalog_conflict")
    return True


def read_qualification(
    evidence_root: Path,
    remote: dict,
    receipts: Mapping[str, dict],
    *,
    final_test_sha256: str,
    final_calibration_sha256: str,
    academy_root: Path | None = None,
    source: str = "remote",
) -> dict | None:
    """Read the sealed controller decision without rehashing remote weight archives."""
    directory = operator_path(evidence_root / _ENTRY)
    if not (directory / "result-seal.json").exists():
        return None
    binding = _binding(
        remote, receipts, final_test_sha256, final_calibration_sha256, source=source
    )
    _verify_parent(binding, academy_root)
    result = _read_result(directory, binding)
    if (
        result is not None
        and result["qualified"] is not None
        and not _catalog_published(directory, result, academy_root)
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
    source: str = "remote",
    evaluator: Callable[[list[str], Path, int, str, str], None] = _evaluate,
) -> dict:
    ensure_data_mutation_allowed("academy_remote_text_qualification")
    binding = _binding(
        remote, receipts, final_test_sha256, final_calibration_sha256, source=source
    )
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
        _verify_parent(binding, academy_root)
        result = _read_result(directory, binding)
        if (
            result is not None
            and "parent" in binding
            and read_run(evidence_root, binding["run_id"])["archive_sha256"]
            != binding["archive_sha256"]
        ):
            raise ValueError("remote_text_final_archive_changed")
        if result is not None and (
            result["qualified"] is None
            or _catalog_published(directory, result, academy_root)
        ):
            return result
        receipt = reverify_run(
            evidence_root,
            remote,
            binding["run_id"],
            remote["plan"]["budget"]["max_artifact_bytes"],
        )
        if receipt["archive_sha256"] != binding["archive_sha256"]:
            raise ValueError("remote_text_final_archive_changed")
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
            parent = _stage_parent(binding, manifest, academy_root, workspace)
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
                    parent=parent,
                )
            if result["qualified"] is not None:
                _verify_parent(binding, academy_root)
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
    *,
    parent: Path | None = None,
) -> dict:
    data = workspace / _HOLDOUT
    calibration = _stage_data(spec, binding, manifest, data)
    snapshot = operator_path(spec.snapshot)
    venv = operator_path(spec.training_venv)
    if not snapshot.is_dir() or not (venv / "bin/python").is_file():
        raise ValueError("remote_text_final_runtime_missing")
    if calibration["judge"] == local_semantic_judge.JUDGE:
        local_semantic_judge.preflight(calibration)
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
    if parent is not None:
        command.append(f"{parent.name}={parent}")
    data_sha = digest(data)
    log = workspace / "evaluation.log"
    started = time.monotonic()
    evaluator(command, log, spec.max_seconds, binding["run_id"], adapter["model"])
    if digest(data) != data_sha:
        raise ValueError("remote_text_final_input_changed")
    result = _measure(
        generation,
        data,
        calibration,
        adapter,
        binding,
        selection,
        seconds=spec.max_seconds - (time.monotonic() - started),
    )
    # The case definitions, outputs and judgments stay on the independent host.
    run_dir = Path(tempfile.mkdtemp(prefix="verified-", dir=directory))
    data.rename(run_dir / _HOLDOUT)
    if log.is_file():
        log.rename(run_dir / "evaluation.log")
    gpu_receipt = workspace / _GPU_RELEASE_RECEIPT
    if gpu_receipt.is_file():
        gpu_receipt.rename(run_dir / _GPU_RELEASE_RECEIPT)
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
                    academy_root=academy_root,
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
            except _QualificationDeferred:
                atomic_json(retry, previous)
                return {"status": "busy", "campaign_id": campaign_id}
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                KeyError,
                RuntimeAdmissionError,
            ):
                return {
                    "status": "retry" if attempts < _MAX_PENDING_RETRIES else "failed",
                    "campaign_id": campaign_id,
                    "attempts": attempts,
                }
            return {"status": result["status"], "campaign_id": campaign_id}
    return {"status": "idle"}


def _pin_from_args(
    parser: argparse.ArgumentParser, args: argparse.Namespace, academy_root: Path
) -> dict:
    if not (
        args.local
        and args.campaign_id
        and args.inputs is None
        and args.final_test_sha256
        and args.final_calibration_sha256
        and not args.pending
    ):
        parser.error("--pin-only takes --local, campaign_id and both digests")
    return pin_local(
        academy_root,
        args.campaign_id,
        final_test_sha256=args.final_test_sha256,
        final_calibration_sha256=args.final_calibration_sha256,
    )


def _qualify_from_args(
    parser: argparse.ArgumentParser, args: argparse.Namespace, academy_root: Path
) -> dict:
    if args.campaign_id is None or args.inputs is None:
        parser.error("provide campaign_id and inputs or use --pending")
    if not args.local:
        directory, state = _controller_state(academy_root, args.campaign_id)
        return _dispatch(academy_root, directory, state, args.inputs, _evaluate)
    evidence, state, receipts, pins = collect_local(academy_root, args.campaign_id)
    return qualify(
        evidence,
        state,
        receipts,
        academy_root,
        QualificationInputs.model_validate(read_json(args.inputs)),
        source="local",
        evaluator=partial(_evaluate, shared_runtime=True),
        **pins,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("academy_root", type=Path)
    parser.add_argument("campaign_id", nargs="?")
    parser.add_argument("inputs", nargs="?", type=Path)
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--pin-only", action="store_true")
    parser.add_argument("--final-test-sha256")
    parser.add_argument("--final-calibration-sha256")
    args = parser.parse_args()
    academy_root = operator_path(args.academy_root)
    if args.pin_only:
        result = _pin_from_args(parser, args, academy_root)
    elif (
        args.final_test_sha256 is not None or args.final_calibration_sha256 is not None
    ):
        parser.error("digests can only be supplied with --local --pin-only")
    elif args.pending:
        if args.campaign_id is not None or args.inputs is not None or args.local:
            parser.error("--pending takes only the Academy root")
        result = qualify_pending(academy_root)
    else:
        result = _qualify_from_args(parser, args, academy_root)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
