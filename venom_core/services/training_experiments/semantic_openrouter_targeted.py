"""Frozen, operator-run regression panels for the Academy OpenRouter judge."""

from __future__ import annotations

import ctypes
import errno
import json
import math
import os
import tempfile
from collections import Counter
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from typing import cast

from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.remote_training.paths import data_directory, operator_path

from . import openrouter_semantic_judge as judge
from . import semantic_openrouter_audit as audit
from .profiles import digest, stable_hash
from .semantic_judge_v5 import MAX_EVIDENCE_TEXT_CHARS

_PANEL_FILE = "panel.json"
_INVALID = "remote_audit_targeted_panel_invalid"
_OUTPUT_EXISTS = "remote_audit_output_exists_or_overlaps"
_RENAME_NOREPLACE = 1


def _validate_panel(panel: dict) -> list[Decimal]:
    audit._require(
        panel.get("judge") == judge.JUDGE
        and panel.get("model") == judge.MODEL
        and panel.get("provider") == judge.PROVIDER
        and panel.get("endpoint") == judge.ENDPOINT
        and panel.get("prompt_sha256") == judge._contract()["prompt_sha256"],
        _INVALID,
    )
    cases, order = panel["cases"], panel["order"]
    audit._require(isinstance(cases, dict) and isinstance(order, list), _INVALID)
    audit._require(
        0 < len(order) <= 228
        and all(isinstance(label, str) for label in order)
        and set(order) == cases.keys()
        and all(count == 2 for count in Counter(order).values()),
        _INVALID,
    )
    reservations = {}
    for label, case in cases.items():
        body = case["body"]
        packet = json.loads(body["messages"][1]["content"])
        text = packet["candidate"]
        criteria = packet["criteria"]
        audit._require(
            stable_hash(judge._control_request({**packet, "id": label}, {"text": text}))
            == stable_hash(body),
            _INVALID,
        )
        expected = case["expected"]
        audit._require(
            expected.keys() == set(judge.DECISION_FIELDS)
            and set(expected["atoms"]) == {criterion["id"] for criterion in criteria},
            _INVALID,
        )
        decision = judge.local._Decision.model_validate({**expected, "reason": ""})
        audit._require(
            decision.unsupported != "unclear"
            and "unclear" not in decision.atoms.values()
            and (
                "contradicted" not in decision.atoms.values()
                or decision.unsupported == "yes"
            ),
            _INVALID,
        )
        quote = case.get("required_unsupported_quote")
        if quote is not None:
            audit._require(
                isinstance(quote, str)
                and len(quote) <= MAX_EVIDENCE_TEXT_CHARS
                and bool(quote.strip())
                and quote in text
                and decision.unsupported == "yes",
                _INVALID,
            )
        reservations[label] = judge.reserve(body)
    return [reservations[label] for label in order]


def _write_panel(directory: Path, raw: bytes) -> None:
    with data_directory(directory) as directory_fd:
        descriptor = os.open(
            _PANEL_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


class _PublicationSyncError(OSError):
    """The complete directory was renamed, but its parent could not be synced."""


def _publish(staged: Path, output: Path) -> None:
    # Linux renameat2 provides the no-replacement guarantee even for empty targets.
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    with data_directory(output.parent) as directory_fd:
        if rename(
            directory_fd,
            os.fsencode(staged.name),
            directory_fd,
            os.fsencode(output.name),
            _RENAME_NOREPLACE,
        ):
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise ValueError(_OUTPUT_EXISTS)
            raise OSError(error, os.strerror(error), output)
        try:
            os.fsync(directory_fd)
        except OSError as error:
            raise _PublicationSyncError(error.errno, error.strerror, output) from error


def prepare(
    panel: Path,
    output: Path,
    *,
    panel_sha256: str,
    budget_usd: str,
    max_seconds: float,
    max_request_usd: str = "0.01",
    initial_accounted_usd: str = "0",
    initial_unknown_reserved_usd: str = "0",
) -> dict:
    """Freeze an unchanged regression panel without obtaining credentials."""
    panel, output = operator_path(panel), operator_path(output)
    audit._require(
        not output.exists() and not panel.is_relative_to(output),
        _OUTPUT_EXISTS,
    )
    raw = audit._bytes(panel.parent, panel.name, panel_sha256)
    quotes = _validate_panel(json.loads(raw))
    budget, per_request, initial, unknown = (
        judge._money(value)
        for value in (
            budget_usd,
            max_request_usd,
            initial_accounted_usd,
            initial_unknown_reserved_usd,
        )
    )
    audit._require(
        0 < per_request <= budget and 0 <= unknown <= initial <= budget,
        "remote_audit_budget_invalid",
    )
    audit._require(
        type(max_seconds) in (int, float)
        and math.isfinite(max_seconds)
        and 0 < max_seconds <= 86400,
        "remote_audit_deadline_invalid",
    )
    maximum = max(quotes)
    reserve = maximum * cast(int, audit._RATE_LIMIT_POLICY["max_retries_per_audit"])
    planned = initial + sum(quotes, Decimal(0)) + reserve
    audit._require(
        maximum <= per_request and planned <= budget, "remote_audit_budget_invalid"
    )
    protocol = {
        "schema_version": 1,
        "kind": "targeted_regression",
        "panel_sha256": panel_sha256,
        "planned_requests": len(quotes),
        "planned_budget_usd": str(planned),
        "max_case_reservation_usd": str(maximum),
        "budget_usd": str(budget),
        "max_request_usd": str(per_request),
        "initial_accounted_usd": str(initial),
        "initial_unknown_reserved_usd": str(unknown),
        "max_seconds": max_seconds,
        "judge": judge.JUDGE,
        "request_contract": judge._contract(),
        "implementation_sha256": judge.implementation_identity(),
        "audit_runner_sha256": digest(Path(audit.__file__)),
        "targeted_runner_sha256": digest(Path(__file__)),
        "request_timeout_seconds": audit._REQUEST_TIMEOUT_SECONDS,
        "automatic_retry": audit._AUTOMATIC_RETRY,
        "rate_limit": audit._RATE_LIMIT_POLICY,
        "manual_review_required": True,
        "created_at": audit._utc(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".targeted-", dir=output.parent) as temp:
        staged = Path(temp)
        _write_panel(staged, raw)
        atomic_json(staged / "protocol.json", protocol)
        sha = digest(staged / "protocol.json")
        atomic_json(
            staged / "frozen.json", {"protocol_sha256": sha, "created_at": audit._utc()}
        )
        result = {
            "status": "prepared_not_qualified",
            "audit_root": str(output),
            "protocol_sha256": sha,
            **protocol,
        }
        try:
            _publish(staged, output)
        except _PublicationSyncError as error:
            result.update(
                status="published_durability_unconfirmed",
                sync_errno=error.errno,
                verification_action="verify-targeted",
            )
    return result


def verify(output: Path) -> dict:
    """Verify the published seal and panel without accessing a provider."""
    root = operator_path(output)
    protocol, sha = audit._sealed_protocol(root)
    audit._require(protocol.get("kind") == "targeted_regression", _INVALID)
    frozen_panel(root, protocol)
    return {
        "status": "verified_targeted",
        "audit_root": str(root),
        "protocol_sha256": sha,
    }


def frozen_panel(root: Path, protocol: dict) -> dict:
    audit._require(
        protocol["targeted_runner_sha256"] == digest(Path(__file__))
        and protocol["manual_review_required"] is True,
        "remote_audit_frozen_contract_changed",
    )
    panel = json.loads(audit._bytes(root, _PANEL_FILE, protocol["panel_sha256"]))
    reservations = _validate_panel(panel)
    planned = (
        judge._money(protocol["initial_accounted_usd"])
        + sum(reservations, Decimal(0))
        + max(reservations) * protocol["rate_limit"]["max_retries_per_audit"]
    )
    audit._require(
        len(reservations) == protocol["planned_requests"]
        and max(reservations) == judge._money(protocol["max_case_reservation_usd"])
        and planned == judge._money(protocol["planned_budget_usd"]),
        _INVALID,
    )
    return panel


def _differences(row: dict, case: dict) -> list[str]:
    differences = [
        field
        for field, value in case["expected"].items()
        if row["decision"][field] != value
    ]
    quote = case.get("required_unsupported_quote")
    if quote is not None:
        payload = json.loads(row["response"]["choices"][0]["message"]["content"])
        if not any(
            claim["grounding"] == "unsupported" and quote in claim["text"]
            for claim in payload["additional_claims"]
        ):
            differences.append("unsupported_quote")
    return differences


def _requests(panel: dict) -> list[tuple[dict, dict, dict, Decimal]]:
    repeats: Counter[str] = Counter()
    requests = []
    for label in panel["order"]:
        repeats[label] += 1
        body = panel["cases"][label]["body"]
        candidate = json.loads(body["messages"][1]["content"])["candidate"]
        entry = {"label": label, "repeat": repeats[label]}
        requests.append((entry, {"text": candidate}, body, judge.reserve(body)))
    return requests


def _recorded_prefix(state: audit._AuditState) -> list[dict]:
    requests = _requests(state.manifest)
    root = state.root
    paths = sorted((root / "receipts").glob("*.json"))
    audit._require(len(paths) <= len(requests), _INVALID)
    result_path = root / "result.json"
    if result_path.is_file():
        result = audit.read_json(result_path)
        audit._require(
            result["status"] in {"provider_unavailable", "provider_rate_limited"}
            and result["protocol_sha256"] == state.protocol_sha
            and result["receipt_hashes"] == audit._hashes(root),
            "remote_audit_resume_result_invalid",
        )
    ledger = audit.read_json(root / "ledger.json")
    audit._require(
        ledger["pending_call_id"] is None, "remote_audit_resume_pending_call"
    )
    recorded = []
    for index, path in enumerate(paths, 1):
        entry, answer, body, reservation = requests[index - 1]
        row = audit.read_json(path)
        audit._require(
            path.name == f"{index:03d}.json"
            and row["index"] == index
            and all(row[k] == v for k, v in entry.items())
            and row["protocol_sha256"] == state.protocol_sha
            and stable_hash(body)
            == row["request_sha256"]
            == stable_hash(row["request"])
            and row["response_sha256"] == stable_hash(row["response"])
            and judge._money(row["reserved_usd"]) == reservation,
            _INVALID,
        )
        if row["status"] == "completed":
            judge._verify_call(row, body, answer["text"], state.protocol_sha)
        elif row["status"] == "rejected_decision":
            judge._verify_rejected_call(row, body, answer["text"], state.protocol_sha)
        else:
            audit._require(
                index == len(paths)
                and row["status"] == "failed"
                and (row.get("http_status") == 429 or audit._provider_unavailable(row))
                and judge.reported_cost(row["response"]) == row.get("cost_usd"),
                "remote_audit_resume_transport_unverified",
            )
        recorded.append(row)
    audit._require(len({row["call_id"] for row in recorded}) == len(recorded), _INVALID)
    state.known, state.unknown = judge._audit_costs(
        [{**row, "cost_usd": row.get("cost_usd") or "0"} for row in recorded],
        state.protocol,
    )
    state.unknown += sum(
        (
            judge._money(row["reserved_usd"])
            for row in recorded
            if row["cost_usd"] is None
        ),
        Decimal(0),
    )
    audit._require(
        state.known == judge._money(ledger["actual_known_cost_usd"])
        and state.unknown == judge._money(ledger["unknown_reserved_usd"])
        and state.accounted == judge._money(ledger["accounted_usd"])
        and state.accounted <= state.budget,
        "remote_audit_resume_ledger_changed",
    )
    return recorded


def resume(state: audit._AuditState) -> dict:
    recorded = _recorded_prefix(state)
    started = audit.read_json(state.root / "started.json")
    audit._require(started["protocol_sha256"] == state.protocol_sha, _INVALID)
    elapsed = (
        judge._time(audit._utc()) - judge._time(started["created_at"])
    ).total_seconds()
    audit._require(
        0 <= elapsed < state.protocol["max_seconds"], "remote_audit_resume_deadline"
    )
    state.start = audit.time.monotonic() - elapsed
    state.rows = recorded
    state.retries = sum(len(judge._rate_limit_attempts(row)) for row in recorded)
    prior_attempts = []
    if recorded and recorded[-1]["status"] == "failed":
        tail = state.rows.pop()
        prior_attempts = [
            *judge._rate_limit_attempts(tail),
            {key: value for key, value in tail.items() if key != "rate_limit_attempts"},
        ]
        policy = state.protocol["rate_limit"]
        audit._require(
            len(prior_attempts) <= len(policy["backoff_seconds"])
            and state.retries < policy["max_retries_per_audit"]
            and sum(
                audit._provider_unavailable(row) and row["http_status"] == 200
                for row in prior_attempts
            )
            <= 1,
            "remote_audit_resume_retries_exhausted",
        )
    state.generations = {row["response"]["id"] for row in state.rows}
    audit._require(len(state.generations) == len(state.rows), _INVALID)
    result_path = state.root / "result.json"
    if result_path.is_file():
        history = state.root / "prior-results"
        history.mkdir(exist_ok=True)
        result_path.replace(history / f"{digest(result_path)}.json")
    return execute(state, prior_attempts=prior_attempts, resuming=True)


def execute(
    state: audit._AuditState,
    *,
    prior_attempts: list[dict] | None = None,
    resuming: bool = False,
) -> dict:
    """Run the sealed panel, optionally continuing a verified prefix."""
    if not resuming:
        state.start = audit.time.monotonic()
        (state.root / "receipts").mkdir()
    planned = judge._money(state.protocol["planned_budget_usd"])
    maximum = judge._money(state.protocol["max_case_reservation_usd"])
    if planned > state.budget or maximum > state.per_request:
        state.status = "budget_exhausted"
        return audit._audit_result(state)
    state.next_post_at = audit._provider_next_post_at(state.rate_path)
    requests = _requests(state.manifest)
    if prior_attempts:
        last = prior_attempts[-1]
        finished = judge._time(last["finished_at"])
        delay = judge._retry_wait_seconds(last, len(prior_attempts) - 1, finished)
        elapsed = (judge._time(audit._utc()) - finished).total_seconds()
        state.next_post_at = max(
            state.next_post_at, audit.time.monotonic() + delay - elapsed
        )
    elif state.rows:
        finished = judge._time(state.rows[-1]["finished_at"])
        elapsed = (judge._time(audit._utc()) - finished).total_seconds()
        interval = state.protocol["rate_limit"]["interval_seconds"]
        state.next_post_at = max(
            state.next_post_at, audit.time.monotonic() + interval - elapsed
        )
    if not audit._schedule_fits(state, len(requests) - len(state.rows)):
        state.status = "deadline_exceeded"
        return audit._audit_result(state)
    with ExitStack() as stack:
        for request in requests[len(state.rows) :]:
            status = audit._submit_case(
                state, request, stack, prior_attempts=prior_attempts
            )
            prior_attempts = None
            if status not in {"completed", "rejected_decision"}:
                break
        else:
            state.status = "targeted_review_required"
    cases = state.manifest["cases"]
    mismatches = []
    completed = 0
    for row in state.rows:
        if row["status"] == "rejected_decision":
            differences = [row["error_type"]]
        elif row["status"] == "completed":
            completed += 1
            differences = _differences(row, cases[row["label"]])
        else:
            continue
        if differences:
            mismatches.append(
                {
                    "index": row["index"],
                    "label": row["label"],
                    "differences": differences,
                }
            )
    if state.status == "targeted_review_required" and mismatches:
        state.status = "targeted_regression_failed"
    state.metrics = {
        "planned": len(requests),
        "completed": completed,
        "mismatches": mismatches,
        "manual_review_required": True,
    }
    return audit._audit_result(state)
