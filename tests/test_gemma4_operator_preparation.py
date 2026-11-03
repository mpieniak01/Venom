"""CPU session transfer contracts: exact variants, explicit inputs, no holdout."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile

import pytest

from venom_core.services.gemma4_operator import preparation
from venom_core.services.gemma4_operator.data_release import build_release
from venom_core.services.gemma4_operator.identity import (
    MODEL_TAGS,
    VARIANT_SHAPES,
    bind_ollama,
)
from venom_core.services.gemma4_operator.material import digest, prepare_material
from venom_core.services.gemma4_operator.profile import (
    MODEL_LOADERS,
    PINNED_REVISIONS,
    SNAPSHOT_FILES,
    GemmaProfile,
)
from venom_core.services.gemma4_operator.training import GemmaTrainingRecipe
from venom_core.services.remote_training.bundles import verify_bundle

CANARY = "WITHHELD_CANARY_DO_NOT_TRANSFER"


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False))


def _canonical(split):
    return {
        "record_id": split + "-case",
        "problem_group": split + "-group",
        "split": split,
        "language": "en",
        "training_allowed": split == "train",
        "tools": [],
        "messages": [
            {"role": "user", "content": split + " task"},
            {
                "role": "assistant",
                "content": CANARY if split == "holdout" else "verified answer",
            },
        ],
        "supervised_assistant_indices": [1],
        "context_only_assistant_indices": [],
    }


def _rehash(document):
    for split, rows in document["records"].items():
        for row in rows:
            row["sequence_sha256"] = digest(
                {k: v for k, v in row.items() if k != "sequence_sha256"}
            )
        document["split_summary"][split] = {
            "records": len(rows),
            "tokens": sum(len(row["input_ids"]) for row in rows),
            "supervised_tokens": sum(
                sum(token != -100 for token in row["labels"]) for row in rows
            ),
            "records_sha256": digest(rows),
        }
    document["encoded_release_sha256"] = digest(
        {k: v for k, v in document.items() if k != "encoded_release_sha256"}
    )


def _encoded(prepared, profile):
    release = build_release(prepared["records"], profile)
    records = {}
    for split in ("train", "validation"):
        source = prepared["records"][split][0]
        records[split] = [
            {
                "record_id": source["record_id"],
                "problem_group": source["problem_group"],
                "language": source["language"],
                "source_record_sha256": digest(source),
                "input_ids": [1, 5, 6, 7],
                "attention_mask": [1, 1, 1, 1],
                "labels": [-100, -100, 6, 7],
                "supervised_assistant_indices": [1],
                "assistant_token_spans": [
                    {
                        "message_index": 1,
                        "start": 2,
                        "end": 4,
                        "supervised": True,
                        "native_continuation": False,
                        "stop_token": "<turn|>",
                        "stop_token_id": 7,
                    }
                ],
            }
        ]
    result = {
        "schema_version": 1,
        "kind": "gemma4_encoded_release",
        "model_profile": profile.identity(),
        "tokenizer_identity": {
            "model": profile.model,
            "revision": profile.revision,
            "files": dict(profile.files),
            "vocabulary_size": 10,
        },
        "source_release_sha256": release["release_sha256"],
        "source_records_sha256": release["training_payload"]["records_sha256"],
        "records": records,
        "split_summary": {},
        "packing": {"enabled": False, "sequence_boundary": "one_canonical_record"},
        "mask_policy": "selected_assistant_turns_only",
    }
    _rehash(result)
    return result


@pytest.fixture(params=sorted(MODEL_LOADERS))
def inputs(request, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))
    model = request.param
    snapshot = tmp_path / "metadata"
    snapshot.mkdir()
    contents = {name: "{}" for name in SNAPSHOT_FILES}
    contents["chat_template.jinja"] = "fixture template"
    contents["config.json"] = json.dumps(
        {
            "architectures": [MODEL_LOADERS[model]],
            "text_config": {"max_position_embeddings": 4096},
        }
    )
    for name, content in contents.items():
        (snapshot / name).write_text(content)
    profile = GemmaProfile(
        model=model,
        revision=PINNED_REVISIONS[model],
        loader=MODEL_LOADERS[model],
        context=4096,
        enable_thinking=False,
        files={
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in contents.items()
        },
    )
    root = tmp_path / "corpus"
    root.mkdir()
    prepared = prepare_material(
        {s: [_canonical(s)] for s in ("train", "validation", "holdout")}
    )
    _write(root / "prepared.json", prepared)
    _write(
        root / "manifest.json",
        {
            "material_version": 5,
            "prepared_manifest": prepared["manifest"],
            "files": {
                "prepared.json": {"sha256": preparation.sha256(root / "prepared.json")}
            },
        },
    )
    encoded = _encoded(prepared, profile)
    encoded_path = tmp_path / "encoded.json"
    _write(encoded_path, encoded)
    count, layers, hidden = VARIANT_SHAPES[model]
    binding = bind_ollama(
        profile,
        {"name": MODEL_TAGS[model], "digest": "a" * 64},
        {
            "details": {
                "family": "gemma4",
                "format": "gguf",
                "quantization_level": "Q4_K_M",
            },
            "model_info": {
                "general.architecture": "gemma4",
                "general.parameter_count": count,
                "gemma4.block_count": layers,
                "gemma4.embedding_length": hidden,
            },
            "capabilities": ["completion", "vision", "tools"],
        },
    )
    binding_path = tmp_path / "binding.json"
    _write(binding_path, binding)
    return {
        "root": root,
        "snapshot": snapshot,
        "profile": profile,
        "encoded": encoded,
        "encoded_path": encoded_path,
        "binding": binding,
        "binding_path": binding_path,
        "tmp": tmp_path,
    }


def _run(inputs, **overrides):
    values = {
        "corpus_root": inputs["root"],
        "encoded_path": inputs["encoded_path"],
        "binding_path": inputs["binding_path"],
        "recipe": GemmaTrainingRecipe.for_profile(
            inputs["profile"], quantization="nf4"
        ),
        "destination": inputs["tmp"] / "session",
        "snapshot": inputs["snapshot"],
        "run_id": "fixture-run",
        "max_updates": 160,
        "max_seconds": 3600,
    }
    values.update(overrides)
    return preparation.prepare_session(**values)


@pytest.mark.parametrize("precision", ["nf4", "bf16"])
def test_session_package_is_variant_specific_and_contains_only_allowlist(
    inputs, precision
):
    before = {p: p.read_bytes() for p in inputs["root"].rglob("*") if p.is_file()}
    recipe = GemmaTrainingRecipe.for_profile(inputs["profile"], quantization=precision)
    report = _run(inputs, recipe=recipe)
    output = inputs["tmp"] / "session"
    bundle = verify_bundle(
        output / "input.zip",
        expected_identity=report["identity"],
        expected_run_id="fixture-run",
    )
    assert set(bundle["files"]) == set(preparation.INPUT_FILES)
    assert report["identity"]["model"] == inputs["profile"].model
    assert report["identity"]["revision"] == inputs["profile"].revision
    assert report["identity"]["limits"] == {"max_updates": 160, "max_seconds": 3600}
    assert (
        report["identity"]["encoding_sha256"]
        == inputs["encoded"]["encoded_release_sha256"]
    )
    assert report["identity"]["profile_sha256"] == digest(recipe.identity())
    assert report["ready_for_remote_session"] is True
    assert report["gpu_qualified"] is False
    assert report["training_started"] is False
    assert report["model_loaded"] is False
    assert report["activation_authorized"] is False
    with zipfile.ZipFile(output / "input.zip") as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            *("payload/" + name for name in preparation.INPUT_FILES),
        }
        assert (
            CANARY
            not in b"".join(archive.read(name) for name in archive.namelist()).decode()
        )
    assert all(p.read_bytes() == content for p, content in before.items())
    assert json.loads((output / "preflight.json").read_text()) == report


def test_immutable_output_cannot_be_replaced(inputs):
    _run(inputs)
    with pytest.raises(FileExistsError, match="output_exists"):
        _run(inputs)


def test_wrong_variant_recipe_is_rejected_before_publication(inputs):
    other = next(model for model in MODEL_LOADERS if model != inputs["profile"].model)
    recipe = GemmaTrainingRecipe(model=other, revision=PINNED_REVISIONS[other])
    with pytest.raises(ValueError, match="profile_mismatch"):
        _run(inputs, recipe=recipe)
    assert not (inputs["tmp"] / "session").exists()


def test_binding_profile_and_digest_must_match(inputs):
    binding = copy.deepcopy(inputs["binding"])
    binding["binding_sha256"] = "f" * 64
    _write(inputs["binding_path"], binding)
    with pytest.raises(ValueError, match="binding_identity_mismatch"):
        _run(inputs)
    assert not (inputs["tmp"] / "session").exists()


def test_other_variant_ollama_tag_cannot_be_used(inputs):
    binding = copy.deepcopy(inputs["binding"])
    other = next(model for model in MODEL_TAGS if model != inputs["profile"].model)
    binding["ollama"]["tag"] = MODEL_TAGS[other]
    _write(inputs["binding_path"], binding)
    with pytest.raises(ValueError, match="explicit_variant"):
        _run(inputs)


def test_resealed_encoding_cannot_claim_a_different_canonical_record(inputs):
    encoded = copy.deepcopy(inputs["encoded"])
    encoded["records"]["train"][0]["source_record_sha256"] = "a" * 64
    _rehash(encoded)
    _write(inputs["encoded_path"], encoded)
    with pytest.raises(ValueError, match="encoded_record_mismatch"):
        _run(inputs)
    assert not (inputs["tmp"] / "session").exists()


def test_encoded_holdout_is_rejected_even_when_document_resealed(inputs):
    encoded = copy.deepcopy(inputs["encoded"])
    encoded["records"]["holdout"] = copy.deepcopy(encoded["records"]["validation"])
    _rehash(encoded)
    _write(inputs["encoded_path"], encoded)
    with pytest.raises(ValueError, match="encoded_splits_invalid"):
        _run(inputs)


def test_canonical_hash_change_is_rejected(inputs):
    (inputs["root"] / "prepared.json").write_text("{}")
    with pytest.raises(ValueError, match="canonical_hash_mismatch"):
        _run(inputs)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_updates": True},
        {"max_updates": 257},
        {"max_updates": 0},
        {"max_seconds": True},
        {"max_seconds": 86401},
        {"run_id": "../escape"},
    ],
)
def test_invalid_budgets_fail_before_publication(inputs, changes):
    with pytest.raises(ValueError):
        _run(inputs, **changes)
    assert not (inputs["tmp"] / "session").exists()


def test_bounded_json_rejects_before_decoding(inputs, monkeypatch):
    monkeypatch.setattr(preparation, "MAX_METADATA_BYTES", 8)
    with pytest.raises(ValueError, match="metadata_too_large"):
        preparation._read(inputs["encoded_path"])


def test_pack_failure_never_publishes_ready_report(inputs, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(preparation, "create_bundle", fail)
    with pytest.raises(OSError, match="disk failure"):
        _run(inputs)
    assert (inputs["tmp"] / "session").is_dir()
    assert not (inputs["tmp"] / "session/preflight.json").exists()


def test_metadata_symlink_cannot_escape_allowlist(inputs):
    target = inputs["tmp"] / "linked.json"
    target.symlink_to(inputs["encoded_path"])
    with pytest.raises(ValueError, match="symlink"):
        _run(inputs, encoded_path=target)


EVALUATION_CANARY = "HIDDEN_EVALUATION_ORACLE_ONLY"


def _evaluation(inputs):
    root = inputs["tmp"] / "evaluation-source"
    fixture = root / "fixtures/retention"
    fixture.mkdir(parents=True)
    (fixture / ".keep").write_text("")
    image = fixture / "image.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture-pixels")
    image_hash = preparation.sha256(image)
    case = {
        "id": "retention",
        "fixture": "fixtures/retention",
        "family": "vision_retention",
        "prompt": "Describe the attached image",
        "system": "Use Finish",
        "tools": [],
        "oracle": {"status": "success", "summary_regexes": [EVALUATION_CANARY]},
        "images": [{"path": "fixtures/retention/image.png", "sha256": image_hash}],
    }
    cases = root / "cases.jsonl"
    cases.write_text(json.dumps(case) + "\n")
    manifest = {
        "cases": "cases.jsonl",
        "case_count": 1,
        "files": {
            name: preparation.sha256(root / name)
            for name in (
                "cases.jsonl",
                "fixtures/retention/image.png",
                "fixtures/retention/.keep",
            )
        },
        "sandbox_image": "sha256:" + "a" * 64,
        "qualification": {
            "status": "PASS",
            "scope": "oracle_contract_only_cpu",
            "model_qualified": False,
        },
    }
    path = root / "manifest.json"
    _write(path, manifest)
    return path


def test_separate_evaluation_bundle_preserves_training_allowlist_and_gpu_policy(inputs):
    evaluation = _evaluation(inputs)
    report = _run(inputs, evaluation_cases=evaluation)
    output = inputs["tmp"] / "session"
    training = verify_bundle(
        output / "input.zip",
        expected_identity=report["identity"],
        expected_run_id="fixture-run",
    )
    assessment = report["evaluation"]
    frozen = verify_bundle(
        output / "evaluation.zip",
        expected_identity=report["identity"],
        expected_run_id="fixture-run-eval",
    )
    assert set(training["files"]) == set(preparation.INPUT_FILES)
    assert set(frozen["files"]) == {
        "manifest.json",
        "cases.jsonl",
        "fixtures/retention/image.png",
        "fixtures/retention/.keep",
    }
    assert frozen["identity"] == training["identity"]
    assert assessment["remote_run_id"] == "fixture-run-eval"
    assert assessment["manifest_relative"] == "manifest.json"
    assert assessment["transfer_archive"] == "evaluation.zip"
    assert assessment["transfer_sha256"] == preparation.sha256(
        output / "evaluation.zip"
    )
    assert assessment["model_results_present"] is False
    assert report["ready_for_complete_remote_workflow"] is True
    assert report["evaluation_package_prepared"] is True
    assert report["status"] == "SESSION_PACKAGE_PREPARED"
    assert report["model_execution_policy"] == {
        "gpu_required": True,
        "cpu_fallback": False,
    }
    with zipfile.ZipFile(output / "input.zip") as archive:
        content = b"".join(archive.read(name) for name in archive.namelist())
        assert EVALUATION_CANARY.encode() not in content
        assert CANARY.encode() not in content
    with zipfile.ZipFile(output / "evaluation.zip") as archive:
        content = b"".join(archive.read(name) for name in archive.namelist())
        assert EVALUATION_CANARY.encode() in content
        assert CANARY.encode() not in content


def test_no_evaluation_package_is_explicitly_incomplete_for_full_workflow(inputs):
    report = _run(inputs)
    assert report["ready_for_remote_session"] is True
    assert report["ready_for_complete_remote_workflow"] is False
    assert report["evaluation_package_prepared"] is False
    assert report["evaluation"]["prepared"] is False
    assert not (inputs["tmp"] / "session/evaluation.zip").exists()


def test_corrupted_evaluation_image_rejects_before_any_package_creation(inputs):
    path = _evaluation(inputs)
    (path.parent / "fixtures/retention/image.png").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="evaluation_changed"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_asset_symlink_rejects_before_any_package_creation(inputs):
    path = _evaluation(inputs)
    image = path.parent / "fixtures/retention/image.png"
    original = image.with_name("copy.png")
    image.rename(original)
    image.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_manifest_traversal_rejects_before_any_package_creation(inputs):
    path = _evaluation(inputs)
    document = json.loads(path.read_text())
    document["files"]["../canonical-holdout.jsonl"] = "a" * 64
    _write(path, document)
    with pytest.raises(ValueError, match="path_invalid"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_fixture_traversal_is_not_normalized_away(inputs):
    path = _evaluation(inputs)
    cases_path = path.parent / "cases.jsonl"
    row = json.loads(cases_path.read_text())
    row["fixture"] = "fixtures/retention/../retention"
    cases_path.write_text(json.dumps(row) + "\n")
    document = json.loads(path.read_text())
    document["files"]["cases.jsonl"] = preparation.sha256(cases_path)
    _write(path, document)
    with pytest.raises(ValueError, match="path_invalid"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_fixture_answers_cannot_be_added_to_transfer_allowlist(inputs):
    path = _evaluation(inputs)
    answer = path.parent / "fixtures/retention/answers.json"
    _write(answer, {"answer": EVALUATION_CANARY})
    document = json.loads(path.read_text())
    document["files"]["fixtures/retention/answers.json"] = preparation.sha256(answer)
    _write(path, document)
    with pytest.raises(ValueError, match="evaluation_file_not_allowed"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_run_id_limit_is_checked_before_package_creation(inputs):
    path = _evaluation(inputs)
    with pytest.raises(ValueError, match="run_id_invalid"):
        _run(inputs, evaluation_cases=path, run_id="a" * 60)
    assert not (inputs["tmp"] / "session").exists()


def test_evaluation_pack_race_cannot_publish_a_ready_report(inputs, monkeypatch):
    path = _evaluation(inputs)
    original = preparation.create_bundle

    def changed(source, files, destination, **kwargs):
        if destination.name == "evaluation.zip":
            (source / "fixtures/retention/image.png").write_bytes(
                b"changed during pack"
            )
        return original(source, files, destination, **kwargs)

    monkeypatch.setattr(preparation, "create_bundle", changed)
    with pytest.raises(ValueError, match="changed_during_pack"):
        _run(inputs, evaluation_cases=path)
    assert not (inputs["tmp"] / "session/preflight.json").exists()
