"""History and adapter metadata helpers for Academy routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


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


def save_adapter_metadata(job: dict[str, Any], adapter_path: Path) -> None:
    """Persist deterministic adapter metadata after successful training."""
    metadata_file = adapter_path.parent / "metadata.json"
    metadata = {
        "job_id": job.get("job_id"),
        "base_model": job.get("base_model"),
        "dataset_path": job.get("dataset_path"),
        "parameters": job.get("parameters", {}),
        "created_at": job.get("finished_at") or datetime.now().isoformat(),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "source": "academy",
    }
    with open(metadata_file, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
