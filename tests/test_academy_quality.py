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
