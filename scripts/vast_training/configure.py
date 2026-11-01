#!/usr/bin/env python3
"""Generate an Axolotl JSON/YAML-compatible SFT configuration using a local JSONL."""

import argparse
import json
import re
from pathlib import Path


def make_config(
    mode, model, revision, dataset, output, max_steps=100, sequence_len=2048
):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use an immutable, 40-character Hugging Face commit SHA")
    if max_steps <= 0 or sequence_len < 64:
        raise ValueError("Positive steps and sequence length >=64 required")
    with Path(dataset).open() as stream:
        count = 0
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("text"), str)
                or not row["text"].strip()
            ):
                raise ValueError(f"JSONL line {number} needs nonempty text")
            count += 1
    if count < 2:
        raise ValueError("At least two JSONL records required")
    value = {
        "base_model": model,
        "revision_of_model": revision,
        "datasets": [
            {
                "path": str(Path(dataset).resolve()),
                "type": "completion",
                "field": "text",
                "ds_type": "json",
            }
        ],
        "dataset_prepared_path": str(
            Path(output).resolve().parent / "prepared" / Path(output).name
        ),
        "output_dir": str(Path(output).resolve()),
        "val_set_size": 0,
        "sequence_len": sequence_len,
        "sample_packing": False,
        "micro_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "max_steps": max_steps,
        "save_steps": min(50, max_steps),
        "save_total_limit": 2,
        "logging_steps": 1,
        "bf16": True,
        "tf32": True,
        "gradient_checkpointing": True,
        "optimizer": "adamw_torch",
        "learning_rate": 2e-5 if mode == "full" else 2e-4,
        "lr_scheduler": "cosine",
        "warmup_ratio": 0.03,
        "weight_decay": 0.01,
        "flash_attention": False,
        "save_safetensors": True,
        "seed": 42,
    }
    if mode != "full":
        value.update(
            adapter=mode,
            lora_r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            lora_target_linear=True,
            load_in_4bit=(mode == "qlora"),
        )
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["lora", "qlora", "full"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--output", required=True, type=Path, help="Model/adapter output directory"
    )
    parser.add_argument(
        "--config", required=True, type=Path, help="Destination .yml config"
    )
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--sequence-len", type=int, default=2048)
    args = parser.parse_args()
    if args.config.exists():
        parser.error("Config already exists; choose a new run path")
    result = make_config(
        args.mode,
        args.model,
        args.revision,
        args.dataset,
        args.output,
        args.max_steps,
        args.sequence_len,
    )
    args.config.parent.mkdir(parents=True, exist_ok=True)
    with args.config.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(args.config)


if __name__ == "__main__":
    main()
