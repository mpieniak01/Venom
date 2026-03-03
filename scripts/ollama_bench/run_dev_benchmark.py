#!/usr/bin/env python3
# ruff: noqa: E402
"""Orkiestrator benchmarku dev: proste + złożone + feedback loop dla modeli Ollama."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import subprocess

from scripts.ollama_bench.common import (
    DEFAULT_OLLAMA_ENDPOINT,
    discover_models,
    utc_now_iso,
)


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run full dev benchmark for local Ollama models"
    )
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT)
    parser.add_argument(
        "--models", default="", help="Comma-separated allowlist of models"
    )
    parser.add_argument("--max-models", type=int, default=0, help="0 means no limit")
    parser.add_argument(
        "--profile",
        choices=("full", "complex"),
        default="full",
        help="full = simple+complex+loop, complex = complex+loop",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--options", default='{"temperature": 0.1, "top_p": 0.9}')
    parser.add_argument("--out", default="data/benchmarks/ollama_dev_coding")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    models = discover_models(endpoint=args.endpoint)
    if args.models.strip():
        allow = {name.strip() for name in args.models.split(",") if name.strip()}
        models = [name for name in models if name in allow]
    if args.max_models > 0:
        models = models[: args.max_models]

    if not models:
        raise RuntimeError("No models selected for benchmark")

    summary = {
        "started_at": utc_now_iso(),
        "endpoint": args.endpoint,
        "models": models,
        "runs": [],
    }

    for model in models:
        task_sequence = (
            ("python_simple", "python_complex")
            if args.profile == "full"
            else ("python_complex",)
        )
        for task in task_sequence:
            cmd = [
                "python",
                "scripts/ollama_bench/run_python_task.py",
                "--model",
                model,
                "--task",
                task,
                "--endpoint",
                args.endpoint,
                "--timeout",
                str(args.timeout),
                "--options",
                args.options,
                "--out",
                args.out,
            ]
            rc, output = _run(cmd)
            summary["runs"].append(
                {
                    "model": model,
                    "task": task,
                    "tool": "run_python_task",
                    "rc": rc,
                    "output": output,
                }
            )

        loop_cmd = [
            "python",
            "scripts/ollama_bench/run_feedback_loop.py",
            "--model",
            model,
            "--task",
            "python_complex_bugfix",
            "--endpoint",
            args.endpoint,
            "--timeout",
            str(args.timeout),
            "--max-rounds",
            str(args.max_rounds),
            "--options",
            args.options,
            "--out",
            args.out,
        ]
        rc, output = _run(loop_cmd)
        summary["runs"].append(
            {
                "model": model,
                "task": "python_complex_bugfix",
                "tool": "run_feedback_loop",
                "rc": rc,
                "output": output,
            }
        )

    score_cmd = [
        "python",
        "scripts/ollama_bench/scoreboard.py",
        "--input",
        args.out,
        "--csv",
        str(out_dir / "scoreboard.csv"),
        "--md",
        str(out_dir / "scoreboard.md"),
    ]
    score_rc, score_out = _run(score_cmd)
    summary["scoreboard"] = {"rc": score_rc, "output": score_out}
    summary["finished_at"] = utc_now_iso()

    summary_path = out_dir / "run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        json.dumps(
            {"summary": str(summary_path), "models": len(models)}, ensure_ascii=False
        )
    )

    all_rc = [entry["rc"] for entry in summary["runs"]] + [score_rc]
    return 0 if all(rc == 0 for rc in all_rc) else 2


if __name__ == "__main__":
    raise SystemExit(main())
