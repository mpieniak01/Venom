"""Audit supervision against the pinned LFM3 Omni text template."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from statistics import median

from scripts.academy.omni_pl_chat_data import (
    read_jsonl,
    sha256,
    validate_messages,
    validate_splits,
    validate_supervision,
    write_jsonl,
)

IGNORE = -100
EOS = "<|im_end|>"
ASSISTANT_OPEN = "<|im_start|>assistant\n<think></think>"
SNAPSHOT_PIN = Path(__file__).resolve().parents[1] / "llm" / "omni_native_snapshot.json"
TEXT_FILES = (
    "chat_template.jinja",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
)


def verify_snapshot(snapshot: Path, *, full: bool = False) -> dict:
    pin = json.loads(SNAPSHOT_PIN.read_text(encoding="utf-8"))
    root = snapshot.resolve()
    for name in pin["files"] if full else TEXT_FILES:
        path = root / name
        expected = pin["files"][name]
        if (
            path.resolve() != path
            or not path.is_file()
            or path.stat().st_size != expected["size"]
            or sha256(path) != expected["sha256"]
        ):
            raise ValueError(f"snapshot differs from the pinned model: {name}")
    return pin


def render(
    tokenizer, template: str, messages: list[dict], *, generation: bool = False
) -> str:
    return tokenizer.apply_chat_template(
        messages,
        chat_template=template,
        tokenize=False,
        add_generation_prompt=generation,
        enable_thinking=False,
    )


def masked_example(tokenizer, template: str, row: dict, max_tokens: int) -> dict:
    """Supervise the selected assistant bodies and their EOS, using token offsets."""
    messages = row["messages"]
    supervision = row["supervision"]
    validate_messages(messages, "assistant")
    validate_supervision(messages, supervision)
    rendered = render(tokenizer, template, messages)
    encoded = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    input_ids = encoded["input_ids"]
    if len(input_ids) > max_tokens:
        raise ValueError(
            f"{row['record_id']}: {len(input_ids)} tokens exceed limit {max_tokens}"
        )
    labels = [IGNORE] * len(input_ids)
    position = 0
    if rendered.count(ASSISTANT_OPEN) != sum(
        msg["role"] == "assistant" for msg in messages
    ):
        raise ValueError("vendor template changed assistant delimiters")
    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        start = rendered.index(ASSISTANT_OPEN, position) + len(ASSISTANT_OPEN)
        eos_start = rendered.index(EOS, start)
        end = eos_start + len(EOS)
        position = end
        if rendered[start:eos_start] != message["content"]:
            raise ValueError(f"{row['record_id']}: template altered assistant content")
        if index not in supervision:
            continue
        indices = [
            i
            for i, (left, right) in enumerate(encoded["offset_mapping"])
            if left < end and right > start
        ]
        if not indices or any(
            encoded["offset_mapping"][i][0] < start
            or encoded["offset_mapping"][i][1] > end
            for i in indices
        ):
            raise ValueError(f"{row['record_id']}: token crosses an assistant boundary")
        target = [input_ids[i] for i in indices]
        if (
            len(target) < 2
            or target[-1] != tokenizer.eos_token_id
            or tokenizer.decode(
                target[:-1],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            ).strip()
            != message["content"].strip()
        ):
            raise ValueError(f"{row['record_id']}: target or EOS failed round-trip")
        for i in indices:
            labels[i] = input_ids[i]
    return {
        "input_ids": input_ids,
        "labels": labels,
        "attention_mask": [1] * len(input_ids),
    }


def audit(
    snapshot: Path, records: list[dict], max_tokens: int
) -> tuple[list[dict], dict]:
    from transformers import AutoTokenizer

    pin = verify_snapshot(snapshot)
    validate_splits(records)
    if any(row["split"] != "train" for row in records):
        raise ValueError("mask audit requires approved training records")
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    template = (snapshot / "chat_template.jinja").read_text(encoding="utf-8")
    observations = []
    for row in records:
        encoded = masked_example(tokenizer, template, row, max_tokens)
        observations.append(
            {
                "record_id": row["record_id"],
                "tokens": len(encoded["input_ids"]),
                "supervised": sum(label != IGNORE for label in encoded["labels"]),
                "target_turns": len(row["supervision"]),
            }
        )
    counts = [item["tokens"] for item in observations]
    return observations, {
        "repo": pin["repo"],
        "revision": pin["revision"],
        "files": {name: pin["files"][name] for name in TEXT_FILES},
        "transformers": version("transformers"),
        "tokenizers": version("tokenizers"),
        "records": len(records),
        "max_tokens": max_tokens,
        "min_input_tokens": min(counts),
        "median_input_tokens": median(counts),
        "max_input_tokens": max(counts),
        "supervised_tokens": sum(item["supervised"] for item in observations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=1024)
    args = parser.parse_args()
    observations, report = audit(args.snapshot, read_jsonl(args.train), args.max_tokens)
    report["train_sha256"] = sha256(args.train)
    args.output.mkdir(parents=True, exist_ok=False)
    write_jsonl(args.output / "masks.jsonl", observations)
    (args.output / "manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
