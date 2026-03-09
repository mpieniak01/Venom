#!/usr/bin/env python3
"""Create Ollama model with converted GGUF adapter for Academy run."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def _resolve_adapter_dir(args: argparse.Namespace) -> Path:
    if args.adapter_dir:
        adapter_dir = Path(args.adapter_dir).expanduser().resolve()
    else:
        adapter_id = args.adapter_id.strip()
        if not adapter_id:
            raise ValueError("adapter-id is required when adapter-dir is not provided")
        adapter_dir = (
            Path(args.models_dir).expanduser().resolve() / adapter_id / "adapter"
        )
    if not adapter_dir.exists() or not adapter_dir.is_dir():
        raise FileNotFoundError(f"adapter dir not found: {adapter_dir}")
    return adapter_dir


def _run_conversion(adapter_dir: Path, args: argparse.Namespace) -> Path:
    cmd = [
        "python3",
        str(Path(__file__).resolve().parent / "convert_lora_adapter_to_gguf.py"),
        "--adapter-dir",
        str(adapter_dir),
    ]
    if args.base_model:
        cmd.extend(["--base-model", args.base_model])
    if args.llama_cpp_dir:
        cmd.extend(["--llama-cpp-dir", args.llama_cpp_dir])
    if args.convert_script:
        cmd.extend(["--convert-script", args.convert_script])
    cmd.extend(["--outtype", args.outtype])
    if args.force_convert:
        cmd.append("--force")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        details = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise RuntimeError(f"adapter GGUF conversion failed: {details}")
    gguf_path = (
        Path((proc.stdout or "").strip().splitlines()[-1]).expanduser().resolve()
    )
    if not gguf_path.exists() or not gguf_path.is_file():
        raise RuntimeError(f"GGUF adapter file not found after conversion: {gguf_path}")
    return gguf_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Ollama model from base model + LoRA GGUF adapter."
    )
    parser.add_argument(
        "--adapter-id", default="", help="Adapter ID (self_learning_xxx)."
    )
    parser.add_argument(
        "--adapter-dir", default="", help="Direct path to adapter directory."
    )
    parser.add_argument(
        "--models-dir",
        default="data/models",
        help="Models root dir (used with --adapter-id).",
    )
    parser.add_argument("--from-model", required=True, help="Ollama FROM model.")
    parser.add_argument(
        "--output-model", required=True, help="Target Ollama model name."
    )
    parser.add_argument(
        "--base-model", default="", help="HF base model path or repo id."
    )
    parser.add_argument("--llama-cpp-dir", default="", help="Path to llama.cpp root.")
    parser.add_argument(
        "--convert-script", default="", help="Path to convert_lora_to_gguf.py."
    )
    parser.add_argument("--outtype", default="f16", choices=["f16", "f32"])
    parser.add_argument("--force-convert", action="store_true")
    args = parser.parse_args()

    adapter_dir = _resolve_adapter_dir(args)
    gguf_path = _run_conversion(adapter_dir, args)
    modelfile_content = f"FROM {args.from_model}\nADAPTER {gguf_path}\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".Modelfile", delete=False
    ) as tmp:
        tmp.write(modelfile_content)
        modelfile_path = Path(tmp.name)

    proc = subprocess.run(
        ["ollama", "create", args.output_model, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        details = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise RuntimeError(f"ollama create failed: {details}")
    print(args.output_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
