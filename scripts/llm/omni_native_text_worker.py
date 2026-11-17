"""One offline text-only native Omni PEFT generation, with loaded-weight evidence."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import time
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from omni_native_worker import SNAPSHOT, WorkerError, gpu_budget, verify_snapshot


def identity(request: dict) -> dict:
    expected = request["identity"]
    if expected["revision"] != verify_snapshot():
        raise WorkerError("omni_native_snapshot_invalid")
    for name, key in (
        ("adapter_config.json", "config_sha256"),
        ("adapter_model.safetensors", "weights_sha256"),
    ):
        with (Path("/adapter") / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected[key]:
                raise WorkerError("omni_native_adapter_changed")
    return expected


def generate(request: dict) -> dict:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    started = time.perf_counter()
    verified = identity(request)
    gpu_budget(torch)
    processor = AutoProcessor.from_pretrained(
        SNAPSHOT, local_files_only=True, trust_remote_code=True
    )
    base = AutoModelForMultimodalLM.from_pretrained(
        SNAPSHOT,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    ).eval()
    base.generation_config.temperature = None
    base.generation_config.top_k = None
    model = PeftModel.from_pretrained(base, "/adapter", is_trainable=False).eval()
    if any(p.device.type != "cuda" for p in model.parameters()):
        raise WorkerError("omni_native_cuda_unavailable")
    module = import_module(type(base.model.language_model).__module__)
    with (
        torch.inference_mode(),
        patch.object(module, "can_use_lfm3_conv", return_value=False),
    ):
        inputs = processor.apply_chat_template(
            request["messages"],
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            add_generation_prompt=True,
            enable_thinking=False,
        )
        length = int(inputs["input_ids"].shape[1])
        if length > 4096:
            raise WorkerError("omni_native_context_too_large")
        ready = time.perf_counter()
        output = model.generate(
            **inputs.to("cuda"),
            generation_mode="text",
            do_sample=False,
            max_new_tokens=request["max_tokens"],
            return_dict_in_generate=True,
        )
        tokens = output.sequences[0, length : int(output.sequence_lengths[0])]
        text = processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        torch.cuda.synchronize()
    if not text:
        raise WorkerError("omni_native_empty_text")
    return {
        "text": text,
        "identity": verified,
        "prompt_tokens": length,
        "output_tokens": len(tokens),
        "load_ms": round((ready - started) * 1000),
        "generate_ms": round((time.perf_counter() - ready) * 1000),
        "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20),
    }


def main() -> None:
    request = json.load(sys.stdin)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = generate(request)
    except WorkerError as exc:
        result = {"error": str(exc)}
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
