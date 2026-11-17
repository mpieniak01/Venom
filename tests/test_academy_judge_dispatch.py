"""Remote Academy review must never silently become exact or local judging."""

import json
import time
from copy import deepcopy
from unittest.mock import Mock

import pytest

from venom_core.services.training_experiments import calibration
from venom_core.services.training_experiments import (
    checkpoint_evaluation as checkpoints,
)
from venom_core.services.training_experiments import local_semantic_judge as local
from venom_core.services.training_experiments import openrouter_semantic_judge as remote
from venom_core.services.training_experiments import remote_text_qualification as final
from venom_core.services.training_experiments import semantic_judge_dispatch as dispatch
from venom_core.services.training_experiments import worker
from venom_core.services.training_experiments.profiles import digest
from venom_core.services.training_experiments.quality_native import evaluation_identity

HASH = "a" * 64


@pytest.fixture
def remote_calibration():
    return {
        "schema_version": 1,
        "judge": remote.JUDGE,
        "reviewer": "remote CPU fixture",
        "dev_sha256": HASH,
        "judge_qualification": {
            "protocol_sha256": "b" * 64,
            "result_sha256": "c" * 64,
        },
        "cases": {
            "one": {
                "claims": {
                    "person": {
                        "kind": "value",
                        "field_aliases": ["osoba"],
                        "value_aliases": ["Ada"],
                    }
                }
            }
        },
    }


@pytest.fixture(autouse=True)
def forbid_local_judging(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("remote review reached a local model")

    for name in (
        "qualification",
        "preflight",
        "review_bundle",
        "verify_review_receipt",
    ):
        monkeypatch.setattr(local, name, forbidden)


def _case():
    return {
        "record_id": "one",
        "criteria": [{"id": "person", "kind": "content", "description": "Osoba Ada."}],
    }


@pytest.mark.parametrize(
    "unknown", ["not-a-judge", "semantic-openrouter-luna-field-v2"]
)
def test_unknown_judge_is_rejected_before_exact_fallback(unknown):
    settings = {"judge": unknown}
    for action in (dispatch.backend, dispatch.is_semantic, calibration.scorer_protocol):
        with pytest.raises(ValueError, match="experiment_judge_version_invalid"):
            action(settings)


def test_exact_and_local_identities_are_preserved():
    assert dispatch.is_semantic({"judge": "exact-v1"}) is False
    assert calibration.scorer_protocol({"judge": "exact-v1"}) == "omni-rubric-v1"
    assert dispatch.backend({"judge": local.JUDGE}) is local


def test_remote_calibration_requires_remote_qualification(
    remote_calibration, monkeypatch
):
    pin = object()
    qualify = Mock(return_value=pin)
    monkeypatch.setattr(remote, "qualification", qualify)
    calibration.validate_calibration(remote_calibration, HASH, [_case()])
    qualify.assert_called_once_with(remote_calibration)
    qualify.side_effect = ValueError("remote_qualification_failed")
    with pytest.raises(ValueError, match="remote_qualification_failed"):
        calibration.validate_calibration(remote_calibration, HASH, [_case()])


def test_remote_calibration_cannot_skip_case_coverage(remote_calibration, monkeypatch):
    monkeypatch.setattr(remote, "qualification", lambda _: object())
    remote_calibration["cases"] = {}
    with pytest.raises(ValueError, match="experiment_calibration_coverage"):
        calibration.validate_calibration(remote_calibration, HASH, [_case()])


def test_remote_preflight_delegates_without_local_runtime(
    remote_calibration, monkeypatch
):
    preflight = Mock()
    monkeypatch.setattr(remote, "preflight", preflight)
    dispatch.preflight(remote_calibration)
    preflight.assert_called_once_with(remote_calibration)


def test_remote_identity_changes_the_quality_cache(remote_calibration, monkeypatch):
    generation = {
        "model_repo": "fixture-model",
        "snapshot_manifest_sha256": HASH,
        "data_sha256": HASH,
        "revision": "fixed",
        "max_prompt_tokens": 1280,
        "max_new_tokens": 256,
        "seed": 42,
        "engine": "native",
        "template": "fixed",
        "generation_mode": "greedy",
        "do_sample": False,
        "enable_thinking": False,
    }
    scorer = Mock(return_value=f"{remote.JUDGE}:first-qualified-protocol")
    monkeypatch.setattr(remote, "scorer_protocol", scorer)
    identity = evaluation_identity(generation, HASH, calibration=remote_calibration)
    scorer.assert_called_once_with(remote_calibration)
    scorer.return_value = f"{remote.JUDGE}:different-qualified-protocol"
    changed = evaluation_identity(generation, HASH, calibration=remote_calibration)
    exact = evaluation_identity(
        generation, HASH, calibration={"judge": "exact-v1", "schema_version": 1}
    )
    assert identity != changed
    assert identity != exact


@pytest.mark.parametrize("reuse", [False, True])
def test_checkpoint_review_dispatches_remote_and_preserves_reuse(
    remote_calibration, monkeypatch, tmp_path, reuse
):
    instance = object.__new__(worker.Worker)
    instance.directory = tmp_path
    instance.run_id = "remote-cpu"
    instance.deadline = time.monotonic() + 100
    instance.check_budget = Mock()
    bundle = {"cases": [_case()], "answers": []}
    reused = [{"record_id": "one", "label": "base"}] if reuse else []
    fresh = [{"record_id": "one", "label": "candidate"}]
    monkeypatch.setattr(worker, "review_data", lambda *_: bundle)
    monkeypatch.setattr(
        worker,
        "calibrated_judgments",
        Mock(side_effect=AssertionError("exact fallback")),
    )
    reuse_call = Mock(return_value=(bundle, reused))
    monkeypatch.setattr(worker, "reuse_baseline_reviews", reuse_call)
    review = Mock(return_value=fresh)
    monkeypatch.setattr(remote, "review_bundle", review)
    step = 42 if reuse else None
    actual = instance._checkpoint_judgments(
        tmp_path,
        tmp_path / "dev",
        step,
        remote_calibration,
        state={"checkpoint_steps": [21, 42], "manifest_sha256": HASH},
    )
    assert actual == [*reused, *fresh]
    assert reuse_call.call_count == int(reuse)
    args, kwargs = review.call_args
    assert args[:3] == (remote_calibration, bundle, "remote-cpu")
    assert 0 < args[3] <= 100
    assert kwargs["check"] == instance.check_budget


def test_final_review_dispatches_remote_and_keeps_deadline(
    remote_calibration, monkeypatch
):
    checks = []
    bundle = {"cases": [], "answers": []}
    grade = [{"record_id": "one", "label": "candidate"}]

    def review(settings, payload, run_id, seconds, *, check):
        assert (settings, payload, run_id, seconds) == (
            remote_calibration,
            bundle,
            "final-cpu",
            10,
        )
        check()
        return grade

    monkeypatch.setattr(remote, "review_bundle", review)
    monkeypatch.setattr(
        final,
        "calibrated_judgments",
        Mock(side_effect=AssertionError("exact fallback")),
    )
    assert (
        final._final_judgments(
            remote_calibration, bundle, "final-cpu", 10, lambda: checks.append(True)
        )
        == grade
    )
    assert checks == [True]


def test_remote_cached_final_requires_evidence_verification(
    remote_calibration, monkeypatch, tmp_path
):
    binding = {"run_id": "final-cpu"}
    result = {
        "binding": binding,
        "qualified": None,
        "calibration_protocol": {"judge": remote.JUDGE},
    }
    (tmp_path / "result.json").write_text(json.dumps(result))
    (tmp_path / "result-seal.json").write_text(
        json.dumps({"sha256": digest(tmp_path / "result.json")})
    )
    verification = Mock(return_value=tmp_path)
    monkeypatch.setattr(final, "_verify_final_evidence", verification)
    assert final._read_result(tmp_path, binding) == result
    verification.assert_called_once_with(tmp_path, result)
    verification.side_effect = ValueError("remote_text_final_evidence_changed")
    with pytest.raises(ValueError, match="remote_text_final_evidence_changed"):
        final._read_result(tmp_path, binding)


def test_unknown_checkpoint_reviewer_cannot_reach_exact(monkeypatch, tmp_path):
    instance = object.__new__(worker.Worker)
    instance.directory = tmp_path
    instance.run_id = "unknown-cpu"
    instance.deadline = time.monotonic() + 100
    monkeypatch.setattr(worker, "review_data", lambda *_: {"cases": [], "answers": []})
    fallback = Mock(side_effect=AssertionError("unknown scorer reached exact"))
    monkeypatch.setattr(worker, "calibrated_judgments", fallback)
    with pytest.raises(ValueError, match="experiment_judge_version_invalid"):
        instance._checkpoint_judgments(
            tmp_path, tmp_path / "dev", None, {"judge": "unknown"}, state={}
        )
    fallback.assert_not_called()


def test_receipt_verifier_selects_remote_type_and_rejects_unknown(monkeypatch):
    pin = remote.QualificationRemote.model_construct()
    receipt = Mock()
    monkeypatch.setattr(remote, "verify_review_receipt", receipt)
    arguments = ({}, {}, {}, {})
    dispatch.verify_review_receipt(pin, *arguments)
    receipt.assert_called_once_with(pin, *arguments)
    with pytest.raises(ValueError, match="experiment_judge_version_invalid"):
        dispatch.verify_review_receipt(object(), *arguments)


@pytest.mark.parametrize("tamper", [None, "receipt", "history"])
def test_remote_baseline_cache_replays_receipt_and_own_history(
    remote_calibration, monkeypatch, tmp_path, tamper
):
    from scripts.academy import omni_pl_chat_scoring

    source = tmp_path / "checkpoint-evaluations" / "21"
    previous = {"models": {"base": {"base": True}}, "seed": 42, "outputs": "first"}
    current = {**deepcopy(previous), "outputs": "second"}
    receipt = {"run_id": "remote-cpu", "scorer_protocol": f"{remote.JUDGE}:qualified"}
    grade = {"record_id": "one", "label": "B", "model_review_call": {"id": "original"}}
    bundle = {
        "cases": [_case()],
        "answers": [
            {
                "case": _case(),
                "answers": {"A": {"text": "Ada"}, "C": {"text": "Candidate"}},
            }
        ],
    }
    raw = {"output": "Ada", "input_messages": [{"role": "user", "content": "Osoba?"}]}
    original_inputs = {"one": {"raw": raw, "label": "B", "answer": {"text": "Ada"}}}
    target_inputs = {
        "one": {"raw": deepcopy(raw), "label": "A", "answer": {"text": "Ada"}}
    }
    if tamper == "history":
        target_inputs["one"]["raw"]["input_messages"][0]["content"] = "Other history"
    monkeypatch.setattr(
        checkpoints,
        "_baseline_source",
        lambda *_: (source, previous, receipt, [grade]),
    )
    monkeypatch.setattr(checkpoints, "read_generation", lambda _: (current, None))
    monkeypatch.setattr(checkpoints, "rows", lambda _: bundle["answers"])
    monkeypatch.setattr(
        checkpoints,
        "_baseline_inputs",
        lambda path, *_: original_inputs if path == source else target_inputs,
    )
    monkeypatch.setattr(omni_pl_chat_scoring, "aggregate", lambda *_: None)
    pin = remote.QualificationRemote.model_construct()
    monkeypatch.setattr(remote, "qualification", lambda _: pin)
    verification = Mock()
    if tamper == "receipt":
        verification.side_effect = ValueError(
            "experiment_checkpoint_baseline_receipt_changed"
        )
    monkeypatch.setattr(remote, "verify_review_receipt", verification)
    if tamper:
        with pytest.raises(
            ValueError,
            match="experiment_checkpoint_baseline_(generation|receipt)_changed",
        ):
            checkpoints.reuse_baseline_reviews(
                tmp_path,
                42,
                bundle,
                remote_calibration,
                steps=[21, 42],
                manifest_sha256=HASH,
            )
        assert verification.call_count == int(tamper == "receipt")
    else:
        pending, reused = checkpoints.reuse_baseline_reviews(
            tmp_path,
            42,
            bundle,
            remote_calibration,
            steps=[21, 42],
            manifest_sha256=HASH,
        )
        verification.assert_called_once_with(
            pin,
            remote_calibration["cases"]["one"],
            _case(),
            target_inputs["one"]["answer"],
            grade,
        )
        assert reused == [{**grade, "label": "A", "review_reused_from": receipt}]
        assert pending["answers"][0]["answers"] == {"C": {"text": "Candidate"}}


def test_local_receipt_dispatch_remains_explicit(monkeypatch):
    pin = local.Qualification.model_construct()
    verify = Mock()
    monkeypatch.setattr(local, "verify_review_receipt", verify)
    dispatch.verify_review_receipt(pin, {}, {}, {}, {})
    verify.assert_called_once_with(pin, {}, {}, {}, {})


def test_local_scorer_protocol_remains_pinned():
    settings = {
        "judge": local.JUDGE,
        "schema_version": 1,
        "judge_qualification": {"protocol_sha256": HASH, "result_sha256": "b" * 64},
    }
    assert calibration.scorer_protocol(settings) == (
        f"{local.JUDGE}:schema-1:{HASH}:" + "b" * 64
    )


def test_final_remote_without_deadline_callback_does_not_fall_back(
    remote_calibration, monkeypatch
):
    review = Mock(return_value=[])
    monkeypatch.setattr(remote, "review_bundle", review)
    monkeypatch.setattr(
        final,
        "calibrated_judgments",
        Mock(side_effect=AssertionError("exact fallback")),
    )
    assert final._final_judgments(remote_calibration, {}, "remote-cpu", 10, None) == []
    assert review.call_args.args == (remote_calibration, {}, "remote-cpu", 10)


@pytest.mark.parametrize("invalid_id", [[], {}, True])
def test_malformed_judge_ids_fail_with_contract_error(remote_calibration, invalid_id):
    settings = {**remote_calibration, "judge": invalid_id}
    for action in (dispatch.backend, dispatch.is_semantic, calibration.scorer_protocol):
        with pytest.raises(ValueError, match="experiment_judge_version_invalid"):
            action(settings)
    with pytest.raises(ValueError, match="experiment_calibration_invalid"):
        calibration.validate_calibration(settings, HASH, [_case()])
