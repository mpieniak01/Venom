"""Tests for persistent operator run trends service."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services import model_introspection_operator_trends_service as service


def test_record_operator_run_persists_and_computes_trends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "operator_run_trends.json"
    monkeypatch.setattr(
        service, "_resolve_storage_path", lambda settings=None: store_path
    )

    first = service.record_operator_run(
        request_id="req-1",
        rag_source="runtime_trace",
        probe_source="probe_runtime",
        stream_quality="live_streaming",
        coverage_percent=88.4,
        first_content_ms=120.0,
        token_noise_ratio=0.22,
    )
    second = service.record_operator_run(
        request_id="req-2",
        rag_source="graph_fallback",
        probe_source="probe_unavailable",
        stream_quality="single_chunk_delayed",
        coverage_percent=45.0,
        first_content_ms=2100.0,
        token_noise_ratio=0.81,
    )

    assert first is not None
    assert second is not None
    assert second["runs"] == 2
    assert second["runtime_trace_rate"] == 50.0
    assert second["probe_runtime_rate"] == 50.0
    assert second["probe_success_rate"] == 50.0
    assert second["fallback_rate"] == 50.0
    assert second["high_coverage_rate"] == 50.0
    assert second["live_streaming_rate"] == 50.0
    assert second["avg_first_content_ms"] == 1110.0
    assert second["first_chunk_p95_ms"] == 2001.0
    assert second["avg_noise_ratio"] == 0.515
    assert store_path.exists()


def test_record_operator_run_upserts_by_request_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "operator_run_trends.json"
    monkeypatch.setattr(
        service, "_resolve_storage_path", lambda settings=None: store_path
    )

    service.record_operator_run(
        request_id="req-1",
        rag_source="graph_fallback",
        probe_source="probe_unavailable",
        stream_quality="single_chunk_delayed",
        coverage_percent=10.0,
        first_content_ms=800.0,
        token_noise_ratio=0.91,
    )
    trends = service.record_operator_run(
        request_id="req-1",
        rag_source="runtime_trace",
        probe_source="probe_runtime",
        stream_quality="live_streaming",
        coverage_percent=95.0,
        first_content_ms=90.0,
        token_noise_ratio=0.11,
    )

    assert trends is not None
    assert trends["runs"] == 1
    assert trends["runtime_trace_rate"] == 100.0
    assert trends["probe_runtime_rate"] == 100.0
    assert trends["probe_success_rate"] == 100.0
    assert trends["fallback_rate"] == 0.0
    assert trends["high_coverage_rate"] == 100.0
    assert trends["avg_first_content_ms"] == 90.0


def test_trends_helpers_handle_invalid_store_payload(
    monkeypatch, tmp_path: Path
) -> None:
    store_path = tmp_path / "operator_run_trends.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        service, "_resolve_storage_path", lambda settings=None: store_path
    )

    trends = service.record_operator_run(
        request_id="req-x",
        rag_source="graph_fallback",
        probe_source="probe_unavailable",
        stream_quality="single_chunk",
        coverage_percent=None,
        first_content_ms=None,
        token_noise_ratio=None,
    )
    assert trends is not None
    assert trends["runs"] == 1
    assert trends["avg_first_content_ms"] is None
    assert trends["first_chunk_p95_ms"] is None


def test_record_operator_run_rejects_empty_request_id() -> None:
    assert (
        service.record_operator_run(
            request_id="   ",
            rag_source="graph_fallback",
            probe_source="probe_unavailable",
            stream_quality="single_chunk",
            coverage_percent=None,
            first_content_ms=None,
            token_noise_ratio=None,
        )
        is None
    )


def test_resolve_storage_path_uses_closed_namespace_for_untrusted_prefix() -> None:
    cfg = SimpleNamespace(STORAGE_PREFIX="../../etc/passwd", ENVIRONMENT_ROLE="dev")
    path = service._resolve_storage_path(settings=cfg)  # noqa: SLF001
    assert path.parent.name == "dev"
    assert str(path).endswith("/data/introspection/dev/operator_run_trends.json")


def test_evaluate_slo_gate_passes_when_thresholds_met() -> None:
    trends = {
        "runs": 20,
        "probe_success_rate": 95.0,
        "fallback_rate": 5.0,
        "first_chunk_p95_ms": 1800.0,
    }
    gate = service.evaluate_slo_gate(trends, min_runs=20)
    assert gate["ok"] is True
    assert gate["reason"] == "ok"


def test_evaluate_slo_gate_fails_when_thresholds_not_met() -> None:
    trends = {
        "runs": 20,
        "probe_success_rate": 70.0,
        "fallback_rate": 30.0,
        "first_chunk_p95_ms": 3200.0,
    }
    gate = service.evaluate_slo_gate(trends, min_runs=20)
    assert gate["ok"] is False
    assert gate["reason"] == "threshold_failed"
    failed_checks = [check for check in gate["checks"] if not check["ok"]]
    assert len(failed_checks) >= 3


def test_evaluate_consecutive_slo_windows_passes_for_three_windows() -> None:
    records = []
    for index in range(70):
        records.append(
            {
                "request_id": f"req-{index}",
                "ts_ms": 1000 + index,
                "rag_source": "runtime_trace",
                "probe_source": "probe_runtime",
                "stream_quality": "live_streaming",
                "coverage_percent": 90.0,
                "first_content_ms": 1200.0,
                "token_noise_ratio": 0.2,
            }
        )
    result = service.evaluate_consecutive_slo_windows(
        records,
        window=20,
        required_consecutive=3,
    )
    assert result["ok"] is True
    assert result["passed_consecutive"] >= 3


def test_evaluate_consecutive_slo_windows_fails_when_probe_low() -> None:
    records = []
    for index in range(70):
        records.append(
            {
                "request_id": f"req-{index}",
                "ts_ms": 1000 + index,
                "rag_source": "runtime_trace",
                "probe_source": "probe_unavailable",
                "stream_quality": "live_streaming",
                "coverage_percent": 90.0,
                "first_content_ms": 1200.0,
                "token_noise_ratio": 0.2,
            }
        )
    result = service.evaluate_consecutive_slo_windows(
        records,
        window=20,
        required_consecutive=3,
    )
    assert result["ok"] is False
    assert result["reason"] == "consecutive_windows_failed"


def test_record_operator_run_computes_deep_metrics_trends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "operator_run_trends.json"
    monkeypatch.setattr(
        service, "_resolve_storage_path", lambda settings=None: store_path
    )

    trends = service.record_operator_run(
        request_id="req-1",
        rag_source="runtime_trace",
        probe_source="probe_runtime",
        stream_quality="live_streaming",
        coverage_percent=88.4,
        first_content_ms=120.0,
        token_noise_ratio=0.22,
        mlp_l2=1.5,
        cosine_similarity=0.95,
    )
    assert trends is not None
    assert trends["avg_mlp_l2"] == 1.5
    assert trends["avg_cosine_similarity"] == 0.95

    trends2 = service.record_operator_run(
        request_id="req-2",
        rag_source="runtime_trace",
        probe_source="probe_runtime",
        stream_quality="live_streaming",
        coverage_percent=88.4,
        first_content_ms=120.0,
        token_noise_ratio=0.22,
        mlp_l2=2.5,
        cosine_similarity=0.85,
    )
    assert trends2 is not None
    assert trends2["avg_mlp_l2"] == 2.0
    assert trends2["avg_cosine_similarity"] == 0.90


def test_record_operator_run_ttl_retention_and_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import time

    store_path = tmp_path / "operator_run_trends.json"
    monkeypatch.setattr(
        service, "_resolve_storage_path", lambda settings=None: store_path
    )

    # 1. Test limit 200 records
    for i in range(210):
        service.record_operator_run(
            request_id=f"req-limit-{i}",
            rag_source="runtime_trace",
            probe_source="probe_runtime",
            stream_quality="live_streaming",
            coverage_percent=88.4,
            first_content_ms=120.0,
            token_noise_ratio=0.22,
        )

    records = service.get_operator_run_records()
    assert len(records) == 200

    # 2. Test TTL retention (30 days)
    old_ts_ms = int(time.time() * 1000) - (31 * 24 * 60 * 60 * 1000)
    old_record = {
        "request_id": "old-req",
        "ts_ms": old_ts_ms,
        "rag_source": "runtime_trace",
        "probe_source": "probe_runtime",
        "stream_quality": "live_streaming",
        "coverage_percent": 88.4,
        "first_content_ms": 120.0,
        "token_noise_ratio": 0.22,
    }
    # write to file directly first
    service._write_records(store_path, [old_record])

    # now insert a new record, which should trigger upsert and filter out the old one
    service.record_operator_run(
        request_id="new-req",
        rag_source="runtime_trace",
        probe_source="probe_runtime",
        stream_quality="live_streaming",
        coverage_percent=88.4,
        first_content_ms=120.0,
        token_noise_ratio=0.22,
    )
    records = service.get_operator_run_records()
    assert len(records) == 1
    assert records[0]["request_id"] == "new-req"


def test_is_finite_float_nan_inf() -> None:
    assert service._is_finite_float(1.5) is True
    assert service._is_finite_float(True) is False
    assert service._is_finite_float(False) is False
    assert service._is_finite_float(float("nan")) is False
    assert service._is_finite_float(float("inf")) is False
    assert service._is_finite_float(float("-inf")) is False
    assert service._is_finite_float("not a float") is False


def test_upsert_record_keeps_descending_ts_order() -> None:
    import time

    now_ms = int(time.time() * 1000)
    records = [
        {"request_id": "old-a", "ts_ms": now_ms - 3000},
        {"request_id": "old-b", "ts_ms": now_ms - 1000},
    ]
    record = {"request_id": "new", "ts_ms": now_ms - 2000}
    result = service._upsert_record(records, record, max_records=10)
    assert [entry["request_id"] for entry in result] == ["old-b", "new", "old-a"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        "12.5",
        {},
        [],
        float("nan"),
        float("inf"),
        -float("inf"),
        10**400,
    ],
)
def test_normalize_record_rejects_nonfinite_or_unrepresentable_metrics(
    monkeypatch, value
):
    monkeypatch.setattr(service.time, "time", lambda: 123.0)
    fields = [
        "coverage_percent",
        "first_content_ms",
        "token_noise_ratio",
        "mlp_l2",
        "residual_l2",
        "delta_l2",
        "cosine_similarity",
    ]
    record = service._normalize_record(
        {
            "request_id": "malformed-metrics",
            "ts_ms": value,
            **dict.fromkeys(fields, value),
        }
    )
    assert record is not None
    assert record["ts_ms"] == 123000
    assert all(record[field] is None for field in fields)


@pytest.mark.parametrize("value", [0, 12, -3, 0.25])
def test_normalize_record_preserves_finite_numeric_metrics(value):
    record = service._normalize_record(
        {
            "request_id": "valid-metrics",
            "ts_ms": 321000,
            "coverage_percent": value,
            "mlp_l2": value,
        }
    )
    assert record is not None
    assert record["ts_ms"] == 321000
    assert record["coverage_percent"] == float(value)
    assert record["mlp_l2"] == float(value)


@pytest.mark.parametrize(
    "invalid", [True, float("nan"), float("inf"), float("-inf"), 10**400]
)
def test_direct_trends_reject_invalid_metrics_without_normalization(invalid):
    from venom_core.services.model_introspection_operator_trends_service import (
        compute_run_trends,
    )

    keys = [
        "first_content_ms",
        "token_noise_ratio",
        "mlp_l2",
        "cosine_similarity",
        "coverage_percent",
    ]
    valid = dict.fromkeys(keys, 1.0)
    valid["coverage_percent"] = 80.0
    result = compute_run_trends([valid, dict.fromkeys(keys, invalid)])
    assert result["avg_first_content_ms"] == 1.0
    assert result["avg_noise_ratio"] == 1.0
    assert result["avg_mlp_l2"] == 1.0
    assert result["avg_cosine_similarity"] == 1.0
    assert result["high_coverage_rate"] == 50.0
