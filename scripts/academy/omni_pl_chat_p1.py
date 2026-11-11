"""Run the small Omni text LoRA and checkpoint-resume qualification in isolation."""

import argparse
import hashlib
import json
import math
import os
import resource
import sys
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from scripts.academy.omni_pl_chat_data import read_jsonl, sha256, validate_splits
from scripts.academy.omni_pl_chat_masks import IGNORE, masked_example, verify_snapshot

STEPS = 8
SAVE_EVERY = 2
SEED = 42
MAX_TOKENS = 1024
LR = 2e-4
CHECKPOINT_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "optimizer.pt",
    "scheduler.pt",
    "rng_state.pth",
    "trainer_state.json",
    "training_args.bin",
)


def _write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _checkpoint_hashes(path: Path) -> dict[str, str]:
    return {name: sha256(path / name) for name in CHECKPOINT_FILES}


def _verify_boundary() -> None:
    status = Path("/proc/self/status").read_text()
    fields = dict(line.split(":\t", 1) for line in status.splitlines() if ":\t" in line)
    if any(
        int(fields[key], 16)
        for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    ):
        raise RuntimeError("training worker must have no capabilities")
    if (
        fields["NoNewPrivs"] != "1"
        or Path("/mnt/c").exists()
        or Path("/home/ubuntu/venom").exists()
    ):
        raise RuntimeError("training worker requires the isolated pilot launcher")
    for path in ("/job", "/inputs/model", "/inputs/train.jsonl"):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise RuntimeError(f"{path} must be mounted read-only")
    if any(
        line.split()[1] == "00000000"
        for line in Path("/proc/net/route").read_text().splitlines()[1:]
    ):
        raise RuntimeError("training worker has a default network route")


def _collate(rows: list[dict], pad_token: int) -> dict:
    import torch

    longest = max(len(row["input_ids"]) for row in rows)
    pad_values = {"input_ids": pad_token, "attention_mask": 0, "labels": IGNORE}
    return {
        name: torch.tensor(
            [row[name] + [pad] * (longest - len(row[name])) for row in rows]
        )
        for name, pad in pad_values.items()
    }


def run(mode: str) -> None:
    _verify_boundary()
    started = monotonic()
    snapshot = Path("/inputs/model")
    train_path = Path("/inputs/train.jsonl")
    output = Path("/out")
    pin = verify_snapshot(snapshot, full=True)
    records = read_jsonl(train_path)
    validate_splits(records)
    if not 8 <= len(records) <= 16 or any(row["split"] != "train" for row in records):
        raise ValueError("P1 requires 8–16 reviewed training records")

    import torch
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
    from transformers import (
        AutoModelForMultimodalLM,
        AutoProcessor,
        Trainer,
        TrainerCallback,
        TrainingArguments,
        enable_full_determinism,
    )

    enable_full_determinism(SEED)
    mib = 2**20
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("P1 requires a CUDA device with BF16 support")
    free, total = torch.cuda.mem_get_info()
    if free < 6500 * mib:
        raise RuntimeError(f"only {free // mib} MiB free on the GPU")
    torch.cuda.set_per_process_memory_fraction(min(1.0, (free - 1000 * mib) / total))
    torch.cuda.reset_peak_memory_stats()

    profile = {
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_manifest_sha256": sha256(
            Path("/job/scripts/llm/omni_native_snapshot.json")
        ),
        "train_sha256": sha256(train_path),
        "script_sha256": {
            name: sha256(Path("/job/scripts/academy") / name)
            for name in (
                "omni_pl_chat_p1.py",
                "omni_pl_chat_masks.py",
                "omni_pl_chat_data.py",
            )
        },
        "environment": {
            name: version(name)
            for name in (
                "torch",
                "transformers",
                "tokenizers",
                "peft",
                "accelerate",
                "numpy",
                "safetensors",
            )
        },
        "python": sys.version.split()[0],
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(),
        "seed": SEED,
        "full_determinism": True,
        "dtype": "bf16",
        "rank": 4,
        "alpha": 8,
        "dropout": 0.0,
        "target_modules": r"model\.language_model\..*\.(q_proj|v_proj)",
        "steps": STEPS,
        "save_every": SAVE_EVERY,
        "warmup_steps": 1,
        "learning_rate": LR,
        "max_tokens": MAX_TOKENS,
        "microbatch": 1,
    }

    checkpoint = None
    if mode == "resume":
        checkpoint = output / f"checkpoint-{SAVE_EVERY}"
        if json.loads((output / "profile.json").read_text()) != profile:
            raise ValueError("resume profile differs from the original run")
        if json.loads((checkpoint / "hashes.json").read_text()) != _checkpoint_hashes(
            checkpoint
        ):
            raise ValueError("checkpoint files differ from the saved receipt")
    else:
        _write_json(output / "profile.json", profile)

    processor = AutoProcessor.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=True
    )
    template = (snapshot / "chat_template.jinja").read_text(encoding="utf-8")
    encoded = [
        masked_example(processor.tokenizer, template, row, MAX_TOKENS)
        for row in records
    ]
    for row, item in zip(records, encoded, strict=True):
        canonical = processor.apply_chat_template(
            row["messages"],
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            add_generation_prompt=False,
            enable_thinking=False,
        )
        if canonical["input_ids"][0].tolist() != item["input_ids"]:
            raise ValueError(
                f"{row['record_id']}: training tokens differ from the vendor processor"
            )

    base = AutoModelForMultimodalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    )
    backbone = import_module(type(base.model.language_model).__module__)
    base.config.use_cache = False
    model = get_peft_model(
        base,
        LoraConfig(
            r=profile["rank"],
            lora_alpha=profile["alpha"],
            lora_dropout=profile["dropout"],
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=profile["target_modules"],
        ),
    )
    trainable = {
        name: param.numel()
        for name, param in model.named_parameters()
        if param.requires_grad
    }
    if not trainable or any(
        ".language_model." not in name or ".lora_" not in name for name in trainable
    ):
        raise RuntimeError(
            "trainable parameters must be LoRA tensors in the language model"
        )
    initial = {
        name: value.detach().cpu().clone()
        for name, value in get_peft_model_state_dict(model).items()
    }

    class PilotCallback(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if torch.cuda.mem_get_info()[0] < 600 * mib:
                raise RuntimeError("stopped at the GPU headroom threshold")
            if mode == "initial" and state.global_step == SAVE_EVERY:
                control.should_training_stop = True

        def on_save(self, args, state, control, **kwargs):
            saved = output / f"checkpoint-{state.global_step}"
            _write_json(saved / "hashes.json", _checkpoint_hashes(saved))

    args = TrainingArguments(
        output_dir=str(output),
        max_steps=STEPS,
        per_device_train_batch_size=1,
        learning_rate=LR,
        warmup_steps=profile["warmup_steps"],
        lr_scheduler_type="linear",
        bf16=True,
        optim="adamw_torch",
        seed=SEED,
        data_seed=SEED,
        full_determinism=True,
        dataloader_num_workers=0,
        save_strategy="steps",
        save_steps=SAVE_EVERY,
        logging_steps=1,
        logging_nan_inf_filter=False,
        report_to="none",
        disable_tqdm=True,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=encoded,
        data_collator=lambda rows: _collate(rows, processor.tokenizer.pad_token_id),
        callbacks=[PilotCallback()],
    )
    with patch.object(backbone, "can_use_lfm3_conv", return_value=False):
        trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
    expected_step = SAVE_EVERY if mode == "initial" else STEPS
    if trainer.state.global_step != expected_step:
        raise RuntimeError("unexpected final optimizer step")
    step_logs = [item for item in trainer.state.log_history if "loss" in item]
    if len(step_logs) != expected_step or any(
        not math.isfinite(item["loss"])
        or not math.isfinite(item.get("grad_norm", math.nan))
        or item["grad_norm"] <= 0
        for item in step_logs
    ):
        raise RuntimeError("missing step measurements or invalid loss/gradients")
    changed = [
        name
        for name, value in get_peft_model_state_dict(model).items()
        if not torch.equal(value.detach().cpu(), initial[name])
    ]
    if not changed:
        raise RuntimeError("no adapter tensor changed")

    receipt = {
        "mode": mode,
        "final_step": trainer.state.global_step,
        "trainable": trainable,
        "trainable_count": sum(trainable.values()),
        "changed_tensors": changed,
        "records": len(records),
        "supervised_tokens": sum(
            label != IGNORE for item in encoded for label in item["labels"]
        ),
        "step_logs": step_logs,
        "checkpoint": f"checkpoint-{expected_step}",
        "initial_gpu_free_mib": free // mib,
        "peak_gpu_allocated_mib": round(torch.cuda.max_memory_allocated() / mib, 1),
        "peak_gpu_reserved_mib": round(torch.cuda.max_memory_reserved() / mib, 1),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
        ),
        "elapsed_seconds": round(monotonic() - started, 3),
    }
    _write_json(output / f"{mode}.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def compare(control: Path, resumed: Path) -> None:
    from safetensors import safe_open

    profiles = [(root / "profile.json").read_bytes() for root in (control, resumed)]
    if profiles[0] != profiles[1]:
        raise ValueError("control and resumed training used different profiles")
    control_receipt = json.loads((control / "control.json").read_text())
    resumed_receipt = json.loads((resumed / "resume.json").read_text())
    if control_receipt["step_logs"] != resumed_receipt["step_logs"]:
        raise ValueError("control and resumed step losses or gradients differ")

    def adapter_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with safe_open(path, framework="numpy") as adapter:
            for key in adapter.keys():
                value = adapter.get_tensor(key)
                digest.update(
                    key.encode() + str(value.shape).encode() + str(value.dtype).encode()
                )
                digest.update(value.tobytes())
        return digest.hexdigest()

    files = [
        root / f"checkpoint-{STEPS}" / "adapter_model.safetensors"
        for root in (control, resumed)
    ]
    result = [adapter_digest(path) for path in files]
    if result[0] != result[1]:
        raise ValueError("control and resumed final adapter tensors differ")
    print(
        json.dumps(
            {"status": "PASS", "steps": STEPS, "adapter_tensor_sha256": result[0]},
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "initial", "resume", "compare"))
    parser.add_argument("directories", type=Path, nargs="*")
    args = parser.parse_args()
    if args.mode == "compare" and len(args.directories) == 2:
        compare(*args.directories)
    elif args.mode != "compare" and not args.directories:
        run(args.mode)
    else:
        parser.error("compare requires control and resumed directories")


if __name__ == "__main__":
    main()
