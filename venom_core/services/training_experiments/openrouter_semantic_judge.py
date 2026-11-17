"""Qualified OpenRouter field reviewer; no local model or GPU access.

Audit v3 is a separate protocol. Historical private v2 results cannot qualify it.
All verification/replay functions are offline. Real requests occur only in
review_bundle, after qualification, configuration and budget checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from pydantic import Field

from venom_core.config import SETTINGS
from venom_core.services import openrouter_runtime as runtime
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from . import local_semantic_judge as local
from . import semantic_judge_v4 as controls
from . import semantic_judge_v5 as fields
from .profiles import digest, read_json, stable_hash

JUDGE = "semantic-openrouter-luna-field-v3"
JUDGES = frozenset({JUDGE})
PROMPT = (
    fields.PROMPT
    + """

Doprecyzowanie kontraktu v3: odróżniaj potrzebę, zamówienie i stan wykonania.
Zdanie, że dostawa nie wymaga chłodzenia, nie dowodzi, że chłodzenia nie zamówiono.
Jeżeli kryterium wymaga zakomunikowania braku danych w źródle, a kandydat zamiast
tego podaje definitywną wartość, relation=omitted (nie zakomunikował braku),
a tę konkretną nieudowodnioną wartość zapisz w additional_claims jako unsupported.
Nie stwierdzaj, że nieznana wartość jest faktycznie fałszywa. Gdy źródło jawnie
mówi, że nie zamówiono chłodzenia, odpowiedź, że je zamówiono, jest contradicted.
Parafraza osoby jest dopuszczalna, gdy zachowuje rolę podaną jawnie w materiale.
Sama lokalizacja odbioru nie dowodzi, że właściciel miejsca osobiście wydaje rzeczy.
"""
)
MODEL = "openai/gpt-6-luna"
PROVIDER = "Azure"
ROUTE = "azure"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OUTPUT = 900
INPUT_PRICE = Decimal("0.10")
OUTPUT_PRICE = Decimal("0.50")
PHASE1 = {"legacy": 60, "development": 48, "extra": 32, "contrasts": 16}
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ERROR = "experiment_remote_judge_invalid"
DECISION_FIELDS = controls.DECISION_FIELDS


class QualificationRemote(local._Strict):
    schema_version: Literal[1]
    judge: Literal["semantic-openrouter-luna-field-v3"]
    audit_root: str = Field(min_length=1)
    model: Literal["openai/gpt-6-luna"]
    provider: Literal["Azure"]
    endpoint: Literal["https://openrouter.ai/api/v1/chat/completions"]
    protocol_sha256: Digest
    result_sha256: Digest
    controls_manifest_sha256: Digest
    prompt_sha256: Digest
    request_contract_sha256: Digest
    implementation_sha256: Digest


def _require(value: bool) -> None:
    if not value:
        raise ValueError(ERROR)


def _money(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("experiment_remote_judge_cost_invalid")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("experiment_remote_judge_cost_invalid") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("experiment_remote_judge_cost_invalid")
    return result


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError(ERROR)
    result = datetime.fromisoformat(value)
    _require(result.tzinfo is not None)
    return result


def _root(path: str) -> Path:
    result = operator_path(Path(path))
    _require(result.is_absolute())
    return result


def _bound(root: Path, name: str, sha: str) -> dict:
    # All callers supply fixed names, never paths from result/HTTP data.
    path = root / name
    _require(digest(path) == sha)
    value = read_json(path)
    _require(isinstance(value, dict) and digest(path) == sha)
    return value


def _contract() -> dict:
    return {
        "judge": JUDGE,
        "model": MODEL,
        "provider": PROVIDER,
        "endpoint": ENDPOINT,
        "route": ROUTE,
        "max_completion_tokens": OUTPUT,
        "reasoning": {"effort": "low", "exclude": True},
        "input_per_m_usd": str(INPUT_PRICE),
        "output_per_m_usd": str(OUTPUT_PRICE),
        "zdr_required": False,
        "automatic_retry": False,
        "response_format": "strict_field_schema",
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    }


def implementation_identity() -> str:
    directory = Path(__file__).parent
    paths = [
        directory / name
        for name in (
            "openrouter_semantic_judge.py",
            "semantic_judge_v5.py",
            "local_semantic_judge.py",
            "semantic_judge_v4.py",
            "semantic_judge_controls.py",
            "profiles.py",
            "grounded_claims.py",
        )
    ]
    paths.append(directory.parents[2] / "scripts/academy/omni_pl_chat_dialogue.py")
    return stable_hash({path.name: digest(path) for path in paths})


def reported_cost(body: dict) -> str | None:
    # Keep calibration -> dispatch imports independent of ExperimentService.
    from .dialogue_judge import reported_cost as cost

    return cost(body)


def claim_rubric(spec: dict) -> dict:
    return local.claim_rubric(spec)


def request_payload(spec: dict, case: dict, answer: dict) -> dict:
    _require(
        answer.get("finish") == "stop"
        and answer.get("error") is None
        and isinstance(answer.get("text"), str)
    )
    material = local._material(spec, case, answer)
    _require(len(json.dumps(material, ensure_ascii=False).encode()) <= 16_000)
    ids = [item["id"] for item in material["criteria"]]
    _require(bool(ids) and len(ids) == len(set(ids)))
    body = fields.request(MODEL, material, ids)
    body["messages"][0]["content"] = PROMPT
    return {
        "model": MODEL,
        "messages": body["messages"],
        "max_completion_tokens": OUTPUT,
        "reasoning": {"effort": "low", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "factual_field_review",
                "strict": True,
                "schema": body["format"],
            },
        },
        "provider": {
            "only": [ROUTE],
            "allow_fallbacks": False,
            "require_parameters": True,
            "max_price": {
                "prompt": float(INPUT_PRICE),
                "completion": float(OUTPUT_PRICE),
                "request": 0,
            },
        },
    }


def _control_request(case: dict, answer: dict) -> dict:
    # Audit cases have no runtime wrapper; use the same material/prompt/schema.
    normalized = {
        **case,
        "criteria": [{**c, "kind": "content"} for c in case["criteria"]],
    }
    normalized["record_id"] = case["id"]
    return request_payload(
        {"evidence": case.get("evidence", [])},
        normalized,
        {"text": answer["text"], "finish": "stop", "error": None},
    )


def reserve(body: dict) -> Decimal:
    tokens = sum(len(item["content"].encode()) + 128 for item in body["messages"])
    tokens += len(json.dumps(body["response_format"]).encode()) + 1024
    return (INPUT_PRICE * tokens + OUTPUT_PRICE * OUTPUT) / Decimal(1_000_000)


def decode(response: dict, body: dict, candidate: str) -> local._Decision:
    _require(response.get("model") == MODEL and response.get("provider") == PROVIDER)
    _require(isinstance(response.get("id"), str) and bool(response["id"].strip()))
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError(ERROR)
    choice = choices[0]
    _require(choice.get("finish_reason") == "stop")
    content = choice.get("message", {}).get("content")
    _require(isinstance(content, str))
    ids = list(
        body["response_format"]["json_schema"]["schema"]["properties"]["checks"][
            "properties"
        ]
    )
    result = fields.decode(
        {
            "model": MODEL,
            "done": True,
            "done_reason": "stop",
            "message": {"content": content},
        },
        ids,
        MODEL,
        candidate=candidate,
    )
    _require(result is not None)
    assert result is not None
    return result


def _jobs(root: Path, manifest: dict, split: str) -> tuple[dict, dict]:
    if split == "contrasts":
        from .semantic_judge_controls import jobs_for_contrasts

        return jobs_for_contrasts(root, manifest)
    return controls.jobs_for(root, manifest, split)


def _audit_order(root: Path, manifest: dict) -> list[dict]:
    entry = "phase1-order.json"
    order = _bound(root / "controls", entry, manifest["files"][entry])["jobs"]
    expected = {
        (split, ident) for split in PHASE1 for ident in _jobs(root, manifest, split)[0]
    }
    _require(len(order) == 156 and len(expected) == 156)
    _require(Counter(row["split"] for row in order) == PHASE1)
    _require(
        all(type(row.get("repeat")) is int and row["repeat"] == 1 for row in order)
    )
    _require({(row["split"], row["answer_id"]) for row in order} == expected)
    held, _ = _jobs(root, manifest, "holdout")
    _require(len(held) == 24)
    return order + [
        {"split": "holdout", "answer_id": ident, "repeat": repeat}
        for repeat in (1, 2, 3)
        for ident in held
    ]


def _audit_metrics(root: Path, manifest: dict, rows: list[dict]) -> dict:
    decisions: dict[str, dict] = {split: {} for split in (*PHASE1, "holdout")}
    for row in rows:
        decisions[row["split"]].setdefault(row["answer_id"], []).append(
            local._Decision.model_validate(row["decision"])
        )
    _, gold = _jobs(root, manifest, "legacy")
    actual = {key: arr[0] for key, arr in decisions["legacy"].items()}
    positives = set(gold["accepted"])
    accepted = {key for key, decision in actual.items() if local._supported(decision)}
    styles = local._style_checks(gold, positives, set(gold["rejected"]))
    metrics = {
        "legacy_positive": len(accepted & positives),
        "legacy_negative": len(set(gold["rejected"]) - accepted),
        "legacy_style": sum(
            (actual[key].polish_ok, actual[key].natural_ok) == expected
            for key, expected in styles.items()
        ),
        "legacy_semantics": sum(
            local._semantic_check(actual[key], expected)
            for key, expected in gold["expected_semantics"].items()
        ),
    }
    for split in ("development", "extra", "contrasts", "holdout"):
        _, gold = _jobs(root, manifest, split)
        metrics[split + "_full"] = sum(
            {key: getattr(decision, key) for key in DECISION_FIELDS}
            == gold["answers"][ident]["decision"]
            for ident, arr in decisions[split].items()
            for decision in arr
        )
    metrics["holdout_stable_groups"] = sum(
        len(arr) == 3
        and all(
            {k: getattr(d, k) for k in DECISION_FIELDS}
            == {k: getattr(arr[0], k) for k in DECISION_FIELDS}
            for d in arr
        )
        for arr in decisions["holdout"].values()
    )
    return metrics


def _verify_call(
    row: dict, body: dict, candidate: str, protocol_sha: str
) -> local._Decision:
    _require(
        row.get("status") == "completed" and row.get("protocol_sha256") == protocol_sha
    )
    _require(
        row.get("request") == body and row.get("request_sha256") == stable_hash(body)
    )
    response = row.get("response")
    _require(
        isinstance(response, dict)
        and row.get("response_sha256") == stable_hash(response)
    )
    assert isinstance(response, dict)
    result = decode(response, body, candidate)
    _require(row.get("decision") == result.model_dump())
    cost = reported_cost(response)
    _require(cost is not None and row.get("cost_usd") == cost)
    _money(cost)
    _require(_money(row["reserved_usd"]) == reserve(body))
    _require(_time(row["started_at"]) <= _time(row["finished_at"]))
    return result


def verify_audit(pin: QualificationRemote) -> None:
    root = _root(pin.audit_root)
    protocol = _bound(root, "protocol.json", pin.protocol_sha256)
    result = _bound(root, "result.json", pin.result_sha256)
    manifest = _bound(
        root / "controls", "frozen-manifest.json", pin.controls_manifest_sha256
    )
    expected_thresholds = {
        "legacy_positive": 24,
        "legacy_negative": 36,
        "legacy_style": 24,
        "legacy_semantics": 6,
        "development_full": 48,
        "extra_full": 32,
        "contrasts_full": 16,
        "holdout_full": 72,
        "holdout_stable_groups": 24,
    }
    _require(
        manifest.get("control_version") == "luna-controls-v3"
        and manifest.get("status") == "frozen_before_any_inference"
        and manifest.get("thresholds") == expected_thresholds
    )
    _require(
        protocol.get("judge") == JUDGE
        and protocol.get("request_contract") == _contract()
    )
    _require(protocol.get("controls_manifest_sha256") == pin.controls_manifest_sha256)
    _require(
        pin.prompt_sha256 == _contract()["prompt_sha256"]
        and pin.request_contract_sha256 == stable_hash(_contract())
        and pin.implementation_sha256 == implementation_identity()
    )
    _require(protocol.get("implementation_sha256") == pin.implementation_sha256)
    _require(
        result.get("status") == "passed"
        and result.get("protocol_sha256") == pin.protocol_sha256
    )
    review = _bound(root, "data-review.json", protocol["data_review_sha256"])
    _require(
        review.get("status") == "passed"
        and review.get("controls_manifest_sha256") == pin.controls_manifest_sha256
        and isinstance(review.get("reviewer"), str)
        and bool(review["reviewer"].strip())
    )
    # The held-out bytes are only needed when replaying an already completed PASS.
    held = manifest["holdout"]
    for name in ("panel.json", "gold.json"):
        _require(digest(root / "controls" / "holdout" / name) == held["files"][name])
    verified_manifest = {
        **manifest,
        "files": {
            **manifest["files"],
            **{"holdout/" + name: sha for name, sha in held["files"].items()},
        },
    }
    order = _audit_order(root, verified_manifest)
    hashes = result["receipt_hashes"]
    _require(set(hashes) == {f"{i:03d}.json" for i in range(1, 229)})
    rows = []
    seen_calls: set[str] = set()
    seen_generations: set[str] = set()
    previous_end = _time(review["created_at"])
    for index, expected in enumerate(order, 1):
        row = _bound(
            root / "receipts", f"{index:03d}.json", hashes[f"{index:03d}.json"]
        )
        _require(type(row.get("index")) is int and row["index"] == index)
        _require(all(row.get(k) == v for k, v in expected.items()))
        _require(
            isinstance(row.get("call_id"), str) and row["call_id"] not in seen_calls
        )
        _require(_time(row["started_at"]) >= previous_end)
        previous_end = _time(row["finished_at"])
        case, answer = _jobs(root, verified_manifest, row["split"])[0][row["answer_id"]]
        _verify_call(
            row, _control_request(case, answer), answer["text"], pin.protocol_sha256
        )
        generation = row["response"]["id"]
        _require(generation not in seen_generations)
        seen_generations.add(generation)
        seen_calls.add(row["call_id"])
        rows.append(row)
    metrics = _audit_metrics(root, verified_manifest, rows)
    _require(metrics == expected_thresholds and result.get("metrics") == metrics)
    phase1 = _bound(root, "phase1-result.json", result["phase1_result_sha256"])
    _require(phase1.get("status") == "passed" and phase1.get("rows") == 156)
    _require(
        phase1.get("receipt_hashes")
        == {k: v for k, v in hashes.items() if int(k[:3]) <= 156}
    )
    _require(
        _time(rows[155]["finished_at"])
        <= _time(phase1["finished_at"])
        <= _time(rows[156]["started_at"])
    )
    total = sum((_money(row["cost_usd"]) for row in rows), Decimal(0))
    _require(_money(result["actual_known_cost_usd"]) == total)
    _require(_money(result["accounted_usd"]) >= total)


def qualification(calibration: dict) -> QualificationRemote:
    _require(calibration.get("judge") == JUDGE)
    pin = QualificationRemote.model_validate(calibration.get("judge_qualification"))
    verify_audit(pin)
    return pin


def scorer_protocol(calibration: dict) -> str:
    pin = qualification(calibration)
    return JUDGE + ":" + stable_hash(pin.model_dump())


def preflight(calibration: dict) -> None:
    qualification(calibration)
    _review_settings(calibration)
    if (
        not runtime.is_enabled()
        or not runtime.cloud_allowed()
        or not runtime.credential()
    ):
        raise ValueError("experiment_remote_judge_unavailable")


def _review_settings(calibration: dict) -> tuple[Path, Decimal, Decimal]:
    config = calibration.get("remote_review", {})
    _require(set(config) == {"ledger_root", "budget_usd", "max_request_usd"})
    root = _root(config["ledger_root"])
    budget = min(
        _money(config["budget_usd"]), Decimal(str(SETTINGS.OPENROUTER_DAILY_LIMIT_USD))
    )
    per_request = min(
        _money(config["max_request_usd"]),
        Decimal(str(SETTINGS.OPENROUTER_MESSAGE_LIMIT_USD)),
    )
    _require(budget > 0 and per_request > 0 and per_request <= budget)
    return root, budget, per_request


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_review_receipt(
    pin: QualificationRemote, spec: dict, case: dict, answer: dict, grade: dict
) -> None:
    body = request_payload(spec, case, answer)
    raw = grade.get("model_review_call")
    if not isinstance(raw, dict):
        raise ValueError(ERROR)
    # Validate before constructing a path or opening any receipt.
    _require(
        len(raw["receipt_name"]) == 37
        and raw["receipt_name"].endswith(".json")
        and all(c in "0123456789abcdef" for c in raw["receipt_name"][:-5])
    )
    row = _bound(
        _root(raw["ledger_root"]) / "receipts",
        raw["receipt_name"],
        raw["receipt_sha256"],
    )
    _require(row.get("qualification_sha256") == stable_hash(pin.model_dump()))
    decision = _verify_call(row, body, answer["text"], pin.protocol_sha256)
    expected = local._grade(decision, claim_rubric(spec), case, answer, judge=JUDGE)
    _require(all(grade.get(key) == value for key, value in expected.items()))


def review_bundle(
    calibration: dict,
    bundle: dict,
    run_id: str,
    seconds: float,
    *,
    check: Callable[[], None] = lambda: None,
) -> list[dict]:
    """One fail-fast run; persist reservations before POST, never retry."""
    pin = qualification(calibration)
    root, budget, per_request = _review_settings(calibration)
    _require(math.isfinite(seconds) and seconds > 0)
    if (
        not runtime.is_enabled()
        or not runtime.cloud_allowed()
        or not runtime.credential()
    ):
        raise ValueError("experiment_remote_judge_unavailable")
    cases = {c["record_id"]: c for c in bundle["cases"]}
    plan = [
        (row["case"]["record_id"], label, answer)
        for row in bundle["answers"]
        for label, answer in row["answers"].items()
    ]
    _require(len({(ident, label) for ident, label, _ in plan}) == len(plan))
    root.mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(exist_ok=True)
    deadline = time.monotonic() + seconds
    identity = stable_hash(pin.model_dump())
    observations = []
    with file_lock(root / "ledger.lock", blocking=False):
        ledger_path = root / "ledger.json"
        ledger = (
            read_json(ledger_path)
            if ledger_path.exists()
            else {
                "qualification_sha256": identity,
                "accounted_usd": read_json(_root(pin.audit_root) / "result.json")[
                    "accounted_usd"
                ],
                "receipts": {},
            }
        )
        _require(ledger["qualification_sha256"] == identity)
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + runtime.credential()},
        ) as client:
            for ident, label, answer in plan:
                check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("experiment_judge_time_limit")
                spec, case = calibration["cases"][ident], cases[ident]
                body = request_payload(spec, case, answer)
                reservation = reserve(body)
                accounted = _money(ledger["accounted_usd"])
                if reservation > per_request or accounted + reservation > budget:
                    raise ValueError("experiment_remote_judge_budget_exhausted")
                call_id = uuid4().hex
                row = {
                    "status": "attempted",
                    "run_id": run_id,
                    "call_id": call_id,
                    "record_id": ident,
                    "label": label,
                    "qualification_sha256": identity,
                    "protocol_sha256": pin.protocol_sha256,
                    "request": body,
                    "request_sha256": stable_hash(body),
                    "reserved_usd": str(reservation),
                    "started_at": _utc(),
                    "response": {},
                    "cost_usd": None,
                }
                path = root / "receipts" / (call_id + ".json")
                atomic_json(path, row)
                ledger["accounted_usd"] = str(accounted + reservation)
                ledger["receipts"][path.name] = digest(path)
                atomic_json(ledger_path, ledger)
                try:
                    response = client.post(
                        ENDPOINT, json=body, timeout=min(75.0, remaining)
                    )
                    response.raise_for_status()
                    raw = response.json()
                    _require(isinstance(raw, dict))
                    row["response"] = raw
                    row["cost_usd"] = reported_cost(raw)
                    decision = decode(raw, body, answer["text"])
                    _require(row["cost_usd"] is not None)
                    row["decision"] = decision.model_dump()
                    row["status"] = "completed"
                finally:
                    row["finished_at"] = _utc()
                    row["response_sha256"] = stable_hash(row["response"])
                    if row["cost_usd"] is not None:
                        ledger["accounted_usd"] = str(
                            accounted + _money(row["cost_usd"])
                        )
                    atomic_json(path, row)
                    ledger["receipts"][path.name] = digest(path)
                    atomic_json(ledger_path, ledger)
                if time.monotonic() > deadline:
                    raise TimeoutError("experiment_judge_time_limit")
                observations.append(
                    {
                        **local._grade(
                            decision, claim_rubric(spec), case, answer, judge=JUDGE
                        ),
                        "record_id": ident,
                        "label": label,
                        "model_review_call": {
                            "ledger_root": str(root),
                            "receipt_name": path.name,
                            "receipt_sha256": digest(path),
                        },
                    }
                )
    return observations
