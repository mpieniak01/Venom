#!/usr/bin/env python3
"""Shared helpers for 202C runtime diagnostics scripts."""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import statistics
import subprocess
import threading
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
    first_token_latency_ms: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    usage_source: str | None = None
    tokens_per_second: float | None = None
    time_per_output_token_ms: float | None = None


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
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
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


@dataclass
class _ResourceSamples:
    """Constant-space, successful observations only; zero is a valid reading."""

    count: int = 0
    total: float = 0.0
    peak: float | None = None
    first_s: float | None = None
    last_s: float | None = None
    interval_total_s: float = 0.0
    interval_min_s: float | None = None
    interval_max_s: float | None = None

    def add(self, value: float, elapsed_s: float) -> None:
        if self.last_s is not None:
            interval = max(0.0, elapsed_s - self.last_s)
            self.interval_total_s += interval
            self.interval_min_s = (
                interval
                if self.interval_min_s is None
                else min(self.interval_min_s, interval)
            )
            self.interval_max_s = max(self.interval_max_s or 0.0, interval)
        if self.first_s is None:
            self.first_s = elapsed_s
        self.last_s = elapsed_s
        self.count += 1
        self.total += value
        self.peak = value if self.peak is None else max(self.peak, value)

    def mean(self) -> float | None:
        return self.total / self.count if self.count else None

    def timing(self) -> dict[str, Any]:
        return {
            "first_sample_elapsed_s": self.first_s,
            "last_sample_elapsed_s": self.last_s,
            "actual_interval_mean_s": (
                self.interval_total_s / (self.count - 1) if self.count > 1 else None
            ),
            "actual_interval_min_s": self.interval_min_s,
            "actual_interval_max_s": self.interval_max_s,
        }


class ProcessResourceSampler:
    """Read-only sampled process tree and node/device resource observations.

    RSS sums can count shared pages more than once. GPU memory is device-wide,
    not attributable to roots. Polling can miss short-lived children and peaks.
    Memory fields retain the legacy ``_mb`` names but contain MiB (2**20 bytes).
    Only the one monitor subprocess created here may be terminated by finish().
    """

    _MAX_PROCESSES = 4096
    _MAX_ERRORS = 32
    _JOIN_TIMEOUT_SEC = 1.0

    def __init__(
        self,
        root_pids: list[int] | None = None,
        interval_sec: float = 0.1,
        gpu_index: int = 0,
    ) -> None:
        if not math.isfinite(interval_sec) or not 0.02 <= interval_sec <= 5.0:
            raise ValueError(
                "interval_sec must be finite and between 0.02 and 5 seconds"
            )
        if (
            isinstance(gpu_index, bool)
            or not isinstance(gpu_index, int)
            or gpu_index < 0
        ):
            raise ValueError("gpu_index must be a nonnegative integer")
        roots = list(dict.fromkeys(root_pids or []))
        if len(roots) > self._MAX_PROCESSES or any(
            isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
            for pid in roots
        ):
            raise ValueError(
                "root_pids must contain at most 4096 positive integer PIDs"
            )
        self._root_ids = roots
        self._requested_interval = interval_sec
        self._interval = interval_sec
        self._gpu_index = gpu_index
        self._roots: dict[int, dict[str, Any]] = {}
        self._tracked: dict[int, tuple[float, float | None]] = {}
        self._retired: set[int] = set()
        self._errors: list[str] = []
        self._dropped_errors = 0
        self._psutil: Any = None
        self._read_errors: tuple[type[Exception], ...] = (
            OSError,
            ValueError,
            TypeError,
        )
        self._process_samples = _ResourceSamples()
        self._rss = _ResourceSamples()
        self._node = _ResourceSamples()
        self._gpu = _ResourceSamples()
        self._cpu_seconds = 0.0
        self._cpu_delta_count = 0
        self._stop = threading.Event()
        self._gpu_sample_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._gpu_reader: threading.Thread | None = None
        self._gpu_monitor: subprocess.Popen[str] | None = None
        self._started_perf: float | None = None
        self._started_wall: float | None = None
        self._ended_perf: float | None = None
        self._result: dict[str, Any] | None = None

    def _error(self, message: str) -> None:
        if message in self._errors:
            return
        if len(self._errors) < self._MAX_ERRORS:
            self._errors.append(message)
        else:
            self._dropped_errors += 1

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("invalid resource reading")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("invalid resource reading")
        return number

    def _elapsed(self) -> float:
        if self._started_perf is None:
            return 0.0
        return max(0.0, time.perf_counter() - self._started_perf)

    def start(self) -> ProcessResourceSampler:
        if self._started_perf is not None or self._result is not None:
            return self
        self._started_perf = time.perf_counter()
        self._started_wall = time.time()
        if not self._root_ids:
            self._error("root_pids_not_provided")
            return self
        self._roots = {
            pid: {"pid": pid, "create_time": None, "status": "UNAVAILABLE"}
            for pid in self._root_ids
        }
        try:
            self._psutil = importlib.import_module("psutil")
        except ImportError:
            self._error("psutil_unavailable")
            return self
        self._read_errors += (self._psutil.Error,)
        for pid in self._root_ids:
            identity: dict[str, Any] = {"pid": pid, "create_time": None, "status": "OK"}
            self._roots[pid] = identity
            try:
                identity["create_time"] = self._number(
                    self._psutil.Process(pid).create_time()
                )
            except self._read_errors as exc:
                identity["status"] = "UNAVAILABLE"
                self._retired.add(pid)
                self._error(f"root_identity_unavailable:{pid}:{type(exc).__name__}")
        if not any(item["status"] == "OK" for item in self._roots.values()):
            return self
        self._sample()
        self._start_gpu_monitor()
        self._worker = threading.Thread(
            target=self._sample_loop, name="benchmark-resource-sampler", daemon=True
        )
        try:
            self._worker.start()
        except RuntimeError as exc:
            self._worker = None
            self._error(f"process_sampler_start_failed:{type(exc).__name__}")
        return self

    def _sample_loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    def _lose_identity(self, pid: int, reason: str) -> None:
        self._retired.add(pid)
        if pid in self._roots:
            self._roots[pid]["status"] = reason
        self._error(f"process_identity_{reason.lower()}:{pid}")

    def _checked_process(self, pid: int, birth: float) -> Any:
        process = self._psutil.Process(pid)
        if self._number(process.create_time()) != birth:
            self._lose_identity(pid, "CHANGED")
            return None
        return process

    def _candidates(self) -> dict[int, float]:
        candidates = {
            pid: state[0]
            for pid, state in self._tracked.items()
            if pid not in self._retired
        }
        for pid, identity in self._roots.items():
            if identity["status"] != "OK":
                continue
            birth = identity["create_time"]
            try:
                process = self._checked_process(pid, birth)
                if process is None:
                    candidates.pop(pid, None)
                    continue
                candidates[pid] = birth
                descendants = process.children(recursive=True)
            except self._read_errors as exc:
                # A failed root traversal cannot silently claim complete scope.
                self._error(f"root_scope_read_failed:{pid}:{type(exc).__name__}")
                try:
                    process = self._checked_process(pid, birth)
                except self._read_errors:
                    self._lose_identity(pid, "UNAVAILABLE")
                    candidates.pop(pid, None)
                continue
            for child in descendants:
                child_pid = child.pid
                if child_pid in self._retired or child_pid in candidates:
                    continue
                if len(candidates) >= self._MAX_PROCESSES:
                    self._error("process_scope_limit_reached")
                    break
                try:
                    child_birth = self._number(
                        self._psutil.Process(child_pid).create_time()
                    )
                except self._read_errors as exc:
                    self._error(
                        f"child_identity_unavailable:{child_pid}:{type(exc).__name__}"
                    )
                    continue
                candidates[child_pid] = child_birth
        return candidates

    def _process_values(
        self, pid: int, birth: float
    ) -> tuple[float | None, float | None] | None:
        try:
            process = self._checked_process(pid, birth)
            if process is None:
                return None
            cpu = rss = None
            try:
                times = process.cpu_times()
                cpu = self._number(
                    self._number(times.user) + self._number(times.system)
                )
            except self._read_errors as exc:
                self._error(f"process_cpu_unavailable:{pid}:{type(exc).__name__}")
            try:
                rss = self._number(process.memory_info().rss) / (1024**2)
            except self._read_errors as exc:
                self._error(f"process_rss_unavailable:{pid}:{type(exc).__name__}")
            # A fresh Process avoids psutil's cached create_time on PID reuse.
            if self._checked_process(pid, birth) is None:
                return None
            return cpu, rss
        except self._read_errors as exc:
            self._lose_identity(pid, "UNAVAILABLE")
            self._error(f"process_read_failed:{pid}:{type(exc).__name__}")
            return None

    def _sample(self) -> None:
        elapsed = self._elapsed()
        rss_values: list[float] = []
        observed = False
        for pid, birth in self._candidates().items():
            if pid in self._retired:
                continue
            if pid not in self._tracked and len(self._tracked) >= self._MAX_PROCESSES:
                self._error("process_scope_limit_reached")
                continue
            previous = self._tracked.get(pid)
            if previous is not None and previous[0] != birth:
                self._lose_identity(pid, "CHANGED")
                continue
            values = self._process_values(pid, birth)
            if values is None:
                continue
            cpu, rss = values
            observed |= cpu is not None or rss is not None
            if rss is not None:
                rss_values.append(rss)
            prior_cpu = previous[1] if previous else None
            if previous is None and birth >= (self._started_wall or math.inf):
                # New children can be counted from birth; pre-existing CPU is excluded.
                prior_cpu = 0.0
            if cpu is not None and prior_cpu is not None:
                if cpu >= prior_cpu:
                    self._cpu_seconds += cpu - prior_cpu
                    self._cpu_delta_count += 1
                else:
                    self._error(f"process_cpu_counter_regressed:{pid}")
            self._tracked[pid] = (birth, cpu if cpu is not None else prior_cpu)
        if observed:
            self._process_samples.add(0.0, elapsed)
        if rss_values:
            self._rss.add(sum(rss_values), elapsed)
        try:
            memory = self._psutil.virtual_memory()
            used = self._number(memory.total) - self._number(memory.available)
            self._node.add(self._number(used) / (1024**2), elapsed)
        except self._read_errors as exc:
            self._error(f"node_ram_unavailable:{type(exc).__name__}")

    def _start_gpu_monitor(self) -> None:
        try:
            self._gpu_monitor = subprocess.Popen(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                    f"--id={self._gpu_index}",
                    f"--loop-ms={round(self._interval * 1000)}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="ascii",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            self._error(f"gpu_monitor_unavailable:{type(exc).__name__}")
            return
        self._gpu_reader = threading.Thread(
            target=self._read_gpu, name="benchmark-gpu-reader", daemon=True
        )
        try:
            self._gpu_reader.start()
        except RuntimeError as exc:
            self._gpu_reader = None
            self._error(f"gpu_reader_start_failed:{type(exc).__name__}")
            self._stop_gpu_monitor()

    def _read_gpu(self) -> None:
        monitor = self._gpu_monitor
        if monitor is None or monitor.stdout is None:
            return
        oversized = False
        try:
            while not self._stop.is_set():
                line = monitor.stdout.readline(128)
                if self._stop.is_set():
                    break
                if not line:
                    if not self._stop.is_set():
                        self._error("gpu_monitor_ended_before_window")
                    break
                if not line.endswith("\n") or oversized:
                    oversized = not line.endswith("\n")
                    self._error("gpu_monitor_invalid_or_oversized_line")
                    continue
                text = line.strip()
                if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text) is None:
                    self._error("gpu_monitor_invalid_numeric_reading")
                    continue
                value = float(text)
                if math.isfinite(value):
                    with self._gpu_sample_lock:
                        if self._stop.is_set():
                            break
                        self._gpu.add(value, self._elapsed())
                else:
                    self._error("gpu_monitor_invalid_numeric_reading")
        except (OSError, ValueError) as exc:
            self._error(f"gpu_monitor_read_failed:{type(exc).__name__}")

    def _stop_gpu_monitor(self) -> None:
        monitor = self._gpu_monitor
        if monitor is None:
            return
        try:
            if monitor.poll() is None:
                monitor.terminate()
                try:
                    monitor.wait(timeout=self._JOIN_TIMEOUT_SEC)
                except subprocess.TimeoutExpired:
                    monitor.kill()
                    monitor.wait(timeout=self._JOIN_TIMEOUT_SEC)
            elif not self._stop.is_set():
                self._error("gpu_monitor_ended_before_window")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._error(f"gpu_monitor_cleanup_failed:{type(exc).__name__}")
        if self._gpu_reader is not None:
            self._gpu_reader.join(timeout=self._JOIN_TIMEOUT_SEC)
            if self._gpu_reader.is_alive():
                self._error("gpu_reader_shutdown_timeout")
                return
        if monitor.stdout is not None:
            monitor.stdout.close()

    def finish(self) -> dict[str, Any]:
        if self._result is not None:
            return dict(self._result)
        with self._gpu_sample_lock:
            self._stop.set()
        if self._started_perf is None:
            self._error("sampler_not_started")
        if self._worker is not None:
            self._worker.join(timeout=self._JOIN_TIMEOUT_SEC)
            if self._worker.is_alive():
                self._error("process_sampler_shutdown_timeout")
            else:
                self._sample()
        self._ended_perf = time.perf_counter()
        self._stop_gpu_monitor()
        elapsed = (
            max(0.0, self._ended_perf - self._started_perf)
            if self._started_perf is not None
            else 0.0
        )
        process_available = self._process_samples.count > 0
        cpu_available = self._cpu_delta_count > 0
        partial = (
            bool(self._errors)
            or not cpu_available
            or not self._rss.count
            or not self._gpu.count
            or not self._node.count
        )
        self._result = {
            "status": ("PARTIAL" if partial else "OK")
            if process_available
            else "UNAVAILABLE",
            "cpu_status": ("PARTIAL" if self._errors else "OK")
            if cpu_available
            else "UNAVAILABLE",
            "process_rss_status": ("PARTIAL" if self._errors else "OK")
            if self._rss.count
            else "UNAVAILABLE",
            "node_ram_status": (
                "PARTIAL"
                if any(e.startswith("node_ram_") for e in self._errors)
                else "OK"
            )
            if self._node.count
            else "UNAVAILABLE",
            "gpu_status": (
                "PARTIAL" if any(e.startswith("gpu_") for e in self._errors) else "OK"
            )
            if self._gpu.count
            else "UNAVAILABLE",
            "cpu_mean_percent_one_core": (
                self._cpu_seconds / elapsed * 100
                if cpu_available and elapsed > 0
                else None
            ),
            "cpu_seconds_observed": self._cpu_seconds if cpu_available else None,
            "process_rss_mb_sampled_peak": self._rss.peak,
            "process_rss_mb_mean": self._rss.mean(),
            "node_ram_used_mb_sampled_peak": self._node.peak,
            "node_ram_used_mb_mean": self._node.mean(),
            "gpu_device_used_mb_sampled_peak": self._gpu.peak,
            "gpu_device_used_mb_mean": self._gpu.mean(),
            "gpu_sample_count": self._gpu.count,
            "process_sample_count": self._process_samples.count,
            "node_ram_sample_count": self._node.count,
            "process_rss_sample_count": self._rss.count,
            "cpu_delta_count": self._cpu_delta_count,
            "window_elapsed_s": elapsed,
            "window_started_at_unix_s": self._started_wall,
            "requested_interval_sec": self._requested_interval,
            "effective_interval_sec": self._interval,
            "root_identities": [dict(identity) for identity in self._roots.values()],
            "observed_process_identity_count": len(self._tracked),
            "retired_process_count": len(self._retired),
            "process_scope": "explicit_roots_and_observed_descendants",
            "node_ram_scope": "whole_node_total_minus_available",
            "gpu_scope": "whole_device_not_process_attributed",
            "gpu_index": self._gpu_index,
            "memory_unit": "MiB",
            "sampling": {
                "process": self._process_samples.timing(),
                "node_ram": self._node.timing(),
                "gpu_device": self._gpu.timing(),
            },
            "caveats": [
                "Sampling may miss short-lived children, their final CPU time, and peaks.",
                "Summed process RSS may count shared pages more than once; PSS is not measured.",
                "CPU is user+system deltas; 100 percent means one logical core.",
                "Node RAM and device VRAM include unrelated workloads.",
                "Means are arithmetic means of successful samples, not time-weighted means.",
                "Known descendant identities remain in scope after reparenting.",
            ],
            "errors": list(self._errors),
            "dropped_error_count": self._dropped_errors,
        }
        return dict(self._result)


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
        "stream": True,
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
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0]
            if resp.status != 200 or content_type != "text/event-stream":
                raise ValueError("response_is_not_sse")
            return _read_timed_sse(resp, started=started, timeout_sec=timeout_sec)
    except error.HTTPError as exc:
        details = exc.read(401).decode("utf-8", errors="replace")
        message = f"http_error:{exc.code}:{details[:400]}"
    except (OSError, error.URLError, ValueError, UnicodeError) as exc:
        message = f"stream_or_transport_error:{type(exc).__name__}:{exc}"
    return StreamResult(
        ok=False,
        text="",
        latency_ms=(time.perf_counter() - started) * 1000.0,
        event_count=0,
        error=message,
    )


def _native_usage_from_done(packet_text: str) -> dict[str, int]:
    """Only accept explicit upstream counts, including legitimate zero counters."""
    packet = json.loads(packet_text)
    if not isinstance(packet, dict) or packet.get("usage_source") != "upstream":
        return {}
    raw_usage = packet.get("usage")
    if not isinstance(raw_usage, dict):
        raise ValueError("invalid_native_usage")
    usage: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key not in raw_usage:
            continue
        value = raw_usage[key]
        if type(value) is not int or value < 0:
            raise ValueError("invalid_native_usage_counter")
        usage[key] = value
    if all(
        key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    ):
        if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            raise ValueError("inconsistent_native_usage_total")
    return usage


def _read_timed_sse(response, *, started: float, timeout_sec: float) -> StreamResult:
    """Measure arrival of the first nonempty text event, without buffering to EOF."""
    event_name = "message"
    data: list[str] = []
    chunks: list[str] = []
    event_count = 0
    received = 0
    first_token_ms = None
    text_events = 0
    usage: dict[str, int] = {}
    saw_done = False
    while True:
        if time.perf_counter() - started > timeout_sec:
            raise TimeoutError("stream_deadline_exceeded")
        raw = response.readline(65537)
        if time.perf_counter() - started > timeout_sec:
            raise TimeoutError("stream_deadline_exceeded")
        if not raw:
            break
        received += len(raw)
        if len(raw) > 65536 or received > 1024 * 1024:
            raise ValueError("stream_too_large")
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line:
            if data:
                event_count += 1
                packet_text = "\n".join(data)
                if event_name == "content":
                    packet = json.loads(packet_text)
                    text = packet.get("text") if isinstance(packet, dict) else None
                    if not isinstance(text, str):
                        raise ValueError("invalid_content_event")
                    if text.strip():
                        text_events += 1
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000.0
                    chunks.append(text)
                elif event_name == "error":
                    raise ValueError("server_error_event:" + packet_text[:400])
                elif event_name == "done":
                    usage = _native_usage_from_done(packet_text)
                    saw_done = True
                    break
            event_name, data = "message", []
    full_text = "".join(chunks).strip()
    ok = saw_done and bool(full_text)
    latency_ms = (time.perf_counter() - started) * 1000.0
    output_tokens = usage.get("completion_tokens")
    if output_tokens == 0 and full_text:
        raise ValueError("native_output_usage_zero_for_text")
    tokens_per_second = None
    tpot_ms = None
    if ok and output_tokens is not None and latency_ms > 0:
        tokens_per_second = output_tokens / (latency_ms / 1000.0)
        if output_tokens > 1 and text_events > 1 and first_token_ms is not None:
            tpot_ms = (latency_ms - first_token_ms) / (output_tokens - 1)
    return StreamResult(
        ok=ok,
        text=full_text,
        latency_ms=latency_ms,
        event_count=event_count,
        error=None if ok else "empty_or_incomplete_stream",
        first_token_latency_ms=first_token_ms,
        prompt_tokens=usage.get("prompt_tokens"),
        output_tokens=output_tokens,
        total_tokens=usage.get("total_tokens"),
        usage_source="upstream" if usage else None,
        tokens_per_second=tokens_per_second,
        time_per_output_token_ms=tpot_ms,
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
