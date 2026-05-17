from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from venom_core.services import runtime_switch_telemetry as telemetry


def test_normalize_runtime_switch_source_defaults_to_ui() -> None:
    assert telemetry.normalize_runtime_switch_source(None) == "ui"
    assert telemetry.normalize_runtime_switch_source("   ") == "ui"
    assert telemetry.normalize_runtime_switch_source(" Make_Start ") == "make_start"


def test_assert_runtime_switch_source_allowed_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        telemetry.assert_runtime_switch_source_allowed("manual_shell")
    assert exc.value.status_code == 403


def test_assert_runtime_switch_ownership_token_paths(monkeypatch) -> None:
    telemetry._missing_runtime_switch_token_warned = False  # noqa: SLF001
    monkeypatch.setenv("VENOM_RUNTIME_SWITCH_TOKEN", "")
    telemetry.assert_runtime_switch_ownership_token("anything")

    monkeypatch.setenv("VENOM_RUNTIME_SWITCH_TOKEN", "token-123")
    telemetry.assert_runtime_switch_ownership_token("token-123")

    with pytest.raises(HTTPException) as exc:
        telemetry.assert_runtime_switch_ownership_token("wrong")
    assert exc.value.status_code == 403


def test_assert_runtime_switch_ownership_token_warns_once_when_disabled(
    monkeypatch,
) -> None:
    warnings: list[str] = []
    telemetry._missing_runtime_switch_token_warned = False  # noqa: SLF001
    monkeypatch.setenv("VENOM_RUNTIME_SWITCH_TOKEN", "")
    monkeypatch.setattr(
        telemetry.logger, "warning", lambda message: warnings.append(message)
    )

    telemetry.assert_runtime_switch_ownership_token("ignored")
    telemetry.assert_runtime_switch_ownership_token("ignored")

    assert len(warnings) == 1
    assert "ownership checks are disabled" in warnings[0]


def test_emit_runtime_model_event_uses_collector(monkeypatch) -> None:
    collector = Mock()
    monkeypatch.setattr(
        telemetry.metrics_module, "get_metrics_collector", lambda: collector
    )

    telemetry.emit_runtime_model_event(
        "runtime_model_selected",
        source="ui",
        runtime="vllm",
    )

    collector.record_runtime_switch_event.assert_called_once_with(
        event_name="runtime_model_selected",
        source="ui",
        runtime="vllm",
    )


def test_emit_runtime_model_event_without_collector(monkeypatch) -> None:
    monkeypatch.setattr(telemetry.metrics_module, "get_metrics_collector", lambda: None)
    telemetry.emit_runtime_model_event(
        "runtime_model_selected",
        source="ui",
        runtime="vllm",
    )
