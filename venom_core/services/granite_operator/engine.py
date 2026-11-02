"""Optional, isolated PyTorch/PEFT worker. Never imported by application startup."""

from __future__ import annotations

import copy
import importlib.metadata
import json
import math
import os
import sqlite3
import time
from pathlib import Path

from .contract import (
    TrainingProfile,
    digest,
    file_digest,
    inside,
    snapshot_metadata,
    write_json,
)
from .encoding import collate, encode
from .sampling import FamilyEpochOrder


def require_owner() -> None:
    """Accept only a live parent holding the host admission database."""
    database = os.environ.get("VENOM_GRANITE_ADMISSION_DB")
    if not database:
        raise RuntimeError("host_runtime_admission_required")
    with sqlite3.connect("file:" + database + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT 1 FROM lease WHERE pid=? AND owner='granite-training' "
            "AND engine='granite-training' AND run_id=? AND quarantine=0 AND cancelled=0",
            (os.getppid(), os.environ.get("VENOM_GRANITE_RUN_ID")),
        ).fetchone()
    if not row:
        raise RuntimeError("host_runtime_reservation_missing")


def tensor_hash(named) -> str:
    """Hash all selected tensors, including frozen quantized storage."""
    import hashlib

    result = hashlib.sha256()
    for name, value in named:
        result.update(name.encode())
        value = value.detach().contiguous().cpu()
        result.update(str((value.dtype, tuple(value.shape))).encode())
        result.update(value.view(__import__("torch").uint8).numpy().tobytes())
    return result.hexdigest()


def loss_for(model, batch):
    """Compute shifted assistant-only loss without allocating ignored logits."""
    import torch

    labels = batch["labels"][0]
    positions = torch.where(labels[1:] != -100)[0]
    if not positions.numel():
        raise ValueError("granite_empty_shifted_mask")
    output = model(
        input_ids=batch["input_ids"],
        attention_mask=batch["attention_mask"],
        use_cache=False,
        logits_to_keep=positions,
    )
    targets = labels[positions + 1]
    loss = torch.nn.functional.cross_entropy(output.logits[0].float(), targets)
    return loss, int(targets.numel())


def finite(value, label: str) -> float:
    """Never serialize NaN/Inf as a successful training observation."""
    number = float(value.detach() if hasattr(value, "detach") else value)
    if not math.isfinite(number):
        raise RuntimeError("granite_nonfinite_" + label)
    return number


def encoded_rows(rows, tokenizer, profile):
    return [encode(row, tokenizer, profile.context) for row in rows]


def environment_identity(profile, manifest, tokenizer, snapshot: Path) -> dict:
    """Bind qualification to source, software, weights, template and hardware."""
    import torch

    package_root = Path(__file__).parent
    lock = (
        package_root.parents[2]
        / "requirements/locks/granite-operator-training-linux-py314.txt"
    )
    sources = {p.name: file_digest(p) for p in sorted(package_root.glob("*.py"))}
    return {
        "profile": profile.identity(),
        "datasets": manifest["datasets"],
        "code": sources,
        "dependency_lock": file_digest(lock),
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "transformers",
                "peft",
                "bitsandbytes",
                "trl",
                "datasets",
            )
        },
        "gpu": torch.cuda.get_device_name(0),
        "gpu_memory": torch.cuda.get_device_properties(0).total_memory,
        "cuda": torch.version.cuda,
        "template": digest(tokenizer.chat_template),
        "checkpoint_config": file_digest(snapshot / "config.json"),
        "snapshot_metadata": snapshot_metadata(snapshot),
        "weights": {
            p.name: file_digest(p) for p in sorted(snapshot.glob("*.safetensors"))
        },
    }


class Session:
    """One CUDA owner, one base and one adapter; lifetime bounded by subprocess."""

    def __init__(
        self, profile: TrainingProfile, snapshot: Path, adapter: Path | None = None
    ):
        require_owner()
        profile.validate()
        import torch
        from peft import (
            LoraConfig,
            PeftModel,
            get_peft_model,
            prepare_model_for_kbit_training,
        )
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        if not torch.cuda.is_available():
            raise RuntimeError("granite_cuda_required")
        torch.manual_seed(profile.seed)
        torch.cuda.manual_seed_all(profile.seed)
        self.torch = torch
        self.profile = profile
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        kwargs = {}
        if profile.quantization == "nf4":
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        start = time.monotonic()
        base = AutoModelForCausalLM.from_pretrained(
            snapshot,
            local_files_only=True,
            dtype=torch.bfloat16,
            device_map={"": 0},
            attn_implementation="sdpa",
            **kwargs,
        )
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
                    gradient_checkpointing_kwargs={"use_reentrant": False}
                )
                base.enable_input_require_grads()
        if adapter is None:
            self.model = get_peft_model(
                base,
                LoraConfig(
                    r=profile.rank,
                    lora_alpha=profile.alpha,
                    lora_dropout=profile.dropout,
                    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                    bias="none",
                    task_type="CAUSAL_LM",
                ),
            )
        else:
            self.model = PeftModel.from_pretrained(base, adapter, is_trainable=True)
        self.load_seconds = time.monotonic() - start
        self.parameters = [p for p in self.model.parameters() if p.requires_grad]
        if not self.parameters or any(
            p.requires_grad and "lora_" not in name
            for name, p in self.model.named_parameters()
        ):
            raise RuntimeError("granite_unexpected_trainable_base")
        self.optimizer = torch.optim.AdamW(
            self.parameters, lr=profile.learning_rate, weight_decay=0.01
        )
        self.step = 0
        self.target_tokens = 0
        self.logs: list[dict] = []
        self.base_hash = tensor_hash(
            (n, p) for n, p in self.model.named_parameters() if not p.requires_grad
        )
        self.initial_adapter_hash = self.adapter_hash()

    def adapter_hash(self):
        return tensor_hash(
            (n, p) for n, p in self.model.named_parameters() if p.requires_grad
        )

    def batch(self, row):
        return {
            k: v.to("cuda")
            for k, v in collate([row], self.tokenizer.pad_token_id, self.torch).items()
        }

    def train(self, rows, updates: int, *, families: list[str] | None = None):
        """Resume the selected row policy; dropout RNG is checkpointed separately."""
        if not rows or type(updates) is not int or updates < 1:
            raise ValueError("granite_training_rows_or_updates_invalid")
        sampler = None
        if self.profile.row_order == FamilyEpochOrder.policy:
            if families is None or len(families) != len(rows):
                raise ValueError("granite_sampling_families_required")
            sampler = FamilyEpochOrder(families, self.profile.seed)
            expected = sampler.identity(self.step * self.profile.accumulation)
            if getattr(self, "sampling_state", expected) != expected:
                raise ValueError("granite_sampling_checkpoint_changed")
            self.sampling_state = expected
        self.model.train()
        start = time.monotonic()
        for _ in range(updates):
            self.optimizer.zero_grad(set_to_none=True)
            total = 0.0
            tokens = 0
            for micro in range(self.profile.accumulation):
                position = self.step * self.profile.accumulation + micro
                index = sampler.index(position) if sampler else position % len(rows)
                loss, count = loss_for(self.model, self.batch(rows[index]))
                total += finite(loss.detach(), "loss") / self.profile.accumulation
                (loss / self.profile.accumulation).backward()
                tokens += count
            norm = self.torch.nn.utils.clip_grad_norm_(self.parameters, 1.0)
            finite(norm, "gradient")
            self.optimizer.step()
            self.step += 1
            self.target_tokens += tokens
            if sampler:
                self.sampling_state = sampler.identity(
                    self.step * self.profile.accumulation
                )
            event = {
                "step": self.step,
                "loss": total,
                "gradient_norm": float(norm),
                "target_tokens": self.target_tokens,
                "elapsed_seconds": time.monotonic() - start,
            }
            self.logs.append(event)
            print(json.dumps(event), flush=True)
        self.torch.cuda.synchronize()
        return time.monotonic() - start

    def evaluate(self, rows):
        self.model.eval()
        weighted = 0.0
        tokens = 0
        with self.torch.no_grad():
            for row in rows:
                loss, count = loss_for(self.model, self.batch(row))
                weighted += finite(loss, "validation") * count
                tokens += count
        return {"assistant_nll": weighted / tokens, "target_tokens": tokens}

    def probe(self, row, disable=False):
        self.model.eval()
        batch = self.batch(row)
        position = self.torch.where(batch["labels"][0, 1:] != -100)[0][-1:]
        with self.torch.no_grad():
            if disable:
                with self.model.disable_adapter():
                    logits = self.model(
                        input_ids=batch["input_ids"],
                        attention_mask=batch["attention_mask"],
                        use_cache=False,
                        logits_to_keep=position,
                    ).logits
            else:
                logits = self.model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    use_cache=False,
                    logits_to_keep=position,
                ).logits
        return logits[0, 0].detach().float().cpu()

    def save(self, path: Path, probe_row, fingerprint: str):
        path.mkdir(parents=True, exist_ok=False)
        self.model.save_pretrained(path, safe_serialization=True)
        self.tokenizer.save_pretrained(path)
        state = {
            "step": self.step,
            "target_tokens": self.target_tokens,
            "optimizer": self.optimizer.state_dict(),
            "scheduler": {
                "kind": "constant",
                "step": self.step,
                "learning_rate": self.profile.learning_rate,
            },
            "cpu_rng": self.torch.get_rng_state(),
            "cuda_rng": self.torch.cuda.get_rng_state_all(),
            "probe": self.probe(probe_row),
        }
        if self.profile.row_order != "sequential":
            state["sampling"] = self.sampling_state
        self.torch.save(state, path / "training-state.pt")
        write_json(
            path / "receipt.json",
            {
                "fingerprint": fingerprint,
                "step": self.step,
                "files": {
                    p.name: file_digest(p) for p in path.iterdir() if p.is_file()
                },
            },
        )

    def restore(self, path: Path, probe_row, fingerprint: str):
        receipt = json.loads((path / "receipt.json").read_text())
        if receipt["fingerprint"] != fingerprint:
            raise ValueError("granite_checkpoint_fingerprint_changed")
        if any(file_digest(inside(path, n)) != h for n, h in receipt["files"].items()):
            raise ValueError("granite_checkpoint_corrupt")
        state = self.torch.load(
            path / "training-state.pt", map_location="cpu", weights_only=True
        )
        if not self.torch.allclose(
            self.probe(probe_row), state["probe"], atol=0.05, rtol=0.01
        ):
            raise RuntimeError("granite_reload_logits_mismatch")
        if state["scheduler"] != {
            "kind": "constant",
            "step": state["step"],
            "learning_rate": self.profile.learning_rate,
        }:
            raise RuntimeError("granite_scheduler_mismatch")
        sampling = state.get("sampling")
        if self.profile.row_order == "sequential":
            if sampling is not None:
                raise ValueError("granite_sampling_policy_mismatch")
        elif (
            not isinstance(sampling, dict)
            or sampling.get("policy") != self.profile.row_order
            or sampling.get("seed") != self.profile.seed
            or sampling.get("samples_seen") != state["step"] * self.profile.accumulation
        ):
            raise ValueError("granite_sampling_checkpoint_invalid")
        else:
            self.sampling_state = sampling
        self.optimizer.load_state_dict(state["optimizer"])
        self.step = state["step"]
        self.target_tokens = state["target_tokens"]
        self.torch.set_rng_state(state["cpu_rng"])
        self.torch.cuda.set_rng_state_all(state["cuda_rng"])
        return True

    def long_context(self, row):
        """Real configured-length backward pass; synthetic stress input, never corpus."""
        padded = copy.deepcopy(row)
        # A valid corpus may start with a direct answer and no tool observation.
        # Stress only an unsupervised turn; never pad the assistant target.
        padding = next(
            (m for m in reversed(padded["messages"]) if m["role"] == "tool"), None
        )
        if padding is None:
            padding = next(
                (m for m in reversed(padded["messages"]) if m["role"] == "user"), None
            )
        if padding is None:
            raise ValueError("granite_long_context_unsupervised_turn_missing")
        original = padding["content"]
        low, high = 0, self.profile.context * 2
        best = None
        while low <= high:
            middle = (low + high) // 2
            padding["content"] = original + " stress" * middle
            try:
                candidate = encode(padded, self.tokenizer, self.profile.context)
                best = candidate
                low = middle + 1
            except ValueError as error:
                if str(error) != "granite_context_or_offsets_invalid":
                    raise
                high = middle - 1
        if best is None or len(best["input_ids"]) < self.profile.context - 8:
            raise RuntimeError("granite_long_context_not_reached")
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        loss, _ = loss_for(self.model, self.batch(best))
        finite(loss, "long_context_loss")
        loss.backward()
        finite(
            self.torch.nn.utils.clip_grad_norm_(self.parameters, 1.0),
            "long_context_gradient",
        )
        self.optimizer.zero_grad(set_to_none=True)
        return {"tokens": len(best["input_ids"]), "loss": float(loss.detach())}

    def checks(self):
        return {
            "mask": True,
            "updated_adapter": self.adapter_hash() != self.initial_adapter_hash,
            "frozen_base": tensor_hash(
                (n, p) for n, p in self.model.named_parameters() if not p.requires_grad
            )
            == self.base_hash,
        }
