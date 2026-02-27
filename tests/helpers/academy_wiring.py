"""Shared test wiring helpers for Academy route tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


def make_academy_dependencies(**overrides: Any) -> dict[str, Any]:
    """Build default dependency set for Academy router tests."""
    defaults: dict[str, Any] = {
        "professor": MagicMock(),
        "dataset_curator": MagicMock(),
        "gpu_habitat": MagicMock(training_containers={}),
        "lessons_store": MagicMock(),
        "model_manager": MagicMock(),
    }
    defaults.update(overrides)
    return defaults


def build_academy_app(**overrides: Any) -> FastAPI:
    """Build FastAPI app with wired Academy router dependencies."""
    app = FastAPI()
    academy_routes.set_dependencies(**make_academy_dependencies(**overrides))
    app.include_router(academy_routes.router)
    return app


@contextmanager
def academy_client(
    *, bypass_localhost: bool = True, **overrides: Any
) -> Iterator[TestClient]:
    """Yield TestClient for Academy app with optional localhost guard bypass."""
    app = build_academy_app(**overrides)
    if bypass_localhost:
        with patch(
            "venom_core.api.routes.academy.require_localhost_request",
            return_value=None,
        ):
            yield TestClient(app)
    else:
        yield TestClient(app)
