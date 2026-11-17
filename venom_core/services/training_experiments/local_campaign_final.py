"""Private held-out inputs and durable local campaign final qualification."""

from __future__ import annotations

import math
import re
import tempfile
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.runtime_admission import RuntimeAdmissionError

from .calibration import scorer_protocol
from .campaign_schema import CampaignId
from .profiles import digest, load_profile, read_json, resolve_input
from .remote_text_local import collect_local, pin_state

if TYPE_CHECKING:
    from .campaign import CampaignService
    from .remote_text_qualification import QualificationInputs

_INPUTS = "local-text-final-inputs"
_IDS = TypeAdapter(CampaignId)
_FINISHED = frozenset({"passed", "failed_quality", "incomplete"})


def _input_path(root: Path, inputs_id: str) -> Path:
    _IDS.validate_python(inputs_id)
    return operator_path(root / _INPUTS / f"{inputs_id}.json")


def register_inputs(root: Path, inputs_id: str, values: dict) -> dict:
    """Register immutable paths privately; the campaign plan freezes their contents."""
    from .remote_text_qualification import QualificationInputs

    ensure_data_mutation_allowed("academy_local_text_qualification_register")
    spec = QualificationInputs.model_validate(values)
    payload = spec.model_dump(mode="json")
    for key in (
        "train",
        "dev",
        "final_test",
        "calibration",
        "snapshot",
        "training_venv",
    ):
        payload[key] = str(operator_path(Path(payload[key]).absolute()))
    path = _input_path(root, inputs_id)
    # Reject broken input packages before publishing a catalog entry.
    prepared = QualificationInputs.model_validate(payload)
    summary = _summarize_inputs(inputs_id, prepared)
    from .remote_text_qualification import _stage_data

    with tempfile.TemporaryDirectory(prefix="academy-final-register-") as temporary:
        _stage_data(
            prepared,
            summary,
            {
                "profile": {
                    "train_sha256": digest(prepared.train),
                    "dev_sha256": digest(prepared.dev),
                }
            },
            Path(temporary) / "holdout.jsonl",
        )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("campaign_final_inputs_not_private")
    with file_lock(path.parent / ".catalog.lock"):
        if path.exists() and read_json(path) != payload:
            raise ValueError("campaign_final_inputs_conflict")
        atomic_json(path, payload)
    return summary


def _input_summary(path: Path) -> dict:
    from .remote_text_qualification import QualificationInputs

    spec = QualificationInputs.model_validate(read_json(path))
    return _summarize_inputs(path.stem, spec)


def _summarize_inputs(inputs_id: str, spec: QualificationInputs) -> dict:
    return {
        "inputs_id": inputs_id,
        "final_test_sha256": digest(spec.final_test),
        "final_calibration_sha256": digest(spec.calibration),
        "max_seconds": spec.max_seconds,
    }


def list_inputs(root: Path) -> list[dict]:
    """Expose identifiers and hashes, never controller-only paths or test contents."""
    directory = operator_path(root / _INPUTS)
    if not directory.exists():
        return []
    if directory.stat().st_mode & 0o077:
        raise ValueError("campaign_final_inputs_not_private")
    return [_input_summary(path) for path in sorted(directory.glob("*.json"))]


def freeze_inputs(root: Path, plan: dict, request: dict) -> dict:
    from .remote_text_qualification import (
        QualificationInputs,
        _planned_parent,
        _stage_data,
        _verify_parent,
    )

    path = _input_path(root, request["inputs_id"])
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("campaign_final_inputs_not_private")
    checksum = digest(path)
    spec = QualificationInputs.model_validate(read_json(path))
    profile, _ = load_profile(root, plan["profile_id"])
    if (
        request["reserve_seconds"] < spec.max_seconds
        or operator_path(spec.snapshot) != resolve_input(root, profile.snapshot)
        or operator_path(spec.training_venv)
        != resolve_input(root, profile.training_venv)
    ):
        raise ValueError("campaign_final_runtime_mismatch")
    parent = _planned_parent(plan, plan["variants"][0]["run_id"])
    if parent is None:
        raise ValueError("campaign_final_parent_required")
    _verify_parent({"parent": parent}, root)
    pins = {
        "final_test_sha256": digest(spec.final_test),
        "final_calibration_sha256": digest(spec.calibration),
    }
    # Reuse the final evaluator's separation and calibration validation before training.
    with tempfile.TemporaryDirectory(prefix="academy-final-check-") as temporary:
        calibration = _stage_data(
            spec,
            pins,
            {"profile": profile.model_dump()},
            Path(temporary) / "holdout.jsonl",
        )
    if digest(path) != checksum:
        raise ValueError("campaign_final_inputs_changed")
    return {
        "inputs_id": request["inputs_id"],
        "reserve_seconds": request["reserve_seconds"],
        "inputs_sha256": checksum,
        **pins,
        "parent_weights_sha256": parent["entry"]["weights_sha256"],
        "scorer_protocol": scorer_protocol(calibration),
    }


def verify_inputs(root: Path, plan: dict) -> None:
    expected = plan["final_qualification"]
    if freeze_inputs(root, plan, expected) != expected:
        raise ValueError("campaign_final_inputs_changed")


def pin_inputs(root: Path, state: dict) -> None:
    """Called while the campaign state lock is held, before persisting started_at."""
    verify_inputs(root, state["plan"])
    spec = state["plan"]["final_qualification"]
    pin_state(
        root,
        state,
        final_test_sha256=spec["final_test_sha256"],
        final_calibration_sha256=spec["final_calibration_sha256"],
    )


def finish(state: dict, result: dict) -> None:
    status = result["status"]
    state["qualification"] = result
    state["qualification_status"] = status if status in _FINISHED else "incomplete"
    state["phase"] = "complete"
    state["status"] = state.get("training_status", state["status"])
    state["worker"] = None


def incomplete(state: dict, reason: str) -> None:
    finish(state, {"status": "incomplete", "qualified": None, "reason": reason})


def transition(state: dict) -> None:
    """Reserve the exact selected finalist after trials become quiescent."""
    if not state["plan"].get("final_qualification") or state.get("phase") != "trials":
        return
    if state["status"] not in {"succeeded", "timed_out", "stopped", "blocked"}:
        return
    state["training_status"] = state["status"]
    confirmation = state.get("repeat_confirmation", {})
    if confirmation.get("status") in {"failed_quality", "incomplete"}:
        finish(
            state,
            {
                "status": confirmation["status"],
                "qualified": None,
                "reason": confirmation["reason"],
            },
        )
    elif state["status"] in {"stopped", "blocked"}:
        incomplete(state, state.get("error") or f"campaign_{state['status']}")
    elif state["selected_run_id"] is None:
        assessed = (
            any(trial.get("result_sha256") for trial in state["trials"])
            and all(
                trial["status"] in {"succeeded", "skipped"} for trial in state["trials"]
            )
            and not state.get("quality_policy_error")
        )
        if assessed:
            finish(
                state,
                {
                    "status": "failed_quality",
                    "qualified": None,
                    "reason": "campaign_no_eligible_finalist",
                },
            )
        else:
            incomplete(state, "campaign_final_candidate_missing")
    else:
        state.update(
            phase="qualification", status="qualifying", qualification_status="pending"
        )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, RuntimeAdmissionError):
        return "campaign_final_runtime_admission_failed"
    code = str(exc)
    return (
        code
        if re.fullmatch(r"(?:campaign_|remote_text_|experiment_)[a-z0-9_]+", code)
        else "campaign_final_failed"
    )


def _check(service: CampaignService, campaign_id: str) -> float:
    state = service._state(service.directory(campaign_id))
    if state.get("termination") in {"stopped", "blocked"}:
        raise ValueError(state.get("error") or "campaign_final_stopped")
    remaining = state["deadline_at"] - service._clock()
    if remaining <= 0:
        raise TimeoutError("campaign_final_deadline_exhausted")
    if not service._artifact_budget(state):
        raise ValueError("campaign_storage_budget_exhausted")
    return remaining


def read_result(root: Path, state: dict) -> dict | None:
    from .remote_text_evidence import read_run
    from .remote_text_qualification import read_qualification

    run_id = state.get("selected_run_id")
    if not run_id:
        return None
    evidence = operator_path(
        root / "local-text-qualification" / state["campaign_id"] / "evidence"
    )
    if not (evidence / "final-qualification" / "result-seal.json").exists():
        return None
    completed = {**state, "status": state["training_status"]}
    config = state["plan"]["final_qualification"]
    return read_qualification(
        evidence,
        completed,
        {run_id: read_run(evidence, run_id)},
        academy_root=root,
        source="local",
        **{
            key: config[key]
            for key in ("final_test_sha256", "final_calibration_sha256")
        },
    )


def observe(root: Path, state: dict) -> None:
    """Fail closed if a displayed published decision or its evidence changed."""
    if state.get("phase") != "complete" or not state.get("qualification", {}).get(
        "binding"
    ):
        return
    try:
        result = read_result(root, state)
        if result is None or result["status"] == "catalog_pending":
            incomplete(state, "campaign_final_evidence_missing")
        else:
            finish(state, result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        incomplete(state, _error_code(exc))


def _execute(service: CampaignService, state: dict) -> dict:
    from .remote_text_qualification import QualificationInputs, _evaluate, qualify

    root = service.experiments.root
    campaign_id = state["campaign_id"]
    cached = read_result(root, state)
    if cached is not None and cached["status"] != "catalog_pending":
        return cached
    check = partial(_check, service, campaign_id)
    check()
    verify_inputs(root, state["plan"])
    config = state["plan"]["final_qualification"]
    evidence, completed, receipts, pins = collect_local(
        root, campaign_id, timeout=math.floor(check())
    )
    spec = QualificationInputs.model_validate(
        read_json(_input_path(root, config["inputs_id"]))
    )
    return qualify(
        evidence,
        completed,
        receipts,
        root,
        spec,
        source="local",
        evaluator=partial(_evaluate, shared_runtime=True, check=check),
        check=check,
        **pins,
    )


def _recover_result(service: CampaignService, state: dict) -> None:
    # A crash consumes its attempt; recover a sealed result without inference.
    try:
        cached = read_result(service.experiments.root, state)
        if cached is not None and cached["status"] != "catalog_pending":
            finish(state, cached)
        else:
            incomplete(state, "campaign_final_retries_exhausted")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        incomplete(state, _error_code(exc))


def _begin(service: CampaignService, directory: Path) -> tuple[dict, bool]:
    with file_lock(directory / ".state.lock"):
        state = service._state(directory)
        if state.get("phase") != "qualification":
            return state, False
        if (
            state.get("qualification_attempts", 0)
            > state["plan"]["budget"]["max_retries"]
        ):
            _recover_result(service, state)
            service._save(directory, state)
            return state, False
        state["qualification_status"] = "running"
        state["qualification_attempts"] = state.get("qualification_attempts", 0) + 1
        service._save(directory, state)
        return state, True


def _record_deferred(service: CampaignService, directory: Path) -> dict:
    with file_lock(directory / ".state.lock"):
        state = service._state(directory)
        state["qualification_attempts"] -= 1
        state["qualification_status"] = "pending"
        service._elapsed(state)
        service._save(directory, state)
        return state


def _record_failure(service: CampaignService, directory: Path, exc: Exception) -> dict:
    with file_lock(directory / ".state.lock"):
        state = service._state(directory)
        state["qualification_error"] = _error_code(exc)
        expired = state["deadline_at"] <= service._clock()
        stopped = state.get("termination") in {"stopped", "blocked"}
        retries = state["plan"]["budget"]["max_retries"]
        service._elapsed(state)
        if expired or stopped or state["qualification_attempts"] > retries:
            incomplete(state, state["qualification_error"])
        else:
            state["qualification_status"] = "pending"
        service._save(directory, state)
        return state


def _record_result(service: CampaignService, directory: Path, result: dict) -> dict:
    with file_lock(directory / ".state.lock"):
        state = service._state(directory)
        service._elapsed(state)
        service._artifact_budget(state)
        finish(state, result)
        state.pop("qualification_error", None)
        service._save(directory, state)
        return state


def advance(service: CampaignService, campaign_id: str) -> dict:
    """One detached worker owns final execution; status/stop stay responsive."""
    from .remote_text_qualification import _QualificationDeferred

    directory = service.directory(campaign_id)
    try:
        with file_lock(directory / ".qualification-worker.lock", blocking=False):
            state, execute = _begin(service, directory)
            if not execute:
                return state
            try:
                result = _execute(service, state)
            except _QualificationDeferred:
                return _record_deferred(service, directory)
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                KeyError,
                RuntimeAdmissionError,
            ) as exc:
                return _record_failure(service, directory, exc)
            return _record_result(service, directory, result)
    except BlockingIOError:
        return service.status(campaign_id)


def resume_pending(root: Path) -> dict:
    """Recover one interrupted automatic local session without resetting its budget."""
    from .campaign import CampaignService
    from .service import ExperimentService

    ensure_data_mutation_allowed("academy_campaign_activate")
    service = CampaignService(ExperimentService(root))
    for state in service.list():
        if state.get("phase") not in {"trials", "qualification"}:
            continue
        if state["status"] == "interrupted":
            try:
                resumed = service.resume(state["campaign_id"])
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                # Changed inputs must not leave a session in an endless recovery
                # loop. The normal worker first quiesces any owned trial.
                directory = service.directory(state["campaign_id"])
                with file_lock(directory / ".state.lock"):
                    failed = service._state(directory)
                    failed.update(
                        status="stopping", termination="blocked", error=_error_code(exc)
                    )
                    service._save(directory, failed)
                resumed = service.resume(state["campaign_id"])
            return {"status": resumed["status"], "campaign_id": state["campaign_id"]}
    return {"status": "idle"}
