"""Explicit offline GPU worker. Uses HF checkpoints including optimizer/RNG state."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import time
from pathlib import Path
from typing import Any

from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training.paths import operator_path

from .profile import LOCK, Recipe

VERSIONS = {"torch": "2.13.0", "transformers": "5.17.0", "peft": "0.21.2"}


def environment() -> dict[str, Any]:
    versions = {name: importlib.metadata.version(name) for name in VERSIONS}
    if versions != VERSIONS or platform.python_version() != "3.14.8":
        raise ValueError("functiongemma_environment_unqualified")
    return {
        "python": platform.python_version(),
        "versions": versions,
        "lock": LOCK,
        "gpu_qualified": False,
    }


def tree_hashes(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("functiongemma_checkpoint_symlink")
        if path.is_file() and path.name != "receipt.json":
            files[str(path.relative_to(root))] = file_digest(path)
    if not files:
        raise ValueError("functiongemma_artifacts_missing")
    return files


def verify_checkpoint(root: Path, fingerprint: str) -> dict:
    receipt = json.loads((root / "receipt.json").read_text())
    if receipt.get("fingerprint") != fingerprint or receipt.get("files") != tree_hashes(
        root
    ):
        raise ValueError("functiongemma_checkpoint_changed")
    for name in ("trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth"):
        if name not in receipt["files"]:
            raise ValueError("functiongemma_resume_state_missing")
    return receipt


def validate_request(request: dict) -> Recipe:
    recipe = Recipe(**request["recipe"])
    recipe.validate()
    if request.get("stage") not in {"smoke", "train", "resume"}:
        raise ValueError("functiongemma_stage_invalid")
    if request.get("gpu_authorized") is not True:
        raise ValueError("functiongemma_gpu_authorization_required")
    if request["stage"] != "smoke" and not request.get("qualification"):
        raise ValueError("functiongemma_smoke_required")
    if request["stage"] == "resume" and not request.get("checkpoint"):
        raise ValueError("functiongemma_resume_checkpoint_required")
    if request["stage"] != "resume" and request.get("checkpoint"):
        raise ValueError("functiongemma_unexpected_checkpoint")
    if any(
        os.environ.get(key) != "1" for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    ):
        raise ValueError("functiongemma_offline_required")
    return recipe


def collate(rows: list[dict], *, torch: Any, pad_id: int) -> dict:
    length = max(len(row["input_ids"]) for row in rows)
    batch = {}
    for key, pad in (("input_ids", pad_id), ("attention_mask", 0), ("labels", -100)):
        batch[key] = torch.tensor(
            [row[key] + [pad] * (length - len(row[key])) for row in rows]
        )
    return batch


def trainer_arguments(recipe: Recipe, output: Path, *, smoke: bool) -> dict:
    budget_args = (
        {"max_steps": 1, "eval_strategy": "no"}
        if smoke
        else {
            "num_train_epochs": recipe.epochs,
            "eval_strategy": "steps",
            "eval_steps": 1,
        }
    )
    return {
        "output_dir": str(output),
        "per_device_train_batch_size": recipe.batch_size,
        "per_device_eval_batch_size": recipe.batch_size,
        "gradient_accumulation_steps": recipe.accumulation,
        "learning_rate": recipe.learning_rate,
        "weight_decay": recipe.weight_decay,
        "warmup_ratio": 0.0 if smoke else recipe.warmup_ratio,
        "lr_scheduler_type": "linear",
        "optim": "adamw_torch",
        "bf16": True,
        "fp16": False,
        "seed": recipe.seed,
        "data_seed": recipe.seed,
        "save_strategy": "epoch" if not smoke else "steps",
        "save_steps": 1,
        "save_only_model": False,
        "report_to": [],
        "push_to_hub": False,
        "remove_unused_columns": False,
        "dataloader_drop_last": False,
        "logging_steps": 1,
        **budget_args,
    }


def run(request: dict) -> dict:
    """No model imports before request, local artifacts and ownership are checked."""
    recipe = validate_request(request)
    dependencies = environment()
    encoded_path = operator_path(request["encoded_release"])
    document = json.loads(encoded_path.read_text())
    from .encoding import validate_encoded_release

    records = validate_encoded_release(document, context=recipe.context)
    snapshot = operator_path(request["snapshot"], allow_symlinks=True)
    if snapshot.name != recipe.revision:
        raise ValueError("functiongemma_pinned_snapshot_required")
    weights = sorted(snapshot.glob("*.safetensors"))
    if not weights:
        raise ValueError("functiongemma_weights_missing")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    template_hash = hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
    if document.get("tokenizer_template_sha256") != template_hash:
        raise ValueError("functiongemma_tokenizer_template_changed")
    snapshot_hashes = {
        p.name: file_digest(p) for p in snapshot.iterdir() if p.is_file()
    }
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise ValueError("functiongemma_single_gpu_required")
    fingerprint = digest(
        {
            "recipe": recipe.identity(),
            "encoded": file_digest(encoded_path),
            "snapshot": snapshot_hashes,
            "dependencies": dependencies,
            "host": platform.node(),
        }
    )
    output = operator_path(request["output"])
    if output.exists():
        raise FileExistsError("functiongemma_output_exists")
    qualification = None
    if request["stage"] != "smoke":
        proof_path = operator_path(request["qualification"])
        qualification = json.loads(proof_path.read_text())
        if (
            qualification.get("fingerprint") != fingerprint
            or qualification.get("qualified") is not True
        ):
            raise ValueError("functiongemma_smoke_mismatch")
        verify_checkpoint(operator_path(qualification["checkpoint"]), fingerprint)
    resume = operator_path(request["checkpoint"]) if request.get("checkpoint") else None
    if resume:
        verify_checkpoint(resume, fingerprint)
    # The ledger must be the host's shared ledger, never a per-run substitute.
    from venom_core.services.runtime_admission import RuntimeAdmission

    ledger = os.environ.get("VENOM_GRANITE_ADMISSION_DB")
    if not ledger:
        raise ValueError("functiongemma_shared_admission_required")
    lease = RuntimeAdmission(operator_path(ledger), enabled=True).acquire(
        owner="functiongemma-training",
        run_id=request["run_id"],
        engine="functiongemma-training",
        model=recipe.model,
    )
    try:
        with lease.operation(kind="lifecycle"):
            return _execute(
                request, recipe, records, snapshot, output, fingerprint, resume
            )
    finally:
        lease.release()


def parameter_evidence(model):
    from venom_core.services.granite_operator.engine import tensor_hash

    return {
        name: tensor_hash(parameter)
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }


def probe_logits(model, row):
    import torch

    from venom_core.services.granite_operator.engine import tensor_hash

    model.eval()
    values = {
        key: torch.tensor([row[key]], device="cuda")
        for key in ("input_ids", "attention_mask")
    }
    with torch.inference_mode():
        return tensor_hash(model(**values).logits)


def _execute(request, recipe, records, snapshot, output, fingerprint, resume):
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("functiongemma_cuda_bf16_required")
    set_seed(recipe.seed)
    model = AutoModelForCausalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
    )
    if model.config.architectures != ["Gemma3ForCausalLM"]:
        raise ValueError("functiongemma_architecture_mismatch")
    targets = sorted(
        name
        for name, _ in model.named_modules()
        if name.rsplit(".", 1)[-1] in {"q_proj", "k_proj", "v_proj", "o_proj"}
    )
    if recipe.method == "lora":
        from peft import LoraConfig, get_peft_model

        if {name.rsplit(".", 1)[-1] for name in targets} != {
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
        }:
            raise ValueError("functiongemma_lora_targets_missing")
        model = get_peft_model(
            model,
            LoraConfig(
                r=recipe.rank,
                lora_alpha=recipe.alpha,
                lora_dropout=recipe.dropout,
                target_modules=targets,
                task_type="CAUSAL_LM",
                bias="none",
            ),
        )
    if any(p.device.type != "cuda" for p in model.parameters()):
        raise RuntimeError("functiongemma_offload_forbidden")
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    smoke = request["stage"] == "smoke"
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "status.json", {"state": "failed", "activation_allowed": False})
    torch.cuda.reset_peak_memory_stats()
    args = TrainingArguments(**trainer_arguments(recipe, output, smoke=smoke))
    if not smoke:
        args.eval_steps = max(
            1, (recipe.budget(len(records["train"]))["updates_per_epoch"] + 1) // 2
        )
    started = time.monotonic()
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=records["train"],
        eval_dataset=records["validation"],
        data_collator=lambda rows: collate(
            rows, torch=torch, pad_id=tokenizer.pad_token_id
        ),
    )
    before = parameter_evidence(model)
    trainer.train(resume_from_checkpoint=str(resume) if resume else None)
    if not before or before == parameter_evidence(model):
        raise RuntimeError("functiongemma_trainable_weights_unchanged")
    checkpoint = output / ("checkpoint-" + str(trainer.state.global_step))
    _seal(checkpoint, fingerprint)
    probe = probe_logits(model, records["validation"][0])
    checks = {"save": True, "reload": False, "resume": False, "weights_updated": True}
    if smoke:
        # Fresh model plus Trainer restores model/adapter, optimizer, scheduler and RNG.
        del trainer, model
        torch.cuda.empty_cache()
        reloaded = _resume_smoke(
            recipe, records, snapshot, output / "reload", checkpoint, probe
        )
        checkpoint = reloaded
        _seal(checkpoint, fingerprint)
        checks.update(reload=True, resume=True)
    result = {
        "fingerprint": fingerprint,
        "qualified": smoke and all(checks.values()),
        "checks": checks,
        "checkpoint": str(checkpoint),
        "recipe": recipe.identity(),
        "budget": recipe.budget(len(records["train"])),
        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "elapsed_seconds": time.monotonic() - started,
        "artifact_bytes": sum(
            p.stat().st_size for p in checkpoint.rglob("*") if p.is_file()
        ),
        "activation_allowed": False,
        "evaluation_required": True,
        "qualification_scope": "save_reload_resume_only",
    }
    write_json(output / "metrics.json", result)
    write_json(
        output / "status.json", {"state": "succeeded", "activation_allowed": False}
    )
    return result


def _seal(checkpoint, fingerprint):
    write_json(
        checkpoint / "receipt.json",
        {"fingerprint": fingerprint, "files": tree_hashes(checkpoint)},
    )
    verify_checkpoint(checkpoint, fingerprint)


def _resume_smoke(recipe, records, snapshot, output, checkpoint, probe):
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    model = AutoModelForCausalLM.from_pretrained(
        snapshot if recipe.method == "lora" else checkpoint,
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=True,
        trust_remote_code=False,
    )
    if recipe.method == "lora":
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model, checkpoint, is_trainable=True, local_files_only=True
        )
    if probe_logits(model, records["validation"][0]) != probe:
        raise RuntimeError("functiongemma_reload_logits_changed")
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    arguments = trainer_arguments(recipe, output, smoke=True)
    arguments["max_steps"] = 2
    trainer = Trainer(
        model=model,
        args=TrainingArguments(**arguments),
        train_dataset=records["train"],
        data_collator=lambda rows: collate(
            rows, torch=torch, pad_id=tokenizer.pad_token_id
        ),
    )
    trainer.train(resume_from_checkpoint=str(checkpoint))
    if trainer.state.global_step != 2:
        raise RuntimeError("functiongemma_resume_progress_invalid")
    return output / "checkpoint-2"
