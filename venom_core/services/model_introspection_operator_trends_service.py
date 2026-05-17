"""Persistent operator run trends for model introspection analysis."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None  # type: ignore[assignment]

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_TRENDS_FILENAME = "operator_run_trends.json"
_MAX_STORED_RUNS = 200
_DEFAULT_WINDOW = 20
_STORE_LOCK = threading.Lock()
_DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "data" / "introspection"
_DEFAULT_PROBE_SUCCESS_RATE_MIN = 90.0
_DEFAULT_FIRST_CHUNK_P95_MS_MAX = 2500.0
_DEFAULT_FALLBACK_RATE_MAX = 25.0


def _resolve_storage_namespace(cfg: Any) -> str:
    """Map runtime config to a closed namespace, never raw user path segments."""
    storage_prefix = str(getattr(cfg, "STORAGE_PREFIX", "") or "").strip().lower()
    if storage_prefix.strip("/") == "preprod":
        return "preprod"
    environment_role = str(getattr(cfg, "ENVIRONMENT_ROLE", "") or "").strip().lower()
    if environment_role == "preprod":
        return "preprod"
    return "dev"


def _resolve_storage_path(settings: Any | None = None) -> Path:
    cfg = settings or SETTINGS
    namespace = _resolve_storage_namespace(cfg)
    root = _DEFAULT_STORAGE_ROOT.resolve()
    return root / namespace / _TRENDS_FILENAME


def _normalize_record(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    request_id = str(raw.get("request_id") or "").strip()
    if not request_id:
        return None
    ts_ms_value = raw.get("ts_ms")
    ts_ms = int(ts_ms_value) if isinstance(ts_ms_value, (int, float)) else 0
    record: dict[str, Any] = {
        "request_id": request_id,
        "ts_ms": ts_ms if ts_ms > 0 else int(time.time() * 1000),
        "rag_source": str(raw.get("rag_source") or "graph_fallback"),
        "probe_source": str(raw.get("probe_source") or "probe_unavailable"),
        "stream_quality": str(raw.get("stream_quality") or "unknown"),
        "coverage_percent": None,
        "first_content_ms": None,
        "token_noise_ratio": None,
    }
    coverage_percent = raw.get("coverage_percent")
    if isinstance(coverage_percent, (int, float)):
        record["coverage_percent"] = float(coverage_percent)
    first_content_ms = raw.get("first_content_ms")
    if isinstance(first_content_ms, (int, float)):
        record["first_content_ms"] = float(first_content_ms)
    token_noise_ratio = raw.get("token_noise_ratio")
    if isinstance(token_noise_ratio, (int, float)):
        record["token_noise_ratio"] = float(token_noise_ratio)
    return record


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read operator trends store", exc_info=True)
        return []
    if not isinstance(raw, list):
        return []
    records: list[dict[str, Any]] = []
    for entry in raw:
        normalized = _normalize_record(entry)
        if normalized is not None:
            records.append(normalized)
    return records


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    with NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(payload)
        temp_name = tmp_file.name
    os.replace(temp_name, path)


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _upsert_record(
    records: list[dict[str, Any]],
    record: dict[str, Any],
    max_records: int = _MAX_STORED_RUNS,
) -> list[dict[str, Any]]:
    request_id = record["request_id"]
    filtered = [entry for entry in records if entry.get("request_id") != request_id]
    return [record, *filtered][:max_records]


def _compute_rate(
    records: list[dict[str, Any]],
    predicate: Any,
) -> float:
    if not records:
        return 0.0
    matches = sum(1 for entry in records if predicate(entry))
    return round((matches / len(records)) * 100.0, 1)


def _compute_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    bounded = max(0.0, min(100.0, percentile))
    raw_index = (len(ordered) - 1) * (bounded / 100.0)
    lower = int(raw_index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = raw_index - lower
    value = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(value, 1)


def compute_run_trends(
    records: list[dict[str, Any]],
    *,
    window: int = _DEFAULT_WINDOW,
) -> dict[str, Any] | None:
    if not records:
        return None
    bounded_window = max(1, min(window, len(records)))
    sample = records[:bounded_window]
    first_content_values = [
        float(entry["first_content_ms"])
        for entry in sample
        if isinstance(entry.get("first_content_ms"), (int, float))
    ]
    noise_values = [
        float(entry["token_noise_ratio"])
        for entry in sample
        if isinstance(entry.get("token_noise_ratio"), (int, float))
    ]
    avg_first_content_ms = (
        round(sum(first_content_values) / len(first_content_values), 1)
        if first_content_values
        else None
    )
    avg_noise_ratio = (
        round(sum(noise_values) / len(noise_values), 4) if noise_values else None
    )
    probe_runtime_rate = _compute_rate(
        sample,
        lambda entry: entry.get("probe_source") == "probe_runtime",
    )
    fallback_rate = round(100.0 - probe_runtime_rate, 1)
    first_chunk_p95_ms = _compute_percentile(first_content_values, 95.0)
    return {
        "runs": len(sample),
        "window": bounded_window,
        "runtime_trace_rate": _compute_rate(
            sample,
            lambda entry: entry.get("rag_source") == "runtime_trace",
        ),
        "probe_runtime_rate": probe_runtime_rate,
        "probe_success_rate": probe_runtime_rate,
        "fallback_rate": fallback_rate,
        "high_coverage_rate": _compute_rate(
            sample,
            lambda entry: isinstance(entry.get("coverage_percent"), (int, float))
            and float(entry["coverage_percent"]) >= 70.0,
        ),
        "live_streaming_rate": _compute_rate(
            sample,
            lambda entry: entry.get("stream_quality") == "live_streaming",
        ),
        "avg_first_content_ms": avg_first_content_ms,
        "first_chunk_p95_ms": first_chunk_p95_ms,
        "avg_noise_ratio": avg_noise_ratio,
    }


def evaluate_slo_gate(
    trends: dict[str, Any] | None,
    *,
    min_runs: int = _DEFAULT_WINDOW,
    probe_success_rate_min: float = _DEFAULT_PROBE_SUCCESS_RATE_MIN,
    first_chunk_p95_ms_max: float = _DEFAULT_FIRST_CHUNK_P95_MS_MAX,
    fallback_rate_max: float = _DEFAULT_FALLBACK_RATE_MAX,
) -> dict[str, Any]:
    if not trends:
        return {
            "ok": False,
            "reason": "no_trends",
            "min_runs": min_runs,
            "runs": 0,
            "checks": [],
        }
    runs = int(trends.get("runs") or 0)
    probe_success_raw = trends.get("probe_success_rate")
    fallback_raw = trends.get("fallback_rate")
    probe_success_rate = (
        float(probe_success_raw) if isinstance(probe_success_raw, (int, float)) else 0.0
    )
    fallback_rate = (
        float(fallback_raw) if isinstance(fallback_raw, (int, float)) else 100.0
    )
    first_chunk_p95_ms = trends.get("first_chunk_p95_ms")
    has_min_runs = runs >= min_runs
    probe_ok = probe_success_rate >= probe_success_rate_min
    fallback_ok = fallback_rate <= fallback_rate_max
    p95_ok = (
        isinstance(first_chunk_p95_ms, (int, float))
        and float(first_chunk_p95_ms) <= first_chunk_p95_ms_max
    )
    checks = [
        {
            "id": "min_runs",
            "ok": has_min_runs,
            "actual": runs,
            "expected_min": min_runs,
        },
        {
            "id": "probe_success_rate",
            "ok": probe_ok,
            "actual": probe_success_rate,
            "expected_min": probe_success_rate_min,
        },
        {
            "id": "fallback_rate",
            "ok": fallback_ok,
            "actual": fallback_rate,
            "expected_max": fallback_rate_max,
        },
        {
            "id": "first_chunk_p95_ms",
            "ok": p95_ok,
            "actual": first_chunk_p95_ms,
            "expected_max": first_chunk_p95_ms_max,
        },
    ]
    ok = has_min_runs and probe_ok and fallback_ok and p95_ok
    return {
        "ok": ok,
        "reason": "ok" if ok else "threshold_failed",
        "runs": runs,
        "min_runs": min_runs,
        "probe_success_rate": probe_success_rate,
        "fallback_rate": fallback_rate,
        "first_chunk_p95_ms": first_chunk_p95_ms,
        "checks": checks,
    }


def evaluate_consecutive_slo_windows(
    records: list[dict[str, Any]],
    *,
    window: int = _DEFAULT_WINDOW,
    required_consecutive: int = 3,
    probe_success_rate_min: float = _DEFAULT_PROBE_SUCCESS_RATE_MIN,
    first_chunk_p95_ms_max: float = _DEFAULT_FIRST_CHUNK_P95_MS_MAX,
    fallback_rate_max: float = _DEFAULT_FALLBACK_RATE_MAX,
) -> dict[str, Any]:
    if required_consecutive < 1:
        required_consecutive = 1
    if not records:
        return {
            "ok": False,
            "reason": "no_records",
            "required_consecutive": required_consecutive,
            "passed_consecutive": 0,
            "windows": [],
        }
    windows: list[dict[str, Any]] = []
    passed_consecutive = 0
    max_windows = min(len(records), window + required_consecutive + 8)
    for offset in range(0, max_windows):
        sample = records[offset:]
        trends = compute_run_trends(sample, window=window)
        gate = evaluate_slo_gate(
            trends,
            min_runs=window,
            probe_success_rate_min=probe_success_rate_min,
            first_chunk_p95_ms_max=first_chunk_p95_ms_max,
            fallback_rate_max=fallback_rate_max,
        )
        gate["offset"] = offset
        windows.append(gate)
        if gate["ok"]:
            passed_consecutive += 1
            if passed_consecutive >= required_consecutive:
                break
        else:
            passed_consecutive = 0
    ok = passed_consecutive >= required_consecutive
    return {
        "ok": ok,
        "reason": "ok" if ok else "consecutive_windows_failed",
        "required_consecutive": required_consecutive,
        "passed_consecutive": passed_consecutive,
        "windows": windows,
    }


def evaluate_persisted_slo_windows(
    *,
    settings: Any = None,
    window: int = _DEFAULT_WINDOW,
    required_consecutive: int = 3,
    probe_success_rate_min: float = _DEFAULT_PROBE_SUCCESS_RATE_MIN,
    first_chunk_p95_ms_max: float = _DEFAULT_FIRST_CHUNK_P95_MS_MAX,
    fallback_rate_max: float = _DEFAULT_FALLBACK_RATE_MAX,
) -> dict[str, Any]:
    path = _resolve_storage_path(settings=settings)
    with _STORE_LOCK:
        with _file_lock(path):
            records = _read_records(path)
    return evaluate_consecutive_slo_windows(
        records,
        window=window,
        required_consecutive=required_consecutive,
        probe_success_rate_min=probe_success_rate_min,
        first_chunk_p95_ms_max=first_chunk_p95_ms_max,
        fallback_rate_max=fallback_rate_max,
    )


def record_operator_run(
    *,
    request_id: str,
    rag_source: str,
    probe_source: str,
    stream_quality: str,
    coverage_percent: float | None,
    first_content_ms: float | None,
    token_noise_ratio: float | None,
    settings: Any = None,
) -> dict[str, Any] | None:
    if not request_id.strip():
        return None
    path = _resolve_storage_path(settings=settings)
    record = _normalize_record(
        {
            "request_id": request_id,
            "ts_ms": int(time.time() * 1000),
            "rag_source": rag_source,
            "probe_source": probe_source,
            "stream_quality": stream_quality,
            "coverage_percent": coverage_percent,
            "first_content_ms": first_content_ms,
            "token_noise_ratio": token_noise_ratio,
        }
    )
    if record is None:
        return None
    with _STORE_LOCK:
        with _file_lock(path):
            records = _read_records(path)
            next_records = _upsert_record(records, record)
            try:
                _write_records(path, next_records)
            except OSError:
                logger.warning("Failed to persist operator trends store", exc_info=True)
            return compute_run_trends(next_records)
