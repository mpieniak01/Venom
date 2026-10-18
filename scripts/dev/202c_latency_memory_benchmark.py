#!/usr/bin/env python3
"""202C receiver latency/memory benchmark for Simple and native endpoints.

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
    StreamResult,
    activate_runtime,
    dump_json,
    dump_text,
    http_json,
    load_prompts_jsonl,
    native_chat,
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


def _generation_seed(value: str) -> int:
    parsed = int(value)
    if not -(2**63) <= parsed < 2**63:
        raise argparse.ArgumentTypeError("Seed must fit a signed 64-bit integer")
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
    parser.add_argument("--seed", type=_generation_seed, default=None)
    for role in ("baseline", "candidate"):
        parser.add_argument(f"--{role}-model", default="")
        parser.add_argument(
            f"--{role}-transport", choices=("simple", "native"), default="simple"
        )
        parser.add_argument(
            f"--{role}-native-base-url",
            default="",
            help="Prestarted OpenAI-compatible /v1 base URL; no Venom activation.",
        )
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
    seed: int | None = None,
    transport: str = "simple",
    native_base_url: str = "",
) -> dict[str, Any]:
    if not prompts or repetitions <= 0 or warmup < 0 or max_tokens <= 0:
        raise ValueError("invalid_benchmark_counts_or_prompts")
    if transport not in {"simple", "native"}:
        raise ValueError("invalid_benchmark_transport")
    if transport == "native" and (not native_base_url or not model_name):
        raise ValueError("native_model_and_base_url_required")
    if transport == "simple":
        activation_ok, activation_message, activation_payload = activate_runtime(
            base_url, runtime_id, model_name
        )
    else:
        activation_ok, activation_message = True, "prestarted_native_endpoint"
        activation_payload = {"activation_performed": False}

    def request_case(prompt: dict[str, Any]) -> StreamResult:
        receiver = stream_simple_chat if transport == "simple" else native_chat
        return receiver(
            base_url if transport == "simple" else native_base_url,
            prompt=prompt["prompt"],
            model=model_name,
            max_tokens=prompt.get("max_tokens", max_tokens),
            temperature=temperature,
            seed=seed,
            stream=prompt.get("stream", True),
        )

    if not activation_ok:
        return {
            "runtime_id": runtime_id,
            "selected_model": model_name,
            "activation_ok": False,
            "measurement_complete": False,
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
    cold_start_result = request_case(prompts[0])
    cold_start_latency_ms = cold_start_result.latency_ms

    for idx in range(warmup):
        prompt = prompts[idx % len(prompts)]
        result = request_case(prompt)
        warmup_samples.append(
            {
                "iteration": idx + 1,
                "prompt_id": prompt["id"],
                "stream": prompt.get("stream", True),
                "max_tokens": prompt.get("max_tokens", max_tokens),
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
            result = request_case(prompt)
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
                    "stream": prompt.get("stream", True),
                    "max_tokens": prompt.get("max_tokens", max_tokens),
                    "ok": result.ok,
                    "latency_ms": round(result.latency_ms, 2),
                    "first_token_latency_ms": result.first_token_latency_ms,
                    "output_tokens": result.output_tokens,
                    "prompt_tokens": result.prompt_tokens,
                    "total_tokens": result.total_tokens,
                    "reported_model": result.reported_model,
                    "model_identity": "reported_match"
                    if result.reported_model
                    else "unreported",
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

    result_report: dict[str, Any] = {
        "runtime_id": runtime_id,
        "selected_model": model_name,
        "transport": transport,
        "native_base_url": native_base_url if transport == "native" else None,
        "requested_generation_settings": {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
        },
        "activation_ok": True,
        "activation_message": activation_message,
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
    result_report["errors"] = _measurement_errors(result_report, repetitions, warmup)
    result_report["measurement_complete"] = not result_report["errors"]
    return result_report


def _measurement_errors(
    result: dict[str, Any], repetitions: int, warmup: int
) -> list[str]:
    """Completeness is a data-quality verdict, never the formal task-266 budget."""
    errors = list(result.get("errors", []))
    if result.get("activation_ok") is not True:
        errors.append("activation_failed")
    if result.get("cold_start", {}).get("ok") is not True:
        errors.append("first_request_failed")
    for key, expected in (("warmup_samples", warmup), ("samples", repetitions)):
        samples = result.get(key, [])
        if len(samples) != expected:
            errors.append(f"{key}_incomplete:{len(samples)}/{expected}")
        for index, sample in enumerate(samples, 1):
            if sample.get("ok") is not True:
                errors.append(
                    f"{key}_failed:{index}:{sample.get('error') or 'unknown'}"
                )
    return list(dict.fromkeys(errors))


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
    lines.append("# 202C Receiver Performance Comparison")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Base URL: {report.get('base_url', '')}")
    lines.append("Measurement completeness is not formal task-266 qualification.")
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

    needs_simple = any(
        getattr(args, f"{role}_transport") == "simple"
        for role in ("baseline", "candidate")
    )
    base_url = (
        resolve_base_url(env_file=env_file, explicit=args.base_url)
        if needs_simple
        else str(args.base_url).rstrip("/")
    )
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
        "measurement_complete": False,
        "qualification_status": "NOT_QUALIFIED",
        "kpi_scope": "exploratory_diagnostics_only_not_frozen_acceptance_budgets",
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

    if args.repetitions <= 0 or args.warmup < 0 or args.max_tokens <= 0:
        report["errors"].append("invalid_benchmark_counts")
    for role in ("baseline", "candidate"):
        if getattr(args, f"{role}_transport") == "native" and (
            not getattr(args, f"{role}_model").strip()
            or not getattr(args, f"{role}_native_base_url").strip()
        ):
            report["errors"].append(f"{role}_native_model_and_base_url_required")
    if report["errors"]:
        dump_json((root / args.json_output).resolve(), report)
        return 1
    if needs_simple and not wait_backend_ready(base_url, timeout_sec=30):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    options_payload: dict[str, Any] = {}
    if any(
        not getattr(args, f"{role}_model").strip() for role in ("baseline", "candidate")
    ):
        code, discovered_options = http_json(
            f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
        )
        if code != 200 or not isinstance(discovered_options, dict):
            report["errors"].append("runtime_options_unavailable")
            dump_json((root / args.json_output).resolve(), report)
            return 1
        options_payload = discovered_options
    selections = {}
    models = {}
    for role in ("baseline", "candidate"):
        explicit = getattr(args, f"{role}_model").strip()
        if explicit:
            models[role] = explicit
            selections[role] = {"reason": "explicit_model_id", "selected": explicit}
        else:
            models[role], selections[role] = pick_gemma3_model_with_reason(
                options_payload, getattr(args, f"{role}_runtime")
            )
        if not models[role]:
            report["errors"].append(f"{role}_model_missing")
    if report["errors"]:
        dump_json((root / args.json_output).resolve(), report)
        return 1
    baseline_model, candidate_model = models["baseline"], models["candidate"]
    baseline_model_selection = selections["baseline"]
    candidate_model_selection = selections["candidate"]

    baseline = _run_benchmark_for_runtime(
        base_url=base_url,
        runtime_id=args.baseline_runtime,
        model_name=str(baseline_model),
        prompts=prompts,
        repetitions=args.repetitions,
        warmup=args.warmup,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        transport=args.baseline_transport,
        native_base_url=args.baseline_native_base_url,
        process_root_pids=args.baseline_root_pid,
        sample_interval_sec=args.resource_interval_sec,
        gpu_index=args.gpu_index,
        seed=args.seed,
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
        transport=args.candidate_transport,
        native_base_url=args.candidate_native_base_url,
        process_root_pids=args.candidate_root_pid,
        sample_interval_sec=args.resource_interval_sec,
        gpu_index=args.gpu_index,
        seed=args.seed,
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
        "cold_start_definition": "First request after Simple activation or to a prestarted native endpoint; no proven unload/reboot cold cycle.",
        "resource_window": "Measured repetitions only; explicit root PIDs and descendants.",
        "requested_resource_interval_sec": args.resource_interval_sec,
        "gpu_device_index": args.gpu_index,
    }
    for role, result in (("baseline", baseline), ("candidate", candidate)):
        report["errors"].extend(
            f"{role}:{message}"
            for message in _measurement_errors(result, args.repetitions, args.warmup)
        )
    report["measurement_complete"] = not report["errors"]
    report["kpi"], report["derived"] = _comparison_metrics(baseline, candidate)

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
