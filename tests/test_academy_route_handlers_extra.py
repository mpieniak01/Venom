from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from venom_core.api.schemas.academy import DatasetScopeRequest
from venom_core.services.academy import route_handlers


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

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


@pytest.mark.asyncio
async def test_list_adapters_handler_maps_generic_error_to_http_500() -> None:
    academy = _build_academy_base()
    academy._get_model_manager = lambda: object()
    academy.academy_models = SimpleNamespace(
        list_adapters=AsyncMock(side_effect=RuntimeError("boom"))
    )
    with pytest.raises(HTTPException) as exc:
        await route_handlers.list_adapters_handler(academy=academy)
    assert exc.value.status_code == 500


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
