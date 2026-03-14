#!/usr/bin/env python3
"""202C.4 automation workload tuning matrix for ONNX vs Ollama."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import dump_json, dump_text


def _parse_int_list(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        values.append(int(item))
    return values


def _parse_float_list(raw: str) -> list[float]:
    values: list[float] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        values.append(float(item))
    return values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C.4 automation perf tuning matrix")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--prompts", default="tests/data/202c/gemma3_eval_prompts.jsonl"
    )
    parser.add_argument("--category", default="automation")
    parser.add_argument("--repetitions", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--max-tokens-list", default="48,64,80,96")
    parser.add_argument("--temperature-list", default="0.0,0.1")
    parser.add_argument(
        "--json-output",
        default="test-results/202c4/automation_perf_matrix.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c4/automation_perf_matrix.md",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 202C.4 Automation Perf Matrix")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Category: {report.get('category', '')}")
    lines.append("")
    lines.append("## Best Profile")
    lines.append("")
    best = report.get("best_profile") or {}
    if best:
        lines.append(f"- max_tokens: {best.get('max_tokens')}")
        lines.append(f"- temperature: {best.get('temperature')}")
        lines.append(f"- p95_ratio: {best.get('p95_ratio')}")
        lines.append(f"- candidate_p95_ms: {best.get('candidate_p95_ms')}")
        lines.append(f"- baseline_p95_ms: {best.get('baseline_p95_ms')}")
    else:
        lines.append("- no successful profiles")
    lines.append("")
    lines.append("## Matrix")
    lines.append("")
    lines.append(
        "| max_tokens | temperature | ratio | baseline_p95_ms | candidate_p95_ms | errors |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for row in report.get("profiles", []):
        lines.append(
            f"| {row.get('max_tokens')} | {row.get('temperature')} | {row.get('p95_ratio')} | {row.get('baseline_p95_ms')} | {row.get('candidate_p95_ms')} | {len(row.get('errors', []))} |"
        )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    matrix_dir = (root / "test-results/202c4/matrix_runs").resolve()
    matrix_dir.mkdir(parents=True, exist_ok=True)

    max_tokens_values = _parse_int_list(args.max_tokens_list)
    temperatures = _parse_float_list(args.temperature_list)
    profiles: list[dict[str, Any]] = []
    benchmark_script = (root / "scripts/dev/202c_latency_memory_benchmark.py").resolve()

    for max_tokens in max_tokens_values:
        for temperature in temperatures:
            slug = f"automation_mt{max_tokens}_temp{str(temperature).replace('.', '_')}"
            json_output = matrix_dir / f"{slug}.json"
            md_output = matrix_dir / f"{slug}.md"
            cmd = [
                sys.executable,
                str(benchmark_script),
                "--env-file",
                args.env_file,
                "--prompts",
                args.prompts,
                "--categories",
                args.category,
                "--repetitions",
                str(args.repetitions),
                "--warmup",
                str(args.warmup),
                "--max-tokens",
                str(max_tokens),
                "--temperature",
                str(temperature),
                "--json-output",
                str(json_output.relative_to(root)),
                "--md-output",
                str(md_output.relative_to(root)),
            ]
            if args.base_url.strip():
                cmd.extend(["--base-url", args.base_url.strip()])
            completed = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            payload: dict[str, Any] = {}
            errors: list[str] = []
            if json_output.exists():
                try:
                    payload = _load_json(json_output)
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"json_load_failed:{exc}")
            else:
                errors.append(f"benchmark_exit:{completed.returncode}")
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                if stderr:
                    errors.append(stderr[:300])

            baseline_p95 = float(
                payload.get("baseline", {}).get("summary", {}).get("p95_ms", 0.0) or 0.0
            )
            candidate_p95 = float(
                payload.get("candidate", {}).get("summary", {}).get("p95_ms", 0.0)
                or 0.0
            )
            ratio = float(
                payload.get("derived", {}).get("p95_ratio_candidate_vs_baseline", 0.0)
                or 0.0
            )

            profiles.append(
                {
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "baseline_p95_ms": round(baseline_p95, 2),
                    "candidate_p95_ms": round(candidate_p95, 2),
                    "p95_ratio": round(ratio, 4),
                    "candidate_error_count": payload.get("candidate", {})
                    .get("summary", {})
                    .get("error_count", 0),
                    "baseline_error_count": payload.get("baseline", {})
                    .get("summary", {})
                    .get("error_count", 0),
                    "json_output": str(json_output.relative_to(root)),
                    "md_output": str(md_output.relative_to(root)),
                    "errors": errors,
                }
            )

    successful = [
        item
        for item in profiles
        if not item.get("errors") and item.get("p95_ratio", 0.0) > 0.0
    ]
    successful.sort(
        key=lambda item: (
            float(item.get("p95_ratio", 999.0)),
            float(item.get("candidate_error_count", 999.0)),
            float(item.get("candidate_p95_ms", 999999.0)),
        )
    )
    best_profile = successful[0] if successful else None

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "category": args.category,
        "repetitions": args.repetitions,
        "warmup": args.warmup,
        "max_tokens_list": max_tokens_values,
        "temperature_list": temperatures,
        "profiles": profiles,
        "best_profile": best_profile,
        "kpi": {
            "best_ratio_within_1_35": bool(
                best_profile and float(best_profile.get("p95_ratio", 99.0)) <= 1.35
            ),
            "best_ratio_within_1_50": bool(
                best_profile and float(best_profile.get("p95_ratio", 99.0)) <= 1.50
            ),
        },
    }

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
