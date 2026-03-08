#!/usr/bin/env python3
"""Convert PEFT LoRA adapter to GGUF adapter artifact for Ollama."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_GGUF_NAME = "Adapter-F16-LoRA.gguf"


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_llama_cpp_convert_script(args: argparse.Namespace) -> Path:
    if args.convert_script:
        script = Path(args.convert_script).expanduser().resolve()
        if script.exists() and script.is_file():
            return script
        raise FileNotFoundError(f"convert script not found: {script}")

    if args.llama_cpp_dir:
        candidate = (
            Path(args.llama_cpp_dir).expanduser().resolve() / "convert_lora_to_gguf.py"
        )
        if candidate.exists() and candidate.is_file():
            return candidate
        raise FileNotFoundError(f"convert_lora_to_gguf.py not found in: {candidate}")

    env_script = str(os.getenv("VENOM_LLAMA_CPP_CONVERT_SCRIPT", "")).strip()
    if env_script:
        candidate = Path(env_script).expanduser().resolve()
        if candidate.exists() and candidate.is_file():
            return candidate

    env_dir = str(os.getenv("VENOM_LLAMA_CPP_DIR", "")).strip()
    if env_dir:
        candidate = Path(env_dir).expanduser().resolve() / "convert_lora_to_gguf.py"
        if candidate.exists() and candidate.is_file():
            return candidate

    repo_candidate = (
        _resolve_repo_root() / "tools" / "llama.cpp" / "convert_lora_to_gguf.py"
    )
    if repo_candidate.exists() and repo_candidate.is_file():
        return repo_candidate

    raise FileNotFoundError(
        "convert_lora_to_gguf.py not found. Set --convert-script or --llama-cpp-dir."
    )


def _resolve_hf_snapshot(repo_id: str) -> Path | None:
    normalized = repo_id.strip().strip("/")
    if "/" not in normalized:
        return None
    owner, name = normalized.split("/", 1)
    snapshots_dir = (
        _resolve_repo_root()
        / "models"
        / "cache"
        / "huggingface"
        / "hub"
        / f"models--{owner}--{name}"
        / "snapshots"
    )
    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return None
    snapshots = sorted(
        [p for p in snapshots_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for snapshot in snapshots:
        if (snapshot / "config.json").exists():
            return snapshot.resolve()
    return None


def _resolve_base_model_path(args: argparse.Namespace, adapter_dir: Path) -> Path:
    if args.base_model:
        candidate = Path(args.base_model).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
        snapshot = _resolve_hf_snapshot(args.base_model)
        if snapshot is not None:
            return snapshot
        raise FileNotFoundError(
            f"base model is not a local HF directory or cached repo snapshot: {args.base_model}"
        )

    metadata_file = adapter_dir.parent / "metadata.json"
    if metadata_file.exists():
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                parameters = payload.get("parameters")
                candidate_values = []
                if isinstance(parameters, dict):
                    candidate_values.append(
                        str(parameters.get("training_base_model") or "").strip()
                    )
                candidate_values.extend(
                    [
                        str(payload.get("effective_base_model") or "").strip(),
                        str(payload.get("base_model") or "").strip(),
                    ]
                )
                for value in candidate_values:
                    if not value:
                        continue
                    candidate = Path(value).expanduser()
                    if candidate.exists() and candidate.is_dir():
                        if (candidate / "config.json").exists():
                            return candidate.resolve()
                    snapshot = _resolve_hf_snapshot(value)
                    if snapshot is not None:
                        return snapshot
        except Exception:
            pass
    raise ValueError(
        "Cannot resolve base model path. Pass --base-model (local dir or repo id)."
    )


def _resolve_existing_gguf(adapter_dir: Path) -> Path | None:
    default = adapter_dir / DEFAULT_GGUF_NAME
    if default.exists() and default.is_file():
        return default.resolve()
    ggufs = sorted([p for p in adapter_dir.glob("*.gguf") if p.is_file()])
    return ggufs[0].resolve() if ggufs else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert LoRA adapter directory to GGUF adapter for Ollama."
    )
    parser.add_argument(
        "--adapter-dir", required=True, help="Path to adapter directory."
    )
    parser.add_argument(
        "--base-model",
        default="",
        help="HF local base model path or HF repo id (optional, auto from metadata when omitted).",
    )
    parser.add_argument("--llama-cpp-dir", default="", help="Path to llama.cpp root.")
    parser.add_argument(
        "--convert-script",
        default="",
        help="Path to convert_lora_to_gguf.py.",
    )
    parser.add_argument(
        "--outtype", default="f16", choices=["f16", "f32"], help="GGUF output type."
    )
    parser.add_argument("--force", action="store_true", help="Force reconversion.")
    args = parser.parse_args()

    adapter_dir = Path(args.adapter_dir).expanduser().resolve()
    if not adapter_dir.exists() or not adapter_dir.is_dir():
        raise FileNotFoundError(f"adapter dir not found: {adapter_dir}")
    if not (adapter_dir / "adapter_config.json").exists():
        raise FileNotFoundError(
            f"adapter_config.json missing in adapter dir: {adapter_dir}"
        )

    if not args.force:
        existing = _resolve_existing_gguf(adapter_dir)
        if existing is not None:
            print(existing)
            return 0

    base_model_path = _resolve_base_model_path(args, adapter_dir)
    convert_script = _resolve_llama_cpp_convert_script(args)
    cmd = [
        sys.executable,
        str(convert_script),
        "--outtype",
        args.outtype,
        "--base",
        str(base_model_path),
        str(adapter_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        details = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise RuntimeError(f"LoRA->GGUF conversion failed: {details}")

    resolved = _resolve_existing_gguf(adapter_dir)
    if resolved is None:
        raise RuntimeError("conversion finished but no *.gguf produced")
    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
