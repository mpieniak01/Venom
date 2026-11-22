"""Verify immutable Academy quality evidence and paired experiment reasoning."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from scripts.academy.omni_pl_chat_recipe import (
    LANGUAGE_TARGET_MODULES,
    P13_LANGUAGE_SELECTOR,
    validate_recipe,
)
from scripts.academy.quality import main
from venom_core.services.training_experiments.quality import (
    QualityStore,
    analyze_quality,
    quality_record_view,
)
from venom_core.services.training_experiments.quality_history import (
    analyze_record,
    list_records,
)
from venom_core.services.training_experiments.quality_schema import (
    QualityBundle,
    QualityRecord,
)
from venom_core.services.training_experiments.service import ExperimentService


def case(category, base, candidate, *, base_critical=False, candidate_critical=False):
    return {
        "category": category,
        "base": {"usable": base, "critical": base_critical},
        "candidate": {"usable": candidate, "critical": candidate_critical},
    }


def record(record_id="run-a"):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "split": "dev",
        "identity": {
            "model": "model",
            "base_sha256": "a" * 64,
            "dataset_sha256": "b" * 64,
            "protocol_sha256": "c" * 64,
        },
        "source": {"identity": record_id, "sha256": "d" * 64, "kind": "historical"},
        "cases": {
            "a": case("asr", True, False),
            "b": case("asr", False, True, candidate_critical=None),
            "c": case("text", False, True),
        },
        "train_sha256": "e" * 64,
        "recipe": {"target_modules": ["q_proj"], "loss_mode": "strict", "rank": 8},
        "runtime": {"engine": "1.0"},
        "protected_case_ids": ["c", "a"],
    }


def test_import_is_idempotent_and_validates_sealed_record(tmp_path):
    store = QualityStore(tmp_path)
    payload = record()
    stored = store.import_record(QualityRecord.model_validate(payload))
    path = tmp_path / "quality" / "run-a.json"
    original = path.read_bytes()
    payload["protected_case_ids"].reverse()
    payload["cases"] = dict(reversed(list(payload["cases"].items())))
    assert store.import_record(payload) == stored
    assert path.read_bytes() == original
    assert store.get("run-a") == stored
    assert store.list() == ([stored], [])
    payload["source"]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="quality_record_identity_conflict"):
        store.import_record(payload)
    assert path.read_bytes() == original

    tampered = json.loads(original)
    tampered["cases"]["a"]["candidate"]["usable"] = True
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="quality_record_hash_changed"):
        store.get("run-a")


def test_corrupt_history_does_not_hide_verified_records(tmp_path):
    experiments = ExperimentService(tmp_path)
    store = QualityStore(experiments.root)
    verified = store.import_record(record("run-b"))
    tampered = store.import_record(record("run-c"))
    (store.directory / "run-a.json").write_text("{", encoding="utf-8")
    tampered["cases"]["a"]["candidate"]["usable"] = True
    (store.directory / "run-c.json").write_text(json.dumps(tampered), encoding="utf-8")

    result = list_records(experiments)

    assert result["unavailable_record_ids"] == ["history:run-a", "history:run-c"]
    assert [item["record_id"] for item in result["records"]] == ["history:run-b"]
    assert result["records"][0]["result_sha256"] == verified["result_sha256"]
    assert analyze_record(experiments, "history:run-b", None)["record"][
        "record_id"
    ] == ("history:run-b")
    with pytest.raises(json.JSONDecodeError):
        analyze_record(experiments, "history:run-a", None)
    with pytest.raises(ValueError, match="quality_record_hash_changed"):
        analyze_record(experiments, "history:run-b", "history:run-c")


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("model", "different-model", "quality_model_mismatch"),
        ("base_sha256", "f" * 64, "quality_base_mismatch"),
        ("dataset_sha256", "f" * 64, "quality_dataset_mismatch"),
        ("protocol_sha256", "f" * 64, "quality_protocol_mismatch"),
        ("protocol_sha256", None, "quality_identity_unverified"),
    ],
)
def test_comparison_requires_same_verified_identity(field, value, issue):
    candidate, peer = record(), record("run-b")
    peer["identity"][field] = value
    peer["protected_case_ids"] = ["b"]
    result = analyze_quality(candidate, peer)
    assert result["comparison_issues"] == [issue]
    assert result["comparison"] == []
    assert result["protected_case_ids"] == ["a", "c"]
    assert result["proposal"]["status"] == "insufficient_evidence"


def test_cases_and_categories_are_paired_exactly():
    candidate, peer = record(), record("run-b")
    peer["cases"]["b"]["category"] = "text"
    assert analyze_quality(candidate, peer)["comparison_issues"] == [
        "quality_category_mismatch"
    ]
    peer["cases"].pop("b")
    assert analyze_quality(candidate, peer)["comparison_issues"] == [
        "quality_case_set_mismatch"
    ]


def test_p14_proposal_translates_the_p13_selector_to_a_runnable_language_scope():
    candidate, peer = record(), record("run-b")
    candidate["recipe"] = validate_recipe({"steps": 128, "save_every": 128})
    peer["recipe"] = {**candidate["recipe"], "target_modules": P13_LANGUAGE_SELECTOR}

    proposal = analyze_quality(candidate, peer)["proposal"]

    assert proposal["status"] == "ready"
    assert proposal["factor"] == "target_modules"
    control, alternate = (
        validate_recipe(item["recipe"]) for item in proposal["variants"]
    )
    assert control.pop("target_modules") == ["q_proj", "v_proj"]
    assert alternate.pop("target_modules") == list(LANGUAGE_TARGET_MODULES)
    assert control == alternate
    assert peer["recipe"]["target_modules"] == P13_LANGUAGE_SELECTOR


@pytest.mark.parametrize(
    "selector",
    [P13_LANGUAGE_SELECTOR, list(reversed(LANGUAGE_TARGET_MODULES))],
)
def test_equivalent_language_scopes_do_not_propose_duplicate_trials(selector):
    candidate, peer = record(), record("run-b")
    candidate["recipe"] = validate_recipe(
        {"target_modules": list(LANGUAGE_TARGET_MODULES)}
    )
    peer["recipe"] = {**candidate["recipe"], "target_modules": selector}

    proposal = analyze_quality(candidate, peer)["proposal"]

    assert proposal["status"] == "insufficient_evidence"
    assert proposal["variants"] == []
    assert "quality_recipe_difference_unverified" in proposal["reasons"]


def test_case_counts_and_one_factor_proposal_use_comparable_dev_records():
    candidate, peer = record(), record("run-b")
    peer["train_sha256"] = "f" * 64
    peer["recipe"].update(target_modules=["q_proj", "v_proj"], loss_mode="standard")
    peer["protected_case_ids"] = ["a", "b"]
    peer["cases"]["a"]["candidate"]["usable"] = True
    peer["cases"]["c"]["candidate"]["usable"] = False
    candidate["outcome"] = "REVISE"

    result = analyze_quality(
        quality_record_view(candidate), QualityRecord.model_validate(peer)
    )
    assert result["decision"] == "REVISE"
    assert result["comparable"]
    assert result["summary"][0] == {
        "category": "total",
        "n": 3,
        "base_usable": 1,
        "candidate_usable": 2,
        "base_critical": 0,
        "candidate_critical": None,
        "usable_delta": 1 / 3,
        "critical_delta": None,
        "lost_usable": 1,
        "gained_usable": 2,
    }
    assert result["comparison"][1]["category"] == "asr"
    assert result["comparison"][1]["lost_usable"] == 1
    assert result["comparison"][2]["category"] == "text"
    assert result["comparison"][2]["gained_usable"] == 1
    assert result["comparison"][0]["reference_usable"] == 2
    assert result["comparison"][0]["usable_delta"] == 0
    assert result["protected_case_ids"] == ["a", "b", "c"]
    assert result["protected"] == {
        "total": 3,
        "evaluated": 3,
        "passed": 2,
        "base_passed": 1,
        "reference_passed": 2,
        "missing_case_ids": [],
        "reference_missing_case_ids": [],
    }
    findings = {item["code"]: item for item in result["findings"]}
    assert findings["quality_critical_unknown"]["case_ids"] == ["b"]
    assert findings["quality_recipe_confounded"]["fields"] == [
        "loss_mode",
        "target_modules",
        "train_sha256",
    ]
    proposal = result["proposal"]
    assert proposal["status"] == "ready"
    assert proposal["factor"] == "target_modules"
    assert proposal["fixed"] == {
        "train_sha256": candidate["train_sha256"],
        "runtime": candidate["runtime"],
    }
    assert proposal["variants"] == [
        {"name": "control", "recipe": candidate["recipe"]},
        {
            "name": "isolated",
            "recipe": {**candidate["recipe"], "target_modules": ["q_proj", "v_proj"]},
        },
    ]


def test_missing_protected_and_baseline_conflict_block_proposal():
    candidate, peer = record(), record("run-b")
    peer["recipe"]["rank"] = 16
    candidate["protected_case_ids"].append("missing")
    peer["cases"]["a"]["base"]["usable"] = False
    result = analyze_quality(candidate, peer)
    assert result["protected"]["total"] == 3
    assert result["protected"]["evaluated"] == 2
    assert result["protected"]["missing_case_ids"] == ["missing"]
    assert result["proposal"]["variants"] == []
    assert result["proposal"]["reasons"] == [
        "quality_protected_evidence_missing",
        "quality_baseline_outcomes_changed",
    ]


def test_holdout_has_report_but_cannot_offer_planning_evidence():
    candidate, peer = record(), record("run-b")
    candidate["split"] = "holdout"
    peer["split"] = "holdout"
    peer["recipe"]["rank"] = 16
    result = analyze_quality(candidate, peer)
    assert result["comparable"]
    assert result["comparison"]
    assert result["protected_case_ids"] == []
    assert result["proposal"]["status"] == "insufficient_evidence"
    assert "quality_holdout_excluded" in result["proposal"]["reasons"]
    peer["split"] = "dev"
    assert analyze_quality(candidate, peer)["comparison_issues"] == [
        "quality_split_mismatch"
    ]


def test_evidence_decisions_remain_conservative():
    candidate = record()
    assert analyze_quality(candidate)["decision"] == "INCOMPLETE"
    candidate["cases"]["b"]["candidate"]["critical"] = False
    assert analyze_quality(candidate)["decision"] == "REVISE"
    candidate["cases"]["a"]["candidate"]["usable"] = True
    assert analyze_quality(candidate)["decision"] == "GO"
    candidate["cases"]["a"]["candidate"]["critical"] = True
    assert analyze_quality(candidate)["decision"] == "STOP"
    candidate["outcome"] = "REVISE"
    assert analyze_quality(candidate)["decision"] == "REVISE"


def test_reference_cannot_mask_a_critical_regression_from_base():
    candidate, peer = record(), record("run-b")
    candidate["cases"]["a"]["candidate"]["usable"] = True
    candidate["cases"]["b"]["candidate"]["critical"] = True
    peer["cases"]["b"]["candidate"]["critical"] = True

    result = analyze_quality(candidate, peer)

    assert result["comparison"][0]["gained_usable"] == 1
    assert result["comparison"][0]["critical_delta"] == 0
    assert result["summary"][0]["critical_delta"] == 1 / 3
    assert result["decision"] == "STOP"
    findings = {item["code"]: item["case_ids"] for item in result["findings"]}
    assert findings["quality_new_critical"] == ["b"]


def test_reference_cannot_replace_missing_base_critical_evidence():
    candidate, peer = record(), record("run-b")
    candidate["cases"]["a"]["candidate"]["usable"] = True
    candidate["cases"]["b"]["base"]["critical"] = None
    candidate["cases"]["b"]["candidate"]["critical"] = False
    peer["cases"]["b"]["candidate"]["critical"] = False

    result = analyze_quality(candidate, peer)

    assert result["comparison"][0]["gained_usable"] == 1
    assert result["comparison"][0]["critical_delta"] == 0
    assert result["summary"][0]["critical_delta"] is None
    assert result["decision"] == "INCOMPLETE"
    findings = {item["code"]: item["case_ids"] for item in result["findings"]}
    assert findings["quality_critical_unknown"] == ["b"]


def test_changed_base_blocks_go_when_reference_comparison_improves():
    candidate, peer = record(), record("run-b")
    candidate["cases"]["a"]["candidate"]["usable"] = True
    candidate["cases"]["b"]["candidate"]["critical"] = False
    peer["cases"]["a"]["base"]["usable"] = False
    peer["cases"]["b"]["candidate"]["critical"] = False

    result = analyze_quality(candidate, peer)

    assert result["comparison"][0]["gained_usable"] == 1
    assert result["comparison"][0]["critical_delta"] == 0
    assert result["decision"] == "INCOMPLETE"
    findings = {item["code"]: item["case_ids"] for item in result["findings"]}
    assert findings["quality_baseline_outcomes_changed"] == ["a"]


def test_go_requires_every_protected_case_to_remain_usable():
    candidate, peer = record(), record("run-b")
    candidate["cases"]["b"]["candidate"]["critical"] = False
    peer["cases"]["b"]["candidate"] = {"usable": False, "critical": False}

    result = analyze_quality(candidate, peer)

    assert result["protected_case_ids"] == ["a", "c"]
    assert result["protected"]["evaluated"] == result["protected"]["total"] == 2
    assert result["protected"]["passed"] == result["protected"]["base_passed"] == 1
    assert result["protected"]["reference_passed"] == 1
    assert result["summary"][0]["lost_usable"] == 1
    assert result["comparison"][0]["lost_usable"] == 0
    assert result["comparison"][0]["gained_usable"] == 1
    assert result["decision"] == "REVISE"
    candidate["outcome"] = "GO"
    assert analyze_quality(candidate, peer)["decision"] == "GO"


def test_bundle_validates_version_and_unique_ids():
    first = record()
    with pytest.raises(ValidationError, match="quality_duplicate_records"):
        QualityBundle.model_validate({"schema_version": 1, "records": [first, first]})
    with pytest.raises(ValidationError, match="schema_version"):
        QualityBundle.model_validate({"schema_version": 2, "records": [first]})
    invalid = deepcopy(first)
    invalid["cases"]["a"]["candidate"]["usable"] = 1
    with pytest.raises(ValidationError, match="usable"):
        QualityRecord.model_validate(invalid)


def test_cli_import_list_show_and_analyze(tmp_path, capsys):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps({"schema_version": 1, "records": [record(), record("run-b")]}),
        encoding="utf-8",
    )
    prefix = ["--root", str(tmp_path / "experiments")]
    main([*prefix, "import", str(bundle)])
    imported = json.loads(capsys.readouterr().out)
    assert [item["record_id"] for item in imported] == ["run-a", "run-b"]
    main([*prefix, "list"])
    assert [
        item["record_id"] for item in json.loads(capsys.readouterr().out)["records"]
    ] == [
        "history:run-a",
        "history:run-b",
    ]
    main([*prefix, "show", "history:run-a"])
    assert json.loads(capsys.readouterr().out) == imported[0]
    main([*prefix, "analyze", "history:run-a", "--reference-id", "history:run-b"])
    analyzed = json.loads(capsys.readouterr().out)
    assert analyzed["comparable"]
    assert analyzed["record"]["record_id"] == "history:run-a"
    assert analyzed["reference_id"] == "history:run-b"
    assert analyzed["protected_case_ids"] == ["a", "c"]


def test_history_cohorts_keep_overlapping_case_counts_and_compare_membership(tmp_path):
    candidate, reference = record(), record("previous")
    candidate["cohorts"] = {"retention": ["b", "a"], "structured_retention": ["a"]}
    reference["cohorts"] = {"retention": ["a", "b"], "structured_retention": ["a"]}
    store = QualityStore(tmp_path)
    stored = store.import_record(candidate)
    candidate["cohorts"]["retention"].reverse()
    assert store.import_record(candidate) == stored
    assert store.get(candidate["record_id"]) == stored

    result = analyze_quality(stored, reference)
    assert result["comparable"]
    assert [(row["category"], row["n"]) for row in result["cohorts"]] == [
        ("retention", 2),
        ("structured_retention", 1),
    ]
    assert result["cohorts"][0]["candidate_critical"] is None
    assert result["cohorts"][1]["candidate_critical"] == 0
    assert result["cohort_comparison"][0]["reference_usable"] == 1

    reference["cohorts"]["structured_retention"] = ["b"]
    result = analyze_quality(stored, reference)
    assert result["comparison_issues"] == ["quality_cohort_mismatch"]
    assert result["cohort_comparison"] == []


@pytest.mark.parametrize(
    ("cohorts", "reason"),
    [
        ({}, "quality_cohorts_invalid"),
        ({"total": ["a"]}, "quality_cohorts_invalid"),
        ({"retention": []}, "quality_cohort_cases_invalid"),
        ({"retention": ["a", "a"]}, "quality_cohort_cases_invalid"),
        ({"retention": ["missing"]}, "quality_cohort_cases_invalid"),
    ],
)
def test_quality_import_rejects_invalid_cohorts(cohorts, reason):
    payload = {**record(), "cohorts": cohorts}
    with pytest.raises(ValidationError, match=reason):
        quality_record_view(payload)


def test_external_outcome_is_historical_and_keeps_old_seals(tmp_path):
    from venom_core.services.training_experiments.profiles import stable_hash

    payload = record()
    legacy = QualityRecord.model_validate(payload).model_dump(
        mode="json",
        exclude={
            "cohorts",
            "reviewed_run",
            "candidate_sha256",
            "candidate_config_sha256",
        },
    )
    for item in legacy["cases"].values():
        for role in ("base", "candidate"):
            item[role].pop("passed")
    legacy["protected_case_ids"] = sorted(legacy["protected_case_ids"])
    expected = stable_hash(legacy)
    assert quality_record_view(payload) == {**legacy, "result_sha256": expected}

    payload["reviewed_run"] = {
        "run_id": "native-run",
        "checkpoint_sha256": "2" * 64,
        "generation_manifest_sha256": "3" * 64,
    }
    with pytest.raises(ValidationError, match="quality_external_review_invalid"):
        quality_record_view(payload)

    payload["outcome"] = "REVISE"
    store = QualityStore(tmp_path)
    sealed = store.import_record(payload)
    assert sealed["result_sha256"] != expected
    assert store.get("run-a")["reviewed_run"] == payload["reviewed_run"]
    with pytest.raises(ValueError, match="quality_record_hash_changed"):
        quality_record_view(
            {**sealed, "reviewed_run": {**payload["reviewed_run"], "run_id": "other"}}
        )

    payload["source"]["kind"] = "academy"
    with pytest.raises(ValidationError, match="quality_external_review_invalid"):
        quality_record_view(payload)


def test_parent_policy_retains_hits_and_measures_real_parent():
    from venom_core.services.training_experiments.quality_guard import (
        evaluate,
        freeze_policy,
        verify_context,
    )

    ref = record("parent")
    ref["cases"] = {
        "a": case("source", False, True),
        "b": case("source", False, False),
        "c": case("source", True, False),
    }
    ref["candidate_sha256"] = "f" * 64
    ref["protected_case_ids"] = []
    ref = quality_record_view(ref)
    settings = {
        "reference_record_ids": ["parent"],
        "parent_reference_record_id": "parent",
        "protected_case_ids": [],
        "protect_reference_hits": False,
        "protect_base_hits": False,
        "min_category_usable_delta": {"source": 0.0},
        "no_new_critical": True,
    }
    context = {
        "identity": ref["identity"],
        "case_categories": dict.fromkeys(ref["cases"], "source"),
        "initial_adapter_sha256": "f" * 64,
    }
    policy = freeze_policy(settings, context, lambda _: ref)
    assert policy["protected_case_ids"] == ["a"]
    candidate = {
        **ref,
        "cases": {
            "a": case("source", False, True),
            "b": case("source", False, True),
            "c": case("source", True, False),
        },
    }
    result, _ = evaluate(policy, candidate, None)
    assert result["status"] == "passed"
    assert result["parent_delta"]["usable_delta"] == pytest.approx(1 / 3)
    assert result["category_deltas"]["source"]["base"] == 1
    candidate["cases"]["a"]["candidate"]["usable"] = False
    result, _ = evaluate(policy, candidate, None)
    assert result["lost_case_ids"] == ["a"]
    assert result["parent_delta"]["usable_delta"] == 0
    candidate["cases"]["c"]["base"]["critical"] = True
    candidate["cases"]["c"]["candidate"]["critical"] = True
    result, _ = evaluate(policy, candidate, None)
    assert result["new_critical_case_ids"] == ["c"]
    with pytest.raises(ValueError, match="parent_adapter_changed"):
        freeze_policy(
            settings, {**context, "initial_adapter_sha256": "e" * 64}, lambda _: ref
        )
    with pytest.raises(ValueError, match="parent_adapter_changed"):
        verify_context(policy, {**context, "initial_adapter_sha256": "e" * 64})
    with pytest.raises(ValueError, match="parent_reference_missing"):
        freeze_policy({**settings, "reference_record_ids": []}, context, lambda _: ref)


def test_dialogue_summary_preserves_pairs_and_requires_independent_open_chat_review():
    from scripts.academy.omni_pl_chat_dialogue import grouped_scores, paired_delta

    cases = [
        {
            "record_id": f"t{i}",
            "group_id": f"family-{i // 2}",
            "dialogue": {"id": "d1" if i < 2 else "d2", "turn_index": i % 2 + 1},
            "chat_group": "W" if i < 2 else "K",
            "contrast_pair_id": "pair",
            "decision": "accepted" if i % 2 else "rejected",
        }
        for i in range(4)
    ]
    cases[2]["contrast_pair_id"] = cases[3]["contrast_pair_id"] = "pair2"
    verdicts = {
        "candidate": {
            row["record_id"]: {"usable": int(index != 1), "passed": int(index != 1)}
            for index, row in enumerate(cases)
        }
    }
    summary = grouped_scores(cases, verdicts, {"candidate": ["t1"]})["candidate"]
    assert summary["conversations"]["d1"]["assessment"] == "independent_review_required"
    assert summary["conversations"]["d1"]["critical_case_ids"] == ["t1"]
    assert summary["conversations"]["d2"]["all_turns_usable"]
    assert not summary["contrast_pairs"]["pair"]["both_usable"]
    assert summary["contrast_pairs"]["pair2"]["both_usable"]
    result = paired_delta([0, 0, 1, 1], [1, 1, 1, 1], ["x", "x", "y", "y"])
    assert result == paired_delta([0, 0, 1, 1], [1, 1, 1, 1], ["x", "x", "y", "y"])
    assert result["gains"] == 2
    assert result["losses"] == 0
    assert result["family_bootstrap"]["families"] == 2
    assert result["family_bootstrap"]["interval_95"] == [0.0, 1.0]
    with pytest.raises(ValueError, match="coverage"):
        paired_delta([0], [1], [])
    with pytest.raises(ValueError, match="equal nonempty"):
        paired_delta([], [])


def test_whole_dialogue_pair_requires_both_complete_branches():
    from scripts.academy.omni_pl_chat_dialogue import grouped_scores

    cases = [
        {
            "record_id": f"{branch}-{turn}",
            "group_id": "paired-family",
            "dialogue": {"id": branch, "turn_index": turn},
            "decision": branch,
            "chat_group": "K",
        }
        for branch in ("accepted", "rejected")
        for turn in range(1, 5)
    ]
    verdicts = {
        "candidate": {row["record_id"]: {"usable": 1, "passed": 1} for row in cases}
    }
    family = grouped_scores(cases, verdicts, {})["candidate"]["dialogue_families"][
        "paired-family"
    ]
    assert family["contrast_pair_complete"]
    assert family["both_conversations_usable"]
    verdicts["candidate"]["rejected-3"]["usable"] = 0
    family = grouped_scores(cases, verdicts, {})["candidate"]["dialogue_families"][
        "paired-family"
    ]
    assert family["contrast_pair_complete"]
    assert not family["both_conversations_usable"]
    cases[0]["decision"] = "rejected"
    family = grouped_scores(cases, verdicts, {})["candidate"]["dialogue_families"][
        "paired-family"
    ]
    assert not family["contrast_pair_complete"]


@pytest.mark.parametrize(
    ("candidate_passes", "status", "reason"),
    [
        ([True, True, True], "passed", None),
        ([True, False, False], "rejected", "parent_full_pass_no_gain"),
        ([False, True, True], "rejected", "parent_full_pass_lost"),
    ],
)
def test_parent_full_pass_guard_cannot_exchange_format_for_usable_gain(
    candidate_passes, status, reason
):
    from venom_core.services.training_experiments.quality_guard import (
        evaluate,
        freeze_policy,
    )

    ref = record("parent")
    ref["candidate_sha256"] = "f" * 64
    ref["protected_case_ids"] = []
    ref["cases"] = {
        key: {
            "category": "source",
            "base": {"usable": False, "critical": False},
            "candidate": {"usable": index < 2, "critical": False, "passed": index == 0},
        }
        for index, key in enumerate(("a", "b", "c"))
    }
    ref = quality_record_view(ref)
    settings = {
        "reference_record_ids": ["parent"],
        "parent_reference_record_id": "parent",
        "protected_case_ids": [],
        "protect_reference_hits": True,
        "protect_base_hits": False,
        "protect_parent_full_pass": True,
        "min_category_usable_delta": {},
        "no_new_critical": True,
    }
    context = {
        "identity": ref["identity"],
        "case_categories": dict.fromkeys(ref["cases"], "source"),
        "initial_adapter_sha256": "f" * 64,
    }
    policy = freeze_policy(settings, context, lambda _: ref)
    current = deepcopy(ref)
    for (key, row), passed in zip(
        current["cases"].items(), candidate_passes, strict=True
    ):
        row["candidate"] = {"usable": True, "critical": False, "passed": passed}
    decision, _ = evaluate(policy, current, None)
    assert decision["status"] == status
    assert decision["parent_delta"]["usable_delta"] == pytest.approx(1 / 3)
    assert decision["full_pass_delta"] == pytest.approx((sum(candidate_passes) - 1) / 3)
    if reason:
        assert reason in {item["code"] for item in decision["reasons"]}
    assert decision["lost_parent_full_pass_case_ids"] == (
        [] if candidate_passes[0] else ["a"]
    )
    current["cases"]["b"]["candidate"].pop("passed")
    with pytest.raises(ValueError, match="case_evidence_missing"):
        evaluate(policy, current, None)
    ref["cases"]["b"]["candidate"].pop("passed")
    with pytest.raises(ValueError, match="case_evidence_missing"):
        freeze_policy(settings, context, lambda _: ref)


def test_full_pass_cannot_be_true_for_an_unusable_or_critical_outcome():
    payload = record()
    payload["cases"]["a"]["candidate"]["passed"] = True
    with pytest.raises(ValidationError, match="full_pass_requires_usable"):
        quality_record_view(payload)
    payload["cases"]["a"]["candidate"].update(usable=True, critical=True)
    with pytest.raises(ValidationError, match="full_pass_requires_usable"):
        quality_record_view(payload)


def test_dialogue_null_rejected_before_generation_and_absent_field_supported():
    from scripts.academy.omni_pl_chat_dialogue import validate_dialogues

    validate_dialogues([{"messages": [{"role": "user", "content": "hello"}]}])
    with pytest.raises(ValueError, match="invalid dialogue identity"):
        validate_dialogues([{"dialogue": None}])


@pytest.mark.parametrize(
    "parent_unknown,candidate_unknown", [(True, False), (False, True), (True, True)]
)
def test_unknown_critical_metrics_remain_unavailable(parent_unknown, candidate_unknown):
    from venom_core.services.training_experiments.quality_guard import (
        _decisions,
        _parent_delta,
    )

    reference = {"usable": True, "critical": None if parent_unknown else False}
    policy = {
        "protected_case_ids": [],
        "protect_base_hits": False,
        "no_new_critical": False,
        "parent_cases": {"a": reference},
        "parent_reference_record_id": "prior",
    }
    cases = {
        "a": case(
            "text", True, True, candidate_critical=None if candidate_unknown else False
        )
    }
    assert _decisions(policy, cases)[1] == []
    assert _parent_delta(policy, cases)["critical_delta"] is None
    policy["no_new_critical"] = True
    with pytest.raises(ValueError, match="case_evidence_missing"):
        _decisions(policy, cases)


def diagnostic_input():
    return {
        "role": "chat",
        "dataset_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "min_families": 2,
        "cases": {
            "a": {"area": "sources", "level": "P2", "family": "pair"},
            "b": {"area": "sources", "level": "P2", "family": "pair"},
            "c": {"area": "sources", "level": "P2", "family": "independent"},
        },
    }


def test_diagnose_sealed_record_counts_families_and_keeps_unknown(tmp_path, capsys):
    quality = record()
    quality["cases"]["a"] = case("asr", True, False, candidate_critical=True)
    quality["cases"]["b"] = case("asr", True, True, candidate_critical=None)
    for row in quality["cases"].values():
        row["base"]["passed"] = row["base"]["usable"]
        row["candidate"]["passed"] = row["candidate"]["usable"]
    quality["cases"]["c"]["candidate"]["passed"] = None

    verified = QualityStore(tmp_path).import_record(quality)
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps(diagnostic_input()), encoding="utf-8")
    main(["--root", str(tmp_path), "diagnose", "history:run-a", str(matrix)])
    result = json.loads(capsys.readouterr().out)
    assert result["result_sha256"] == verified["result_sha256"]
    assert result["identity"] == quality["identity"]
    assert len(result["matrix_sha256"]) == 64
    assert len(result["cells"]) == 9
    diagnostic = next(
        row
        for row in result["cells"]
        if (row["area"], row["level"]) == ("sources", "P2")
    )
    assert (diagnostic["cases"], diagnostic["families"], diagnostic["status"]) == (
        3,
        2,
        "REVIEW",
    )
    assert diagnostic["usable"]["changed_to_true"] == ["independent"]
    assert diagnostic["usable"]["changed_to_false"] == ["pair"]
    assert diagnostic["passed"]["candidate"]["known"] == 1
    assert diagnostic["critical"]["changed_to_true"] == ["pair"]
    assert diagnostic["critical"]["candidate"]["known"] == 2
    assert diagnostic["usable"]["candidate"]["interval_95"] == pytest.approx(
        [0.09453, 0.90547], abs=1e-5
    )
    assert result["cells"][0]["passed"]["candidate"]["interval_95"] is None
    assert result["cells"][0]["status"] == "REVIEW"

    quality["record_id"] = "complete"
    quality["cases"]["c"]["candidate"]["passed"] = True
    QualityStore(tmp_path).import_record(quality)
    main(["--root", str(tmp_path), "diagnose", "history:complete", str(matrix)])
    result = json.loads(capsys.readouterr().out)
    assert (
        next(row for row in result["cells"] if row["families"])["status"] == "measured"
    )


@pytest.mark.parametrize(
    "problem,error",
    [
        ("holdout", "diagnostic_dev_required"),
        ("dataset_sha256", "diagnostic_identity_mismatch"),
        ("protocol_sha256", "diagnostic_identity_mismatch"),
        ("missing_case", "diagnostic_case_coverage"),
        ("wrong_role", "diagnostic_area_outside_role"),
        ("unknown_level", "literal_error"),
    ],
)
def test_diagnose_rejects_incompatible_evidence(tmp_path, capsys, problem, error):
    quality = record()
    manifest = diagnostic_input()
    if problem == "holdout":
        quality["split"] = "holdout"
    elif problem in {"dataset_sha256", "protocol_sha256"}:
        manifest[problem] = "f" * 64
    elif problem == "missing_case":
        manifest["cases"].pop("c")
    elif problem == "wrong_role":
        manifest["role"] = "decision"
    else:
        manifest["cases"]["c"]["level"] = "P4"
    QualityStore(tmp_path).import_record(quality)
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(["--root", str(tmp_path), "diagnose", "history:run-a", str(matrix)])
    assert exc.value.code == 1
    assert error in capsys.readouterr().err
