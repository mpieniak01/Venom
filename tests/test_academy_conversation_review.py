"""Offline receipt and binding tests; no campaign or holdout is opened."""

import copy
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from venom_core.services.training_experiments.conversation_review import (
    register_review,
    register_review_request,
    score,
    verify_final_review,
    verify_review,
)


def _evidence(conversations=96):
    panel, p13, candidate = {}, {}, {}
    for index in range(conversations):
        conversation = f"C{index:03}"
        group = "SKWR"[index % 4]
        turns = {f"T{turn}": ["helpful", "safe"] for turn in range(4)}
        panel[conversation] = {"group": group, "turns": turns}
        verdicts = {
            turn: {"criteria": {"helpful": True, "safe": True}, "critical": False}
            for turn in turns
        }
        p13[conversation] = verdicts
        candidate[conversation] = json.loads(json.dumps(verdicts))
    return panel, p13, candidate


def _register(tmp_path, mode="dev"):
    panel, p13, candidate = _evidence(96 if mode == "dev" else 48)
    qualification_binding = {
        "campaign_id": "campaign-01",
        "run_id": "run-01",
        "archive_sha256": "8" * 64,
        "step": 13,
        "checkpoint_sha256": "a" * 64,
        "development_identity": "b" * 64,
        "development_protocol": "c" * 64,
        "final_test_sha256": "d" * 64,
        "final_calibration_sha256": "e" * 64,
        "parent": {
            "entry": {
                "model": "P13",
                "weights_sha256": "f" * 64,
                "config_sha256": "1" * 64,
                "snapshot_sha256": "2" * 64,
            }
        },
    }
    identity = {
        "model": "P13",
        "weights_sha256": "f" * 64,
        "config_sha256": "1" * 64,
        "snapshot_sha256": "2" * 64,
    }
    candidate_identity = {
        **identity,
        "model": "P13",
        "weights_sha256": qualification_binding["checkpoint_sha256"],
    }
    binding = {
        "campaign_id": "campaign-01",
        "qualification": qualification_binding,
        "p13_identity": identity,
        "candidate_identity": candidate_identity,
    }
    receipt = register_review(
        tmp_path,
        "review-0a-01",
        mode=mode,
        panel=panel,
        p13=p13,
        candidate=candidate,
        binding=binding,
        p13_identity=identity,
        candidate_identity=candidate_identity,
        reviewer_id="operator-7",
        reviewer_note="Przegląd 96 pełnych rozmów.",
    )
    return binding, receipt


def test_receipt_scores_and_verifies_exact_final_binding(tmp_path):
    binding, receipt = _register(tmp_path)

    verified = verify_review(tmp_path, receipt["review_id"], binding)

    assert verified["status"] == "PASS"
    assert verified["conversations"] == 96
    assert verified["turns"] == 384
    assert verified["groups"] == {"K": 24, "R": 24, "S": 24, "W": 24}
    assert verified["reviewer_id"] == "operator-7"
    assert len(verified["panel_sha256"]) == 64
    assert len(verified["judgments_sha256"]) == 64
    assert receipt["binding_sha256"]


def test_receipt_rejects_other_checkpoint_and_tampered_judgments(tmp_path):
    binding, receipt = _register(tmp_path)
    changed = {
        **binding,
        "qualification": {**binding["qualification"], "checkpoint_sha256": "9" * 64},
    }
    with pytest.raises(ValueError, match="binding_mismatch"):
        verify_review(tmp_path, receipt["review_id"], changed)

    judgment_path = (
        tmp_path / "conversation-reviews" / receipt["review_id"] / "judgments.json"
    )
    judgments = json.loads(judgment_path.read_text(encoding="utf-8"))
    judgments["candidate"]["C000"]["T0"]["criteria"]["helpful"] = False
    judgment_path.write_text(json.dumps(judgments), encoding="utf-8")
    with pytest.raises(ValueError, match="judgments_hash_mismatch"):
        verify_review(tmp_path, receipt["review_id"], binding)


def test_final_binding_rechecks_weights_config_snapshot_and_parent(tmp_path):
    binding, receipt = _register(tmp_path, mode="final")

    verified = verify_final_review(
        tmp_path,
        receipt["review_id"],
        binding["qualification"],
        candidate_config_sha256=binding["candidate_identity"]["config_sha256"],
    )

    assert verified["candidate_identity"] == binding["candidate_identity"]
    with pytest.raises(ValueError, match="model_binding_invalid"):
        verify_final_review(
            tmp_path,
            receipt["review_id"],
            binding["qualification"],
            candidate_config_sha256="9" * 64,
        )


@pytest.mark.parametrize(
    ("mode", "expected_path"),
    [
        ("dev", ("campaigns", "campaign-01")),
        (
            "final",
            ("local-text-qualification", "campaign-01", "evidence"),
        ),
    ],
)
def test_cli_registration_writes_where_campaign_reads(tmp_path, mode, expected_path):
    source = tmp_path / "source"
    binding, receipt = _register(source, mode=mode)
    judgments = json.loads(
        (
            source / "conversation-reviews" / receipt["review_id"] / "judgments.json"
        ).read_text(encoding="utf-8")
    )
    request = {
        "review_id": f"request-{mode}",
        "mode": mode,
        **judgments,
        "binding": binding,
        "p13_identity": binding["p13_identity"],
        "candidate_identity": binding["candidate_identity"],
        "reviewer_id": "operator-7",
        "reviewer_note": "Wynik ręcznej oceny.",
    }

    registered = register_review_request(tmp_path, request)

    assert (
        tmp_path.joinpath(*expected_path, "conversation-reviews", f"request-{mode}")
        .joinpath("receipt.json")
        .exists()
    )
    assert registered["status"] == "PASS"


def test_final_review_rejects_dev_receipt(tmp_path):
    binding, receipt = _register(tmp_path, mode="dev")

    with pytest.raises(ValueError, match="final_mode_required"):
        verify_final_review(
            tmp_path,
            receipt["review_id"],
            binding["qualification"],
            candidate_config_sha256=binding["candidate_identity"]["config_sha256"],
        )


def test_receipt_registration_is_immutable(tmp_path):
    binding, _receipt = _register(tmp_path)
    panel, p13, candidate = _evidence()
    binding["qualification"]["run_id"] = "different"
    with pytest.raises(ValueError, match="immutable_conflict"):
        register_review(
            tmp_path,
            "review-0a-01",
            mode="dev",
            panel=panel,
            p13=p13,
            candidate=candidate,
            binding=binding,
            p13_identity=binding["p13_identity"],
            candidate_identity=binding["candidate_identity"],
            reviewer_id="operator-7",
            reviewer_note="repeat",
        )


def test_required_final_gate_rejects_wrong_receipt_before_holdout_work(
    tmp_path, monkeypatch
):
    import venom_core.services.training_experiments.remote_text_qualification as qualification
    from venom_core.services.training_experiments.remote_text_qualification import (
        QualificationInputs,
        _qualify_locked,
    )

    binding, _receipt = _register(tmp_path / "evidence")
    wrong_binding = {
        **binding["qualification"],
        "checkpoint_sha256": "9" * 64,
    }
    spec = QualificationInputs(
        train=tmp_path / "train.jsonl",
        dev=tmp_path / "dev.jsonl",
        final_test=tmp_path / "final.jsonl",
        calibration=tmp_path / "calibration.json",
        snapshot=tmp_path / "snapshot",
        training_venv=tmp_path / "venv",
        max_seconds=60,
        conversation_review_required=True,
        conversation_review_id="review-0a-01",
    )
    final_dir = tmp_path / "evidence" / "final-qualification"
    final_dir.mkdir(parents=True)

    def stage_candidate(_root, _run_id, _step, checkpoint, **_kwargs):
        checkpoint.mkdir()
        return {"recipe": {}}

    monkeypatch.setattr(qualification, "_verify_parent", lambda *_args: None)
    monkeypatch.setattr(
        qualification,
        "reverify_run",
        lambda *_args: {"archive_sha256": wrong_binding["archive_sha256"]},
    )
    monkeypatch.setattr(qualification, "stage_candidate", stage_candidate)
    monkeypatch.setattr(
        qualification,
        "_adapter_identity",
        lambda *_args: {
            "model": "Omni",
            "weights_sha256": "a" * 64,
            "config_sha256": "3" * 64,
            "snapshot_sha256": "4" * 64,
        },
    )
    monkeypatch.setattr(qualification, "_stage_parent", lambda *_args: None)
    monkeypatch.setattr(
        qualification,
        "_run_final",
        lambda *_args, **_kwargs: pytest.fail("holdout evaluator must not run"),
    )

    with pytest.raises(ValueError, match="binding_mismatch"):
        _qualify_locked(
            final_dir,
            tmp_path / "evidence",
            {"plan": {"budget": {"max_artifact_bytes": 1}, "selection": {}}},
            tmp_path / "academy",
            spec,
            wrong_binding,
            lambda *_args: pytest.fail("holdout evaluator must not run"),
        )

    assert not (final_dir / "intent.json").exists()
    assert not list(final_dir.glob("*/holdout.jsonl"))


def test_campaign_profile_must_name_receipt_when_0a_gate_is_enabled():
    from venom_core.services.training_experiments.campaign_schema import (
        CampaignFinalQualification,
    )
    from venom_core.services.training_experiments.remote_text_qualification import (
        QualificationInputs,
    )

    with pytest.raises(ValueError, match="conversation_review_id_required"):
        CampaignFinalQualification(
            inputs_id="fresh",
            reserve_seconds=60,
            conversation_review_required=True,
        )
    config = CampaignFinalQualification(
        inputs_id="fresh",
        reserve_seconds=60,
        conversation_review_required=True,
        conversation_review_id="review-0a-01",
    )
    assert config.conversation_review_id == "review-0a-01"
    with pytest.raises(ValueError, match="conversation_review_id_required"):
        QualificationInputs(
            train="train",
            dev="dev",
            final_test="final",
            calibration="calibration",
            snapshot="snapshot",
            training_venv="venv",
            max_seconds=60,
            conversation_review_required=True,
        )


def test_campaign_spec_explicitly_enables_0a_review_without_changing_defaults():
    from tests.test_training_experiment_campaign import make_spec

    plain = make_spec(count=1)
    assert plain.conversation_review is None
    reviewed = make_spec(
        count=1,
        review_mode="automatic",
        retention="keep_all",
        checkpoint_steps=[2],
        quality_policy={
            "reference_record_ids": ["history:p13"],
            "parent_reference_record_id": "history:p13",
            "protect_parent_full_pass": True,
        },
        selection={
            "min_usable_delta": 0.05,
            "max_critical_delta": 0,
            "protect_parent_full_pass": True,
        },
        final_qualification={"inputs_id": "final", "reserve_seconds": 30},
        conversation_review={
            "panel_sha256": "0" * 64,
            "receipt_id_prefix": "review-0a",
        },
    )
    assert reviewed.conversation_review.receipt_id_prefix == "review-0a"


def _checkpoint_campaign(tmp_path, monkeypatch):
    from venom_core.services.training_experiments import campaign as campaign_module
    from venom_core.services.training_experiments.campaign import CampaignService

    panel, p13, candidate = _evidence()
    from venom_core.services.training_experiments.conversation_review import payload_sha

    panel_hash = payload_sha(panel)
    config_bytes = b'{"r":8,"alpha":16}'
    checkpoint_sha = "a" * 64
    config_sha = __import__("hashlib").sha256(config_bytes).hexdigest()
    snapshot_sha = "b" * 64
    dataset_sha = "c" * 64
    protocol_sha = "d" * 64
    model = "LiquidAI/LFM3-Omni-2B"
    p13_identity = {
        "model": model,
        "weights_sha256": "e" * 64,
        "config_sha256": "f" * 64,
        "snapshot_sha256": snapshot_sha,
    }
    candidate_identity = {
        "model": model,
        "weights_sha256": checkpoint_sha,
        "config_sha256": config_sha,
        "snapshot_sha256": snapshot_sha,
    }
    run_id = "campaign-0a-01"
    campaign_id = "academy-0a"
    expected_identity = {
        "model": model,
        "base_sha256": snapshot_sha,
        "dataset_sha256": dataset_sha,
        "protocol_sha256": protocol_sha,
    }
    candidate_record = {
        "identity": expected_identity,
        "source": {"sha256": "1" * 64},
        "candidate_sha256": checkpoint_sha,
    }
    parent_record = {
        "split": "dev",
        "source": {"sha256": "2" * 64},
        "candidate_sha256": p13_identity["weights_sha256"],
        "candidate_config_sha256": p13_identity["config_sha256"],
        "identity": expected_identity,
    }
    report = {
        "summaries": {
            "base": {"total": {"n": 96, "usable": 50, "critical": 0}},
            "candidate": {"total": {"n": 96, "usable": 75, "critical": 0}},
        }
    }
    fake = SimpleNamespace(root=tmp_path)
    run_dir = tmp_path / "runs" / run_id
    config_path = run_dir / "training" / "checkpoint-13" / "adapter_config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_bytes(config_bytes)
    fake.run_dir = lambda _run: run_dir
    fake.run_lock = lambda _run: nullcontext()
    fake.checkpoint_report = lambda *_args: (
        report,
        candidate_record["source"]["sha256"],
    )
    monkeypatch.setattr(
        campaign_module.quality_native,
        "native_record",
        lambda *_args: candidate_record,
    )
    monkeypatch.setattr(
        campaign_module.quality_native,
        "get_record",
        lambda *_args: parent_record,
    )
    monkeypatch.setattr(
        campaign_module.quality_guard,
        "evaluate",
        lambda _policy, _record, protocol: (
            {
                "status": "passed",
                "parent_delta": {
                    "usable_delta": 0.25,
                    "critical_delta": 0.0,
                    "full_pass_delta": 0.25,
                },
            },
            protocol,
        ),
    )
    service = CampaignService(fake)
    service._verify_quality_policy = lambda _plan: None
    plan = {
        "campaign_id": campaign_id,
        "plan_sha256": "3" * 64,
        "profile_identity": "4" * 64,
        "checkpoint_evaluation_identity": expected_identity,
        "checkpoint_steps": [13],
        "selection": {
            "min_usable_delta": 0.05,
            "max_critical_delta": 0,
            "protect_parent_full_pass": False,
        },
        "quality_policy": {"parent_reference_record_id": "history:p13"},
        "final_qualification": {"inputs_id": "final", "reserve_seconds": 30},
        "conversation_review": {
            "panel_sha256": panel_hash,
            "receipt_id_prefix": "review-0a",
        },
        "variants": [
            {
                "run_id": run_id,
                "initial_adapter": {
                    "model": p13_identity["model"],
                    "weights_sha256": p13_identity["weights_sha256"],
                    "config_sha256": p13_identity["config_sha256"],
                    "snapshot_sha256": p13_identity["snapshot_sha256"],
                },
            }
        ],
    }
    return (
        service,
        plan,
        run_id,
        panel,
        p13,
        candidate,
        p13_identity,
        candidate_identity,
    )


@pytest.mark.parametrize("tamper", ["replace", "remove"])
def test_dev_checkpoint_waits_then_rechecks_and_blocks_tampered_winner(
    tmp_path, monkeypatch, tamper
):
    from venom_core.services.training_experiments.campaign import _rank
    from venom_core.services.training_experiments.conversation_review import (
        checkpoint_review_id,
        register_review,
    )

    service, plan, run_id, panel, p13, candidate, p13_id, candidate_id = (
        _checkpoint_campaign(tmp_path, monkeypatch)
    )
    state = {
        "campaign_id": plan["campaign_id"],
        "plan": plan,
        "phase": "trials",
        "status": "succeeded",
        "training_status": "succeeded",
        "started_at": None,
        "elapsed_seconds": 0,
        "worker": None,
        "final_qualification": {"inputs_id": "final", "reserve_seconds": 30},
        "trials": [{"run_id": run_id, "status": "succeeded"}],
    }

    pending = service._assess_checkpoint(state, run_id, 13, None)
    pending["quality_guard"] = {"status": "passed"}
    state["trials"][0]["checkpoint_evaluations"] = [pending]
    _rank(state)
    assert pending["qualified"] is False
    assert pending["conversation_review_status"] == "pending"
    assert state["selected_run_id"] is None
    from venom_core.services.training_experiments.local_campaign_final import transition

    transition(state)
    assert state["status"] == "awaiting_review"
    assert state["phase"] == "trials"

    binding = pending["conversation_review_binding"]
    receipt_id = checkpoint_review_id("review-0a", run_id, 13)
    register_review(
        service.directory(plan["campaign_id"]),
        receipt_id,
        mode="dev",
        panel=panel,
        p13=p13,
        candidate=candidate,
        binding=binding,
        p13_identity=p13_id,
        candidate_identity=candidate_id,
        reviewer_id="operator-7",
        reviewer_note="Reviewed full 0A conversations.",
    )
    campaign_directory = service.directory(plan["campaign_id"])
    campaign_directory.mkdir(parents=True, exist_ok=True)
    service._save(campaign_directory, state)
    resumed = service.advance(plan["campaign_id"])

    approved = resumed["trials"][0]["checkpoint_evaluations"][0]
    assert approved["conversation_review_status"] == "pass"
    assert approved["qualified"] is True
    assert resumed["selected_run_id"] == run_id
    assert resumed["selected_checkpoint_step"] == 13
    assert resumed["phase"] == "qualification"

    receipt_path = (
        service.directory(plan["campaign_id"])
        / "conversation-reviews"
        / receipt_id
        / "receipt.json"
    )
    if tamper == "replace":
        receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_data["reviewer_note"] = "Receipt changed after PASS."
        receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")
    else:
        receipt_path.unlink()

    from venom_core.services.training_experiments.local_campaign_final import transition

    transition(copy.deepcopy(resumed), service=service)
    viewed = service.status(plan["campaign_id"])
    assert viewed["selected_run_id"] is None
    assert viewed["status"] == "blocked"
    from venom_core.services.training_experiments import local_campaign_final

    monkeypatch.setattr(
        local_campaign_final,
        "advance",
        lambda *_args: pytest.fail("final qualification must not start"),
    )
    rejected = service.advance(plan["campaign_id"])
    assert rejected["selected_run_id"] is None
    assert rejected["status"] == "blocked"
    assert rejected["error"] == "campaign_quality_conversation_review_changed"
    assert rejected.get("qualification_attempts", 0) == 0


@pytest.mark.parametrize("failure", ["hash", "panel", "p13", "candidate", "stop"])
def test_dev_checkpoint_never_selects_invalid_or_stopped_receipt(
    tmp_path, monkeypatch, failure
):
    from venom_core.services.training_experiments.campaign import _rank
    from venom_core.services.training_experiments.conversation_review import (
        checkpoint_review_id,
        register_review,
    )

    service, plan, run_id, panel, p13, candidate, p13_id, candidate_id = (
        _checkpoint_campaign(tmp_path, monkeypatch)
    )
    state = {
        "campaign_id": plan["campaign_id"],
        "plan": plan,
        "trials": [{"run_id": run_id, "status": "succeeded"}],
    }
    baseline = service._assess_checkpoint(state, run_id, 13, None)
    binding = baseline["conversation_review_binding"]
    if failure == "p13":
        p13_id = {**p13_id, "weights_sha256": "8" * 64}
        binding["p13_identity"] = p13_id
    elif failure == "candidate":
        candidate_id = {**candidate_id, "weights_sha256": "7" * 64}
        binding["candidate_identity"] = candidate_id
    elif failure == "stop":
        for key in list(candidate)[:25]:
            candidate[key]["T0"]["criteria"]["helpful"] = False
    receipt_id = checkpoint_review_id("review-0a", run_id, 13)
    register_review(
        service.directory(plan["campaign_id"]),
        receipt_id,
        mode="dev",
        panel=panel,
        p13=p13,
        candidate=candidate,
        binding=binding,
        p13_identity=p13_id,
        candidate_identity=candidate_id,
        reviewer_id="operator-7",
        reviewer_note=f"Failure fixture: {failure}.",
    )
    if failure == "panel":
        plan["conversation_review"]["panel_sha256"] = "9" * 64
    elif failure == "hash":
        judgments_path = (
            service.directory(plan["campaign_id"])
            / "conversation-reviews"
            / receipt_id
            / "judgments.json"
        )
        judgments = json.loads(judgments_path.read_text(encoding="utf-8"))
        judgments["candidate"]["C000"]["T0"]["criteria"]["safe"] = False
        judgments_path.write_text(json.dumps(judgments), encoding="utf-8")

    item = service._assess_checkpoint(state, run_id, 13, None)
    state["trials"][0]["checkpoint_evaluations"] = [item]
    _rank(state)

    assert item["qualified"] is False
    assert state["selected_run_id"] is None
    assert item["conversation_review_status"] in {"blocked", "stop"}


def test_scorer_stops_checkpoint_with_critical_error_or_lost_full_pass():
    panel, p13, candidate = _evidence()
    candidate["C000"]["T0"]["critical"] = True
    candidate["C001"]["T0"]["criteria"]["safe"] = False

    result = score("dev", panel, p13, candidate)

    assert result["status"] == "STOP"
    assert "C000/T0" in result["critical"]
    assert "C001" in result["lost"]


def test_malformed_nested_payloads_raise_conversation_review_errors(tmp_path):
    binding, receipt = _register(tmp_path)
    judgments_path = (
        tmp_path / "conversation-reviews" / receipt["review_id"] / "judgments.json"
    )
    judgments_path.write_text(json.dumps({"panel": [], "p13": {}, "candidate": {}}))
    with pytest.raises(ValueError, match="conversation_review_payload_invalid"):
        verify_review(tmp_path, receipt["review_id"], binding)

    receipt_path = (
        tmp_path / "conversation-reviews" / receipt["review_id"] / "receipt.json"
    )
    receipt_path.write_text(json.dumps(["invalid"]))
    with pytest.raises(ValueError, match="conversation_review_receipt_invalid"):
        verify_final_review(
            tmp_path,
            receipt["review_id"],
            binding["qualification"],
            candidate_config_sha256=binding["candidate_identity"]["config_sha256"],
        )


def test_review_registration_never_publishes_partial_directory(tmp_path, monkeypatch):
    import venom_core.services.training_experiments.conversation_review as review_module

    panel, p13, candidate = _evidence()
    _binding, receipt = _register(tmp_path / "seed")
    original = review_module.atomic_json
    writes = 0

    def fail_second(path, payload):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("simulated write failure")
        return original(path, payload)

    monkeypatch.setattr(review_module, "atomic_json", fail_second)
    target = tmp_path / "failed" / "conversation-reviews"
    with pytest.raises(OSError, match="simulated"):
        review_module.register_review(
            tmp_path / "failed",
            "review-0a-02",
            mode="dev",
            panel=panel,
            p13=p13,
            candidate=candidate,
            binding=receipt["binding"],
            p13_identity=receipt["p13_identity"],
            candidate_identity=receipt["candidate_identity"],
            reviewer_id="operator-7",
            reviewer_note="atomicity check",
        )
    assert not (target / "review-0a-02").exists()
