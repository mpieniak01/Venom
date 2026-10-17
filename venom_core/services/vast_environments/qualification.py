"""Qualification of the observed stack for one explicit workload."""

from __future__ import annotations

from venom_core.infrastructure.providers.vast.models import EnvironmentPlan, now
from venom_core.infrastructure.providers.vast.runtime_contracts import version_parts

POLICY_VERSION = "vast-runtime-v1"


def _minimum(actual, expected: str, field: str, failed: list, unknown: list) -> None:
    if not expected:
        return
    observed, required = version_parts(actual), version_parts(expected)
    if observed is None:
        unknown.append(field)
    elif required is not None and observed < required:
        failed.append(field)


def _acceleration(
    profile, probe: dict, engine: dict, failed: list, unknown: list
) -> None:
    runtime = profile.runtime
    if runtime.acceleration == "any":
        return
    if runtime.acceleration == "cpu":
        if (
            profile.mode == "ollama"
            and (probe.get("ollama_processor") or {}).get("cpu_percent") != 100
        ):
            unknown.append("cpu_backend")
        elif profile.mode != "ollama":
            unknown.append("cpu_backend")
        return
    if probe.get("status") == "failed" and probe.get("cuda_error") in {
        209,
        218,
        222,
        999,
    }:
        unknown.append("cuda_probe_support")
    elif probe.get("status") == "failed":
        failed.append("cuda_kernel")
    elif probe.get("status") != "passed":
        unknown.append("cuda_kernel")
    if profile.mode in {"vllm", "pytorch"}:
        state = probe.get("engine_kernel")
        if state in {"failed", "missing"}:
            failed.append("engine_kernel")
        elif state != "passed":
            unknown.append("engine_kernel")
    if profile.mode == "ollama":
        processor = probe.get("ollama_processor") or {}
        percent = processor.get("gpu_percent")
        if percent is None:
            unknown.append("model_gpu_backend")
        elif percent == 0 or (percent < 100 and not runtime.allow_cpu_offload):
            failed.append("model_gpu_backend")
        loaded = engine.get("loaded_model") or {}
        if loaded.get("digest") != profile.model_digest:
            unknown.append("loaded_model_digest")


def _scope(failed: list, probe: dict) -> str:
    if any(
        x in failed
        for x in [
            "cuda_kernel",
            "engine_kernel",
            "compute_capability",
            "model_gpu_backend",
        ]
    ):
        return "stack_gpu"
    if any(x in failed for x in ["driver_version", "driver_cuda"]):
        return "host"
    return "workload"


def qualify(
    plan: EnvironmentPlan,
    inspection: dict,
    probe: dict,
    engine: dict | None = None,
    benchmark: dict | None = None,
    *,
    evaluate_performance: bool = True,
) -> dict:
    profile, runtime = plan.profile, plan.profile.runtime
    engine = engine or {}
    failed = ["capacity." + x for x in inspection.get("reasons", [])]
    unknown = ["capacity." + x for x in inspection.get("unknown", [])]
    if engine.get("readiness") == "inconclusive":
        unknown.append("model_readiness")
    _acceleration(profile, probe, engine, failed, unknown)
    _minimum(
        probe.get("driver_version"),
        runtime.min_driver,
        "driver_version",
        failed,
        unknown,
    )
    _minimum(probe.get("driver_cuda"), runtime.min_cuda, "driver_cuda", failed, unknown)
    _minimum(
        probe.get("driver_cuda"), runtime.image_min_cuda, "driver_cuda", failed, unknown
    )
    packages = probe.get("packages") or {}
    version = engine.get("engine_version") or packages.get(
        profile.mode if profile.mode != "pytorch" else "torch"
    )
    _minimum(version, runtime.min_engine_version, "engine_version", failed, unknown)
    if runtime.compute_capabilities:
        compute = probe.get("compute_cap")
        if compute is None:
            unknown.append("compute_capability")
        elif compute not in runtime.compute_capabilities:
            failed.append("compute_capability")
    if benchmark is not None:
        if benchmark.get("status") == "unsuitable":
            failed.append("benchmark")
        elif benchmark.get("status") != "suitable":
            unknown.append("benchmark")
    if evaluate_performance and runtime.max_ttft_s is not None:
        value = (benchmark or {}).get("short_ttft_median_s")
        if value is None:
            unknown.append("ttft")
        elif value > runtime.max_ttft_s:
            failed.append("ttft")
    if evaluate_performance and runtime.min_characters_s is not None:
        samples = (benchmark or {}).get("samples", [])
        values = [
            x["characters_s"]
            for x in samples
            if x.get("status") == "ok"
            and x.get("characters_s") is not None
            and x.get("case", "").startswith("short")
        ]
        if not values:
            unknown.append("characters_s")
        elif min(values) < runtime.min_characters_s:
            failed.append("characters_s")
    failed, unknown = sorted(set(failed)), sorted(set(unknown))
    return {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "observed_at": now().isoformat(),
        "status": "unsuitable" if failed else "inconclusive" if unknown else "suitable",
        "reasons": failed,
        "unknown": unknown,
        "cause_scope": _scope(failed, probe) if failed else "stack_gpu",
        "requirements": runtime.model_dump(mode="json"),
        "declared": plan.assessment.runtime,
        "observed": {"probe": probe, "engine_version": version, "engine": engine},
        "inspection": inspection,
        "benchmark": benchmark,
        "performance_evaluated": evaluate_performance,
        "automatic_repair": False,
    }
