"""Frozen retention conversion and lexical-oracle limits, without model inference."""

import copy
import hashlib
import json
import struct
import zlib

import pytest

from scripts.granite_operator.comparison_support import load_frozen, oracle, snapshot
from venom_core.services.gemma4_operator.retention import prepare_retention_cases

IMAGE = "sha256:" + "a" * 64


def png():
    def chunk(name, data):
        return (
            struct.pack(">I", len(data))
            + name
            + data
            + struct.pack(">I", zlib.crc32(name + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def save_source(root, rows):
    path = root / "capability-reserve/cases.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    metadata = {
        "path": "capability-reserve/cases.jsonl",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows),
        "case_ids": [row["id"] for row in rows],
        "included_in_training": False,
        "assets": {
            "shape.png": hashlib.sha256(
                (path.parent / "shape.png").read_bytes()
            ).hexdigest()
        },
    }
    (root / "manifest.json").write_text(json.dumps({"capability_reserve": metadata}))


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))
    root = tmp_path / "corpus"
    (root / "capability-reserve").mkdir(parents=True)
    image = png()
    (root / "capability-reserve/shape.png").write_bytes(image)
    common = {
        "language": "en",
        "training_allowed": False,
        "split": "capability_holdout",
        "model_evaluated": False,
    }
    rows = [
        {
            **common,
            "id": "summary-en",
            "problem_group": "summary",
            "family": "summarization",
            "prompt": "Summarize the facts",
            "input": "Service atlas: pending=3, running=2, completed=7. No tasks were cancelled.",
            "expected_facts": {
                "service": "atlas",
                "pending": 3,
                "running": 2,
                "completed": 7,
                "cancelled": 0,
            },
            "verifier_contract": "semantic_fact_preservation_and_no_unsupported_claims_v1",
        },
        {
            **common,
            "id": "translation-pl",
            "problem_group": "translation",
            "family": "translation",
            "prompt": "Translate into English",
            "language": "pl",
            "input": "Nie usuwaj pliku config/runtime.json bez zgody operatora.",
            "reference_translation": "Do not delete config/runtime.json without the operator's permission.",
            "expected_preserved_strings": ["config/runtime.json"],
            "target_language": "en",
            "verifier_contract": "translation_meaning_negation_and_identifiers_v1",
        },
        {
            **common,
            "id": "vision-en",
            "problem_group": "vision",
            "family": "vision_retention",
            "prompt": "Describe the image",
            "expected_facts": {"shape": "square", "color": "red", "count": 1},
            "image": "shape.png",
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "requires_multimodal_processor": True,
            "verifier_contract": "shape_color_count_from_grounded_pixels_v1",
        },
    ]
    save_source(root, rows)
    return root, rows, tmp_path / "comparison"


def test_conversion_is_loadable_has_no_visible_answer_files_and_never_claims_model_quality(
    source,
):
    root, rows, target = source
    original = copy.deepcopy(rows)
    path = prepare_retention_cases(root, target, sandbox_image=IMAGE)
    manifest, cases = load_frozen(path)
    assert rows == original
    assert manifest["case_count"] == 3
    assert manifest["qualification"] == {
        "status": "PASS",
        "scope": "oracle_contract_only_cpu",
        "model_qualified": False,
    }
    assert manifest["model_evaluated"] is False
    assert manifest["independent_final_benchmark"] is False
    assert manifest["diagnostic_requires_serial_comparison"] is True
    assert (
        manifest["source"]["capability_sha256"]
        == hashlib.sha256(
            (root / "capability-reserve/cases.jsonl").read_bytes()
        ).hexdigest()
    )
    for case, row in zip(cases, rows, strict=True):
        assert [tool["function"]["name"] for tool in case["tools"]] == ["Finish"]
        assert case["oracle"]["no_terminal"] is True
        visible = list((target / case["fixture"]).iterdir())
        assert {file.name for file in visible} <= {".keep", "image.png"}
        assert "reference_translation" not in case
        assert "expected_facts" not in case
        assert case["prompt"] == row["prompt"] + (
            "\n\n" + row["input"] if "input" in row else ""
        )
    assert cases[2]["images"][0]["path"] in manifest["files"]


@pytest.mark.parametrize(
    "index,good,bad",
    [
        (
            0,
            "Service atlas: pending=3, running=2, completed=7. No tasks were cancelled.",
            "Service atlas: pending=7, running=3, completed=2. No tasks were cancelled.",
        ),
        (
            1,
            "Do not delete config/runtime.json without the operator's permission.",
            "Delete config/runtime.json with permission.",
        ),
        (2, "One red square", "Two blue triangles"),
    ],
)
def test_existing_oracle_checks_observed_answer_not_its_success_status(
    source, index, good, bad
):
    root, _, target = source
    path = prepare_retention_cases(root, target, sandbox_image=IMAGE)
    _, cases = load_frozen(path)
    case = cases[index]
    workspace = target / case["fixture"]
    before = snapshot(workspace)
    assert oracle(
        case, workspace, before, [], {"status": "success", "summary": good}, [], None
    )["success"]
    assert not oracle(
        case, workspace, before, [], {"status": "success", "summary": bad}, [], None
    )["success"]
    assert not oracle(
        case,
        workspace,
        before,
        [{"command": "unexpected", "result": None}],
        {"status": "success", "summary": good},
        [],
        None,
    )["success"]


def test_output_is_immutable_and_tampered_images_are_rejected(source):
    root, _, target = source
    prepare_retention_cases(root, target, sandbox_image=IMAGE)
    with pytest.raises(FileExistsError):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)
    (target / "fixtures/vision-en/image.png").write_bytes(b"changed")
    manifest_path = target / "manifest.json"
    with pytest.raises(ValueError, match="dataset_changed"):
        load_frozen(manifest_path)


def test_changed_source_fails_before_publication(source):
    root, _, target = source
    path = root / "capability-reserve/cases.jsonl"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="source_hash_mismatch"):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)
    assert not target.exists()


@pytest.mark.parametrize(
    "change,error",
    [
        (lambda rows: rows[0].update(training_allowed=True), "reserve_policy_invalid"),
        (
            lambda rows: rows[0].update(expected_facts={"unverified": "unknown"}),
            "fact_unsupported",
        ),
        (
            lambda rows: rows[1].update(target_language="invalid"),
            "translation_language_invalid",
        ),
        (
            lambda rows: rows[2].update(requires_multimodal_processor=False),
            "image_processor_required",
        ),
        (lambda rows: rows[0].update(problem_group=""), "problem_group_required"),
    ],
)
def test_resealed_invalid_source_is_not_silently_weakened(source, change, error):
    root, rows, target = source
    change(rows)
    save_source(root, rows)
    with pytest.raises(ValueError, match=error):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)
    assert not target.exists()
    assert not list(target.parent.glob(".retention-stage-*"))


def test_source_image_hash_and_symlink_rejections_are_atomic(source):
    root, _, target = source
    image = root / "capability-reserve/shape.png"
    image.write_bytes(b"modified")
    with pytest.raises(ValueError, match="image_hash_mismatch"):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)
    assert not target.exists()
    copy = image.with_name("copy.png")
    image.rename(copy)
    image.symlink_to(copy)
    with pytest.raises(ValueError, match="source_file_invalid"):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)


def test_unpinned_sandbox_and_source_escape_are_rejected(source):
    root, _, target = source
    with pytest.raises(ValueError, match="sandbox_image_unpinned"):
        prepare_retention_cases(root, target, sandbox_image="latest")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["capability_reserve"]["path"] = "../outside.jsonl"
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="source_path_invalid"):
        prepare_retention_cases(root, target, sandbox_image=IMAGE)
