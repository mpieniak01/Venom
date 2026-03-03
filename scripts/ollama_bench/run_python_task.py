#!/usr/bin/env python3
# ruff: noqa: E402
"""Uruchamia pojedyncze zadanie codingowe Python dla wskazanego modelu Ollama."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import subprocess
from typing import Any

from scripts.ollama_bench.common import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaError,
    build_workspace,
    ollama_generate_with_timing,
    parse_model_files_response,
    run_checks,
    safe_snippet,
    utc_now_iso,
)
from scripts.ollama_bench.tasks import build_prompt, get_task, list_tasks


def _parse_options(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--options must be JSON object")
    return data


def _safe_model_name(model: str) -> str:
    return model.replace(":", "_").replace("/", "_")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Python coding task against Ollama model"
    )
    parser.add_argument("--model", required=True, help="Model name from ollama list")
    parser.add_argument(
        "--task",
        default="python_complex",
        choices=list_tasks(),
        help="Task ID",
    )
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--options", default='{"temperature": 0.1, "top_p": 0.9}')
    parser.add_argument(
        "--out",
        default="data/benchmarks/ollama_dev_coding",
        help="Output directory for json artifacts",
    )
    args = parser.parse_args()

    options = _parse_options(args.options)
    task = get_task(args.task)
    prompt = build_prompt(task)

    artifact = {
        "run_type": "single_task",
        "created_at": utc_now_iso(),
        "model": args.model,
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "passed": False,
    }

    try:
        raw, timing = ollama_generate_with_timing(
            model=args.model,
            prompt=prompt,
            endpoint=args.endpoint,
            timeout=args.timeout,
            options=options,
        )
        model_files = parse_model_files_response(raw, task.required_files)

        workspace = build_workspace(model_files, task.tests)
        checks = run_checks(workspace)
        artifact.update(
            {
                "passed": checks.passed,
                "workspace": str(workspace),
                "checks": checks.to_dict(),
                "raw_response_preview": safe_snippet(raw, 1200),
                "files": model_files,
                "timing": timing,
            }
        )
    except (
        OllamaError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        artifact["error"] = str(exc)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"single_{_safe_model_name(args.model)}_{task.task_id}.json"
    out_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        json.dumps(
            {"artifact": str(out_path), "passed": artifact["passed"]},
            ensure_ascii=False,
        )
    )
    return 0 if artifact["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
