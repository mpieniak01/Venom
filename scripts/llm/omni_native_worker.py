"""Run one pinned Omni generation in an offline CUDA-only subprocess."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import math
import sys
import time
import wave
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any
from unittest.mock import patch

MIB = 2**20
OUTPUT_HZ = 24000
MAX_INPUT_TOKENS = 4096
MAX_OUTPUT_TOKENS = 128
SNAPSHOT = Path("/model")
PIN = Path("/job/omni_native_snapshot.json")


class WorkerError(Exception):
    """A stable error code for the parent, without inference content."""


def verify_snapshot() -> str:
    identity = json.loads(PIN.read_text(encoding="utf-8"))
    entries = identity["files"]
    actual = {
        p.relative_to(SNAPSHOT).as_posix() for p in SNAPSHOT.rglob("*") if p.is_file()
    }
    if actual != entries.keys():
        raise WorkerError("omni_native_snapshot_invalid")
    for name, entry in entries.items():
        path = SNAPSHOT / name
        if path.resolve() != path or path.stat().st_size != entry["size"]:
            raise WorkerError("omni_native_snapshot_invalid")
        with path.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != entry["sha256"]:
                raise WorkerError("omni_native_snapshot_invalid")
    return str(identity["revision"])


def gpu_budget(torch: Any) -> None:
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise WorkerError("omni_native_cuda_unavailable")
    free, total = torch.cuda.mem_get_info()
    budget = min(free - 640 * MIB, 11 * 1024 * MIB - (total - free))
    if budget < 4700 * MIB:
        raise WorkerError("omni_native_gpu_busy")
    torch.cuda.set_per_process_memory_fraction(budget / total)


def media_content(row: dict[str, Any]) -> list[dict[str, Any]]:
    import numpy as np
    from PIL import Image
    from scipy.signal import resample_poly

    media = []
    if row.get("image"):
        image_bytes = base64.b64decode(row["image"], validate=True)
        with Image.open(io.BytesIO(image_bytes), formats=["JPEG", "PNG"]) as image:
            image.thumbnail((1280, 1280))
            media.append({"type": "image", "image": image.convert("RGB")})
    signal = np.frombuffer(base64.b64decode(row["pcm"], validate=True), dtype="<i2")
    waveform = signal.astype(np.float32) / 32768
    rate = int(row["sample_rate"])
    if rate != 16000:
        scale = math.gcd(16000, rate)
        waveform = resample_poly(waveform, 16000 // scale, rate // scale)
    media.append({"type": "audio", "audio": waveform})
    return media


def conversation(request: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = "Answer the latest spoken question in Polish. Be concise. Ask for clarification when needed."
    if request["mode"] == "interleaved":
        prompt += " Respond with interleaved text and audio."
    messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
    for row in request["history"]:
        content = media_content(row) if row.get("pcm") else row["content"]
        messages.append({"role": row["role"], "content": content})
    messages.append({"role": "user", "content": media_content(request)})
    return messages


def decode_wav(codec: Any, output: Any) -> bytes:
    import numpy as np

    frames = int(output.audio_lengths[0])
    if frames <= 0:
        raise WorkerError("omni_native_no_audio")
    audio = codec.decode(output.audio_codes[:1, :, :frames]).audio_values[0]
    samples = audio.float().flatten().cpu().numpy()
    if not samples.size or not np.isfinite(samples).all() or not np.any(samples):
        raise WorkerError("omni_native_no_audio")
    pcm = np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setparams((1, 2, OUTPUT_HZ, 0, "NONE", "not compressed"))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


@dataclass(frozen=True)
class LoadedModel:
    revision: str
    processor: Any
    model: Any
    codec: Any


def load_model() -> LoadedModel:
    revision = verify_snapshot()
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    gpu_budget(torch)
    processor = AutoProcessor.from_pretrained(
        SNAPSHOT, local_files_only=True, trust_remote_code=True
    )
    model = AutoModelForMultimodalLM.from_pretrained(
        SNAPSHOT,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    ).eval()
    codec = processor.audio_tokenizer.to(device=model.device).eval()
    if any(p.device.type != "cuda" for m in (model, codec) for p in m.parameters()):
        raise WorkerError("omni_native_cuda_unavailable")
    return LoadedModel(revision, processor, model, codec)


def generate_turn(request: dict[str, Any], loaded: LoadedModel) -> dict[str, Any]:
    import torch

    processor, model, codec = loaded.processor, loaded.model, loaded.codec
    model_ready = time.perf_counter()
    mode = request["mode"]
    torch.manual_seed(42)
    with torch.inference_mode(), contextlib.ExitStack() as stack:
        # The pinned revision was qualified with the reference CUDA convolution.
        modules = {
            type(model.model.language_model).__module__,
            type(codec.decoder.lfm).__module__,
        }
        for name in modules:
            stack.enter_context(
                patch.object(
                    import_module(name), "can_use_lfm3_conv", return_value=False
                )
            )
        inputs = processor.apply_chat_template(
            conversation(request),
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            add_generation_prompt=True,
        ).to(device="cuda", dtype=torch.bfloat16)
        prompt_length = int(inputs["input_ids"].shape[1])
        if prompt_length > MAX_INPUT_TOKENS:
            raise WorkerError("omni_native_context_too_large")
        prepared = time.perf_counter()
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_OUTPUT_TOKENS,
            generation_mode=mode,
            audio_temperature=0.4,
            audio_repetition_penalty=1.2,
        )
        torch.cuda.synchronize()
        generated = time.perf_counter()
        wav = decode_wav(codec, output)
        text = None
        if mode == "interleaved":
            tokens = output.sequences[0, prompt_length : output.sequence_lengths[0]]
            text = (
                processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()
                or None
            )
        torch.cuda.synchronize()
    return {
        "model_revision": loaded.revision,
        "text": text,
        "wav": base64.b64encode(wav).decode("ascii"),
        "timings_ms": {
            "load": 0,
            "prepare": round((prepared - model_ready) * 1000),
            "generate": round((generated - prepared) * 1000),
            "decode": round((time.perf_counter() - generated) * 1000),
        },
        "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / MIB),
        "generation_count": 1,
    }


def main() -> None:
    started = time.perf_counter()
    request = json.load(sys.stdin)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = load_model()
            load_ms = round((time.perf_counter() - started) * 1000)
            result = generate_turn(request, model)
            result["timings_ms"]["load"] = load_ms
    except WorkerError as exc:
        result = {"error": str(exc)}
    except Exception as exc:
        import torch

        if isinstance(exc, torch.cuda.OutOfMemoryError):
            result = {"error": "omni_native_gpu_busy"}
        else:
            raise
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
