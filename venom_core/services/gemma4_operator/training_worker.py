"""Remote-only atomic Gemma SFT entry point using the existing native trainer.

Run through the prepared remote RPC interpreter and the existing host admission
lease. Importing this module does not import Torch or load/download a model.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sqlite3
import time
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable

from venom_core.services.granite_operator.contract import (
    file_digest,
    inside,
    write_json,
)
from venom_core.services.granite_operator.engine import (
    Session,
    finite,
    loss_for,
    tensor_hash,
)
from venom_core.services.remote_training.paths import operator_path

from .profile import (
    MODEL,
    MODEL_LOADERS,
    PINNED_REVISIONS,
    GemmaProfile,
    loader_for_model,
)
from .training import (
    GemmaTrainingRecipe,
    execution_identity,
    identity_fingerprint,
    read_json,
    require_qualification,
    target_modules_for,
    validate_request,
    verified_checkpoint,
)


def require_owner() -> None:
    """Require this worker's real parent reservation in the shared host ledger."""
    database = os.environ.get("VENOM_GRANITE_ADMISSION_DB")
    run_id = os.environ.get("VENOM_GRANITE_RUN_ID")
    if not database or not run_id:
        raise RuntimeError("host_runtime_admission_required")
    target = operator_path(database)
    with sqlite3.connect("file:" + str(target) + "?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT 1 FROM lease WHERE pid=? AND owner='gemma-training' "
            "AND engine='gemma-training' AND run_id=? AND quarantine=0 AND cancelled=0",
            (os.getppid(), run_id),
        ).fetchone()
    if not row:
        raise RuntimeError("host_runtime_reservation_missing")


def load_encoded(path: str | Path, profile: GemmaProfile) -> tuple[dict, dict]:
    from .encoding import validate_encoded_release

    document = read_json(path)
    return document, validate_encoded_release(document, profile)


def probe_runtime() -> dict[str, Any]:
    """This remote probe checks CUDA, but never creates a model."""
    import torch

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("gemma_training_cuda_bf16_required")
    return {
        "gpu": torch.cuda.get_device_name(0),
        "gpu_memory": torch.cuda.get_device_properties(0).total_memory,
        "cuda": torch.version.cuda,
    }


def require_cuda_placement(model: Any) -> dict[str, Any]:
    """Never accept CPU/disk/meta model offload or an implicit precision fallback."""
    count = 0
    for _, parameter in model.named_parameters():
        count += 1
        if getattr(getattr(parameter, "device", None), "type", None) != "cuda":
            raise RuntimeError("gemma_runtime_cuda_placement_required")
    if count == 0:
        raise RuntimeError("gemma_runtime_cuda_parameters_missing")
    placement = getattr(model, "hf_device_map", None)
    if placement is not None:
        if not isinstance(placement, dict):
            raise RuntimeError("gemma_runtime_device_map_invalid")
        for device in placement.values():
            is_index = type(device) is int and device >= 0
            is_cuda = re.fullmatch(r"cuda(?::[0-9]+)?", str(device)) is not None
            if not is_index and not is_cuda:
                raise RuntimeError("gemma_runtime_offload_forbidden")
    return {
        "gpu_required": True,
        "cpu_fallback": False,
        "disk_offload": False,
        "parameter_tensors_on_cuda": count,
    }


def matched_targets(model: Any, model_id: str = MODEL) -> list[str]:
    names = [
        name
        for name, _ in model.named_modules()
        if re.fullmatch(target_modules_for(model_id), name)
    ]
    if {name.rsplit(".", 1)[-1] for name in names} != {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    }:
        raise RuntimeError("gemma_training_text_targets_missing")
    return sorted(names)


def lora_config(recipe: GemmaTrainingRecipe) -> Any:
    from peft import LoraConfig

    return LoraConfig(
        r=recipe.rank,
        lora_alpha=recipe.alpha,
        lora_dropout=recipe.dropout,
        target_modules=target_modules_for(recipe.model),
        bias="none",
        task_type="CAUSAL_LM",
    )


def inspect_structure(snapshot: Path) -> dict[str, Any]:
    """Verify real Gemma/PEFT attachment on meta tensors, without weights/CUDA."""
    init_empty_weights = importlib.import_module("accelerate").init_empty_weights
    from peft import get_peft_model
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
    )
    architectures = config.architectures
    selected = next(
        (name for name, loader in MODEL_LOADERS.items() if architectures == [loader]),
        None,
    )
    if selected is None:
        raise ValueError("gemma_training_loader_unqualified")
    loader = getattr(
        importlib.import_module("transformers"), loader_for_model(selected)
    )
    recipe = GemmaTrainingRecipe(model=selected, revision=PINNED_REVISIONS[selected])
    with init_empty_weights(include_buffers=True):
        model = loader(config)
        targets = matched_targets(model, selected)
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        adapted = get_peft_model(model, lora_config(recipe))
    if any(parameter.device.type != "meta" for parameter in adapted.parameters()):
        raise RuntimeError("gemma_training_meta_inspection_allocated_weights")
    trainable = [
        name
        for name, parameter in adapted.named_parameters()
        if parameter.requires_grad
    ]
    if not trainable or any("lora_" not in name for name in trainable):
        raise RuntimeError("gemma_training_meta_unexpected_trainables")
    return {
        "loader": type(model).__name__,
        "target_modules": targets,
        "text_layers": config.text_config.num_hidden_layers,
        "parameter_count": parameter_count,
        "model_weights_loaded": False,
        "peft_wrapper": type(adapted).__name__,
        "meta_lora_rank": 16,
        "meta_lora_trainable_tensors": len(trainable),
        "gpu_qualified": False,
    }


class GemmaSession(Session):
    """Reuse native sampler, masked loss, optimizer/RNG state and reload checks."""

    def __init__(
        self,
        profile: GemmaTrainingRecipe,
        snapshot: Path,
        adapter: Path | None = None,
    ):
        require_owner()
        profile.validate()
        import torch
        from peft import PeftModel, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoTokenizer, BitsAndBytesConfig

        probe_runtime()
        torch.manual_seed(profile.seed)
        torch.cuda.manual_seed_all(profile.seed)
        self.torch = torch
        self.profile = profile
        self.tokenizer = AutoTokenizer.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
        )
        kwargs: dict[str, Any] = {}
        if profile.quantization == "nf4":
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        started = time.monotonic()
        loader = getattr(
            importlib.import_module("transformers"), loader_for_model(profile.model)
        )
        base = loader.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.bfloat16,
            device_map={"": 0},
            attn_implementation="sdpa",
            **kwargs,
        )
        require_cuda_placement(base)
        self.target_modules = matched_targets(base, profile.model)
        base.config.use_cache = False
        if profile.quantization == "nf4":
            base = prepare_model_for_kbit_training(
                base,
                use_gradient_checkpointing=profile.gradient_checkpointing,
                gradient_checkpointing_kwargs={"use_reentrant": False},
            )
        else:
            base.requires_grad_(False)
            if profile.gradient_checkpointing:
                base.gradient_checkpointing_enable(
                    gradient_checkpointing_kwargs={"use_reentrant": False},
                )
                base.enable_input_require_grads()
        if adapter is None:
            self.model = get_peft_model(
                base,
                lora_config(profile),
            )
        else:
            config = json.loads((adapter / "adapter_config.json").read_text())
            if config.get("target_modules") != target_modules_for(profile.model):
                raise ValueError("gemma_training_adapter_targets_changed")
            self.model = PeftModel.from_pretrained(base, adapter, is_trainable=True)
        self.placement = require_cuda_placement(self.model)
        self.parameters = [p for p in self.model.parameters() if p.requires_grad]
        if not self.parameters or any(
            p.requires_grad and "lora_" not in name
            for name, p in self.model.named_parameters()
        ):
            raise RuntimeError("gemma_training_unexpected_trainable_base")
        self.optimizer = torch.optim.AdamW(
            self.parameters,
            lr=profile.learning_rate,
            weight_decay=0.01,
        )
        self.load_seconds = time.monotonic() - started
        self.step = 0
        self.target_tokens = 0
        self.logs: list[dict] = []
        self.base_hash = tensor_hash(
            (name, p)
            for name, p in self.model.named_parameters()
            if not p.requires_grad
        )
        self.initial_adapter_hash = self.adapter_hash()

    def context_backward(self, row: dict) -> dict[str, Any]:
        """Full-context memory/backward stress, unsupervised padding, no update."""
        count = self.profile.context - len(row["input_ids"])
        stress = {
            "input_ids": [row["input_ids"][0]] * count + row["input_ids"],
            "attention_mask": [1] * self.profile.context,
            "labels": [-100] * count + row["labels"],
        }
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        loss, tokens = loss_for(self.model, self.batch(stress))
        value = finite(loss, "context_backward_loss")
        loss.backward()
        norm = self.torch.nn.utils.clip_grad_norm_(self.parameters, 1.0)
        finite(norm, "context_backward_gradient")
        self.optimizer.zero_grad(set_to_none=True)
        return {
            "tokens": self.profile.context,
            "supervised_tokens": tokens,
            "loss": value,
        }


def _require_offline() -> None:
    if any(
        os.environ.get(name) != "1"
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    ):
        raise ValueError("gemma_training_offline_required")


def _checkpoint_result(
    output: Path,
    checkpoint: Path,
    fingerprint: str,
    identity: dict,
    hardware: dict,
) -> dict:
    receipt = verified_checkpoint(checkpoint, fingerprint)
    result = {
        "schema_version": 1,
        "kind": "gemma4_adapter_seal",
        "fingerprint": fingerprint,
        "identity": identity,
        "hardware": hardware,
        "checkpoint_receipt": receipt,
        "activation_allowed": False,
        "evaluation_required": True,
        "adapter_sha256": file_digest(checkpoint / "adapter_model.safetensors"),
    }
    write_json(output / "seal.json", result)
    return result


def mask_evidence(document: dict, records: dict) -> dict:
    """Record validation of native spans separately from numerical loss parity."""
    return {
        "basis": "validated_native_token_spans",
        "encoded_release_sha256": document["encoded_release_sha256"],
        "sequences": {split: len(rows) for split, rows in records.items()},
        "supervised_tokens": {
            split: sum(
                sum(token != -100 for token in row["labels"][1:]) for row in rows
            )
            for split, rows in records.items()
        },
        "numerical_loss_parity_measured": False,
    }


def _training_stage(
    request: dict,
    output: Path,
    stage: str,
    updates: int,
    recipe: GemmaTrainingRecipe,
    snapshot: Path,
    records: dict,
    fingerprint: str,
    session_factory: Callable,
    mask_evidence: dict,
) -> dict:
    checkpoint = request.get("checkpoint")
    adapter = operator_path(checkpoint) if checkpoint else None
    previous = verified_checkpoint(adapter, fingerprint) if adapter else None
    if stage in {"train", "resume"}:
        proof = read_json(request["qualification"])
        require_qualification(proof, fingerprint)
        if proof["smoke_metrics"]["first"]["mask_evidence"] != mask_evidence:
            raise ValueError("gemma_training_qualification_mask_changed")
        verified_checkpoint(proof["checkpoint"], fingerprint)
        for name, checksum in proof.get("artifacts", {}).items():
            if (
                file_digest(
                    operator_path(inside(Path(request["qualification"]).parent, name))
                )
                != checksum
            ):
                raise ValueError("gemma_training_qualification_artifact_changed")
    session = session_factory(recipe, snapshot, adapter)
    training = records["train"]
    validation = records["validation"]
    reload_ok = (
        session.restore(adapter, validation[0], fingerprint) if adapter else False
    )
    initial = session.step
    if previous is not None and initial != previous["step"]:
        raise ValueError("gemma_training_resume_step_changed")
    before = session.evaluate(validation)
    seconds = session.train(
        training,
        updates,
        families=[row["problem_group"] for row in training],
    )
    after = session.evaluate(validation)
    checks = session.checks()
    checks["mask"] = all(
        count > 0 for count in mask_evidence["supervised_tokens"].values()
    )
    checks["reload"] = reload_ok
    if (
        checks.get("frozen_base") is not True
        or checks.get("updated_adapter") is not True
    ):
        raise RuntimeError("gemma_training_invariants_failed")
    if session.step != initial + updates:
        raise RuntimeError("gemma_training_update_count_mismatch")
    details = {}
    if stage == "smoke-resume":
        details["context_backward"] = session.context_backward(validation[0])
        checks.update(
            resume=reload_ok and initial > 0,
            context_backward=True,
            adapter_effect=not session.torch.equal(
                session.probe(validation[0]),
                session.probe(validation[0], disable=True),
            ),
        )
    pending = output / ".checkpoint-pending"
    session.save(pending, validation[0], fingerprint)
    verified_checkpoint(pending, fingerprint)
    pending.rename(output / "checkpoint")
    result = {
        "schema_version": 1,
        "stage": stage,
        "fingerprint": fingerprint,
        "checks": checks,
        "mask_evidence": mask_evidence,
        "initial_step": initial,
        "global_step": session.step,
        "target_tokens": session.target_tokens,
        "additional_updates": updates,
        "training_rows": len(training),
        "validation_rows": len(validation),
        "initial_validation": before,
        "validation": after,
        "training_seconds": seconds,
        "steps": session.logs,
        "details": details,
        "checkpoint": str(output / "checkpoint"),
        "activation_allowed": False,
        "gpu_required": True,
        "cpu_fallback": False,
    }
    write_json(output / "metrics.json", result)
    return result


def normalize_request(request: dict) -> dict:
    """Adapt the existing remote coordinator payload without a second lifecycle."""
    if not isinstance(request.get("profile"), dict):
        return dict(request)
    encoded = read_json(request["manifest"])
    profile_data = encoded.get("model_profile")
    if not isinstance(profile_data, dict):
        raise ValueError("gemma_training_manifest_profile_required")
    recipe_fields = {field.name for field in fields(GemmaTrainingRecipe)}
    supplied = request["profile"]
    recipe = GemmaTrainingRecipe(
        **{key: value for key, value in supplied.items() if key in recipe_fields}
    )
    if supplied != recipe.identity():
        raise ValueError("gemma_training_coordinator_profile_mismatch")
    native_stage = request.get("stage")
    if not isinstance(native_stage, str):
        raise ValueError("gemma_training_stage_invalid")
    aliases = {
        "smoke-first": "smoke",
        "smoke-resume": "smoke-resume",
        "train-first": "train",
        "train-resume": "resume",
    }
    return {
        **request,
        "schema_version": 1,
        "stage": aliases.get(native_stage, native_stage),
        "model_profile": profile_data,
        "recipe": {
            key: value for key, value in supplied.items() if key in recipe_fields
        },
        "encoded_release": request["manifest"],
    }


def run(
    request: dict,
    *,
    session_factory: Callable = GemmaSession,
    runtime_probe: Callable = probe_runtime,
    owner_check: Callable = require_owner,
) -> dict:
    """Execute one stage; failure preserves its independent directory and status."""
    request = normalize_request(request)
    stage, updates = validate_request(request)
    _require_offline()
    recipe = GemmaTrainingRecipe(**request["recipe"])
    if "model_profile" in request:
        profile = GemmaProfile(**request["model_profile"])
    else:
        profile = GemmaProfile.load(operator_path(request["profile"]))
    recipe.validate_profile(profile)
    snapshot = operator_path(request["snapshot"])
    document, records = load_encoded(request["encoded_release"], profile)
    identity = execution_identity(profile, recipe, document, snapshot)
    dependencies = identity["environment"]
    if dependencies["status"] != "PASS":
        raise ValueError("gemma_training_dependencies_unqualified")
    identity["structure"] = inspect_structure(snapshot)
    # Admission is required even for a CUDA probe: no local or CI GPU surprises.
    owner_check()
    hardware = runtime_probe()
    fingerprint = identity_fingerprint(identity, hardware)
    output = operator_path(request["output"])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "identity.json", {"identity": identity, "hardware": hardware})
    write_json(output / "status.json", {"state": "failed", "stage": stage})
    if stage == "preflight":
        result = {
            "status": "PREPARED",
            "fingerprint": fingerprint,
            "model_loaded": False,
            "gpu_qualified": False,
            "training_qualified": False,
            "activation_allowed": False,
            "gpu_required": True,
            "cpu_fallback": False,
        }
        write_json(output / "preflight.json", result)
    elif stage == "seal":
        result = _checkpoint_result(
            output,
            operator_path(request["checkpoint"]),
            fingerprint,
            identity,
            hardware,
        )
    else:
        result = _training_stage(
            request,
            output,
            stage,
            updates,
            recipe,
            snapshot,
            records,
            fingerprint,
            session_factory,
            mask_evidence(document, records),
        )
    write_json(output / "status.json", {"state": "succeeded", "stage": stage})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    result = run(read_json(args.request))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
