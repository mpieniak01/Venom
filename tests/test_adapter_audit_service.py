from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services.academy import adapter_audit_service as svc
from venom_core.services.academy.adapter_metadata_service import (
    ADAPTER_METADATA_INCONSISTENT,
)


def test_adapter_audit_helpers_payload_and_active_resolution() -> None:
    payload = svc._empty_adapters_audit_payload()
    assert payload["count"] == 0
    assert payload["summary"]["compatible"] == 0

    assert svc._resolve_active_adapter_id(None) == ""
    assert (
        svc._resolve_active_adapter_id(
            SimpleNamespace(get_active_adapter_info=lambda: "x")
        )
        == ""
    )
    mgr = SimpleNamespace(get_active_adapter_info=lambda: {"adapter_id": "adapter-1"})
    assert svc._resolve_active_adapter_id(mgr) == "adapter-1"


def test_evaluate_adapter_audit_status_branches() -> None:
    category, reason, message = svc._evaluate_adapter_audit_status(
        assessment={
            "trusted": False,
            "reason_code": ADAPTER_METADATA_INCONSISTENT,
            "reason": "bad",
        },
        base_model="m",
        runtime_local_id=None,
        selected_model="",
        selected_model_canonical="",
    )
    assert category == "blocked_mismatch"
    assert reason == ADAPTER_METADATA_INCONSISTENT
    assert "bad" in message

    category, reason, _ = svc._evaluate_adapter_audit_status(
        assessment={"trusted": True},
        base_model="base-model",
        runtime_local_id="ollama",
        selected_model="other-model",
        selected_model_canonical="other-model",
    )
    assert category == "blocked_mismatch"
    assert reason is not None

    category, reason, _ = svc._evaluate_adapter_audit_status(
        assessment={"trusted": True},
        base_model="google/gemma-3-4b-it",
        runtime_local_id="onnx",
        selected_model="gemma-3-4b-it-onnx-build-test",
        selected_model_canonical="gemma-3-4b-it",
    )
    assert category == "compatible"
    assert reason is None


def test_build_adapter_audit_item_populates_expected_fields(tmp_path: Path) -> None:
    training_dir = tmp_path / "adapter-1"
    adapter_path = training_dir / "adapter"
    item = svc._build_adapter_audit_item(
        training_dir=training_dir,
        adapter_path=adapter_path,
        assessment={
            "canonical_base_model": "base",
            "trusted": False,
            "sources": ["metadata"],
        },
        base_model="base",
        category="blocked_unknown_base",
        reason_code="X",
        message="msg",
        active_adapter_id="adapter-1",
    )
    assert item["adapter_id"] == "adapter-1"
    assert item["is_active"] is True
    assert item["manual_repair_hint"] is not None


@pytest.mark.asyncio
async def test_validate_adapter_runtime_compatibility_short_circuit_cases(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path))
    mgr = object()

    # Empty runtime id -> no-op.
    await svc.validate_adapter_runtime_compatibility(
        mgr=mgr,
        adapter_id="a1",
        runtime_id="",
        settings_obj=settings,
    )

    # Unsupported runtime id -> explicit error.
    with pytest.raises(ValueError, match="local runtimes"):
        await svc.validate_adapter_runtime_compatibility(
            mgr=mgr,
            adapter_id="a1",
            runtime_id="cloud",
            settings_obj=settings,
        )


def test_audit_adapters_returns_empty_payload_when_models_dir_missing(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "missing"))
    payload = svc.audit_adapters(mgr=None, settings_obj=settings)
    assert payload["count"] == 0
    assert payload["adapters"] == []
