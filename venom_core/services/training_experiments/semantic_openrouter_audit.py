"""Operator-requested OpenRouter qualification runner; imports never call a provider."""

from __future__ import annotations

import hashlib
import math
import signal
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
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

_MANIFEST_FILE = "frozen-manifest.json"
_PROTOCOL_FILE = "protocol.json"
_RESULT_FILE = "result.json"
_HOLDOUT_RESERVE_FILE = "holdout-reserve.json"
_LEDGER_FILE = "ledger.json"
_PHASE1_RESULT_FILE = "phase1-result.json"
_REQUEST_TIMEOUT_SECONDS = 75


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
    manifest_raw = _bytes(controls, _MANIFEST_FILE, controls_sha256)
    manifest = read_json(controls / _MANIFEST_FILE)
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
        "request_timeout_seconds": _REQUEST_TIMEOUT_SECONDS,
        "holdout_cleanup_seconds": 120,
        "initial_accounted_usd": str(initial),
        "initial_unknown_reserved_usd": str(unknown),
        "max_seconds": max_seconds,
        "created_at": _utc(),
        "automatic_retry": False,
        "operator_execute_required": True,
        "uncertain_decision": "stop_without_qualification",
    }
    atomic_json(output / _PROTOCOL_FILE, protocol)
    atomic_json(
        output / "frozen.json",
        {"protocol_sha256": digest(output / _PROTOCOL_FILE), "created_at": _utc()},
    )
    return {"status": "prepared_not_qualified", "audit_root": str(output), **protocol}


def _static(root: Path) -> tuple[dict, dict, str]:
    protocol = read_json(root / _PROTOCOL_FILE)
    sha = digest(root / _PROTOCOL_FILE)
    _require(
        read_json(root / "frozen.json")["protocol_sha256"] == sha
        and protocol["audit_runner_sha256"] == digest(Path(__file__))
        and protocol["implementation_sha256"] == judge.implementation_identity()
        and protocol["judge"] == judge.JUDGE
        and protocol["request_contract"] == judge._contract()
        and protocol["request_timeout_seconds"] == _REQUEST_TIMEOUT_SECONDS,
        "remote_audit_frozen_contract_changed",
    )
    _bytes(root, "data-review.json", protocol["data_review_sha256"])
    _bytes(root / "controls", _MANIFEST_FILE, protocol["controls_manifest_sha256"])
    manifest = read_json(root / "controls/frozen-manifest.json")
    for name, expected in manifest["files"].items():
        _require(name in CONTROL_FILES, "remote_audit_controls_invalid")
        _bytes(root / "controls", name, expected)
    return protocol, manifest, sha


class AuditRequestTimeout(httpx.TimeoutException):
    """The entire HTTP exchange exceeded its wall-clock allowance."""


def _require_request_timer() -> None:
    _require(
        hasattr(signal, "setitimer")
        and threading.current_thread() is threading.main_thread(),
        "remote_audit_request_timer_unavailable",
    )
    _require(
        signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
        "remote_audit_request_timer_in_use",
    )


def _expire_request(_signum: int, _frame: object) -> None:
    raise AuditRequestTimeout("remote_audit_request_deadline_exceeded")


def post_with_deadline(
    client: httpx.Client, body: dict, timeout_seconds: float
) -> httpx.Response:
    """Bound the POST, including reading its complete body, on the operator CLI."""
    _require_request_timer()
    _require(
        math.isfinite(timeout_seconds) and timeout_seconds > 0,
        "remote_audit_request_timeout_invalid",
    )
    previous = signal.signal(signal.SIGALRM, _expire_request)
    try:
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        return client.post(
            judge.ENDPOINT,
            json=body,
            timeout=httpx.Timeout(timeout_seconds, connect=min(8, timeout_seconds)),
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


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
            "protocol_sha256": digest(root / _PROTOCOL_FILE),
            "result_sha256": digest(root / _RESULT_FILE),
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
    _require_request_timer()
    with file_lock(root / "session.lock", blocking=False):
        _require(not (root / "started.json").exists(), "remote_audit_single_attempt")
        atomic_json(
            root / "started.json",
            {"created_at": _utc(), "protocol_sha256": protocol_sha},
        )
        return _execute(
            root, protocol, manifest, protocol_sha, budget, per_request, client_factory
        )


@dataclass
class _AuditState:
    root: Path
    protocol: dict
    manifest: dict
    protocol_sha: str
    budget: Decimal
    per_request: Decimal
    client_factory: Callable
    rows: list[dict] = field(default_factory=list)
    known: Decimal = Decimal(0)
    unknown: Decimal = Decimal(0)
    status: str = "transport_incomplete"
    metrics: dict | None = None
    phase1_sha: str | None = None
    holdout_opened: bool = False
    start: float = 0
    generations: set[str] = field(default_factory=set)
    order: list[dict] = field(default_factory=list)
    client: httpx.Client | None = None

    @property
    def initial(self) -> Decimal:
        return judge._money(self.protocol["initial_accounted_usd"])

    @property
    def accounted(self) -> Decimal:
        return self.initial + self.known + self.unknown

    def remaining(self) -> float:
        return self.protocol["max_seconds"] - (time.monotonic() - self.start)

    def ledger(self, pending: str | None) -> None:
        atomic_json(
            self.root / _LEDGER_FILE,
            {
                "accounted_usd": str(self.accounted),
                "pending_call_id": pending,
                "actual_known_cost_usd": str(self.known),
                "unknown_reserved_usd": str(self.unknown),
                "created_at": _utc(),
            },
        )


def _next_audit_request(state: _AuditState) -> tuple | None:
    _static(state.root)
    if state.remaining() <= 0:
        state.status = "deadline_exceeded"
        return None
    entry = state.order[len(state.rows)]
    case, answer = judge._jobs(state.root, state.manifest, entry["split"])[0][
        entry["answer_id"]
    ]
    body = judge._control_request(case, answer)
    reservation = judge.reserve(body)
    if entry["split"] == "holdout" and reservation > judge._money(
        state.protocol["holdout_max_request_usd"]
    ):
        state.status = "holdout_request_bound_exceeded"
        return None
    if reservation > state.per_request or state.accounted + reservation > state.budget:
        state.status = "budget_exhausted"
        return None
    return entry, answer, body, reservation


def _post_audit_row(
    state: _AuditState, row: dict, answer: dict, stack: ExitStack
) -> None:
    if state.client is None:
        state.client = stack.enter_context(
            state.client_factory(
                timeout=httpx.Timeout(_REQUEST_TIMEOUT_SECONDS, connect=8),
                trust_env=False,
                follow_redirects=False,
                headers={"Authorization": "Bearer " + runtime.credential()},
            )
        )
    # Receipt/ledger fsync and client construction belong to the same deadline.
    remaining = state.remaining()
    reservation = judge._money(row["reserved_usd"])
    if remaining <= 0:
        state.unknown -= reservation
        row.update(status="not_sent", cost_usd="0", error_type="deadline_exceeded")
        state.status = "deadline_exceeded"
        return
    response = post_with_deadline(
        state.client,
        row["request"],
        min(state.protocol["request_timeout_seconds"], remaining),
    )
    row["http_status"] = response.status_code
    try:
        row["response"] = response.json()
    except ValueError:
        row["response"] = {"non_json_body": response.text[:16000]}
        raise
    _require(isinstance(row["response"], dict), "remote_audit_response_invalid")
    row["cost_usd"] = judge.reported_cost(row["response"])
    if row["cost_usd"] is not None:
        state.known += judge._money(row["cost_usd"])
        state.unknown -= reservation
    response.raise_for_status()
    _require(row["cost_usd"] is not None, "remote_audit_cost_missing")
    _require(
        judge._money(row["cost_usd"]) <= reservation,
        "remote_audit_reservation_exceeded",
    )
    decision = judge.decode(row["response"], row["request"], answer["text"])
    generation = row["response"]["id"]
    _require(generation not in state.generations, "remote_audit_duplicate_generation")
    state.generations.add(generation)
    row["decision"] = decision.model_dump()
    _require(
        decision.unsupported != "unclear" and "unclear" not in decision.atoms.values(),
        "remote_audit_uncertain",
    )
    row["status"] = "completed"


def _audit_next(state: _AuditState, stack: ExitStack) -> bool:
    request = _next_audit_request(state)
    if request is None:
        return False
    entry, answer, body, reservation = request
    row = {
        **entry,
        "index": len(state.rows) + 1,
        "call_id": uuid4().hex,
        "status": "attempted",
        "protocol_sha256": state.protocol_sha,
        "request": body,
        "request_sha256": stable_hash(body),
        "reserved_usd": str(reservation),
        "cost_usd": None,
        "started_at": _utc(),
        "response": {},
    }
    path = state.root / "receipts" / f"{row['index']:03d}.json"
    atomic_json(path, row)
    state.unknown += reservation
    state.ledger(row["call_id"])
    try:
        _post_audit_row(state, row, answer, stack)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        row.update(status="failed", error_type=type(exc).__name__)
    finally:
        row["finished_at"] = _utc()
        row["response_sha256"] = stable_hash(row["response"])
        atomic_json(path, row)
        state.rows.append(row)
        state.ledger(None)
    return row["status"] == "completed"


def _reserve_holdout(state: _AuditState) -> bool:
    cap = judge._money(state.protocol["holdout_max_request_usd"])
    reserve = 72 * cap
    remaining_budget = state.budget - state.accounted
    remaining_seconds = state.remaining()
    required_seconds = (
        72 * state.protocol["request_timeout_seconds"]
        + state.protocol["holdout_cleanup_seconds"]
    )
    if remaining_budget < reserve:
        state.status = "holdout_budget_unavailable"
        return False
    if remaining_seconds < required_seconds:
        state.status = "holdout_deadline_unavailable"
        return False
    atomic_json(
        state.root / _HOLDOUT_RESERVE_FILE,
        {
            "phase1_result_sha256": state.phase1_sha,
            "request_bound_usd": str(cap),
            "budget_reserve_usd": str(reserve),
            "remaining_budget_usd": str(remaining_budget),
            "remaining_seconds": remaining_seconds,
            "required_seconds": required_seconds,
            "created_at": _utc(),
        },
    )
    return True


def _phase1_gate(state: _AuditState) -> bool:
    state.metrics = judge._audit_metrics(
        state.root, state.manifest, state.rows, phase1=True
    )
    expected = {
        k: v
        for k, v in state.manifest["thresholds"].items()
        if not k.startswith("holdout")
    }
    passed = state.metrics == expected
    atomic_json(
        state.root / _PHASE1_RESULT_FILE,
        {
            "status": "passed" if passed else "failed_qualification",
            "rows": 156,
            "metrics": state.metrics,
            "receipt_hashes": _hashes(state.root),
            "finished_at": _utc(),
        },
    )
    state.phase1_sha = digest(state.root / _PHASE1_RESULT_FILE)
    if not passed:
        state.status = "failed_qualification"
        return False
    if not _reserve_holdout(state):
        return False
    state.holdout_opened = True
    try:
        state.manifest = _stage_holdout(state.root, state.manifest)
        state.order = judge._audit_order(state.root, state.manifest)
    except (OSError, ValueError, KeyError, TypeError):
        state.status = "holdout_stage_incomplete"
        return False
    return True


def _audit_result(state: _AuditState) -> dict:
    if state.remaining() < 0:
        state.status = "deadline_exceeded"
    reserve_path = state.root / _HOLDOUT_RESERVE_FILE
    result = {
        "status": state.status,
        "protocol_sha256": state.protocol_sha,
        "rows": len(state.rows),
        "holdout_opened": state.holdout_opened,
        "holdout_reserve_sha256": digest(reserve_path)
        if reserve_path.exists()
        else None,
        "metrics": state.metrics,
        "receipt_hashes": _hashes(state.root),
        "phase1_result_sha256": state.phase1_sha,
        "actual_known_cost_usd": str(state.known),
        "unknown_reserved_usd": str(state.unknown),
        "carried_unknown_reserved_usd": state.protocol["initial_unknown_reserved_usd"],
        "accounted_usd": str(state.accounted),
        "finished_at": _utc(),
    }
    atomic_json(state.root / _RESULT_FILE, result)
    if state.status == "passed":
        _publish_qualification(state.root, state.protocol, result)
    return result


def _publish_qualification(root: Path, protocol: dict, result: dict) -> None:
    pin = _pin(root, protocol)
    try:
        judge.verify_audit(pin)
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status="verification_failed", error_type=type(exc).__name__)
        atomic_json(root / _RESULT_FILE, result)
    else:
        atomic_json(root / "qualification.json", pin.model_dump())


def _execute(
    root: Path,
    protocol: dict,
    manifest: dict,
    protocol_sha: str,
    budget: Decimal,
    per_request: Decimal,
    client_factory: Callable,
) -> dict:
    state = _AuditState(
        root, protocol, manifest, protocol_sha, budget, per_request, client_factory
    )
    state.order = judge._audit_order(root, manifest, phase1=True)
    state.start = time.monotonic()
    (root / "receipts").mkdir()
    with ExitStack() as stack:
        while len(state.rows) < len(state.order):
            if not _audit_next(state, stack):
                break
            if len(state.rows) == 156 and not _phase1_gate(state):
                break
            if len(state.rows) == 228:
                state.metrics = judge._audit_metrics(root, state.manifest, state.rows)
                state.status = (
                    "passed"
                    if state.metrics == state.manifest["thresholds"]
                    else "failed_qualification"
                )
    return _audit_result(state)


def _hashes(root: Path) -> dict[str, str]:
    return {p.name: digest(p) for p in sorted((root / "receipts").glob("*.json"))}
