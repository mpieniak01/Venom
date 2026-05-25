import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.main as main_module


def test_setup_router_dependencies_wires_globals(monkeypatch):
    calls = {}

    def make_dummy(name):
        def set_dependencies(*args, **kwargs):
            calls[name] = {"args": args, "kwargs": kwargs}

        return SimpleNamespace(set_dependencies=set_dependencies, router=None)

    monkeypatch.setattr(main_module, "feedback_routes", make_dummy("feedback"))
    monkeypatch.setattr(main_module, "queue_routes", make_dummy("queue"))
    monkeypatch.setattr(main_module, "metrics_routes", make_dummy("metrics"))
    monkeypatch.setattr(main_module, "memory_routes", make_dummy("memory"))
    monkeypatch.setattr(main_module, "git_routes", make_dummy("git"))
    monkeypatch.setattr(main_module, "knowledge_routes", make_dummy("knowledge"))
    monkeypatch.setattr(main_module, "agents_routes", make_dummy("agents"))
    monkeypatch.setattr(main_module, "system_deps", make_dummy("system_deps"))
    monkeypatch.setattr(main_module, "nodes_routes", make_dummy("nodes"))
    monkeypatch.setattr(main_module, "strategy_routes", make_dummy("strategy"))
    monkeypatch.setattr(main_module, "models_routes", make_dummy("models"))
    monkeypatch.setattr(main_module, "flow_routes", make_dummy("flow"))
    monkeypatch.setattr(main_module, "benchmark_routes", make_dummy("benchmark"))
    monkeypatch.setattr(main_module, "calendar_routes", make_dummy("calendar"))

    monkeypatch.setattr(main_module, "orchestrator", object())
    monkeypatch.setattr(main_module, "state_manager", object())
    monkeypatch.setattr(main_module, "request_tracer", object())
    monkeypatch.setattr(main_module, "vector_store", object())
    monkeypatch.setattr(main_module, "git_skill", object())
    monkeypatch.setattr(main_module, "graph_store", object())
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "gardener_agent", object())
    monkeypatch.setattr(main_module, "shadow_agent", object())
    monkeypatch.setattr(main_module, "file_watcher", object())
    monkeypatch.setattr(main_module, "documenter_agent", object())
    monkeypatch.setattr(main_module, "background_scheduler", object())
    monkeypatch.setattr(
        main_module, "service_monitor", SimpleNamespace(set_orchestrator=lambda x: None)
    )
    monkeypatch.setattr(main_module, "llm_controller", object())
    monkeypatch.setattr(main_module, "model_manager", object())
    monkeypatch.setattr(main_module, "node_manager", object())
    monkeypatch.setattr(main_module, "benchmark_service", object())
    monkeypatch.setattr(main_module, "google_calendar_skill", object())
    monkeypatch.setattr(main_module, "model_registry", object())
    monkeypatch.setattr(main_module, "hardware_bridge", object())

    main_module.setup_router_dependencies()

    assert calls["feedback"]["args"][0] is main_module.orchestrator
    assert calls["feedback"]["args"][1] is main_module.state_manager
    assert calls["feedback"]["args"][2] is main_module.request_tracer
    assert calls["system_deps"]["args"][0] is main_module.background_scheduler
    assert calls["system_deps"]["args"][1] is main_module.service_monitor
    assert calls["models"]["kwargs"]["model_registry"] is main_module.model_registry


def _install_academy_dummy_modules(monkeypatch):
    professor_mod = ModuleType("venom_core.agents.professor")
    dataset_mod = ModuleType("venom_core.learning.dataset_curator")
    habitat_mod = ModuleType("venom_core.infrastructure.gpu_habitat")

    class DummyProfessor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummyDatasetCurator:
        def __init__(self, lessons_store):
            self.lessons_store = lessons_store

    class DummyGPUHabitat:
        def __init__(self, enable_gpu):
            self.enable_gpu = enable_gpu

    professor_mod.Professor = DummyProfessor
    dataset_mod.DatasetCurator = DummyDatasetCurator
    habitat_mod.GPUHabitat = DummyGPUHabitat

    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)
    monkeypatch.setitem(sys.modules, "venom_core.learning.dataset_curator", dataset_mod)
    monkeypatch.setitem(
        sys.modules, "venom_core.infrastructure.gpu_habitat", habitat_mod
    )


def test_initialize_academy_restores_active_adapter(monkeypatch):
    _install_academy_dummy_modules(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(
        main_module.SETTINGS, "ACADEMY_ENABLE_GPU", False, raising=False
    )
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "orchestrator", SimpleNamespace(kernel=object()))
    model_manager = MagicMock()
    model_manager.restore_active_adapter.return_value = True
    monkeypatch.setattr(main_module, "model_manager", model_manager)

    main_module._initialize_academy()

    assert main_module.dataset_curator is not None
    assert main_module.gpu_habitat is not None
    assert main_module.professor is not None
    model_manager.restore_active_adapter.assert_called_once()


def test_initialize_academy_restore_error_falls_back(monkeypatch):
    _install_academy_dummy_modules(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module.SETTINGS, "ACADEMY_ENABLE_GPU", True, raising=False)
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "orchestrator", SimpleNamespace(kernel=object()))
    model_manager = MagicMock()
    model_manager.restore_active_adapter.side_effect = RuntimeError("restore failed")
    monkeypatch.setattr(main_module, "model_manager", model_manager)

    main_module._initialize_academy()

    assert main_module.professor is not None
    model_manager.restore_active_adapter.assert_called_once()


def test_initialize_academy_disabled_returns_early(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", False, raising=False)
    main_module._initialize_academy()


def test_get_orchestrator_kernel_prefers_task_dispatcher_kernel(monkeypatch):
    sentinel_dispatcher_kernel = object()
    sentinel_orchestrator_kernel = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(kernel=sentinel_dispatcher_kernel),
            kernel=sentinel_orchestrator_kernel,
        ),
    )

    assert main_module._get_orchestrator_kernel() is sentinel_dispatcher_kernel


def test_get_orchestrator_kernel_falls_back_to_orchestrator_kernel(monkeypatch):
    sentinel_orchestrator_kernel = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(), kernel=sentinel_orchestrator_kernel
        ),
    )

    assert main_module._get_orchestrator_kernel() is sentinel_orchestrator_kernel


def test_get_orchestrator_kernel_returns_none_when_orchestrator_missing(monkeypatch):
    monkeypatch.setattr(main_module, "orchestrator", None)
    assert main_module._get_orchestrator_kernel() is None


def test_get_orchestrator_skill_manager_from_task_dispatcher(monkeypatch):
    sentinel_skill_manager = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(skill_manager=sentinel_skill_manager)
        ),
    )

    assert main_module._get_orchestrator_skill_manager() is sentinel_skill_manager


def test_get_orchestrator_skill_manager_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace()),
    )

    assert main_module._get_orchestrator_skill_manager() is None


def test_select_startup_model_prefers_first_available_when_no_match():
    selected = main_module._select_startup_model(
        {"model-a", "model-b"},
        desired_model="missing-desired",
        previous_model="missing-previous",
    )
    assert selected in {"model-a", "model-b"}


def test_audio_decoder_chain_and_effective_profile_branches():
    assert main_module._normalize_audio_decoder_chain(None) == []
    assert main_module._normalize_audio_decoder_chain(123) == []
    assert main_module._normalize_audio_decoder_chain(
        ["gemma_native", "whisper", "unknown", "faster_whisper", "whisper"]
    ) == ["gemma_native", "faster_whisper"]

    assert (
        main_module._effective_audio_decoder_chain("chat_tekstowy", "hybrid", []) == []
    )
    assert main_module._effective_audio_decoder_chain("auto", "gemma_native", []) == [
        "gemma_native"
    ]
    assert main_module._effective_audio_decoder_chain("auto", "faster_whisper", []) == [
        "faster_whisper"
    ]
    assert main_module._effective_audio_decoder_chain("auto", "hybrid", []) == [
        "gemma_native",
        "faster_whisper",
    ]
    assert main_module._effective_audio_decoder_chain("auto", "auto", []) == []
    assert main_module._effective_audio_decoder_chain(
        "runtime_lokalny", "hybrid", ["gemma_native", "faster_whisper"]
    ) == ["faster_whisper"]
    assert main_module._effective_audio_decoder_chain(
        "venom-agent", "gemma_native", ["gemma_native"]
    ) == ["faster_whisper"]


def test_validate_voice_route_contract_all_error_branches():
    with pytest.raises(main_module.HTTPException) as exc_chat:
        main_module._validate_voice_route_contract(
            voice_route_profile="chat_tekstowy",
            audio_decoder_profile="hybrid",
            audio_decoder_chain=["gemma_native"],
        )
    assert exc_chat.value.status_code == 400

    with pytest.raises(main_module.HTTPException) as exc_gemma_empty:
        main_module._validate_voice_route_contract(
            voice_route_profile="gemma4",
            audio_decoder_profile="auto",
            audio_decoder_chain=[],
        )
    assert exc_gemma_empty.value.status_code == 400

    with pytest.raises(main_module.HTTPException) as exc_gemma_first:
        main_module._validate_voice_route_contract(
            voice_route_profile="gemma4",
            audio_decoder_profile="faster_whisper",
            audio_decoder_chain=["faster_whisper"],
        )
    assert exc_gemma_first.value.status_code == 400

    with pytest.raises(main_module.HTTPException) as exc_local_profile:
        main_module._validate_voice_route_contract(
            voice_route_profile="runtime_lokalny",
            audio_decoder_profile="gemma_native",
            audio_decoder_chain=["faster_whisper"],
        )
    assert exc_local_profile.value.status_code == 400

    with pytest.raises(main_module.HTTPException) as exc_local_chain:
        main_module._validate_voice_route_contract(
            voice_route_profile="venom-agent",
            audio_decoder_profile="auto",
            audio_decoder_chain=["gemma_native", "faster_whisper"],
        )
    assert exc_local_chain.value.status_code == 400

    # happy path branch for contract validator
    main_module._validate_voice_route_contract(
        voice_route_profile="auto",
        audio_decoder_profile="auto",
        audio_decoder_chain=[],
    )


@pytest.mark.asyncio
async def test_update_audio_route_profile_uses_snapshot_defaults(monkeypatch):
    updates: list[dict[str, object]] = []

    def _update_config(payload):
        updates.append(payload)
        return {"success": True}

    import venom_core.services.config_manager as config_manager_module

    monkeypatch.setattr(
        config_manager_module,
        "config_manager",
        SimpleNamespace(update_config=_update_config),
    )
    monkeypatch.setattr(main_module.SETTINGS, "VOICE_ROUTE_PROFILE", "auto")
    monkeypatch.setattr(main_module.SETTINGS, "AUDIO_DECODER_PROFILE", "hybrid")
    monkeypatch.setattr(
        main_module.SETTINGS, "AUDIO_DECODER_CHAIN", "gemma_native,faster_whisper"
    )

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    payload = main_module.AudioRouteProfileUpdateRequest(
        voice_route_profile=None,
        audio_decoder_profile=None,
        audio_decoder_chain=None,
    )
    result = await main_module.update_audio_route_profile(payload, request)

    assert result["status"] == "success"
    assert updates[-1]["VOICE_ROUTE_PROFILE"] == "auto"
    assert updates[-1]["AUDIO_DECODER_PROFILE"] == "hybrid"
    assert updates[-1]["AUDIO_DECODER_CHAIN"] == "gemma_native,faster_whisper"


@pytest.mark.asyncio
async def test_update_audio_route_profile_raises_500_on_non_dict_result(monkeypatch):
    import venom_core.services.config_manager as config_manager_module

    monkeypatch.setattr(
        config_manager_module,
        "config_manager",
        SimpleNamespace(update_config=lambda _payload: None),
    )
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    payload = main_module.AudioRouteProfileUpdateRequest(
        voice_route_profile="auto",
        audio_decoder_profile="auto",
        audio_decoder_chain=[],
    )

    with pytest.raises(main_module.HTTPException) as excinfo:
        await main_module.update_audio_route_profile(payload, request)

    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_gemma4_audio_enabled(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            runtime_id="multi_runtime@localhost",
            provider="multi_runtime",
            model_name="google/gemma-4-E2B-it",
            endpoint="http://127.0.0.1:8014",
            config_hash="cfg-a",
        ),
    )
    monkeypatch.setattr(
        main_module,
        "SETTINGS",
        SimpleNamespace(
            GEMMA4_AUDIO_ENABLED=True,
            GEMMA4_AUDIO_SUPPORTS_AUDIO=True,
            GEMMA4_AUDIO_SUPPORTS_TEXT=True,
            GEMMA4_AUDIO_MODEL_ID="google/gemma-4-E2B-it",
            GEMMA4_AUDIO_ENDPOINT="http://127.0.0.1:8014",
        ),
    )

    snapshot = await main_module._build_voice_runtime_snapshot()

    assert snapshot["runtime_capabilities"]["compatibility_profile"] == (
        "multi_runtime_native"
    )
    assert snapshot["voice_pipeline"]["stt"] == "native_audio"


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_gemma4_audio_metadata_only(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            runtime_id="multi_runtime@localhost",
            provider="multi_runtime",
            model_name="",
            endpoint="",
            config_hash="cfg-b",
        ),
    )
    monkeypatch.setattr(
        main_module,
        "SETTINGS",
        SimpleNamespace(
            GEMMA4_AUDIO_ENABLED=False,
            GEMMA4_AUDIO_SUPPORTS_AUDIO=True,
            GEMMA4_AUDIO_SUPPORTS_TEXT=True,
            GEMMA4_AUDIO_MODEL_ID="google/gemma-4-E4B-it",
            GEMMA4_AUDIO_ENDPOINT="http://127.0.0.1:8014",
        ),
    )

    snapshot = await main_module._build_voice_runtime_snapshot()

    assert snapshot["model_name"] == "google/gemma-4-E4B-it"
    assert snapshot["endpoint"] == "http://127.0.0.1:8014"
    assert snapshot["runtime_capabilities"]["probes"]["health"]["reason"] == (
        "runtime_not_enabled"
    )
    assert snapshot["voice_pipeline"]["stt"] == "faster_whisper"


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_ollama_cache_hit(monkeypatch):
    runtime = SimpleNamespace(
        runtime_id="ollama@localhost",
        provider="ollama",
        model_name="qwen2.5-coder:3b",
        endpoint="http://localhost:11434",
        config_hash="cfg-hit",
    )
    monkeypatch.setattr(main_module, "get_active_llm_runtime", lambda: runtime)
    cache_key = "|".join(
        [runtime.provider, runtime.model_name, runtime.endpoint, runtime.config_hash]
    )
    main_module._voice_runtime_snapshot_cache["entry"] = {
        "key": cache_key,
        "snapshot": {
            "runtime_id": runtime.runtime_id,
            "provider": runtime.provider,
            "model_name": runtime.model_name,
            "voice_pipeline": {"stt": "cached"},
        },
        "captured_at": 10**9,
    }

    probe_mock = AsyncMock()
    monkeypatch.setattr(main_module, "probe_ollama_runtime_capabilities", probe_mock)
    monkeypatch.setattr(
        main_module.asyncio,
        "get_running_loop",
        lambda: SimpleNamespace(time=lambda: 10**9),
    )

    snapshot = await main_module._build_voice_runtime_snapshot()

    assert snapshot["voice_pipeline"]["stt"] == "cached"
    probe_mock.assert_not_called()


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_ollama_stale_fallback(monkeypatch):
    runtime = SimpleNamespace(
        runtime_id="ollama@localhost",
        provider="ollama",
        model_name="qwen2.5-coder:3b",
        endpoint="http://localhost:11434",
        config_hash="cfg-stale",
    )
    monkeypatch.setattr(main_module, "get_active_llm_runtime", lambda: runtime)
    cache_key = "|".join(
        [runtime.provider, runtime.model_name, runtime.endpoint, runtime.config_hash]
    )
    main_module._voice_runtime_snapshot_cache["entry"] = {
        "key": cache_key,
        "snapshot": {
            "runtime_id": runtime.runtime_id,
            "provider": runtime.provider,
            "model_name": runtime.model_name,
            "voice_pipeline": {"stt": "old"},
        },
        "captured_at": 0.0,
    }

    monkeypatch.setattr(
        main_module, "OllamaClient", lambda endpoint: SimpleNamespace(endpoint=endpoint)
    )
    monkeypatch.setattr(
        main_module,
        "probe_ollama_runtime_capabilities",
        AsyncMock(side_effect=RuntimeError("probe down")),
    )
    monkeypatch.setattr(
        main_module.asyncio,
        "get_running_loop",
        lambda: SimpleNamespace(time=lambda: 1000.0),
    )

    snapshot = await main_module._build_voice_runtime_snapshot()

    assert snapshot["stale"] is True
    assert snapshot["stale_reason"] == "probe down"


def _patch_setup_routes(monkeypatch):
    def make_dummy():
        return SimpleNamespace(
            set_dependencies=lambda *args, **kwargs: None, router=None
        )

    monkeypatch.setattr(main_module, "tasks_routes", make_dummy())
    monkeypatch.setattr(main_module, "feedback_routes", make_dummy())
    monkeypatch.setattr(main_module, "queue_routes", make_dummy())
    monkeypatch.setattr(main_module, "metrics_routes", make_dummy())
    monkeypatch.setattr(main_module, "memory_routes", make_dummy())
    monkeypatch.setattr(main_module, "memory_projection_routes", make_dummy())
    monkeypatch.setattr(main_module, "git_routes", make_dummy())
    monkeypatch.setattr(main_module, "knowledge_routes", make_dummy())
    monkeypatch.setattr(main_module, "agents_routes", make_dummy())
    monkeypatch.setattr(main_module, "academy_routes", make_dummy())
    monkeypatch.setattr(main_module, "system_deps", make_dummy())
    monkeypatch.setattr(main_module, "nodes_routes", make_dummy())
    monkeypatch.setattr(main_module, "strategy_routes", make_dummy())
    monkeypatch.setattr(main_module, "models_routes", make_dummy())
    monkeypatch.setattr(main_module, "flow_routes", make_dummy())
    monkeypatch.setattr(main_module, "benchmark_routes", make_dummy())
    monkeypatch.setattr(main_module, "calendar_routes", make_dummy())


def _patch_setup_runtime_globals(monkeypatch):
    monkeypatch.setattr(main_module, "state_manager", object())
    monkeypatch.setattr(main_module, "request_tracer", object())
    monkeypatch.setattr(main_module, "vector_store", object())
    monkeypatch.setattr(main_module, "graph_store", object())
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "session_store", object())
    monkeypatch.setattr(main_module, "git_skill", object())
    monkeypatch.setattr(main_module, "gardener_agent", object())
    monkeypatch.setattr(main_module, "shadow_agent", object())
    monkeypatch.setattr(main_module, "file_watcher", object())
    monkeypatch.setattr(main_module, "documenter_agent", object())
    monkeypatch.setattr(main_module, "background_scheduler", object())
    monkeypatch.setattr(
        main_module,
        "service_monitor",
        SimpleNamespace(set_orchestrator=lambda *_: None),
    )
    monkeypatch.setattr(main_module, "llm_controller", object())
    monkeypatch.setattr(main_module, "model_manager", object())
    monkeypatch.setattr(main_module, "node_manager", object())
    monkeypatch.setattr(main_module, "benchmark_service", object())
    monkeypatch.setattr(main_module, "google_calendar_skill", object())
    monkeypatch.setattr(main_module, "model_registry", object())
    monkeypatch.setattr(main_module, "hardware_bridge", object())
    monkeypatch.setattr(main_module, "token_economist", None)


def test_setup_router_dependencies_retries_professor_init_success(monkeypatch):
    _patch_setup_routes(monkeypatch)
    _patch_setup_runtime_globals(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module, "professor", None)
    monkeypatch.setattr(main_module, "dataset_curator", object())
    monkeypatch.setattr(main_module, "gpu_habitat", object())
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace(kernel=object())),
    )

    professor_mod = ModuleType("venom_core.agents.professor")

    class DummyProfessor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    professor_mod.Professor = DummyProfessor
    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)

    main_module.setup_router_dependencies()

    assert isinstance(main_module.professor, DummyProfessor)
    assert (
        main_module.professor.kwargs["dataset_curator"] is main_module.dataset_curator
    )


def test_setup_router_dependencies_retries_professor_init_handles_exception(
    monkeypatch,
):
    _patch_setup_routes(monkeypatch)
    _patch_setup_runtime_globals(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module, "professor", None)
    monkeypatch.setattr(main_module, "dataset_curator", object())
    monkeypatch.setattr(main_module, "gpu_habitat", object())
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace(kernel=object())),
    )

    professor_mod = ModuleType("venom_core.agents.professor")

    class FailingProfessor:
        def __init__(self, **_kwargs):
            raise RuntimeError("boom")

    professor_mod.Professor = FailingProfessor
    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)

    main_module.setup_router_dependencies()

    assert main_module.professor is None


def test_initialize_academy_self_learning_init_error_sets_none(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module, "vector_store", object())
    monkeypatch.setattr(main_module, "model_manager", object())
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(
        main_module,
        "initialize_academy",
        lambda **_kwargs: (object(), object(), object()),
    )

    failing_module = ModuleType("venom_core.services.academy.self_learning_service")

    class FailingSelfLearningService:
        def __init__(self, **_kwargs):
            raise RuntimeError("init failed")

    failing_module.SelfLearningService = FailingSelfLearningService
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.academy.self_learning_service",
        failing_module,
    )

    main_module._initialize_academy()
    assert main_module.self_learning_service is None


def test_setup_router_dependencies_ignores_self_learning_refresh_error(monkeypatch):
    _patch_setup_routes(monkeypatch)
    _patch_setup_runtime_globals(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", False, raising=False)
    monkeypatch.setattr(main_module, "professor", None)
    monkeypatch.setattr(main_module, "dataset_curator", None)
    monkeypatch.setattr(main_module, "gpu_habitat", None)
    monkeypatch.setattr(main_module, "lessons_store", None)
    monkeypatch.setattr(main_module, "orchestrator", None)
    monkeypatch.setattr(
        main_module,
        "self_learning_service",
        SimpleNamespace(
            set_runtime_dependencies=MagicMock(side_effect=RuntimeError("boom"))
        ),
    )

    main_module.setup_router_dependencies()


def test_initialize_ghost_agent_if_enabled_returns_when_feature_disabled(monkeypatch):
    monkeypatch.setattr(
        main_module.SETTINGS, "ENABLE_GHOST_AGENT", False, raising=False
    )
    sentinel = object()
    monkeypatch.setattr(main_module, "ghost_agent", sentinel)

    def _kernel_should_not_be_called():
        raise AssertionError("_get_orchestrator_kernel should not be called")

    monkeypatch.setattr(
        main_module, "_get_orchestrator_kernel", _kernel_should_not_be_called
    )

    main_module._initialize_ghost_agent_if_enabled()

    assert main_module.ghost_agent is sentinel


def test_initialize_ghost_agent_if_enabled_returns_when_kernel_missing(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_GHOST_AGENT", True, raising=False)
    sentinel = object()
    monkeypatch.setattr(main_module, "ghost_agent", sentinel)
    monkeypatch.setattr(main_module, "_get_orchestrator_kernel", lambda: None)

    main_module._initialize_ghost_agent_if_enabled()

    assert main_module.ghost_agent is sentinel


def test_initialize_ghost_agent_if_enabled_sets_ghost_agent(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_GHOST_AGENT", True, raising=False)
    kernel = object()
    monkeypatch.setattr(main_module, "_get_orchestrator_kernel", lambda: kernel)

    class DummyGhostAgent:
        def __init__(self, *, kernel):
            self.kernel = kernel

    monkeypatch.setattr(main_module, "GhostAgent", DummyGhostAgent)
    monkeypatch.setattr(main_module, "ghost_agent", None)

    main_module._initialize_ghost_agent_if_enabled()

    assert isinstance(main_module.ghost_agent, DummyGhostAgent)
    assert main_module.ghost_agent.kernel is kernel


def test_initialize_ghost_agent_if_enabled_handles_init_exception(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_GHOST_AGENT", True, raising=False)
    monkeypatch.setattr(main_module, "_get_orchestrator_kernel", lambda: object())

    class FailingGhostAgent:
        def __init__(self, *, kernel):  # noqa: ARG002
            raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "GhostAgent", FailingGhostAgent)
    monkeypatch.setattr(main_module, "ghost_agent", object())

    main_module._initialize_ghost_agent_if_enabled()

    assert main_module.ghost_agent is None


@pytest.mark.asyncio
async def test_lifespan_invokes_ghost_init_step(monkeypatch):
    monkeypatch.setattr(main_module, "validate_environment_policy", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_observability", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_model_services", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_calendar_skill", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_node_manager", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_orchestrator", lambda: None)
    monkeypatch.setattr(main_module, "_ensure_storage_dirs", lambda: "/tmp/venom-tests")
    monkeypatch.setattr(main_module, "_initialize_memory_stores", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_academy", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_token_economist", lambda: None)
    monkeypatch.setattr(main_module, "_initialize_gardener_and_git", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_background_scheduler", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_documenter_and_watcher", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_avatar_stack", AsyncMock())
    monkeypatch.setattr(main_module, "_initialize_shadow_stack", AsyncMock())
    ghost_init = MagicMock()
    monkeypatch.setattr(main_module, "_initialize_ghost_agent_if_enabled", ghost_init)
    setup_routes = MagicMock()
    monkeypatch.setattr(main_module, "setup_router_dependencies", setup_routes)
    monkeypatch.setattr(main_module, "_ensure_local_llm_ready", AsyncMock())
    shutdown_runtime = AsyncMock()
    monkeypatch.setattr(main_module, "_shutdown_runtime_components", shutdown_runtime)
    monkeypatch.setattr(main_module, "audio_engine", None)

    app = SimpleNamespace(state=SimpleNamespace())
    async with main_module.lifespan(app):
        if hasattr(app.state, "startup_llm_task"):
            await app.state.startup_llm_task

    ghost_init.assert_called_once()
    setup_routes.assert_called_once()
    shutdown_runtime.assert_awaited_once()


async def _done_task() -> None:
    return None


def test_initialize_background_scheduler_retention_recent_no_startup_task(monkeypatch):
    class DummyScheduler:
        def __init__(self, event_broadcaster):
            self.event_broadcaster = event_broadcaster
            self.job_ids = []

        async def start(self):
            return None

        def add_interval_job(self, func, minutes, job_id, description):
            self.job_ids.append(job_id)

    monkeypatch.setattr(main_module, "BackgroundScheduler", DummyScheduler)
    monkeypatch.setattr(main_module.job_scheduler, "consolidate_memory", AsyncMock())
    monkeypatch.setattr(main_module.job_scheduler, "check_health", AsyncMock())
    monkeypatch.setattr(
        main_module.job_scheduler, "cleanup_runtime_files", lambda **_: {}
    )
    monkeypatch.setattr(
        main_module.asyncio, "to_thread", AsyncMock(side_effect=[False])
    )
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_MEMORY_CONSOLIDATION", False)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_HEALTH_CHECKS", False)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_RUNTIME_RETENTION_CLEANUP", True)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_DAYS", 7)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_INTERVAL_MINUTES", 11)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_TARGETS", ["./logs"])
    monkeypatch.setattr(main_module.SETTINGS, "REPO_ROOT", ".")
    monkeypatch.setattr(main_module, "request_tracer", None)
    monkeypatch.setattr(main_module, "vector_store", None)
    monkeypatch.setattr(main_module, "event_broadcaster", object())
    monkeypatch.setattr(main_module, "startup_runtime_retention_task", None)

    import asyncio

    asyncio.run(main_module._initialize_background_scheduler())

    assert "cleanup_runtime_files" in main_module.background_scheduler.job_ids
    assert main_module.startup_runtime_retention_task is None


def test_shutdown_runtime_components_clears_startup_retention_task(monkeypatch):
    import asyncio

    async def _runner() -> None:
        task = asyncio.create_task(_done_task())
        monkeypatch.setattr(main_module, "startup_runtime_retention_task", task)

        monkeypatch.setattr(
            main_module.llm_simple_routes,
            "release_onnx_simple_client",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(
            main_module.tasks_routes,
            "release_onnx_task_runtime",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(main_module, "request_tracer", None)
        monkeypatch.setattr(main_module, "desktop_sensor", None)
        monkeypatch.setattr(main_module, "shadow_agent", None)
        monkeypatch.setattr(main_module, "node_manager", None)
        monkeypatch.setattr(main_module, "background_scheduler", None)
        monkeypatch.setattr(main_module, "file_watcher", None)
        monkeypatch.setattr(main_module, "gardener_agent", None)
        monkeypatch.setattr(main_module, "hardware_bridge", None)
        monkeypatch.setattr(
            main_module,
            "state_manager",
            SimpleNamespace(shutdown=AsyncMock()),
        )

        await main_module._shutdown_runtime_components()
        assert main_module.startup_runtime_retention_task is None

    asyncio.run(_runner())


def test_clear_startup_runtime_retention_task_sets_none(monkeypatch):
    monkeypatch.setattr(main_module, "startup_runtime_retention_task", object())
    main_module._clear_startup_runtime_retention_task()
    assert main_module.startup_runtime_retention_task is None


def test_shutdown_runtime_components_stops_all_components_when_set(monkeypatch):
    import asyncio

    async def _runner() -> None:
        done_task = asyncio.create_task(_done_task())
        await done_task
        monkeypatch.setattr(main_module, "startup_runtime_retention_task", done_task)

        monkeypatch.setattr(
            main_module.llm_simple_routes,
            "release_onnx_simple_client",
            MagicMock(return_value=None),
        )
        monkeypatch.setattr(
            main_module.tasks_routes,
            "release_onnx_task_runtime",
            MagicMock(return_value=None),
        )

        monkeypatch.setattr(
            main_module,
            "request_tracer",
            SimpleNamespace(stop_watchdog=AsyncMock()),
        )
        monkeypatch.setattr(
            main_module, "desktop_sensor", SimpleNamespace(stop=AsyncMock())
        )
        monkeypatch.setattr(
            main_module, "shadow_agent", SimpleNamespace(stop=AsyncMock())
        )
        monkeypatch.setattr(
            main_module, "node_manager", SimpleNamespace(stop=AsyncMock())
        )
        monkeypatch.setattr(
            main_module,
            "background_scheduler",
            SimpleNamespace(stop=AsyncMock()),
        )
        monkeypatch.setattr(
            main_module, "file_watcher", SimpleNamespace(stop=AsyncMock())
        )
        monkeypatch.setattr(
            main_module, "gardener_agent", SimpleNamespace(stop=AsyncMock())
        )
        monkeypatch.setattr(
            main_module,
            "hardware_bridge",
            SimpleNamespace(disconnect=AsyncMock()),
        )
        monkeypatch.setattr(
            main_module,
            "state_manager",
            SimpleNamespace(shutdown=AsyncMock()),
        )

        await main_module._shutdown_runtime_components()

        main_module.request_tracer.stop_watchdog.assert_awaited_once()
        main_module.desktop_sensor.stop.assert_awaited_once()
        main_module.shadow_agent.stop.assert_awaited_once()
        main_module.node_manager.stop.assert_awaited_once()
        main_module.background_scheduler.stop.assert_awaited_once()
        main_module.file_watcher.stop.assert_awaited_once()
        main_module.gardener_agent.stop.assert_awaited_once()
        main_module.hardware_bridge.disconnect.assert_awaited_once()
        main_module.state_manager.shutdown.assert_awaited_once()
        assert main_module.startup_runtime_retention_task is None

    asyncio.run(_runner())
