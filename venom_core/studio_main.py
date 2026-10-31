"""Standalone Studio ASGI entrypoint; does not import the Full application.

Select ``venom_core.studio_main:app`` in the same environment/storage profile.
Only the HTTP surface and startup services differ. Route handlers are shared.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from venom_core.api.middleware.http_audit import audit_http_requests
from venom_core.api.middleware.traffic_control import TrafficControlMiddleware
from venom_core.api.studio_routes import (
    configure_studio_dependencies,
    include_studio_routes,
)
from venom_core.api.transport_access import TransportAccessMiddleware
from venom_core.bootstrap.studio_runtime import StudioRuntime
from venom_core.version import APP_VERSION


def create_app(runtime_factory: Callable[[], Any] = StudioRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime = runtime_factory()
        application.state.studio_runtime = runtime
        try:
            await runtime.start(application)
            configure_studio_dependencies(application, runtime)
            yield
        finally:
            await runtime.close()

    application = FastAPI(title="Venom Studio", version=APP_VERSION, lifespan=lifespan)
    application.add_middleware(TrafficControlMiddleware)
    application.add_middleware(TransportAccessMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"{scheme}://{host}:{port}"
            for scheme in ("http", "https")
            for host in ("localhost", "127.0.0.1")
            for port in (3000, 3100)
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "x-session-id"],
    )
    application.middleware("http")(audit_http_requests)
    include_studio_routes(application)
    return application


app = create_app()
