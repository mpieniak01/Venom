"""v4 requires every raw call and repeated decision; v3 pins remain unchanged."""

import json
from contextlib import contextmanager

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
            "rejected": rejected,
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
    atomic_json(
        root / "controls/legacy/judge-qualification-receipt.json",
        {
            "schema_version": 1,
            "model": "test-judge",
            "model_sha256": "d" * 64,
            "ollama_version": "0.40.14",
            "prompt_sha256": judge.PROMPT_SHA256,
            "protocol_sha256": "e" * 64,
            "gold_sha256": "f" * 64,
            "result_sha256": "a" * 64,
            "true_positives": 24,
            "positive_total": 24,
            "false_positives": 0,
            "negative_total": 36,
            "families_covered": 12,
            "families_total": 12,
        },
    )
    atomic_json(
        root / "controls/frozen-manifest.json",
        {
            "status": "frozen_before_any_inference",
            "files": {name: digest(root / "controls" / name) for name in audit.FILES},
        },
    )
    receipt = {
        "schema_version": 2,
        "model": "test-judge",
        "model_sha256": "d" * 64,
        "ollama_version": "0.40.14",
        "prompt_sha256": judge.PROMPT_V4_SHA256,
        "true_positives": 24,
        "positive_total": 24,
        "false_positives": 0,
        "negative_total": 36,
        "families_covered": 12,
        "families_total": 12,
        "accuracy_manifest_sha256": digest(root / "controls/frozen-manifest.json"),
        "gold_sha256": digest(root / "controls/legacy/qualification-gold.json"),
    }
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
    }
    atomic_json(root / "judge-protocol.json", protocol)
    receipt["protocol_sha256"] = digest(root / "judge-protocol.json")
    reviews = []
    for index, entry in enumerate(first + hold, 1):
        key = entry["split"], entry["answer_id"]
        case, answer = all_jobs[key]
        request = audit.request_for(receipt["model"], case, answer)
        value = gold_decisions[key]
        response = {
            "model": receipt["model"],
            "done": True,
            "done_reason": "stop",
            "message": {"content": json.dumps(value)},
        }
        path = root / "judge-calls" / f"{index:03d}.json"
        atomic_json(
            path,
            {
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
        root / "judge-result.json",
        {
            "status": "complete",
            "protocol_sha256": receipt["protocol_sha256"],
            "rows": reviews,
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
        == "691b19fec941849745791af5bbe2fe50afde3bf5ace31200c2a8ce4a1943d40e"
    )
    assert "czytelnia" not in judge.PROMPT_V4.lower()
    assert judge.prompt_for(judge.JUDGE) == judge.PROMPT
    with pytest.raises(ValueError):
        judge.prompt_for("unknown")


@pytest.mark.parametrize("fail_phase1", [False, True])
def test_runner_preserves_calls_and_gates_holdout(
    qualified_v4, tmp_path, monkeypatch, fail_phase1
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
        assert action == "chat" and timeout > 0
        calls.append(stable_hash(payload))
        response = json.loads(json.dumps(originals[stable_hash(payload)]))
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
    monkeypatch.setattr(cli, "prepare_audit", lambda *_args: context)

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
