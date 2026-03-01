from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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
        route_handlers.activate_adapter_handler(
            request=SimpleNamespace(adapter_id="a1"),
            req=SimpleNamespace(),
            academy=academy,
        )
    assert exc.value.status_code == 503


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


@pytest.mark.asyncio
async def test_get_trainable_models_handler_delegates_to_service() -> None:
    academy = _build_academy_base()
    academy._get_model_manager = lambda: object()
    academy.academy_models = SimpleNamespace(
        list_trainable_models=AsyncMock(return_value=[{"id": "m1"}])
    )
    result = await route_handlers.get_trainable_models_handler(academy=academy)
    assert result == [{"id": "m1"}]
