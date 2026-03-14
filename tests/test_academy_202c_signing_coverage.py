"""202C coverage: adapter signing, ONNX history branches, route handlers.

Targets the new lines added in PR 202C that were below the 80 % changed-lines
coverage threshold:
- adapter_metadata_service: get/write/ensure chat signature
- adapter_management_service: sign_adapter_for_chat / ensure_adapter_signed_for_chat
- route_handlers: sign_adapter_for_chat_handler + _prepare_adapter_activation signature check
- academy_history.save_adapter_metadata: ONNX conversion plan + auto_sign branches
- academy_training: allow_indirect_onnx_path + build_job_record new fields
- academy.py endpoint: POST /adapters/{adapter_id}/sign
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from tests.helpers.academy_wiring import academy_client
from venom_core.api.routes import academy_history, academy_training
from venom_core.services.academy import (
    adapter_management_service,
    adapter_metadata_service,
    route_handlers,
)
from venom_core.services.academy.adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


class _Logger:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def info(self, *_a: Any, **_kw: Any) -> None:
        pass

    def warning(self, *_a: Any, **_kw: Any) -> None:
        pass

    def error(self, msg: str, *_a: Any, **_kw: Any) -> None:
        self.errors.append(msg)


@dataclass
class _AcademyRouteError(Exception):
    status_code: int
    detail: Any

    def __str__(self) -> str:
        return str(self.detail)


def _build_academy(*, manager: Any = None) -> Any:
    acad = SimpleNamespace()
    acad.logger = _Logger()
    acad.AcademyRouteError = _AcademyRouteError
    acad._to_http_exception = lambda e: HTTPException(
        status_code=e.status_code, detail=e.detail
    )
    acad._ensure_academy_enabled = lambda: None
    acad.require_localhost_request = lambda _req: None
    acad._get_model_manager = lambda: manager
    return acad


# ---------------------------------------------------------------------------
# adapter_metadata_service: get_adapter_chat_signature
# ---------------------------------------------------------------------------


def test_get_signature_returns_none_when_no_metadata(tmp_path: Path) -> None:
    assert (
        adapter_metadata_service.get_adapter_chat_signature(adapter_dir=tmp_path)
        is None
    )


def test_get_signature_returns_none_when_value_is_not_dict(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text(
        json.dumps({"chat_signature": "flat-string"}), encoding="utf-8"
    )
    assert (
        adapter_metadata_service.get_adapter_chat_signature(adapter_dir=tmp_path)
        is None
    )


# ---------------------------------------------------------------------------
# adapter_metadata_service: write_adapter_chat_signature
# ---------------------------------------------------------------------------


def test_write_signature_persists_all_fields(tmp_path: Path) -> None:
    sig = adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="ollama",
        model_id="gemma3:latest",
        signer="academy-ui",
        conversion_mode="none",
    )
    assert sig["signed"] is True
    assert sig["runtime_id"] == "ollama"
    assert sig["model_id"] == "gemma3:latest"
    assert sig["signer"] == "academy-ui"
    # Round-trip read-back
    loaded = adapter_metadata_service.get_adapter_chat_signature(adapter_dir=tmp_path)
    assert loaded is not None
    assert loaded["runtime_id"] == "ollama"


def test_write_signature_defaults_signer_to_system_and_model_to_none(
    tmp_path: Path,
) -> None:
    sig = adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="vllm",
        model_id=None,
        signer=None,
        conversion_mode="merge_export",
    )
    assert sig["signer"] == "system"
    assert sig["model_id"] is None
    assert sig["conversion_mode"] == "merge_export"


# ---------------------------------------------------------------------------
# adapter_metadata_service: ensure_adapter_chat_signature
# ---------------------------------------------------------------------------


def test_ensure_signature_raises_when_not_signed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ADAPTER_NOT_SIGNED_FOR_CHAT"):
        adapter_metadata_service.ensure_adapter_chat_signature(
            adapter_dir=tmp_path,
            runtime_id="ollama",
            model_id=None,
        )


def test_ensure_signature_raises_on_runtime_mismatch(tmp_path: Path) -> None:
    adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="ollama",
        model_id=None,
        signer="ci",
        conversion_mode="none",
    )
    with pytest.raises(ValueError, match="ADAPTER_SIGNATURE_RUNTIME_MISMATCH"):
        adapter_metadata_service.ensure_adapter_chat_signature(
            adapter_dir=tmp_path,
            runtime_id="vllm",
            model_id=None,
        )


def test_ensure_signature_raises_on_model_mismatch(tmp_path: Path) -> None:
    adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="ollama",
        model_id="gemma3:latest",
        signer="ci",
        conversion_mode="none",
    )
    with pytest.raises(ValueError, match="ADAPTER_SIGNATURE_MODEL_MISMATCH"):
        adapter_metadata_service.ensure_adapter_chat_signature(
            adapter_dir=tmp_path,
            runtime_id="ollama",
            model_id="llama3.2:latest",
        )


def test_ensure_signature_returns_on_exact_match(tmp_path: Path) -> None:
    adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="ollama",
        model_id="gemma3:latest",
        signer="ci",
        conversion_mode="none",
    )
    result = adapter_metadata_service.ensure_adapter_chat_signature(
        adapter_dir=tmp_path,
        runtime_id="ollama",
        model_id="gemma3:latest",
    )
    assert result["signed"] is True
    assert result["runtime_id"] == "ollama"


# ---------------------------------------------------------------------------
# adapter_management_service: sign_adapter_for_chat
# ---------------------------------------------------------------------------


def _patch_adapter_dir(
    tmp_path: Path, adapter_id: str, *, create_adapter: bool = False
):
    """
    Return a context-manager pair that patches _runtime_service resolution helpers.
    If create_adapter=True, creates the adapter sub-path so existence checks pass.
    """
    adapter_dir = tmp_path / "adapters" / adapter_id
    if create_adapter:
        (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    else:
        adapter_dir.mkdir(parents=True, exist_ok=True)
    p1 = patch.object(
        adapter_management_service._runtime_service,
        "_resolve_academy_models_dir",
        return_value=tmp_path / "models",
    )
    p2 = patch.object(
        adapter_management_service._runtime_service,
        "_resolve_adapter_dir",
        return_value=adapter_dir,
    )
    return adapter_dir, p1, p2


def test_management_sign_adapter_raises_not_found_when_adapter_missing(
    tmp_path: Path,
) -> None:
    adapter_dir, p1, p2 = _patch_adapter_dir(tmp_path, "a1", create_adapter=False)
    with p1, p2, pytest.raises(FileNotFoundError):
        adapter_management_service.sign_adapter_for_chat(
            mgr=object(),
            adapter_id="a1",
            runtime_id="ollama",
            model_id=None,
            signer=None,
            conversion_mode="none",
            settings_obj=object(),
        )


def test_management_sign_adapter_success(tmp_path: Path) -> None:
    adapter_dir, p1, p2 = _patch_adapter_dir(tmp_path, "a1", create_adapter=True)
    with p1, p2:
        result = adapter_management_service.sign_adapter_for_chat(
            mgr=object(),
            adapter_id="a1",
            runtime_id="ollama",
            model_id="gemma3:latest",
            signer="academy-ui",
            conversion_mode="none",
            settings_obj=object(),
        )
    assert result["success"] is True
    assert result["adapter_id"] == "a1"
    assert result["signature"]["runtime_id"] == "ollama"


# ---------------------------------------------------------------------------
# adapter_management_service: ensure_adapter_signed_for_chat
# ---------------------------------------------------------------------------


def test_management_ensure_signed_raises_not_found_when_adapter_missing(
    tmp_path: Path,
) -> None:
    adapter_dir, p1, p2 = _patch_adapter_dir(tmp_path, "b1", create_adapter=False)
    with p1, p2, pytest.raises(FileNotFoundError):
        adapter_management_service.ensure_adapter_signed_for_chat(
            settings_obj=object(),
            adapter_id="b1",
            runtime_id="ollama",
            model_id=None,
        )


def test_management_ensure_signed_succeeds_when_signature_present(
    tmp_path: Path,
) -> None:
    adapter_dir, p1, p2 = _patch_adapter_dir(tmp_path, "b1", create_adapter=True)
    adapter_metadata_service.write_adapter_chat_signature(
        adapter_dir=adapter_dir,
        runtime_id="ollama",
        model_id=None,
        signer="ci",
        conversion_mode="none",
    )
    with p1, p2:
        result = adapter_management_service.ensure_adapter_signed_for_chat(
            settings_obj=object(),
            adapter_id="b1",
            runtime_id="ollama",
            model_id=None,
        )
    assert result["signed"] is True


# ---------------------------------------------------------------------------
# route_handlers: sign_adapter_for_chat_handler
# ---------------------------------------------------------------------------


def test_sign_handler_success() -> None:
    manager = object()
    academy = _build_academy(manager=manager)
    expected = {
        "success": True,
        "adapter_id": "a1",
        "signature": {"runtime_id": "ollama"},
    }
    academy.academy_models = SimpleNamespace(
        sign_adapter_for_chat=Mock(return_value=expected)
    )
    result = route_handlers.sign_adapter_for_chat_handler(
        adapter_id="a1",
        request=SimpleNamespace(
            runtime_id="ollama",
            model_id="gemma3:latest",
            signer="ci",
            conversion_mode="none",
        ),
        req=SimpleNamespace(),
        academy=academy,
    )
    assert result == expected


def test_sign_handler_no_manager_raises_503() -> None:
    academy = _build_academy(manager=None)
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="a1",
            request=SimpleNamespace(runtime_id="ollama"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 503


def test_sign_handler_empty_runtime_raises_400() -> None:
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(sign_adapter_for_chat=Mock())
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="a1",
            request=SimpleNamespace(
                runtime_id="", model_id=None, signer=None, conversion_mode="none"
            ),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["reason_code"] == "ADAPTER_SIGNATURE_RUNTIME_REQUIRED"


def test_sign_handler_file_not_found_exact_message_raises_404() -> None:
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(
        sign_adapter_for_chat=Mock(
            side_effect=FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)
        )
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="missing",
            request=SimpleNamespace(
                runtime_id="ollama", model_id=None, signer=None, conversion_mode="none"
            ),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == ADAPTER_NOT_FOUND_DETAIL


def test_sign_handler_file_not_found_other_message_raises_500() -> None:
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(
        sign_adapter_for_chat=Mock(side_effect=FileNotFoundError("/nonexistent/path"))
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="a1",
            request=SimpleNamespace(
                runtime_id="ollama", model_id=None, signer=None, conversion_mode="none"
            ),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 500


def test_sign_handler_generic_exception_raises_500() -> None:
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(
        sign_adapter_for_chat=Mock(side_effect=RuntimeError("db exploded"))
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="a1",
            request=SimpleNamespace(
                runtime_id="ollama", model_id=None, signer=None, conversion_mode="none"
            ),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 500
    assert exc.value.detail["reason_code"] == "ADAPTER_SIGNATURE_FAILED"
    assert academy.logger.errors  # error was logged


def test_sign_handler_academy_route_error_re_raised_as_http() -> None:
    err = _AcademyRouteError(status_code=503, detail="academy offline")
    academy = _build_academy(manager=object())
    academy._ensure_academy_enabled = lambda: (_ for _ in ()).throw(err)
    with pytest.raises(HTTPException) as exc:
        route_handlers.sign_adapter_for_chat_handler(
            adapter_id="a1",
            request=SimpleNamespace(runtime_id="ollama"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# route_handlers: _prepare_adapter_activation – require_chat_signature branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_activation_calls_ensure_signed_when_required() -> None:
    ensure_mock = Mock()
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=AsyncMock(return_value=None),
        ensure_adapter_signed_for_chat=ensure_mock,
    )
    request = SimpleNamespace(
        adapter_id="a1",
        adapter_path="/tmp/a1",
        runtime_id="ollama",
        model_id="gemma3:latest",
        deploy_to_chat_runtime=True,
        require_chat_signature=True,
    )
    await route_handlers._prepare_adapter_activation(
        academy=academy,
        manager=object(),
        request=request,
        requested_runtime_id="ollama",
    )
    ensure_mock.assert_called_once_with(
        adapter_id="a1",
        runtime_id="ollama",
        model_id="gemma3:latest",
    )


@pytest.mark.asyncio
async def test_prepare_activation_skips_ensure_when_not_required() -> None:
    ensure_mock = Mock()
    academy = _build_academy(manager=object())
    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=AsyncMock(return_value=None),
        ensure_adapter_signed_for_chat=ensure_mock,
    )
    request = SimpleNamespace(
        adapter_id="a1",
        adapter_path="/tmp/a1",
        runtime_id="ollama",
        model_id="gemma3:latest",
        deploy_to_chat_runtime=True,
        require_chat_signature=False,
    )
    await route_handlers._prepare_adapter_activation(
        academy=academy,
        manager=object(),
        request=request,
        requested_runtime_id="ollama",
    )
    ensure_mock.assert_not_called()


# ---------------------------------------------------------------------------
# academy_history: ONNX conversion plan + auto_sign branches
# ---------------------------------------------------------------------------


def test_save_adapter_metadata_writes_onnx_conversion_plan(tmp_path: Path) -> None:
    adapter_path = tmp_path / "job-onnx" / "adapter"
    adapter_path.parent.mkdir(parents=True)
    adapter_path.write_text("weights", encoding="utf-8")
    job = {
        "job_id": "job-onnx",
        "base_model": "gemma-3-4b-it",
        "parameters": {
            "runtime_id": "vllm",
            "onnx_conversion_mode": "merge_export",
        },
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:10:00",
    }
    academy_history.save_adapter_metadata(job, adapter_path)
    metadata = json.loads(
        (adapter_path.parent / "metadata.json").read_text(encoding="utf-8")
    )
    plan = metadata.get("onnx_conversion_plan", {})
    assert plan.get("mode") == "merge_export"
    assert plan.get("status") == "planned"
    assert plan.get("target_runtime") == "onnx"


def test_save_adapter_metadata_auto_sign_writes_chat_signature(
    tmp_path: Path,
) -> None:
    adapter_path = tmp_path / "job-signed" / "adapter"
    adapter_path.parent.mkdir(parents=True)
    adapter_path.write_text("weights", encoding="utf-8")
    job = {
        "job_id": "job-signed",
        "base_model": "gemma-3-4b-it",
        "parameters": {
            "runtime_id": "vllm",
            "auto_sign_for_chat": True,
            "chat_signer": "ci-runner",
            "chat_target_model_id": "gemma3:latest",
        },
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:10:00",
    }
    academy_history.save_adapter_metadata(job, adapter_path)
    metadata = json.loads(
        (adapter_path.parent / "metadata.json").read_text(encoding="utf-8")
    )
    sig = metadata.get("chat_signature", {})
    assert sig.get("signed") is True
    assert sig.get("signer") == "ci-runner"
    assert sig.get("runtime_id") == "vllm"


# ---------------------------------------------------------------------------
# academy_training: allow_indirect_onnx_path + build_job_record new fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_runtime_allows_onnx_with_indirect_path_set() -> None:
    # Must not raise; ONNX is accepted when indirect path is allowed
    await academy_training.validate_runtime_compatibility_for_base_model(
        base_model="gemma-3-4b-it",
        runtime_id="onnx",
        allow_indirect_onnx_path=True,
    )


def test_build_job_record_includes_onnx_and_sign_fields(tmp_path: Path) -> None:
    from venom_core.api.routes.academy_training import build_job_record

    request = SimpleNamespace(
        runtime_id="vllm",
        onnx_conversion_mode="merge_export",
        auto_sign_for_chat=True,
        chat_signer="ci",
        chat_target_model_id="gemma3:latest",
        lora_rank=8,
        learning_rate=0.0002,
        num_epochs=2,
        batch_size=1,
        max_seq_length=1024,
    )
    record = build_job_record(
        dataset_path="/tmp/ds.jsonl",
        base_model="gemma-3-4b-it",
        output_dir=tmp_path / "output",
        request=request,
    )
    params = record["parameters"]
    assert params["onnx_conversion_mode"] == "merge_export"
    assert params["auto_sign_for_chat"] is True
    assert params["chat_signer"] == "ci"
    assert params["chat_target_model_id"] == "gemma3:latest"


# ---------------------------------------------------------------------------
# API endpoint: POST /adapters/{adapter_id}/sign
# ---------------------------------------------------------------------------


@patch("venom_core.config.SETTINGS")
def test_sign_adapter_endpoint_returns_200_on_success(
    mock_settings: Any, tmp_path: Path
) -> None:
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "models")
    with academy_client() as client:
        with patch(
            "venom_core.api.routes.academy.academy_route_handlers"
            ".sign_adapter_for_chat_handler",
            return_value={
                "success": True,
                "adapter_id": "a1",
                "signature": {"runtime_id": "ollama", "signed": True},
            },
        ):
            response = client.post(
                "/api/v1/academy/adapters/a1/sign",
                json={"runtime_id": "ollama", "model_id": "gemma3:latest"},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["adapter_id"] == "a1"


@patch("venom_core.config.SETTINGS")
def test_sign_adapter_endpoint_returns_422_when_runtime_id_missing(
    mock_settings: Any,
) -> None:
    mock_settings.ENABLE_ACADEMY = True
    with academy_client() as client:
        response = client.post(
            "/api/v1/academy/adapters/a1/sign",
            json={},  # runtime_id is required by AdapterChatSignRequest
        )
    assert response.status_code == 422
