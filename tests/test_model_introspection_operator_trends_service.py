"""Tests for persistent operator run trends service."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
