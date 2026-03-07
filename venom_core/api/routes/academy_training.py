"""Training lifecycle helpers for Academy routes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException

from venom_core.api.schemas.academy import AcademyJobSummary
from venom_core.services.academy.trainable_catalog_service import (
    _canonical_runtime_model_id,
    discover_runtime_model_families,
    resolve_runtime_compatibility,
)


def resolve_dataset_path(
    dataset_path: Optional[str],
    *,
    academy_training_dir: str,
    dataset_required_detail: str,
) -> str:
    """Resolve dataset path, using latest dataset_*.jsonl when not provided."""
    if dataset_path:
        return dataset_path
    training_dir = Path(academy_training_dir)
    if not training_dir.exists():
        raise HTTPException(status_code=400, detail=dataset_required_detail)
    datasets = sorted(training_dir.glob("dataset_*.jsonl"))
    if not datasets:
        raise HTTPException(status_code=400, detail=dataset_required_detail)
    return str(datasets[-1])


def ensure_trainable_base_model(
    *,
    request_base_model: Optional[str],
    is_model_trainable_fn: Callable[[str], bool],
) -> str:
    """Validate explicitly requested base model for Academy pipeline."""
    base_model = str(request_base_model or "").strip()
    if not base_model:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "MODEL_BASE_MODEL_REQUIRED",
                "message": (
                    "Training requires an explicit base_model selection. "
                    "Choose a trainable model from the Academy catalog."
                ),
                "reason_code": "MODEL_BASE_MODEL_REQUIRED",
            },
        )
    if not is_model_trainable_fn(base_model):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "MODEL_NOT_TRAINABLE",
                "message": (
                    f"Model '{base_model}' is not trainable. "
                    "Use /api/v1/system/llm-runtime/options "
                    "(model_catalog.trainable_models) to see supported models."
                ),
                "reason_code": "MODEL_NOT_TRAINABLE",
            },
        )
    return base_model


def _infer_training_provider(model_id: str) -> str:
    normalized = model_id.strip().lower()
    if ":" in normalized:
        return "ollama"
    if normalized.startswith("unsloth/"):
        return "unsloth"
    if "/" in normalized:
        return "huggingface"
    return "unknown"


async def validate_runtime_compatibility_for_base_model(
    *,
    base_model: str,
    runtime_id: Optional[str],
    manager: Any | None = None,
) -> None:
    """Reject runtime/base_model pairs that are outside Academy deploy contract."""
    normalized_runtime_id = str(runtime_id or "").strip().lower()
    if not normalized_runtime_id:
        return
    runtime_model_families: dict[str, set[str]] = {}
    if manager is not None and hasattr(manager, "list_local_models"):
        try:
            local_models = await manager.list_local_models()
        except Exception:
            local_models = []
        runtime_model_families = discover_runtime_model_families(local_models)
    compatibility = resolve_runtime_compatibility(
        provider=_infer_training_provider(base_model),
        available_runtime_ids=["vllm", "ollama", "onnx"],
        model_metadata={"name": base_model},
        model_id=base_model,
        runtime_model_families=runtime_model_families,
    )
    if compatibility.get(normalized_runtime_id):
        return
    compatible_runtimes = [
        runtime for runtime, allowed in compatibility.items() if bool(allowed)
    ]
    raise HTTPException(
        status_code=400,
        detail={
            "error": "MODEL_RUNTIME_INCOMPATIBLE",
            "message": (
                f"Model '{base_model}' is incompatible with runtime "
                f"'{normalized_runtime_id}'."
            ),
            "reason_code": "MODEL_RUNTIME_INCOMPATIBLE",
            "requested_runtime_id": normalized_runtime_id,
            "requested_base_model": base_model,
            "effective_base_model": _canonical_runtime_model_id(base_model),
            "compatible_runtimes": compatible_runtimes,
        },
    )


def build_job_record(
    *,
    dataset_path: str,
    base_model: str,
    output_dir: Path,
    request: Any,
) -> Dict[str, Any]:
    """Create queued training-job record persisted in history."""
    job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {
        "job_id": job_id,
        "job_name": job_id,
        "dataset_path": dataset_path,
        "base_model": base_model,
        "parameters": {
            "requested_runtime_id": getattr(request, "runtime_id", None),
            "requested_base_model": base_model,
            "effective_runtime_id": getattr(request, "runtime_id", None),
            "effective_base_model": base_model,
            "runtime_id": getattr(request, "runtime_id", None),
            "lora_rank": request.lora_rank,
            "learning_rate": request.learning_rate,
            "num_epochs": request.num_epochs,
            "batch_size": request.batch_size,
            "max_seq_length": request.max_seq_length,
        },
        "status": "queued",
        "started_at": datetime.now().isoformat(),
        "output_dir": str(output_dir),
    }


def curate_dataset_scope(
    *,
    request: Any,
    req: Any,
    resolve_conversion_file_ids_for_dataset_fn: Callable[..., List[str]],
    get_dataset_curator_fn: Callable[[], Any],
    collect_scope_counts_fn: Callable[[Any, Any], Dict[str, int]],
    ingest_uploads_for_curate_fn: Callable[[Any, List[str]], int],
    ingest_converted_files_for_curate_fn: Callable[[Any, Any, List[str]], int],
    logger: Any,
) -> Dict[str, Any]:
    """Run full dataset curation flow for selected scope."""
    conversion_file_ids = resolve_conversion_file_ids_for_dataset_fn(
        req=req,
        requested_ids=request.conversion_file_ids,
    )
    logger.info(
        "Curating dataset: lessons=%s git=%s task_history=%s uploads=%s converted=%s",
        request.include_lessons,
        request.include_git,
        request.include_task_history,
        len(request.upload_ids or []),
        len(conversion_file_ids),
    )
    curator = get_dataset_curator_fn()
    curator.clear()

    scope_counts = collect_scope_counts_fn(curator, request)
    uploads_count = 0
    if request.upload_ids:
        uploads_count = ingest_uploads_for_curate_fn(curator, request.upload_ids)
    converted_count = 0
    if conversion_file_ids:
        converted_count = ingest_converted_files_for_curate_fn(
            curator,
            req,
            conversion_file_ids,
        )
    removed = curator.filter_low_quality()
    dataset_path = curator.save_dataset(format=request.format)
    stats = curator.get_statistics()
    return {
        "dataset_path": dataset_path,
        "stats": stats,
        "scope_counts": scope_counts,
        "uploads_count": uploads_count,
        "converted_count": converted_count,
        "removed_low_quality": removed,
        "quality_profile": request.quality_profile,
    }


def preview_dataset_scope(
    *,
    request: Any,
    req: Any,
    resolve_conversion_file_ids_for_dataset_fn: Callable[..., List[str]],
    get_dataset_curator_fn: Callable[[], Any],
    collect_scope_counts_fn: Callable[[Any, Any], Dict[str, int]],
    ingest_uploads_for_preview_fn: Callable[[Any, List[str], List[str]], int],
    ingest_converted_files_for_preview_fn: Callable[
        [Any, Any, List[str], List[str]], int
    ],
    add_low_examples_warning_fn: Callable[[List[str], int, str], None],
    build_preview_samples_fn: Callable[[Any], List[Dict[str, str]]],
    logger: Any,
) -> Dict[str, Any]:
    """Run preview flow for selected scope without persisting dataset."""
    conversion_file_ids = resolve_conversion_file_ids_for_dataset_fn(
        req=req,
        requested_ids=request.conversion_file_ids,
    )
    logger.info(
        "Previewing dataset: lessons=%s git=%s task_history=%s uploads=%s converted=%s",
        request.include_lessons,
        request.include_git,
        request.include_task_history,
        len(request.upload_ids or []),
        len(conversion_file_ids),
    )
    curator = get_dataset_curator_fn()
    curator.clear()

    by_source = collect_scope_counts_fn(curator, request)
    warnings: List[str] = []
    if request.upload_ids:
        by_source["uploads"] = ingest_uploads_for_preview_fn(
            curator,
            request.upload_ids,
            warnings,
        )
    if conversion_file_ids:
        by_source["converted"] = ingest_converted_files_for_preview_fn(
            curator,
            req,
            conversion_file_ids,
            warnings,
        )

    removed = curator.filter_low_quality()
    stats = curator.get_statistics()
    total_examples = stats.get("total_examples", 0)
    add_low_examples_warning_fn(warnings, total_examples, request.quality_profile)
    samples = build_preview_samples_fn(curator)
    return {
        "total_examples": total_examples,
        "by_source": by_source,
        "removed_low_quality": removed,
        "warnings": warnings,
        "samples": samples,
    }


def find_job_or_404(job_id: str, *, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find job in history or raise 404 HTTPException."""
    job = next((j for j in jobs if j.get("job_id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


def sync_job_status_with_habitat(
    *,
    habitat: Any,
    job_id: str,
    job: Dict[str, Any],
    job_name: str,
    normalize_status_fn: Callable[[Optional[str]], str],
    terminal_statuses: set[str],
    update_job_fn: Callable[[str, Dict[str, Any]], None],
) -> tuple[Dict[str, Any], str]:
    """Sync runtime habitat status into persisted job history."""
    status_info = habitat.get_training_status(job_name)
    current_status = normalize_status_fn(status_info.get("status"))
    if current_status != job.get("status"):
        updates = {"status": current_status}
        if current_status in terminal_statuses:
            updates["finished_at"] = datetime.now().isoformat()
        if current_status == "finished":
            adapter_path = Path(job.get("output_dir", "")) / "adapter"
            if adapter_path.exists():
                updates["adapter_path"] = str(adapter_path)
        update_job_fn(job_id, updates)
        job.update(updates)
    return status_info, current_status


def save_finished_job_metadata(
    *,
    job: Dict[str, Any],
    current_status: str,
    save_adapter_metadata_fn: Callable[[Dict[str, Any], Path], None],
    log_internal_operation_failure_fn: Callable[[str], None],
) -> None:
    """Persist adapter metadata for successfully finished jobs."""
    if current_status != "finished" or not job.get("adapter_path"):
        return
    adapter_path_obj = Path(job["adapter_path"])
    if not adapter_path_obj.exists():
        return
    try:
        save_adapter_metadata_fn(job, adapter_path_obj)
    except Exception:
        log_internal_operation_failure_fn("Failed to save adapter metadata")


def cleanup_terminal_job_container(
    *,
    habitat: Any,
    job_id: str,
    job: Dict[str, Any],
    job_name: str,
    current_status: str,
    terminal_statuses: set[str],
    update_job_fn: Callable[[str, Dict[str, Any]], None],
    log_internal_operation_failure_fn: Callable[[str], None],
) -> None:
    """Cleanup runtime container for terminal jobs and mark as cleaned."""
    if current_status not in terminal_statuses or job.get("container_cleaned"):
        return
    try:
        habitat.cleanup_job(job_name)
        update_job_fn(job_id, {"container_cleaned": True})
        job["container_cleaned"] = True
    except Exception:
        log_internal_operation_failure_fn("Failed to cleanup container")


def sse_event(payload: Dict[str, Any]) -> str:
    """Serialize one SSE payload event."""
    return f"data: {json.dumps(payload)}\n\n"


def parse_stream_log_line(log_line: str) -> tuple[Optional[str], str]:
    """Split raw streamed log line into timestamp and message."""
    if " " not in log_line:
        return None, log_line
    timestamp, message = log_line.split(" ", 1)
    return timestamp, message


def extract_metrics_data(
    *,
    parser: Any,
    all_metrics: List[Any],
    message: str,
) -> Optional[Dict[str, Any]]:
    """Extract line metrics payload for SSE stream."""
    metrics = parser.parse_line(message)
    if not metrics:
        return None
    all_metrics.append(metrics)
    return {
        "epoch": metrics.epoch,
        "total_epochs": metrics.total_epochs,
        "loss": metrics.loss,
        "progress_percent": metrics.progress_percent,
    }


def build_log_event(
    *,
    line_no: int,
    message: str,
    timestamp: Optional[str],
    metrics_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build SSE payload for one streamed log entry."""
    payload: Dict[str, Any] = {
        "type": "log",
        "line": line_no,
        "message": message,
        "timestamp": timestamp,
    }
    if metrics_data:
        payload["metrics"] = metrics_data
    return payload


def periodic_stream_events(
    *,
    line_no: int,
    habitat: Any,
    job_name: str,
    parser: Any,
    all_metrics: List[Any],
    normalize_status_fn: Callable[[Optional[str]], str],
    terminal_statuses: set[str],
) -> tuple[List[Dict[str, Any]], bool]:
    """Emit periodic metrics/status SSE events and stop flag."""
    if line_no % 10 != 0:
        return [], False
    events: List[Dict[str, Any]] = []
    status_info = habitat.get_training_status(job_name)
    current_status = normalize_status_fn(status_info.get("status"))
    if all_metrics:
        events.append(
            {"type": "metrics", "data": parser.aggregate_metrics(all_metrics)}
        )
    should_stop = False
    if current_status in terminal_statuses:
        events.append({"type": "status", "status": current_status})
        should_stop = True
    return events, should_stop


async def stream_training_logs_events(
    *,
    job_id: str,
    job_name: str,
    habitat: Any,
    parser_factory: Callable[[], Any],
    normalize_status_fn: Callable[[Optional[str]], str],
    terminal_statuses: set[str],
    logger: Any,
):
    """Async generator for training-log SSE stream."""
    try:
        parser = parser_factory()
        all_metrics: List[Any] = []
        yield sse_event({"type": "connected", "job_id": job_id})
        if not habitat or job_name not in habitat.training_containers:
            yield sse_event(
                {"type": "error", "message": "Training container not found"}
            )
            return
        last_line_sent = 0
        for log_line in habitat.stream_job_logs(job_name):
            timestamp, message = parse_stream_log_line(log_line)
            metrics_data = extract_metrics_data(
                parser=parser,
                all_metrics=all_metrics,
                message=message,
            )
            yield sse_event(
                build_log_event(
                    line_no=last_line_sent,
                    message=message,
                    timestamp=timestamp,
                    metrics_data=metrics_data,
                )
            )
            last_line_sent += 1
            events, should_stop = periodic_stream_events(
                line_no=last_line_sent,
                habitat=habitat,
                job_name=job_name,
                parser=parser,
                all_metrics=all_metrics,
                normalize_status_fn=normalize_status_fn,
                terminal_statuses=terminal_statuses,
            )
            for event in events:
                yield sse_event(event)
            if should_stop:
                break
            await asyncio.sleep(0.1)
    except KeyError:
        yield sse_event(
            {"type": "error", "message": "Job not found in container registry"}
        )
    except Exception as exc:
        logger.error(f"Error streaming logs: {exc}", exc_info=True)
        yield sse_event({"type": "error", "message": str(exc)})


def list_jobs_response(
    *,
    jobs: List[Dict[str, Any]],
    to_job_summary_fn: Callable[[Dict[str, Any]], AcademyJobSummary],
    limit: int,
    status: Optional[str] = None,
) -> List[AcademyJobSummary]:
    """Build sorted/filtered job summary list."""
    summaries = [to_job_summary_fn(job) for job in jobs]
    if status:
        summaries = [item for item in summaries if item.status == status]
    return sorted(summaries, key=lambda j: j.started_at or "", reverse=True)[:limit]


def cancel_training_job(
    *,
    job_id: str,
    habitat: Any,
    jobs: List[Dict[str, Any]],
    update_job_fn: Callable[[str, Dict[str, Any]], None],
    logger: Any,
) -> Dict[str, Any]:
    """Cancel job, cleanup container and persist cancelled status."""
    job = next((j for j in jobs if j.get("job_id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    job_name = job.get("job_name", job_id)
    if habitat:
        try:
            habitat.cleanup_job(job_name)
            logger.info(f"Container cleaned up for job: {job_name}")
        except Exception as exc:
            logger.warning(f"Failed to cleanup container: {exc}")
    update_job_fn(
        job_id,
        {
            "status": "cancelled",
            "finished_at": datetime.now().isoformat(),
        },
    )
    return {
        "success": True,
        "message": f"Training job {job_id} cancelled",
        "job_id": job_id,
    }
