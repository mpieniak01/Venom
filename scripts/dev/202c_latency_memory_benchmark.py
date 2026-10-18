#!/usr/bin/env python3
"""202C latency/memory benchmark for Gemma-3 (ONNX vs Ollama).

TTFT is the receiver's first nonempty text event, not latency/event count.
Token throughput/TPOT use only native reported usage when present. Missing usage
stays unavailable, not estimated. Resources are sampled over the measured-request
window for explicitly supplied process trees. Node/device memory includes ambient
usage; a sampled maximum can miss short spikes. This benchmark alone does not
satisfy the full lifecycle/resource qualification required by task 266.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    ProcessResourceSampler,
    activate_runtime,
    dump_json,
    dump_text,
    http_json,
    load_prompts_jsonl,
    pick_gemma3_model_with_reason,
    resolve_base_url,
    stream_simple_chat,
    summarize_latency,
    wait_backend_ready,
)


def _positive_pid(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("PID must be positive")
    return parsed


def _sample_interval(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.02 <= parsed <= 5.0:
        raise argparse.ArgumentTypeError("Sampling interval must be 0.02..5 seconds")
    return parsed


def _gpu_index(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("GPU index must be nonnegative")
    return parsed


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
    for role in ("baseline", "candidate"):
        parser.add_argument(
            f"--{role}-root-pid",
            type=_positive_pid,
            action="append",
            default=[],
            help="Repeat for known API/engine root PIDs. No automatic process discovery.",
        )
    parser.add_argument("--resource-interval-sec", type=_sample_interval, default=0.1)
    parser.add_argument("--gpu-index", type=_gpu_index, default=0)
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
    process_root_pids: list[int] | None = None,
    sample_interval_sec: float = 0.1,
    gpu_index: int = 0,
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

    # First post-activation request, not a proven unload/reboot cold cycle.
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

    sampler = ProcessResourceSampler(
        root_pids=process_root_pids,
        interval_sec=sample_interval_sec,
        gpu_index=gpu_index,
    ).start()
    try:
        for idx in range(repetitions):
            prompt = prompts[idx % len(prompts)]
            result = stream_simple_chat(
                base_url,
                prompt=prompt["prompt"],
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
            )
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
                    "error": result.error,
                }
            )
    finally:
        resources = sampler.finish()
    resources["benchmark_stage"] = "measured_repetitions_only"
    resources["excluded_stages"] = [
        "activation",
        "first_post_activation_request",
        "warmup",
    ]

    summary: dict[str, Any] = (
        dict(summarize_latency(latencies_ms))
        if latencies_ms
        else {
            "count": 0,
            **{key: None for key in ("p50_ms", "p95_ms", "p99_ms", "mean_ms")},
        }
    )
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
            "cold_start_latency_ms": round(cold_start_latency_ms, 2)
            if cold_start_result.ok
            else None,
            "warmup_count": len(warmup_samples),
            "resource_status": resources["status"],
            "cpu_mean_percent_one_core": resources["cpu_mean_percent_one_core"],
            "process_rss_mb_sampled_peak": resources["process_rss_mb_sampled_peak"],
            "node_ram_used_mb_sampled_peak": resources["node_ram_used_mb_sampled_peak"],
            "gpu_device_used_mb_sampled_peak": resources[
                "gpu_device_used_mb_sampled_peak"
            ],
            # Legacy summary keys are sampled node/device aliases, not process peaks.
            "host_mem_used_mb_peak": resources["node_ram_used_mb_sampled_peak"],
            "gpu_mem_used_mb_peak": resources["gpu_device_used_mb_sampled_peak"],
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
            "memory_note": "Sampled over measured repetitions only. CPU: 100%=one core; RSS sums process trees and can double-count shared pages. Host/GPU legacy keys alias sampled node RAM/device VRAM (ambient allocations included); short spikes can be missed. Null means unavailable, never zero.",
        }
    )

    return {
        "runtime_id": runtime_id,
        "selected_model": model_name,
        "activation_ok": True,
        "activation_message": "ok",
        "activation_payload": activation_payload,
        "cold_start": {
            "ok": cold_start_result.ok,
            "observed_latency_ms": cold_start_latency_ms,
            "error": cold_start_result.error,
        },
        "warmup_samples": warmup_samples,
        "samples": samples,
        "resources": resources,
        "summary": summary,
        "errors": [],
    }


def _comparison_metrics(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> tuple[dict[str, bool | None], dict[str, Any]]:
    summaries = [runtime.get("summary", {}) for runtime in (baseline, candidate)]
    p95s = [summary.get("p95_ms") for summary in summaries]
    valid_latency = all(
        runtime.get("activation_ok")
        and summary.get("success_count", 0) > 0
        and isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
        for runtime, summary, value in zip((baseline, candidate), summaries, p95s)
    )
    ratio = float(p95s[1]) / float(p95s[0]) if valid_latency else None
    samples = [runtime.get("samples", []) for runtime in (baseline, candidate)]
    rates = [
        sum(not sample["ok"] for sample in items) / len(items)
        if runtime.get("activation_ok") and items
        else None
        for runtime, items in zip((baseline, candidate), samples)
    ]
    baseline_rate, candidate_rate = rates
    error_delta = (
        candidate_rate - baseline_rate
        if baseline_rate is not None and candidate_rate is not None
        else None
    )
    return (
        {
            "p95_latency_within_25pct": ratio <= 1.25 if ratio is not None else None,
            "p95_latency_within_35pct": ratio <= 1.35 if ratio is not None else None,
            "candidate_error_rate_not_worse_than_2pp": error_delta <= 0.02
            if error_delta is not None
            else None,
        },
        {
            "p95_ratio_candidate_vs_baseline": round(ratio, 4)
            if ratio is not None
            else None
        },
    )


def _display_metric(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return str(round(value, 2)) if math.isfinite(value) else "unavailable"
    return str(value)


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
        "resource_status",
        "cpu_mean_percent_one_core",
        "process_rss_mb_sampled_peak",
        "node_ram_used_mb_sampled_peak",
        "gpu_device_used_mb_sampled_peak",
    ):
        lines.append(
            f"| {key} | {_display_metric(baseline.get('summary', {}).get(key))} | {_display_metric(candidate.get('summary', {}).get(key))} |"
        )
    lines.append("")
    lines.append(
        "TTFT: arrival of the first nonempty text event. Token rates use native output counts only; unavailable counts stay null. Receiver TPOT needs multiple text events and includes transport/aggregation effects."
    )
    lines.append("")
    lines.append(
        "Resources: measured repetitions only, excluding activation/cold/warmup. "
        "CPU 100%=one core; RSS sums explicit process trees (shared pages may repeat). "
        "RAM/VRAM are node/device samples including ambient allocations, not isolated "
        "inference peaks. Short spikes can be missed; missing reads stay unavailable. "
        "Root identities, sample counts, intervals and errors are recorded in JSON."
    )
    lines.append("")
    lines.append("## Exploratory KPI Verdict (not task 266 qualification)")
    lines.append("")
    for key, value in metrics.items():
        verdict = "unavailable" if value is None else "pass" if value else "fail"
        lines.append(f"- {key}: {verdict}")
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
        process_root_pids=args.baseline_root_pid,
        sample_interval_sec=args.resource_interval_sec,
        gpu_index=args.gpu_index,
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
        process_root_pids=args.candidate_root_pid,
        sample_interval_sec=args.resource_interval_sec,
        gpu_index=args.gpu_index,
    )

    report["baseline"] = baseline
    report["candidate"] = candidate
    report["model_selection"] = {
        "baseline": baseline_model_selection,
        "candidate": candidate_model_selection,
    }
    report["benchmark_mode"] = {
        "cold_start_included": True,
        "warmup_excluded_from_primary_percentiles": True,
        "cold_start_definition": "First request after activation; no forced unload or reboot.",
        "resource_window": "Measured repetitions only; explicit root PIDs and descendants.",
        "requested_resource_interval_sec": args.resource_interval_sec,
        "gpu_device_index": args.gpu_index,
    }
    report["kpi"], report["derived"] = _comparison_metrics(baseline, candidate)

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
