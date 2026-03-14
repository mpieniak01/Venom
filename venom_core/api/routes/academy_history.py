"""History and adapter metadata helpers for Academy routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from venom_core.services.academy import adapter_runtime_service as _adapter_runtime
from venom_core.services.academy.adapter_metadata_service import (
    AdapterMetadataContext,
    build_canonical_adapter_metadata,
    write_canonical_adapter_metadata,
)


def load_jobs_history(jobs_file: Path, *, logger: Any) -> list[dict[str, Any]]:
    """Load JSONL training-job history."""
    if not jobs_file.exists():
        return []

    jobs: list[dict[str, Any]] = []
    try:
        with open(jobs_file, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    jobs.append(json.loads(line))
                except Exception as exc:
                    logger.warning("Failed to parse jobs history line: %s", exc)
    except Exception as exc:
        logger.warning("Failed to load jobs history file: %s", exc)
    return jobs


def save_job_to_history(
    job: dict[str, Any],
    jobs_file: Path,
    *,
    logger: Any,
) -> None:
    """Append one job record to JSONL history."""
    jobs_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(jobs_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to save job to history: %s", exc)


def update_job_in_history(
    job_id: str,
    updates: dict[str, Any],
    jobs_file: Path,
    *,
    logger: Any,
) -> None:
    """Update one job record in JSONL history."""
    if not jobs_file.exists():
        return

    try:
        jobs = load_jobs_history(jobs_file, logger=logger)
        updated = False
        for job in jobs:
            if job.get("job_id") == job_id:
                job.update(updates)
                updated = True
                break
        if not updated:
            return

        with open(jobs_file, "w", encoding="utf-8") as handle:
            for job in jobs:
                handle.write(json.dumps(job, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to update job in history: %s", exc)


def _training_parameters(job: dict[str, Any]) -> dict[str, Any]:
    parameters = job.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def _apply_onnx_conversion_plan(
    *, metadata: dict[str, Any], parameters: dict[str, Any]
) -> str:
    onnx_conversion_mode = (
        str(parameters.get("onnx_conversion_mode") or "none").strip().lower()
    )
    if onnx_conversion_mode != "none":
        metadata["onnx_conversion_plan"] = {
            "mode": onnx_conversion_mode,
            "status": "planned",
            "target_runtime": "onnx",
        }
    return onnx_conversion_mode


def _append_optional_ollama_metadata(
    *,
    metadata: dict[str, Any],
    runtime_id: str,
    adapter_dir: Path,
    base_model: str,
) -> None:
    if runtime_id != "ollama":
        return
    gguf_path = _adapter_runtime._ensure_ollama_adapter_gguf(
        adapter_dir=adapter_dir,
        from_model=base_model,
    )
    metadata["ollama_adapter_gguf_path"] = str(gguf_path)


def _write_optional_chat_signature(
    *,
    parameters: dict[str, Any],
    adapter_dir: Path,
    runtime_id: str,
    onnx_conversion_mode: str,
) -> None:
    if not bool(parameters.get("auto_sign_for_chat")):
        return
    from venom_core.services.academy.adapter_metadata_service import (
        write_adapter_chat_signature,
    )

    write_adapter_chat_signature(
        adapter_dir=adapter_dir,
        runtime_id=runtime_id or "vllm",
        model_id=str(parameters.get("chat_target_model_id") or "").strip() or None,
        signer=str(parameters.get("chat_signer") or "system").strip() or "system",
        conversion_mode=("gguf" if runtime_id == "ollama" else onnx_conversion_mode)
        or "none",
    )


def save_adapter_metadata(job: dict[str, Any], adapter_path: Path) -> None:
    """Persist deterministic adapter metadata after successful training."""
    parameters = _training_parameters(job)
    runtime_id = str(parameters.get("runtime_id") or "").strip().lower()
    base_model = str(job.get("base_model") or "").strip()
    adapter_dir = adapter_path.parent
    metadata = build_canonical_adapter_metadata(
        adapter_id=str(adapter_dir.name),
        base_model=base_model,
        created_at=str(job.get("finished_at") or datetime.now().isoformat()),
        source_flow="training",
        source="academy",
        training_params=parameters,
        context=AdapterMetadataContext(
            run_id=str(job.get("job_id") or adapter_dir.name),
            requested_runtime_id=runtime_id or None,
            requested_base_model=base_model,
            effective_runtime_id=runtime_id or None,
            effective_base_model=base_model,
            dataset_path=job.get("dataset_path"),
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
        ),
    )
    metadata["job_id"] = job.get("job_id")
    onnx_conversion_mode = _apply_onnx_conversion_plan(
        metadata=metadata,
        parameters=parameters,
    )
    _append_optional_ollama_metadata(
        metadata=metadata,
        runtime_id=runtime_id,
        adapter_dir=adapter_dir,
        base_model=base_model,
    )
    write_canonical_adapter_metadata(adapter_dir=adapter_dir, payload=metadata)
    _write_optional_chat_signature(
        parameters=parameters,
        adapter_dir=adapter_dir,
        runtime_id=runtime_id,
        onnx_conversion_mode=onnx_conversion_mode,
    )
