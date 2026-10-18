#!/usr/bin/env python3
"""202C latency/memory benchmark for Gemma-3 (ONNX vs Ollama).

TTFT is the receiver's first nonempty text event, not latency/event count.
Token throughput/TPOT use only native reported usage when present. Missing usage
stays unavailable, not estimated. Memory uses boundary snapshots, not sampled inference peaks. This benchmark alone does
not satisfy the full lifecycle/resource qualification required by task 266.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    activate_runtime,
    dump_json,
    dump_text,
    gpu_memory_used_mb,
    http_json,
    load_prompts_jsonl,
    pick_gemma3_model_with_reason,
    resolve_base_url,
    stream_simple_chat,
    summarize_latency,
    system_memory_used_mb,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C latency and memory benchmark")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--baseline-runtime", default="ollama")
    parser.add_argument("--candidate-runtime", default="onnx")
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--prompts",
        default="tests/data/202c/gemma3_eval_prompts.jsonl",
    )
    parser.add_argument(
        "--categories",
        default="",
        help="Optional comma-separated prompt categories (e.g. chat,automation,coding)",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/202c/perf_onnx_vs_ollama.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c/perf_onnx_vs_ollama.md",
    )
    return parser.parse_args()


def _run_benchmark_for_runtime(
    *,
    base_url: str,
    runtime_id: str,
    model_name: str,
    prompts: list[dict[str, Any]],
    repetitions: int,
    warmup: int,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    activation_ok, activation_message, activation_payload = activate_runtime(
        base_url, runtime_id, model_name
    )
    if not activation_ok:
        return {
            "runtime_id": runtime_id,
            "selected_model": model_name,
            "activation_ok": False,
            "activation_message": activation_message,
            "activation_payload": activation_payload,
            "errors": [activation_message],
            "samples": [],
            "summary": {},
        }

    samples: list[dict[str, Any]] = []
    warmup_samples: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    first_token_latencies_ms: list[float] = []
    throughput_tps: list[float] = []
    tpot_values_ms: list[float] = []
    host_mem_peaks: list[float] = []
    gpu_mem_peaks: list[float] = []

    # First request after activation approximates cold-start impact.
    cold_start_result = stream_simple_chat(
        base_url,
        prompt=prompts[0]["prompt"],
        model=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    cold_start_latency_ms = cold_start_result.latency_ms

    for idx in range(max(0, warmup)):
        prompt = prompts[idx % len(prompts)]
        result = stream_simple_chat(
            base_url,
            prompt=prompt["prompt"],
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        warmup_samples.append(
            {
                "iteration": idx + 1,
                "prompt_id": prompt["id"],
                "ok": result.ok,
                "latency_ms": round(result.latency_ms, 2),
                "error": result.error,
            }
        )

    for idx in range(repetitions):
        prompt = prompts[idx % len(prompts)]
        host_before = system_memory_used_mb()
        gpu_before = gpu_memory_used_mb()
        result = stream_simple_chat(
            base_url,
            prompt=prompt["prompt"],
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        host_after = system_memory_used_mb()
        gpu_after = gpu_memory_used_mb()

        host_peak = max(host_before, host_after)
        gpu_peak = max(gpu_before, gpu_after)

        host_mem_peaks.append(host_peak)
        gpu_mem_peaks.append(gpu_peak)
        if result.ok:
            latencies_ms.append(result.latency_ms)
            if result.first_token_latency_ms is not None:
                first_token_latencies_ms.append(result.first_token_latency_ms)
            if result.tokens_per_second is not None:
                throughput_tps.append(result.tokens_per_second)
            if result.time_per_output_token_ms is not None:
                tpot_values_ms.append(result.time_per_output_token_ms)

        samples.append(
            {
                "iteration": idx + 1,
                "prompt_id": prompt["id"],
                "ok": result.ok,
                "latency_ms": round(result.latency_ms, 2),
                "first_token_latency_ms": result.first_token_latency_ms,
                "output_tokens": result.output_tokens,
                "prompt_tokens": result.prompt_tokens,
                "usage_source": result.usage_source,
                "tokens_per_second": result.tokens_per_second,
                "time_per_output_token_ms": result.time_per_output_token_ms,
                "host_mem_used_mb_peak": round(host_peak, 2),
                "gpu_mem_used_mb_peak": round(gpu_peak, 2),
                "error": result.error,
            }
        )

    summary: dict[str, Any] = dict(summarize_latency(latencies_ms))
    warm_summary = summarize_latency(
        [float(sample["latency_ms"]) for sample in warmup_samples if sample.get("ok")]
    )
    first_token_summary = summarize_latency(first_token_latencies_ms)
    throughput_summary = summarize_latency(throughput_tps)
    tpot_summary = summarize_latency(tpot_values_ms)
    successes = sum(1 for sample in samples if sample["ok"])
    summary.update(
        {
            "success_count": sum(1 for sample in samples if sample["ok"]),
            "error_count": sum(1 for sample in samples if not sample["ok"]),
            "cold_start_latency_ms": round(cold_start_latency_ms, 2),
            "warmup_count": len(warmup_samples),
            "host_mem_used_mb_peak": round(
                max(host_mem_peaks) if host_mem_peaks else 0.0, 2
            ),
            "gpu_mem_used_mb_peak": round(
                max(gpu_mem_peaks) if gpu_mem_peaks else 0.0, 2
            ),
            "first_token_latency_ms": {
                "p50_ms": round(first_token_summary["p50_ms"], 2)
                if first_token_latencies_ms
                else None,
                "p95_ms": round(first_token_summary["p95_ms"], 2)
                if first_token_latencies_ms
                else None,
                "sample_count": len(first_token_latencies_ms),
            },
            "tokens_per_sec": {
                "p50": throughput_summary["p50_ms"] if throughput_tps else None,
                "p95": throughput_summary["p95_ms"] if throughput_tps else None,
                "mean": throughput_summary["mean_ms"] if throughput_tps else None,
                "sample_count": len(throughput_tps),
                "missing_count": successes - len(throughput_tps),
                "status": (
                    "AVAILABLE"
                    if throughput_tps and len(throughput_tps) == successes
                    else "PARTIAL"
                    if throughput_tps
                    else "UNAVAILABLE"
                ),
                "source": "Upstream output-token count / receiver end-to-end seconds; never words/chunks.",
            },
            "time_per_output_token_ms": {
                "p50_ms": tpot_summary["p50_ms"] if tpot_values_ms else None,
                "p95_ms": tpot_summary["p95_ms"] if tpot_values_ms else None,
                "sample_count": len(tpot_values_ms),
                "definition": "(receiver E2E - first text latency)/(native output tokens - 1); needs >1 output token and >1 nonempty text event. Includes transport/aggregation effects, not pure inference time.",
            },
            "warmup_summary": warm_summary,
            "memory_note": "Host/GPU memory uses boundary node-level snapshots, not sampled inference peaks.",
        }
    )

    return {
        "runtime_id": runtime_id,
        "selected_model": model_name,
        "activation_ok": True,
        "activation_message": "ok",
        "activation_payload": activation_payload,
        "warmup_samples": warmup_samples,
        "samples": samples,
        "summary": summary,
        "errors": [],
    }


def _build_markdown(report: dict[str, Any]) -> str:
    baseline = report.get("baseline", {})
    candidate = report.get("candidate", {})
    metrics = report.get("kpi", {})

    lines: list[str] = []
    lines.append("# 202C Perf ONNX vs Ollama")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Base URL: {report.get('base_url', '')}")
    lines.append("")
    lines.append("## Runtime Summary")
    lines.append("")
    lines.append("| Metric | Baseline | Candidate |")
    lines.append("|---|---:|---:|")
    for key in (
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "mean_ms",
        "cold_start_latency_ms",
        "host_mem_used_mb_peak",
        "gpu_mem_used_mb_peak",
    ):
        lines.append(
            f"| {key} | {baseline.get('summary', {}).get(key, 0)} | {candidate.get('summary', {}).get(key, 0)} |"
        )
    lines.append("")
    lines.append(
        "TTFT: arrival of the first nonempty text event. Token rates use native output counts only; unavailable counts stay null. Receiver TPOT needs multiple text events and includes transport/aggregation effects."
    )
    lines.append("")
    lines.append("## KPI Verdict")
    lines.append("")
    for key, value in metrics.items():
        lines.append(f"- {key}: {'pass' if value else 'fail'}")
    lines.append("")
    lines.append("## Warmup")
    lines.append("")
    lines.append(
        f"- baseline_warmup_count: {baseline.get('summary', {}).get('warmup_count', 0)}"
    )
    lines.append(
        f"- candidate_warmup_count: {candidate.get('summary', {}).get('warmup_count', 0)}"
    )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    base_url = resolve_base_url(env_file=env_file, explicit=args.base_url)
    prompts_path = (root / args.prompts).resolve()
    prompts = load_prompts_jsonl(prompts_path)

    categories = [
        part.strip().lower()
        for part in str(args.categories or "").split(",")
        if part.strip()
    ]
    if categories:
        selected = set(categories)
        prompts = [
            item
            for item in prompts
            if str(item.get("category") or "").strip().lower() in selected
        ]

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "prompts_path": str(prompts_path),
        "categories_filter": categories,
        "prompt_count": len(prompts),
        "repetitions": args.repetitions,
        "errors": [],
    }

    if not prompts:
        report["errors"].append("prompts_empty_after_filter")
        dump_json((root / args.json_output).resolve(), report)
        dump_text(
            (root / args.md_output).resolve(),
            "# 202C Perf\n\nNo prompts available after category filtering.",
        )
        return 1

    if not wait_backend_ready(base_url, timeout_sec=30):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        dump_text(
            (root / args.md_output).resolve(), "# 202C Perf\n\nBackend not ready."
        )
        return 1

    code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
    )
    if code != 200 or not isinstance(options_payload, dict):
        report["errors"].append("runtime_options_unavailable")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    baseline_model, baseline_model_selection = pick_gemma3_model_with_reason(
        options_payload, args.baseline_runtime
    )
    candidate_model, candidate_model_selection = pick_gemma3_model_with_reason(
        options_payload, args.candidate_runtime
    )
    if not baseline_model:
        report["errors"].append("baseline_model_missing")
    if not candidate_model:
        report["errors"].append("candidate_model_missing")
    if report["errors"]:
        dump_json((root / args.json_output).resolve(), report)
        return 1

    baseline = _run_benchmark_for_runtime(
        base_url=base_url,
        runtime_id=args.baseline_runtime,
        model_name=str(baseline_model),
        prompts=prompts,
        repetitions=args.repetitions,
        warmup=args.warmup,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    candidate = _run_benchmark_for_runtime(
        base_url=base_url,
        runtime_id=args.candidate_runtime,
        model_name=str(candidate_model),
        prompts=prompts,
        repetitions=args.repetitions,
        warmup=args.warmup,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    baseline_p95 = float(baseline.get("summary", {}).get("p95_ms", 0.0) or 0.0)
    candidate_p95 = float(candidate.get("summary", {}).get("p95_ms", 0.0) or 0.0)
    p95_ratio = (candidate_p95 / baseline_p95) if baseline_p95 > 0 else 0.0

    report["baseline"] = baseline
    report["candidate"] = candidate
    report["model_selection"] = {
        "baseline": baseline_model_selection,
        "candidate": candidate_model_selection,
    }
    report["benchmark_mode"] = {
        "cold_start_included": True,
        "warmup_excluded_from_primary_percentiles": True,
    }
    report["kpi"] = {
        "p95_latency_within_25pct": p95_ratio <= 1.25 if baseline_p95 > 0 else False,
        "p95_latency_within_35pct": p95_ratio <= 1.35 if baseline_p95 > 0 else False,
        "candidate_error_rate_not_worse_than_2pp": (
            (
                candidate.get("summary", {}).get("error_count", 0)
                / max(1, args.repetitions)
            )
            - (
                baseline.get("summary", {}).get("error_count", 0)
                / max(1, args.repetitions)
            )
        )
        <= 0.02,
    }
    report["derived"] = {
        "p95_ratio_candidate_vs_baseline": round(p95_ratio, 4),
    }

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
