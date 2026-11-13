"""Run the small Omni text LoRA and checkpoint-resume qualification in isolation."""

import argparse
import hashlib
import json
import math
import os
import re
import resource
import sys
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from unittest.mock import patch

from scripts.academy.omni_pl_chat_adapter import (
    ADAPTER_CONFIG,
    ADAPTER_WEIGHTS,
    read_initial_adapter_handoff,
    verify_initial_adapter,
)
from scripts.academy.omni_pl_chat_data import read_jsonl, sha256, validate_splits
from scripts.academy.omni_pl_chat_masks import IGNORE, masked_example, verify_snapshot
from scripts.academy.omni_pl_chat_recipe import (
    DEFAULT_RECIPE,
    load_recipe,
    validate_recipe,
)

STEPS = DEFAULT_RECIPE["steps"]
_RECIPE_PATH = Path("/inputs/recipe.json")
_INITIAL_ADAPTER_DIR = Path("/inputs/initial-adapter")
_INITIAL_HANDOFF = Path("/inputs/initial-adapter.json")
CHECKPOINT_FILES = (
    ADAPTER_CONFIG,
    ADAPTER_WEIGHTS,
    "optimizer.pt",
    "scheduler.pt",
    "rng_state.pth",
    "trainer_state.json",
    "training_args.bin",
)


def _write_json(path: Path, data: dict) -> None:
    """Publish a complete receipt exactly once."""
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".receipt-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path)
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink()


def _checkpoint_hashes(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("checkpoint must be a real directory")
    files = {name: path / name for name in CHECKPOINT_FILES}
    if any(file.is_symlink() or not file.is_file() for file in files.values()):
        raise ValueError("checkpoint is missing verified training state")
    return {name: sha256(file) for name, file in files.items()}


def verify_checkpoint(path: Path) -> dict[str, str]:
    receipt = path / "hashes.json"
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("checkpoint is missing its hash receipt")
    hashes = _checkpoint_hashes(path)
    if json.loads(receipt.read_text(encoding="utf-8")) != hashes:
        raise ValueError("checkpoint files differ from the saved receipt")
    return hashes


def _resume_checkpoint(output: Path, step_limit: int) -> Path:
    sealed: list[tuple[int, Path]] = []
    for entry in output.iterdir():
        match = re.fullmatch(r"checkpoint-([1-9][0-9]*)", entry.name)
        if match is not None:
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("checkpoint must be a real directory")
            receipt = entry / "hashes.json"
            if receipt.is_symlink():
                raise ValueError("checkpoint receipt must be a regular file")
            if receipt.exists():
                sealed.append((int(match[1]), entry))
    if not sealed:
        raise ValueError("no sealed checkpoint is available")
    step, latest = max(sealed)
    if step >= step_limit:
        raise ValueError("checkpoint has reached or exceeded the planned step budget")
    verify_checkpoint(latest)
    trainer_state = json.loads(
        (latest / "trainer_state.json").read_text(encoding="utf-8")
    )
    if trainer_state.get("global_step") != step:
        raise ValueError("checkpoint step differs from the verified trainer state")
    return latest


def _verify_boundary(extra_read_only: tuple[str, ...] = ()) -> None:
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
    for path in ("/job", "/inputs/model", "/inputs/train.jsonl", *extra_read_only):
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


def _supervised_token_count(labels):
    """Count causal-LM targets after the model's one-position label shift."""
    return (labels[..., 1:] != IGNORE).sum()


def _token_normalized_text_loss(outputs, labels, accumulated_tokens):
    """Scale an Omni microbatch mean to its share of the accumulated tokens."""
    text_loss = outputs.text_loss
    if text_loss is None or outputs.audio_loss is not None:
        raise ValueError("text-only training requires the Omni text loss")
    count = _supervised_token_count(labels)
    if int(count) <= 0 or accumulated_tokens is None or int(accumulated_tokens) <= 0:
        raise ValueError("token-normalized training requires supervised tokens")
    return (
        text_loss * count.to(text_loss.device) / accumulated_tokens.to(text_loss.device)
    )


def _token_trainer_type(trainer_type):
    class TokenNormalizedTrainer(trainer_type):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.model_accepts_loss_kwargs = False
            self.loss_is_scaled_for_ga = True

        def _get_num_items_in_batch(self, batch_samples, device):
            if self.args.world_size != 1 or self.args.n_gpu > 1:
                raise RuntimeError("token-normalized Omni training requires one device")
            total = sum(
                (_supervised_token_count(batch["labels"]) for batch in batch_samples)
            )
            if int(total) <= 0:
                raise ValueError("accumulated batch has no supervised tokens")
            return total.to(device)

        def compute_loss(
            self, model, inputs, return_outputs=False, num_items_in_batch=None
        ):
            outputs = model(**inputs)
            loss = _token_normalized_text_loss(
                outputs, inputs["labels"], num_items_in_batch
            )
            return (loss, outputs) if return_outputs else loss

    return TokenNormalizedTrainer


def _module_inventory(model, selector):
    groups = {
        "q_proj": "attention",
        "k_proj": "attention",
        "v_proj": "attention",
        "o_proj": "attention",
        "in_proj": "convolution_projection",
        "out_proj": "convolution_projection",
        "w1": "mlp",
        "w2": "mlp",
        "w3": "mlp",
    }
    inventory = []
    for name, module in model.named_modules():
        if not selector.fullmatch(name):
            continue
        suffix = name.rsplit(".", 1)[-1]
        weight = getattr(module, "weight", None)
        if suffix not in groups or weight is None or not hasattr(weight, "numel"):
            raise RuntimeError(f"unsupported matched language module: {name}")
        inventory.append(
            {
                "name": name,
                "group": groups[suffix],
                "type": type(module).__name__,
                "weight_shape": list(weight.shape),
                "weight_parameters": weight.numel(),
            }
        )
    if not inventory:
        raise RuntimeError("no language modules match the LoRA recipe")
    return sorted(inventory, key=lambda item: item["name"])


def _prepare_inputs(
    snapshot: Path, train_path: Path, recipe: dict, *, legacy: bool, preflight: bool
):
    pin = verify_snapshot(snapshot, full=True)
    train_hash = sha256(train_path)
    if recipe.get("train_sha256", train_hash) != train_hash:
        raise ValueError("training data differs from the recipe digest")
    records = read_jsonl(train_path)
    validate_splits(records)
    lower, upper = (8, 16) if legacy else (1, 2048)
    if not lower <= len(records) <= upper or any(
        row["split"] != "train" for row in records
    ):
        raise ValueError(f"expected {lower} to {upper} reviewed training records")

    if preflight:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False
        )
        processor = None
    else:
        from transformers import AutoProcessor

        processor = AutoProcessor.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=True
        )
        tokenizer = processor.tokenizer
    template = (snapshot / "chat_template.jinja").read_text(encoding="utf-8")
    encoded = [
        masked_example(tokenizer, template, row, recipe["max_tokens"])
        for row in records
    ]
    counts = []
    for row, item in zip(records, encoded, strict=True):
        if processor is not None:
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
        supervised = sum(label != IGNORE for label in item["labels"])
        if not supervised:
            raise ValueError(f"{row['record_id']}: training mask is empty")
        counts.append(supervised)
    upper_bound = (
        max(counts)
        * recipe["microbatch"]
        * recipe["gradient_accumulation_steps"]
        * recipe["steps"]
    )
    if upper_bound > recipe.get("max_supervised_tokens", upper_bound):
        raise ValueError("training supervision could exceed the recipe token budget")
    observations = {
        "train_sha256": train_hash,
        "records": len(records),
        "supervised_tokens": sum(counts),
        "supervised_token_exposure_upper_bound": upper_bound,
    }
    return pin, processor, encoded, observations


def _load_adapter_tensors(model, weights: Path) -> int:
    import torch
    from peft import get_peft_model_state_dict, set_peft_model_state_dict
    from safetensors import safe_open

    expected = get_peft_model_state_dict(model)
    with safe_open(weights, framework="pt", device="cpu") as source:
        if set(source.keys()) != expected.keys():
            raise ValueError("experiment_initial_adapter_tensor_names_mismatch")
        tensors = {}
        for name, parameter in expected.items():
            meta = source.get_slice(name)
            if meta.get_shape() != list(parameter.shape) or meta.get_dtype() not in {
                "F32",
                "F16",
                "BF16",
            }:
                raise ValueError("experiment_initial_adapter_tensor_shape_or_dtype")
            value = source.get_tensor(name)
            if not torch.isfinite(value).all():
                raise ValueError("experiment_initial_adapter_tensor_nonfinite")
            tensors[name] = value

    set_peft_model_state_dict(model, tensors)
    loaded = get_peft_model_state_dict(model)
    if loaded.keys() != tensors.keys() or any(
        not torch.equal(loaded[name].detach().cpu(), tensor)
        for name, tensor in tensors.items()
    ):
        raise ValueError("experiment_initial_adapter_tensor_load_mismatch")
    return len(tensors)


def run(mode: str) -> None:
    legacy = not _RECIPE_PATH.exists()
    has_initial = _INITIAL_HANDOFF.exists()
    read_only = () if legacy else (str(_RECIPE_PATH),)
    if has_initial or _INITIAL_ADAPTER_DIR.exists():
        if legacy or not has_initial:
            raise ValueError("experiment_initial_adapter_handoff_missing")
        read_only += (
            str(_INITIAL_HANDOFF),
            str(_INITIAL_ADAPTER_DIR / ADAPTER_CONFIG),
            str(_INITIAL_ADAPTER_DIR / ADAPTER_WEIGHTS),
        )
    _verify_boundary(read_only)
    started = monotonic()
    snapshot = Path("/inputs/model")
    train_path = Path("/inputs/train.jsonl")
    output = Path("/out")
    recipe = validate_recipe({}) if legacy else load_recipe(_RECIPE_PATH)
    initial_adapter = None
    if has_initial:
        initial_adapter = read_initial_adapter_handoff(_INITIAL_HANDOFF)
        verify_initial_adapter(_INITIAL_ADAPTER_DIR, initial_adapter, recipe)
    initialization = {"initial_adapter": initial_adapter} if has_initial else {}
    pin, processor, encoded, observations = _prepare_inputs(
        snapshot, train_path, recipe, legacy=legacy, preflight=mode == "preflight"
    )
    environment = {
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
    }
    if mode == "preflight":
        _write_json(
            output / "preflight.json",
            {
                "model": pin["repo"],
                "revision": pin["revision"],
                "environment": environment,
                "recipe": recipe,
                **initialization,
                **observations,
            },
        )
        return

    import torch
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
    from peft.tuners.lora import LoraLayer
    from transformers import (
        AutoModelForMultimodalLM,
        Trainer,
        TrainerCallback,
        TrainingArguments,
        enable_full_determinism,
    )

    enable_full_determinism(recipe["seed"])
    mib = 2**20
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("Omni training requires a CUDA device with BF16 support")
    free, total = torch.cuda.mem_get_info()
    if free < 6500 * mib:
        raise RuntimeError(f"only {free // mib} MiB free on the GPU")
    allocator_limit_mib = free // mib - recipe["gpu_allocator_reserve_mib"]
    torch.cuda.set_per_process_memory_fraction(
        min(1.0, (free - recipe["gpu_allocator_reserve_mib"] * mib) / total)
    )
    torch.cuda.reset_peak_memory_stats()
    minimum_gpu_free_mib = free // mib

    targets = "|".join(recipe["target_modules"])
    profile = {
        **recipe,
        **initialization,
        "model": pin["repo"],
        "revision": pin["revision"],
        "snapshot_manifest_sha256": sha256(
            Path("/job/scripts/llm/omni_native_snapshot.json")
        ),
        "train_sha256": observations["train_sha256"],
        "script_sha256": {
            name: sha256(Path("/job/scripts/academy") / name)
            for name in (
                "omni_pl_chat_p1.py",
                "omni_pl_chat_masks.py",
                "omni_pl_chat_data.py",
                "omni_pl_chat_recipe.py",
                "omni_pl_chat_adapter.py",
            )
        },
        "environment": environment,
        "python": sys.version.split()[0],
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(),
        "full_determinism": True,
        "dtype": "bf16",
        "target_modules": rf"model\.language_model\..*\.({targets})",
    }

    checkpoint = None
    if mode == "resume":
        if json.loads((output / "profile.json").read_text(encoding="utf-8")) != profile:
            raise ValueError("resume profile differs from the original run")
        checkpoint = _resume_checkpoint(output, recipe["steps"])
    else:
        _write_json(output / "profile.json", profile)

    base = AutoModelForMultimodalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    )
    backbone = import_module(type(base.model.language_model).__module__)
    base.config.use_cache = False
    if recipe["gradient_checkpointing"]:
        base.requires_grad_(False)
        base.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        base.enable_input_require_grads()
    selector = re.compile(profile["target_modules"])
    module_inventory = _module_inventory(base, selector)
    planned_modules = {item["name"] for item in module_inventory}
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
    adapted_layers = {
        name: layer
        for name, layer in base.named_modules()
        if isinstance(layer, LoraLayer)
    }
    if adapted_layers.keys() != planned_modules:
        raise RuntimeError("adapted LoRA modules differ from the language recipe")
    module_groups = {item["name"]: item["group"] for item in module_inventory}
    adapted_groups = {
        group: {"modules": 0, "trainable_parameters": 0}
        for group in set(module_groups.values())
    }
    for name, layer in adapted_layers.items():
        group = adapted_groups[module_groups[name]]
        group["modules"] += 1
        group["trainable_parameters"] += sum(
            param.numel()
            for param in layer.parameters(recurse=True)
            if param.requires_grad
        )
    parameters = dict(model.named_parameters())
    trainable = {
        name: param.numel() for name, param in parameters.items() if param.requires_grad
    }
    if not trainable or any(
        ".language_model." not in name or ".lora_" not in name for name in trainable
    ):
        raise RuntimeError(
            "trainable parameters must be LoRA tensors in the language model"
        )
    if checkpoint is not None:
        loaded_tensors = _load_adapter_tensors(model, checkpoint / ADAPTER_WEIGHTS)
    elif initial_adapter is not None:
        loaded_tensors = _load_adapter_tensors(
            model, _INITIAL_ADAPTER_DIR / ADAPTER_WEIGHTS
        )
    else:
        loaded_tensors = 0
    initial = {
        name: value.detach().cpu().clone()
        for name, value in get_peft_model_state_dict(model).items()
    }

    class PilotCallback(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            nonlocal minimum_gpu_free_mib
            free_now_mib = torch.cuda.mem_get_info()[0] // mib
            minimum_gpu_free_mib = min(minimum_gpu_free_mib, free_now_mib)
            if free_now_mib < recipe["gpu_step_min_free_mib"]:
                _write_json(
                    output / f"gpu-stop-{state.global_step}.json",
                    {
                        "step": state.global_step,
                        "gpu_free_mib": free_now_mib,
                        "gpu_step_min_free_mib": recipe["gpu_step_min_free_mib"],
                        "peak_gpu_allocated_mib": torch.cuda.max_memory_allocated()
                        / mib,
                        "peak_gpu_reserved_mib": torch.cuda.max_memory_reserved() / mib,
                    },
                )
                raise RuntimeError(
                    "stopped at the GPU headroom threshold: "
                    f"{free_now_mib} MiB free below "
                    f"{recipe['gpu_step_min_free_mib']} MiB"
                )
            if state.global_step == recipe["steps"]:
                control.should_save = True
            if mode == "initial" and state.global_step == recipe["save_every"]:
                control.should_training_stop = True

        def on_save(self, args, state, control, **kwargs):
            saved = output / f"checkpoint-{state.global_step}"
            _write_json(saved / "hashes.json", _checkpoint_hashes(saved))

    args = TrainingArguments(
        output_dir=str(output),
        max_steps=recipe["steps"],
        per_device_train_batch_size=recipe["microbatch"],
        gradient_accumulation_steps=recipe["gradient_accumulation_steps"],
        learning_rate=recipe["learning_rate"],
        warmup_steps=profile["warmup_steps"],
        lr_scheduler_type=recipe["lr_scheduler_type"],
        bf16=True,
        optim="adamw_torch",
        seed=recipe["seed"],
        data_seed=recipe["seed"],
        full_determinism=True,
        dataloader_num_workers=0,
        save_strategy="steps",
        save_steps=recipe["save_every"],
        logging_steps=1,
        logging_nan_inf_filter=False,
        report_to="none",
        disable_tqdm=True,
        remove_unused_columns=False,
    )
    trainer_type = (
        Trainer
        if recipe["loss_mode"] == "model_default"
        else _token_trainer_type(Trainer)
    )
    trainer = trainer_type(
        model=model,
        args=args,
        train_dataset=encoded,
        data_collator=lambda rows: _collate(rows, processor.tokenizer.pad_token_id),
        callbacks=[PilotCallback()],
    )
    trainer.create_optimizer()
    optimized_ids = {
        id(parameter)
        for group in trainer.optimizer.param_groups
        for parameter in group["params"]
    }
    optimized_parameters = sorted(
        name for name, parameter in parameters.items() if id(parameter) in optimized_ids
    )
    if optimized_ids != {
        id(parameter) for parameter in parameters.values() if parameter.requires_grad
    }:
        raise RuntimeError("optimizer parameters differ from trainable adapter tensors")
    # A MagicMock would retain every CUDA tensor argument for the whole training.
    with patch.object(
        backbone, "can_use_lfm3_conv", new=lambda *_args, **_kwargs: False
    ):
        trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
    expected_step = recipe["save_every"] if mode == "initial" else recipe["steps"]
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
        **initialization,
        "state_source": "checkpoint"
        if checkpoint
        else ("initial_adapter" if has_initial else "base"),
        "loaded_tensors": loaded_tensors,
        "fresh_optimizer": checkpoint is None,
        "final_step": trainer.state.global_step,
        "module_inventory": module_inventory,
        "adapted_modules": sorted(adapted_layers),
        "adapted_groups": adapted_groups,
        "trainable": trainable,
        "trainable_count": sum(trainable.values()),
        "frozen_parameter_count": sum(
            parameter.numel()
            for parameter in parameters.values()
            if not parameter.requires_grad
        ),
        "optimizer_parameters": optimized_parameters,
        "changed_tensors": changed,
        **observations,
        "step_logs": step_logs,
        "checkpoint": f"checkpoint-{expected_step}",
        "initial_gpu_free_mib": free // mib,
        "gpu_total_mib": total // mib,
        "gpu_allocator_limit_mib": allocator_limit_mib,
        "minimum_gpu_free_mib_at_step": minimum_gpu_free_mib,
        "peak_gpu_allocated_mib": round(torch.cuda.max_memory_allocated() / mib, 1),
        "peak_gpu_reserved_mib": round(torch.cuda.max_memory_reserved() / mib, 1),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
        ),
        "elapsed_seconds": round(monotonic() - started, 3),
    }
    receipt["checkpoint_sha256"] = verify_checkpoint(output / receipt["checkpoint"])[
        "adapter_model.safetensors"
    ]
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

    steps = json.loads(profiles[0])["steps"]
    checkpoints = [root / f"checkpoint-{steps}" for root in (control, resumed)]
    for checkpoint in checkpoints:
        verify_checkpoint(checkpoint)
    files = [checkpoint / "adapter_model.safetensors" for checkpoint in checkpoints]
    result = [adapter_digest(path) for path in files]
    if result[0] != result[1]:
        raise ValueError("control and resumed final adapter tensors differ")
    print(
        json.dumps(
            {"status": "PASS", "steps": steps, "adapter_tensor_sha256": result[0]},
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("preflight", "control", "initial", "resume", "compare")
    )
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
