"""Operator-requested OpenRouter qualification runner; imports never call a provider."""

from __future__ import annotations

import hashlib
import math
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable
from uuid import uuid4

import httpx

from venom_core.config import SETTINGS
from venom_core.services import openrouter_runtime as runtime
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from . import openrouter_semantic_judge as judge
from .profiles import digest, read_json, stable_hash

CONTROL_FILES = frozenset(
    {
        "legacy/qualification-panel.json",
        "legacy/qualification-gold.json",
        "development/panel.json",
        "development/gold.json",
        "extra/panel.json",
        "extra/gold.json",
        "contrasts/panel.json",
        "contrasts/gold.json",
        "phase1-order.json",
        "semantic-contract.json",
        "repair-provenance.json",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise ValueError(error)


def _bytes(root: Path, name: str, expected: str) -> bytes:
    path = operator_path(root / name)
    _require(path.is_relative_to(root), "remote_audit_path_escape")
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == expected, "remote_audit_file_changed")
    return raw


def prepare(
    controls: Path,
    data_review: Path,
    output: Path,
    *,
    controls_sha256: str,
    data_review_sha256: str,
    budget_usd: str,
    max_seconds: float,
    holdout_max_request_usd: str,
    max_request_usd: str = "0.01",
    initial_accounted_usd: str = "0",
    initial_unknown_reserved_usd: str = "0",
) -> dict:
    """Freeze a separate namespace; holdout contents remain at their original path."""
    controls, data_review, output = (
        operator_path(path) for path in (controls, data_review, output)
    )
    _require(
        not output.exists()
        and not output.is_relative_to(controls)
        and not controls.is_relative_to(output),
        "remote_audit_output_exists_or_overlaps",
    )
    manifest_raw = _bytes(controls, "frozen-manifest.json", controls_sha256)
    manifest = read_json(controls / "frozen-manifest.json")
    _require(
        manifest.get("control_version") == "luna-controls-v3"
        and manifest.get("status") == "frozen_before_any_inference"
        and set(manifest["files"]) == CONTROL_FILES,
        "remote_audit_controls_invalid",
    )
    review_raw = _bytes(data_review.parent, data_review.name, data_review_sha256)
    review = read_json(data_review)
    _require(
        review.get("status") == "passed"
        and review.get("controls_manifest_sha256") == controls_sha256
        and isinstance(review.get("reviewer"), str)
        and bool(review["reviewer"].strip())
        and judge._time(review["created_at"]) <= datetime.now(timezone.utc),
        "remote_audit_data_review_required",
    )
    budget, per_request, initial, unknown, held_cap = (
        judge._money(value)
        for value in (
            budget_usd,
            max_request_usd,
            initial_accounted_usd,
            initial_unknown_reserved_usd,
            holdout_max_request_usd,
        )
    )
    _require(
        0 < held_cap <= per_request <= budget and 0 <= unknown <= initial <= budget,
        "remote_audit_budget_invalid",
    )
    _require(
        type(max_seconds) in (int, float)
        and math.isfinite(max_seconds)
        and 0 < max_seconds <= 86400,
        "remote_audit_deadline_invalid",
    )
    frozen_files = {
        name: _bytes(controls, name, sha) for name, sha in manifest["files"].items()
    }
    # No access to the holdout descriptor's source_directory occurs in prepare.
    output.mkdir(parents=True)
    for name, raw in frozen_files.items():
        target = output / "controls" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (output / "controls/frozen-manifest.json").write_bytes(manifest_raw)
    (output / "data-review.json").write_bytes(review_raw)
    judge._audit_order(output, manifest, phase1=True)
    protocol = {
        "schema_version": 1,
        "judge": judge.JUDGE,
        "request_contract": judge._contract(),
        "controls_manifest_sha256": controls_sha256,
        "implementation_sha256": judge.implementation_identity(),
        "data_review_sha256": data_review_sha256,
        "audit_runner_sha256": digest(Path(__file__)),
        "budget_usd": str(budget),
        "max_request_usd": str(per_request),
        "holdout_max_request_usd": str(held_cap),
        "holdout_request_timeout_seconds": 75,
        "holdout_cleanup_seconds": 120,
        "initial_accounted_usd": str(initial),
        "initial_unknown_reserved_usd": str(unknown),
        "max_seconds": max_seconds,
        "created_at": _utc(),
        "automatic_retry": False,
        "operator_execute_required": True,
        "uncertain_decision": "stop_without_qualification",
    }
    atomic_json(output / "protocol.json", protocol)
    atomic_json(
        output / "frozen.json",
        {"protocol_sha256": digest(output / "protocol.json"), "created_at": _utc()},
    )
    return {"status": "prepared_not_qualified", "audit_root": str(output), **protocol}


def _static(root: Path) -> tuple[dict, dict, str]:
    protocol = read_json(root / "protocol.json")
    sha = digest(root / "protocol.json")
    _require(
        read_json(root / "frozen.json")["protocol_sha256"] == sha
        and protocol["audit_runner_sha256"] == digest(Path(__file__))
        and protocol["implementation_sha256"] == judge.implementation_identity()
        and protocol["judge"] == judge.JUDGE
        and protocol["request_contract"] == judge._contract(),
        "remote_audit_frozen_contract_changed",
    )
    _bytes(root, "data-review.json", protocol["data_review_sha256"])
    _bytes(
        root / "controls", "frozen-manifest.json", protocol["controls_manifest_sha256"]
    )
    manifest = read_json(root / "controls/frozen-manifest.json")
    for name, expected in manifest["files"].items():
        _require(name in CONTROL_FILES, "remote_audit_controls_invalid")
        _bytes(root / "controls", name, expected)
    return protocol, manifest, sha


def _stage_holdout(root: Path, manifest: dict) -> dict:
    held = manifest["holdout"]
    _require(
        set(held["files"]) == {"panel.json", "gold.json"},
        "remote_audit_holdout_invalid",
    )
    source = operator_path(Path(held["source_directory"]))
    raw_files = {
        name: _bytes(source, name, expected) for name, expected in held["files"].items()
    }
    target = root / "controls/holdout"
    target.mkdir()
    for name, raw in raw_files.items():
        (target / name).write_bytes(raw)
    return {
        **manifest,
        "files": {
            **manifest["files"],
            **{"holdout/" + name: sha for name, sha in held["files"].items()},
        },
    }


def _pin(root: Path, protocol: dict) -> judge.QualificationRemote:
    return judge.QualificationRemote.model_validate(
        {
            "schema_version": 1,
            "judge": judge.JUDGE,
            "audit_root": str(root),
            "model": judge.MODEL,
            "provider": judge.PROVIDER,
            "endpoint": judge.ENDPOINT,
            "protocol_sha256": digest(root / "protocol.json"),
            "result_sha256": digest(root / "result.json"),
            "controls_manifest_sha256": protocol["controls_manifest_sha256"],
            "prompt_sha256": judge._contract()["prompt_sha256"],
            "request_contract_sha256": stable_hash(judge._contract()),
            "implementation_sha256": protocol["implementation_sha256"],
        }
    )


def run(
    audit_root: Path,
    *,
    execute: bool = False,
    client_factory: Callable = httpx.Client,
) -> dict:
    """One explicit attempt; fake transports are used only by offline tests."""
    _require(execute is True, "remote_audit_operator_execute_required")
    root = operator_path(audit_root)
    protocol, manifest, protocol_sha = _static(root)
    _require(
        runtime.is_enabled() and runtime.cloud_allowed() and bool(runtime.credential()),
        "remote_audit_provider_unavailable",
    )
    budget = min(
        judge._money(protocol["budget_usd"]),
        Decimal(str(SETTINGS.OPENROUTER_DAILY_LIMIT_USD)),
    )
    per_request = min(
        judge._money(protocol["max_request_usd"]),
        Decimal(str(SETTINGS.OPENROUTER_MESSAGE_LIMIT_USD)),
    )
    initial = judge._money(protocol["initial_accounted_usd"])
    _require(
        0 < judge._money(protocol["holdout_max_request_usd"]) <= per_request <= budget
        and initial <= budget,
        "remote_audit_budget_invalid",
    )
    with file_lock(root / "session.lock", blocking=False):
        _require(not (root / "started.json").exists(), "remote_audit_single_attempt")
        atomic_json(
            root / "started.json",
            {"created_at": _utc(), "protocol_sha256": protocol_sha},
        )
        return _execute(
            root, protocol, manifest, protocol_sha, budget, per_request, client_factory
        )


def _execute(
    root: Path,
    protocol: dict,
    manifest: dict,
    protocol_sha: str,
    budget: Decimal,
    per_request: Decimal,
    client_factory: Callable,
) -> dict:
    order = judge._audit_order(root, manifest, phase1=True)
    rows: list[dict] = []
    known, unknown = Decimal(0), Decimal(0)
    initial = judge._money(protocol["initial_accounted_usd"])
    status, metrics = "transport_incomplete", None
    phase1_sha = None
    holdout_opened = False
    held_cap = judge._money(protocol["holdout_max_request_usd"])
    start = time.monotonic()
    generations: set[str] = set()
    (root / "receipts").mkdir()
    with ExitStack() as stack:
        client = None
        index = 0
        while index < len(order):
            _static(root)
            remaining = protocol["max_seconds"] - (time.monotonic() - start)
            if remaining <= 0:
                status = "deadline_exceeded"
                break
            entry = order[index]
            case, answer = judge._jobs(root, manifest, entry["split"])[0][
                entry["answer_id"]
            ]
            body = judge._control_request(case, answer)
            reservation = judge.reserve(body)
            if entry["split"] == "holdout" and reservation > held_cap:
                status = "holdout_request_bound_exceeded"
                break
            if (
                reservation > per_request
                or initial + known + unknown + reservation > budget
            ):
                status = "budget_exhausted"
                break
            row = {
                **entry,
                "index": index + 1,
                "call_id": uuid4().hex,
                "status": "attempted",
                "protocol_sha256": protocol_sha,
                "request": body,
                "request_sha256": stable_hash(body),
                "reserved_usd": str(reservation),
                "cost_usd": None,
                "started_at": _utc(),
                "response": {},
            }
            path = root / "receipts" / f"{index + 1:03d}.json"
            atomic_json(path, row)
            unknown += reservation
            atomic_json(
                root / "ledger.json",
                {
                    "accounted_usd": str(initial + known + unknown),
                    "pending_call_id": row["call_id"],
                    "created_at": _utc(),
                },
            )
            try:
                if client is None:
                    client = stack.enter_context(
                        client_factory(
                            timeout=httpx.Timeout(75, connect=8),
                            trust_env=False,
                            follow_redirects=False,
                            headers={"Authorization": "Bearer " + runtime.credential()},
                        )
                    )
                response = client.post(
                    judge.ENDPOINT,
                    json=body,
                    timeout=httpx.Timeout(
                        min(75, remaining), connect=min(8, remaining)
                    ),
                )
                row["http_status"] = response.status_code
                try:
                    row["response"] = response.json()
                except ValueError:
                    row["response"] = {"non_json_body": response.text[:16000]}
                    raise
                _require(
                    isinstance(row["response"], dict), "remote_audit_response_invalid"
                )
                row["cost_usd"] = judge.reported_cost(row["response"])
                if row["cost_usd"] is not None:
                    cost = judge._money(row["cost_usd"])
                    known += cost
                    unknown -= reservation
                response.raise_for_status()
                _require(row["cost_usd"] is not None, "remote_audit_cost_missing")
                _require(
                    judge._money(row["cost_usd"]) <= reservation,
                    "remote_audit_reservation_exceeded",
                )
                decision = judge.decode(row["response"], body, answer["text"])
                generation = row["response"]["id"]
                _require(
                    generation not in generations, "remote_audit_duplicate_generation"
                )
                generations.add(generation)
                row["decision"] = decision.model_dump()
                _require(
                    decision.unsupported != "unclear"
                    and "unclear" not in decision.atoms.values(),
                    "remote_audit_uncertain",
                )
                row["status"] = "completed"
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                row.update(status="failed", error_type=type(exc).__name__)
            finally:
                row["finished_at"] = _utc()
                row["response_sha256"] = stable_hash(row["response"])
                atomic_json(path, row)
                rows.append(row)
                atomic_json(
                    root / "ledger.json",
                    {
                        "accounted_usd": str(initial + known + unknown),
                        "pending_call_id": None,
                        "actual_known_cost_usd": str(known),
                        "unknown_reserved_usd": str(unknown),
                        "created_at": _utc(),
                    },
                )
            index += 1
            if row["status"] != "completed":
                status = "transport_incomplete"
                break
            if index == 156:
                metrics = judge._audit_metrics(root, manifest, rows, phase1=True)
                expected = {
                    k: v
                    for k, v in manifest["thresholds"].items()
                    if not k.startswith("holdout")
                }
                phase1_status = (
                    "passed" if metrics == expected else "failed_qualification"
                )
                atomic_json(
                    root / "phase1-result.json",
                    {
                        "status": phase1_status,
                        "rows": 156,
                        "metrics": metrics,
                        "receipt_hashes": _hashes(root),
                        "finished_at": _utc(),
                    },
                )
                phase1_sha = digest(root / "phase1-result.json")
                if phase1_status != "passed":
                    status = "failed_qualification"
                    break
                held_reserve = 72 * held_cap
                remaining_budget = budget - initial - known - unknown
                remaining_seconds = protocol["max_seconds"] - (time.monotonic() - start)
                required_seconds = (
                    72 * protocol["holdout_request_timeout_seconds"]
                    + protocol["holdout_cleanup_seconds"]
                )
                if remaining_budget < held_reserve:
                    status = "holdout_budget_unavailable"
                    break
                if remaining_seconds < required_seconds:
                    status = "holdout_deadline_unavailable"
                    break
                atomic_json(
                    root / "holdout-reserve.json",
                    {
                        "phase1_result_sha256": phase1_sha,
                        "request_bound_usd": str(held_cap),
                        "budget_reserve_usd": str(held_reserve),
                        "remaining_budget_usd": str(remaining_budget),
                        "remaining_seconds": remaining_seconds,
                        "required_seconds": required_seconds,
                        "created_at": _utc(),
                    },
                )
                # Conservative exposure flag also covers failed/partial copying.
                holdout_opened = True
                try:
                    manifest = _stage_holdout(root, manifest)
                    order = judge._audit_order(root, manifest)
                except (OSError, ValueError, KeyError, TypeError):
                    status = "holdout_stage_incomplete"
                    break
            if index == 228:
                metrics = judge._audit_metrics(root, manifest, rows)
                status = (
                    "passed"
                    if metrics == manifest["thresholds"]
                    else "failed_qualification"
                )
    if time.monotonic() - start > protocol["max_seconds"]:
        status = "deadline_exceeded"
    result = {
        "status": status,
        "protocol_sha256": protocol_sha,
        "rows": len(rows),
        "holdout_opened": holdout_opened,
        "holdout_reserve_sha256": (
            digest(root / "holdout-reserve.json")
            if (root / "holdout-reserve.json").exists()
            else None
        ),
        "metrics": metrics,
        "receipt_hashes": _hashes(root),
        "phase1_result_sha256": phase1_sha,
        "actual_known_cost_usd": str(known),
        "unknown_reserved_usd": str(unknown),
        "carried_unknown_reserved_usd": protocol["initial_unknown_reserved_usd"],
        "accounted_usd": str(initial + known + unknown),
        "finished_at": _utc(),
    }
    atomic_json(root / "result.json", result)
    if status == "passed":
        pin = _pin(root, protocol)
        try:
            judge.verify_audit(pin)
        except (ValueError, KeyError, TypeError) as exc:
            result.update(status="verification_failed", error_type=type(exc).__name__)
            atomic_json(root / "result.json", result)
        else:
            atomic_json(root / "qualification.json", pin.model_dump())
    return result


def _hashes(root: Path) -> dict[str, str]:
    return {p.name: digest(p) for p in sorted((root / "receipts").glob("*.json"))}
