"""Offline contracts for the Polish Omni pilot data and label masks."""

import json

import pytest

from scripts.academy import omni_pl_chat_data as data
from scripts.academy import omni_pl_chat_eval_cases as cases
from scripts.academy.omni_pl_chat_masks import (
    ASSISTANT_OPEN,
    EOS,
    IGNORE,
    masked_example,
)


class OffsetTokenizer:
    """One character per token, with an indivisible EOS."""

    eos_token_id = 1

    def apply_chat_template(self, messages, **options):
        return "<|startoftext|>" + "\n".join(
            (
                ASSISTANT_OPEN
                if m["role"] == "assistant"
                else f"<|im_start|>{m['role']}\n"
            )
            + m["content"]
            + EOS
            for m in messages
        )

    def __call__(self, text, **options):
        ids, offsets = [], []
        offset = 0
        while offset < len(text):
            if text.startswith(EOS, offset):
                end, token = offset + len(EOS), self.eos_token_id
            else:
                end, token = offset + 1, ord(text[offset]) + 2
            ids.append(token)
            offsets.append((offset, end))
            offset = end
        return {"input_ids": ids, "offset_mapping": offsets}

    def decode(self, ids, **options):
        return "".join(chr(token - 2) for token in ids)


def test_only_reviewed_assistant_bodies_and_eos_are_supervised():
    row = {
        "record_id": "r1",
        "messages": [
            {"role": "system", "content": "Po polsku."},
            {"role": "user", "content": "Wstęp?"},
            {"role": "assistant", "content": "Wczesna odpowiedź."},
            {"role": "user", "content": "A wynik?"},
            {"role": "assistant", "content": "Żółta łódź."},
        ],
        "supervision": [4],
    }
    tokenizer = OffsetTokenizer()
    batch = masked_example(tokenizer, "template", row, 4096)
    target = [label for label in batch["labels"] if label != IGNORE]
    assert target[-1] == tokenizer.eos_token_id
    assert tokenizer.decode(target[:-1]) == "Żółta łódź."
    assert len(batch["labels"]) == len(batch["input_ids"])
    with pytest.raises(ValueError, match="exceed limit"):
        masked_example(tokenizer, "template", row, 16)
    row["supervision"] = [3]
    with pytest.raises(ValueError, match="assistant message indices"):
        masked_example(tokenizer, "template", row, 4096)


def test_preparation_requires_explicit_review_and_rejects_split_leakage(
    tmp_path, monkeypatch
):
    prompt = {"role": "user", "content": "Gdzie jest żółta łódź?"}
    chosen = [prompt, {"role": "assistant", "content": "Przy nabrzeżu."}]
    rejected = [prompt, {"role": "assistant", "content": "Na parkingu."}]
    path = tmp_path / "ranking.jsonl"
    data.write_jsonl(
        path,
        [
            {"id": "neut-gen_20_1", "chosen": chosen, "rejected": rejected},
            {"id": "neut-gen_20_2", "chosen": chosen, "rejected": rejected},
            {"id": "polqa_q2_p1-3_1", "chosen": chosen, "rejected": rejected},
        ],
    )
    monkeypatch.setattr(data, "SOURCE_HASHES", {path.name: data.sha256(path)})
    candidates, report = data.extract_candidates(tmp_path)
    assert report["rejected"] == {
        "duplicate_chosen_transcript": 1,
        "benchmark_derived": 1,
    }
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["messages"] == chosen
    assert candidate["quality_status"] == "pending_review"
    assert candidate["group_id"] == "pllum-align-ranking-neut-gen_20"
    with pytest.raises(ValueError, match="missing review_note"):
        data.apply_reviews(candidates, [{"record_id": candidate["record_id"]}])
    accepted = data.apply_reviews(
        candidates,
        [
            {"record_id": candidate["record_id"], "review_note": "Zgodna z treścią."},
        ],
    )
    eval_row = {
        "record_id": "test-dev",
        "group_id": candidate["group_id"],
        "language": "pl",
        "split": "dev",
        "messages": [prompt],
    }
    with pytest.raises(ValueError, match="multiple splits"):
        data.validate_splits(accepted, [eval_row])
    eval_row["group_id"] = "different-group"
    with pytest.raises(ValueError, match="identical generation prompt"):
        data.validate_splits(accepted, [eval_row])
    path.write_text(json.dumps({"changed": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        data.extract_candidates(tmp_path)


def test_frozen_eval_cases_are_disjoint_and_export_without_overwriting(tmp_path):
    dev = cases.load_cases(split="dev")
    pilot = cases.load_cases(split="pilot")
    assert len(dev) == 32
    assert len(pilot) == 64
    data.validate_splits(dev, pilot)
    target = tmp_path / "pilot.jsonl"
    assert cases.write_split(target, split="pilot") == 64
    assert data.read_jsonl(target) == pilot
    with pytest.raises(FileExistsError):
        cases.write_split(target, split="dev")
