"""Guard provenance, split isolation and tool requirements in the chat suite."""

import json

import pytest

from scripts.academy.oasst2_polish_candidates import select_paths
from scripts.academy.omni_pl_chat_data import sha256, write_jsonl
from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from scripts.academy.polish_chat_quality import (
    CASES,
    capture_tool_cases,
    export_model_cases,
    export_reviewed_train,
    read_cases,
)
from scripts.academy.polish_chat_quality_report import build_report, write_report
from scripts.academy.wildchat_polish_candidates import user_candidate
from venom_core.services import studio_normal_chat


def test_quality_suite_is_complete_and_model_export_excludes_live_facts(tmp_path):
    cases = read_cases()
    assert len(cases) == 32
    assert sum(len(case["messages"]) >= 3 for case in cases) >= 12
    assert {case["capability"] for case in cases} == {"model", "web", "weather", "wiki"}
    exported = tmp_path / "model.jsonl"
    count = export_model_cases(exported)
    model_cases = [
        json.loads(line) for line in exported.read_text(encoding="utf-8").splitlines()
    ]
    assert (
        count
        == len(model_cases)
        == sum(case["capability"] == "model" for case in cases)
    )
    validate_dev_cases(model_cases)
    assert not any(
        case["record_id"]
        in {row["record_id"] for row in cases if row["capability"] != "model"}
        for case in model_cases
    )


@pytest.mark.asyncio
async def test_tool_capture_freezes_studio_context_and_source_states(
    tmp_path, monkeypatch
):
    async def fake_context(message, *, use_notes=False):
        assert not use_notes
        if "jutro rano" in message:
            return ""
        return (
            "\n[PUBLIC_SOURCES] Retrieved at: 2026-11-14T08:00:00+00:00.\n"
            "Source: https://example.org/article/1\n[/PUBLIC_SOURCES]"
        )

    monkeypatch.setattr(studio_normal_chat, "current_chat_context", fake_context)
    result = await capture_tool_cases(tmp_path / "capture")
    assert result["cases"] == 9
    directory = tmp_path / "capture"
    inputs = [
        json.loads(line)
        for line in (directory / "tool-dev.jsonl").read_text().splitlines()
    ]
    evidence = [
        json.loads(line)
        for line in (directory / "source-evidence.jsonl").read_text().splitlines()
    ]
    assert len(inputs) == len(evidence) == 9
    validate_dev_cases(inputs)
    assert all(row["messages"][0]["role"] == "system" for row in inputs)
    assert all(row["max_new_tokens"] == 384 for row in inputs)
    assert (
        next(row for row in evidence if row["record_id"] == "polchat-v1-12")[
            "history_turns"
        ]
        == 2
    )
    assert (
        next(row for row in evidence if row["record_id"] == "polchat-v1-16")[
            "source_state"
        ]
        == "not_routed"
    )
    assert any(
        row["source_urls"] == ["https://example.org/article/1"] for row in evidence
    )
    with pytest.raises(FileExistsError):
        await capture_tool_cases(directory)


def test_gpu_evaluator_rejects_case_budget_above_ceiling():
    row = read_cases()[0].copy()
    row["max_new_tokens"] = 513
    with pytest.raises(ValueError, match="generation limit"):
        validate_dev_cases([row])


def test_quality_report_checks_seals_and_separates_model_from_sources(tmp_path):
    cases = read_cases()
    model_ids = [row["record_id"] for row in cases if row["capability"] == "model"]
    tool_ids = [row["record_id"] for row in cases if row["capability"] != "model"]
    model_input = tmp_path / "model-dev.jsonl"
    write_jsonl(model_input, [row for row in cases if row["capability"] == "model"])
    capture = tmp_path / "tool-capture"
    capture.mkdir()
    tool_input = capture / "tool-dev.jsonl"
    write_jsonl(tool_input, [row for row in cases if row["capability"] != "model"])
    source = capture / "source-evidence.jsonl"
    write_jsonl(
        source,
        [
            {
                "record_id": case_id,
                "capability": "wiki",
                "route": "wiki",
                "source_state": "retrieved",
                "source_urls": ["https://example.org/article/1"],
            }
            for case_id in tool_ids
        ],
    )
    (capture / "manifest.json").write_text(
        json.dumps(
            {
                "cases_sha256": sha256(CASES),
                "tool_dev_sha256": sha256(tool_input),
                "source_evidence_sha256": sha256(source),
            }
        )
    )

    for name, path, ids in (
        ("model-eval", model_input, model_ids),
        ("tool-eval", tool_input, tool_ids),
    ):
        directory = tmp_path / name
        directory.mkdir()
        raw = directory / "raw.jsonl"
        write_jsonl(
            raw,
            [
                {
                    "case": case_id,
                    "model": variant,
                    "response": {
                        "finish": "stop",
                        "text": "Źródło: https://example.org/article/1",
                    },
                    "output_tokens": 5,
                    "elapsed_seconds": 1.2,
                }
                for variant in ("base", "checkpoint-7")
                for case_id in ids
            ],
        )
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "data_sha256": sha256(path),
                    "evaluated_ids": ids,
                    "outputs": {"raw.jsonl": sha256(raw)},
                    "models": {
                        "base": {"base": True},
                        "checkpoint-7": {"hash": "same"},
                    },
                    "snapshot_manifest_sha256": "snapshot",
                }
            )
        )

    report = write_report(tmp_path, tmp_path / "report")
    assert report["technical"]["base"]["model"]["cases"] == 23
    assert report["technical"]["base"]["with_sources"]["cases"] == 9
    assert report["identical_answers"] == {"model": 23, "with_sources": 9}
    assert report["citations"]["checkpoint-7"]["matching_source_urls"] == 9
    assert "awaiting_blind_review" in (tmp_path / "report/report.json").read_text()
    with pytest.raises(FileExistsError):
        write_report(tmp_path, tmp_path / "report")
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="source capture differs"):
        build_report(tmp_path)


def test_reviewed_training_export_rejects_unreviewed_and_eval_overlap(tmp_path):
    source = tmp_path / "reviewed.jsonl"
    output = tmp_path / "train.jsonl"
    row = {
        "record_id": "reviewed-example-01",
        "group_id": "reviewed-family-01",
        "split": "train",
        "language": "pl",
        "messages": [
            {
                "role": "user",
                "content": "Podaj prosty sposób na opisanie słoików w spiżarni.",
            },
            {
                "role": "assistant",
                "content": "Napisz zawartość i datę na papierowej etykiecie.",
            },
        ],
        "supervision": [1],
        "quality_status": "accepted",
        "source_repo": "local-authored",
        "source_revision": "test-fixture-v1",
        "source_record_id": "fixture-01",
        "license": "CC0-1.0",
        "review_note": "Fixture for exporter validation only.",
        "reviewer_id": "test-reviewer",
    }
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    assert export_reviewed_train(source, output) == 1
    assert json.loads(output.read_text(encoding="utf-8")) == row

    output.unlink()
    row["reviewer_id"] = ""
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="human review"):
        export_reviewed_train(source, output)
    assert not output.exists()

    row["reviewer_id"] = "test-reviewer"
    row["group_id"] = read_cases()[0]["group_id"]
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overlaps"):
        export_reviewed_train(source, output)


def test_wildchat_queue_keeps_only_user_prompts_and_rejects_obvious_identifiers():
    row = {
        "conversation": [
            {
                "role": "user",
                "language": "Polish",
                "content": "Jak spakować plecak na weekend?",
            },
            {
                "role": "assistant",
                "language": "Polish",
                "content": "Odpowiedź źródłowego modelu nie może trafić do nadzoru.",
            },
            {"role": "user", "language": "Polish", "content": "A gdy ma padać deszcz?"},
        ]
    }
    candidate = user_candidate(row, 0, 1, 2)
    assert candidate is not None
    assert candidate["training_eligible"] is False
    assert candidate["quality_status"] == "pending_review"
    assert candidate["user_prompts"] == [
        "Jak spakować plecak na weekend?",
        "A gdy ma padać deszcz?",
    ]
    assert "Odpowiedź źródłowego modelu" not in json.dumps(
        candidate, ensure_ascii=False
    )
    row["conversation"][2]["content"] = "Napisz do mnie na osoba@example.com"
    assert user_candidate(row, 0, 1, 2) is None


def test_oasst2_queue_keeps_one_reviewed_polish_path_per_tree():
    def row(message_id, parent_id, role, text, rank=None):
        return {
            "message_id": message_id,
            "parent_id": parent_id,
            "message_tree_id": "tree-1",
            "role": role,
            "lang": "pl",
            "text": text,
            "rank": rank,
            "review_result": True,
            "deleted": False,
            "synthetic": False,
            "user_id": "must-not-leak",
        }

    rows = [
        row("u1", None, "prompter", "Jak przygotować herbatę?"),
        row("a1", "u1", "assistant", "Zalej liście wodą.", 0),
        row("u2", "a1", "prompter", "A jak długo parzyć?"),
        row("a2", "u2", "assistant", "Kilka minut, zależnie od rodzaju.", 0),
        row("a3", "u2", "assistant", "Nie wiem.", 1),
    ]
    candidates = select_paths(rows)
    assert len(candidates) == 1
    assert candidates[0]["source_record_id"] == "a2"
    assert len(candidates[0]["messages"]) == 4
    assert candidates[0]["supervision"] == [3]
    assert candidates[0]["quality_status"] == "pending_review"
    assert candidates[0]["training_eligible"] is False
    assert "must-not-leak" not in json.dumps(candidates)

    rows[2]["lang"] = "en"
    assert select_paths(rows)[0]["source_record_id"] == "a1"

    rows[2]["lang"] = "pl"
    rows[1]["rank"] = 1
    assert select_paths(rows)[0]["review_flags"] == ["non_top_rank_context"]
