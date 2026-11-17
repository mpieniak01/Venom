"""v4 requires every raw call and repeated decision; v3 pins remain unchanged."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.training_experiments import local_semantic_judge as judge
from venom_core.services.training_experiments import semantic_judge_audit as runner
from venom_core.services.training_experiments import semantic_judge_v4 as audit
from venom_core.services.training_experiments.calibration import scorer_protocol
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    stable_hash,
)


def _v6_example():
    from venom_core.services.training_experiments import semantic_judge_v6 as v6

    material = {
        "messages": [{"role": "user", "content": "Miejsce: taca A. Podaj miejsce."}],
        "criteria": [{"id": "location", "description": "Miejsce to taca A."}],
        "evidence": [{"ref": "old", "text": "Nieaktualne", "current": False}],
        "candidate": "Nie z tacy A.",
    }
    request = judge._request("judge", material, ["location"], judge=judge.JUDGE_V6)
    primary = {
        "checks": {
            "location": {
                "required": "taca A",
                "observed": "taca A",
                "relation": "supported",
            }
        },
        "additional_claims": [],
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "fixture",
    }
    guard = {
        "checks": {
            "location": {
                "source_refs": [{"ref": "U0", "quote": "Miejsce: taca A."}],
                "candidate_quotes": ["Nie z tacy A."],
                "relation": "denies",
            }
        },
        "source_instruction_quotes": [],
        "candidate_instruction_quotes": [],
        "instruction_effect": "absent",
        "reason": "Zanegowano miejsce.",
    }
    assert v6.sources(material) == {"U0": material["messages"][0]["content"]}
    return request, primary, guard


def _v6_response(request, primary, guard):
    import time
    import uuid

    stamp = time.time_ns()
    return {
        "protocol": judge.JUDGE_V6,
        "status": "complete",
        "calls": [
            {
                "call_id": uuid.uuid4().hex,
                "started_at_ns": stamp,
                "finished_at_ns": stamp + 1,
                "started_monotonic_ns": index * 2 + 1,
                "finished_monotonic_ns": index * 2 + 2,
                "request": stage,
                "request_sha256": stable_hash(stage),
                "response": {
                    "model": "judge",
                    "done": True,
                    "done_reason": "stop",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "message": {"content": json.dumps(value)},
                },
            }
            for index, (stage, value) in enumerate(
                zip(request["stages"], (primary, guard), strict=True)
            )
        ],
    }


@pytest.mark.parametrize(
    "relation,expected",
    [
        ("denies", "contradicted"),
        ("entails", "supported"),
        ("absent", "unclear"),
        ("unclear", "unclear"),
    ],
)
def test_v6_polarity_veto_and_other_conflicts_abstain(relation, expected):
    request, primary, guard = _v6_example()
    guard["checks"]["location"]["relation"] = relation
    if relation == "absent":
        guard["checks"]["location"]["candidate_quotes"] = []
    response = _v6_response(request, primary, guard)
    result = judge._decode(
        response, ["location"], "judge", judge=judge.JUDGE_V6, request=request
    )
    assert result.atoms == {"location": expected}
    assert (result.unsupported == "yes") == (relation == "denies")
    assert judge._decode(response, ["location"], "judge", judge=judge.JUDGE_V6) is None


@pytest.mark.parametrize(
    "damage",
    [
        "wrong_source",
        "old_source",
        "wrong_quote",
        "blank_quote",
        "missing_quote",
        "missing_source",
        "different_request",
        "missing_stage",
        "thinking",
        "wrong_model",
        "invalid_json",
        "extra_atom",
        "cut_polarity",
    ],
)
def test_v6_invalid_guard_evidence_fails_closed(damage):
    request, primary, guard = _v6_example()
    check = guard["checks"]["location"]
    if damage == "wrong_source":
        check["source_refs"][0]["ref"] = "C0"
    elif damage == "old_source":
        check["source_refs"][0] = {"ref": "E0", "quote": "Nieaktualne"}
    elif damage == "wrong_quote":
        check["candidate_quotes"] = ["z tacy B"]
    elif damage == "blank_quote":
        check["candidate_quotes"] = [" \t"]
    elif damage == "missing_quote":
        check["candidate_quotes"] = []
    elif damage == "missing_source":
        check["source_refs"] = []
    elif damage == "extra_atom":
        guard["checks"]["other"] = check
    elif damage == "cut_polarity":
        check["candidate_quotes"] = ["tacy A"]
    response = _v6_response(request, primary, guard)
    if damage == "different_request":
        response["calls"][1]["request_sha256"] = "f" * 64
    elif damage == "missing_stage":
        response["calls"].pop()
    elif damage == "thinking":
        response["calls"][1]["response"]["message"]["thinking"] = "forbidden"
    elif damage == "wrong_model":
        response["calls"][1]["response"]["model"] = "other"
    elif damage == "invalid_json":
        response["calls"][1]["response"]["message"]["content"] = "invalid"
    assert (
        judge._decode(
            response, ["location"], "judge", judge=judge.JUDGE_V6, request=request
        )
        is None
    )


@pytest.mark.parametrize(
    "effect,primary_injection,expected",
    [
        ("executed", False, True),
        ("ignored", False, False),
        ("absent", False, False),
        ("ignored", True, True),
        ("unclear", False, False),
    ],
)
def test_v6_instruction_control_is_separate_from_fact_and_style(
    effect, primary_injection, expected
):
    request, primary, guard = _v6_example()
    primary["injection"] = primary_injection
    primary["polish_ok"] = False
    guard["instruction_effect"] = effect
    if effect in {"executed", "ignored"}:
        guard["source_instruction_quotes"] = [{"ref": "C0", "quote": "Nie z tacy A."}]
    if effect == "executed":
        guard["candidate_instruction_quotes"] = ["Nie z tacy A."]
    result = judge._decode(
        _v6_response(request, primary, guard),
        ["location"],
        "judge",
        judge=judge.JUDGE_V6,
        request=request,
    )
    assert result.injection is expected
    assert result.polish_ok is False
    guard["source_instruction_quotes"] = [{"ref": "U99", "quote": "Missing"}]
    assert (
        judge._decode(
            _v6_response(request, primary, guard),
            ["location"],
            "judge",
            judge=judge.JUDGE_V6,
            request=request,
        )
        is None
    )


def decision(positive=True, *, omitted=False):
    return {
        "atoms": {
            "fact": "supported"
            if positive
            else "omitted"
            if omitted
            else "contradicted"
        },
        "unsupported": "no" if positive or omitted else "yes",
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "fixture evidence",
    }


def _legacy():
    cases, accepted, rejected, styles, semantics, answers = [], [], [], {}, {}, {}
    for family in range(12):
        case = {
            "id": f"L{family}",
            "messages": [],
            "criteria": [{"description": "A fact", "id": "fact"}],
            "answers": [],
        }
        count = 5 if family < 6 else 4 if family < 9 else 6
        for index in range(count):
            ident = f"L{family}-{index}"
            case["answers"].append({"id": ident, "text": ident})
            positive = index < 2
            (accepted if positive else rejected).append(ident)
            value = decision(positive)
            contrast = 2 if family < 9 else 4
            value["polish_ok"] = index != contrast or family < 6
            value["natural_ok"] = index != contrast + 1 or family < 6
            if family >= 6 and (positive or index in {contrast, contrast + 1}):
                styles[ident] = {key: value[key] for key in ("polish_ok", "natural_ok")}
            if family >= 9 and index == 2:
                semantics[ident] = {
                    "atoms": {"fact": "contradicted"},
                    "unsupported": "yes",
                    "injection": False,
                }
            if family >= 9 and index == 3:
                value["injection"] = True
                semantics[ident] = {"injection": True}
            answers[ident] = value
        cases.append(case)
    return (
        {"cases": cases},
        {
            "accepted": accepted,
            "rejected": {
                ident: {"critical": True, "failure": "wrong_fact"} for ident in rejected
            },
            "expected_style": styles,
            "expected_semantics": semantics,
            "challenge_cases": [c["id"] for c in cases[-3:]],
        },
        answers,
    )


def _new(split, families):
    cases, gold, answers = [], {}, {}
    for family in range(families):
        case = {
            "id": f"{split}{family}",
            "messages": [],
            "criteria": [{"description": "A fact", "id": "fact", "kind": "content"}],
            "answers": [],
        }
        for index in range(4):
            ident = f"{split}{family}-{index}"
            case["answers"].append({"id": ident, "text": ident})
            value = decision(index < 2, omitted=index == 3)
            answers[ident] = value
            gold[ident] = {
                "case_id": case["id"],
                "expected": "positive" if index < 2 else "negative",
                "decision": {k: value[k] for k in audit.DECISION_FIELDS},
            }
        cases.append(case)
    return {"cases": cases}, {"answers": gold}, answers


@pytest.fixture
def qualified_v4(tmp_path, monkeypatch):
    root = tmp_path / "v4"
    (root / "controls").mkdir(parents=True)
    (root / "judge-calls").mkdir()
    monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT", str(root))
    all_jobs, gold_decisions = {}, {}
    for split, factory in (
        ("legacy", _legacy),
        ("development", lambda: _new("D", 12)),
        ("holdout", lambda: _new("H", 6)),
    ):
        panel, gold, values = factory()
        (root / "controls" / split).mkdir()
        suffix = "qualification-" if split == "legacy" else ""
        for name, value in (("panel", panel), ("gold", gold)):
            atomic_json(root / "controls" / split / f"{suffix}{name}.json", value)
        for case in panel["cases"]:
            for answer in case["answers"]:
                all_jobs[split, answer["id"]] = case, answer
                gold_decisions[split, answer["id"]] = values[answer["id"]]
    first = [
        {"split": split, "case_id": case["id"], "answer_id": ident, "repeat": 1}
        for (split, ident), (case, _) in all_jobs.items()
        if split != "holdout"
    ]
    hold = [
        {"split": split, "case_id": case["id"], "answer_id": ident, "repeat": repeat}
        for repeat in (1, 2, 3)
        for (split, ident), (case, _) in all_jobs.items()
        if split == "holdout"
    ]
    atomic_json(
        root / "controls/execution-order.json",
        {"phase1_legacy_and_development": first, "phase2_holdout_stability": hold},
    )
    atomic_json(root / "controls/options.json", judge.OPTIONS)
    (root / "controls/prompt-proposal.txt").write_text(judge.PROMPT_V4 + "\n")
    for name in audit.FILES:
        path = root / "controls" / name
        if not path.exists():
            atomic_json(path, {})
    legacy = root / "controls/legacy"
    old_protocol = {
        "system": judge.PROMPT,
        "options": judge.OPTIONS,
        "model": "test-judge",
        "model_sha256": "d" * 64,
        "ollama": {"version": "0.40.14"},
        "gold_sha256": digest(legacy / "qualification-gold.json"),
        "panel_sha256": digest(legacy / "qualification-panel.json"),
        "manifest_sha256": digest(legacy / "qualification-manifest.json"),
    }
    atomic_json(legacy / "judge-protocol.json", old_protocol)
    atomic_json(
        legacy / "judge-result.json",
        {"protocol_sha256": digest(legacy / "judge-protocol.json")},
    )
    old_pin = {
        "schema_version": 1,
        "model": "test-judge",
        "model_sha256": "d" * 64,
        "ollama_version": "0.40.14",
        "prompt_sha256": judge.PROMPT_SHA256,
        "protocol_sha256": digest(legacy / "judge-protocol.json"),
        "gold_sha256": digest(legacy / "qualification-gold.json"),
        "result_sha256": digest(legacy / "judge-result.json"),
        "true_positives": 24,
        "positive_total": 24,
        "false_positives": 0,
        "negative_total": 36,
        "families_covered": 12,
        "families_total": 12,
    }
    atomic_json(legacy / "judge-qualification-receipt.json", old_pin)
    atomic_json(
        root / "controls/frozen-manifest.json",
        {
            "status": "frozen_before_any_inference",
            "files": {name: digest(root / "controls" / name) for name in audit.FILES},
        },
    )
    receipt = {
        **old_pin,
        "schema_version": 2,
        "prompt_sha256": judge.PROMPT_V4_SHA256,
        "accuracy_manifest_sha256": digest(root / "controls/frozen-manifest.json"),
    }
    intent = {
        "run_id": "fixture-v4",
        "manifest_sha256": receipt["accuracy_manifest_sha256"],
        "seconds": 300,
        "cleanup_seconds": 120,
        "implementation_sha256": audit.implementation_hashes(),
    }
    atomic_json(root / "intent.json", intent)
    protocol = {
        "schema_version": 4,
        "judge": judge.JUDGE_V4,
        "system": judge.PROMPT_V4,
        "options": judge.OPTIONS,
        "model": receipt["model"],
        "model_sha256": receipt["model_sha256"],
        "ollama": {"version": receipt["ollama_version"]},
        "accuracy_manifest_sha256": receipt["accuracy_manifest_sha256"],
        "implementation_sha256": audit.implementation_hashes(),
        "run_id": intent["run_id"],
        "intent_sha256": digest(root / "intent.json"),
    }
    atomic_json(root / "judge-protocol.json", protocol)
    receipt["protocol_sha256"] = digest(root / "judge-protocol.json")
    scope = {
        "run_id": intent["run_id"],
        "intent_sha256": protocol["intent_sha256"],
        "protocol_sha256": receipt["protocol_sha256"],
    }
    wall, mono = 1800000000000000000, 1000000
    atomic_json(
        root / "started.json",
        {**scope, "started_at_ns": wall, "started_monotonic_ns": mono},
    )
    reviews = []
    for index, entry in enumerate(first + hold, 1):
        key = entry["split"], entry["answer_id"]
        case, answer = all_jobs[key]
        request = audit.request_for(receipt["model"], case, answer)
        value = gold_decisions[key]
        start_wall, start_mono = wall + index * 1000000, mono + index * 1000000
        response = {
            "model": receipt["model"],
            "done": True,
            "done_reason": "stop",
            "created_at": datetime.fromtimestamp(
                start_wall / 1e9, timezone.utc
            ).isoformat(),
            "message": {"content": json.dumps(value)},
        }
        path = root / "judge-calls" / f"{index:03d}.json"
        atomic_json(
            path,
            {
                **scope,
                "call_id": f"{index:032x}",
                "started_at_ns": start_wall,
                "finished_at_ns": start_wall + 1000,
                "started_monotonic_ns": start_mono,
                "finished_monotonic_ns": start_mono + 1000,
                "request": request,
                "request_sha256": stable_hash(request),
                "response": response,
            },
        )
        reviews.append(
            {
                **entry,
                "index": index,
                "request_sha256": stable_hash(request),
                "decision": value,
                "call_sha256": digest(path),
            }
        )
    atomic_json(
        root / "phase1-pass.json",
        {
            **scope,
            "completed_calls": 108,
            "phase1_rows_sha256": stable_hash(reviews[:108]),
            "closed_at_ns": wall + 108 * 1000000 + 2000,
            "closed_monotonic_ns": mono + 108 * 1000000 + 2000,
        },
    )
    atomic_json(
        root / "judge-result.json",
        {
            **scope,
            "status": "complete",
            "rows": reviews,
            "holdout_opened": True,
            "completed_calls": 180,
            "started_sha256": digest(root / "started.json"),
            "phase1_marker_sha256": digest(root / "phase1-pass.json"),
            "finished_monotonic_ns": mono + 181 * 1000000,
            "finished_at_ns": wall + 181 * 1000000,
            "metrics": {
                "legacy_correct": 60,
                "development_correct": 48,
                "holdout_correct": 72,
                "stable_groups": 24,
            },
        },
    )
    receipt["result_sha256"] = digest(root / "judge-result.json")
    return {"judge": judge.JUDGE_V4, "judge_qualification": receipt}, root


def _reseal_result(settings, root, result):
    atomic_json(root / "judge-result.json", result)
    settings["judge_qualification"]["result_sha256"] = digest(
        root / "judge-result.json"
    )


def test_complete_v4_audit_and_versioned_protocol(qualified_v4):
    settings, root = qualified_v4
    pin = judge.qualification(settings)
    assert isinstance(pin, judge.QualificationV4)
    assert pin.true_positives == 24
    assert scorer_protocol({**settings, "schema_version": 1}).startswith(
        "semantic-local-v4:"
    )
    assert (
        audit.verify_rows(
            root,
            audit.control_files(root, pin.accuracy_manifest_sha256),
            pin,
            read_json(root / "judge-result.json")["rows"],
        )["stable_groups"]
        == 24
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "swapped",
        "incomplete",
        "metrics",
        "request",
        "request_sha",
        "row_decision",
        "raw_decision",
        "unclear",
        "missing_call",
    ],
)
def test_resealed_incomplete_or_tampered_audit_refuses(qualified_v4, damage):
    settings, root = qualified_v4
    result = read_json(root / "judge-result.json")
    if damage == "missing":
        result["rows"].pop()
    elif damage == "duplicate":
        result["rows"][-1] = result["rows"][-2]
    elif damage == "swapped":
        result["rows"][0], result["rows"][1] = result["rows"][1], result["rows"][0]
    elif damage == "incomplete":
        result["status"] = "incomplete"
    elif damage == "metrics":
        result["metrics"]["holdout_correct"] = 71
    else:
        row = result["rows"][-1]
        path = root / "judge-calls" / "180.json"
        call = read_json(path)
        if damage == "missing_call":
            path.unlink()
        elif damage == "request":
            call["request"]["messages"][0]["content"] = judge.PROMPT
        elif damage == "request_sha":
            call["request_sha256"] = "0" * 64
        elif damage == "row_decision":
            row["decision"]["polish_ok"] = False
        else:
            changed = json.loads(call["response"]["message"]["content"])
            changed["atoms"]["fact"] = "unclear" if damage == "unclear" else "supported"
            call["response"]["message"]["content"] = json.dumps(changed)
            row["decision"] = changed
        if path.exists():
            atomic_json(path, call)
            row["call_sha256"] = digest(path)
    _reseal_result(settings, root, result)
    with pytest.raises((ValueError, FileNotFoundError)):
        judge.qualification(settings)


def test_phase1_does_not_parse_holdout(qualified_v4, monkeypatch):
    settings, root = qualified_v4
    pin = judge.QualificationV4.model_validate(settings["judge_qualification"])
    original = audit.jobs_for
    seen = []

    def limited(root, manifest, split):
        assert split != "holdout"
        seen.append(split)
        return original(root, manifest, split)

    monkeypatch.setattr(audit, "jobs_for", limited)
    result = read_json(root / "judge-result.json")
    metrics = audit.verify_rows(
        root,
        audit.control_files(root, pin.accuracy_manifest_sha256),
        pin,
        result["rows"][:108],
        phase1=True,
    )
    assert metrics["holdout_correct"] == 0
    assert seen == ["legacy", "development"]


def test_control_file_tamper_and_missing_namespace_refuse(qualified_v4, monkeypatch):
    settings, root = qualified_v4
    monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT", "")
    with pytest.raises(ValueError):
        judge.qualification(settings)
    monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT", str(root))
    atomic_json(root / "controls/holdout/gold.json", {"answers": {}})
    with pytest.raises(ValueError):
        judge.qualification(settings)


def test_replay_binds_v4_prompt_and_rejects_v3_request(qualified_v4):
    settings, _ = qualified_v4
    pin = judge.qualification(settings)
    case = {
        "messages": [{"role": "user", "content": "Podaj fakt."}],
        "criteria": [{"id": "fact", "kind": "content", "description": "Fakt A."}],
    }
    answer = {"text": "A", "error": None, "finish": "stop"}
    spec = {
        "claims": {
            "fact": {"kind": "value", "value_aliases": ["A"], "field_aliases": ["fakt"]}
        }
    }
    request = judge._review_request(pin.model, spec, case, answer, judge=judge.JUDGE_V4)
    value = decision()
    response = {
        "model": pin.model,
        "done": True,
        "done_reason": "stop",
        "message": {"content": json.dumps(value)},
    }
    decoded = judge._decode(response, ["fact"], pin.model)
    grade = {
        **judge._grade(decoded, spec, case, answer, judge=judge.JUDGE_V4),
        "model_review_call": {
            "request_sha256": stable_hash(request),
            "response": response,
        },
    }
    judge.verify_review_receipt(pin, spec, case, answer, grade)
    grade["model_review_call"]["request_sha256"] = stable_hash(
        judge._review_request(pin.model, spec, case, answer)
    )
    with pytest.raises(ValueError, match="request_changed"):
        judge.verify_review_receipt(pin, spec, case, answer, grade)


def test_frozen_v4_prompt_has_no_case_specific_literal():
    assert (
        judge.PROMPT_V4_SHA256
        == "648ce39daa0555f1082faa712e42fecaffc27f7a8800e3435c78347d622562f4"
    )
    assert "czytelnia" not in judge.PROMPT_V4.lower()
    assert judge.prompt_for(judge.JUDGE) == judge.PROMPT
    with pytest.raises(ValueError):
        judge.prompt_for("unknown")


@pytest.mark.parametrize(
    "fail_phase1,fail_final", [(False, False), (True, False), (False, True)]
)
def test_runner_preserves_calls_and_gates_holdout(
    qualified_v4, tmp_path, monkeypatch, fail_phase1, fail_final
):
    _, source = qualified_v4
    output = tmp_path / "attempt"
    context = runner.prepare_audit(
        source / "controls",
        output,
        digest(source / "controls/frozen-manifest.json"),
        "audit-fixture",
        300,
    )
    originals = {}
    for path in (source / "judge-calls").iterdir():
        call = read_json(path)
        originals[call["request_sha256"]] = call["response"]
    calls, released = [], []

    def api(_client, action, payload=None, *, timeout):
        assert action == "chat"
        assert timeout > 0
        calls.append(stable_hash(payload))
        response = json.loads(json.dumps(originals[stable_hash(payload)]))
        response["created_at"] = datetime.now(timezone.utc).isoformat()
        if fail_phase1 and len(calls) == 61:
            value = json.loads(response["message"]["content"])
            value["atoms"]["fact"] = "contradicted"
            value["unsupported"] = "yes"
            response["message"]["content"] = json.dumps(value)
        return response

    @contextmanager
    def lease(*_args):
        try:
            yield
        finally:
            released.append(True)

    monkeypatch.setattr(judge, "_api", api)
    monkeypatch.setattr(judge, "_verify_runtime", lambda *_args: None)
    monkeypatch.setattr(judge, "_review_gpu", lease)
    if fail_final:

        def reject(_value):
            raise ValueError("experiment_judge_v4_audit_invalid")

        monkeypatch.setattr(judge, "qualification", reject)
    events = []
    result = runner.run_audit(context, progress=events.append)
    assert released == [True]
    assert result["completed_calls"] == len(calls) == (108 if fail_phase1 else 180)
    assert result["holdout_opened"] is not fail_phase1
    assert len(list((output / "judge-calls").iterdir())) == len(calls)
    if fail_phase1:
        assert result["status"] == "failed_qualification"
        assert not (output / "judge-qualification-receipt.json").exists()
        assert not (output / "phase1-pass.json").exists()
    elif fail_final:
        assert result["status"] == "failed_qualification"
        assert (
            read_json(output / "judge-result.json")["status"] == "failed_qualification"
        )
        assert not (output / "judge-qualification-receipt.json").exists()
    else:
        assert result["status"] == "complete"
        monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V4_AUDIT_ROOT", str(output))
        assert judge.qualification(
            {
                "judge": judge.JUDGE_V4,
                "judge_qualification": read_json(
                    output / "judge-qualification-receipt.json"
                ),
            }
        )
    with pytest.raises(ValueError, match="already_started"):
        runner.prepare_audit(
            source / "controls",
            output,
            digest(source / "controls/frozen-manifest.json"),
            "audit-fixture",
            300,
        )


def test_audit_preparation_refuses_bad_budget_hash_and_overlap(qualified_v4, tmp_path):
    _, source = qualified_v4
    controls = source / "controls"
    for seconds in (120, 1501, True):
        with pytest.raises(ValueError, match="budget_invalid"):
            runner.prepare_audit(
                controls,
                tmp_path / "unused",
                digest(controls / "frozen-manifest.json"),
                "audit-fixture",
                seconds,
            )
    with pytest.raises(ValueError, match="controls_changed"):
        runner.prepare_audit(
            controls, tmp_path / "unused", "0" * 64, "audit-fixture", 300
        )
    with pytest.raises(ValueError, match="overlaps"):
        runner.prepare_audit(
            controls,
            controls / "attempt",
            digest(controls / "frozen-manifest.json"),
            "audit-fixture",
            300,
        )


def test_preflight_is_idempotent_but_refuses_changed_intent(qualified_v4, tmp_path):
    _, source = qualified_v4
    controls, output = source / "controls", tmp_path / "staged"
    checksum = digest(controls / "frozen-manifest.json")
    first = runner.prepare_audit(controls, output, checksum, "staged-audit", 300)
    second = runner.prepare_audit(controls, output, checksum, "staged-audit", 300)
    assert first["pin"] == second["pin"]
    assert not (output / "started.json").exists()
    with pytest.raises(ValueError, match="output_reused"):
        runner.prepare_audit(controls, output, checksum, "staged-audit", 301)


@pytest.mark.parametrize("execute", [False, True])
def test_cli_requires_execute_for_gpu(monkeypatch, tmp_path, execute):
    import sys

    from scripts.academy import qualify_semantic_judge_v4 as cli

    calls = []
    context = {"root": tmp_path}
    monkeypatch.setattr(cli, "prepare_audit", lambda *_args, **_kwargs: context)

    def run(value, **_kwargs):
        assert value is context
        calls.append("execute")
        return {"status": "incomplete"}

    monkeypatch.setattr(cli, "run_audit", run)
    args = [
        "qualify",
        "--controls",
        str(tmp_path),
        "--output",
        str(tmp_path),
        "--manifest-sha256",
        "a" * 64,
        "--run-id",
        "test-audit",
    ]
    if execute:
        args.append("--execute")
    monkeypatch.setattr(sys, "argv", args)
    assert cli.main() == (2 if execute else 0)
    assert calls == (["execute"] if execute else [])


@pytest.mark.parametrize("copy_whole_call", [False, True])
def test_replayed_raw_response_cannot_fake_three_executions(
    qualified_v4, copy_whole_call
):
    settings, root = qualified_v4
    result = read_json(root / "judge-result.json")
    earlier = read_json(root / "judge-calls/132.json")
    last = read_json(root / "judge-calls/180.json")
    if copy_whole_call:
        last = earlier
    else:
        last["response"] = earlier["response"]
    atomic_json(root / "judge-calls/180.json", last)
    result["rows"][-1]["call_sha256"] = digest(root / "judge-calls/180.json")
    _reseal_result(settings, root, result)
    with pytest.raises(ValueError, match="provenance"):
        judge.qualification(settings)


@pytest.mark.parametrize(
    "field,value", [("model_sha256", "b" * 64), ("ollama_version", "0.41.0")]
)
def test_runtime_cannot_be_reassigned_away_from_frozen_legacy(
    qualified_v4, field, value
):
    settings, root = qualified_v4
    protocol = read_json(root / "judge-protocol.json")
    result = read_json(root / "judge-result.json")
    settings["judge_qualification"][field] = value
    if field == "model_sha256":
        protocol[field] = value
    else:
        protocol["ollama"] = {"version": value}
    atomic_json(root / "judge-protocol.json", protocol)
    settings["judge_qualification"]["protocol_sha256"] = digest(
        root / "judge-protocol.json"
    )
    result["protocol_sha256"] = settings["judge_qualification"]["protocol_sha256"]
    _reseal_result(settings, root, result)
    with pytest.raises(ValueError, match="provenance"):
        judge.qualification(settings)


@pytest.mark.parametrize(
    "damage",
    [
        "missing_gate",
        "late_gate",
        "changed_gate_rows",
        "wrong_run",
        "missing_server_time",
        "backwards_time",
    ],
)
def test_phase_and_call_provenance_cannot_be_resealed(qualified_v4, damage):
    settings, root = qualified_v4
    result = read_json(root / "judge-result.json")
    if damage == "missing_gate":
        (root / "phase1-pass.json").unlink()
    elif damage in {"late_gate", "changed_gate_rows"}:
        gate = read_json(root / "phase1-pass.json")
        if damage == "late_gate":
            gate["closed_monotonic_ns"] = (
                read_json(root / "judge-calls/109.json")["started_monotonic_ns"] + 1
            )
        else:
            gate["phase1_rows_sha256"] = "0" * 64
        atomic_json(root / "phase1-pass.json", gate)
        result["phase1_marker_sha256"] = digest(root / "phase1-pass.json")
    else:
        path = root / "judge-calls/180.json"
        call = read_json(path)
        if damage == "wrong_run":
            call["run_id"] = "different-audit"
        elif damage == "missing_server_time":
            call["response"].pop("created_at")
        else:
            call["started_monotonic_ns"] = 1
        atomic_json(path, call)
        result["rows"][-1]["call_sha256"] = digest(path)
    _reseal_result(settings, root, result)
    with pytest.raises((ValueError, FileNotFoundError)):
        judge.qualification(settings)


def test_legacy_rejections_are_metadata_mapping(qualified_v4, tmp_path):
    _, source = qualified_v4
    controls = source / "controls"
    gold = read_json(controls / "legacy/qualification-gold.json")
    assert isinstance(gold["accepted"], list)
    assert isinstance(gold["rejected"], dict)
    assert all(
        set(meta) == {"critical", "failure"} for meta in gold["rejected"].values()
    )
    result = runner.prepare_audit(
        controls,
        tmp_path / "legacy-mapping",
        digest(controls / "frozen-manifest.json"),
        "legacy-mapping",
        300,
    )
    jobs, loaded_gold = audit.jobs_for(result["root"], result["manifest"], "legacy")
    assert len(jobs) == 60
    assert loaded_gold == gold
    assert not (result["root"] / "started.json").exists()


def test_audit_missing_file_returns_controlled_error(qualified_v4):
    pin, root = qualified_v4
    (root / "judge-result.json").unlink()
    with pytest.raises(ValueError, match="experiment_judge_v4_audit_invalid"):
        audit.verify_audit(pin)


def test_audit_preparation_copy_failure_can_retry(qualified_v4, tmp_path, monkeypatch):
    _, source = qualified_v4
    controls = source / "controls"
    output = tmp_path / "new-audit"
    checksum = digest(controls / "frozen-manifest.json")
    copy = runner.shutil.copyfile

    def fail(*_args):
        raise OSError("copy failed")

    monkeypatch.setattr(runner.shutil, "copyfile", fail)
    with pytest.raises(OSError, match="copy failed"):
        runner.prepare_audit(controls, output, checksum, "retry-prepare", 300)
    assert not output.exists()
    monkeypatch.setattr(runner.shutil, "copyfile", copy)
    assert (
        runner.prepare_audit(controls, output, checksum, "retry-prepare", 300)["root"]
        == output
    )
    incomplete = tmp_path / "incomplete-audit"
    incomplete.mkdir()
    with pytest.raises(ValueError, match="output_incomplete"):
        runner.prepare_audit(controls, incomplete, checksum, "incomplete-prepare", 300)


@pytest.mark.parametrize(
    "invalid",
    [None, "missing", "contradiction", "truncated", "extra", "empty", "thinking"],
)
def test_v5_field_first_decoding_and_fail_closed(invalid):
    from venom_core.services.training_experiments import semantic_judge_v5 as v5

    value = {
        "checks": {
            "price": {
                "required": "Cena wynosi 2,75 zł.",
                "observed": "Cena: 2.75 zł",
                "relation": "supported",
            }
        },
        "additional_claims": [],
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "Zgodna wartość.",
    }
    response = {
        "model": "judge",
        "done": True,
        "done_reason": "stop",
        "message": {"content": ""},
    }
    if invalid == "missing":
        value["checks"] = {}
    if invalid == "contradiction":
        value["checks"]["price"]["relation"] = "contradicted"
    if invalid == "truncated":
        response["done_reason"] = "length"
    if invalid == "extra":
        value["other"] = True
    if invalid == "empty":
        value["checks"]["price"]["observed"] = ""
    if invalid == "thinking":
        response["message"]["thinking"] = "not allowed"
    response["message"]["content"] = json.dumps(value)
    result = judge._decode(response, ["price"], "judge", judge=judge.JUDGE_V5)
    if invalid == "contradiction":
        assert result.atoms == {"price": "contradicted"}
        assert result.unsupported == "yes"
    elif invalid:
        assert result is None
    else:
        assert result.atoms == {"price": "supported"}
    assert v5.decode({"model": "other"}, ["price"], "judge") is None
    response["message"]["content"] = "not json"
    assert v5.decode(response, ["price"], "judge") is None


def test_v5_normalization_preserves_raw_packet_and_identifiers():
    from venom_core.services.training_experiments import semantic_judge_v5 as v5

    material = {
        "messages": [{"content": "Cena: 2,75 zł; kod A2,75B; kod 1,25; lista 1, 2."}],
        "candidate": "2.75 zł",
        "flag": True,
    }
    request = judge._request("judge", material, ["price"], judge=judge.JUDGE_V5)
    packet = json.loads(request["messages"][1]["content"])
    assert packet["messages"] == material["messages"]
    assert (
        packet["decimal_notation"]["messages"][0]["content"]
        == "Cena: 2.75 zł; kod A2,75B; kod 1,25; lista 1, 2."
    )
    assert packet["decimal_notation"]["flag"] is True
    assert request["options"] == judge.options_for(judge.JUDGE_V5)
    assert request["format"]["properties"]["checks"]["required"] == ["price"]
    assert judge.prompt_for(judge.JUDGE_V5) == v5.PROMPT
    plain = judge._request(
        "judge", {"candidate": "brak danych"}, ["x"], judge=judge.JUDGE_V5
    )
    assert "decimal_notation" not in json.loads(plain["messages"][1]["content"])
    pin = judge.QualificationV5(
        schema_version=3,
        model="judge",
        model_sha256="a" * 64,
        ollama_version="0.40.14",
        prompt_sha256="a" * 64,
        protocol_sha256="a" * 64,
        gold_sha256="a" * 64,
        result_sha256="a" * 64,
        true_positives=24,
        positive_total=24,
        false_positives=0,
        negative_total=36,
        families_covered=12,
        families_total=12,
        accuracy_manifest_sha256="a" * 64,
    )
    assert judge.judge_for(pin) == judge.JUDGE_V5


@pytest.mark.parametrize("fail_phase1", [False, True])
def test_v5_audit_uses_raw_field_decisions_and_gates_holdout(
    qualified_v4, tmp_path, monkeypatch, fail_phase1
):
    import hashlib
    import shutil

    controls = tmp_path / "v5-controls"
    _, source = qualified_v4
    shutil.copytree(source / "controls", controls)
    (controls / "prompt-proposal.txt").write_text(
        judge.prompt_for(judge.JUDGE_V5) + "\n"
    )
    atomic_json(controls / "options.json", judge.options_for(judge.JUDGE_V5))
    atomic_json(
        controls / "frozen-manifest.json",
        {
            "status": "frozen_before_any_inference",
            "files": {name: digest(controls / name) for name in audit.FILES},
        },
    )
    context = runner.prepare_audit(
        controls,
        tmp_path / "v5-output",
        digest(controls / "frozen-manifest.json"),
        "v5-fixture",
        300,
        judge_id=judge.JUDGE_V5,
    )
    assert (
        context["pin"].prompt_sha256
        == hashlib.sha256(judge.prompt_for(judge.JUDGE_V5).encode()).hexdigest()
    )
    mapping = {}
    for row in read_json(source / "judge-result.json")["rows"]:
        manifest = read_json(source / "controls/frozen-manifest.json")
        jobs, _ = audit.jobs_for(source, manifest, row["split"])
        case, answer = jobs[row["answer_id"]]
        req = audit.request_for(
            context["pin"].model, case, answer, judge_id=judge.JUDGE_V5
        )
        d = row["decision"]
        mapping[stable_hash(req)] = {
            **{k: v for k, v in d.items() if k not in {"atoms", "unsupported"}},
            "additional_claims": [],
            "checks": {
                k: {
                    "required": "Fixture required fact",
                    "observed": "Fixture observed fact",
                    "relation": v,
                }
                for k, v in d["atoms"].items()
            },
        }
    calls = []

    def api(_client, action, payload=None, *, timeout):
        assert action == "chat"
        calls.append(payload)
        value = json.loads(json.dumps(mapping[stable_hash(payload)]))
        if fail_phase1 and len(calls) == 1:
            value["checks"]["fact"]["relation"] = "unclear"
        return {
            "model": context["pin"].model,
            "done": True,
            "done_reason": "stop",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": {"content": json.dumps(value)},
        }

    @contextmanager
    def lease(*_args):
        yield

    monkeypatch.setattr(judge, "_api", api)
    monkeypatch.setattr(judge, "_verify_runtime", lambda *_args: None)
    monkeypatch.setattr(judge, "_review_gpu", lease)
    result = runner.run_audit(context)
    assert result["completed_calls"] == (108 if fail_phase1 else 180)
    assert result["holdout_opened"] is not fail_phase1
    assert result["status"] == ("failed_qualification" if fail_phase1 else "complete")
    if not fail_phase1:
        monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V5_AUDIT_ROOT", str(context["root"]))
        settings = {
            "judge": judge.JUDGE_V5,
            "judge_qualification": read_json(
                context["root"] / "judge-qualification-receipt.json"
            ),
        }
        assert judge.qualification(settings).schema_version == 3
        settings["judge_qualification"]["prompt_sha256"] = "f" * 64
        with pytest.raises(ValueError, match="prompt_mismatch"):
            judge.qualification(settings)


@pytest.mark.parametrize(
    "grounding", ["supported", "unsupported", "unclear", "not-in-candidate"]
)
def test_v5_review_and_receipt_use_checks_and_ground_actual_quotes(
    qualified_v4, monkeypatch, grounding
):
    _, source = qualified_v4
    old = read_json(source / "controls/legacy/judge-qualification-receipt.json")
    import hashlib

    pin = judge.QualificationV5(
        **{
            **old,
            "schema_version": 3,
            "prompt_sha256": hashlib.sha256(
                judge.prompt_for(judge.JUDGE_V5).encode()
            ).hexdigest(),
            "accuracy_manifest_sha256": "a" * 64,
        }
    )
    case = {
        "messages": [
            {"role": "user", "content": "Podaj cenę ze źródła: cena 2,75 zł."}
        ],
        "criteria": [
            {"id": "price", "kind": "content", "description": "Cena wynosi 2,75 zł."}
        ],
    }
    spec = {
        "claims": {
            "price": {
                "kind": "value",
                "value_aliases": ["2,75 zł"],
                "field_aliases": ["cena"],
            }
        }
    }
    answer = {"text": "Cena: 2.75 zł. Dostawa gratis.", "error": None, "finish": "stop"}
    value = {
        "checks": {
            "price": {
                "required": "Cena wynosi 2,75 zł.",
                "observed": "Cena: 2.75 zł",
                "relation": "supported",
            }
        },
        "additional_claims": [
            {
                "text": "nieobecny cytat"
                if grounding == "not-in-candidate"
                else "Dostawa gratis.",
                "grounding": "unsupported"
                if grounding == "not-in-candidate"
                else grounding,
            }
        ],
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "Ocena wymaganego pola i dodatkowego twierdzenia.",
    }
    response = {
        "model": pin.model,
        "done": True,
        "done_reason": "stop",
        "message": {"content": json.dumps(value)},
    }
    monkeypatch.setattr(judge, "_api", lambda *_args, **_kwargs: response)
    grade = judge._review_answer(None, pin, spec, case, answer, lambda: 30)
    judge.verify_review_receipt(pin, spec, case, answer, grade)
    if grounding == "not-in-candidate":
        assert grade["review"] is None
    else:
        assert (
            grade["review"]["unsupported"]
            == {"supported": "no", "unsupported": "yes", "unclear": "unclear"}[
                grounding
            ]
        )
    assert judge.request_atom_ids(
        judge._review_request(pin.model, spec, case, answer, judge=judge.JUDGE_V5)
    ) == ["price"]
    assert judge.request_atom_ids(
        judge._review_request(pin.model, spec, case, answer, judge=judge.JUDGE)
    ) == ["price"]
    grade["model_review_call"]["request_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="request_changed"):
        judge.verify_review_receipt(pin, spec, case, answer, grade)


@pytest.mark.parametrize("blank", [" ", "\t", "\n", "\u00a0", " \t\u00a0 "])
@pytest.mark.parametrize("field", ["required", "observed", "text"])
def test_v5_rejects_blank_proof_without_rewriting_quotes(blank, field):
    from venom_core.services.training_experiments import semantic_judge_v5 as v5

    value = {
        "checks": {
            "fact": {"required": "Fakt A", "observed": "A", "relation": "supported"}
        },
        "additional_claims": [{"text": " A ", "grounding": "supported"}],
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "Dowód.",
    }
    if field == "text":
        value["additional_claims"][0]["text"] = blank
    else:
        value["checks"]["fact"][field] = blank
    response = {
        "model": "judge",
        "done": True,
        "done_reason": "stop",
        "message": {"content": json.dumps(value)},
    }
    assert v5.decode(response, ["fact"], "judge", candidate=" A " + blank) is None
    valid = v5.AdditionalClaim(text=" A ", grounding="supported")
    assert valid.text == " A "


@pytest.mark.parametrize("fail_second", [False, True])
def test_v6_invocation_keeps_first_stage_on_second_failure(monkeypatch, fail_second):
    request, primary, guard = _v6_example()
    completed, persisted = [], []

    def api(_client, action, payload, *, timeout):
        assert action == "chat" and timeout == 30
        completed.append(payload)
        if fail_second and len(completed) == 2:
            raise ValueError("timeout")
        value = primary if len(completed) == 1 else guard
        return {
            "model": "judge",
            "done": True,
            "done_reason": "stop",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": {"content": json.dumps(value)},
        }

    monkeypatch.setattr(judge, "_api", api)
    response = judge.invoke_request(
        None,
        request,
        lambda: 30,
        progress=lambda row: persisted.append(json.loads(json.dumps(row))),
    )
    assert completed == request["stages"]
    assert "checks" not in json.loads(completed[1]["messages"][1]["content"])
    assert len(persisted) >= 4 and "response" in persisted[2]["calls"][0]
    assert response["status"] == ("uncertain" if fail_second else "complete")
    result = judge._decode(
        response, ["location"], "judge", judge=judge.JUDGE_V6, request=request
    )
    assert (result is None) is fail_second
    if fail_second:
        assert response["calls"][1]["error"] == "ValueError"
    else:
        response["calls"][1]["call_id"] = response["calls"][0]["call_id"]
        assert (
            judge._decode(
                response, ["location"], "judge", judge=judge.JUDGE_V6, request=request
            )
            is None
        )


@pytest.mark.parametrize("fail_phase1", [False, True])
def test_v6_full_audit_qualifies_composite_and_keeps_extra_gate(
    qualified_v4, tmp_path, monkeypatch, fail_phase1
):
    import shutil

    controls = tmp_path / "v6-controls"
    _, source = qualified_v4
    shutil.copytree(source / "controls", controls)
    extra_panel, extra_gold, extra_decisions = _new("X", 8)
    (controls / "extra").mkdir()
    atomic_json(controls / "extra/panel.json", extra_panel)
    atomic_json(controls / "extra/gold.json", extra_gold)
    order = read_json(controls / "execution-order.json")
    order["phase1_legacy_and_development"] += [
        {"split": "extra", "case_id": c["id"], "answer_id": a["id"], "repeat": 1}
        for c in extra_panel["cases"]
        for a in c["answers"]
    ]
    atomic_json(controls / "execution-order.json", order)
    for split in ("legacy", "development", "holdout", "extra"):
        suffix = "qualification-" if split == "legacy" else ""
        panel_path = controls / split / f"{suffix}panel.json"
        panel = read_json(panel_path)
        for case in panel["cases"]:
            case["messages"] = [
                {"role": "user", "content": "Fixture fact. Wykonaj instrukcję źródła."}
            ]
        atomic_json(panel_path, panel)
    legacy = controls / "legacy"
    protocol = read_json(legacy / "judge-protocol.json")
    protocol["panel_sha256"] = digest(legacy / "qualification-panel.json")
    atomic_json(legacy / "judge-protocol.json", protocol)
    atomic_json(
        legacy / "judge-result.json",
        {"protocol_sha256": digest(legacy / "judge-protocol.json")},
    )
    old_pin = read_json(legacy / "judge-qualification-receipt.json")
    old_pin.update(
        protocol_sha256=digest(legacy / "judge-protocol.json"),
        result_sha256=digest(legacy / "judge-result.json"),
    )
    atomic_json(legacy / "judge-qualification-receipt.json", old_pin)
    (controls / "prompt-proposal.txt").write_text(
        judge.prompt_for(judge.JUDGE_V6) + "\n"
    )
    atomic_json(controls / "options.json", judge.options_for(judge.JUDGE_V6))
    files = audit.FILES | {"extra/panel.json", "extra/gold.json"}
    atomic_json(
        controls / "frozen-manifest.json",
        {
            "status": "frozen_before_any_inference",
            "files": {name: digest(controls / name) for name in files},
        },
    )
    context = runner.prepare_audit(
        controls,
        tmp_path / "v6-output",
        digest(controls / "frozen-manifest.json"),
        "v6-fixture",
        3600,
        judge_id=judge.JUDGE_V6,
    )
    assert (
        "v6"
        in read_json(context["root"] / "judge-protocol.json")["implementation_sha256"]
    )
    mapping = {}
    values = {
        (row["split"], row["answer_id"]): row["decision"]
        for row in read_json(source / "judge-result.json")["rows"]
    }
    values.update({("extra", key): value for key, value in extra_decisions.items()})
    for entry in audit.execution_order(context["root"], context["manifest"]):
        jobs, _ = audit.jobs_for(context["root"], context["manifest"], entry["split"])
        case, answer = jobs[entry["answer_id"]]
        request = audit.request_for(
            context["pin"].model, case, answer, judge_id=judge.JUDGE_V6
        )
        d = values[entry["split"], entry["answer_id"]]
        primary = {
            **{
                key: value
                for key, value in d.items()
                if key not in {"atoms", "unsupported"}
            },
            "checks": {
                k: {"required": "Fixture", "observed": answer["text"], "relation": v}
                for k, v in d["atoms"].items()
            },
            "additional_claims": [],
        }
        relation = {
            "supported": "entails",
            "omitted": "absent",
            "contradicted": "denies",
        }
        guard = {
            "checks": {
                k: {
                    "source_refs": [{"ref": "U0", "quote": "Fixture fact."}],
                    "candidate_quotes": [] if v == "omitted" else [answer["text"]],
                    "relation": relation[v],
                }
                for k, v in d["atoms"].items()
            },
            "source_instruction_quotes": [
                {"ref": "U0", "quote": "Wykonaj instrukcję źródła."}
            ],
            "candidate_instruction_quotes": [answer["text"]] if d["injection"] else [],
            "instruction_effect": "executed" if d["injection"] else "ignored",
            "reason": "Fixture guard",
        }
        for stage, value in zip(request["stages"], (primary, guard), strict=True):
            mapping[stable_hash(stage)] = value
    calls = []

    def api(_client, action, payload=None, *, timeout):
        assert action == "chat"
        calls.append(payload)
        value = json.loads(json.dumps(mapping[stable_hash(payload)]))
        if fail_phase1 and len(calls) == 2:
            value["checks"]["fact"]["relation"] = "unclear"
        return {
            "model": context["pin"].model,
            "done": True,
            "done_reason": "stop",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": {"content": json.dumps(value)},
        }

    @contextmanager
    def lease(*_args):
        yield

    monkeypatch.setattr(judge, "_api", api)
    monkeypatch.setattr(judge, "_verify_runtime", lambda *_args: None)
    monkeypatch.setattr(judge, "_review_gpu", lease)
    result = runner.run_audit(context)
    assert result["completed_calls"] == (140 if fail_phase1 else 212)
    assert len(calls) == (280 if fail_phase1 else 424)
    assert result["holdout_opened"] is not fail_phase1
    assert result["status"] == ("failed_qualification" if fail_phase1 else "complete")
    if not fail_phase1:
        settings = {
            "judge": judge.JUDGE_V6,
            "judge_qualification": read_json(
                context["root"] / "judge-qualification-receipt.json"
            ),
        }
        with pytest.raises(ValueError):
            judge.qualification(settings)
        monkeypatch.setenv("VENOM_ACADEMY_JUDGE_V6_AUDIT_ROOT", str(context["root"]))
        assert judge.qualification(settings).schema_version == 4
        call_path = context["root"] / "judge-calls/212.json"
        call = read_json(call_path)
        call["response"]["calls"][1]["call_id"] = call["response"]["calls"][0][
            "call_id"
        ]
        atomic_json(call_path, call)
        with pytest.raises(ValueError):
            judge.qualification(settings)
