#!/usr/bin/env python3
# ruff: noqa: E402
"""Scheduler długich benchmarków Ollama (kolejka modeli/zadań + raporty + podsumowanie)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ollama_bench.common import (
    DEFAULT_OLLAMA_ENDPOINT,
    discover_models,
    utc_now_iso,
)

ARTIFACT_RE = re.compile(r'"artifact"\s*:\s*"([^"]+)"')
DEFAULT_TIMEOUT_OVERRIDES = {
    "codestral:latest": 420,
    "deepcoder:latest": 420,
}


@dataclass
class Job:
    """Pojedynczy krok scheduler-a."""

    id: str
    model: str
    mode: str  # single | loop
    task: str
    role: str = "main"  # main | sieve
    status: str = "pending"  # pending | running | completed | failed | skipped
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    rc: int | None = None
    artifact: str | None = None
    output: str | None = None


def _sanitize(text: str) -> str:
    out = text.replace(":", "_").replace("/", "_").replace(" ", "_")
    return "".join(ch for ch in out if ch.isalnum() or ch in {"_", "-", "."})


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_artifact_from_output(output: str) -> str | None:
    match = ARTIFACT_RE.search(output)
    return match.group(1) if match else None


def _build_jobs(
    models: list[str],
    tasks: list[str],
    loop_task: str | None,
    first_sieve_task: str | None = None,
) -> list[Job]:
    now = utc_now_iso()
    jobs: list[Job] = []
    counter = 1
    for model in models:
        if first_sieve_task:
            jobs.append(
                Job(
                    id=f"job-{counter:04d}",
                    model=model,
                    mode="single",
                    task=first_sieve_task,
                    role="sieve",
                    created_at=now,
                )
            )
            counter += 1
        for task in tasks:
            jobs.append(
                Job(
                    id=f"job-{counter:04d}",
                    model=model,
                    mode="single",
                    task=task,
                    created_at=now,
                )
            )
            counter += 1
        if loop_task:
            jobs.append(
                Job(
                    id=f"job-{counter:04d}",
                    model=model,
                    mode="loop",
                    task=loop_task,
                    created_at=now,
                )
            )
            counter += 1
    return jobs


def _parse_timeout_overrides(raw: str) -> dict[str, int]:
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--model-timeout-overrides must be JSON object")
    overrides: dict[str, int] = {}
    for model, value in data.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Model key in timeout overrides must be non-empty string")
        if not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"Timeout override for model '{model}' must be positive int"
            )
        overrides[model] = value
    return overrides


def _job_timeout_seconds(
    job: Job, args: argparse.Namespace, timeout_overrides: dict[str, int]
) -> int:
    return timeout_overrides.get(job.model, args.timeout)


def _job_command(
    job: Job, args: argparse.Namespace, timeout_overrides: dict[str, int]
) -> list[str]:
    python_bin = sys.executable or "python3"
    timeout_seconds = _job_timeout_seconds(job, args, timeout_overrides)
    if job.mode == "single":
        return [
            python_bin,
            "scripts/ollama_bench/run_python_task.py",
            "--model",
            job.model,
            "--task",
            job.task,
            "--endpoint",
            args.endpoint,
            "--timeout",
            str(timeout_seconds),
            "--options",
            args.options,
            "--out",
            args.out,
        ]
    return [
        python_bin,
        "scripts/ollama_bench/run_feedback_loop.py",
        "--model",
        job.model,
        "--task",
        job.task,
        "--endpoint",
        args.endpoint,
        "--timeout",
        str(timeout_seconds),
        "--max-rounds",
        str(args.max_rounds),
        "--options",
        args.options,
        "--out",
        args.out,
    ]


def _state_payload(meta: dict[str, Any], jobs: list[Job]) -> dict[str, Any]:
    return {
        "meta": meta,
        "jobs": [asdict(job) for job in jobs],
    }


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_jobs(path: Path) -> tuple[dict[str, Any], list[Job]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    jobs = [Job(**item) for item in data.get("jobs", [])]
    return meta, jobs


def _write_job_report(report_dir: Path, job: Job) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    name = f"{job.id}_{_sanitize(job.model)}_{job.mode}_{_sanitize(job.task)}.json"
    path = report_dir / name
    path.write_text(
        json.dumps(asdict(job), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def _make_summary(meta: dict[str, Any], jobs: list[Job]) -> dict[str, Any]:
    total = len(jobs)
    completed = sum(1 for job in jobs if job.status == "completed")
    failed = sum(1 for job in jobs if job.status == "failed")
    pending = sum(1 for job in jobs if job.status == "pending")
    skipped = sum(1 for job in jobs if job.status == "skipped")
    return {
        "meta": meta,
        "finished_at": utc_now_iso(),
        "total_jobs": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "skipped": skipped,
        "success_rate": round((completed / total) * 100.0, 2) if total else 0.0,
        "failed_jobs": [
            {
                "id": job.id,
                "model": job.model,
                "mode": job.mode,
                "task": job.task,
                "role": job.role,
                "rc": job.rc,
                "artifact": job.artifact,
            }
            for job in jobs
            if job.status == "failed"
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Long-running scheduler for Ollama coding benchmarks"
    )
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    parser.add_argument(
        "--models", default="", help="CSV allowlist; empty => auto discover"
    )
    parser.add_argument(
        "--tasks",
        default="python_complex",
        help="CSV tasks for single run (e.g. python_simple,python_complex)",
    )
    parser.add_argument(
        "--loop-task",
        default="python_complex_bugfix",
        help="Loop task id. Use empty string to disable loop runs.",
    )
    parser.add_argument(
        "--first-sieve-task",
        default="",
        help="Optional task id run first for each model; failing model is skipped for remaining jobs.",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--model-timeout-overrides",
        default=json.dumps(DEFAULT_TIMEOUT_OVERRIDES, ensure_ascii=False),
        help="JSON map model->timeout seconds (overrides global --timeout for selected models).",
    )
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--sleep-between-jobs", type=float, default=0.0)
    parser.add_argument("--options", default='{"temperature": 0.1, "top_p": 0.9}')
    parser.add_argument("--out", default="data/benchmarks/ollama_dev_coding_scheduler")
    parser.add_argument(
        "--state-file",
        default="",
        help="Optional explicit path to scheduler state file (default: <out>/scheduler_state.json)",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from existing state file"
    )
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timeout_overrides = _parse_timeout_overrides(args.model_timeout_overrides)
    out_dir = Path(args.out)
    report_dir = out_dir / "reports"
    state_file = (
        Path(args.state_file) if args.state_file else out_dir / "scheduler_state.json"
    )

    if args.resume:
        if not state_file.exists():
            raise FileNotFoundError(f"State file not found for --resume: {state_file}")
        meta, jobs = _load_jobs(state_file)
    else:
        models = (
            _parse_csv(args.models)
            if args.models.strip()
            else discover_models(endpoint=args.endpoint)
        )
        tasks = _parse_csv(args.tasks)
        if not tasks:
            raise ValueError("No tasks selected")
        loop_task = args.loop_task.strip() or None
        first_sieve_task = args.first_sieve_task.strip() or None
        jobs = _build_jobs(
            models=models,
            tasks=tasks,
            loop_task=loop_task,
            first_sieve_task=first_sieve_task,
        )
        meta = {
            "created_at": utc_now_iso(),
            "endpoint": args.endpoint,
            "models": models,
            "tasks": tasks,
            "loop_task": loop_task,
            "first_sieve_task": first_sieve_task,
            "out_dir": str(out_dir),
        }
        _save_json(state_file, _state_payload(meta, jobs))

    blocked_models: set[str] = set()
    for job in jobs:
        if job.role == "sieve" and job.status == "failed":
            blocked_models.add(job.model)

    for job in jobs:
        if job.status in {"completed", "failed", "skipped"}:
            continue
        if job.role != "sieve" and job.model in blocked_models:
            job.status = "skipped"
            job.started_at = utc_now_iso()
            job.finished_at = job.started_at
            job.output = "Skipped due to failed first-sieve-task."
            _write_job_report(report_dir, job)
            _save_json(state_file, _state_payload(meta, jobs))
            continue

        job.status = "running"
        job.started_at = utc_now_iso()
        _save_json(state_file, _state_payload(meta, jobs))

        cmd = _job_command(job, args, timeout_overrides)
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        artifact = _parse_artifact_from_output(output)

        job.rc = proc.returncode
        job.output = output
        job.artifact = artifact
        job.finished_at = utc_now_iso()
        job.status = "completed" if proc.returncode == 0 else "failed"
        if job.role == "sieve" and job.status == "failed":
            blocked_models.add(job.model)

        _write_job_report(report_dir, job)
        _save_json(state_file, _state_payload(meta, jobs))

        if proc.returncode != 0 and args.stop_on_failure:
            break
        if args.sleep_between_jobs > 0:
            time.sleep(args.sleep_between_jobs)

    python_bin = sys.executable or "python3"
    scoreboard_cmd = [
        python_bin,
        "scripts/ollama_bench/scoreboard.py",
        "--input",
        str(out_dir),
        "--csv",
        str(out_dir / "scoreboard.csv"),
        "--md",
        str(out_dir / "scoreboard.md"),
    ]
    scoreboard_proc = subprocess.run(
        scoreboard_cmd, text=True, capture_output=True, check=False
    )

    summary = _make_summary(meta, jobs)
    summary["scoreboard"] = {
        "rc": scoreboard_proc.returncode,
        "output": (scoreboard_proc.stdout + "\n" + scoreboard_proc.stderr).strip(),
    }
    summary_path = out_dir / "scheduler_summary.json"
    _save_json(summary_path, summary)

    print(
        json.dumps(
            {
                "state": str(state_file),
                "summary": str(summary_path),
                "jobs": len(jobs),
                "failed": summary["failed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
