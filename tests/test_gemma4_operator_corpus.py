"""G05 preparation uses executed CPU fixtures and never rents a host or model."""

import copy
import hashlib
import json

import pytest

from venom_core.services.gemma4_operator import corpus
from venom_core.services.gemma4_operator.material import digest
from venom_core.services.gemma4_operator.paths import DATA_ROOT_ENV


@pytest.fixture(scope="module")
def executed_supplement():
    return corpus._supplement({"train": 1, "validation": 1, "holdout": 1})


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    root = tmp_path / "parent"
    root.mkdir()
    identities = {}
    manifest = {"material_version": 4, "datasets": {}}
    for split, (name, _) in corpus.G04_FILES.items():
        row = {
            "record_id": "parent-" + split,
            "problem_group": "parent:" + split,
            "split": split,
            "training_allowed": split == "train",
            "language": "pl",
            "messages": [
                {"role": "user", "content": "Parent task " + split},
                {"role": "assistant", "content": "Parent answer " + split},
            ],
            "tools": [],
            "supervised_assistant_indices": [1],
            "context_only_assistant_indices": [],
        }
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        checksum = corpus._bytes_hash(path.read_bytes())
        identities[split] = (name, checksum)
        spec = {"rows": 1, "sha256": checksum}
        if split == "holdout":
            manifest["holdout"] = spec
        else:
            manifest["datasets"][name] = spec
    (root / "pilot-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(corpus, "G04_FILES", identities)
    return root


def test_actual_fixture_calls_have_real_receipts_and_selective_error_context(
    executed_supplement,
):
    for split, rows in executed_supplement["splits"].items():
        assert len(rows) == 12
        assert {row["language"] for row in rows} == {"pl", "en"}
        for row in rows:
            assert row["training_allowed"] is (split == "train")
            assert {t["function"]["name"] for t in row["tools"]} == set(
                corpus.TOOL_NAMES
            )
            assert row["lineage"]["independent_human_review"] is False
            assert not set(row["supervised_assistant_indices"]) & set(
                row["context_only_assistant_indices"]
            )
            if row["record_id"].find("recover_missing_file") >= 0:
                assert len(row["context_only_assistant_indices"]) == 1
    all_rows = {
        row["record_id"]: row
        for rows in executed_supplement["splits"].values()
        for row in rows
    }
    assert len(executed_supplement["receipts"]) == len(all_rows)
    for receipt in executed_supplement["receipts"]:
        row = all_rows[receipt["record_id"]]
        assert receipt["trajectory_sha256"] == digest(
            {"messages": row["messages"], "tools": row["tools"]}
        )
        assert receipt["fixture_after_sha256"] == receipt["expected_state_sha256"]
        assert receipt["independent_state_check"] == "passed"
        assert receipt["network_blocked"] is True
        assert receipt["model_evaluated"] is False
        assert all(
            call["name"] in corpus.TOOL_NAMES for call in receipt["actual_tool_calls"]
        )


def test_parent_is_retained_once_and_holdout_remains_nontraining(
    source, executed_supplement, monkeypatch
):
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = corpus.prepare_corpus(
        source, groups={"train": 1, "validation": 1, "holdout": 1}
    )
    assert result["lineage"]["included_once"] is True
    assert result["lineage"]["hf_mixed"] is False
    assert all(len(rows) == 13 for rows in result["prepared"]["records"].values())
    assert all(
        row["training_allowed"] is False
        for row in result["prepared"]["records"]["holdout"]
    )
    assert before == {p: p.read_bytes() for p in before}


def test_build_release_records_hashes_and_keeps_retention_outside_training(
    source, executed_supplement, monkeypatch
):
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    output = source.parent / "g05"
    result = corpus.build_corpus(
        source, output, groups={"train": 1, "validation": 1, "holdout": 1}
    )
    for name, info in result["files"].items():
        assert corpus._bytes_hash((output / name).read_bytes()) == info["sha256"]
    assert result["prepared_manifest"]["training_ready"] is False
    assert result["training_started"] is False
    assert result["model_loaded"] is False
    reserve = result["capability_reserve"]
    assert reserve["included_in_training"] is False
    assert reserve["audio_qualified"] is False
    cases = [
        json.loads(x)
        for x in (output / reserve["path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert len(cases) == 24
    assert all(row["training_allowed"] is False for row in cases)
    assert {row["family"] for row in cases} == {
        "summarization",
        "translation",
        "vision_retention",
    }
    for case in cases:
        if "image" in case:
            image = output / "capability-reserve" / case["image"]
            assert corpus._bytes_hash(image.read_bytes()) == case["image_sha256"]
            assert image.read_bytes().startswith(b"\x89PNG")
    with pytest.raises(FileExistsError, match="output_exists"):
        corpus.build_corpus(source, output)


def test_parent_hash_change_is_not_silently_accepted(source):
    (source / "domain/train.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="parent_hash_mismatch"):
        corpus.prepare_corpus(source)


def test_parent_claim_cannot_change_the_pinned_identity(source):
    path = source / "pilot-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["datasets"]["domain/train.jsonl"]["sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="parent_hash_mismatch"):
        corpus.prepare_corpus(source)


@pytest.mark.parametrize(
    "groups",
    [
        {},
        {"train": 1},
        {"train": True, "validation": 1, "holdout": 1},
        {"train": 0, "validation": 1, "holdout": 1},
        {"train": 65, "validation": 1, "holdout": 1},
    ],
)
def test_group_budgets_are_bounded(groups):
    with pytest.raises(ValueError, match="gemma_corpus_"):
        corpus._groups(groups)


def test_subprocess_failure_does_not_claim_execution(monkeypatch):
    class Failure:
        returncode = 1
        stderr = b""

    monkeypatch.setattr(corpus.subprocess, "run", lambda *args, **kwargs: Failure())
    with pytest.raises(ValueError, match="fixture_subprocess_failed"):
        corpus._supplement({"train": 1, "validation": 1, "holdout": 1})


def test_parent_manifest_version_is_checked(source):
    path = source / "pilot-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["material_version"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="parent_version_invalid"):
        corpus.prepare_corpus(source)


def test_network_blocker_has_no_fallback():
    with pytest.raises(PermissionError, match="network_disabled"):
        corpus._deny_network(("example.invalid", 443))


def test_png_fixture_is_deterministic_and_not_a_text_training_sample():
    red = corpus._png_rectangle(255, 0, 0)
    assert (
        hashlib.sha256(red).hexdigest()
        == "b122809aebbd6402a239242eb7059587a0d54a2a2cf01cba7dd40850e99fbe22"
    )
    assert red != corpus._png_rectangle(0, 0, 255)


def test_parent_change_during_fixture_execution_is_rejected(
    source, executed_supplement, monkeypatch
):
    def mutate_source(groups):
        (source / "domain/train.jsonl").write_text("changed", encoding="utf-8")
        return copy.deepcopy(executed_supplement)

    monkeypatch.setattr(corpus, "_supplement", mutate_source)
    with pytest.raises(ValueError, match="parent_changed_during_execution"):
        corpus.prepare_corpus(
            source, groups={"train": 1, "validation": 1, "holdout": 1}
        )


def test_recipe_change_during_execution_is_rejected(
    source, executed_supplement, monkeypatch
):
    original = corpus.Path.read_bytes
    accesses = []

    def read(path):
        if path == corpus.Path(corpus.__file__):
            accesses.append(path)
            return b"recipe-before" if len(accesses) == 1 else b"recipe-after"
        return original(path)

    monkeypatch.setattr(corpus.Path, "read_bytes", read)
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    with pytest.raises(ValueError, match="recipe_changed_during_execution"):
        corpus.prepare_corpus(
            source, groups={"train": 1, "validation": 1, "holdout": 1}
        )


def test_clarification_really_has_no_service_name_before_user_reply(
    executed_supplement,
):
    for rows in executed_supplement["splits"].values():
        for row in rows:
            if "clarify_then_apply" not in row["record_id"]:
                continue
            first_user, question, reply = row["messages"][:3]
            service = reply["content"].split(";")[0]
            assert service not in first_user["content"]
            assert service in reply["content"]
            assert question["role"] == "assistant"
            assert (
                "batch identifier " in first_user["content"]
                or "identyfikator partii " in first_user["content"]
            )


def test_retention_has_bilingual_breadth_assets_and_no_audio_claim(tmp_path):
    reserve = corpus._capability_reserve(tmp_path)
    assert reserve["families"] == {
        "summarization": 8,
        "translation": 8,
        "vision_retention": 8,
    }
    assert reserve["model_neutral"] is True
    assert reserve["shared_preprocessed_tensors"] is False
    assert reserve["audio_qualified"] is False
    rows = [
        json.loads(line)
        for line in (tmp_path / reserve["path"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len({row["id"] for row in rows}) == 24
    for family in reserve["families"]:
        cases = [row for row in rows if row["family"] == family]
        assert sum(row["language"] == "pl" for row in cases) == 4
        assert sum(row["language"] == "en" for row in cases) == 4
        assert all(row["verifier_contract"] for row in cases)
        assert all(row["split"] == "capability_holdout" for row in cases)
    translations = [row for row in rows if row["family"] == "translation"]
    assert all(
        all(
            token in row["input"] and token in row["reference_translation"]
            for token in row["expected_preserved_strings"]
        )
        for row in translations
    )
    vision = [row for row in rows if row["family"] == "vision_retention"]
    assert {row["expected_facts"]["shape"] for row in vision} == {
        "square",
        "circle",
        "triangle",
        "rectangle",
    }
    assert {row["expected_facts"]["count"] for row in vision} == {1, 2}
    assert all(row["requires_multimodal_processor"] is True for row in vision)
    for name, checksum in reserve["assets"].items():
        image = tmp_path / "capability-reserve" / name
        assert image.read_bytes().startswith(b"\x89PNG")
        assert corpus._bytes_hash(image.read_bytes()) == checksum


def test_v2_lineage_binds_previous_release(source, executed_supplement, monkeypatch):
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    first_dir = source.parent / "first"
    first = corpus.build_corpus(
        source, first_dir, groups={"train": 1, "validation": 1, "holdout": 1}
    )
    second_dir = source.parent / "second"
    second = corpus.build_corpus(
        source,
        second_dir,
        groups={"train": 1, "validation": 1, "holdout": 1},
        previous_manifest=first_dir / "manifest.json",
    )
    assert second["corpus_recipe_version"] == 2
    previous = second["lineage"]["previous_g05"]
    assert previous["prepared_sha256"] == first["files"]["prepared.json"]["sha256"]
    assert previous["manifest_sha256"] == corpus._bytes_hash(
        (first_dir / "manifest.json").read_bytes()
    )


def test_previous_release_requires_same_parent(
    source, executed_supplement, monkeypatch
):
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    first_dir = source.parent / "first"
    corpus.build_corpus(
        source, first_dir, groups={"train": 1, "validation": 1, "holdout": 1}
    )
    path = first_dir / "manifest.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["lineage"]["files"] = {}
    path.write_text(json.dumps(doc), encoding="utf-8")
    lineage = {"files": {"different": "f" * 64}}
    with pytest.raises(ValueError, match="previous_release_mismatch"):
        corpus._previous_release(path, lineage)


def _profiles():
    from venom_core.services.gemma4_operator.profile import SNAPSHOT_FILES, GemmaProfile

    return {
        model: GemmaProfile(
            model=model,
            revision=("a" if model.endswith("E4B-it") else "b") * 40,
            loader="Gemma4ForConditionalGeneration"
            if model.endswith("E4B-it")
            else "Gemma4UnifiedForConditionalGeneration",
            context=4096,
            enable_thinking=False,
            files={
                name: ("c" if model.endswith("E4B-it") else "d") * 64
                for name in SNAPSHOT_FILES
            },
        )
        for model in corpus.EXPERIMENT_MODELS
    }


def test_evaluation_definition_has_separate_variant_precision_pairs(tmp_path):
    manifest = {"capability_reserve": corpus._capability_reserve(tmp_path)}
    profiles = _profiles()
    definition = corpus.evaluation_definition(manifest, profiles=profiles)
    assert definition["status"] == "PLANNED_NOT_EXECUTED"
    assert definition["model_evaluated"] is False
    assert definition["promotion_authorized"] is False
    assert definition["cross_variant_paired_accuracy_allowed"] is False
    assert definition["variant_specific_preprocessing_required"] is True
    assert len(definition["comparisons"]) == 4
    assert {c["model"] for c in definition["comparisons"]} == corpus.EXPERIMENT_MODELS
    assert len({c["profile_sha256"] for c in definition["comparisons"]}) == 2
    for comparison in definition["comparisons"]:
        assert comparison["status"] == "NOT_RUN"
        assert comparison["same_variant_required"] is True
        assert {arm["arm"] for arm in comparison["arms"]} == {"base", "adapter"}
        assert {arm["model"] for arm in comparison["arms"]} == {comparison["model"]}
        assert comparison["benchmark_sha256"] == definition["canonical_cases_sha256"]


def test_evaluation_definition_rejects_cross_variant_profile(tmp_path):
    manifest = {"capability_reserve": corpus._capability_reserve(tmp_path)}
    profiles = _profiles()
    profiles["google/gemma-4-E4B-it"] = profiles["google/gemma-4-12B-it"]
    with pytest.raises(ValueError, match="profile_mismatch"):
        corpus.evaluation_definition(manifest, profiles=profiles)


def test_evaluation_definition_requires_both_models(tmp_path):
    manifest = {"capability_reserve": corpus._capability_reserve(tmp_path)}
    with pytest.raises(ValueError, match="models_required"):
        corpus.evaluation_definition(manifest, profiles={})


def test_previous_prepared_bytes_are_verified(source, executed_supplement, monkeypatch):
    monkeypatch.setattr(
        corpus, "_supplement", lambda groups: copy.deepcopy(executed_supplement)
    )
    output = source.parent / "first"
    manifest = corpus.build_corpus(
        source, output, groups={"train": 1, "validation": 1, "holdout": 1}
    )
    (output / "prepared.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="previous_prepared_changed"):
        corpus._previous_release(output / "manifest.json", manifest["lineage"])


@pytest.mark.parametrize("checksum", ["x" * 64, "a" * 63])
def test_evaluation_manifest_hash_is_strict(tmp_path, checksum):
    manifest = {"capability_reserve": corpus._capability_reserve(tmp_path)}
    manifest["capability_reserve"]["sha256"] = checksum
    profiles = _profiles()
    with pytest.raises(ValueError, match="capability_hash_required"):
        corpus.evaluation_definition(manifest, profiles=profiles)


def test_evaluation_case_ids_cannot_be_duplicated(tmp_path):
    manifest = {"capability_reserve": corpus._capability_reserve(tmp_path)}
    manifest["capability_reserve"]["case_ids"] = ["same", "same"]
    profiles = _profiles()
    with pytest.raises(ValueError, match="capability_cases_invalid"):
        corpus.evaluation_definition(manifest, profiles=profiles)


def test_failed_fixture_retains_bounded_decodable_worker_diagnostics(monkeypatch):
    class Failure:
        returncode = 7
        stderr = b"x" * 5000 + b"\nValueError: gemma_corpus_unexpected_tool_outcome\xff"

    monkeypatch.setattr(corpus.subprocess, "run", lambda *args, **kwargs: Failure())
    groups = {"train": 1, "validation": 1, "holdout": 1}
    with pytest.raises(ValueError) as error:
        corpus._supplement(groups)
    diagnostic = str(error.value)
    assert diagnostic.startswith("gemma_corpus_fixture_subprocess_failed:exit=7:")
    assert "gemma_corpus_unexpected_tool_outcome" in diagnostic
    assert "\ufffd" in diagnostic
    assert len(diagnostic) < 2100
    assert "x" * 2001 not in diagnostic
