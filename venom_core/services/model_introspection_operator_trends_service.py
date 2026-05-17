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
    return {
        "runs": len(sample),
        "window": bounded_window,
        "runtime_trace_rate": _compute_rate(
            sample,
            lambda entry: entry.get("rag_source") == "runtime_trace",
        ),
        "probe_runtime_rate": _compute_rate(
            sample,
            lambda entry: entry.get("probe_source") == "probe_runtime",
        ),
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
        "avg_noise_ratio": avg_noise_ratio,
    }


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
