"""Demand-driven wiring of existing host services for the Studio API.

Same SETTINGS, state, SessionStore and runtime admission as Full. No new storage
root, queue, model process, scheduler, watcher or optional module is introduced.
Normal/MAF necessarily construct the existing heavier Orchestrator on first use.
Legacy Direct memory ingestion similarly constructs the existing VectorStore.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from venom_core.api import dependencies as api_deps
from venom_core.config import SETTINGS
from venom_core.services.background_priority import run_drainable_thread
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class LazyAudioEngine:
    """Construct configured audio on first admitted STT/TTS, never warm up at boot."""

    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._instance: Any = None
        self._lock = asyncio.Lock()
        self._closed = False

    def _create(self) -> Any:
        self._instance = self._factory()
        return self._instance

    async def close(self) -> None:
        self._closed = True
        async with self._lock:
            pass

    async def _get(self) -> Any:
        async with self._lock:
            if self._closed:
                raise HTTPException(503, {"reason_code": "audio_not_ready"})
            if self._instance is None:
                self._instance = await run_drainable_thread(self._create)
                if self._instance is None:
                    raise HTTPException(503, {"reason_code": "audio_not_ready"})
            return self._instance

    async def transcribe_checked(self, *args: Any, **kwargs: Any) -> Any:
        return await (await self._get()).transcribe_checked(*args, **kwargs)

    async def speak(self, text: str) -> Any:
        return await (await self._get()).speak(text)

    @property
    def voice(self) -> Any:
        return getattr(self._instance, "voice", None)


class StudioRuntime:
    def __init__(self) -> None:
        self.state_manager: Any = None
        self.session_store: Any = None
        self.request_tracer: Any = None
        self.service_monitor: Any = None
        self.controller: Any = None
        self.model_manager: Any = None
        self.model_registry: Any = None
        self.orchestrator: Any = None
        self.vector_store: Any = None
        self._lock = asyncio.Lock()
        self._restore: list[Callable[[], Any]] = []
        self._closed = False
        self.audio_engine: LazyAudioEngine | None = None
        self._closing: asyncio.Task[None] | None = None
        self._owned_runtime = False
        self.on_dependencies_changed: Callable[[], None] = lambda: None

    def register_cleanup(self, callback: Callable[[], Any]) -> None:
        """Allow the API boundary to restore its own bindings after shutdown."""
        self._restore.append(callback)

    async def start(self, app: FastAPI) -> None:
        from venom_core.core.environment_policy import validate_environment_policy
        from venom_core.core.llm_server_controller import LlmServerController
        from venom_core.core.metrics import init_metrics_collector
        from venom_core.core.model_manager import ModelManager
        from venom_core.core.model_registry import ModelRegistry
        from venom_core.core.permission_guard import permission_guard
        from venom_core.core.service_monitor import (
            ServiceHealthMonitor,
            ServiceRegistry,
        )
        from venom_core.core.state_manager import StateManager
        from venom_core.core.tracer import RequestTracer
        from venom_core.services.session_store import SessionStore

        validate_environment_policy()
        init_metrics_collector()
        self._owned_runtime = True
        # Preserve same-process test/embedding owners. Production runs one API app.
        for name in (
            "state_manager",
            "session_store",
            "request_tracer",
            "orchestrator",
            "vector_store",
        ):
            setter = getattr(api_deps, "set_" + name)
            previous = getattr(api_deps, "_" + name)
            self._restore.append(partial(setter, previous))
        self._restore.append(
            partial(
                setattr,
                permission_guard,
                "_current_level",
                permission_guard._current_level,
            )
        )
        self._restore.append(
            partial(permission_guard.set_state_manager, permission_guard._state_manager)
        )
        self.state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)
        self.session_store = SessionStore()
        self.request_tracer = RequestTracer(
            trace_file_path=str(Path(SETTINGS.MEMORY_ROOT) / "request_traces.json")
        )
        api_deps.set_state_manager(self.state_manager)
        api_deps.set_session_store(self.session_store)
        api_deps.set_request_tracer(self.request_tracer)
        permission_guard.set_state_manager(self.state_manager)
        self.service_monitor = ServiceHealthMonitor(ServiceRegistry())
        self.controller = LlmServerController(SETTINGS)
        self.model_manager = ModelManager(models_dir=str(SETTINGS.ACADEMY_MODELS_DIR))
        self.model_registry = ModelRegistry()
        await self.request_tracer.start_watchdog()
        self.audio_engine = (
            LazyAudioEngine(self._create_audio)
            if SETTINGS.ENABLE_AUDIO_INTERFACE
            else None
        )
        app.state.audio_engine = self.audio_engine

    @staticmethod
    def _create_audio() -> Any:
        from venom_core.bootstrap.runtime_stack import (
            initialize_audio_engine_if_enabled,
        )
        from venom_core.perception.audio_engine import AudioEngine

        return initialize_audio_engine_if_enabled(
            settings=SETTINGS, logger=logger, audio_engine_cls=AudioEngine
        )

    def _create_vector_store(self) -> None:
        from venom_core.memory.vector_store import VectorStore

        self.vector_store = VectorStore()

    async def get_vector_store(self) -> Any:
        async with self._lock:
            if self._closed:
                raise HTTPException(503, "studio_runtime_stopping")
            if self.vector_store is None:
                await run_drainable_thread(self._create_vector_store)
            api_deps.set_vector_store(self.vector_store)
            return self.vector_store

    def _create_orchestrator(self) -> None:
        from venom_core.core.orchestrator import Orchestrator

        if self.vector_store is None:
            self._create_vector_store()
        self.orchestrator = Orchestrator(
            self.state_manager,
            session_store=self.session_store,
            request_tracer=self.request_tracer,
            vector_store=self.vector_store,
        )

    async def get_orchestrator(self) -> Any:
        async with self._lock:
            if self._closed:
                raise HTTPException(503, "studio_runtime_stopping")
            if self.orchestrator is None:
                await run_drainable_thread(self._create_orchestrator)
            api_deps.set_orchestrator(self.orchestrator)
            api_deps.set_vector_store(self.vector_store)
            self.on_dependencies_changed()
            return self.orchestrator

    async def close(self) -> None:
        # A second stop (or caller cancellation) must still await native cleanup.
        if self._closing is None:
            self._closing = asyncio.create_task(self._close_once())
        try:
            await asyncio.shield(self._closing)
        except asyncio.CancelledError:
            while not self._closing.done():
                with suppress(asyncio.CancelledError):
                    try:
                        await asyncio.shield(self._closing)
                    except Exception:
                        break
            if not self._closing.cancelled():
                self._closing.exception()
            raise

    async def _close_once(self) -> None:
        self._closed = True
        try:
            if self.audio_engine is not None:
                await self.audio_engine.close()
            async with self._lock:
                if self.orchestrator is not None:
                    active = tuple(self.orchestrator.active_tasks.values())
                    await self.orchestrator.emergency_stop()
                    await asyncio.gather(*active, return_exceptions=True)
            if not self._owned_runtime:
                return
            from venom_core.services.llm_simple_service import (
                release_onnx_simple_client,
            )
            from venom_core.services.model_resources import (
                prepare_registered_models,
                release_barrier,
                release_registered_models,
                wait_for_model_work,
            )

            await run_drainable_thread(release_onnx_simple_client)
            failures = await prepare_registered_models()
            with release_barrier():
                await run_drainable_thread(wait_for_model_work)
                results = await run_drainable_thread(release_registered_models)
                if failures or any(not item.get("verified") for item in results):
                    raise RuntimeError("studio_model_resources_not_released")
        finally:
            try:
                if self.request_tracer is not None:
                    try:
                        await self.request_tracer.stop_watchdog()
                    finally:
                        await self.request_tracer.shutdown()
            finally:
                try:
                    if self.state_manager is not None:
                        await self.state_manager.shutdown()
                finally:
                    for restore in reversed(self._restore):
                        restore()
                    self._restore.clear()
