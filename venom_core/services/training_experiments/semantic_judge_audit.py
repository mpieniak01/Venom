"""Run one frozen local v4 audit with a gate before held-out inference."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

import httpx

from venom_core.services.remote_training.lifecycle import atomic_json, validate_run_id

from . import local_semantic_judge as judge
from . import semantic_judge_v4 as verifier
from .profiles import digest, read_json, stable_hash

CLEANUP_SECONDS = 120
MAX_SECONDS = 1500
_INTENT = "intent.json"
_STARTED = "started.json"
_PHASE1_PASS = "phase1-pass.json"
_RESULT = "judge-result.json"


def _stage_controls(controls: Path, output: Path, intent: dict) -> None:
    if output.exists():
        if not (output / _INTENT).is_file():
            raise ValueError("experiment_judge_v4_output_incomplete")
        if read_json(output / _INTENT) != intent:
            raise ValueError("experiment_judge_v4_output_reused")
        if (output / _STARTED).exists():
            raise ValueError("experiment_judge_v4_attempt_already_started")
        return
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Build privately, then publish the complete preparation in one rename.
    # An interrupted preparation leaves no partial target for a retry to reuse.
    with tempfile.TemporaryDirectory(
        prefix=".judge-preparation-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "prepared"
        staging.mkdir(mode=0o700)
        _copy_controls(controls, staging, intent)
        staging.rename(output)


def _copy_controls(controls: Path, output: Path, intent: dict) -> None:
    (output / "controls").mkdir(mode=0o700)
    (output / "judge-calls").mkdir(mode=0o700)
    for name in sorted(verifier.FILES | {"frozen-manifest.json"}):
        source = controls / name
        if source.is_symlink() or not source.resolve().is_relative_to(controls):
            raise ValueError("experiment_judge_v4_controls_invalid")
        target = output / "controls" / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    atomic_json(output / _INTENT, intent)


def prepare_audit(
    controls: Path,
    output: Path,
    manifest_sha256: str,
    run_id: str,
    seconds: int,
    *,
    judge_id: str = judge.JUDGE_V4,
) -> dict:
    """Stage immutable inputs; this function does not access a model or GPU."""
    validate_run_id(run_id)
    if judge_id not in {judge.JUDGE_V4, judge.JUDGE_V5}:
        raise ValueError("experiment_judge_version_invalid")
    if type(seconds) is not int or not CLEANUP_SECONDS < seconds <= MAX_SECONDS:
        raise ValueError("experiment_judge_v4_budget_invalid")
    controls, output = controls.resolve(strict=True), output.resolve()
    if output == controls or output.is_relative_to(controls):
        raise ValueError("experiment_judge_v4_output_overlaps_controls")
    if digest(controls / "frozen-manifest.json") != manifest_sha256:
        raise ValueError("experiment_judge_v4_controls_changed")
    intent = {
        "run_id": run_id,
        "controls": str(controls),
        "manifest_sha256": manifest_sha256,
        "seconds": seconds,
        "cleanup_seconds": CLEANUP_SECONDS,
        "implementation_sha256": verifier.implementation_hashes(),
    }
    _stage_controls(controls, output, intent)
    manifest = verifier.control_files(output, manifest_sha256, judge_id=judge_id)
    verifier.execution_order(output, manifest)
    # Only phase-one cases are materialized before their gate has passed.
    verifier.jobs_for(output, manifest, "legacy")
    verifier.jobs_for(output, manifest, "development")
    legacy = judge.Qualification.model_validate(
        read_json(output / "controls/legacy/judge-qualification-receipt.json")
    )
    if legacy.prompt_sha256 != judge.PROMPT_SHA256:
        raise ValueError("experiment_judge_v4_legacy_pin_changed")
    protocol = {
        "schema_version": 5 if judge_id == judge.JUDGE_V5 else 4,
        "judge": judge_id,
        "system": judge.prompt_for(judge_id),
        "options": judge.options_for(judge_id),
        "model": legacy.model,
        "model_sha256": legacy.model_sha256,
        "ollama": {"version": legacy.ollama_version},
        "accuracy_manifest_sha256": manifest_sha256,
        "implementation_sha256": verifier.implementation_hashes(),
        "run_id": run_id,
        "intent_sha256": digest(output / _INTENT),
    }
    path = output / "judge-protocol.json"
    if path.exists():
        if read_json(path) != protocol:
            raise ValueError("experiment_judge_v4_protocol_changed")
    else:
        atomic_json(path, protocol)
    pin_model = (
        judge.QualificationV5 if judge_id == judge.JUDGE_V5 else judge.QualificationV4
    )
    provisional = pin_model(
        **{
            **legacy.model_dump(),
            "schema_version": 3 if judge_id == judge.JUDGE_V5 else 2,
            "true_positives": 24,
            "prompt_sha256": hashlib.sha256(
                judge.prompt_for(judge_id).encode()
            ).hexdigest(),
            "protocol_sha256": digest(path),
            "accuracy_manifest_sha256": manifest_sha256,
            "gold_sha256": manifest["files"]["legacy/qualification-gold.json"],
            "result_sha256": "0" * 64,
        }
    )
    from .semantic_judge_provenance import verify_legacy

    verify_legacy(output, manifest, provisional)
    return {"root": output, "manifest": manifest, "pin": provisional, "intent": intent}


def _collect(
    context: dict,
    client: httpx.Client,
    entries: list[dict],
    rows: list[dict],
    remaining: Callable[[], float],
    progress: Callable[[dict], None],
) -> None:
    root, manifest, pin = context["root"], context["manifest"], context["pin"]
    jobs = {
        split: verifier.jobs_for(root, manifest, split)[0]
        for split in {row["split"] for row in entries}
    }
    for entry in entries:
        remaining()
        index = len(rows) + 1
        case, answer = jobs[entry["split"]][entry["answer_id"]]
        request = verifier.request_for(
            pin.model, case, answer, judge_id=judge.judge_for(pin)
        )
        provenance = {
            "call_id": uuid.uuid4().hex,
            "run_id": context["intent"]["run_id"],
            "intent_sha256": digest(root / _INTENT),
            "protocol_sha256": pin.protocol_sha256,
            "started_at_ns": time.time_ns(),
            "started_monotonic_ns": time.monotonic_ns(),
        }
        response = judge._api(client, "chat", request, timeout=remaining())
        provenance.update(
            finished_at_ns=time.time_ns(), finished_monotonic_ns=time.monotonic_ns()
        )
        decision = judge._decode(
            response,
            [c["id"] for c in case["criteria"]],
            pin.model,
            judge=judge.judge_for(pin),
        )
        request_sha = stable_hash(request)
        path = root / "judge-calls" / f"{index:03d}.json"
        if path.exists():
            raise ValueError("experiment_judge_v4_call_already_exists")
        atomic_json(
            path,
            {
                **provenance,
                "request": request,
                "request_sha256": request_sha,
                "response": response,
            },
        )
        rows.append(
            {
                **entry,
                "index": index,
                "request_sha256": request_sha,
                "decision": decision.model_dump() if decision is not None else None,
                "call_sha256": digest(path),
            }
        )
        atomic_json(
            root / "progress.json", {"completed_calls": len(rows), "rows": rows}
        )
        if index % 18 == 0:
            progress({"stage": "calls", "completed_calls": index})


def run_audit(
    context: dict, *, progress: Callable[[dict], None] = lambda _row: None
) -> dict:
    """Exactly one attempt. Never retry a call to obtain a passing decision."""
    root, manifest, pin = context["root"], context["manifest"], context["pin"]
    scope = {
        "run_id": context["intent"]["run_id"],
        "intent_sha256": digest(root / _INTENT),
        "protocol_sha256": pin.protocol_sha256,
    }
    # Atomic claim prevents concurrent execution and retry-after-exposure.
    with (root / _STARTED).open("x", encoding="utf8") as stream:
        json.dump(
            {
                **scope,
                "started_at_ns": time.time_ns(),
                "started_monotonic_ns": time.monotonic_ns(),
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    started = time.monotonic()
    remaining = judge._deadline(
        context["intent"]["seconds"] - CLEANUP_SECONDS, lambda: None
    )
    rows: list[dict] = []
    result = {
        **scope,
        "status": "incomplete",
        "phase": "legacy_and_development",
        "started_sha256": digest(root / _STARTED),
        "rows": rows,
        "holdout_opened": False,
        "qualification_receipt_required": True,
    }
    try:
        order = verifier.execution_order(root, manifest)
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            judge._verify_runtime(client, pin)
            with judge._review_gpu(client, pin, context["intent"]["run_id"]):
                judge._verify_runtime(client, pin)
                progress(
                    {"stage": "legacy_and_development_started", "planned_calls": 108}
                )
                _collect(context, client, order[:108], rows, remaining, progress)
                try:
                    verifier.verify_rows(root, manifest, pin, rows, phase1=True)
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    result.update(status="failed_qualification", error=str(exc))
                    raise
                atomic_json(
                    root / _PHASE1_PASS,
                    {
                        **scope,
                        "completed_calls": 108,
                        "phase1_rows_sha256": stable_hash(rows),
                        "closed_at_ns": time.time_ns(),
                        "closed_monotonic_ns": time.monotonic_ns(),
                    },
                )
                progress(
                    {"stage": "legacy_and_development_passed", "completed_calls": 108}
                )
                remaining()
                result.update(phase="holdout_stability", holdout_opened=True)
                _collect(context, client, order[108:], rows, remaining, progress)
                try:
                    result["metrics"] = verifier.verify_rows(root, manifest, pin, rows)
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    result.update(status="failed_qualification", error=str(exc))
                    raise
                judge._verify_runtime(client, pin)
        result.update(status="complete", phase="complete")
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        RuntimeError,
    ) as exc:
        result["error"] = str(exc)
        if result["status"] != "failed_qualification":
            result["status"] = "incomplete"
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["finished_at_ns"] = time.time_ns()
        result["finished_monotonic_ns"] = time.monotonic_ns()
        result["completed_calls"] = len(rows)
        if (root / _PHASE1_PASS).exists():
            result["phase1_marker_sha256"] = digest(root / _PHASE1_PASS)
        atomic_json(root / _RESULT, result)
    if result["status"] == "complete":
        receipt = {
            **pin.model_dump(),
            "result_sha256": digest(root / _RESULT),
        }
        judge_id = judge.judge_for(pin)
        location_key = (
            "VENOM_ACADEMY_JUDGE_V5_AUDIT_ROOT"
            if judge_id == judge.JUDGE_V5
            else "VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT"
        )
        old_location = os.environ.get(location_key)
        os.environ[location_key] = str(root)
        try:
            qualified = judge.qualification(
                {"judge": judge_id, "judge_qualification": receipt}
            )
            atomic_json(
                root / "judge-qualification-receipt.json", qualified.model_dump()
            )
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            result.update(status="failed_qualification", error=str(exc))
            atomic_json(root / _RESULT, result)
        finally:
            if old_location is None:
                os.environ.pop(location_key, None)
            else:
                os.environ[location_key] = old_location
        progress(
            {
                "stage": "qualification_passed"
                if result["status"] == "complete"
                else result["status"],
                "completed_calls": 180,
            }
        )
    else:
        progress(
            {
                "stage": result["status"],
                "phase": result["phase"],
                "completed_calls": len(rows),
                "holdout_opened": result["holdout_opened"],
            }
        )
    return result
