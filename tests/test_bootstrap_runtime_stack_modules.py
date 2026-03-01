from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


@pytest.mark.asyncio
async def test_initialize_shadow_stack_enabled_paths_and_callbacks():
    logger = _logger()
    event_broadcaster = SimpleNamespace(broadcast_event=AsyncMock())
    settings = SimpleNamespace(
        ENABLE_PROACTIVE_MODE=True,
        SHADOW_CONFIDENCE_THRESHOLD=0.42,
        ENABLE_DESKTOP_SENSOR=True,
        SHADOW_PRIVACY_FILTER=True,
    )
    orchestrator = SimpleNamespace(goal_store={"ok": True})

    class _Suggestion:
        title = "Fix"
        message = "Do it"
        action_payload = {"type": "task_update"}

        def to_dict(self):
            return {"title": self.title}

    class _ShadowAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False

        async def start(self):
            self.started = True

        async def analyze_sensor_data(self, _data):
            return _Suggestion()

    class _DesktopSensor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False

        async def start(self):
            self.started = True

    class _Notifier:
        def __init__(self, webhook_handler):
            self.webhook_handler = webhook_handler
            self.send_toast = AsyncMock()

    kernel_module = ModuleType("venom_core.execution.kernel_builder")
    shadow_module = ModuleType("venom_core.agents.shadow")
    desktop_module = ModuleType("venom_core.perception.desktop_sensor")
    notifier_module = ModuleType("venom_core.ui.notifier")

    class _KB:
        def build_kernel(self):
            return object()

    kernel_module.KernelBuilder = _KB
    shadow_module.ShadowAgent = _ShadowAgent
    desktop_module.DesktopSensor = _DesktopSensor
    notifier_module.Notifier = _Notifier

    with patch.dict(
        "sys.modules",
        {
            kernel_module.__name__: kernel_module,
            shadow_module.__name__: shadow_module,
            desktop_module.__name__: desktop_module,
            notifier_module.__name__: notifier_module,
        },
    ):
        shadow_agent, desktop_sensor, notifier = await stack.initialize_shadow_stack(
            settings=settings,
            logger=logger,
            orchestrator=orchestrator,
            lessons_store=object(),
            event_broadcaster=event_broadcaster,
            system_log_event_type="SYS",
        )

    assert shadow_agent is not None and shadow_agent.started is True
    assert desktop_sensor is not None and desktop_sensor.started is True
    assert notifier is not None

    clipboard_cb = desktop_sensor.kwargs["clipboard_callback"]
    await clipboard_cb({"type": "clipboard"})
    notifier.send_toast.assert_awaited_once()
    assert event_broadcaster.broadcast_event.await_count >= 1

    await notifier.webhook_handler({"type": "unknown"})
    assert event_broadcaster.broadcast_event.await_count >= 2


@pytest.mark.asyncio
async def test_initialize_shadow_stack_returns_none_on_exception():
    logger = _logger()
    settings = SimpleNamespace(
        ENABLE_PROACTIVE_MODE=True,
        SHADOW_CONFIDENCE_THRESHOLD=0.1,
        ENABLE_DESKTOP_SENSOR=False,
        SHADOW_PRIVACY_FILTER=False,
    )

    shadow_module = ModuleType("venom_core.agents.shadow")
    shadow_module.ShadowAgent = None  # will fail at ShadowAgent(...)
    kernel_module = ModuleType("venom_core.execution.kernel_builder")
    kernel_module.KernelBuilder = lambda: SimpleNamespace(build_kernel=lambda: object())
    desktop_module = ModuleType("venom_core.perception.desktop_sensor")
    desktop_module.DesktopSensor = object
    notifier_module = ModuleType("venom_core.ui.notifier")
    notifier_module.Notifier = lambda webhook_handler: SimpleNamespace(
        webhook_handler=webhook_handler, send_toast=AsyncMock()
    )

    with patch.dict(
        "sys.modules",
        {
            shadow_module.__name__: shadow_module,
            kernel_module.__name__: kernel_module,
            desktop_module.__name__: desktop_module,
            notifier_module.__name__: notifier_module,
        },
    ):
        result = await stack.initialize_shadow_stack(
            settings=settings,
            logger=logger,
            orchestrator=SimpleNamespace(goal_store=None),
            lessons_store=None,
            event_broadcaster=SimpleNamespace(broadcast_event=AsyncMock()),
            system_log_event_type="SYS",
        )

    assert result == (None, None, None)


@pytest.mark.asyncio
async def test_runtime_stack_guard_branches_for_disabled_or_invalid_config(
    tmp_path: Path,
):
    logger = _logger()

    settings_disabled = SimpleNamespace(ENABLE_NEXUS=False)
    assert (
        await stack.initialize_node_manager(
            settings=settings_disabled,
            logger=logger,
        )
        is None
    )

    settings_empty_token = SimpleNamespace(
        ENABLE_NEXUS=True,
        NEXUS_SHARED_TOKEN=SimpleNamespace(get_secret_value=lambda: ""),
        NEXUS_HEARTBEAT_TIMEOUT=10,
        APP_PORT=8000,
    )
    assert (
        await stack.initialize_node_manager(
            settings=settings_empty_token,
            logger=logger,
        )
        is None
    )

    settings_iot = SimpleNamespace(
        ENABLE_IOT_BRIDGE=True,
        RIDER_PI_PASSWORD=SimpleNamespace(get_secret_value=lambda: "pw"),
        RIDER_PI_HOST="127.0.0.1",
        RIDER_PI_PORT=22,
        RIDER_PI_USERNAME="u",
        RIDER_PI_PROTOCOL="ssh",
    )

    class _Bridge:
        def __init__(self, **_kwargs):
            pass

        async def connect(self):
            return False

    bridge = await stack.initialize_hardware_bridge_if_enabled(
        settings=settings_iot,
        logger=logger,
        extract_secret_value_fn=lambda secret: secret.get_secret_value(),
        hardware_bridge_cls=_Bridge,
    )
    assert bridge is not None

    settings_audio = SimpleNamespace(
        ENABLE_AUDIO_INTERFACE=False,
        VAD_THRESHOLD=0.5,
        SILENCE_DURATION=1.0,
    )
    assert (
        stack.initialize_operator_agent_if_possible(
            settings=settings_audio,
            logger=logger,
            current_audio_engine=None,
            current_hardware_bridge=None,
            operator_agent_cls=lambda **_kwargs: object(),
        )
        is None
    )
    assert (
        stack.initialize_audio_stream_handler_if_possible(
            settings=settings_audio,
            logger=logger,
            current_audio_engine=None,
            current_operator_agent=None,
            audio_stream_handler_cls=lambda **_kwargs: object(),
        )
        is None
    )


def test_bootstrap_agents_import_and_exception_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
):
    logger = _logger()

    calendar_mod = ModuleType("venom_core.execution.skills.google_calendar_skill")

    class _BrokenCalendarSkill:
        def __init__(self):
            raise RuntimeError("init-boom")

    calendar_mod.GoogleCalendarSkill = _BrokenCalendarSkill
    with patch.dict("sys.modules", {calendar_mod.__name__: calendar_mod}):
        assert (
            bootstrap_agents.initialize_calendar_skill(
                settings=SimpleNamespace(ENABLE_GOOGLE_CALENDAR=True),
                logger=logger,
            )
            is None
        )

    class _FailingModelManager:
        def restore_active_adapter(self):
            raise RuntimeError("restore-boom")

    prof_mod = ModuleType("venom_core.agents.professor")
    gpu_mod = ModuleType("venom_core.infrastructure.gpu_habitat")
    cur_mod = ModuleType("venom_core.learning.dataset_curator")

    class _Professor:
        def __init__(self, **_kwargs):
            pass

    class _GPU:
        def __init__(self, **_kwargs):
            pass

    class _Curator:
        def __init__(self, **_kwargs):
            pass

    prof_mod.Professor = _Professor
    gpu_mod.GPUHabitat = _GPU
    cur_mod.DatasetCurator = _Curator

    with patch.dict(
        "sys.modules",
        {
            prof_mod.__name__: prof_mod,
            gpu_mod.__name__: gpu_mod,
            cur_mod.__name__: cur_mod,
        },
    ):
        professor, curator, habitat = bootstrap_agents.initialize_academy(
            settings=SimpleNamespace(ENABLE_ACADEMY=True, ACADEMY_ENABLE_GPU=True),
            logger=logger,
            lessons_store=object(),
            model_manager=_FailingModelManager(),
            get_orchestrator_kernel=lambda: None,
        )

    assert professor is None
    assert curator is not None
    assert habitat is not None
