"""ONNX build helpers for ModelManager."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from venom_core.core.model_manager_discovery import ONNX_METADATA_FILENAME


class LoggerLike(Protocol):
    def info(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


def build_onnx_llm_model(
    *,
    model_name: str,
    output_dir: Optional[str],
    execution_provider: str,
    precision: str,
    builder_script: Optional[str],
    normalize_slug_fn: Callable[[str], str],
    logger: LoggerLike,
) -> Dict[str, Any]:
    """Build ONNX LLM model via onnxruntime-genai builder and persist metadata."""
    if not model_name or not re.match(r"^[\w\-.:/]+$", model_name):
        return {
            "success": False,
            "message": "Nieprawidłowa nazwa modelu ONNX.",
        }

    exec_provider = (execution_provider or "cuda").strip().lower()
    prec = (precision or "int4").strip().lower()
    if exec_provider not in {"cuda", "cpu", "directml"}:
        return {
            "success": False,
            "message": "execution_provider musi być jednym z: cuda, cpu, directml",
        }
    if prec not in {"int4", "fp16"}:
        return {"success": False, "message": "precision musi być: int4 lub fp16"}

    default_script = os.getenv(
        "ONNX_GENAI_BUILDER_SCRIPT",
        "third_party/onnxruntime-genai/src/python/py/models/builder.py",
    )
    script_path = Path(builder_script or default_script).expanduser().resolve()
    if not script_path.exists():
        return {
            "success": False,
            "message": (
                "Nie znaleziono skryptu builder.py. "
                "Ustaw ONNX_GENAI_BUILDER_SCRIPT lub parametr builder_script."
            ),
            "builder_script": str(script_path),
        }

    if output_dir:
        output_path = Path(output_dir).expanduser().resolve()
    else:
        slug = normalize_slug_fn(model_name)
        output_path = (Path("./models") / f"{slug}-onnx").resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable or "python",
        str(script_path),
        "-m",
        model_name,
        "-e",
        exec_provider,
        "-p",
        prec,
        "-o",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Timeout podczas build ONNX modelu."}
    except Exception as exc:
        return {"success": False, "message": f"Błąd build ONNX: {exc}"}

    if result.returncode != 0:
        return {
            "success": False,
            "message": "Builder ONNX zakończył się błędem.",
            "exit_code": result.returncode,
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip(),
        }

    metadata = {
        "provider": "onnx",
        "runtime": "onnx",
        "model_name": model_name,
        "output_dir": str(output_path),
        "precision": prec,
        "execution_provider": exec_provider,
        "builder_script": str(script_path),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    metadata_path = output_path / ONNX_METADATA_FILENAME
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    logger.info("Zbudowano ONNX model: %s -> %s", model_name, output_path)
    return {
        "success": True,
        "message": "Model ONNX zbudowany pomyślnie.",
        "model_name": model_name,
        "output_dir": str(output_path),
        "metadata_path": str(metadata_path),
        "stdout": result.stdout.strip(),
    }
