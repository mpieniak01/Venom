#!/usr/bin/env python3
"""Targeted GPU qualification, including a CUDA backward step; no model downloads."""

import argparse
import importlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def inspect(mode):
    import torch

    errors = []
    versions = {}
    packages = [
        "torch",
        "transformers",
        "peft",
        "trl",
        "datasets",
        "accelerate",
        "axolotl",
    ]
    if mode == "qlora":
        packages.append("bitsandbytes")
    for name in packages:
        importlib.import_module(name)
        versions[name] = importlib.metadata.version(name)
    if sys.version_info[:2] != (3, 12):
        errors.append("Expected Python 3.12")
    if not torch.__version__.startswith("2.13.") or torch.version.cuda != "13.0":
        errors.append("PyTorch/CUDA differ from pinned stack")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; refusing CPU fallback")
    devices = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        with torch.cuda.device(index):
            bf16 = torch.cuda.is_bf16_supported()
            value = torch.randn(
                32, 32, device=f"cuda:{index}", dtype=torch.bfloat16, requires_grad=True
            )
            (value @ value.T).float().square().mean().backward()
            torch.cuda.synchronize(index)
        devices.append(
            {
                "index": index,
                "name": props.name,
                "memory_bytes": props.total_memory,
                "compute_capability": [props.major, props.minor],
                "bf16": bf16,
            }
        )
        if props.major < 8 or not bf16:
            errors.append(f"GPU {index}: Ampere+ and BF16 required")
    if mode == "qlora":
        import bitsandbytes as bnb

        layer = bnb.nn.Linear4bit(
            32, 32, bias=False, quant_type="nf4", compute_dtype=torch.bfloat16
        )
        layer.requires_grad_(False)
        layer = layer.cuda()
        x = torch.randn(2, 32, device="cuda", dtype=torch.bfloat16, requires_grad=True)
        layer(x).float().square().mean().backward()
        torch.cuda.synchronize()
        if x.grad is None or not torch.isfinite(x.grad).all():
            errors.append("4-bit backward failed")
    driver = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True
    ).splitlines()
    if any(int(version.split(".")[0]) < 580 for version in driver):
        errors.append("CUDA 13 requires NVIDIA driver >=580")
    free_disk = shutil.disk_usage("/workspace/data").free
    shm = shutil.disk_usage("/dev/shm").total
    if free_disk < 20 * 1024**3:
        errors.append(
            "Less than 20 GiB free; account separately for model/dataset/checkpoints"
        )
    if shm < 1024**3:
        errors.append("Shared memory <1 GiB; increase container shm before training")
    return {
        "ok": not errors,
        "errors": errors,
        "mode": mode,
        "python": platform.python_version(),
        "versions": versions,
        "cuda": torch.version.cuda,
        "drivers": driver,
        "gpus": devices,
        "free_disk_bytes": free_disk,
        "shm_bytes": shm,
        "test": "CUDA backward + NF4 backward for qlora; no real model training",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["qlora", "lora", "full"], default="qlora")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.mode)
    except Exception as exc:
        result = {"ok": False, "error_type": type(exc).__name__, "message": str(exc)}
    raw = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw + "\n")
    print(raw)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
