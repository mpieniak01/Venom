from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from venom_core.api.schemas.academy import DatasetScopeRequest
from venom_core.services.academy import route_handlers


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.infos: list[str] = []

    def info(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.infos.append(msg % args if args else msg)

    def warning(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.warnings.append(msg % args if args else msg)

    def error(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.errors.append(msg % args if args else msg)


@dataclass
class _AcademyRouteError(Exception):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


def _build_academy_base() -> Any:
    logger = _Logger()
    academy = SimpleNamespace()
    academy.logger = logger
    academy.AcademyRouteError = _AcademyRouteError
    academy._to_http_exception = lambda e: HTTPException(
        status_code=e.status_code, detail=e.detail
    )
    academy._ensure_academy_enabled = lambda: None
    return academy


def test_collect_scope_counts_only_enabled_parts() -> None:
    curator = SimpleNamespace(
        collect_from_lessons=lambda limit: limit // 2,
        collect_from_git_history=lambda max_commits: max_commits // 10,
        collect_from_task_history=lambda max_tasks: max_tasks // 20,
    )
    req = DatasetScopeRequest(
        include_lessons=True,
        include_git=False,
        include_task_history=True,
        lessons_limit=12,
    )
    counts = route_handlers._collect_scope_counts(curator=curator, request=req)
    assert counts == {"lessons": 6, "git": 0, "task_history": 5}


def test_value_error_detail_with_reason_code_includes_context() -> None:
    detail = route_handlers._value_error_detail_with_reason_code(
        ValueError("MODEL_RUNTIME_REQUIRED: Select runtime first"),
        requested_runtime_id="ollama",
        requested_model_id="",
    )

    assert detail == {
        "error": "MODEL_RUNTIME_REQUIRED",
        "message": "Select runtime first",
        "reason_code": "MODEL_RUNTIME_REQUIRED",
        "requested_runtime_id": "ollama",
    }


def test_error_detail_with_reason_code_ignores_blank_context() -> None:
    detail = route_handlers._error_detail_with_reason_code(
        reason_code="TEST_ERROR",
        message="boom",
        adapter_id="a1",
        requested_runtime_id=" ",
    )

    assert detail == {
        "error": "TEST_ERROR",
        "message": "boom",
        "reason_code": "TEST_ERROR",
        "adapter_id": "a1",
    }


def test_resolve_activation_runtime_id_prefers_explicit_runtime() -> None:
    request = SimpleNamespace(runtime_id=" Ollama ", deploy_to_chat_runtime=True)

    assert route_handlers._resolve_activation_runtime_id(request=request) == "Ollama"


def test_resolve_activation_runtime_id_returns_empty_when_deploy_enabled_without_runtime() -> (
    None
):
    request = SimpleNamespace(runtime_id="", deploy_to_chat_runtime=True)

    assert route_handlers._resolve_activation_runtime_id(request=request) == ""


def test_resolve_activation_runtime_id_falls_back_to_active_runtime_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = SimpleNamespace(runtime_id="", deploy_to_chat_runtime=False)
    monkeypatch.setattr(
        route_handlers,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(provider="vllm"),
    )

    assert route_handlers._resolve_activation_runtime_id(request=request) == "vllm"


def test_list_adapters_handler_maps_generic_error_to_http_500() -> None:
    academy = _build_academy_base()
    academy._get_model_manager = lambda: object()
    academy.academy_models = SimpleNamespace(
        list_adapters=Mock(side_effect=RuntimeError("boom"))
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.list_adapters_handler(academy=academy)
    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "ADAPTERS_LIST_FAILED",
        "message": "Failed to list adapters: boom",
        "reason_code": "ADAPTERS_LIST_FAILED",
    }


@pytest.mark.asyncio
async def test_audit_adapters_handler_returns_payload() -> None:
    academy = _build_academy_base()
    manager = object()
    academy._get_model_manager = lambda: manager
    audit_payload = {
        "count": 1,
        "adapters": [
            {
                "adapter_id": "a1",
                "category": "blocked_unknown_base",
            }
        ],
        "summary": {
            "compatible": 0,
            "blocked_unknown_base": 1,
            "blocked_mismatch": 0,
        },
    }
    academy.academy_models = SimpleNamespace(
        audit_adapters=Mock(return_value=audit_payload),
    )

    payload = route_handlers.audit_adapters_handler(
        academy=academy,
        runtime_id="ollama",
        model_id="gemma-3-4b-it",
    )

    assert payload == audit_payload


def test_audit_adapters_handler_maps_generic_error_to_structured_http_500() -> None:
    academy = _build_academy_base()
    academy._get_model_manager = lambda: object()
    academy.academy_models = SimpleNamespace(
        audit_adapters=Mock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(HTTPException) as exc:
        route_handlers.audit_adapters_handler(
            academy=academy,
            runtime_id="ollama",
            model_id="gemma3:latest",
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "ADAPTERS_AUDIT_FAILED",
        "message": "Failed to audit adapters: boom",
        "reason_code": "ADAPTERS_AUDIT_FAILED",
        "requested_runtime_id": "ollama",
        "requested_model_id": "gemma3:latest",
    }


def test_raise_adapter_activation_http_exception_maps_academy_route_error() -> None:
    academy = _build_academy_base()

    with pytest.raises(HTTPException) as exc:
        route_handlers._raise_adapter_activation_http_exception(
            academy=academy,
            exc=_AcademyRouteError(status_code=409, detail="route error"),
            adapter_id="a1",
            requested_runtime_id="ollama",
            requested_model_id="gemma3:latest",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "route error"


def test_raise_adapter_activation_http_exception_maps_runtime_error() -> None:
    academy = _build_academy_base()

    with pytest.raises(HTTPException) as exc:
        route_handlers._raise_adapter_activation_http_exception(
            academy=academy,
            exc=RuntimeError("boom"),
            adapter_id="a1",
            requested_runtime_id="ollama",
            requested_model_id="gemma3:latest",
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "adapter_id": "a1",
        "error": "ADAPTER_ACTIVATION_FAILED",
        "message": "boom",
        "reason_code": "ADAPTER_ACTIVATION_FAILED",
        "requested_model_id": "gemma3:latest",
        "requested_runtime_id": "ollama",
    }


def test_raise_adapter_activation_http_exception_maps_runtime_unavailable_to_http_503() -> (
    None
):
    academy = _build_academy_base()

    with pytest.raises(HTTPException) as exc:
        route_handlers._raise_adapter_activation_http_exception(
            academy=academy,
            exc=RuntimeError(
                "ADAPTER_RUNTIME_SERVICE_UNAVAILABLE: Ollama runtime is offline"
            ),
            adapter_id="a1",
            requested_runtime_id="ollama",
            requested_model_id="gemma3:latest",
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == {
        "adapter_id": "a1",
        "error": "ADAPTER_RUNTIME_SERVICE_UNAVAILABLE",
        "message": "Ollama runtime is offline",
        "reason_code": "ADAPTER_RUNTIME_SERVICE_UNAVAILABLE",
        "requested_model_id": "gemma3:latest",
        "requested_runtime_id": "ollama",
    }


def test_raise_adapter_activation_http_exception_maps_generic_error() -> None:
    academy = _build_academy_base()

    with pytest.raises(HTTPException) as exc:
        route_handlers._raise_adapter_activation_http_exception(
            academy=academy,
            exc=Exception("boom"),
            adapter_id="a1",
            requested_runtime_id="ollama",
            requested_model_id="gemma3:latest",
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "adapter_id": "a1",
        "error": "ADAPTER_ACTIVATION_FAILED",
        "message": "Failed to activate adapter: boom",
        "reason_code": "ADAPTER_ACTIVATION_FAILED",
        "requested_model_id": "gemma3:latest",
        "requested_runtime_id": "ollama",
    }
    assert academy.logger.errors == ["Failed to activate adapter: boom"]


@pytest.mark.asyncio
async def test_activate_adapter_handler_returns_503_when_manager_missing() -> None:
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    academy._get_model_manager = lambda: None
    academy.academy_models = SimpleNamespace()
    with pytest.raises(HTTPException) as exc:
        await route_handlers.activate_adapter_handler(
            request=SimpleNamespace(adapter_id="a1"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_activate_adapter_handler_passes_model_id_to_compatibility_validation() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager
    validate_mock = AsyncMock(return_value=None)

    def activate_mock(**_kwargs: Any) -> dict[str, bool]:
        return {"success": True}

    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=validate_mock,
        activate_adapter=activate_mock,
    )

    await route_handlers.activate_adapter_handler(
        request=SimpleNamespace(
            adapter_id="a1",
            runtime_id="vllm",
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            deploy_to_chat_runtime=False,
        ),
        req=SimpleNamespace(),
        academy=academy,
    )

    validate_mock.assert_awaited_once_with(
        mgr=manager,
        adapter_id="a1",
        runtime_id="vllm",
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
    )


@pytest.mark.asyncio
async def test_activate_adapter_handler_maps_reason_code_value_error_to_http_400() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager

    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=AsyncMock(return_value=None),
        activate_adapter=lambda **_kwargs: (_ for _ in ()).throw(
            ValueError(
                "ADAPTER_BASE_MODEL_MISMATCH: Adapter base model does not match selected runtime model"
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.activate_adapter_handler(
            request=SimpleNamespace(
                adapter_id="a1",
                runtime_id="ollama",
                model_id="gemma-3-4b-it",
                deploy_to_chat_runtime=True,
            ),
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == {
        "adapter_id": "a1",
        "error": "ADAPTER_BASE_MODEL_MISMATCH",
        "message": "Adapter base model does not match selected runtime model",
        "requested_model_id": "gemma-3-4b-it",
        "requested_runtime_id": "ollama",
        "reason_code": "ADAPTER_BASE_MODEL_MISMATCH",
    }


@pytest.mark.asyncio
async def test_activate_adapter_handler_requires_runtime_model_for_chat_runtime_deploy() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager

    validate_mock = AsyncMock(return_value=None)
    activate_mock = Mock(return_value={"success": True})
    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=validate_mock,
        activate_adapter=activate_mock,
    )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.activate_adapter_handler(
            request=SimpleNamespace(
                adapter_id="a1",
                runtime_id="ollama",
                model_id="",
                deploy_to_chat_runtime=True,
            ),
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == {
        "adapter_id": "a1",
        "error": "ADAPTER_RUNTIME_MODEL_REQUIRED",
        "message": "Select runtime model before adapter activation.",
        "requested_runtime_id": "ollama",
        "reason_code": "ADAPTER_RUNTIME_MODEL_REQUIRED",
    }
    validate_mock.assert_not_awaited()
    activate_mock.assert_not_called()


@pytest.mark.asyncio
async def test_start_training_handler_maps_runtime_error_to_structured_http_500() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    academy.DATASET_REQUIRED_DETAIL = "dataset required"
    academy._get_gpu_habitat = lambda: SimpleNamespace(
        run_training_job=Mock(side_effect=RuntimeError("boom"))
    )
    academy._get_model_manager = lambda: None
    academy._is_model_trainable = lambda _name: True
    academy._save_job_to_history = Mock()
    academy._update_job_in_history = Mock()
    academy.academy_training = SimpleNamespace(
        resolve_dataset_path=Mock(return_value="dataset.jsonl"),
        ensure_trainable_base_model=Mock(return_value="gemma-3-4b-it"),
        validate_runtime_compatibility_for_base_model=AsyncMock(return_value=None),
        resolve_training_base_model=AsyncMock(return_value="google/gemma-3-4b-it"),
        build_job_record=Mock(
            return_value={
                "job_id": "training_20260307_000000",
                "parameters": {
                    "requested_runtime_id": "ollama",
                    "requested_base_model": "gemma-3-4b-it",
                },
            }
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.start_training_handler(
            request=SimpleNamespace(
                base_model="gemma-3-4b-it",
                runtime_id="ollama",
                dataset_path=None,
                lora_rank=8,
                learning_rate=0.0002,
                num_epochs=2,
                max_seq_length=1024,
                batch_size=1,
            ),
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "TRAINING_START_FAILED",
        "message": "Failed to start training: boom",
        "reason_code": "TRAINING_START_FAILED",
        "requested_runtime_id": "ollama",
        "requested_base_model": "gemma-3-4b-it",
    }
    academy.academy_training.build_job_record.assert_called_once()
    assert (
        academy.academy_training.build_job_record.call_args.kwargs[
            "training_base_model"
        ]
        == "google/gemma-3-4b-it"
    )


@pytest.mark.asyncio
async def test_activate_adapter_handler_maps_missing_adapter_to_http_404() -> None:
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager

    academy.academy_models = SimpleNamespace(
        validate_adapter_runtime_compatibility=AsyncMock(
            side_effect=FileNotFoundError("Adapter not found")
        ),
        activate_adapter=lambda **_kwargs: {"success": True},
    )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.activate_adapter_handler(
            request=SimpleNamespace(
                adapter_id="missing",
                runtime_id="ollama",
                model_id="gemma3:latest",
                deploy_to_chat_runtime=True,
            ),
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Adapter not found"


@pytest.mark.asyncio
async def test_academy_status_handler_gpu_info_fallback_on_error() -> None:
    academy = _build_academy_base()
    academy._get_lessons_store = lambda: SimpleNamespace(
        get_statistics=lambda: {"total_lessons": 3}
    )
    academy._get_gpu_habitat = lambda: SimpleNamespace(
        is_gpu_available=lambda: True,
        get_gpu_info=lambda: (_ for _ in ()).throw(RuntimeError("gpu err")),
    )
    academy._load_jobs_history = lambda: [
        {"status": "running"},
        {"status": "failed"},
        {"status": "finished"},
    ]
    academy._get_professor = lambda: object()
    academy._get_dataset_curator = lambda: object()
    academy._get_model_manager = lambda: object()

    payload = route_handlers.academy_status_handler(academy=academy)
    assert payload["gpu"]["available"] is True
    assert payload["jobs"]["running"] == 1
    assert payload["jobs"]["failed"] == 1


def test_list_dataset_uploads_and_delete_upload_paths() -> None:
    academy = _build_academy_base()
    academy._load_uploads_metadata = lambda: [
        {
            "id": "f1",
            "name": "a.txt",
            "size_bytes": 1,
            "mime": "text/plain",
            "created_at": "2026-03-01T00:00:00",
            "status": "ready",
            "records_estimate": 0,
            "sha256": "x",
            "error": None,
        }
    ]
    uploads = route_handlers.list_dataset_uploads_handler(academy=academy)
    assert uploads and uploads[0].id == "f1"

    academy.require_localhost_request = lambda _req: None
    academy._get_uploads_dir = lambda: "/tmp"
    academy._check_path_traversal = lambda _path: True
    academy._delete_upload_metadata = lambda _fid: None
    academy.academy_uploads = SimpleNamespace(
        delete_upload_file=lambda **_kwargs: {"success": True, "deleted": "f1"}
    )
    deleted = route_handlers.delete_dataset_upload_handler(
        file_id="f1",
        req=SimpleNamespace(),
        academy=academy,
    )
    assert deleted["success"] is True

    academy.academy_uploads = SimpleNamespace(
        delete_upload_file=lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad"))
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.delete_dataset_upload_handler(
            file_id="f1",
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 400

    academy.academy_uploads = SimpleNamespace(
        delete_upload_file=lambda **_kwargs: (_ for _ in ()).throw(FileNotFoundError())
    )
    with pytest.raises(HTTPException) as exc:
        route_handlers.delete_dataset_upload_handler(
            file_id="f1",
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 404


def test_list_dataset_uploads_maps_generic_error_to_structured_http_500() -> None:
    academy = _build_academy_base()
    academy._load_uploads_metadata = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(HTTPException) as exc:
        route_handlers.list_dataset_uploads_handler(academy=academy)

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "DATASET_UPLOADS_LIST_FAILED",
        "message": "Failed to list dataset uploads: boom",
        "reason_code": "DATASET_UPLOADS_LIST_FAILED",
    }


def test_conversion_listing_download_and_stream_helpers() -> None:
    academy = _build_academy_base()
    academy._resolve_user_id = lambda _req: "u1"
    academy._get_user_conversion_workspace = lambda _uid: {"base_dir": "/tmp/u1"}
    academy._user_conversion_metadata_lock = lambda *_args, **_kwargs: None
    academy._load_user_conversion_metadata = lambda *_args, **_kwargs: []
    academy._normalize_conversion_item = lambda item: item
    academy.academy_conversion = SimpleNamespace(
        list_conversion_files_for_user=lambda **_kwargs: {
            "user_id": "u1",
            "workspace_dir": "/tmp/u1",
            "source_files": [],
            "converted_files": [],
        },
        guess_media_type=lambda _path: "text/plain",
    )
    listed = route_handlers.list_dataset_conversion_files_handler(
        req=SimpleNamespace(),
        academy=academy,
    )
    assert listed.user_id == "u1"

    academy._check_path_traversal = lambda _fid: True
    academy.require_localhost_request = lambda _req: None
    academy._resolve_existing_user_file = lambda _req, file_id: (
        {"name": "x.txt"},
        Path(__file__),
    )
    file_resp = route_handlers.download_dataset_conversion_file_handler(
        file_id="f1",
        req=SimpleNamespace(),
        academy=academy,
    )
    assert isinstance(file_resp, FileResponse)

    academy._check_path_traversal = lambda _fid: False
    with pytest.raises(HTTPException) as exc:
        route_handlers.download_dataset_conversion_file_handler(
            file_id="bad",
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 400

    academy._check_path_traversal = lambda _fid: True
    academy.academy_training = SimpleNamespace(
        find_job_or_404=lambda *_args, **_kwargs: {"job_name": "job-1"}
    )
    academy._load_jobs_history = lambda: []
    academy._stream_training_logs_events = lambda **_kwargs: iter(())
    stream_resp = route_handlers.stream_training_logs_handler(
        job_id="job-1", academy=academy
    )
    assert isinstance(stream_resp, StreamingResponse)


def test_list_dataset_conversion_files_maps_generic_error_to_structured_http_500() -> (
    None
):
    academy = _build_academy_base()
    academy._resolve_user_id = lambda _req: "u1"
    academy._get_user_conversion_workspace = lambda _uid: {"base_dir": "/tmp/u1"}
    academy._user_conversion_metadata_lock = lambda *_args, **_kwargs: None
    academy._load_user_conversion_metadata = lambda *_args, **_kwargs: []
    academy._normalize_conversion_item = lambda item: item
    academy.academy_conversion = SimpleNamespace(
        list_conversion_files_for_user=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
    )

    with pytest.raises(HTTPException) as exc:
        route_handlers.list_dataset_conversion_files_handler(
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "DATASET_CONVERSION_LIST_FAILED",
        "message": "Failed to list conversion files: boom",
        "reason_code": "DATASET_CONVERSION_LIST_FAILED",
    }


@pytest.mark.asyncio
async def test_preview_dataset_conversion_file_maps_generic_error_to_structured_http_500() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    academy._check_path_traversal = lambda _fid: True
    text_file = Path("/tmp/test-preview.txt")
    academy._resolve_existing_user_file = lambda _req, file_id: (
        {"name": "x.txt"},
        text_file,
    )
    academy.academy_conversion = SimpleNamespace(
        read_text_preview=AsyncMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(HTTPException) as exc:
        await route_handlers.preview_dataset_conversion_file_handler(
            file_id="f1",
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "DATASET_FILE_PREVIEW_FAILED",
        "message": "Failed to preview conversion file: boom",
        "reason_code": "DATASET_FILE_PREVIEW_FAILED",
        "file_id": "f1",
    }


def test_download_dataset_conversion_file_maps_generic_error_to_structured_http_500() -> (
    None
):
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    academy._check_path_traversal = lambda _fid: True
    academy._resolve_existing_user_file = lambda _req, file_id: (
        {"name": "x.txt"},
        Path(__file__),
    )
    academy.academy_conversion = SimpleNamespace(
        guess_media_type=lambda _path: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(HTTPException) as exc:
        route_handlers.download_dataset_conversion_file_handler(
            file_id="f1",
            req=SimpleNamespace(),
            academy=academy,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "DATASET_FILE_DOWNLOAD_FAILED",
        "message": "Failed to download conversion file: boom",
        "reason_code": "DATASET_FILE_DOWNLOAD_FAILED",
        "file_id": "f1",
    }


def test_deactivate_adapter_handler_respects_query_flag_false() -> None:
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager
    academy.academy_models = SimpleNamespace(
        deactivate_adapter=lambda **kwargs: kwargs,
    )
    req = SimpleNamespace(query_params={"deploy_to_chat_runtime": "false"})
    payload = route_handlers.deactivate_adapter_handler(req=req, academy=academy)
    assert payload["mgr"] is manager
    assert payload["deploy_to_chat_runtime"] is False


def test_deactivate_adapter_handler_defaults_query_flag_to_true() -> None:
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    manager = object()
    academy._get_model_manager = lambda: manager
    academy.academy_models = SimpleNamespace(
        deactivate_adapter=lambda **kwargs: kwargs,
    )
    req = SimpleNamespace(query_params={})
    payload = route_handlers.deactivate_adapter_handler(req=req, academy=academy)
    assert payload["mgr"] is manager
    assert payload["deploy_to_chat_runtime"] is True


def test_deactivate_adapter_handler_maps_generic_error_to_structured_http_500() -> None:
    academy = _build_academy_base()
    academy.require_localhost_request = lambda _req: None
    academy._get_model_manager = lambda: object()
    academy.academy_models = SimpleNamespace(
        deactivate_adapter=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        route_handlers.deactivate_adapter_handler(
            req=SimpleNamespace(query_params={}),
            academy=academy,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == {
        "error": "ADAPTER_DEACTIVATION_FAILED",
        "message": "Failed to deactivate adapter: boom",
        "reason_code": "ADAPTER_DEACTIVATION_FAILED",
    }
