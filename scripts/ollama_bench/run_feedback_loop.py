#!/usr/bin/env python3
# ruff: noqa: E402
"""Uruchamia pętlę zwrotną naprawy błędów dla zadania Python."""

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
    ensure_files_map,
    extract_json_object,
    ollama_generate,
    run_checks,
    safe_snippet,
    utc_now_iso,
)
from scripts.ollama_bench.tasks import build_feedback_prompt, get_task, list_tasks


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
    parser = argparse.ArgumentParser(description="Run debug feedback loop for a model")
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--task",
        default="python_complex_bugfix",
        choices=list_tasks(),
        help="Task ID with starter files (recommended: python_complex_bugfix)",
    )
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--options", default='{"temperature": 0.1, "top_p": 0.9}')
    parser.add_argument("--out", default="data/benchmarks/ollama_dev_coding")
    args = parser.parse_args()

    options = _parse_options(args.options)
    task = get_task(args.task)
    current_files = dict(task.starter_files)
    if not current_files:
        raise ValueError(
            "Selected task has no starter files; feedback loop needs initial buggy files"
        )

    rounds: list[dict[str, Any]] = []
    solved = False

    run_error: str | None = None
    try:
        for idx in range(1, args.max_rounds + 1):
            workspace = build_workspace(current_files, task.tests)
            checks = run_checks(workspace)
            check_output = (
                f"pytest_rc={checks.pytest_rc}\n{safe_snippet(checks.pytest_output)}\n\n"
                f"ruff_rc={checks.ruff_rc}\n{safe_snippet(checks.ruff_output)}"
            )

            round_entry: dict[str, Any] = {
                "round": idx,
                "workspace": str(workspace),
                "checks": checks.to_dict(),
            }

            if checks.passed:
                solved = True
                round_entry["action"] = "already_passed"
                rounds.append(round_entry)
                break

            prompt = build_feedback_prompt(
                task, check_output=check_output, current_files=current_files
            )
            raw = ollama_generate(
                model=args.model,
                prompt=prompt,
                endpoint=args.endpoint,
                timeout=args.timeout,
                options=options,
            )
            payload = extract_json_object(raw)
            proposed_files = ensure_files_map(payload)

            missing = [
                path for path in task.required_files if path not in proposed_files
            ]
            if missing:
                round_entry["action"] = "invalid_payload"
                round_entry["error"] = f"missing required files: {missing}"
                round_entry["raw_response_preview"] = safe_snippet(raw, 1200)
                rounds.append(round_entry)
                continue

            current_files = {path: proposed_files[path] for path in task.required_files}
            round_entry["action"] = "patched"
            round_entry["raw_response_preview"] = safe_snippet(raw, 1200)
            round_entry["files"] = current_files
            rounds.append(round_entry)

        if not solved:
            final_workspace = build_workspace(current_files, task.tests)
            final_checks = run_checks(final_workspace)
            solved = final_checks.passed
            rounds.append(
                {
                    "round": "final_check",
                    "workspace": str(final_workspace),
                    "checks": final_checks.to_dict(),
                }
            )
    except (
        OllamaError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        run_error = str(exc)

    artifact = {
        "run_type": "feedback_loop",
        "created_at": utc_now_iso(),
        "model": args.model,
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "solved": solved,
        "max_rounds": args.max_rounds,
        "rounds": rounds,
        "final_files": current_files,
    }
    if run_error is not None:
        artifact["error"] = run_error

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"loop_{_safe_model_name(args.model)}_{task.task_id}.json"
    out_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps({"artifact": str(out_path), "solved": solved}, ensure_ascii=False))
    return 0 if solved else 2


if __name__ == "__main__":
    raise SystemExit(main())
