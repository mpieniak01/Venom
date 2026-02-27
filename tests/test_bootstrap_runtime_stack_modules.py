from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from venom_core.bootstrap import agents as bootstrap_agents
from venom_core.bootstrap import runtime_stack as stack


def _logger() -> SimpleNamespace:
    return SimpleNamespace(info=Mock(), warning=Mock(), error=Mock(), debug=Mock())


def test_initialize_calendar_skill_branches():
    logger = _logger()
    settings = SimpleNamespace(ENABLE_GOOGLE_CALENDAR=False)
    assert (
        bootstrap_agents.initialize_calendar_skill(settings=settings, logger=logger)
        is None
    )

    module = ModuleType("venom_core.execution.skills.google_calendar_skill")

    class _Skill:
        def __init__(self):
            self.credentials_available = False

    module.GoogleCalendarSkill = _Skill
    with patch.dict("sys.modules", {module.__name__: module}):
        settings = SimpleNamespace(ENABLE_GOOGLE_CALENDAR=True)
        skill = bootstrap_agents.initialize_calendar_skill(
            settings=settings,
            logger=logger,
        )
        assert skill is not None


def test_initialize_academy_branches():
    logger = _logger()
    settings = SimpleNamespace(ENABLE_ACADEMY=False, ACADEMY_ENABLE_GPU=False)
    professor, curator, habitat = bootstrap_agents.initialize_academy(
        settings=settings,
        logger=logger,
        lessons_store=object(),
        model_manager=None,
        get_orchestrator_kernel=lambda: None,
    )
    assert (professor, curator, habitat) == (None, None, None)

    prof_mod = ModuleType("venom_core.agents.professor")
    gpu_mod = ModuleType("venom_core.infrastructure.gpu_habitat")
    cur_mod = ModuleType("venom_core.learning.dataset_curator")

    class _Professor:
        def __init__(self, **_kwargs):
            pass

    class _GPU:
        def __init__(self, **_kwargs):
            pass

    class _Cur:
        def __init__(self, **_kwargs):
            pass

    prof_mod.Professor = _Professor
    gpu_mod.GPUHabitat = _GPU
    cur_mod.DatasetCurator = _Cur
    with patch.dict(
        "sys.modules",
        {
            prof_mod.__name__: prof_mod,
            gpu_mod.__name__: gpu_mod,
            cur_mod.__name__: cur_mod,
        },
    ):
        settings = SimpleNamespace(ENABLE_ACADEMY=True, ACADEMY_ENABLE_GPU=False)
        model_manager = SimpleNamespace(restore_active_adapter=Mock(return_value=False))
        professor, curator, habitat = bootstrap_agents.initialize_academy(
            settings=settings,
            logger=logger,
            lessons_store=object(),
            model_manager=model_manager,
            get_orchestrator_kernel=lambda: object(),
        )
        assert professor is not None
        assert curator is not None
        assert habitat is not None


@pytest.mark.asyncio
async def test_initialize_node_manager_and_memory_stores(tmp_path: Path):
    logger = _logger()
    settings = SimpleNamespace(
        ENABLE_NEXUS=True,
        NEXUS_SHARED_TOKEN=SimpleNamespace(get_secret_value=lambda: "tok"),
        NEXUS_HEARTBEAT_TIMEOUT=10,
        APP_PORT=9000,
    )

    nm_module = ModuleType("venom_core.core.node_manager")

    class _NM:
        def __init__(self, **_kwargs):
            self.started = False

        async def start(self):
            self.started = True

    nm_module.NodeManager = _NM
    with patch.dict("sys.modules", {nm_module.__name__: nm_module}):
        nm = await stack.initialize_node_manager(settings=settings, logger=logger)
        assert nm is not None and nm.started is True

    vec_cls = Mock(return_value=SimpleNamespace())
    graph_store = SimpleNamespace(load_graph=Mock())
    graph_cls = Mock(return_value=graph_store)
    lessons_obj = SimpleNamespace(lessons=[1, 2])
    lessons_cls = Mock(return_value=lessons_obj)
    orch = SimpleNamespace(lessons_store=None)
    vector, graph, lessons = stack.initialize_memory_stores(
        settings=settings,
        logger=logger,
        vector_store_cls=vec_cls,
        graph_store_cls=graph_cls,
        lessons_store_cls=lessons_cls,
        orchestrator=orch,
    )
    assert vector is not None and graph is graph_store and lessons is lessons_obj
    assert orch.lessons_store is lessons_obj


@pytest.mark.asyncio
async def test_runtime_stack_scheduler_audio_and_aux_paths(tmp_path: Path):
    logger = _logger()
    settings = SimpleNamespace(
        ENABLE_MEMORY_CONSOLIDATION=True,
        MEMORY_CONSOLIDATION_INTERVAL_MINUTES=30,
        ENABLE_HEALTH_CHECKS=True,
        HEALTH_CHECK_INTERVAL_MINUTES=15,
        ENABLE_RUNTIME_RETENTION_CLEANUP=True,
        RUNTIME_RETENTION_DAYS=7,
        RUNTIME_RETENTION_TARGETS=["data"],
        REPO_ROOT=str(tmp_path),
        RUNTIME_RETENTION_INTERVAL_MINUTES=60,
        ENABLE_AUDIO_INTERFACE=True,
        WHISPER_MODEL_SIZE="tiny",
        TTS_MODEL_PATH="tts.bin",
        AUDIO_DEVICE="cpu",
        ENABLE_IOT_BRIDGE=True,
        RIDER_PI_PASSWORD=SimpleNamespace(get_secret_value=lambda: "pw"),
        RIDER_PI_HOST="127.0.0.1",
        RIDER_PI_PORT=22,
        RIDER_PI_USERNAME="u",
        RIDER_PI_PROTOCOL="ssh",
        VAD_THRESHOLD=0.3,
        SILENCE_DURATION=1.2,
        ENABLE_PROACTIVE_MODE=False,
    )
    event_broadcaster = object()
    clear_called = {"ok": False}

    class _Scheduler:
        def __init__(self, **_kwargs):
            self.jobs = []

        async def start(self):
            return None

        def add_interval_job(self, **kwargs):
            self.jobs.append(kwargs)

    class _Jobs:
        @staticmethod
        async def consolidate_memory(_ev):
            return None

        @staticmethod
        async def check_health(_ev):
            return None

        @staticmethod
        def cleanup_runtime_files(**_kwargs):
            return None

        @staticmethod
        def should_run_runtime_retention_now(**_kwargs):
            return True

    tracer = SimpleNamespace(clear_old_traces=Mock())
    scheduler, startup_task = await stack.initialize_background_scheduler(
        settings=settings,
        logger=logger,
        event_broadcaster=event_broadcaster,
        vector_store=object(),
        request_tracer=tracer,
        background_scheduler_cls=_Scheduler,
        job_scheduler_module=_Jobs,
        asyncio_module=asyncio,
        clear_startup_runtime_retention_task=lambda: clear_called.__setitem__(
            "ok", True
        ),
    )
    assert scheduler is not None
    assert startup_task is not None
    await startup_task
    assert clear_called["ok"] is True
    assert len(scheduler.jobs) >= 3

    audio = stack.initialize_audio_engine_if_enabled(
        settings=settings,
        logger=logger,
        audio_engine_cls=lambda **kwargs: kwargs,
    )
    assert audio["device"] == "cpu"

    class _Bridge:
        def __init__(self, **_kwargs):
            pass

        async def connect(self):
            return True

    bridge = await stack.initialize_hardware_bridge_if_enabled(
        settings=settings,
        logger=logger,
        extract_secret_value_fn=lambda secret: secret.get_secret_value(),
        hardware_bridge_cls=_Bridge,
    )
    assert bridge is not None

    kernel_module = ModuleType("venom_core.execution.kernel_builder")

    class _KB:
        def build_kernel(self):
            return object()

    kernel_module.KernelBuilder = _KB
    with patch.dict("sys.modules", {kernel_module.__name__: kernel_module}):
        operator = stack.initialize_operator_agent_if_possible(
            settings=settings,
            logger=logger,
            current_audio_engine=audio,
            current_hardware_bridge=bridge,
            operator_agent_cls=lambda **kwargs: kwargs,
        )
    assert operator["hardware_bridge"] is bridge

    handler = stack.initialize_audio_stream_handler_if_possible(
        settings=settings,
        logger=logger,
        current_audio_engine=audio,
        current_operator_agent=operator,
        audio_stream_handler_cls=lambda **kwargs: kwargs,
    )
    assert handler["silence_duration"] == 1.2

    shadow = await stack.initialize_shadow_stack(
        settings=settings,
        logger=logger,
        orchestrator=None,
        lessons_store=None,
        event_broadcaster=None,
        system_log_event_type="SYS",
    )
    assert shadow == (None, None, None)


@pytest.mark.asyncio
async def test_initialize_documenter_and_watcher_paths(tmp_path: Path):
    logger = _logger()

    class _Documenter:
        def __init__(self, **_kwargs):
            pass

        def handle_code_change(self, *_args, **_kwargs):
            return None

    class _Watcher:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            return None

    documenter, watcher = await stack.initialize_documenter_and_watcher(
        workspace_path=tmp_path,
        git_skill=object(),
        skill_manager=object(),
        event_broadcaster=object(),
        logger=logger,
        documenter_agent_cls=_Documenter,
        file_watcher_cls=_Watcher,
    )
    assert documenter is not None
    assert watcher is not None
