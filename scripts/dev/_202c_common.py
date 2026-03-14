#!/usr/bin/env python3
"""Shared helpers for 202C runtime diagnostics scripts."""

from __future__ import annotations

import json
import os
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

GEMMA3_TOKENS = ("gemma-3", "gemma3")
DEFAULT_TIMEOUT_SEC = 60.0
ONNX_TEST_MODEL_PATTERNS = (
    "build-test",
    "good--",
    "dummy",
    "test",
)
ONNX_PROD_HINTS = (
    "genai",
    "int4",
    "q4",
)


@dataclass(frozen=True)
class StreamResult:
    ok: bool
    text: str
    latency_ms: float
    event_count: int
    error: str | None = None


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def env_value(name: str, env_file_values: dict[str, str], default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if name in env_file_values:
        return env_file_values[name]
    return default


def resolve_base_url(*, env_file: Path, explicit: str = "") -> str:
    explicit_norm = explicit.strip()
    if explicit_norm:
        return explicit_norm.rstrip("/")
    values = read_env_file(env_file)
    host = env_value("HOST_DISPLAY", values, "127.0.0.1")
    port = env_value("PORT", values, "8000")
    return f"http://{host}:{port}"


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    data_bytes: bytes | None = None
    headers: dict[str, str] = {}
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method, data=data_bytes, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return int(resp.status), None
            try:
                return int(resp.status), json.loads(raw)
            except json.JSONDecodeError:
                return int(resp.status), {"raw": raw}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if raw.strip():
            try:
                return int(exc.code), json.loads(raw)
            except json.JSONDecodeError:
                return int(exc.code), {"raw": raw}
        return int(exc.code), None
    except (error.URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


def wait_backend_ready(base_url: str, timeout_sec: int = 120) -> bool:
    status_url = f"{base_url}/api/v1/system/status"
    deadline = time.time() + max(1, timeout_sec)
    while time.time() < deadline:
        code, _payload = http_json(status_url, timeout_sec=3.0)
        if code == 200:
            return True
        time.sleep(1.0)
    return False


def ensure_output_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_output_parent(path)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def dump_text(path: Path, text: str) -> None:
    ensure_output_parent(path)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def normalize_text(text: str) -> str:
    stripped = text.strip().lower()
    stripped = re.sub(r"\s+", " ", stripped)
    stripped = re.sub(r"[^a-z0-9\s]", "", stripped)
    return stripped


def token_set(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {token for token in normalized.split(" ") if token}


def semantic_similarity_heuristic(a_text: str, b_text: str) -> float:
    a = token_set(a_text)
    b = token_set(b_text)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    common = len(a.intersection(b))
    denom = len(a.union(b))
    return float(common / denom) if denom > 0 else 0.0


def contains_policy_block(text: str) -> bool:
    probe = text.lower()
    patterns = (
        "nie moge",
        "nie mog\u0119",
        "i can't",
        "i cannot",
        "cannot help with that",
        "can't assist",
        "przykro",
        "odmawiam",
    )
    return any(token in probe for token in patterns)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * max(0.0, min(1.0, q))
    low = int(idx)
    high = min(low + 1, len(sorted_vals) - 1)
    frac = idx - low
    return float(sorted_vals[low] * (1 - frac) + sorted_vals[high] * frac)


def system_memory_used_mb() -> float:
    mem_total_kb = 0.0
    mem_available_kb = 0.0
    try:
        for raw in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if raw.startswith("MemTotal:"):
                mem_total_kb = float(raw.split()[1])
            elif raw.startswith("MemAvailable:"):
                mem_available_kb = float(raw.split()[1])
    except OSError:
        return 0.0
    if mem_total_kb <= 0:
        return 0.0
    return max(0.0, (mem_total_kb - mem_available_kb) / 1024.0)


def gpu_memory_used_mb() -> float:
    import subprocess

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return 0.0
    if completed.returncode != 0:
        return 0.0
    values: list[float] = []
    for line in completed.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            values.append(float(text))
        except ValueError:
            continue
    return max(values) if values else 0.0


def _runtime_from_options(
    options_payload: dict[str, Any], runtime_id: str
) -> dict[str, Any] | None:
    runtimes_raw = options_payload.get("runtimes")
    if not isinstance(runtimes_raw, list):
        return None
    runtime_norm = runtime_id.strip().lower()
    for item in runtimes_raw:
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("runtime_id") or "").strip().lower()
        if candidate == runtime_norm:
            return item
    return None


def runtime_models_from_options(
    options_payload: dict[str, Any], runtime_id: str
) -> list[str]:
    runtime = _runtime_from_options(options_payload, runtime_id)
    if not isinstance(runtime, dict):
        return []
    models_raw = runtime.get("models")
    if not isinstance(models_raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in models_raw:
        if not isinstance(item, dict):
            continue
        model_name = str(item.get("name") or item.get("id") or "").strip()
        if not model_name:
            continue
        key = model_name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(model_name)
    return out


def rank_model_for_runtime(runtime_id: str, model_name: str) -> tuple[int, list[str]]:
    runtime = runtime_id.strip().lower()
    lowered = model_name.strip().lower()
    score = 0
    reasons: list[str] = []

    if any(token in lowered for token in GEMMA3_TOKENS):
        score += 200
        reasons.append("gemma3_family")
    if "4b" in lowered:
        score += 30
        reasons.append("prefer_4b")
    if runtime == "onnx":
        if any(pattern in lowered for pattern in ONNX_TEST_MODEL_PATTERNS):
            score -= 120
            reasons.append("penalize_test_artifact")
        if any(hint in lowered for hint in ONNX_PROD_HINTS):
            score += 40
            reasons.append("prefer_prod_quantized")
        if "onnx" in lowered:
            score += 10
            reasons.append("onnx_named_artifact")
    return score, reasons


def pick_gemma3_model_with_reason(
    options_payload: dict[str, Any],
    runtime_id: str,
) -> tuple[str | None, dict[str, Any]]:
    models = runtime_models_from_options(options_payload, runtime_id)
    if not models:
        return None, {
            "reason": "no_models_available",
            "runtime_id": runtime_id,
            "candidates": [],
        }

    ranked: list[dict[str, Any]] = []
    for model in models:
        score, reasons = rank_model_for_runtime(runtime_id, model)
        ranked.append(
            {
                "model": model,
                "score": score,
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: int(item["score"]), reverse=True)
    selected = ranked[0]["model"] if ranked else None
    return selected, {
        "reason": "ranked_selection",
        "runtime_id": runtime_id,
        "selected": selected,
        "candidates": ranked,
    }


def pick_gemma3_model(options_payload: dict[str, Any], runtime_id: str) -> str | None:
    selected, _info = pick_gemma3_model_with_reason(options_payload, runtime_id)
    return selected


def activate_runtime(
    base_url: str, runtime_id: str, model: str | None = None
) -> tuple[bool, str, dict[str, Any] | list[Any] | None]:
    payload: dict[str, Any] = {"server_name": runtime_id}
    if model:
        payload["model"] = model
    code, body = http_json(
        f"{base_url}/api/v1/system/llm-servers/active",
        method="POST",
        payload=payload,
        timeout_sec=120.0 if runtime_id == "vllm" else 90.0,
    )
    if code != 200:
        return False, f"activation_failed status={code}", body
    return True, "ok", body


def get_active_runtime(base_url: str) -> tuple[int, dict[str, Any] | list[Any] | None]:
    return http_json(f"{base_url}/api/v1/system/llm-servers/active", timeout_sec=20.0)


def parse_sse_events(raw_payload: str) -> list[tuple[str, str]]:
    chunks = raw_payload.split("\n\n")
    events: list[tuple[str, str]] = []
    for chunk in chunks:
        event_name = "message"
        data_parts: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
            elif line.startswith("data:"):
                data_parts.append(line.split(":", 1)[1].strip())
        if data_parts:
            events.append((event_name, "\n".join(data_parts)))
    return events


def stream_simple_chat(
    base_url: str,
    *,
    prompt: str,
    model: str | None,
    max_tokens: int,
    temperature: float,
    timeout_sec: float = 180.0,
) -> StreamResult:
    payload: dict[str, Any] = {
        "content": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if model:
        payload["model"] = model
    req = request.Request(
        url=f"{base_url}/api/v1/llm/simple/stream",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    started = time.perf_counter()
    raw = ""
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return StreamResult(
            ok=False,
            text="",
            latency_ms=(time.perf_counter() - started) * 1000.0,
            event_count=0,
            error=f"http_error:{exc.code}:{details[:400]}",
        )
    except (error.URLError, TimeoutError) as exc:
        return StreamResult(
            ok=False,
            text="",
            latency_ms=(time.perf_counter() - started) * 1000.0,
            event_count=0,
            error=f"transport_error:{exc}",
        )

    events = parse_sse_events(raw)
    chunks: list[str] = []
    saw_done = False
    for event_name, event_data in events:
        if event_name == "content":
            try:
                packet = json.loads(event_data)
            except json.JSONDecodeError:
                continue
            text = str(packet.get("text") or "")
            if text:
                chunks.append(text)
        elif event_name == "error":
            return StreamResult(
                ok=False,
                text="",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                event_count=len(events),
                error=f"stream_error:{event_data[:400]}",
            )
        elif event_name == "done":
            saw_done = True

    full_text = "".join(chunks).strip()
    ok = saw_done and bool(full_text)
    return StreamResult(
        ok=ok,
        text=full_text,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        event_count=len(events),
        error=None if ok else "empty_or_incomplete_stream",
    )


def load_prompts_jsonl(path: Path) -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {idx}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"JSONL item at line {idx} is not an object")
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"JSONL item at line {idx} has empty 'prompt'")
        prompt_id = str(item.get("id") or f"prompt_{idx:03d}").strip()
        prompts.append(
            {
                "id": prompt_id,
                "prompt": prompt,
                "category": str(item.get("category") or "general"),
            }
        )
    if not prompts:
        raise ValueError(f"Prompt set is empty: {path}")
    return prompts


def summarize_latency(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
        }
    return {
        "count": float(len(values)),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "mean_ms": float(statistics.fmean(values)),
    }
