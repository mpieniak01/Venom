"""Integrity tests for the blinded conversation-review package."""

import json

import pytest

from scripts.academy.omni_pl_chat_dialogue import DialogueHistory, blind_answer
from scripts.academy.omni_pl_chat_evaluate import blind_mapping
from venom_core.services.training_experiments.checkpoint_evaluation import (
    seal_generation,
)
from venom_core.services.training_experiments.conversation_blind import (
    prepare_blind_package,
)
from venom_core.services.training_experiments.conversation_review import payload_sha
from venom_core.services.training_experiments.profiles import (
    digest,
    read_json,
    stable_hash,
)


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _generation(path, cases, dataset_hash, identity, step):
    path.mkdir()
    tag = f"checkpoint-{step}"
    models = {
        "base": {"base": True},
        tag: {
            "adapter_config.json": identity["config_sha256"],
            "adapter_model.safetensors": identity["weights_sha256"],
        },
    }
    mapping = blind_mapping(cases, list(models))
    raw, blind = [], []
    histories = {model: DialogueHistory() for model in models}
    for case in cases:
        answers = {}
        for label, model in mapping[case["record_id"]].items():
            history = histories[model]
            context = history.context(case)
            row = {
                "case": case["record_id"],
                "model": model,
                "label": label,
                "response": {
                    "text": f"Answer {model}",
                    "finish": "stop",
                    "error": None,
                },
                **context,
            }
            history.remember(case, row, context)
            raw.append(row)
            answers[label] = blind_answer(row)
        blind.append({"case": case, "answers": answers})
    for name, rows in (("raw.jsonl", raw), ("blind.jsonl", blind)):
        (path / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    _write(path / "unblind.json", mapping)
    _write(
        path / "manifest.json",
        {
            "models": models,
            "model_repo": identity["model"],
            "snapshot_manifest_sha256": identity["snapshot_sha256"],
            "data_sha256": dataset_hash,
            "evaluated_ids": [case["record_id"] for case in cases],
            "max_new_tokens": 512,
            "case_max_new_tokens": {case["record_id"]: 512 for case in cases},
            "dialogue_protocol": "own-history-v1",
            "outputs": {
                name: digest(path / name)
                for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
            },
        },
    )
    seal_generation(path)
    return read_json(path / "generation-seal.json")


@pytest.fixture
def input_data(tmp_path):
    panel, cases = {}, []
    for i in range(96):
        conversation, group = f"C{i:03}", "SKWR"[i % 4]
        panel[conversation] = {
            "group": group,
            "turns": {f"T{j}": ["content"] for j in range(1, 5)},
        }
        for turn in range(1, 5):
            cases.append(
                {
                    "record_id": f"{conversation}-{turn}",
                    "group_id": conversation,
                    "review_group": group,
                    "dialogue": {"id": conversation, "turn_index": turn},
                    "messages": [{"role": "user", "content": f"Question {turn}"}],
                    "criteria": [
                        {"id": "content", "kind": "content", "description": "Answer"}
                    ],
                }
            )
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in cases))
    parent = {
        "model": "omni",
        "weights_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
    }
    candidate = {**parent, "weights_sha256": "d" * 64}
    pdir, cdir = tmp_path / "parent", tmp_path / "candidate"
    pseal = _generation(pdir, cases, digest(dataset), parent, 145)
    _generation(cdir, cases, digest(dataset), candidate, 21)
    _write(
        cdir / "result.json",
        {
            "run_id": "run",
            "checkpoint": {"step": 21, "sha256": candidate["weights_sha256"]},
            "generation_sha256": digest(cdir / "generation-seal.json"),
        },
    )
    binding = {
        "panel_sha256": payload_sha(panel),
        "development_identity": {"dataset_sha256": digest(dataset)},
        "p13_identity": parent,
        "candidate_identity": candidate,
        "p13_record_sha256": stable_hash(pseal),
        "checkpoint_result_sha256": digest(cdir / "result.json"),
        "run_id": "run",
        "step": 21,
    }
    pending = {
        "conversation_review_status": "pending",
        "conversation_review_id": "review-01",
        "conversation_review_binding": binding,
    }
    return pending, panel, dataset, pdir, cdir


def test_blind_package_binds_sealed_own_history(input_data):
    package, private = prepare_blind_package(*input_data)
    assert len(package["conversations"]) == 96
    assert set(package["conversations"]["C000"]["turns"]["T1"]["answers"]) == {"A", "B"}
    assert "p13" not in json.dumps(package)
    assert private["package_sha256"] == stable_hash(package)
    assert sorted(private["aliases"]["C000"].values()) == ["candidate", "p13"]


@pytest.mark.parametrize(
    "damage", ["panel", "dataset", "parent", "candidate", "result"]
)
def test_blind_package_rejects_changed_evidence(input_data, damage):
    pending, panel, dataset, parent, candidate = input_data
    if damage == "panel":
        panel["C000"]["turns"]["T1"] = ["other"]
    elif damage == "dataset":
        dataset.write_text(dataset.read_text() + " ")
    elif damage == "parent":
        (parent / "raw.jsonl").write_text("{}")
    elif damage == "candidate":
        (candidate / "blind.jsonl").write_text("{}")
    else:
        (candidate / "result.json").write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        prepare_blind_package(pending, panel, dataset, parent, candidate)


def test_cli_publishes_only_anonymous_review_and_private_mapping(
    input_data, tmp_path, capsys
):
    from scripts.academy.conversation_blind import main

    pending, panel, dataset, parent, candidate = input_data
    pending_path, panel_path = tmp_path / "pending.json", tmp_path / "panel.json"
    _write(pending_path, pending)
    _write(panel_path, panel)
    output = tmp_path / "package"
    args = [
        "--pending",
        str(pending_path),
        "--panel",
        str(panel_path),
        "--dataset",
        str(dataset),
        "--parent",
        str(parent),
        "--candidate",
        str(candidate),
        "--output",
        str(output),
    ]
    main(args)
    review, private = (
        read_json(output / "reviewer.json"),
        read_json(output / "private.json"),
    )
    assert private["package_sha256"] == stable_hash(review)
    assert "aliases" not in json.dumps(review)
    assert "Question 1" in json.dumps(review)
    assert "candidate" not in capsys.readouterr().out
    assert (output.stat().st_mode & 0o777) == 0o700
    before = (output / "reviewer.json").read_bytes()
    with pytest.raises(SystemExit):
        main(args)
    assert (output / "reviewer.json").read_bytes() == before


def test_blind_package_rejects_different_generation_protocol(input_data):
    pending, panel, dataset, parent, candidate = input_data
    manifest_path = parent / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["seed"] = 17
    _write(manifest_path, manifest)
    seal_generation(parent)
    pending["conversation_review_binding"]["p13_record_sha256"] = stable_hash(
        read_json(parent / "generation-seal.json")
    )
    with pytest.raises(ValueError, match="generation_protocol_mismatch"):
        prepare_blind_package(pending, panel, dataset, parent, candidate)


def test_blind_package_rejects_different_history_after_resealing(input_data):
    pending, panel, dataset, parent, candidate = input_data
    raw_path = candidate / "raw.jsonl"
    rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
    row = next(
        row
        for row in rows
        if row["case"] == "C000-2" and row["model"] == "checkpoint-21"
    )
    row["input_messages"][0]["content"] = "Different history"
    raw_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest_path = candidate / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["outputs"]["raw.jsonl"] = digest(raw_path)
    _write(manifest_path, manifest)
    seal_generation(candidate)
    result_path = candidate / "result.json"
    result = read_json(result_path)
    result["generation_sha256"] = digest(candidate / "generation-seal.json")
    _write(result_path, result)
    pending["conversation_review_binding"]["checkpoint_result_sha256"] = digest(
        result_path
    )
    with pytest.raises(ValueError):
        prepare_blind_package(pending, panel, dataset, parent, candidate)
