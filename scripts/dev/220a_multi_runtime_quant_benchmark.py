#!/usr/bin/env python3
"""220A benchmark: multi_runtime Gemma4 quantization/optimization variants.

Runs the same prompt for multiple runtime profile variants and reports:
- request latency (wall clock)
- daemon VRAM status (allocated/reserved/total)
- active precision/quantization/device/cache params

Default prompt (Polish): "co to jest slonce?"
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.multi_runtime.engine import (  # noqa: E402
    MultiRuntimeEngine,
    _get_vram_info,
)


@dataclass
class Variant:
    name: str
    precision: str
    quantization_backend: str | None
    device_target: str
    cache_implementation: str


DEFAULT_VARIANTS: list[Variant] = [
    Variant(
        name="baseline_auto",
        precision="auto",
        quantization_backend=None,
        device_target="auto",
        cache_implementation="dynamic",
    ),
    Variant(
        name="fp16_cuda",
        precision="float16",
        quantization_backend=None,
        device_target="cuda",
        cache_implementation="dynamic",
    ),
    Variant(
        name="int8_bnb_cuda",
        precision="int8",
        quantization_backend="bitsandbytes",
        device_target="cuda",
        cache_implementation="dynamic",
    ),
    Variant(
        name="int4_bnb_cuda",
        precision="int4",
        quantization_backend="bitsandbytes",
        device_target="cuda",
        cache_implementation="dynamic",
    ),
]


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _env_or_file(name: str, env_file: dict[str, str], default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if name in env_file:
        return env_file[name]
    return default


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 60.0,
) -> tuple[int, Any]:
    data_bytes: bytes | None = None
    headers: dict[str, str] = {}
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method, data=data_bytes, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw.strip() else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def _wait_status_ready(daemon_base: str, timeout_sec: int = 180) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        code, payload = _http_json(f"{daemon_base}/v1/daemon/status", timeout_sec=10.0)
        if code == 200 and isinstance(payload, dict):
            if not bool(payload.get("pending_reload", False)):
                return True
        time.sleep(1)
    return False


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _activate_multi_runtime(api_base: str, model: str) -> None:
    code, payload = _http_json(
        f"{api_base}/api/v1/system/llm-servers/active",
        method="POST",
        payload={"server_name": "multi_runtime", "model": model},
        timeout_sec=120.0,
    )
    if code != 200:
        raise RuntimeError(
            f"activate multi_runtime failed: status={code} payload={payload}"
        )


def _apply_variant(daemon_base: str, variant: Variant) -> dict[str, Any]:
    payload = {
        "precision": variant.precision,
        "quantization_backend": variant.quantization_backend,
        "device_target": variant.device_target,
        "cache_implementation": variant.cache_implementation,
    }
    code, body = _http_json(
        f"{daemon_base}/v1/daemon/profile",
        method="POST",
        payload=payload,
        timeout_sec=90.0,
    )
    if code != 200:
        raise RuntimeError(f"profile update failed: status={code} payload={body}")

    required_apply_mode = (
        str(body.get("required_apply_mode", "live"))
        if isinstance(body, dict)
        else "live"
    )
    reload_executed = False
    reload_duration_sec = 0.0
    if required_apply_mode == "soft_reload":
        t0 = time.perf_counter()
        r_code, r_body = _http_json(
            f"{daemon_base}/v1/daemon/reload",
            method="POST",
            payload={},
            timeout_sec=300.0,
        )
        reload_duration_sec = time.perf_counter() - t0
        reload_executed = True
        if r_code != 200:
            raise RuntimeError(f"soft reload failed: status={r_code} payload={r_body}")
    elif required_apply_mode == "hard_restart":
        t0 = time.perf_counter()
        r_code, r_body = _http_json(
            f"{daemon_base}/v1/daemon/restart",
            method="POST",
            payload={},
            timeout_sec=60.0,
        )
        reload_duration_sec = time.perf_counter() - t0
        reload_executed = True
        if r_code != 200:
            raise RuntimeError(f"hard restart failed: status={r_code} payload={r_body}")

    if not _wait_status_ready(daemon_base, timeout_sec=300):
        raise RuntimeError("daemon not ready after profile apply")
    out = body if isinstance(body, dict) else {"raw": body}
    out["required_apply_mode"] = required_apply_mode
    out["reload_executed"] = reload_executed
    out["reload_duration_sec"] = reload_duration_sec
    return out


def _daemon_status(daemon_base: str) -> dict[str, Any]:
    code, payload = _http_json(f"{daemon_base}/v1/daemon/status", timeout_sec=30.0)
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"daemon status failed: status={code} payload={payload}")
    return payload


def _warmup_prompt(daemon_base: str, model: str, prompt: str, max_tokens: int) -> None:
    _run_prompt(daemon_base, model, prompt, max_tokens)


def _run_prompt(
    daemon_base: str, model: str, prompt: str, max_tokens: int
) -> tuple[float, str]:
    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }
    t0 = time.perf_counter()
    code, payload = _http_json(
        f"{daemon_base}/v1/chat/completions",
        method="POST",
        payload=request_payload,
        timeout_sec=180.0,
    )
    elapsed = time.perf_counter() - t0
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"chat failed: status={code} payload={payload}")
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return elapsed, str(content)


def _variant_from_json(items: list[dict[str, Any]]) -> list[Variant]:
    out: list[Variant] = []
    for item in items:
        out.append(
            Variant(
                name=str(item["name"]),
                precision=str(item.get("precision", "auto")),
                quantization_backend=item.get("quantization_backend"),
                device_target=str(item.get("device_target", "auto")),
                cache_implementation=str(item.get("cache_implementation", "dynamic")),
            )
        )
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="220A multi_runtime quant benchmark")
    parser.add_argument("--root", default=".")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--daemon-base", default="")
    parser.add_argument("--model", default="google/gemma-4-E2B-it")
    parser.add_argument("--prompt", default="co to jest slonce?")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--variants-json", default="")
    parser.add_argument(
        "--skip-activate",
        action="store_true",
        help="Skip backend runtime activation and use daemon endpoint directly.",
    )
    parser.add_argument(
        "--output",
        default="test-results/benchmarks/220a_multi_runtime_quant_benchmark.json",
    )
    parser.add_argument(
        "--direct-engine",
        action="store_true",
        help="Run benchmark directly on MultiRuntimeEngine (no HTTP daemon).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = (root / env_path).resolve()
    env_values = _read_env_file(env_path)

    host = _env_or_file("HOST_DISPLAY", env_values, "127.0.0.1")
    api_port = _env_or_file("PORT", env_values, "8000")
    api_base = args.api_base.strip() or f"http://{host}:{api_port}"
    daemon_base = args.daemon_base.strip() or "http://127.0.0.1:8014"

    variants = DEFAULT_VARIANTS
    if args.variants_json.strip():
        variants = _variant_from_json(json.loads(args.variants_json))

    if not args.skip_activate and not args.direct_engine:
        _activate_multi_runtime(api_base, args.model)

    report: dict[str, Any] = {
        "api_base": api_base,
        "daemon_base": daemon_base,
        "model": args.model,
        "prompt": args.prompt,
        "runs": args.runs,
        "results": [],
        "generated_at": int(time.time()),
    }

    cache_dir = _env_or_file("GEMMA4_AUDIO_CACHE_DIR", env_values, "models_cache/hf")
    if not str(cache_dir).startswith("/"):
        cache_dir = str((root / cache_dir).resolve())

    for variant in variants:
        if args.direct_engine:
            vram_before = _get_vram_info().__dict__
            latencies: list[float] = []
            last_answer = ""
            apply_result: dict[str, Any] = {"mode": "direct_engine"}
            active_before: dict[str, Any] = {}
            active_after: dict[str, Any] = {}
            daemon_params_after: dict[str, Any] = {
                "precision": variant.precision,
                "quantization_backend": variant.quantization_backend,
                "device_target": variant.device_target,
                "cache_implementation": variant.cache_implementation,
            }
            engine = MultiRuntimeEngine(
                model_id=args.model,
                cache_dir=cache_dir,
                device=variant.device_target,
                max_new_tokens=args.max_tokens,
                precision=variant.precision,
                quantization_backend=variant.quantization_backend,
            )
            try:
                engine.load()
                for _ in range(max(1, args.runs)):
                    t0 = time.perf_counter()
                    text, _dur = engine.respond(
                        None,
                        sample_rate=16000,
                        prompt=args.prompt,
                        max_new_tokens=args.max_tokens,
                        cache_implementation=variant.cache_implementation,
                    )
                    latencies.append(time.perf_counter() - t0)
                    last_answer = text
            except Exception as exc:  # noqa: BLE001
                apply_result["error"] = str(exc)
            finally:
                engine.unload()
            vram_after = _get_vram_info().__dict__
        else:
            apply_result = _apply_variant(daemon_base, variant)
            status_before = _daemon_status(daemon_base)
            vram_before = status_before.get("vram", {})
            active_before = status_before.get("active_runtime_config", {})

            _warmup_prompt(
                daemon_base,
                args.model,
                args.prompt,
                min(args.max_tokens, 32),
            )
            latencies = []
            last_answer = ""
            for _ in range(max(1, args.runs)):
                elapsed, answer = _run_prompt(
                    daemon_base,
                    args.model,
                    args.prompt,
                    args.max_tokens,
                )
                latencies.append(elapsed)
                last_answer = answer

            status_after = _daemon_status(daemon_base)
            daemon_params_after = status_after.get("params", {})
            active_after = status_after.get("active_runtime_config", {})
            vram_after = status_after.get("vram", {})

        report["results"].append(
            {
                "variant": {
                    "name": variant.name,
                    "precision": variant.precision,
                    "quantization_backend": variant.quantization_backend,
                    "device_target": variant.device_target,
                    "cache_implementation": variant.cache_implementation,
                },
                "apply_result": apply_result,
                "latency_sec": {
                    "samples": latencies,
                    "min": min(latencies) if latencies else None,
                    "max": max(latencies) if latencies else None,
                    "avg": statistics.fmean(latencies) if latencies else None,
                    "median": statistics.median(latencies) if latencies else None,
                },
                "daemon_params_after": daemon_params_after,
                "active_runtime_config_before": active_before,
                "active_runtime_config_after": active_after,
                "vram_before": vram_before,
                "vram_after": vram_after,
                "vram_allocated_delta_mb": round(
                    _to_float(vram_after.get("allocated_mb"))
                    - _to_float(vram_before.get("allocated_mb")),
                    2,
                ),
                "vram_reserved_delta_mb": round(
                    _to_float(vram_after.get("reserved_mb"))
                    - _to_float(vram_before.get("reserved_mb")),
                    2,
                ),
                "answer_preview": last_answer[:400],
            }
        )

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Saved benchmark report: {output_path}")
    print("\nSummary:")
    for item in report["results"]:
        name = item["variant"]["name"]
        latency = item["latency_sec"]
        vram_after = item.get("vram_after", {})
        print(
            f"- {name}: avg={latency['avg']:.3f}s min={latency['min']:.3f}s "
            f"max={latency['max']:.3f}s | backend={vram_after.get('backend')} "
            f"alloc={vram_after.get('allocated_mb')}MB reserved={vram_after.get('reserved_mb')}MB"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
