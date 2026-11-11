"""Merge the verified P1 adapter into a complete BF16 Omni checkpoint."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from scripts.academy.omni_pl_chat_data import sha256
from scripts.academy.omni_pl_chat_masks import verify_snapshot
from scripts.academy.omni_pl_chat_p1 import (
    STEPS,
    _checkpoint_hashes,
    _verify_boundary,
    _write_json,
)


def merge_p1() -> None:
    _verify_boundary()
    snapshot = Path("/inputs/model")
    output = Path("/out")
    checkpoint = output / f"checkpoint-{STEPS}"
    profile = json.loads((output / "profile.json").read_text())
    pin = verify_snapshot(snapshot, full=True)
    if profile["revision"] != pin["revision"] or profile["model"] != pin["repo"]:
        raise ValueError("P1 profile and merge base differ")
    if profile["train_sha256"] != sha256(Path("/inputs/train.jsonl")):
        raise ValueError("P1 profile and training data differ")
    if json.loads((checkpoint / "hashes.json").read_text()) != _checkpoint_hashes(
        checkpoint
    ):
        raise ValueError("P1 checkpoint differs from its receipt")

    import torch
    from peft import PeftModel
    from peft.tuners.lora import LoraLayer
    from safetensors import safe_open
    from transformers import AutoModelForMultimodalLM

    def digest(tensor) -> str:
        return hashlib.sha256(
            tensor.detach().contiguous().view(torch.uint8).numpy().tobytes()
        ).hexdigest()

    dest = output / "merged-hf-bf16"
    if dest.exists():
        raise FileExistsError(dest)
    temporary = Path(tempfile.mkdtemp(prefix="merged-hf-bf16.partial-", dir=output))
    base = AutoModelForMultimodalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cpu",
    )
    adapted = PeftModel.from_pretrained(base, checkpoint, is_trainable=False)
    before = {
        name: digest(layer.get_base_layer().weight)
        for name, layer in base.named_modules()
        if isinstance(layer, LoraLayer)
    }
    if not before or any(
        not name.startswith("model.language_model.") for name in before
    ):
        raise RuntimeError("unexpected P1 merge target")
    merged = adapted.merge_and_unload(safe_merge=True)
    changed = {
        f"{name}.weight": digest(merged.get_submodule(name).weight)
        for name, value in before.items()
        if digest(merged.get_submodule(name).weight) != value
    }
    if not changed:
        raise RuntimeError("merged checkpoint does not contain adapter changes")

    for name in pin["files"]:
        if name == "model.safetensors":
            continue
        path = temporary / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / name, path)
    # The source requests greedy decoding with two sampling-only flags.
    # Transformers accepts these when loading but rejects them when saving.
    normalized_generation_fields = []
    if not merged.generation_config.do_sample:
        for field in ("temperature", "top_k"):
            if getattr(merged.generation_config, field) is not None:
                setattr(merged.generation_config, field, None)
                normalized_generation_fields.append(field)
    merged.save_pretrained(temporary, safe_serialization=True, max_shard_size="5GB")
    weights = temporary / "model.safetensors"
    with (
        safe_open(weights, framework="pt") as result,
        safe_open(snapshot / "model.safetensors", framework="pt") as original,
    ):
        if set(result.keys()) != set(original.keys()):
            raise RuntimeError(
                "merged checkpoint tensor inventory differs from the full Omni base"
            )
        for key, expected in changed.items():
            if digest(result.get_tensor(key)) != expected:
                raise RuntimeError(f"{key}: merged tensor did not survive saving")
        tensor_count = len(result.keys())
    codec = temporary / "audio_tokenizer/model.safetensors"
    if sha256(codec) != pin["files"]["audio_tokenizer/model.safetensors"]["sha256"]:
        raise RuntimeError("original audio tokenizer was not preserved")
    receipt = {
        "source": pin["repo"],
        "revision": pin["revision"],
        "adapter_sha256": sha256(checkpoint / "adapter_model.safetensors"),
        "dtype": "bf16",
        "weights_sha256": sha256(weights),
        "tensor_count": tensor_count,
        "normalized_greedy_config_fields": normalized_generation_fields,
        "changed_language_tensors": changed,
        "audio_tokenizer_sha256": sha256(codec),
    }
    _write_json(temporary / "merge-receipt.json", receipt)
    temporary.rename(dest)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    merge_p1()
