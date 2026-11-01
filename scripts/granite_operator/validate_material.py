"""CPU-only material intake: no model, optimizer, forward pass or training smoke."""

from __future__ import annotations

import argparse
import json
import shlex
from collections import Counter
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    assistant_targets,
    file_digest,
    inside,
    load_dataset,
    write_json,
)
from venom_core.services.granite_operator.encoding import collate, encode
from venom_core.services.maintenance_comparison.protocol import granite_calls


def check_receipt(row: dict, receipt: dict) -> dict:
    """Prevent fabricated observations, repeated failures and training on mistakes."""
    from jsonschema import Draft202012Validator

    schemas = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in row["tools"]
    }
    targets = assistant_targets(row)
    final_calls = row["messages"][-1].get("tool_calls", [])
    if len(final_calls) != 1 or final_calls[0]["function"]["name"] != "Finish":
        raise ValueError("material_final_finish_required")
    seen = set()
    steps = iter(receipt["steps"])
    context_only = []
    commands = []
    for index, message in enumerate(row["messages"]):
        for call in message.get("tool_calls", []):
            function = call["function"]
            Draft202012Validator(schemas[function["name"]]).validate(
                function["arguments"]
            )
            if function["name"] != "Terminal":
                continue
            command = function["arguments"]["command"]
            flags = Counter(
                word for word in shlex.split(command) if word.startswith("-")
            )
            if any(count > 1 for count in flags.values()):
                raise ValueError("material_repeated_command_flags")
            step = next(steps, None)
            if (
                step is None
                or step["command"] != command
                or step["assistant_index"] != index
            ):
                raise ValueError("material_execution_receipt_mismatch")
            expected = {
                key: step["result"][key] for key in ("stdout", "stderr", "exit_code")
            }
            observation = row["messages"][index + 1]
            if (
                observation["role"] != "tool"
                or json.loads(observation["content"]) != expected
            ):
                raise ValueError("material_fabricated_observation")
            signature = (command.strip(), step["before_state"])
            if signature in seen:
                raise ValueError("material_repeated_action_without_change")
            seen.add(signature)
            if step.get("context_only"):
                context_only.append(index)
                if index in targets:
                    raise ValueError("material_bad_prefix_is_supervised")
            commands.append(command)
    if next(steps, None) is not None or not receipt["oracle"]["passed"]:
        raise ValueError("material_receipt_or_oracle_invalid")
    available = {
        i for i, message in enumerate(row["messages"]) if message["role"] == "assistant"
    }
    if targets != available - set(context_only):
        raise ValueError("material_correct_assistant_masked")
    if sorted(row.get("context_only_assistant_indices", [])) != context_only:
        raise ValueError("material_context_metadata_mismatch")
    finish = receipt.get("finishes", {}).get(row.get("language"), receipt.get("finish"))
    if finish != row["messages"][-1]["tool_calls"][0]["function"]["arguments"]:
        raise ValueError("material_finish_not_grounded")
    return {"commands": len(commands), "context_only_assistants": len(context_only)}


def check_native_calls(row: dict, tokenizer) -> int:
    """Require every complete native envelope to decode back to the same call."""
    options = {
        "tools": row["tools"],
        "enable_thinking": False,
        "truncate_history_thinking": False,
    }
    count = 0
    for index, message in enumerate(row["messages"]):
        if not message.get("tool_calls"):
            continue
        prefix = tokenizer.apply_chat_template(
            row["messages"][:index],
            tokenize=False,
            add_generation_prompt=True,
            **options,
        )
        through = tokenizer.apply_chat_template(
            row["messages"][: index + 1],
            tokenize=False,
            add_generation_prompt=False,
            **options,
        )
        if not through.startswith(prefix):
            raise ValueError("material_native_prefix_invalid")
        calls = granite_calls(through[len(prefix) :])
        expected = [
            (c["function"]["name"], c["function"]["arguments"])
            for c in message["tool_calls"]
        ]
        if [(c.name, c.arguments) for c in calls] != expected:
            raise ValueError("material_native_call_roundtrip_invalid")
        count += len(calls)
    return count


def inspect(root: Path, manifest_path: Path, snapshot: Path) -> dict:
    """Load complete conversations, encode native targets and batch on CPU only."""
    import torch
    from transformers import AutoTokenizer

    manifest = json.loads(manifest_path.read_text())
    train, validation = load_dataset(root, manifest, "domain")
    hf_train, hf_validation = load_dataset(root, manifest, "hf")
    receipt_spec = manifest["execution_receipts"]
    receipt_path = inside(root, receipt_spec["path"])
    if file_digest(receipt_path) != receipt_spec["sha256"]:
        raise ValueError("material_receipt_hash_changed")
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    if len(receipts) != receipt_spec["rows"]:
        raise ValueError("material_receipt_count_changed")
    by_fixture = {row["fixture_id"]: row for row in receipts}
    if len(by_fixture) != len(receipts):
        raise ValueError("material_duplicate_fixture_receipt")
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    eos = tokenizer.convert_tokens_to_ids("<|im_end|>")
    encoded = []
    tokens = []
    target_tokens = []
    family_tokens = Counter()
    contexts = 0
    commands = 0
    native_calls = 0
    for row in train + validation:
        quality = check_receipt(row, by_fixture[row["fixture_id"]])
        contexts += quality["context_only_assistants"]
        commands += quality["commands"]
        item = encode(row, tokenizer, 2048)
        native_calls += check_native_calls(row, tokenizer)
        targets = assistant_targets(row)
        if item["labels"].count(eos) != len(targets):
            raise ValueError("material_assistant_end_not_supervised")
        count = sum(value != -100 for value in item["labels"])
        tokens.append(len(item["input_ids"]))
        target_tokens.append(count)
        if row["split"] == "train":
            family_tokens[row["family"]] += count
        for index in targets:
            calls = row["messages"][index].get("tool_calls", [])
            if calls and calls[0]["function"]["name"] == "Terminal":
                if (
                    len(
                        tokenizer(
                            calls[0]["function"]["arguments"]["command"],
                            add_special_tokens=False,
                        )["input_ids"]
                    )
                    > 160
                ):
                    raise ValueError("material_command_too_long")
        encoded.append(item)
    # Retention data is separate: validate its native structure, do not silently mix.
    for row in hf_train + hf_validation:
        encode(row, tokenizer, 2048)
    batch = None
    with torch.device("cpu"):
        batch = collate(encoded[:4], tokenizer.pad_token_id, torch)
    if any(value.device.type != "cpu" for value in batch.values()):
        raise RuntimeError("material_intake_must_remain_cpu_only")
    if batch["labels"].shape != batch["input_ids"].shape:
        raise ValueError("material_batch_shape_mismatch")
    total = sum(family_tokens.values())
    shares = {name: value / total for name, value in family_tokens.items()}
    if max(shares.values()) > 0.15:
        raise ValueError("material_family_target_token_imbalance")
    return {
        "status": "PASS_DATA_INTAKE_ONLY",
        "training_started": False,
        "model_loaded": False,
        "optimizer_created": False,
        "gpu_used": False,
        "manifest_sha256": file_digest(manifest_path),
        "domain_train": len(train),
        "domain_validation": len(validation),
        "hf_train_retained_separately": len(hf_train),
        "hf_validation_retained_separately": len(hf_validation),
        "context_only_assistant_occurrences": contexts,
        "terminal_occurrences": commands,
        "tokens_min": min(tokens),
        "tokens_max": max(tokens),
        "assistant_target_tokens": sum(target_tokens),
        "train_target_token_shares_by_family": shares,
        "cpu_batch_shape": list(batch["input_ids"].shape),
        "train_validation_group_overlap": 0,
        "native_eos_supervision": "PASS",
        "native_tool_calls_roundtripped": native_calls,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or args.data_root / "pilot-manifest.json"
    report = inspect(args.data_root, manifest, args.snapshot)
    write_json(args.data_root / "checks/intake.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
